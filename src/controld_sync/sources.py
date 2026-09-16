"""JSON source loading, normalization, and Control D schema validation."""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .errors import SchemaError, SyncError

RuleAction = tuple[int, int]
DEFAULT_ACTION: RuleAction = (0, 1)


def _domain(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower().rstrip(".")
    if not value or value.startswith("#") or "://" in value or "/" in value:
        return None
    if value.startswith("*."):
        value = value[2:]
    if value.startswith("||"):
        value = value[2:].split("^", 1)[0]
    if value.startswith("www."):
        value = value[4:]
    labels = value.split(".")
    if any(
        not label or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_*" for c in label)
        for label in labels
    ):
        return None
    if len(labels) == 1 and not re.fullmatch(r"[a-z0-9][a-z0-9_*_-]*", labels[0]):
        return None
    return value


def _rule_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    if re.fullmatch(r"@[A-Z0-9_-]+", value):
        return value
    if re.fullmatch(r"\*\.[A-Z0-9-]+", value):
        return value
    return _domain(value.lower())


def _walk_domains(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        rule = _rule_key(value)
        if rule:
            yield rule
    elif isinstance(value, list):
        for item in value:
            yield from _walk_domains(item)
    elif isinstance(value, dict):
        for key in (
            "domain",
            "hostname",
            "host",
            "PK",
            "pk",
            "domains",
            "hosts",
            "entries",
            "rules",
        ):
            if key in value:
                yield from _walk_domains(value[key])


def _load_json(file: Path) -> Any:
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"Could not read JSON file {file}: {exc}") from exc


def validate_folder_schema(data: Any, source: str = "folder") -> tuple[str | None, list[Any]]:
    if not isinstance(data, dict) or ("group" not in data and "rules" not in data):
        return None, []
    group = data.get("group")
    if (
        not isinstance(group, dict)
        or not isinstance(group.get("group"), str)
        or not group["group"].strip()
    ):
        raise SchemaError(f"Invalid Control D folder schema in {source}: group.group is required")
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise SchemaError(f"Invalid Control D folder schema in {source}: rules must be an array")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or not isinstance(rule.get("PK"), str):
            raise SchemaError(
                f"Invalid Control D folder schema in {source}: rules[{index}].PK is required"
            )
        if _rule_key(rule["PK"]) is None:
            raise SchemaError(
                f"Invalid Control D folder schema in {source}: invalid rules[{index}].PK"
            )
    return group["group"].strip(), rules


def _action(value: Any, default: RuleAction = DEFAULT_ACTION) -> RuleAction:
    if not isinstance(value, dict):
        return default
    do = value.get("do", default[0])
    status = value.get("status", default[1])
    if isinstance(do, bool) or not isinstance(do, int) or do < 0:
        raise SchemaError("Control D action.do must be a non-negative integer")
    if isinstance(status, bool) or not isinstance(status, int) or status < 0:
        raise SchemaError("Control D action.status must be a non-negative integer")
    return do, status


def parse_folder_rules(data: Any, fallback_name: str) -> dict[str, RuleAction]:
    """Parse rules while retaining Control D action metadata."""
    group_name, rules = validate_folder_schema(data, fallback_name)
    if isinstance(data, dict) and rules:
        group = data.get("group")
        group_action = _action(group.get("action") if isinstance(group, dict) else None)
        result: dict[str, RuleAction] = {}
        for rule in rules:
            key = _rule_key(rule["PK"])
            if key:
                result[key] = _action(rule.get("action"), group_action)
        if result:
            return result
    values = data.get("rules", data) if isinstance(data, dict) else data
    result = {key: DEFAULT_ACTION for key in _walk_domains(values)}
    if not result:
        raise SyncError(f"No valid domains found in folder {fallback_name!r}")
    return result


def load_folders(source: Path) -> dict[str, set[str]]:
    files = [source] if source.is_file() else sorted(source.glob("*.json"))
    if not files:
        raise SyncError(f"No JSON files found in {source}")
    folders: dict[str, set[str]] = {}
    for file in files:
        data = _load_json(file)
        name, _ = validate_folder_schema(data, str(file))
        if name is None:
            group = data.get("group") if isinstance(data, dict) else None
            name = group.get("group") if isinstance(group, dict) else None
        folder_name = str(name or file.stem)
        domains = set(_walk_domains(data.get("rules", data) if isinstance(data, dict) else data))
        if not domains:
            raise SyncError(f"No valid domains found in {file}")
        folders.setdefault(folder_name, set()).update(domains)
    return folders


def parse_folder_data(data: Any, fallback_name: str) -> set[str]:
    return set(parse_folder_rules(data, fallback_name))


def load_folder_source(source: str, fallback_name: str) -> dict[str, RuleAction]:
    if source.startswith(("https://", "http://")):
        try:
            with urllib.request.urlopen(source, timeout=60) as response:
                data = json.loads(response.read())
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncError(f"Could not download JSON folder {source}: {exc}") from exc
        return parse_folder_rules(data, fallback_name)
    path = Path(source)
    if path.is_dir():
        folders = load_folders(path)
        domains = set().union(*folders.values()) if folders else set()
        if not domains:
            raise SyncError(f"No valid domains found in {source}")
        return {domain: DEFAULT_ACTION for domain in domains}
    return parse_folder_rules(_load_json(path), fallback_name)


def load_domains(source: Path) -> list[str]:
    folders = load_folders(source)
    return sorted(set().union(*folders.values()))


__all__ = [
    "load_domains",
    "load_folder_source",
    "load_folders",
    "parse_folder_data",
    "parse_folder_rules",
    "validate_folder_schema",
    "RuleAction",
]
