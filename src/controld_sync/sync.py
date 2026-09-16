"""Profile and folder synchronization, including atomic replacement."""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from typing import Any

from .api import ControlDClient, _id, _items
from .errors import SyncError
from .sources import DEFAULT_ACTION, RuleAction, _rule_key


def sync_profile(
    client: ControlDClient,
    profile_id: str,
    folder_name: str,
    desired: dict[str, RuleAction],
    apply: bool,
    atomic: bool = True,
    validate_only: bool = False,
) -> tuple[int, int]:
    prefix = f"/profiles/{urllib.parse.quote(profile_id, safe='')}"
    groups = _items(client.request(prefix + "/groups"))
    matches = [
        item for item in groups if str(item.get("name", item.get("group", ""))) == folder_name
    ]
    if len(matches) > 1:
        print(f"warning: [{profile_id}] duplicate groups named {folder_name!r}; using the first")
    folder = matches[0] if matches else None
    if folder is None:
        print(f"[{profile_id}] folder {folder_name!r} does not exist")
        if not apply:
            return len(desired), 0
        group_do, group_status = _folder_action(desired)
        folder_response = client.request(
            prefix + "/groups",
            "POST",
            {
                "name": folder_name,
                "do": group_do,
                "status": group_status,
            },
        )
        folder_id = _id(folder_response)
        if not folder_id:
            raise SyncError(f"[{profile_id}] API did not return the new folder id")
        existing: dict[str, RuleAction] = {}
    else:
        folder_id = _id(folder)
        if not folder_id:
            raise SyncError(f"[{profile_id}] folder has no id")
        existing = _read_group_rules(client, prefix, folder_id)
    additions = sorted(set(desired) - set(existing))
    removals = sorted(set(existing) - set(desired))
    action_changes = sorted(
        key for key in set(desired) & set(existing) if desired[key] != existing[key]
    )
    print(
        f"[{profile_id}] add {len(additions)}, "
        f"remove {len(removals) + len(action_changes)}, total {len(desired)}"
    )
    if validate_only:
        if additions or removals or action_changes:
            raise SyncError(
                f"[{profile_id}] validation failed for folder {folder_name!r}: remote differs"
            )
        return 0, 0
    if not apply:
        return len(additions), len(removals)
    if atomic and folder is not None and (additions or removals):
        return _replace_group(
            client,
            prefix,
            folder_id,
            folder_name,
            desired,
            existing,
            profile_id,
            len(additions),
            len(removals) + len(action_changes),
        )
    changes = {key: desired[key] for key in additions + action_changes}
    for domain in action_changes:
        client.request(prefix + "/rules/" + urllib.parse.quote(domain, safe=""), "DELETE")
    for (do, status), values in _group_by_action(changes):
        for start in range(0, len(values), 500):
            client.request(
                prefix + "/rules",
                "POST",
                {
                    "hostnames": values[start : start + 500],
                    "do": do,
                    "status": status,
                    "group": folder_id,
                },
            )
    for domain in removals:
        client.request(prefix + "/rules/" + urllib.parse.quote(domain, safe=""), "DELETE")
    return len(additions), len(removals)


def _read_group_rules(client: ControlDClient, prefix: str, folder_id: str) -> dict[str, RuleAction]:
    previous: dict[str, RuleAction] | None = None
    for _ in range(4):
        current = {}
        for item in _items(
            client.request(prefix + "/rules/" + urllib.parse.quote(folder_id, safe=""))
        ):
            rule = _rule_key(
                item.get("hostname") or item.get("host") or item.get("domain") or item.get("PK")
            )
            if rule:
                action = item.get("action")
                current[rule] = (
                    (
                        int(action.get("do", DEFAULT_ACTION[0])),
                        int(action.get("status", DEFAULT_ACTION[1])),
                    )
                    if isinstance(action, dict)
                    else DEFAULT_ACTION
                )
        if previous is not None and current == previous:
            return current
        previous = current
        time.sleep(0.05)
    raise SyncError(f"rules for group {folder_id!r} did not settle")


def _backup_name(folder_name: str, suffix: str) -> str:
    """Keep API names within Control D's 32-character limit."""
    candidate = f"{folder_name}_{suffix}"
    if len(candidate) <= 32:
        return candidate
    digest = hashlib.sha1(folder_name.encode("utf-8")).hexdigest()[:6]
    return f"{folder_name[: 32 - len(suffix) - 8]}_{suffix}_{digest}"


