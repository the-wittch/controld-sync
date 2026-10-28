from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from .config import API_BASE
from .errors import SyncError


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# a redirect would carry the bearer token to wherever it points
_open = urllib.request.build_opener(_NoRedirect).open


def _safe_error(text: str, token: str) -> str:
    return text.replace(token, "[REDACTED]") if token else text


def _retry_delay(retry_after: str | None, fallback: float) -> float:
    if not retry_after:
        return fallback
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(retry_after)
    except (TypeError, ValueError):
        return fallback
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    return max(0.0, (target - datetime.now(UTC)).total_seconds())


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("body", "data", "profiles", "groups", "folders", "rules", "items"):
            if key in value:
                return _items(value[key])
    return []


def _id(item: dict[str, Any]) -> str | None:
    body = item.get("body")
    if isinstance(body, dict):
        nested_items = _items(body)
        if nested_items:
            item = nested_items[0]
    nested = item.get("data")
    if isinstance(nested, dict):
        item = nested
    for key in ("id", "pk", "PK", "profile_id", "folder", "group", "hostname", "host"):
        if item.get(key) is not None:
            return str(item[key])
    return None


@dataclass
class ControlDClient:
    token: str
    base_url: str = API_BASE
    timeout: int = 60
    max_retries: int = 3
    backoff: float = 1.0
    sleep: Any = time.sleep

    def request(self, path: str, method: str = "GET", body: Any = None) -> Any:
        method = method.upper()
        url = self.base_url + "/" + path.lstrip("/")
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        attempts = self.max_retries + 1 if method == "GET" else 1
        for attempt in range(attempts):
            last = attempt + 1 == attempts
            backoff = self.backoff * (2**attempt)
            try:
                with _open(request, timeout=self.timeout) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as exc:
                if not last and (exc.code == 429 or 500 <= exc.code < 600):
                    self.sleep(_retry_delay(exc.headers.get("Retry-After"), backoff))
                    continue
                detail = _safe_error(exc.read().decode(errors="replace")[:500], self.token)
                raise SyncError(
                    f"Control D API {method} {path} failed ({exc.code}): {detail}"
                ) from exc
            except urllib.error.URLError as exc:
                if not last:
                    self.sleep(backoff)
                    continue
                raise SyncError(
                    f"Control D API request failed: {_safe_error(str(exc.reason), self.token)}"
                ) from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SyncError(f"Control D returned invalid JSON for {path}") from exc


def list_profiles(client: ControlDClient) -> list[dict[str, Any]]:
    return _items(client.request("/profiles"))


__all__ = ["ControlDClient", "list_profiles"]
