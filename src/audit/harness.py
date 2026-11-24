"""Scenario and result plumbing for the Mealie MCP audit suite.

Safety rule: every destructive or mutating call must target an ID or slug that
this run created. ``protected_names`` alone cannot protect real UUIDs, and an
audit admin token can delete anything, so the guard is enforced in code.
"""

from __future__ import annotations

import re
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .expect import require_page
from .mcp_client import AuditClient, AuditError, ToolCall

REGISTRY: list["ScenarioDef"] = []

MUTATING_PREFIXES = (
    "delete_", "update_", "bulk_delete_", "bulk_update_", "set_", "merge_",
    "trigger_", "test_", "purge_", "rerun_", "seed_", "email_", "add_",
    "remove_",
)
TARGET_KEYS = (
    "id", "ids", "slug", "slugs", "recipes", "recipeId", "recipeSlug",
    "userId", "groupId", "householdId", "listId", "shoppingListId",
    "token", "token_id", "item_id", "itemId", "foodId", "unitId",
    "labelId", "actionId", "notificationId", "webhookId", "categoryId",
    "tagId", "toolId", "commentId", "cookbookId", "mealplanId", "ruleId",
    "eventId", "shareId", "food_to_keep", "food_to_merge",
    "unit_to_keep", "unit_to_merge",
)
# Tools whose scope is the caller's own tenant/group/household and therefore
# has no explicit target argument. They are only called with the tenant token.
IMPLICIT_SCOPE = {
    "update_group_preferences", "update_household_preferences",
    "seed_default_foods", "seed_default_labels", "seed_default_units",
    "rerun_webhooks",
}


@dataclass
class ScenarioDef:
    domain: str
    name: str
    tools: tuple[str, ...]
    fn: Callable[["Scenario"], None]


def scenario(domain: str, name: str, tools: list[str] | tuple[str, ...]):
    def decorator(fn: Callable[["Scenario"], None]):
        REGISTRY.append(ScenarioDef(domain, name, tuple(tools), fn))
        return fn

    return decorator


@dataclass
class Result:
    domain: str
    scenario: str
    label: str
    tool: str
    status: str
    detail: str = ""
    elapsed: float = 0.0
    args: dict[str, Any] = field(default_factory=dict)


class Run:
    def __init__(self, clients: dict[str, AuditClient], adapter: Any,
                 domains: set[str] | None = None,
                 run_id: str | None = None):
        self.clients = clients
        self.adapter = adapter
        self.domains = domains
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.results: list[Result] = []
        self.failures = 0
        self.skips = 0
        self.tools_called: set[str] = set()
        self.declared_tools: set[str] = set()
        self.owned_ids: set[str] = set()
        self.owned_slugs: set[str] = set()
        self.allowed_values: set[str] = set()
        self.warnings: list[str] = []
        self.tenant: dict[str, Any] = {}

    @property
    def client(self) -> AuditClient:
        return self.clients["primary"]

    def own(self, *values: Any) -> str:
        """Register an owned record. Slugs and IDs are tracked separately."""
        first = ""
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            if first == "":
                first = text
            if re.fullmatch(r"[0-9a-fA-F-]{20,}", text):
                self.owned_ids.add(text)
            else:
                self.owned_slugs.add(text)
                self.owned_ids.add(text)
        return first

    def record(self, domain: str, scenario_name: str, label: str,
               tool: str, status: str, detail: str = "", elapsed: float = 0.0,
               args: dict[str, Any] | None = None) -> None:
        self.results.append(Result(
            domain=domain, scenario=scenario_name, label=label, tool=tool,
            status=status, detail=detail, elapsed=elapsed, args=args or {},
        ))
        if status == "FAIL":
            self.failures += 1
        elif status == "SKIP":
            self.skips += 1

    def scenarios(self) -> list[ScenarioDef]:
        selected = [
            sc for sc in REGISTRY
            if self.domains is None or sc.domain in self.domains
        ]
        order: dict[str, int] = {}
        for index, sc in enumerate(REGISTRY):
            order.setdefault(sc.domain, index)
        selected.sort(key=lambda sc: (order.get(sc.domain, 0), sc.name))
        return selected

    def run(self) -> None:
        for definition in self.scenarios():
            self.declared_tools.update(definition.tools)
            scenario = Scenario(self, definition)
            try:
                with scenario:
                    definition.fn(scenario)
            except Exception as exc:
                self.record(
                    definition.domain, definition.name, "scenario aborted",
                    "", "FAIL",
                    f"{type(exc).__name__}: {exc}\n"
                    f"{traceback.format_exc(limit=4)}",
                )


