#!/usr/bin/env python3
"""Validate the repository configuration without contacting Control D."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

SHA = re.compile(r"^[0-9a-f]{40}$")


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return [f"cannot parse {path}: {exc}"]
    for section in ("settings", "profiles", "folders", "profile_folders"):
        if not isinstance(data.get(section), dict):
            errors.append(f"missing [{section}] table")
    settings = data.get("settings", {})
    token = settings.get("api_token", "")
    if token not in ("", None):
        errors.append("settings.api_token must be empty; use CONTROLD_API_TOKEN")
    profiles = data.get("profiles", {})
    names = profiles.get("names", [])
    if not isinstance(names, list) or not names:
        errors.append("[profiles].names must be a non-empty array")
    folders = data.get("folders", {})
    for name, source in folders.items() if isinstance(folders, dict) else []:
        if not isinstance(name, str) or not isinstance(source, str):
            errors.append("folder names and sources must be strings")
            continue
        parsed = urlparse(source)
        if parsed.scheme:
            if parsed.scheme != "https":
                errors.append(f"{name}: source must use HTTPS")
            if parsed.hostname == "raw.githubusercontent.com":
                parts = parsed.path.strip("/").split("/")
                if len(parts) < 3 or not SHA.fullmatch(parts[2]):
                    errors.append(f"{name}: GitHub source must contain a 40-character commit SHA")
    mappings = data.get("profile_folders", {})
    if isinstance(mappings, dict):
        for profile in names if isinstance(names, list) else []:
            selected = mappings.get(profile)
            if not isinstance(selected, list):
                errors.append(f"profile {profile!r} has no folder mapping")
            else:
                errors.extend(
                    f"profile {profile!r} references unknown folder {folder!r}"
                    for folder in selected if folder not in folders
                )
    return errors


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.toml")
    problems = validate(target)
    if problems:
        for problem in problems:
            print(f"::error::{problem}", file=sys.stderr)
        raise SystemExit(1)
    print(f"{target}: valid")
