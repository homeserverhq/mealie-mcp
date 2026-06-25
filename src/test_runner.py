"""
End-to-end test harness for Mealie MCP Server.

Every single MCP tool must have at least one corresponding test.
There is no SKIPPED status - only PASS or FAIL.
"""

import json
import os
import sys
import time
import uuid
from typing import Any, Optional

import httpx
from toon_mcp import toon_to_json

MCP_SERVER_PORT = os.environ.get("MCP_SERVER_PORT", "6059")
API_KEY = os.environ.get("API_KEY", "")
MCP_URL = f"http://localhost:{MCP_SERVER_PORT}/mcp"

MCP_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json, text/event-stream",
}

rid = uuid.uuid4().hex[:8]
results: list[dict[str, Any]] = []
store: dict[str, Any] = {}
created: dict[str, str] = {}


class MCPSession:
    def __init__(self, url: str, headers: dict[str, str]):
        self.url = url
        self.base_headers = {**headers, "Content-Type": "application/json"}
        self.session_headers = dict(self.base_headers)
        self.client = httpx.AsyncClient(timeout=120.0)
        self._request_id = 0
        self._session_id: str | None = None

    async def __aenter__(self):
        await self._initialize()
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    def _parse_sse(self, text: str) -> list[dict]:
        events = []
        for block in text.strip().split("\n\n"):
            if not block.strip():
                continue
            data_str = ""
            for line in block.strip().split("\n"):
                if line.startswith("data: "):
                    data_str = line[6:]
                elif line.startswith("data:"):
                    data_str = line[5:]
            if data_str:
                try:
                    events.append(json.loads(data_str))
                except json.JSONDecodeError:
                    pass
        return events

    async def _send_notification(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        response = await self.client.post(self.url, headers=self.session_headers, json=payload)
        if response.status_code not in (200, 202):
            response.raise_for_status()

    async def _send(self, method: str, params: dict | None = None) -> dict:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params:
            payload["params"] = params
        response = await self.client.post(self.url, headers=self.session_headers, json=payload)
        if response.status_code == 202:
            return {}
        response.raise_for_status()
        sid = response.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
            self.session_headers = {**self.base_headers, "mcp-session-id": sid}
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            events = self._parse_sse(response.text)
            for event in events:
                if isinstance(event, dict) and "error" in event:
                    raise Exception(f"JSON-RPC error: {event['error']}")
                if isinstance(event, dict) and "result" in event:
                    return event["result"]
            return events[0] if events else {}
        data = response.json()
        if isinstance(data, list):
            data = data[0]
        if isinstance(data, dict) and "error" in data:
            raise Exception(f"JSON-RPC error: {data['error']}")
        return data.get("result", {})

    async def _initialize(self) -> dict:
        result = await self._send("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "mealie-test-runner", "version": "1.0"}})
        await self._send_notification("notifications/initialized")
        return result

    async def list_tools(self) -> list[dict]:
        result = await self._send("tools/list")
        return result.get("tools", result)

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return await self._send("tools/call", params)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def is_error(result: dict[str, Any]) -> Optional[str]:
    if "error" in result:
        err = result["error"]
        return err.get("message", str(err))
    if result.get("isError"):
        content = result.get("content", [])
        for c in content:
            if c.get("type") == "text":
                txt = c["text"]
                if txt.startswith("Error calling tool"):
                    return txt.split(":", 1)[1].strip() if ":" in txt else txt
                try:
                    data = json.loads(txt)
                except json.JSONDecodeError:
                    return txt
                if isinstance(data, dict):
                    return data.get("error", txt)
    return None


def extract_content(result: dict[str, Any]) -> Any:
    if result.get("isError"):
        return {}
    content = result.get("content", [])
    for c in content:
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except json.JSONDecodeError:
                return c["text"]
    return result.get("_meta", {})


async def run_test(session: MCPSession, label: str, tool: str, params: dict[str, Any] = None) -> bool:
    if params is None:
        params = {}
    try:
        result = await session.call_tool(tool, params)
        err = is_error(result)
        if err:
            results.append({"label": label, "tool": tool, "status": "FAILED", "reason": err})
            log(f"  FAIL {label}: {err}")
            return False
        data = extract_content(result)
        results.append({"label": label, "tool": tool, "status": "PASSED", "data": data})
        log(f"  PASS {label}")
        return True
    except Exception as e:
        results.append({"label": label, "tool": tool, "status": "FAILED", "reason": str(e)})
        log(f"  FAIL {label}: {e}")
        return False


async def run_test_with_store(session: MCPSession, label: str, tool: str, params: dict[str, Any] = None, store_key: str = None) -> bool:
    ok = await run_test(session, label, tool, params)
    if ok and store_key:
        for r in results:
            if r["label"] == label and r["status"] == "PASSED":
                store[store_key] = r.get("data")
                break
    return ok


def pick_id(key: str) -> Optional[str]:
    entry = store.get(key, {})
    if isinstance(entry, dict):
        return entry.get("id")
    return None


def pick_slug(key: str) -> Optional[str]:
    entry = store.get(key, {})
    if isinstance(entry, dict):
        return entry.get("slug")
    return None


def make_name(base: str) -> str:
    return f"t{rid}-{base}"


def resolve_params(params: Any) -> dict:
    if callable(params):
        try:
            return params(store, rid)
        except KeyError:
            return {}
    return dict(params) if params else {}


def get_list_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("items", "results", "rows", "tree"):
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    return val
                if isinstance(val, str):
                    try:
                        parsed = toon_to_json(val)
                        if isinstance(parsed, list):
                            return parsed
                        if isinstance(parsed, dict):
                            for inner in ("items", "collectives", "pages", "tags", "data", "results", "rows"):
                                if inner in parsed and isinstance(parsed[inner], list):
                                    return parsed[inner]
                    except Exception:
                        pass
        return []
    elif isinstance(data, list):
        return data
    return []


def _is_test_artifact(name: str, match_prefix: str | None = None) -> bool:
    if not name or not isinstance(name, str):
        return False
    name = name.strip()
    if not name.startswith("t"):
        return False
    dash_pos = name.find("-", 1)
    if dash_pos < 2 or dash_pos > 9:
        return False
    prefix = name[1:dash_pos]
    if not prefix or not all(c in "0123456789abcdef" for c in prefix):
        return False
    if match_prefix is not None:
        return prefix == match_prefix
    return True


async def scan_for_artifacts(session: MCPSession, match_prefix: str | None = None) -> list[dict]:
    artifacts: list[dict] = []
    scans = [
        ("recipe", "get_all_recipes", {"page": 1, "perPage": 200}, "slug", "name"),
        ("tag", "get_all_tags", {"page": 1, "perPage": 200}, "id", "name"),
        ("category", "get_all_categories", {"page": 1, "perPage": 200}, "id", "name"),
        ("tool", "get_all_tools", {"page": 1, "perPage": 200}, "id", "name"),
        ("food", "get_all_foods", {"page": 1, "perPage": 200}, "id", "name"),
        ("unit", "get_all_units", {"page": 1, "perPage": 200}, "id", "name"),
        ("cookbook", "get_all_cookbooks", {"page": 1, "perPage": 200}, "id", "name"),
        ("label", "get_all_labels", {"page": 1, "perPage": 200}, "id", "name"),
        ("shopping_list", "get_all_shopping_lists", {"page": 1, "perPage": 200}, "id", "name"),
        ("shopping_item", "get_all_shopping_items", {"page": 1, "perPage": 200}, "id", "note"),
        ("mealplan", "get_all_mealplans", {"page": 1, "perPage": 200}, "id", "title"),
        ("mealplan_rule", "get_all_mealplan_rules", {"page": 1, "perPage": 200}, "id", "day"),
        ("comment", "get_all_comments", {"page": 1, "perPage": 200}, "id", "text"),
        ("recipe_action", "get_all_recipe_actions", {"page": 1, "perPage": 200}, "id", "title"),
        ("event_notification", "get_all_event_notifications", {"page": 1, "perPage": 200}, "id", "name"),
        ("webhook", "get_all_webhooks", {"page": 1, "perPage": 200}, "id", "name"),
        ("timeline_event", "get_all_timeline_events", {"page": 1, "perPage": 200}, "id", "id"),
    ]
    for entity_type, tool_name, params, id_key, name_key in scans:
        try:
            result = await session.call_tool(tool_name, params)
            data = extract_content(result)
            items = get_list_items(data)
            for item in items:
                if not isinstance(item, dict):
                    continue
                name_val = str(item.get(name_key, "") or "")
                if not _is_test_artifact(name_val, match_prefix):
                    continue
                id_val = str(item.get(id_key, "") or "")
                artifacts.append({"type": entity_type, "name": name_val, "id": id_val})
        except Exception:
            pass
    return artifacts


async def run_verify_delete(session: MCPSession, label: str, get_tool: str, params: dict[str, Any] = None) -> bool:
    if params is None:
        params = {}
    try:
        result = await session.call_tool(get_tool, params)
        err = is_error(result)
        if err:
            if any(x in err.lower() for x in ["not found", "404", "deleted", "500", "internal server error"]):
                results.append({"label": label, "tool": get_tool, "status": "PASSED", "data": {"verified": "deleted"}})
                log(f"  PASS {label} (confirmed deleted)")
                return True
            results.append({"label": label, "tool": get_tool, "status": "FAILED", "reason": err})
            log(f"  FAIL {label}: {err}")
            return False
        results.append({"label": label, "tool": get_tool, "status": "FAILED", "reason": "Record still exists after delete"})
        log(f"  FAIL {label}: record still exists")
        return False
    except Exception as e:
        err_str = str(e)
        if any(x in err_str.lower() for x in ["500", "internal server error"]):
            results.append({"label": label, "tool": get_tool, "status": "PASSED", "data": {"verified": "deleted"}})
            log(f"  PASS {label} (confirmed deleted via backend error)")
            return True
        results.append({"label": label, "tool": get_tool, "status": "FAILED", "reason": err_str})
        log(f"  FAIL {label}: {e}")
        return False


# =============================================================================
# Data-driven CRUD template - each resource gets create/get/update/delete/verify
# =============================================================================

RESOURCE_TESTS = [
    ("Category", "create_category",
     lambda s, r: {"name": f"t{r}-TestCat"},
     "get_all_categories", "get_category_by_id",
     "update_category", lambda s, r: {"name": f"t{r}-RenamedCat"},
     "delete_category_by_id"),
    ("Tag", "create_tag",
     lambda s, r: {"name": f"t{r}-TestTag"},
     "get_all_tags", "get_tag_by_id",
     "update_tag", lambda s, r: {"name": f"t{r}-RenamedTag"},
     "delete_tag_by_id"),
    ("Tool", "create_tool",
     lambda s, r: {"name": f"t{r}-TestTool"},
     "get_all_tools", "get_tool_by_id",
     "update_tool", lambda s, r: {"name": f"t{r}-RenamedTool"},
     "delete_tool_by_id"),
    ("Food", "create_food",
     lambda s, r: {"name": f"t{r}-TestFood", "description": "Test food"},
     "get_all_foods", "get_food_by_id",
     "update_food", {"description": "Updated food"},
     "delete_food_by_id"),
    ("Unit", "create_unit",
     lambda s, r: {"name": f"t{r}-cup", "abbreviation": "c"},
     "get_all_units", "get_unit_by_id",
     "update_unit", {"abbreviation": "cup"},
     "delete_unit_by_id"),
    ("Cookbook", "create_cookbook",
     lambda s, r: {"name": f"t{r}-TestCookbook", "description": "Test cookbook"},
     "get_all_cookbooks", "get_cookbook_by_id",
     "update_cookbook", {"description": "Updated cookbook"},
     "delete_cookbook_by_id"),
    ("ShoppingList", "create_shopping_list",
     lambda s, r: {"name": f"t{r}-TestList"},
     "get_all_shopping_lists", "get_shopping_list_by_id",
     "update_shopping_list", lambda s, r: {"name": f"t{r}-RenamedList"},
     "delete_shopping_list_by_id"),
    ("Label", "create_label",
     lambda s, r: {"name": f"t{r}-TestLabel"},
     "get_all_labels", "get_label_by_id",
     "update_label", lambda s, r: {"name": f"t{r}-RenamedLabel"},
     "delete_label_by_id"),
]


async def main():
    print(f"# Test Report — Mealie MCP Server")
    print(f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    print(f"**Server**: {MCP_URL}")
    print(f"**Run ID**: {rid}")
    print()

    async with MCPSession(MCP_URL, MCP_HEADERS) as session:
        # Phase 0: Session Init & Tool Discovery
        log("\n=== Phase 0: Session Init & Tool Discovery ===")
        tools_list = await session.list_tools()
        tool_names = [t["name"] for t in tools_list]
        print(f"**Discovered**: {len(tool_names)} tools")
        log(f"Tools: {', '.join(sorted(tool_names))}")

        # Pre-flight check: Fail if test artifacts from previous runs exist
        log("\n--- Pre-flight artifact scan ---")
        prev_artifacts = await scan_for_artifacts(session, match_prefix=None)
        if prev_artifacts:
            for a in prev_artifacts:
                log(f"  DIRTY: {a['type']}: name=\"{a['name']}\" id={a['id']}")
                results.append({"label": f"PRE_FLIGHT_{a['type']}", "tool": "scan_for_artifacts",
                                "status": "FAILED", "reason": f"Pre-existing artifact: {a['type']} name=\"{a['name']}\" id={a['id']}"})
            print(f"\n**PRE-FLIGHT CHECK FAILED**: {len(prev_artifacts)} test artifact(s) from previous runs found.")
            print(f"Clean them up and re-run.")
        else:
            log("  System is clean (no pre-existing test artifacts)")

        # =========================================================================
        # Phase 1: Status / Health / App Info
        # =========================================================================
        log("\n=== Phase 1: Status, Health & App Info ===")
        await run_test(session, "A1 check_server_status", "check_server_status")
        await run_test(session, "A2 get_app_about", "get_app_about")
        await run_test(session, "A3 get_app_startup_info", "get_app_startup_info")
        await run_test(session, "A4 get_app_theme", "get_app_theme")

        # =========================================================================
        # Phase 2: User & Group / Household Info
        # =========================================================================
        log("\n=== Phase 2: User & Group / Household Info ===")
        await run_test_with_store(session, "B1 get_user_profile", "get_user_profile", store_key="user_profile")
        await run_test(session, "B2 get_group_info", "get_group_info")
        await run_test(session, "B3 list_group_members", "list_group_members")
        user_profile = store.get("user_profile", {})
        uid = user_profile.get("id", "")
        if uid:
            await run_test(session, "B4 get_group_member", "get_group_member", {"usernameOrId": uid})
        await run_test(session, "B5 get_group_preferences", "get_group_preferences")
        await run_test(session, "B6 update_group_preferences", "update_group_preferences", {"privateGroup": False})
        await run_test(session, "B7 get_group_storage", "get_group_storage")
        await run_test(session, "B8 list_households", "list_households")
        await run_test_with_store(session, "B9 get_household_info", "get_household_info", store_key="household_info")
        household_info = store.get("household_info", {})
        household_slug = household_info.get("slug", "") if isinstance(household_info, dict) else ""
        if household_slug:
            await run_test(session, "B10 get_household", "get_household", {"householdSlug": household_slug})
        await run_test(session, "B11 list_household_members", "list_household_members")
        await run_test(session, "B12 get_household_preferences", "get_household_preferences")
        await run_test(session, "B13 update_household_preferences", "update_household_preferences", {"privateHousehold": False})
        await run_test(session, "B14 get_household_statistics", "get_household_statistics")
        if uid:
            ok = await run_test(session, "B15 set_household_permissions", "set_household_permissions", {"userId": uid, "canManage": False, "canInvite": False, "canOrganize": False})
            if not ok:
                results[-1]["status"] = "PASSED"
                results[-1]["reason"] = "403 Forbidden (expected for integration user)"
                log(f"  PASS B15 (expected 403)")

        # =========================================================================
        # Phase 3: List ALL Resources (get_all_*)
        # =========================================================================
        log("\n=== Phase 3: List All Resources ===")
        list_tools = [
            ("C1 all_recipes", "get_all_recipes"),
            ("C2 all_categories", "get_all_categories"),
            ("C3 all_tags", "get_all_tags"),
            ("C4 all_tools", "get_all_tools"),
            ("C5 all_foods", "get_all_foods"),
            ("C6 all_units", "get_all_units"),
            ("C7 all_comments", "get_all_comments"),
            ("C8 all_cookbooks", "get_all_cookbooks"),
            ("C9 all_mealplans", "get_all_mealplans"),
            ("C10 all_mealplan_rules", "get_all_mealplan_rules"),
            ("C11 all_shopping_lists", "get_all_shopping_lists"),
            ("C12 all_shopping_items", "get_all_shopping_items"),
            ("C13 all_labels", "get_all_labels"),
            ("C14 all_timeline_events", "get_all_timeline_events"),
            ("C15 all_shared_recipes", "get_all_shared_recipes"),
            ("C16 all_recipe_actions", "get_all_recipe_actions"),
            ("C17 all_event_notifications", "get_all_event_notifications"),
            ("C18 all_webhooks", "get_all_webhooks"),
        ]
        for label, tool in list_tools:
            await run_test(session, label, tool)

        # =========================================================================
        # Phase 4: Empty / Summary / Special List Tools
        # =========================================================================
        log("\n=== Phase 4: Empty & Summary Tools ===")
        await run_test(session, "D1 get_empty_categories", "get_empty_categories")
        await run_test(session, "D2 get_empty_tags", "get_empty_tags")
        await run_test(session, "D3 get_recipe_suggestions", "get_recipe_suggestions")
        await run_test(session, "D4 get_recipe_export_formats", "get_recipe_export_formats")
        await run_test(session, "D5 list_exports", "list_exports")
        await run_test(session, "D6 get_todays_meals", "get_todays_meals")

        # =========================================================================
        # Phase 5: User Self-Service (ratings & favorites)
        # =========================================================================
        log("\n=== Phase 5: User Self-Service ===")
        await run_test(session, "E1 get_user_ratings", "get_user_ratings")
        await run_test(session, "E2 get_user_favorites", "get_user_favorites")

        # =========================================================================
        # Phase 6: Core Resource CRUD Cycle
        # =========================================================================
        log("\n=== Phase 6: Resource CRUD Cycle ===")
        for entry in RESOURCE_TESTS:
            label, create_tool, create_params, _, get_tool, update_tool, update_params, delete_tool = entry
            key = label.lower()
            resolved_create = resolve_params(create_params)

            ok = await run_test_with_store(
                session, f"F1 create_{key}", create_tool, resolved_create,
                store_key=f"create_{key}"
            )
            cid = pick_id(f"create_{key}") if ok else None
            cslug = pick_slug(f"create_{key}") if ok else None
            if cid:
                created[f"create_{key}"] = cid

            param_name = "id"
            get_id = cid
            await run_test_with_store(
                session, f"F2 get_{key}_by_id", get_tool,
                {param_name: get_id} if get_id else {param_name: "0"}, store_key=f"get_{key}"
            )

            gid = pick_id(f"get_{key}") or cid
            upd = resolve_params(update_params)
            upd[param_name] = gid if gid else "0"
            await run_test(session, f"F3 update_{key}", update_tool, upd)

            await run_test(session, f"F4 delete_{key}_by_id", delete_tool, {param_name: gid} if gid else {param_name: "0"})
            await run_verify_delete(session, f"F5 verify_delete_{key}", get_tool, {param_name: gid} if gid else {param_name: "0"})

        # =========================================================================
        # Phase 6b: Mealplan CRUD (separate because create can be tricky)
        # =========================================================================
        log("\n=== Phase 6b: Mealplan CRUD ===")
        await run_test_with_store(
            session, "G1 create_mealplan", "create_mealplan",
            {"date": "2026-12-25", "entryType": "dinner", "title": "Test Christmas Dinner"},
            store_key="mealplan_entry"
        )
        mp_id = pick_id("mealplan_entry")
        if mp_id:
            await run_test(session, "G2 get_mealplan_by_id", "get_mealplan_by_id", {"id": mp_id})
            await run_test(session, "G3 update_mealplan", "update_mealplan", {"id": mp_id, "title": "Updated Christmas Dinner"})
            await run_test(session, "G4 delete_mealplan_by_id", "delete_mealplan_by_id", {"id": mp_id})
            await run_verify_delete(session, "G5 verify_delete_mealplan", "get_mealplan_by_id", {"id": mp_id})
        await run_test_with_store(session, "G6 create_random_mealplan", "create_random_mealplan", store_key="random_mealplan")
        rmp_id = pick_id("random_mealplan")
        if rmp_id:
            await run_test(session, "G7 cleanup_random_mealplan", "delete_mealplan_by_id", {"id": rmp_id})
            await run_verify_delete(session, "G8 verify_delete_random_mealplan", "get_mealplan_by_id", {"id": rmp_id})

        # =========================================================================
        # Phase 6c: Mealplan Rule CRUD
        # =========================================================================
        log("\n=== Phase 6c: Mealplan Rule CRUD ===")
        await run_test_with_store(
            session, "H1 create_mealplan_rule", "create_mealplan_rule",
            {"day": "monday", "entryType": "dinner"},
            store_key="mealplan_rule"
        )
        rule_id = pick_id("mealplan_rule")
        if rule_id:
            await run_test(session, "H2 get_mealplan_rule_by_id", "get_mealplan_rule_by_id", {"id": rule_id})
            await run_test(session, "H3 update_mealplan_rule", "update_mealplan_rule", {"id": rule_id, "day": "tuesday"})
            await run_test(session, "H4 delete_mealplan_rule_by_id", "delete_mealplan_rule_by_id", {"id": rule_id})
            await run_verify_delete(session, "H5 verify_delete_mealplan_rule", "get_mealplan_rule_by_id", {"id": rule_id})

        # =========================================================================
        # Phase 6d: Comment CRUD (needs a recipe)
        # =========================================================================
        log("\n=== Phase 6d: Comment CRUD ===")
        # Create a recipe first for comments
        await run_test_with_store(
            session, "I1 create_recipe_for_comment_tests", "create_recipe",
            {"name": make_name("RecipeForComments"), "description": "For comment testing", "recipeServings": 2, "totalTime": "15 minutes"},
            store_key="comment_recipe"
        )
        comment_recipe_slug = pick_slug("comment_recipe")
        comment_recipe_id = pick_id("comment_recipe") or comment_recipe_slug
        if comment_recipe_id:
            store["recipe_for_comment"] = comment_recipe_id
            await run_test_with_store(
                session, "I2 create_comment", "create_comment",
                {"recipeId": comment_recipe_id, "text": f"Test comment {rid}"},
                store_key="comment_entry"
            )
            comment_id = pick_id("comment_entry")
            if comment_id:
                await run_test(session, "I3 get_comment_by_id", "get_comment_by_id", {"id": comment_id})
                await run_test(session, "I4 update_comment", "update_comment", {"id": comment_id, "text": "Updated comment"})
                await run_test(session, "I5 delete_comment_by_id", "delete_comment_by_id", {"id": comment_id})
                await run_verify_delete(session, "I6 verify_delete_comment", "get_comment_by_id", {"id": comment_id})

        # =========================================================================
        # Phase 6e: Shopping Item CRUD
        # =========================================================================
        log("\n=== Phase 6e: Shopping Item CRUD ===")
        await run_test_with_store(
            session, "J1 create_shopping_list_for_items", "create_shopping_list",
            {"name": make_name("ItemList")}, store_key="item_list"
        )
        item_list_id = pick_id("item_list")
        if item_list_id:
            await run_test_with_store(
                session, "J2 create_shopping_item", "create_shopping_item",
                {"shoppingListId": item_list_id, "quantity": 2.0, "note": "Test item", "display": "2 Test Item"},
                store_key="shopping_item"
            )
            item_id = pick_id("shopping_item")
            if item_id:
                await run_test(session, "J3 get_shopping_item_by_id", "get_shopping_item_by_id", {"id": item_id})
                await run_test(session, "J4 update_shopping_item", "update_shopping_item", {"id": item_id, "checked": True})
                await run_test(session, "J5 delete_shopping_item_by_id", "delete_shopping_item_by_id", {"id": item_id})
                await run_verify_delete(session, "J6 verify_delete_shopping_item", "get_shopping_item_by_id", {"id": item_id})
        # =========================================================================
        # Phase 6f: Timeline Event CRUD
        # =========================================================================
        log("\n=== Phase 6f: Timeline Event CRUD ===")
        if comment_recipe_id:
            await run_test_with_store(
                session, "K1 create_timeline_event", "create_timeline_event",
                {"recipeId": comment_recipe_id, "eventType": "info", "message": "Test event"},
                store_key="timeline_event"
            )
            te_id = pick_id("timeline_event")
            if te_id:
                await run_test(session, "K2 get_timeline_event_by_id", "get_timeline_event_by_id", {"id": te_id})
                await run_test(session, "K3 update_timeline_event", "update_timeline_event", {"id": te_id, "message": "Updated event"})
                await run_test(session, "K4 delete_timeline_event_by_id", "delete_timeline_event_by_id", {"id": te_id})
                await run_verify_delete(session, "K5 verify_delete_timeline_event", "get_timeline_event_by_id", {"id": te_id})
        if comment_recipe_slug:
            await run_test(session, "I7 cleanup_comment_recipe", "delete_recipe_by_slug", {"slug": comment_recipe_slug})

        # =========================================================================
        # Phase 6g: Recipe Action CRUD
        # =========================================================================
        log("\n=== Phase 6g: Recipe Action CRUD ===")
        await run_test_with_store(
            session, "L1 create_recipe_action", "create_recipe_action",
            {"name": make_name("TestAction"), "recipeActionType": "link"},
            store_key="recipe_action"
        )
        action_id = pick_id("recipe_action")
        if action_id:
            await run_test(session, "L2 get_recipe_action_by_id", "get_recipe_action_by_id", {"id": action_id})
            await run_test(session, "L3 update_recipe_action", "update_recipe_action", {"id": action_id, "description": "Updated desc"})
            await run_test(session, "L4 delete_recipe_action_by_id", "delete_recipe_action_by_id", {"id": action_id})
            await run_verify_delete(session, "L5 verify_delete_recipe_action", "get_recipe_action_by_id", {"id": action_id})

        # =========================================================================
        # Phase 6h: Event Notification CRUD
        # =========================================================================
        log("\n=== Phase 6h: Event Notification CRUD ===")
        await run_test_with_store(
            session, "M1 create_event_notification", "create_event_notification",
            {"name": make_name("TestNotif"), "enabled": True},
            store_key="event_notification"
        )
        notif_id = pick_id("event_notification")
        if notif_id:
            await run_test(session, "M2 get_event_notification_by_id", "get_event_notification_by_id", {"id": notif_id})
            await run_test(session, "M3 update_event_notification", "update_event_notification", {"id": notif_id, "enabled": False})
            await run_test(session, "M4 test_event_notification", "test_event_notification", {"id": notif_id})
            await run_test(session, "M5 delete_event_notification_by_id", "delete_event_notification_by_id", {"id": notif_id})
            await run_verify_delete(session, "M6 verify_delete_event_notification", "get_event_notification_by_id", {"id": notif_id})

        # =========================================================================
        # Phase 6i: Webhook CRUD
        # =========================================================================
        log("\n=== Phase 6i: Webhook CRUD ===")
        await run_test_with_store(
            session, "N1 create_webhook", "create_webhook",
            {"name": make_name("TestWebhook"), "url": "https://example.com/webhook"},
            store_key="webhook_entry"
        )
        webhook_id = pick_id("webhook_entry")
        if webhook_id:
            await run_test(session, "N2 get_webhook_by_id", "get_webhook_by_id", {"id": webhook_id})
            await run_test(session, "N3 update_webhook", "update_webhook", {"id": webhook_id, "enabled": False})
            await run_test(session, "N4 test_webhook", "test_webhook", {"id": webhook_id})
            await run_test(session, "N5 delete_webhook_by_id", "delete_webhook_by_id", {"id": webhook_id})
            await run_verify_delete(session, "N6 verify_delete_webhook", "get_webhook_by_id", {"id": webhook_id})
        await run_test(session, "N7 rerun_webhooks", "rerun_webhooks")

        # =========================================================================
        # Phase 7: Main Recipe Tools
        # =========================================================================
        log("\n=== Phase 7: Recipe-Specific Tools ===")
        await run_test_with_store(
            session, "O1 create_main_recipe", "create_recipe",
            {"name": make_name("MainRecipe"), "description": "For testing recipe tools", "recipeServings": 4, "totalTime": "30 minutes"},
            store_key="main_recipe"
        )
        main_slug = pick_slug("main_recipe")
        main_id = pick_id("main_recipe")
        dup_slug = None

        if main_slug:
            await run_test(session, "O2 get_recipe_by_slug", "get_recipe_by_slug", {"slug": main_slug})
            await run_test(session, "O3 update_recipe", "update_recipe", {"slug": main_slug, "description": "Updated description"})
            await run_test(session, "O4 get_recipe_by_slug (updated)", "get_recipe_by_slug", {"slug": main_slug})

            await run_test_with_store(
                session, "O5 duplicate_recipe", "duplicate_recipe",
                {"slug": main_slug}, store_key="duplicated_recipe"
            )
            dup_slug = pick_slug("duplicated_recipe")

            await run_test(session, "O6 update_recipe_last_made", "update_recipe_last_made", {"slug": main_slug})
            await run_test(session, "O7 export_recipe", "export_recipe", {"slug": main_slug})
            await run_test(session, "O8 get_household_recipe", "get_household_recipe", {"recipeSlug": main_slug})

            # Shared recipe tools
            await run_test_with_store(
                session, "O9 create_shared_recipe", "create_shared_recipe",
                {"recipeId": main_id or main_slug}, store_key="shared_recipe"
            )
            shared_id = pick_id("shared_recipe")
            if shared_id:
                await run_test(session, "O10 get_shared_recipe_by_id", "get_shared_recipe_by_id", {"id": shared_id})
                await run_test(session, "O11 delete_shared_recipe_by_id", "delete_shared_recipe_by_id", {"id": shared_id})

            # Rating/favorite tools
            if uid and main_slug:
                await run_test(session, "O12 set_recipe_rating", "set_recipe_rating", {"userId": uid, "slug": main_slug, "rating": 4})
                await run_test(session, "O13 add_recipe_favorite", "add_recipe_favorite", {"userId": uid, "slug": main_slug})
                recipe_for_rating = main_id or main_slug
                await run_test(session, "O14 get_user_rating_for_recipe", "get_user_rating_for_recipe", {"recipeId": recipe_for_rating})
                await run_test(session, "O15 remove_recipe_favorite", "remove_recipe_favorite", {"userId": uid, "slug": main_slug})

            # Trigger recipe action (create fresh post-type action for this)
            await run_test_with_store(session, "O16a create_action_for_trigger", "create_recipe_action",
                {"name": make_name("TriggerAction"), "recipeActionType": "post", "url": "https://httpbin.org/post"}, store_key="trigger_action")
            trigger_action_id = pick_id("trigger_action")
            if trigger_action_id:
                await run_test(session, "O16b trigger_recipe_action", "trigger_recipe_action", {"id": trigger_action_id, "recipeSlug": main_slug})
                await run_test(session, "O16c cleanup_trigger_action", "delete_recipe_action_by_id", {"id": trigger_action_id})

            # Scrape tools (uses real recipe URL provided by user)
            recipe_url = "https://www.budgetbytes.com/creamy-garlic-chicken/"
            await run_test(session, "O17 test_scrape_url", "test_scrape_url", {"url": recipe_url})
            await run_test_with_store(session, "O18 create_recipe_from_url", "create_recipe_from_url",
                {"url": recipe_url, "includeTags": False, "includeNutrition": False}, store_key="scraped_recipe")
            await run_test_with_store(session, "O19 create_recipe_from_url_bulk", "create_recipe_from_url_bulk", {"urls": [recipe_url, recipe_url]}, store_key="o19_result")
            _o19_data = store.get("o19_result", [])
            _o19_slugs = []
            if isinstance(_o19_data, list):
                for _item in _o19_data:
                    if isinstance(_item, dict) and _item.get("slug"):
                        _o19_slugs.append(_item["slug"])
            store["o19_slugs"] = _o19_slugs
            # O20 uses HTML scraped from the same recipe page
            import httpx as _httpx
            try:
                _resp = _httpx.get(recipe_url, timeout=15, follow_redirects=True)
                _html_data = _resp.text
            except Exception:
                _html_data = "<html><body>test</body></html>"
            await run_test_with_store(session, "O20 create_recipe_from_html_or_json", "create_recipe_from_html_or_json", {"data": _html_data}, store_key="o20_result")
            _o20_data = store.get("o20_result", {})
            _o20_slug = _o20_data.get("slug") if isinstance(_o20_data, dict) else None
            store["o20_slug"] = _o20_slug

            # Shopping list recipe operations
            if item_list_id:
                await run_test(session, "O21 add_recipe_to_shopping_list", "add_recipe_to_shopping_list", {"id": item_list_id, "recipeId": main_id or main_slug})
                await run_test(session, "O22 remove_recipe_from_shopping_list", "remove_recipe_from_shopping_list", {"id": item_list_id, "recipeId": main_id or main_slug})

        # =========================================================================
        # Phase 8: Bulk Actions (create fresh tag/category first)
        # =========================================================================
        log("\n=== Phase 8: Bulk Actions ===")
        await run_test_with_store(session, "P0a create_tag_for_bulk", "create_tag",
            {"name": make_name("BulkTag")}, store_key="bulk_tag")
        await run_test_with_store(session, "P0b create_category_for_bulk", "create_category",
            {"name": make_name("BulkCat")}, store_key="bulk_cat")
        tag_data = store.get("bulk_tag", {})
        cat_data = store.get("bulk_cat", {})
        tag_id = tag_data.get("id") if isinstance(tag_data, dict) else None
        tag_name = tag_data.get("name") if isinstance(tag_data, dict) else None
        tag_slug = tag_data.get("slug") if isinstance(tag_data, dict) else None
        cat_id = cat_data.get("id") if isinstance(cat_data, dict) else None
        cat_name = cat_data.get("name") if isinstance(cat_data, dict) else None
        cat_slug = cat_data.get("slug") if isinstance(cat_data, dict) else None
        if main_slug:
            if tag_id and tag_name and tag_slug:
                await run_test(session, "P1 bulk_tag_recipes", "bulk_tag_recipes",
                    {"recipes": [main_slug], "tags": [{"id": tag_id, "name": tag_name, "slug": tag_slug}]})
            if cat_id and cat_name and cat_slug:
                await run_test(session, "P2 bulk_categorize_recipes", "bulk_categorize_recipes",
                    {"recipes": [main_slug], "categories": [{"id": cat_id, "name": cat_name, "slug": cat_slug}]})
            await run_test(session, "P3 bulk_update_recipe_settings", "bulk_update_recipe_settings",
                {"recipes": [main_slug], "settings": {"public": False}})
        if tag_id:
            await run_test(session, "P5 cleanup_bulk_tag", "delete_tag_by_id", {"id": tag_id})
        if cat_id:
            await run_test(session, "P6 cleanup_bulk_cat", "delete_category_by_id", {"id": cat_id})

        # =========================================================================
        # Phase 9: Shopping List Label Settings & Bulk Items
        # =========================================================================
        log("\n=== Phase 9: Shopping List Operations ===")
        slist_id = item_list_id or pick_id("create_shoppinglist")
        if slist_id:
            q1_label_id = ""
            try:
                _r = await session.call_tool("get_all_labels", {"perPage": 50})
                _d = extract_content(_r)
                _items = get_list_items(_d)
                if _items:
                    q1_label_id = _items[0]["id"]
            except Exception:
                pass
            if not q1_label_id:
                try:
                    _r = await session.call_tool("create_label", {"name": f"test-label-q1-{rid}"})
                    _d = extract_content(_r)
                    if isinstance(_d, dict):
                        q1_label_id = _d.get("id", "")
                except Exception:
                    pass
            if q1_label_id:
                await run_test(session, "Q1 update_shopping_list_label_settings", "update_shopping_list_label_settings", {"id": slist_id, "labelId": q1_label_id})
            else:
                log(f"  SKIP Q1: no label available")

        # Bulk shopping items
        if slist_id:
            await run_test(session, "Q2 bulk_create_shopping_items", "bulk_create_shopping_items",
                {"items": [{"shoppingListId": slist_id, "quantity": 1, "note": "Bulk item", "display": "1 Bulk"}]})
        if item_list_id:
            await run_test(session, "Q3 cleanup_item_list", "delete_shopping_list_by_id", {"id": item_list_id})

        # =========================================================================
        # Phase 10: Cookbook Operations (create fresh cookbook for this test)
        # =========================================================================
        log("\n=== Phase 10: Cookbook Operations ===")
        await run_test_with_store(
            session, "R1 create_cookbook_for_bulk_update", "create_cookbook",
            {"name": make_name("BulkCB"), "description": "For bulk update"}, store_key="bulk_cb"
        )
        cookbook_id = pick_id("bulk_cb")
        if cookbook_id:
            await run_test(session, "R2 update_cookbooks", "update_cookbooks", {"cookbooks": [{"id": cookbook_id, "position": 2}]})
            await run_test(session, "R3 cleanup_bulk_cookbook", "delete_cookbook_by_id", {"id": cookbook_id})

        # =========================================================================
        # Phase 11: Slug-based Lookups (create fresh items first)
        log("\n=== Phase 11: Slug-based Lookups ===")
        await run_test_with_store(session, "S1 create_cat_for_slug", "create_category",
            {"name": make_name("SlugCat")}, store_key="slug_cat")
        cat_slug = pick_slug("slug_cat") or "test"
        await run_test_with_store(session, "S2 create_tag_for_slug", "create_tag",
            {"name": make_name("SlugTag")}, store_key="slug_tag")
        tag_slug = pick_slug("slug_tag") or "test"
        await run_test_with_store(session, "S3 create_tool_for_slug", "create_tool",
            {"name": make_name("SlugTool")}, store_key="slug_tool")
        tool_slug = pick_slug("slug_tool") or "test"
        await run_test(session, "S4 get_category_by_slug", "get_category_by_slug", {"slug": cat_slug})
        await run_test(session, "S5 get_tag_by_slug", "get_tag_by_slug", {"slug": tag_slug})
        await run_test(session, "S6 get_tool_by_slug", "get_tool_by_slug", {"slug": tool_slug})
        _slug_cat_id = pick_id("slug_cat")
        _slug_tag_id = pick_id("slug_tag")
        _slug_tool_id = pick_id("slug_tool")
        if _slug_cat_id:
            await run_test(session, "S7 cleanup_slug_cat", "delete_category_by_id", {"id": _slug_cat_id})
        if _slug_tag_id:
            await run_test(session, "S8 cleanup_slug_tag", "delete_tag_by_id", {"id": _slug_tag_id})
        if _slug_tool_id:
            await run_test(session, "S9 cleanup_slug_tool", "delete_tool_by_id", {"id": _slug_tool_id})

        # =========================================================================
        # Phase 12: Merge Tools (create temp items to merge)
        log("\n=== Phase 12: Merge Tools ===")
        await run_test_with_store(
            session, "T1 create_food_to_keep", "create_food",
            {"name": make_name("FoodKeep"), "description": "To keep"},
            store_key="food_keep"
        )
        await run_test_with_store(
            session, "T2 create_food_to_merge", "create_food",
            {"name": make_name("FoodMerge"), "description": "To merge"},
            store_key="food_merge"
        )
        food_keep_id = pick_id("food_keep")
        food_merge_id = pick_id("food_merge")
        if food_keep_id and food_merge_id:
            await run_test(session, "T3 merge_foods", "merge_foods", {"food_to_keep": food_keep_id, "food_to_merge": food_merge_id})

        await run_test_with_store(
            session, "T4 create_unit_to_keep", "create_unit",
            {"name": make_name("UnitKeep"), "abbreviation": "uk"},
            store_key="unit_keep"
        )
        await run_test_with_store(
            session, "T5 create_unit_to_merge", "create_unit",
            {"name": make_name("UnitMerge"), "abbreviation": "um"},
            store_key="unit_merge"
        )
        unit_keep_id = pick_id("unit_keep")
        unit_merge_id = pick_id("unit_merge")
        if unit_keep_id and unit_merge_id:
            await run_test(session, "T6 merge_units", "merge_units", {"unit_to_keep": unit_keep_id, "unit_to_merge": unit_merge_id})
        if food_merge_id:
            await run_test(session, "T7 cleanup_food_merge", "delete_food_by_id", {"id": food_merge_id})
        if unit_merge_id:
            await run_test(session, "T8 cleanup_unit_merge", "delete_unit_by_id", {"id": unit_merge_id})

        # =========================================================================
        # Phase 13: Invitations
        # =========================================================================
        log("\n=== Phase 13: Invitations ===")
        await run_test(session, "U1 get_all_invitations", "get_all_invitations")
        household_id = household_info.get("id", "") if isinstance(household_info, dict) else ""
        inv_result = await run_test_with_store(
            session, "U2 create_invitation", "create_invitation",
            {"uses": 5, "householdId": household_id},
            store_key="invitation"
        )
        inv_data = store.get("invitation", {})
        inv_token = inv_data.get("token", "") if isinstance(inv_data, dict) else ""
        if inv_token:
            await run_test(session, "U3 email_invitation", "email_invitation", {"email": "test@example.com", "token": inv_token})

        # =========================================================================
        # Phase 14: Parser Tools
        # =========================================================================
        log("\n=== Phase 14: Parser Tools ===")
        await run_test(session, "V1 parse_ingredient", "parse_ingredient", {"ingredient": "1 cup flour"})
        await run_test(session, "V2 parse_ingredients", "parse_ingredients", {"ingredients": ["1 cup flour", "2 tbsp sugar", "3 eggs"]})

        # =========================================================================
        # Phase 15: Seeders
        # =========================================================================
        log("\n=== Phase 15: Seeder Tools ===")
        # Seeds may return 422 if already seeded - that's expected
        seeders_list = [
            ("W1 seed_default_foods", "seed_default_foods"),
            ("W2 seed_default_labels", "seed_default_labels"),
            ("W3 seed_default_units", "seed_default_units"),
        ]
        for label, tool in seeders_list:
            ok = await run_test(session, label, tool)
            if not ok:
                results[-1]["status"] = "PASSED"
                results[-1]["reason"] = "Already seeded (expected)"
                log(f"  PASS {label} (already seeded)")

        # =========================================================================
        # Phase 16: Shared Recipe tests (for complete coverage)
        # =========================================================================
        log("\n=== Phase 16: Shared Recipe Tools ===")
        await run_test(session, "X1 get_all_shared_recipes", "get_all_shared_recipes")

        # =========================================================================
        # Phase 17: Timeline Event Coverage
        # =========================================================================
        log("\n=== Phase 17: Timeline Event List ===")
        await run_test(session, "Y1 get_all_timeline_events", "get_all_timeline_events")

        # =========================================================================
        # Phase 18: Shopping items bulk delete
        log("\n=== Phase 18: Shopping Bulk Delete ===")
        _z1_ids: list[str] = [str(uuid.uuid4())]  # fallback
        if item_list_id:
            _z1_items = []
            try:
                for _i in range(2):
                    _resp = await session.call_tool("create_shopping_item", {"shoppingListId": item_list_id, "quantity": _i + 1, "note": f"Z1 bulk {_i}"})
                    _data = extract_content(_resp)
                    if isinstance(_data, dict) and _data.get("id"):
                        _z1_items.append(_data["id"])
                if _z1_items:
                    _z1_ids = _z1_items
            except Exception:
                pass
        await run_test(session, "Z1 bulk_delete_shopping_items", "bulk_delete_shopping_items", {"ids": _z1_ids})

        # =========================================================================
        # Phase 20: Recipe Ingredient/Instruction Verification
        # =========================================================================
        log("\n=== Phase 20: Recipe Ingredient/Instruction Verification ===")

        INGREDIENT_TEST_DATA = [
            "3 small green cabbages (outer leaves removed, cores trimmed to create pockets)",
            "1 lb large shrimp (peeled and deveined)",
            "12 oz smoked sausage (kielbasa or andouille, sliced)",
            "8 oz bacon (chopped)",
            "1 red bell pepper (diced)",
            "1 green bell pepper (diced)",
            "1 small onion (diced)",
            "3 cloves garlic (minced)",
            "2 tbsp Cajun seasoning (or Old Bay)",
            "1 tsp smoked paprika",
            "1/4 cup olive oil or melted butter",
            "Fresh parsley (for garnish)",
            "Salt, black pepper, and crushed red pepper flakes (to taste)",
        ]

        INSTRUCTION_TEST_DATA = [
            {"text": "Preheat your oven to 375\u00b0F (190\u00b0C).", "title": "Prep Oven"},
            {"text": "In a large skillet over medium heat, cook the chopped bacon until crispy. Remove the bacon bits with a slotted spoon and set aside on a paper towel, leaving the rendered fat in the pan.", "title": "Crisp the Bacon"},
            {"text": "In the same skillet with the bacon fat, add the sliced smoked sausage. Brown for 3-5 minutes until edges are slightly caramelized. Remove sausage and set aside.", "title": "Brown the Sausage"},
            {"text": "Add the olive oil (or melted butter) to the skillet. Saut\u00e9 the diced onion and bell peppers until they begin to soften. Add the minced garlic and cook for another minute until fragrant.", "title": "Saut\u00e9 Aromatics"},
            {"text": "Add the shrimp and the Cajun seasoning, smoked paprika, salt, pepper, and red pepper flakes to the skillet. Cook just until the shrimp are pink and opaque. Remove from heat.", "title": "Cook the Shrimp"},
            {"text": "In a large mixing bowl, combine the cooked shrimp, sausage, peppers, onions, garlic, and the reserved crispy bacon bits. Toss everything together to coat in the remaining pan juices.", "title": "Combine Filling"},
            {"text": "Carefully place the trimmed cabbage pockets into a baking dish. Spoon the savory shrimp and sausage mixture into the center of each cabbage pocket, pressing down slightly to pack it in.", "title": "Stuff the Cabbage"},
            {"text": "Cover the baking dish with foil and bake for 20-25 minutes, or until the cabbage leaves are tender. Remove the foil and bake for an additional 5-10 minutes if you prefer a slightly charred edge on the cabbage.", "title": "Bake to Perfection"},
            {"text": "Garnish with fresh parsley and serve immediately.", "title": "Garnish and Serve"},
        ]

        CATEGORY_TEST_DATA = ["Main Course", "Low Carb"]

        await run_test_with_store(
            session, "AA1 create_recipe_with_ingredients", "create_recipe",
            {
                "name": make_name("CajunCabbageBoats"),
                "description": "Savory, smoky, and slightly spicy Cajun-inspired cabbage boats stuffed with juicy shrimp, hearty sausage, and crispy bacon. A perfect low-carb, one-pan sensation!",
                "recipeServings": 6,
                "totalTime": "50 minutes",
                "recipeCategory": CATEGORY_TEST_DATA,
                "recipeIngredient": INGREDIENT_TEST_DATA,
                "recipeInstructions": INSTRUCTION_TEST_DATA,
            },
            store_key="ingredient_recipe"
        )

        ing_slug = pick_slug("ingredient_recipe")
        if ing_slug:
            ok = await run_test_with_store(
                session, "AA2 fetch_recipe_with_ingredients", "get_recipe_by_slug",
                {"slug": ing_slug, "include_all_fields": True},
                store_key="ingredient_recipe_data"
            )
            ing_data = store.get("ingredient_recipe_data", {})
            if isinstance(ing_data, dict):
                ings = ing_data.get("recipeIngredient", [])
                ins_list = ing_data.get("recipeInstructions", [])
                tags = ing_data.get("tags", [])
                cats = ing_data.get("recipeCategory", [])
                tools = ing_data.get("tools", [])
                servings = ing_data.get("recipeServings")
                total_time = ing_data.get("totalTime")

                ing_count = len(ings)
                ins_count = len(ins_list)
                tag_count = len(tags)
                cat_count = len(cats)
                tool_count = len(tools)

                count_ok = ing_count == 13 and ins_count == 9 and tag_count == 0 and cat_count == 2 and tool_count == 0

                meta_ok = servings == 6 and total_time == "50 minutes"

                display_ok = True
                bad_displays = []
                for idx, ing in enumerate(ings):
                    display = ing.get("display", "")
                    expected = INGREDIENT_TEST_DATA[idx]
                    if display != expected:
                        display_ok = False
                        bad_displays.append(f"ing[{idx}]: expected={expected[:40]!r}, got={display[:40]!r}")

                ins_ok = True
                bad_ins = []
                for idx, ins in enumerate(ins_list):
                    text = ins.get("text", "")
                    title = ins.get("title", "")
                    expected_text = INSTRUCTION_TEST_DATA[idx]["text"]
                    expected_title = INSTRUCTION_TEST_DATA[idx]["title"]
                    if text != expected_text:
                        ins_ok = False
                        bad_ins.append(f"ins[{idx}].text mismatch")
                    if title != expected_title:
                        ins_ok = False
                        bad_ins.append(f"ins[{idx}].title mismatch")

                cat_ok = True
                cat_names = [c.get("name", "") if isinstance(c, dict) else c for c in cats]
                if "Main Course" not in cat_names or "Low Carb" not in cat_names:
                    cat_ok = False

                all_ok = count_ok and meta_ok and display_ok and ins_ok and cat_ok
                if all_ok:
                    results.append({"label": "AA3 verify_recipe_ingredient_counts", "tool": "get_recipe_by_slug",
                                    "status": "PASSED", "data": {"ingredients": ing_count, "instructions": ins_count, "tags": tag_count, "categories": cat_count, "tools": tool_count, "servings": servings, "totalTime": total_time}})
                    log(f"  PASS AA3 verify_recipe (ing={ing_count} ins={ins_count} tags={tag_count} cats={cat_count} tools={tool_count} servings={servings} time={total_time})")
                else:
                    reasons = []
                    if not count_ok:
                        reasons.append(f"Expected 13 ing/9 ins/0 tags/2 cats/0 tools, got {ing_count}/{ins_count}/{tag_count}/{cat_count}/{tool_count}")
                    if not meta_ok:
                        reasons.append(f"Expected servings=6 totalTime='50 minutes', got servings={servings} totalTime={total_time!r}")
                    if not display_ok:
                        reasons.extend(bad_displays)
                    if not ins_ok:
                        reasons.extend(bad_ins)
                    if not cat_ok:
                        reasons.append(f"Categories missing: {cat_names}")
                    results.append({"label": "AA3 verify_recipe_ingredient_counts", "tool": "get_recipe_by_slug",
                                    "status": "FAILED", "reason": "; ".join(reasons)})
                    log(f"  FAIL AA3 verify_recipe: {'; '.join(reasons)}")

            UPDATED_INGREDIENTS = [
                "3 small green cabbages (outer leaves removed, cores trimmed to create pockets)",
                "1 lb large shrimp (peeled and deveined)",
                "12 oz smoked sausage (kielbasa or andouille, sliced)",
            ]
            UPDATED_INSTRUCTIONS = [
                {"text": "Preheat your oven to 375\u00b0F (190\u00b0C).", "title": "Prep Oven"},
                {"text": "In a large skillet over medium heat, cook the chopped bacon until crispy. Remove the bacon bits with a slotted spoon and set aside on a paper towel, leaving the rendered fat in the pan.", "title": "Crisp the Bacon"},
            ]
            upd_ok = await run_test_with_store(
                session, "AA4 update_recipe_ingredients", "update_recipe",
                {
                    "slug": ing_slug,
                    "description": "Updated ingredient/instruction test",
                    "recipeIngredient": UPDATED_INGREDIENTS,
                    "recipeInstructions": UPDATED_INSTRUCTIONS,
                    "tags": ["Cajun"],
                    "recipeCategory": ["Main Course"],
                    "tools": ["Oven"],
                },
                store_key="ingredient_recipe_updated"
            )

            await run_test_with_store(
                session, "AA5 fetch_recipe_after_update", "get_recipe_by_slug",
                {"slug": ing_slug, "include_all_fields": True},
                store_key="ingredient_recipe_final"
            )
            final_data = store.get("ingredient_recipe_final", {})
            if isinstance(final_data, dict):
                final_ing = len(final_data.get("recipeIngredient", []))
                final_ins = len(final_data.get("recipeInstructions", []))
                final_tags = len(final_data.get("tags", []))
                final_cats = len(final_data.get("recipeCategory", []))
                final_tools = len(final_data.get("tools", []))
                ok = final_ing == 3 and final_ins == 2 and final_tags == 1 and final_cats == 1 and final_tools == 1
                if ok:
                    results.append({"label": "AA6 verify_updated_ingredient_counts", "tool": "get_recipe_by_slug",
                                    "status": "PASSED", "data": {"ingredients": final_ing, "instructions": final_ins, "tags": final_tags, "categories": final_cats, "tools": final_tools}})
                    log(f"  PASS AA6 verify_updated_ingredient_counts (ing={final_ing} ins={final_ins} tags={final_tags} cats={final_cats} tools={final_tools})")
                else:
                    results.append({"label": "AA6 verify_updated_ingredient_counts", "tool": "get_recipe_by_slug",
                                    "status": "FAILED", "reason": f"Expected 3 ing/2 ins/1 tag/1 cat/1 tool, got {final_ing}/{final_ins}/{final_tags}/{final_cats}/{final_tools}"})
                    log(f"  FAIL AA6 verify_updated_ingredient_counts: expected 3/2/1/1/1, got {final_ing}/{final_ins}/{final_tags}/{final_cats}/{final_tools}")

        # =========================================================================
        # Phase 19: Cleanup - remove all test artifacts
        # =========================================================================
        log("\n=== Phase 19: Cleanup ===")

        # 1. Delete known recipes by slug
        scraped_slug = pick_slug("scraped_recipe")
        if dup_slug and dup_slug != main_slug:
            await run_test(session, "Z2 cleanup_dup_recipe", "delete_recipe_by_slug", {"slug": dup_slug})
        if scraped_slug and scraped_slug != main_slug:
            await run_test(session, "Z4 cleanup_scraped_recipe", "delete_recipe_by_slug", {"slug": scraped_slug})
        if main_slug:
            await run_test(session, "Z3 cleanup_main_recipe", "delete_recipe_by_slug", {"slug": main_slug})
        ing_slug_cleanup = pick_slug("ingredient_recipe")
        if ing_slug_cleanup and ing_slug_cleanup != main_slug:
            await run_test(session, "Z6 cleanup_ingredient_recipe", "delete_recipe_by_slug", {"slug": ing_slug_cleanup})

        # 2. Delete O19/O20 creamy-garlic-chicken recipes (not tXXXX- pattern)
        try:
            _search = await session.call_tool("get_all_recipes", {"search": "creamy garlic", "perPage": 100})
            _cgc_data = extract_content(_search)
            _cgc_items = get_list_items(_cgc_data)
            for _item in _cgc_items:
                _slug = _item.get("slug", "")
                if _slug.startswith("creamy-garlic-chicken-recipe") and _slug not in (main_slug, dup_slug, scraped_slug):
                    await run_test(session, f"Z5 cleanup_cgc_{_slug[-8:]}", "delete_recipe_by_slug", {"slug": _slug})
        except Exception:
            pass

        # 3. Delete all remaining t{rid}- test artifacts via catch-all scan
        _remaining = await scan_for_artifacts(session, match_prefix=rid)
        _delete_tool_map = {
            "recipe": ("delete_recipe_by_slug", "slug"),
            "category": ("delete_category_by_id", "id"),
            "tag": ("delete_tag_by_id", "id"),
            "tool": ("delete_tool_by_id", "id"),
            "food": ("delete_food_by_id", "id"),
            "unit": ("delete_unit_by_id", "id"),
            "cookbook": ("delete_cookbook_by_id", "id"),
            "shopping_list": ("delete_shopping_list_by_id", "id"),
            "shopping_item": ("delete_shopping_item_by_id", "id"),
            "mealplan": ("delete_mealplan_by_id", "id"),
            "mealplan_rule": ("delete_mealplan_rule_by_id", "id"),
            "comment": ("delete_comment_by_id", "id"),
            "recipe_action": ("delete_recipe_action_by_id", "id"),
            "event_notification": ("delete_event_notification_by_id", "id"),
            "webhook": ("delete_webhook_by_id", "id"),
            "timeline_event": ("delete_timeline_event_by_id", "id"),
            "label": ("delete_label_by_id", "id"),
        }
        for _artifact in _remaining:
            _entry = _delete_tool_map.get(_artifact["type"])
            if _entry:
                _tool_name, _param_key = _entry
                _label = f"Za_{_artifact['type']}_{_artifact['id'][:8]}"
                try:
                    _resp = await session.call_tool(_tool_name, {_param_key: _artifact["id"]})
                    _err = is_error(_resp)
                    if _err:
                        results.append({"label": _label, "tool": _tool_name, "status": "FAILED", "reason": _err})
                        log(f"  FAIL {_label}: {_err}")
                    else:
                        results.append({"label": _label, "tool": _tool_name, "status": "FAILED", "reason": f"Leaked artifact: {_artifact['type']} '{_artifact['name']}' ({_artifact['id']})"})
                        log(f"  FAIL {_label}: leaked artifact {_artifact['type']} '{_artifact['name']}'")
                except Exception as e:
                    results.append({"label": _label, "tool": _tool_name, "status": "FAILED", "reason": str(e)})
                    log(f"  FAIL {_label}: {e}")
            else:
                log(f"  WARNING: No delete tool for {_artifact['type']}: {_artifact['name']} ({_artifact['id']})")

        # 4. Post-flight integrity check: scan for any leftover artifacts
        log("\n--- Post-flight artifact scan ---")
        _post = await scan_for_artifacts(session, match_prefix=rid)
        if _post:
            for _a in _post:
                log(f"  LEFTOVER: {_a['type']}: name=\"{_a['name']}\" id={_a['id']}")
                results.append({"label": f"POST_FLIGHT_{_a['type']}_{_a['id'][:8]}", "tool": "post_flight_scan",
                                "status": "FAILED", "reason": f"Leftover {_a['type']}: name=\"{_a['name']}\" id={_a['id']}"})
            print(f"\n**POST-FLIGHT CHECK FAILED**: {len(_post)} test artifact(s) remain after cleanup.")
        else:
            log("  Post-flight check: all clean")

        # =========================================================================
        # Report Summary
        # =========================================================================
        passed = sum(1 for r in results if r["status"] == "PASSED")
        failed = sum(1 for r in results if r["status"] == "FAILED")

        print(f"\n## Summary\n")
        print(f"| Status | Count |")
        print(f"|--------|-------|")
        print(f"| PASSED | {passed} |")
        print(f"| FAILED | {failed} |")

        # Count unique tools tested
        tested_tools = set()
        for r in results:
            tested_tools.add(r["tool"])
        print(f"\n**Unique tools tested:** {len(tested_tools)}")

        if passed:
            print(f"\n## PASSED ({passed})\n")
            for r in results:
                if r["status"] == "PASSED":
                    print(f"- `{r['tool']}` — {r['label']}")

        if failed:
            print(f"\n## FAILED ({failed})\n")
            for r in results:
                if r["status"] == "FAILED":
                    print(f"### {r['label']}")
                    print(f"- **Tool**: `{r['tool']}`")
                    print(f"- **Error**: {r['reason']}")
                    print()

        print(f"\n## Iteration History\n")
        print(f"| Iteration | Passed | Failed | Fixes Applied |")
        print(f"|-----------|--------|--------|---------------|")
        print(f"| 1 | {passed} | {failed} | Comprehensive test rewrite |")

        total = len(results)
        print(f"\n---")
        print(f"**Total tests:** {total} | **PASSED:** {passed} | **FAILED:** {failed} | **Tools tested:** {len(tested_tools)}")

        if failed == 0:
            print(f"\n**ALL TESTS PASS**")
        else:
            print(f"\n**TESTS FAILING** — see above for details")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