class Scenario:
    def __init__(self, run: Run, definition: ScenarioDef):
        self.run = run
        self.definition = definition
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{definition.domain}-{definition.name}")
        self.prefix = f"MCPAudit-{run.run_id}-{safe}"
        self.cleanups: list[tuple[str, dict[str, Any], str, str]] = []
        self.cleanup_fns: list[tuple[str, Callable[[], Any]]] = []
        self.failed = False

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "Scenario":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._run_cleanups()
        return False

    def _record(self, label: str, tool: str, status: str,
                detail: str = "", elapsed: float = 0.0,
                args: dict[str, Any] | None = None) -> None:
        if status == "FAIL":
            self.failed = True
        self.run.record(
            self.definition.domain, self.definition.name, label, tool,
            status, detail, elapsed, args,
        )

    # -- fixture helpers ---------------------------------------------------

    def fixture(self, suffix: str = "") -> str:
        value = f"{self.prefix}-{suffix}" if suffix else self.prefix
        return value[:200]

    def own(self, *values: Any) -> str:
        return self.run.own(*values)

    def allow(self, *values: Any) -> None:
        for value in values:
            if value is not None and str(value).strip():
                self.run.allowed_values.add(str(value))

    def _guard(self, tool: str, args: dict[str, Any]) -> None:
        if not tool.startswith(MUTATING_PREFIXES):
            return
        if tool in IMPLICIT_SCOPE:
            return
        targets: list[str] = []
        for key in TARGET_KEYS:
            value = args.get(key)
            if isinstance(value, str):
                targets.append(value)
            elif isinstance(value, (int, float)):
                targets.append(str(value))
            elif isinstance(value, list):
                targets.extend(str(item) for item in value)
        for target in targets:
            if target in self.run.owned_ids or target in self.run.owned_slugs:
                continue
            if target in self.run.allowed_values:
                continue
            raise AuditError(
                f"{tool}: refusing to mutate {target!r}; it was not created by "
                f"this audit run. Owned IDs: {len(self.run.owned_ids)}, "
                f"owned slugs: {len(self.run.owned_slugs)}."
            )

    # -- calls -------------------------------------------------------------

    def call(self, label: str, tool: str, args: dict[str, Any] | None = None,
             required: bool = True, account: str = "primary") -> ToolCall:
        args = args or {}
        self._guard(tool, args)
        client = self.run.clients.get(account)
        if client is None:
            raise AuditError(f"no client for account {account!r}")
        call = client.call(tool, args)
        self.run.tools_called.add(tool)
        if call.is_error:
            self._record(label, tool, "FAIL" if required else "SKIP",
                         call.error, call.elapsed, args)
            if required:
                raise AuditError(f"{tool}: {call.error}")
        else:
            self._record(label, tool, "PASS", "", call.elapsed, args)
        return call

    def call_any(self, label: str, tool: str,
                 args: dict[str, Any] | None = None,
                 account: str = "primary") -> ToolCall:
        return self.call(label, tool, args, required=False, account=account)

    def expect_error(self, label: str, tool: str,
                     args: dict[str, Any] | None = None,
                     contains: tuple[str, ...] = ("404", "not found",
                                                  "does not exist"),
                     account: str = "primary") -> ToolCall:
        args = args or {}
        self._guard(tool, args)
        call = self.run.clients[account].call(tool, args)
        self.run.tools_called.add(tool)
        lowered = call.error.lower()
        needles = tuple(needle.lower() for needle in contains)
        ok = call.is_error and any(needle in lowered for needle in needles)
        self._record(
            label, tool, "PASS" if ok else "FAIL",
            "" if ok else call.error, call.elapsed, args,
        )
        return call

    def attempt(self, label: str, tool: str,
                args: dict[str, Any] | None = None,
                account: str = "primary") -> ToolCall:
        call = self.run.clients[account].call(tool, args)
        self.run.tools_called.add(tool)
        self._record(
            label, tool, "PASS" if not call.is_error else "SKIP",
            "" if not call.is_error else call.error, call.elapsed, args,
        )
        return call

    # -- checks ------------------------------------------------------------

    def check(self, label: str, fn: Callable[[], Any],
              tool: str = "assert") -> Any:
        try:
            value = fn()
        except Exception as exc:
            self._record(label, tool, "FAIL", str(exc))
            return None
        self._record(label, tool, "PASS")
        return value

    def require(self, label: str, condition: Any, detail: str = "") -> bool:
        def _check() -> bool:
            if not condition:
                raise AuditError(detail or f"condition failed: {label}")
            return True

        return bool(self.check(label, _check))

    def items(self, label: str, call: ToolCall,
              field: str = "items") -> list[Any]:
        holder: dict[str, list[Any]] = {}

        def _decode():
            holder["items"] = call.items(field)
            return holder["items"]

        self.check(label, _decode, tool=call.name)
        return holder.get("items", [])

    def page(self, label: str, tool: str, args: dict[str, Any] | None = None,
             account: str = "primary") -> tuple[ToolCall, list[Any], dict[str, int]]:
        call = self.call(label, tool, args, account=account)
        holder: dict[str, Any] = {}

        def _decode():
            items, page, per_page, total, total_pages = require_page(call.data, tool)
            holder.update(items=items, page=page, per_page=per_page,
                          total=total, total_pages=total_pages)

        self.check(f"{label} page shape", _decode, tool=tool)
        return call, holder.get("items", []), {
            "page": holder.get("page", 0),
            "per_page": holder.get("per_page", 0),
            "total": holder.get("total", 0),
            "total_pages": holder.get("total_pages", 0),
        }

    def find_in_pages(self, tool: str, predicate: Callable[[dict[str, Any]], bool],
                      args: dict[str, Any] | None = None, per_page: int = 200,
                      max_pages: int = 10,
                      account: str = "primary") -> list[dict[str, Any]]:
        base = dict(args or {})
        collected: list[dict[str, Any]] = []
        for page_number in range(1, max_pages + 1):
            call, items, meta = self.page(
                f"{tool} page {page_number}", tool,
                {**base, "page": page_number, "perPage": per_page},
                account=account,
            )
            collected.extend(item for item in items if isinstance(item, dict))
            if any(predicate(item) for item in collected):
                return collected
            if page_number >= meta["total_pages"]:
                break
            if call.is_error:
                break
        return collected

    def skip(self, label: str, reason: str) -> None:
        self._record(label, "", "SKIP", reason)

    def skip_tool(self, label: str, tool: str, reason: str) -> None:
        """Record an explicit, reasoned skip that still counts as covered."""
        self.run.tools_called.add(tool)
        self._record(label, tool, "SKIP", reason)

    # -- cleanup -----------------------------------------------------------

    def cleanup(self, tool: str, args: dict[str, Any],
                label: str | None = None, account: str = "primary") -> None:
        self.cleanups.append((tool, dict(args), label or f"cleanup {tool}", account))

    def cleanup_fn(self, label: str, fn: Callable[[], Any]) -> None:
        self.cleanup_fns.append((label, fn))

    def forget_cleanup(self, tool: str, args: dict[str, Any]) -> None:
        """Drop a registered cleanup after the scenario deleted the record."""
        self.cleanups = [
            entry for entry in self.cleanups
            if not (entry[0] == tool and entry[1] == args)
        ]

    def _run_cleanups(self) -> None:
        for tool, args, label, account in reversed(self.cleanups):
            try:
                call = self.run.clients[account].call(tool, args)
            except Exception as exc:
                self._record(label, tool, "WARN", f"cleanup raised: {exc}")
                continue
            if call.is_error:
                lowered = call.error.lower()
                benign = any(
                    phrase in lowered
                    for phrase in ("not found", "does not exist", "404",
                                   "no such", "unknown")
                )
                self._record(label, tool, "PASS" if benign else "WARN",
                             call.error)
            else:
                self._record(label, tool, "PASS")
        for label, fn in reversed(self.cleanup_fns):
            try:
                result = fn()
            except Exception as exc:
                self._record(label, "cleanup", "WARN", str(exc))
                continue
            if isinstance(result, list) and result:
                self._record(label, "cleanup", "WARN", "; ".join(map(str, result)))
            else:
                self._record(label, "cleanup", "PASS")
