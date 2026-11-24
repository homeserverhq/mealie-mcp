"""Mealie-specific adapter for the generic audit harness."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import yaml

from .backend import RESOURCES, MealieBackend
from .mcp_client import AuditClient


def _decode_jwt(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


class MealieAdapter:
    name = "mealie"
    allow_destructive = True

    def __init__(self, token: str):
        self.token = token
        self.manifest = yaml.safe_load(
            Path(__file__).with_name("manifest.yaml").read_text(encoding="utf-8")
        )
        self.backend = MealieBackend(token=token) if token else None
        self.identity = _decode_jwt(token) if token else {}
        self.profile: dict[str, Any] = {}
        self.aggregate_flag = os.getenv("ALLOW_ALL_AGGREGATE", "false").lower() in (
            "1", "true", "yes",
        )
        self.allowed_mutation_ids: set[str] = set()
        self.protected_ids: dict[str, set[str]] = {}
        self.snapshot: dict[str, Any] = {}
        self.tenant: dict[str, Any] = {}
        self.warnings: list[str] = []
        self.tenant_enabled = os.getenv("AUDIT_TENANT", "true").lower() in (
            "1", "true", "yes",
        )

    # -- adapter interface -------------------------------------------------

    def fixture_name(self, run_id: str, domain: str, scenario: str,
                     suffix: str = "") -> str:
        value = f"MCPAudit-{run_id}-{domain}-{scenario}"
        if suffix:
            value = f"{value}-{suffix}"
        return value[:200]

    def is_protected(self, name: str) -> bool:
        return False

    def preflight(self, client: AuditClient, run_id: str, full: bool = True) -> list[str]:
        if not full:
            return list(self.warnings)
        if self.backend is None:
            return list(self.warnings)
        self.profile = self.backend.self_profile(self.token)
        if not self.profile:
            raise SystemExit("API key is not accepted by /api/users/self")
        self.snapshot = self.backend.snapshot()
        self.protected_ids = {
            resource: set(ids)
            for resource, ids in self.snapshot.get("ids", {}).items()
        }
        own_user = str(self.profile.get("id") or "")
        if own_user:
            self.allowed_mutation_ids.add(own_user)
        if not self.aggregate_flag:
            self.warnings.append(
                "ALLOW_ALL_AGGREGATE=false: aggregate list calls intentionally "
                "ignore include_all_fields; projection contracts assert that "
                "documented behavior."
            )
        if not self.profile.get("admin"):
            self.warnings.append(
                "Audit key is not admin; admin/tenant contracts will be skipped."
            )
        if self.tenant_enabled and self.profile.get("admin"):
            self.ensure_tenant(run_id)
        elif not self.tenant_enabled:
            self.warnings.append(
                "AUDIT_TENANT=false: cross-tenant isolation contracts will be skipped."
            )
        return list(self.warnings)

    def residue(self, client: AuditClient, run_id: str) -> dict[str, Any]:
        prefix = f"MCPAudit-{run_id}"
        found = self.backend.residue(prefix)
        post = self.backend.snapshot()
        before = self.snapshot.get("counts", {})
        after = post.get("counts", {})
        # Mealie writes a "Recipe Created" timeline event for every created
        # recipe. Those rows are not fixture-prefixed and cannot be removed by
        # the audit, so they are accounted for as a documented side effect.
        side_effect_resources = {"timeline_event"}
        diffs = {
            resource: {"before": before.get(resource), "after": after.get(resource)}
            for resource in RESOURCES
            if resource not in side_effect_resources
            and before.get(resource) != after.get(resource)
        }
        side_effects = {
            resource: {"before": before.get(resource), "after": after.get(resource)}
            for resource in side_effect_resources
            if before.get(resource) != after.get(resource)
        }
        missing_ids = {}
        for resource in ("user", "group", "household"):
            before_ids = set(self.snapshot.get("ids", {}).get(resource, []))
            after_ids = set(post.get("ids", {}).get(resource, []))
            leaked = sorted(before_ids - after_ids)
            if leaked:
                missing_ids[resource] = leaked
        return {
            "prefix": prefix,
            "counts": found.get("counts", {}),
            "examples": found.get("examples", {}),
            "errors": found.get("errors", {}),
            "count_diffs": diffs,
            "side_effects": side_effects,
            "missing_pre_existing": missing_ids,
            "tenant": self.tenant,
        }

    def capabilities(self) -> dict[str, Any]:
        return dict(self.manifest.get("capabilities", {}))

    # -- tenant ------------------------------------------------------------

    def ensure_tenant(self, run_id: str) -> dict[str, Any]:
        if self.tenant:
            return self.tenant
        tag = run_id.lower()
        group_name = f"MCPAudit-{tag}-group"
        household_name = f"MCPAudit-{tag}-household"
        username = f"mcpaudit_{tag}"
        password = f"AuditPass-{tag}"
        group = self.backend.create_group(group_name)
        household = self.backend.create_household(household_name, group["id"])
        user = self.backend.create_user({
            "username": username,
            "fullName": f"MCP Audit {run_id}",
            "email": f"{username}@example.com",
            "password": password,
            "admin": False,
            "group": group_name,
            "household": household_name,
            "canOrganize": True,
            "canManageHousehold": True,
            "canManage": True,
        })
        member_username = f"mcpaudit_{tag}_member"
        member = self.backend.create_user({
            "username": member_username,
            "fullName": f"MCP Audit Member {run_id}",
            "email": f"{member_username}@example.com",
            "password": password,
            "admin": False,
            "group": group_name,
            "household": household_name,
            "canOrganize": False,
        })
        token = self.backend.login(username, password)
        profile = self.backend.self_profile(token)
        self.tenant = {
            "group_id": group["id"],
            "group_slug": group.get("slug", ""),
            "group_name": group_name,
            "household_id": household["id"],
            "household_slug": household.get("slug", ""),
            "household_name": household_name,
            "user_id": user["id"],
            "member_user_id": member["id"],
            "member_username": member_username,
            "username": username,
            "password": password,
            "token": token,
            "profile": profile,
            "extra_households": [],
        }
        # A freshly created group also receives a default household.
        for record in self.backend.households():
            if record.get("groupId") == group["id"] and record.get("id") != household["id"]:
                self.tenant["extra_households"].append(record["id"])
        self.allowed_mutation_ids.update({
            self.tenant["group_id"],
            self.tenant["household_id"],
            self.tenant["user_id"],
            self.tenant["member_user_id"],
            *self.tenant["extra_households"],
        })
        self.warnings.append(
            f"Audit tenant created: group={group_name} user={username}; it is "
            "deleted during teardown."
        )
        return self.tenant

    def tenant_token(self) -> str:
        return str(self.tenant.get("token") or "")

    def teardown_tenant(self) -> list[str]:
        """Delete the audit tenant in dependency order.

        Mealie auto-creates a default household when a group is created, so
        every household in the group must be deleted before the group.
        """
        errors: list[str] = []
        if not self.tenant or self.backend is None:
            return errors
        user_id = self.tenant.get("user_id")
        member_id = self.tenant.get("member_user_id")
        group_id = self.tenant.get("group_id")
        for label, target in (("member", member_id), ("user", user_id)):
            if target:
                try:
                    self.backend.delete_path(f"/api/admin/users/{target}")
                except Exception as exc:
                    errors.append(f"delete {label}: {exc}")
        if group_id:
            try:
                for record in self.backend.households():
                    if record.get("groupId") == group_id:
                        try:
                            self.backend.delete_path(
                                f"/api/admin/households/{record['id']}"
                            )
                        except Exception as exc:
                            errors.append(f"delete household {record.get('id')}: {exc}")
                self.backend.delete_path(f"/api/admin/groups/{group_id}")
            except Exception as exc:
                errors.append(f"delete group: {exc}")
        return errors

    def close(self) -> None:
        if self.backend is not None:
            self.backend.close()
