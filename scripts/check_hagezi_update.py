#!/usr/bin/env python3
"""Report or safely prepare a pinned HaGeZi update; never edits by default."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from validate_config import validate

API = "https://api.github.com/repos/hagezi/dns-blocklists/commits/main"
URL = re.compile(r"(https://raw\.githubusercontent\.com/hagezi/dns-blocklists/)([0-9a-f]{40})(/)")


def latest_sha() -> str:
    request = urllib.request.Request(
        API, headers={"Accept": "application/vnd.github+json", "User-Agent": "controld-sync"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        value = json.loads(response.read())
    sha = value.get("sha") if isinstance(value, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("GitHub returned no immutable HaGeZi commit SHA")
    return sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument(
        "--update", action="store_true", help="write only safe HaGeZi pin replacements"
    )
    args = parser.parse_args()
    problems = validate(args.config)
    if problems:
        print("Configuration is not safe to update:")
        print("\n".join(f"- {item}" for item in problems))
        return 1
    text = args.config.read_text(encoding="utf-8")
    current = {match.group(2) for match in URL.finditer(text)}
    if not current:
        print("No pinned HaGeZi sources found; nothing to update.")
        return 0
    try:
        newest = latest_sha()
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"HaGeZi update check unavailable: {exc}")
        return 2
    if current == {newest}:
        print(f"HaGeZi is up to date ({newest}).")
        return 0
    print(f"HaGeZi update available: {', '.join(sorted(current))} -> {newest}")
    if args.update:
        updated = URL.sub(lambda match: match.group(1) + newest + match.group(3), text)
        args.config.write_text(updated, encoding="utf-8")
        print(f"Updated {args.config}; review this change in a pull request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
