import importlib.util
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from email.message import Message
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from controld_sync import (
    SchemaError,
    SyncError,
    __version__,
    _rule_key,
    _validate_api_base,
    content_hash,
    load_cache,
    load_config,
    load_domains,
    load_folder_source,
    load_folders,
    save_cache,
)
from controld_sync.api import ControlDClient
from controld_sync.sources import parse_folder_rules
from controld_sync.sync import (
    _backup_name,
    find_folder_overlaps,
    resolve_profiles,
    select_non_overlapping_folders,
    sync_profile,
)


def _load_validate_config():
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_config.py"
    spec = importlib.util.spec_from_file_location("validate_config", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate


validate = _load_validate_config()


class LoadDomainsTests(unittest.TestCase):
    def test_version_is_available(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_loads_nested_json_and_normalizes_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "list.json"
            path.write_text(
                json.dumps(
                    {
                        "entries": [{"hostname": "Tracker.Example."}, {"domain": "||ads.example^"}],
                        "domains": ["*.cdn.example"],
                    }
                )
            )
            self.assertEqual(
                load_domains(path), ["*.cdn.example", "ads.example", "tracker.example"]
            )

    def test_directory_combines_files_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.json").write_text('["a.example"]')
            (root / "b.json").write_text('["a.example", "b.example"]')
            self.assertEqual(load_domains(root), ["a.example", "b.example"])

    def test_reads_control_d_folder_export_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom-name.json"
            path.write_text(
                json.dumps(
                    {
                        "group": {"group": "Badware Hoster"},
                        "rules": [{"PK": "bad.example", "action": {"do": 0}}],
                    }
                )
            )
            self.assertEqual(load_folders(path), {"Badware Hoster": {"bad.example"}})

    def test_accepts_control_d_selector_rules(self):
        self.assertEqual(_rule_key("@RU"), "@RU")
        self.assertEqual(_rule_key("@CN"), "@CN")
        self.assertEqual(_rule_key("*.actor"), "*.ACTOR")
        self.assertEqual(_rule_key("*.edu.eu"), "*.edu.eu")
        self.assertEqual(_rule_key("*.co.com"), "*.co.com")
        self.assertEqual(_rule_key("777*.livepartners.com"), "777*.livepartners.com")
        self.assertEqual(_rule_key("actor"), "actor")

    def test_preserves_control_d_rule_actions(self):
        rules = parse_folder_rules(
            {
                "group": {"group": "Apple PR allow", "action": {"do": 1, "status": 1}},
                "rules": [{"PK": "mask.icloud.com", "action": {"do": 1, "status": 1}}],
            },
            "allow",
        )
        self.assertEqual(rules, {"mask.icloud.com": (1, 1)})

    def test_rejects_malformed_control_d_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(
                json.dumps({"group": {"group": "Broken"}, "rules": [{"host": "x.example"}]})
            )
            with self.assertRaises(SchemaError):
                load_folders(path)

    def test_cache_is_hashable_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            digest = content_hash(["B.example", "a.example"])
            save_cache(path, {"source": digest})
            self.assertEqual(load_cache(path)["source"], digest)

    def test_loads_toml_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "[settings]\ndry_run = true\n"
                '[profiles]\nnames = ["Kids"]\n'
                '[folders]\n"Ads" = "ads.json"\n'
                '[profile_folders]\nKids = ["Ads"]\n'
            )
            config = load_config(path)
            self.assertEqual(config["profiles"]["names"], ["Kids"])
            self.assertEqual(config["profile_folders"]["Kids"], ["Ads"])

    def test_api_base_requires_https_except_loopback(self):
        self.assertEqual(
            _validate_api_base("https://api.controld.com/"), "https://api.controld.com"
        )
        self.assertEqual(_validate_api_base("http://127.0.0.1:8000"), "http://127.0.0.1:8000")
        with self.assertRaises(SyncError):
            _validate_api_base("http://example.com")
        with self.assertRaises(SyncError):
            _validate_api_base("https://example.com")

    def test_cache_accepts_timestamped_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            save_cache(path, {"profile:folder": {"hash": "abc", "updated_at": "now"}})
            self.assertEqual(load_cache(path)["profile:folder"]["hash"], "abc")

    def test_backup_names_are_at_most_32_characters(self):
        self.assertLessEqual(len(_backup_name("a" * 100, "OLD")), 32)

    def test_get_retries_but_post_does_not(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"{}"

        retry = urllib.error.HTTPError("x", 503, "busy", Message(), io.BytesIO(b""))
        calls = []

        def opener(request, timeout):
            calls.append(request.method)
            if len(calls) == 1:
                raise retry
            return Response()

        client = ControlDClient("secret", base_url="https://api.controld.com", sleep=lambda _: None)
        with patch("controld_sync.api._open", opener):
            client.request("/profiles")
        self.assertEqual(calls, ["GET", "GET"])
        calls.clear()
        with patch("controld_sync.api._open", opener):
            with self.assertRaises(SyncError):
                client.request("/groups", "POST", {})
        self.assertEqual(calls, ["POST"])

    def test_sync_smoke_exercises_profile_lookup_and_rule_writes(self):
        responses = {
            ("GET", "/profiles"): {"body": {"profiles": [{"name": "Kids", "PK": "profile-1"}]}},
            ("GET", "/profiles/profile-1/groups"): {
                "body": {"groups": [{"name": "Ads", "PK": "group-1"}]}
            },
            ("GET", "/profiles/profile-1/rules/group-1"): {
                "body": {"rules": [{"PK": "old.example", "action": {"do": 0, "status": 1}}]}
            },
        }
        requests = []

        class Response:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.payload

        def opener(request, timeout):
            path = request.full_url.removeprefix("https://api.controld.test")
            method = request.method
            body = json.loads(request.data) if request.data else None
            requests.append((method, path, body, request.headers["Authorization"]))
            if (method, path) in responses:
                return Response(responses[(method, path)])
            if method == "POST" and path == "/profiles/profile-1/rules":
                return Response({})
            if method == "DELETE" and path == "/profiles/profile-1/rules/old.example":
                return Response({})
            raise AssertionError(f"unexpected Control D request: {method} {path}")

        client = ControlDClient(
            "secret",
            base_url="https://api.controld.test",
            sleep=lambda _: None,
        )
        with patch("controld_sync.api._open", opener):
            profiles = resolve_profiles(client, ["Kids"])
            result = sync_profile(
                client,
                profiles["Kids"],
                "Ads",
                {"new.example": (0, 1)},
                apply=True,
                atomic=False,
            )

        self.assertEqual(result, (1, 1))
        self.assertEqual(
            [(method, path) for method, path, _, _ in requests],
            [
                ("GET", "/profiles"),
                ("GET", "/profiles/profile-1/groups"),
                ("GET", "/profiles/profile-1/rules/group-1"),
                ("GET", "/profiles/profile-1/rules/group-1"),
                ("GET", "/profiles/profile-1/groups"),
                ("POST", "/profiles/profile-1/rules"),
                ("DELETE", "/profiles/profile-1/rules/old.example"),
            ],
        )
        self.assertEqual(requests[5][2]["hostnames"], ["new.example"])
        self.assertEqual(requests[5][2]["group"], "group-1")
        self.assertTrue(all(headers == "Bearer secret" for _, _, _, headers in requests))

    def test_find_folder_overlaps_reports_shared_rules(self):
        messages = find_folder_overlaps(
            {
                "Spam TLDs": {"*.ACTOR": (0, 1), "other.example": (0, 1)},
                "Most Abused TLDs": {"*.ACTOR": (0, 1), "extra.example": (0, 1)},
            }
        )
        self.assertEqual(len(messages), 1)
        self.assertIn("*.ACTOR", messages[0])
        self.assertIn("Spam TLDs", messages[0])
        self.assertIn("Most Abused TLDs", messages[0])

    def test_select_non_overlapping_folders_prefers_smaller(self):
        selected, skipped = select_non_overlapping_folders(
            {
                "Spam TLDs": {"*.ACTOR": (0, 1), "*.BIZ": (0, 1)},
                "Most Abused TLDs": {
                    "*.ACTOR": (0, 1),
                    "*.BIZ": (0, 1),
                    "*.ZIP": (0, 1),
                },
                "Referral": {"ref.example": (1, 1)},
            }
        )
        self.assertEqual(selected, ["Referral", "Spam TLDs"])
        self.assertEqual(skipped, ["Most Abused TLDs"])

    def test_validate_config_rejects_overlapping_mapped_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.json").write_text(
                json.dumps(
                    {
                        "group": {"group": "A"},
                        "rules": [{"PK": "shared.example", "action": {"do": 0, "status": 1}}],
                    }
                )
            )
            (root / "b.json").write_text(
                json.dumps(
                    {
                        "group": {"group": "B"},
                        "rules": [{"PK": "shared.example", "action": {"do": 0, "status": 1}}],
                    }
                )
            )
            config = root / "config.toml"
            config.write_text(
                '[settings]\napi_token = ""\n'
                '[profiles]\nnames = ["Kids"]\n'
                '[folders]\n"A" = "a.json"\n"B" = "b.json"\n'
                '[profile_folders]\nKids = ["A", "B"]\n'
            )
            problems = validate(config)
            self.assertTrue(any("share" in item for item in problems))

    def test_atomic_replace_deletes_before_recreating(self):
        rules = {"body": {"rules": [{"PK": "old.example", "action": {"do": 0, "status": 1}}]}}
        state = {"groups": [{"name": "Ads", "PK": "group-1"}], "rules": dict(rules)}
        requests = []

        class Response:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.payload

        def opener(request, timeout):
            path = request.full_url.removeprefix("https://api.controld.test")
            method = request.method
            body = json.loads(request.data) if request.data else None
            requests.append((method, path, body))
            if method == "GET" and path == "/profiles/profile-1/groups":
                return Response({"body": {"groups": list(state["groups"])}})
            if method == "GET" and path == "/profiles/profile-1/rules/group-1":
                return Response(state["rules"])
            if method == "GET" and path == "/profiles/profile-1/rules/group-2":
                return Response(
                    {"body": {"rules": [{"PK": "new.example", "action": {"do": 0, "status": 1}}]}}
                )
            if method == "DELETE" and path == "/profiles/profile-1/groups/group-1":
                state["groups"] = []
                return Response({})
            if method == "POST" and path == "/profiles/profile-1/groups":
                assert isinstance(body, dict)
                state["groups"] = [{"name": body["name"], "PK": "group-2"}]
                return Response({"body": {"groups": [{"PK": "group-2"}]}})
            if method == "POST" and path == "/profiles/profile-1/rules":
                return Response({})
            raise AssertionError(f"unexpected Control D request: {method} {path}")

        client = ControlDClient(
            "secret",
            base_url="https://api.controld.test",
            sleep=lambda _: None,
        )
        with patch("controld_sync.api._open", opener):
            result = sync_profile(
                client,
                "profile-1",
                "Ads",
                {"new.example": (0, 1)},
                apply=True,
                atomic=True,
            )

        self.assertEqual(result, (1, 1))
        methods = [(method, path) for method, path, _ in requests]
        delete_at = methods.index(("DELETE", "/profiles/profile-1/groups/group-1"))
        create_at = methods.index(("POST", "/profiles/profile-1/groups"))
        rules_at = methods.index(("POST", "/profiles/profile-1/rules"))
        self.assertLess(delete_at, create_at)
        self.assertLess(create_at, rules_at)
        self.assertEqual(requests[rules_at][2]["hostnames"], ["new.example"])
        self.assertEqual(requests[rules_at][2]["group"], "group-2")

    def test_www_prefix_is_kept(self):
        self.assertEqual(_rule_key("www.example.com"), "www.example.com")

    def test_sources_must_use_https(self):
        with self.assertRaises(SyncError):
            load_folder_source("http://example.com/list.json", "List")

    def test_oversized_source_is_rejected(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def geturl(self):
                return "https://example.com/list.json"

            def read(self, size):
                return b"x" * size

        with patch("urllib.request.urlopen", lambda request, timeout: Response()):
            with self.assertRaisesRegex(SyncError, "larger than"):
                load_folder_source("https://example.com/list.json", "List")

    def test_api_does_not_follow_redirects(self):
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:1/steal")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Redirect)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            client = ControlDClient(
                "secret", base_url=f"http://127.0.0.1:{server.server_port}", max_retries=0
            )
            with self.assertRaisesRegex(SyncError, r"\(302\)"):
                client.request("/profiles")
        finally:
            thread.join(5)
            server.server_close()

    def test_failed_restore_is_reported(self):
        state = {"deleted": False}

        class Response:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.payload

        def opener(request, timeout):
            path = request.full_url.removeprefix("https://api.controld.test")
            method = request.method
            if method == "GET" and path == "/profiles/profile-1/groups":
                groups = [] if state["deleted"] else [{"name": "Ads", "PK": "group-1"}]
                return Response({"body": {"groups": groups}})
            if method == "GET" and path == "/profiles/profile-1/rules/group-1":
                return Response({"body": {"rules": [{"PK": "old.example"}]}})
            if method == "DELETE" and path == "/profiles/profile-1/groups/group-1":
                state["deleted"] = True
                return Response({})
            raise urllib.error.HTTPError(request.full_url, 500, "down", Message(), None)

        client = ControlDClient("secret", base_url="https://api.controld.test", max_retries=0)
        with patch("controld_sync.api._open", opener):
            with self.assertRaisesRegex(SyncError, "restoring the previous 1 rules also failed"):
                sync_profile(
                    client, "profile-1", "Ads", {"new.example": (0, 1)}, apply=True, atomic=True
                )


if __name__ == "__main__":
    unittest.main()
