"""Synchronize JSON domain lists into Control D custom-rule folders."""

from .api import ControlDClient, list_profiles
from .cache import content_hash, load_cache, save_cache
from .config import API_BASE, _validate_api_base, load_config
from .errors import SchemaError, SyncError
from .sources import _rule_key, load_domains, load_folder_source, load_folders, parse_folder_data, validate_folder_schema
from .hagezi import generate_hagezi_config
from .sync import resolve_profiles, sync_profile
from .cli import main

__all__ = [
    "API_BASE", "ControlDClient", "SchemaError", "SyncError", "content_hash",
    "load_cache", "load_config", "load_domains", "load_folder_source",
    "load_folders", "main", "parse_folder_data", "save_cache", "sync_profile",
    "generate_hagezi_config",
    "resolve_profiles", "validate_folder_schema", "list_profiles",
]
