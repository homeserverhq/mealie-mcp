"""Assertion helpers used by Mealie MCP audit contracts."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, Iterable
from urllib.parse import urlparse

from .mcp_client import AuditError, decode_items, decode_toon

DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_OFFSET = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)
DURATION = re.compile(r"^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+(\.\d+)?S)?)?$")


def require(condition: Any, message: str) -> None:
    if not condition:
        raise AuditError(message)


def require_ok(call, label: str = "") -> None:
    if call.is_error:
        raise AuditError(f"{label or call.name} failed: {call.error}")


def require_keys(data: dict[str, Any], *keys: str) -> None:
    require(isinstance(data, dict),
            f"expected a dict response, got {type(data).__name__}")
    missing = [key for key in keys if key not in data]
    require(not missing, f"response is missing keys {missing}; got {sorted(data)}")


def require_list(value: Any, field: str) -> list[Any]:
    require(isinstance(value, list), f"{field} is {type(value).__name__}, expected list")
    return value


def items_of(call, field: str = "items") -> list[Any]:
    return decode_items(call.data, call.name, field)


def find_item(items: Iterable[Any], **fields: Any) -> dict[str, Any]:
    for item in items:
        if isinstance(item, dict) and all(item.get(key) == value for key, value in fields.items()):
            return item
    sample = [
        {key: item.get(key) for key in fields}
        for item in list(items)[:3]
        if isinstance(item, dict)
    ]
    raise AuditError(f"no item matched {fields}; first matches: {sample!r}")


def find_item_ci(items: Iterable[Any], key: str, value: str) -> dict[str, Any]:
    wanted = value.casefold()
    for item in items:
        if isinstance(item, dict) and str(item.get(key, "")).casefold() == wanted:
            return item
    raise AuditError(f"no item with {key}={value!r}")


def require_page(data: dict[str, Any], tool: str = "list") -> tuple[list[Any], int, int, int, int]:
    """Validate the standard offset page envelope.

    Returns ``(items, page, per_page, total, total_pages)``. Pagination
    metadata must be top-level and structured; a page object nested inside
    ``items`` is a contract violation.
    """
    require(isinstance(data, dict), f"{tool}: response is not a dict")
    items = decode_items(data, tool, "items")
    page = data.get("page")
    per_page = data.get("per_page")
    total = data.get("total")
    total_pages = data.get("total_pages")
    require(isinstance(page, int), f"{tool}: page is {page!r}, expected int")
    require(isinstance(per_page, int), f"{tool}: per_page is {per_page!r}, expected int")
    require(isinstance(total, int), f"{tool}: total is {total!r}, expected int")
    require(isinstance(total_pages, int),
            f"{tool}: total_pages is {total_pages!r}, expected int")
    require(page >= 1, f"{tool}: page is {page}, expected >= 1")
    require(1 <= per_page <= 200, f"{tool}: per_page is {per_page}, expected 1..200")
    require(total >= 0, f"{tool}: total is {total}, expected >= 0")
    expected_pages = 0 if total == 0 else (total + per_page - 1) // per_page
    require(total_pages == expected_pages,
            f"{tool}: total_pages is {total_pages}, expected {expected_pages} "
            f"for total={total}, per_page={per_page}")
    require(len(items) <= per_page,
            f"{tool}: returned {len(items)} items for per_page={per_page}")
    return items, page, per_page, total, total_pages


def require_date_only(value: Any, field: str) -> str:
    require(isinstance(value, str) and DATE_ONLY.match(value),
            f"{field} is {value!r}, expected YYYY-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise AuditError(f"{field} is not a real date: {value!r} ({exc})") from exc
    return value


def require_datetime_offset(value: Any, field: str) -> str:
    require(isinstance(value, str) and DATETIME_OFFSET.match(value),
            f"{field} is {value!r}, expected ISO 8601 with an explicit offset")
    return value


def require_duration(value: Any, field: str) -> str:
    require(isinstance(value, str) and DURATION.match(value),
            f"{field} is {value!r}, expected an ISO 8601 duration such as PT45M")
    return value


def require_absolute_url(value: Any, field: str) -> str:
    require(isinstance(value, str) and value.startswith(("http://", "https://")),
            f"{field} is {value!r}, expected an absolute URL")
    parsed = urlparse(value)
    require(bool(parsed.netloc), f"{field} has no host: {value!r}")
    return value


def require_contains_path(value: Any, field: str, *parts: str) -> str:
    require(isinstance(value, str), f"{field} is {value!r}, expected a string")
    parsed = urlparse(value)
    for part in parts:
        require(part in parsed.path,
                f"{field} path {parsed.path!r} is missing {part!r}")
    return value


def require_count_eq(data: dict[str, Any], field: str, expected: int) -> None:
    actual = data.get(field)
    require(actual == expected, f"{field} is {actual!r}, expected {expected}")


def require_at_most(value: Any, maximum: int, field: str) -> None:
    require(isinstance(value, int), f"{field} is {type(value).__name__}, expected int")
    require(value <= maximum, f"{field} is {value}, expected <= {maximum}")


def require_not_empty(items: list[Any], label: str) -> None:
    require(bool(items), f"{label} returned an empty list")


def require_empty(items: list[Any], label: str) -> None:
    require(not items, f"{label} returned {len(items)} item(s), expected none")


def require_contains(items: list[Any], label: str, **fields: Any) -> dict[str, Any]:
    try:
        return find_item(items, **fields)
    except AuditError as exc:
        raise AuditError(f"{label}: {exc}") from exc


def require_not_contains(items: list[Any], label: str, **fields: Any) -> None:
    for item in items:
        if isinstance(item, dict) and all(item.get(k) == v for k, v in fields.items()):
            raise AuditError(f"{label}: unexpectedly found item matching {fields}")


def require_no_raw_binary(text: str, label: str) -> None:
    require("\x00" not in text, f"{label}: response contains NUL bytes")
    require("%PDF-" not in text[:200], f"{label}: response contains raw PDF bytes")
    require("\x89PNG" not in text[:200], f"{label}: response contains raw PNG bytes")


def require_no_secret(text: str, secrets: Iterable[str], label: str) -> None:
    for secret in secrets:
        if secret and secret in text:
            raise AuditError(f"{label}: response leaks a credential")


def require_jsonable(data: Any, label: str) -> None:
    try:
        json.dumps(data)
    except (TypeError, ValueError) as exc:
        raise AuditError(f"{label} is not JSON-serializable: {exc}") from exc


def scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(scalar_text(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}={scalar_text(v)}" for k, v in value.items())
    return str(value)


def decode_map(data: dict[str, Any], field: str, tool: str) -> dict[str, Any]:
    """Decode a TOON object field (used for non-page aggregate responses)."""
    value = decode_toon(data.get(field), tool, field)
    require(isinstance(value, dict), f"{tool}: {field} is {type(value).__name__}, expected object")
    return value
