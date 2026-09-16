"""TOML configuration loading and API URL validation."""

from __future__ import annotations

import tomllib
import urllib.parse
from pathlib import Path
from typing import Any

from .errors import SyncError

API_BASE = "https://api.controld.com"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
API_HOSTS = {"api.controld.com"}


def _validate_api_base(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" and parsed.hostname not in LOOPBACK_HOSTS:
        raise SyncError("API base URL must use HTTPS, except for loopback test servers")
    if parsed.hostname not in API_HOSTS and parsed.hostname not in LOOPBACK_HOSTS:
        raise SyncError("API base URL must be api.controld.com, except for loopback test servers")
    if parsed.query or parsed.fragment or not parsed.netloc:
        raise SyncError("API base URL must be an absolute URL without a query or fragment")
    return value.rstrip("/")


def load_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SyncError(f"Could not read config file {path}: {exc}") from exc
    for section in ("settings", "profiles", "folders", "profile_folders"):
        if section not in config or not isinstance(config[section], dict):
            raise SyncError(f"Config must contain a [{section}] table")
    if any(not isinstance(name, str) or not isinstance(source, str)
           for name, source in config["folders"].items()):
        raise SyncError("[folders] names and sources must be strings")
    return config

__all__ = ["API_BASE", "LOOPBACK_HOSTS", "API_HOSTS", "load_config", "_validate_api_base"]
