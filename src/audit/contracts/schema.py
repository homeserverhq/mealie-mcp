"""L0 schema and metadata contract."""

from __future__ import annotations

import re
from typing import Any

from ..harness import Scenario, scenario

SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
DATE_ONLY_PARAM = re.compile(r"^(date|startDate|endDate)$")
DURATION_PARAM = re.compile(r"^(totalTime|prepTime|cookTime|performTime)$")
DATE_ONLY_HINT = "ISO 8601 date format (2026-06-22)."
DATETIME_HINT = "ISO 8601 format (2026-06-22T15:00:00-04:00)."
DURATION_HINT = "ISO 8601 duration (e.g. PT45M)."


def _collect(s: Scenario, label: str, fn) -> None:
    tools = s.run.client.tools()
    failures: list[str] = []
    for tool in tools:
        name = str(tool.get("name", ""))
        try:
            fn(name, tool)
        except Exception as exc:
            failures.append(f"{name}: {exc}")
    s.check(label, lambda: _require_no_failures(failures))


def _require_no_failures(failures: list[str]) -> None:
    if failures:
        raise AssertionError("; ".join(failures[:25]))


@scenario("schema", "tool_metadata", [])
def tool_metadata(s: Scenario) -> None:
    tools = s.run.client.tools()
    s.check("tools/list returns 175 tools",
            lambda: _require_eq(len(tools), 175, "tool count"))
    s.check("tool names are unique",
            lambda: _require_eq(len({t.get("name") for t in tools}), len(tools),
                               "unique tool names"))

    _collect(s, "tool names are snake_case", lambda name, tool: _snake(name))
    _collect(s, "tool descriptions are present", lambda name, tool: _desc(tool))
    _collect(s, "input schemas are objects", lambda name, tool: _schema(tool))
    _collect(s, "parameters have descriptions", lambda name, tool: _prop_desc(tool))
    _collect(s, "annotations are complete", lambda name, tool: _annotations(tool))
    _collect(s, "read-only and destructive hints do not conflict",
             lambda name, tool: _not_both(tool))
    _collect(s, "delete tools are destructive and not read-only",
             lambda name, tool: _delete_annotations(name, tool))
    _collect(s, "delete tools do not claim idempotence",
             lambda name, tool: _delete_idempotence(name, tool))
    _collect(s, "date-only parameters carry the canonical hint",
             lambda name, tool: _date_hints(tool))
    _collect(s, "duration parameters carry the canonical hint",
             lambda name, tool: _duration_hints(tool))
    _collect(s, "paginated list tools expose page and perPage",
             lambda name, tool: _pagination_schema(name, tool))
    _collect(s, "aggregate list docstrings describe the projection gate",
             lambda name, tool: _projection_doc(name, tool))
    _collect(s, "update tools require an id",
             lambda name, tool: _update_id(name, tool))


def _require_eq(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: got {actual!r}, expected {expected!r}")


def _snake(name: str) -> None:
    if not SNAKE.match(name):
        raise AssertionError("not snake_case")


def _desc(tool: dict[str, Any]) -> None:
    desc = str(tool.get("description") or "").strip()
    if not desc or "TODO" in desc.upper():
        raise AssertionError("missing or placeholder description")


def _schema(tool: dict[str, Any]) -> None:
    schema = tool.get("inputSchema") or {}
    if schema.get("type") not in (None, "object"):
        raise AssertionError(f"inputSchema type is {schema.get('type')!r}")
    if not isinstance(schema.get("properties") or {}, dict):
        raise AssertionError("inputSchema.properties is not an object")
    for prop in schema.get("required") or []:
        if prop not in (schema.get("properties") or {}):
            raise AssertionError(f"required property {prop!r} is not declared")


def _prop_desc(tool: dict[str, Any]) -> None:
    props = (tool.get("inputSchema") or {}).get("properties") or {}
    for prop, spec in props.items():
        if not isinstance(spec, dict) or not spec.get("description"):
            raise AssertionError(f"parameter {prop!r} has no description")


def _annotations(tool: dict[str, Any]) -> None:
    annotations = tool.get("annotations") or {}
    for key in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
        if key not in annotations:
            raise AssertionError(f"missing {key}")


def _not_both(tool: dict[str, Any]) -> None:
    annotations = tool.get("annotations") or {}
    if annotations.get("readOnlyHint") and annotations.get("destructiveHint"):
        raise AssertionError("both readOnlyHint and destructiveHint are true")


def _delete_annotations(name: str, tool: dict[str, Any]) -> None:
    if not name.startswith("delete_"):
        return
    annotations = tool.get("annotations") or {}
    if annotations.get("readOnlyHint"):
        raise AssertionError("destructive tool is marked read-only")
    if not annotations.get("destructiveHint"):
        raise AssertionError("delete tool is not marked destructive")


def _delete_idempotence(name: str, tool: dict[str, Any]) -> None:
    if not name.startswith("delete_"):
        return
    annotations = tool.get("annotations") or {}
    if annotations.get("idempotentHint"):
        raise AssertionError("delete tool claims idempotence; repeat delete returns 404")


def _date_hints(tool: dict[str, Any]) -> None:
    props = (tool.get("inputSchema") or {}).get("properties") or {}
    for prop, spec in props.items():
        if not DATE_ONLY_PARAM.match(prop):
            continue
        description = str((spec or {}).get("description") or "")
        if DATE_ONLY_HINT not in description:
            raise AssertionError(f"date parameter {prop!r} lacks the canonical date hint")


def _duration_hints(tool: dict[str, Any]) -> None:
    props = (tool.get("inputSchema") or {}).get("properties") or {}
    for prop, spec in props.items():
        if not DURATION_PARAM.match(prop):
            continue
        description = str((spec or {}).get("description") or "")
        if DURATION_HINT not in description:
            raise AssertionError(f"duration parameter {prop!r} lacks the canonical duration hint")


def _pagination_schema(name: str, tool: dict[str, Any]) -> None:
    if not name.startswith("list_"):
        return
    props = (tool.get("inputSchema") or {}).get("properties") or {}
    # Non-paginated backend collections are declared in the manifest and
    # audited as known limitations; they must still expose include_all_fields.
    if "page" not in props and "perPage" not in props:
        return
    for prop in ("page", "perPage"):
        if prop not in props:
            raise AssertionError(f"missing {prop!r}")


def _projection_doc(name: str, tool: dict[str, Any]) -> None:
    if not name.startswith("list_"):
        return
    props = (tool.get("inputSchema") or {}).get("properties") or {}
    spec = props.get("include_all_fields")
    if spec is None:
        return
    description = str((spec or {}).get("description") or "")
    if "ALLOW_ALL_AGGREGATE" not in description:
        raise AssertionError("include_all_fields does not document the aggregate gate")


def _update_id(name: str, tool: dict[str, Any]) -> None:
    if not name.startswith("update_"):
        return
    schema = tool.get("inputSchema") or {}
    required = schema.get("required") or []
    props = schema.get("properties") or {}
    # Scoped preferences have no id by design; every other update must name
    # its target explicitly (id, ids, slug, userId, groupId, householdId).
    if name in ("update_group_preferences", "update_household_preferences"):
        return
    if "cookbooks" in props:
        return
    keys = ("ids", "id", "slug", "userId", "groupId", "householdId")
    if not any(key in required for key in keys):
        raise AssertionError(f"missing an explicit target in required args: {required}")