def _group_named(groups: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next(
        (item for item in groups if str(item.get("name", item.get("group", ""))) == name), None
    )


def _delete_named_group(
    client: ControlDClient, prefix: str, groups: list[dict[str, Any]], name: str
) -> None:
    stale = _group_named(groups, name)
    if stale is None:
        return
    stale_id = _id(stale)
    if stale_id:
        client.request(prefix + "/groups/" + urllib.parse.quote(stale_id, safe=""), "DELETE")


def _replace_group(
    client: ControlDClient,
    prefix: str,
    folder_id: str,
    folder_name: str,
    desired: dict[str, RuleAction],
    original: dict[str, RuleAction],
    profile_id: str,
    additions: int,
    removals: int,
) -> tuple[int, int]:
    new_id = None
    try:
        groups = _items(client.request(prefix + "/groups"))
        old_name, new_name = _backup_name(folder_name, "OLD"), _backup_name(folder_name, "NEW")
        _delete_named_group(client, prefix, groups, old_name)
        _delete_named_group(client, prefix, groups, new_name)
        old_do, old_status = _folder_action(original)
        backup = client.request(
            prefix + "/groups",
            "POST",
            {
                "name": old_name,
                "do": old_do,
                "status": old_status,
            },
        )
        backup_id = _id(backup)
        if not backup_id:
            raise SyncError(f"[{profile_id}] backup group creation returned no id")
        for (do, status), old_values in _group_by_action(original):
            for start in range(0, len(old_values), 500):
                client.request(
                    prefix + "/rules",
                    "POST",
                    {
                        "hostnames": old_values[start : start + 500],
                        "do": do,
                        "status": status,
                        "group": backup_id,
                    },
                )
        new_do, new_status = _folder_action(desired)
        replacement = client.request(
            prefix + "/groups",
            "POST",
            {
                "name": new_name,
                "do": new_do,
                "status": new_status,
            },
        )
        new_id = _id(replacement)
        if not new_id:
            raise SyncError(f"[{profile_id}] replacement group creation returned no id")
        for (do, status), values in _group_by_action(desired):
            for start in range(0, len(values), 500):
                client.request(
                    prefix + "/rules",
                    "POST",
                    {
                        "hostnames": values[start : start + 500],
                        "do": do,
                        "status": status,
                        "group": new_id,
                    },
                )
        if _read_group_rules(client, prefix, new_id) != desired:
            raise SyncError(f"[{profile_id}] post-import validation failed for {folder_name!r}")
        client.request(prefix + "/groups/" + urllib.parse.quote(folder_id, safe=""), "DELETE")
        final = client.request(
            prefix + "/groups",
            "POST",
            {
                "name": folder_name,
                "do": new_do,
                "status": new_status,
            },
        )
        final_id = _id(final)
        if not final_id:
            raise SyncError(f"[{profile_id}] final group creation returned no id")
        for (do, status), values in _group_by_action(desired):
            for start in range(0, len(values), 500):
                client.request(
                    prefix + "/rules",
                    "POST",
                    {
                        "hostnames": values[start : start + 500],
                        "do": do,
                        "status": status,
                        "group": final_id,
                    },
                )
        if _read_group_rules(client, prefix, final_id) != desired:
            raise SyncError(
                f"[{profile_id}] final post-import validation failed for {folder_name!r}"
            )
        client.request(prefix + "/groups/" + urllib.parse.quote(new_id, safe=""), "DELETE")
        client.request(prefix + "/groups/" + urllib.parse.quote(backup_id, safe=""), "DELETE")
        return additions, removals
    except (SyncError, OSError, ValueError, TypeError) as exc:
        if new_id:
            try:
                client.request(prefix + "/groups/" + urllib.parse.quote(new_id, safe=""), "DELETE")
            except SyncError:
                pass
        try:
            old_do, old_status = _folder_action(original)
            restored = client.request(
                prefix + "/groups",
                "POST",
                {
                    "name": folder_name,
                    "do": old_do,
                    "status": old_status,
                },
            )
            restored_id = _id(restored)
            if restored_id:
                for (do, status), values in _group_by_action(original):
                    for start in range(0, len(values), 500):
                        client.request(
                            prefix + "/rules",
                            "POST",
                            {
                                "hostnames": values[start : start + 500],
                                "do": do,
                                "status": status,
                                "group": restored_id,
                            },
                        )
        except SyncError:
            pass
        if isinstance(exc, SyncError):
            raise
        raise SyncError(f"[{profile_id}] atomic replacement failed: {exc}") from exc


def _group_by_action(rules: dict[str, RuleAction]) -> list[tuple[RuleAction, list[str]]]:
    grouped: dict[RuleAction, list[str]] = {}
    for rule, action in rules.items():
        grouped.setdefault(action, []).append(rule)
    return [(action, sorted(values)) for action, values in sorted(grouped.items())]


def _folder_action(rules: dict[str, RuleAction]) -> RuleAction:
    """Use the first normalized rule action as the Control D group action."""
    return rules[sorted(rules)[0]] if rules else DEFAULT_ACTION


def resolve_profiles(client: ControlDClient, names: list[str]) -> dict[str, str]:
    available = _items(client.request("/profiles"))
    resolved = {}
    for name in names:
        profile = next((item for item in available if str(item.get("name", "")) == name), None)
        if profile is None:
            raise SyncError(f"Control D profile {name!r} was not found")
        profile_id = _id(profile)
        if not profile_id:
            raise SyncError(f"Control D profile {name!r} has no id")
        resolved[name] = profile_id
    return resolved


__all__ = ["resolve_profiles", "sync_profile"]
