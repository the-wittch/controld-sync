import json
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import io
from pathlib import Path

from controld_sync import (SchemaError, _rule_key, _validate_api_base, content_hash,
                           load_cache, load_config, load_domains, load_folders, save_cache,
                           __version__)
from controld_sync.sources import parse_folder_rules
from controld_sync.api import ControlDClient
from controld_sync.sync import _backup_name


class LoadDomainsTests(unittest.TestCase):
    def test_version_is_available(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_loads_nested_json_and_normalizes_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "list.json"
            path.write_text(json.dumps({
                "entries": [{"hostname": "Tracker.Example."}, {"domain": "||ads.example^"}],
                "domains": ["*.cdn.example"],
            }))
            self.assertEqual(load_domains(path), ["ads.example", "cdn.example", "tracker.example"])

    def test_directory_combines_files_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.json").write_text('["a.example"]')
            (root / "b.json").write_text('["a.example", "b.example"]')
            self.assertEqual(load_domains(root), ["a.example", "b.example"])

    def test_reads_control_d_folder_export_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom-name.json"
            path.write_text(json.dumps({
                "group": {"group": "Badware Hoster"},
                "rules": [{"PK": "bad.example", "action": {"do": 0}}],
            }))
            self.assertEqual(load_folders(path), {"Badware Hoster": {"bad.example"}})

    def test_accepts_control_d_selector_rules(self):
        self.assertEqual(_rule_key("@RU"), "@RU")
        self.assertEqual(_rule_key("@CN"), "@CN")
        self.assertEqual(_rule_key("*.actor"), "*.ACTOR")
        self.assertEqual(_rule_key("777*.livepartners.com"), "777*.livepartners.com")
        self.assertEqual(_rule_key("actor"), "actor")

    def test_preserves_control_d_rule_actions(self):
        rules = parse_folder_rules({
            "group": {"group": "Apple PR allow", "action": {"do": 1, "status": 1}},
            "rules": [{"PK": "mask.icloud.com", "action": {"do": 1, "status": 1}}],
        }, "allow")
        self.assertEqual(rules, {"mask.icloud.com": (1, 1)})

    def test_rejects_malformed_control_d_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"group": {"group": "Broken"}, "rules": [{"host": "x.example"}]}))
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
                '[settings]\ndry_run = true\n'
                '[profiles]\nnames = ["Kids"]\n'
                '[folders]\n"Ads" = "ads.json"\n'
                '[profile_folders]\nKids = ["Ads"]\n'
            )
            config = load_config(path)
            self.assertEqual(config["profiles"]["names"], ["Kids"])
            self.assertEqual(config["profile_folders"]["Kids"], ["Ads"])

    def test_api_base_requires_https_except_loopback(self):
        self.assertEqual(_validate_api_base("https://api.controld.com/"), "https://api.controld.com")
        self.assertEqual(_validate_api_base("http://127.0.0.1:8000"), "http://127.0.0.1:8000")
        with self.assertRaises(Exception):
            _validate_api_base("http://example.com")
        with self.assertRaises(Exception):
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
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"{}"
        retry = urllib.error.HTTPError("x", 503, "busy", {}, io.BytesIO(b""))
        calls = []
        def opener(request, timeout):
            calls.append(request.method)
            if len(calls) == 1:
                raise retry
            return Response()
        client = ControlDClient("secret", base_url="https://api.controld.com", sleep=lambda _: None)
        with patch("urllib.request.urlopen", opener):
            client.request("/profiles")
        self.assertEqual(calls, ["GET", "GET"])
        calls.clear()
        with patch("urllib.request.urlopen", opener):
            with self.assertRaises(Exception):
                client.request("/groups", "POST", {})
        self.assertEqual(calls, ["POST"])


if __name__ == "__main__":
    unittest.main()
