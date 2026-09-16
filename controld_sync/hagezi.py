"""HaGeZi Control D folder discovery and configuration generation."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .errors import SyncError

GITHUB_CONTENTS_URL = "https://api.github.com/repos/hagezi/dns-blocklists/contents/controld"
GITHUB_COMMIT_URL = "https://api.github.com/repos/hagezi/dns-blocklists/commits"
RAW_URL = "https://raw.githubusercontent.com/hagezi/dns-blocklists/{ref}/controld/{name}"


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "controld-sync"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"Could not read HaGeZi folder metadata from {url}: {exc}") from exc


def generate_hagezi_config(
    output: Path,
    profile_name: str = "Init",
    ref: str = "main",
) -> int:
    """Discover HaGeZi Control D folders and write a token-free TOML config."""
    commit = _get_json(f"{GITHUB_COMMIT_URL}/{urllib.parse.quote(ref, safe='')}")
    pinned_ref = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(pinned_ref, str) or not pinned_ref:
        raise SyncError(f"Could not resolve HaGeZi ref {ref!r} to an immutable commit")
    listing = _get_json(f"{GITHUB_CONTENTS_URL}?ref={urllib.parse.quote(pinned_ref, safe='')}")
    if not isinstance(listing, list):
        raise SyncError("HaGeZi GitHub contents response was not a list")
    entries = [
        item for item in listing
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].endswith("-folder.json")
        and item.get("type") == "file"
    ]
    if not entries:
        raise SyncError("No HaGeZi Control D folder JSON files were found")

    folders: dict[str, str] = {}
    for entry in sorted(entries, key=lambda item: str(item["name"])):
        name = str(entry["name"])
        data = _get_json(RAW_URL.format(ref=pinned_ref, name=name))
        group = data.get("group") if isinstance(data, dict) else None
        folder_name = group.get("group") if isinstance(group, dict) else None
        if not isinstance(folder_name, str) or not folder_name.strip():
            raise SyncError(f"HaGeZi folder {name} has no valid group.group name")
        folders[folder_name.strip()] = RAW_URL.format(
            ref=pinned_ref, name=name
        )

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
    lines.extend(["", "[profile_folders]", f"{quote(profile_name)} = [" +
                  ", ".join(quote(name) for name in sorted(folders)) + "]", ""])
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise SyncError(f"Could not write generated config {output}: {exc}") from exc
    return len(folders)


__all__ = ["generate_hagezi_config"]
