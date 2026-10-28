from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

from .errors import SyncError
from .sources import fetch_json, parse_folder_rules
from .sync import select_non_overlapping_folders

GITHUB_CONTENTS_URL = "https://api.github.com/repos/hagezi/dns-blocklists/contents/controld"
GITHUB_COMMIT_URL = "https://api.github.com/repos/hagezi/dns-blocklists/commits"
RAW_URL = "https://raw.githubusercontent.com/hagezi/dns-blocklists/{ref}/controld/{name}"


def _get_json(url: str) -> Any:
    return fetch_json(url, {"Accept": "application/vnd.github+json"})


def generate_hagezi_config(
    output: Path,
    profile_name: str = "Init",
    ref: str = "main",
) -> int:
    commit = _get_json(f"{GITHUB_COMMIT_URL}/{urllib.parse.quote(ref, safe='')}")
    pinned_ref = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(pinned_ref, str) or not pinned_ref:
        raise SyncError(f"Could not resolve HaGeZi ref {ref!r} to an immutable commit")
    listing = _get_json(f"{GITHUB_CONTENTS_URL}?ref={urllib.parse.quote(pinned_ref, safe='')}")
    if not isinstance(listing, list):
        raise SyncError("HaGeZi GitHub contents response was not a list")
    entries = [
        item
        for item in listing
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].endswith("-folder.json")
        and item.get("type") == "file"
    ]
    if not entries:
        raise SyncError("No HaGeZi Control D folder JSON files were found")

    folders: dict[str, str] = {}
    folder_rules = {}
    for entry in sorted(entries, key=lambda item: str(item["name"])):
        name = str(entry["name"])
        data = _get_json(RAW_URL.format(ref=pinned_ref, name=name))
        group = data.get("group") if isinstance(data, dict) else None
        folder_name = group.get("group") if isinstance(group, dict) else None
        if not isinstance(folder_name, str) or not folder_name.strip():
            raise SyncError(f"HaGeZi folder {name} has no valid group.group name")
        key = folder_name.strip()
        folders[key] = RAW_URL.format(ref=pinned_ref, name=name)
        folder_rules[key] = parse_folder_rules(data, key)

    selected, skipped = select_non_overlapping_folders(folder_rules)

    quote = json.dumps
    lines = [
        "[settings]",
        'api_token = ""',
        "dry_run = true",
        'cache_file = ".controld-sync-cache.json"',
        "atomic_replace = true",
        "fail_on_drift = false",
        "",
        "[profiles]",
        f"names = [{quote(profile_name)}]",
        "",
        "[folders]",
    ]
    lines.extend(f"{quote(name)} = {quote(source)}" for name, source in sorted(folders.items()))
    lines.extend(["", "[profile_folders]"])
    if skipped:
        lines.append(
            "# Folders omitted from the profile mapping because they share rule "
            "hostnames with a selected folder (Control D rules are unique per profile):"
        )
        lines.extend(f"# - {name}" for name in skipped)
    lines.extend(
        [
            f"{quote(profile_name)} = [" + ", ".join(quote(name) for name in selected) + "]",
            "",
        ]
    )
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise SyncError(f"Could not write generated config {output}: {exc}") from exc
    return len(folders)


__all__ = ["generate_hagezi_config"]
