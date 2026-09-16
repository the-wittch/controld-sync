"""Command-line orchestration for Control D synchronization."""

from __future__ import annotations

import argparse
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from .api import ControlDClient, _id, list_profiles
from .cache import content_hash, load_cache, save_cache
from .config import API_BASE, _validate_api_base, load_config
from .errors import SyncError
from .hagezi import generate_hagezi_config
from .sources import load_folder_source
from .sync import resolve_profiles, sync_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--apply", action="store_true", help="Override config and perform writes")
    parser.add_argument("--dry-run", action="store_true", help="Override config and never perform writes")
    parser.add_argument("--check-drift", action="store_true", help="Fail when a remote folder differs from its source")
    parser.add_argument("--validate", action="store_true", help="Validate remote folders without changing them")
    parser.add_argument("--check-updates", action="store_true", help="Check source freshness without advancing cache")
    parser.add_argument("--no-cache", action="store_true", help="Disable reading and writing the source cache")
    parser.add_argument("--list-profiles", action="store_true",
                        help="List Control D profile names and IDs, then exit")
    parser.add_argument("--api-base", default=os.environ.get("CONTROLD_API_BASE_URL", API_BASE))
    parser.add_argument("--generate-hagezi-config", type=Path, metavar="PATH",
                        help="Generate a token-free config containing all HaGeZi Control D folders")
    parser.add_argument("--init-profile-name", default="Init",
                        help="Profile name assigned all generated HaGeZi folders (default: Init)")
    parser.add_argument("--hagezi-ref", default="main",
                        help="HaGeZi repository ref used by --generate-hagezi-config (default: main)")
    args = parser.parse_args()
    try:
        if args.generate_hagezi_config:
            count = generate_hagezi_config(
                args.generate_hagezi_config, args.init_profile_name, args.hagezi_ref
            )
            print(f"Generated {args.generate_hagezi_config} with {count} HaGeZi folders "
                  f"assigned to profile {args.init_profile_name!r}")
            return 0
        if args.apply and args.dry_run:
            raise SyncError("--apply and --dry-run cannot be used together")
        config = load_config(args.config)
        settings = config["settings"]
        token = os.environ.get("CONTROLD_API_TOKEN") or str(settings.get("api_token", "")).strip()
        if not token:
            raise SyncError("Set settings.api_token in config.toml or CONTROLD_API_TOKEN")
        client = ControlDClient(token, _validate_api_base(args.api_base))
        if args.list_profiles:
            for profile in list_profiles(client):
                profile_id = _id(profile) or "(no ID returned)"
                print(f"{profile.get('name', '(unnamed)')}\t{profile_id}")
            return 0
        profile_names = config["profiles"].get("names")
        if not isinstance(profile_names, list) or not profile_names:
            raise SyncError("[profiles] names must be a non-empty array")
        folder_sources, mappings = config["folders"], config["profile_folders"]
        if not folder_sources or not mappings:
            raise SyncError("[folders] and [profile_folders] must not be empty")
        config_dir = args.config.resolve().parent
        cache_path = (config_dir / str(settings.get("cache_file", ".controld-sync-cache.json"))).resolve()
        cache = {} if args.no_cache else load_cache(cache_path)
        checked_at = datetime.now(timezone.utc).isoformat()
        folders = {
            str(name): load_folder_source(
                str(source) if str(source).startswith(("http://", "https://"))
                else str((config_dir / str(source)).resolve()), str(name))
            for name, source in folder_sources.items()
        }
        profile_ids = resolve_profiles(client, [str(name) for name in profile_names])
        apply = args.apply or (not args.dry_run and not bool(settings.get("dry_run", True)))
        atomic, fail_on_drift = bool(settings.get("atomic_replace", True)), args.check_drift or bool(settings.get("fail_on_drift", False))
        summaries = []
        for profile_name, profile_id in profile_ids.items():
            selected = mappings.get(profile_name)
            if not isinstance(selected, list):
                raise SyncError(f"[profile_folders] missing mapping for {profile_name!r}")
            for folder_name in selected:
                if str(folder_name) not in folders:
                    raise SyncError(f"Profile {profile_name!r} references unknown folder {folder_name!r}")
                desired = folders[str(folder_name)]
                digest = content_hash(desired)
                cache_key = f"{profile_id}:{folder_name}"
                cached = cache.get(cache_key)
                cached_hash = cached.get("hash") if isinstance(cached, dict) else cached
                source_changed = cached_hash != digest
                if not source_changed:
                    print(f"[{profile_name}] {folder_name!r} source unchanged")
                elif args.check_updates:
                    print(f"[{profile_name}] {folder_name!r} source changed since last apply")
                try:
                    if args.check_updates:
                        # This mode is deliberately source-only: loading the URL/file
                        # above is the freshness check, and the cached digest is the
                        # last successfully applied source version.
                        additions, removals = 0, 0
                    else:
                        additions, removals = sync_profile(
                            client, profile_id, str(folder_name), desired,
                            apply and not args.validate,
                            atomic=atomic, validate_only=args.validate,
                        )
                except SyncError:
                    cache.pop(cache_key, None)
                    if not args.no_cache and not args.check_updates and not args.validate:
                        save_cache(cache_path, cache)
                    raise
                if fail_on_drift and (additions or removals):
                    raise SyncError(f"[{profile_name}] drift detected in folder {folder_name!r}")
                summaries.append({
                    "profile": profile_name, "profile_id": profile_id, "folder": str(folder_name),
                    "desired": len(desired), "additions": additions, "removals": removals,
                    "checked_at": checked_at, "source_hash": digest,
                    "source_changed": source_changed,
                    "previous_source_hash": cached_hash,
                })
                if apply and not args.check_updates and not args.validate and not args.no_cache:
                    cache[cache_key] = {"hash": digest, "updated_at": checked_at}
        if summaries:
            print(json.dumps({"folders": summaries}, sort_keys=True))
        should_save = (apply or bool(settings.get("write_cache", False))) and not args.check_updates and not args.validate
        if not args.no_cache and should_save:
            save_cache(cache_path, cache)
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: invalid configuration or local file: {exc}", file=sys.stderr)
        return 1
    return 0

__all__ = ["main"]
