"""Persistent source cache helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .errors import SyncError


def content_hash(domains: Iterable[str]) -> str:
    payload = "\n".join(sorted(set(domains))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"Could not read cache file {path}: {exc}") from exc
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and (isinstance(v, str) or (
            isinstance(v, dict) and isinstance(v.get("hash"), str)
        )) for k, v in value.items()
    ):
        raise SyncError(f"Cache file {path} must contain a JSON object of hashes")
    return value


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    try:
        temporary.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise SyncError(f"Could not write cache file {path}: {exc}") from exc

__all__ = ["content_hash", "load_cache", "save_cache"]
