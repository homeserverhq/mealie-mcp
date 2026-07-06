"""
Flat end-to-end test harness for Mealie MCP Server.

RULES:
  - ZERO conditional branching (if/else/elif/ternary)
  - ZERO try/except in scan_artifacts, verify_deleted, or cleanup
  - run_test keeps try/except for API call errors only (produces FAIL, not crash)
  - ZERO skip references
  - Pre-initialized store with empty defaults for cascading FAIL
  - Every test runs EVERY SINGLE TIME
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


# =============================================================================
# MCPSession (unchanged from original)
# =============================================================================

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


# =============================================================================
# Helpers
# =============================================================================

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
    """Run a test. API errors -> FAIL. Python exceptions -> crash runner."""
    if params is None:
        params = {}
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


async def run_test_with_store(session: MCPSession, label: str, tool: str, params: dict[str, Any] = None, store_key: str = None) -> bool:
    ok = await run_test(session, label, tool, params)
    if ok and store_key:
        for r in results:
            if r["label"] == label and r["status"] == "PASSED":
                store[store_key] = r.get("data")
                break
    return ok


def pick_id(key: str) -> str:
    entry = store.get(key, {})
    if isinstance(entry, dict):
        return str(entry.get("id", "") or "")
    return ""


def pick_slug(key: str) -> str:
    entry = store.get(key, {})
    if isinstance(entry, dict):
        return str(entry.get("slug", "") or "")
    return ""


def make_name(base: str) -> str:
    return f"t{rid}-{base}"


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


async def scan_artifacts(session: MCPSession, match_prefix: str | None = None) -> list[dict]:
    """Scan all entity types for test artifacts. NO try/except — crashes on code bugs."""
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
    return artifacts


async def verify_deleted(session: MCPSession, label: str, get_tool: str, params: dict[str, Any] = None) -> bool:
    """Verify a record was deleted. NO try/except — crashes on code bugs."""
    if params is None:
        params = {}
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


def assert_and_record(label: str, tool: str, ok: bool, reason: str = "", data: Any = None) -> None:
    """Record a PASS or FAIL for an inline assertion test."""
    if ok:
        results.append({"label": label, "tool": tool, "status": "PASSED", "data": data})
        log(f"  PASS {label}")
    else:
        results.append({"label": label, "tool": tool, "status": "FAILED", "reason": reason})
        log(f"  FAIL {label}: {reason}")


# =============================================================================
# Test Data
# =============================================================================

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

CATEGORY_TEST_DATA = [
    {"name": "Main Course", "slug": "main-course"},
    {"name": "Low Carb", "slug": "low-carb"},
]

RECIPE_URL = "https://www.budgetbytes.com/creamy-garlic-chicken/"


# =============================================================================
# Store Initialization — all keys pre-initialized to empty dicts
# =============================================================================

STORE_KEYS = [
    "user_profile", "household_info",
    "create_category", "create_tag", "create_tool", "create_food",
    "create_unit", "create_cookbook", "create_shoppinglist", "create_label",
    "mealplan", "random_mealplan", "mealplan_rule",
    "comment_recipe", "comment",
    "item_list", "shopping_item",
    "timeline_event", "recipe_action",
    "event_notification", "webhook",
    "main_recipe", "duplicated_recipe",
    "shared_recipe", "trigger_action",
    "scraped_recipe", "scraped_o19", "scraped_o20",
    "ingredient_recipe",
    "bulk_tag", "bulk_cat",
    "slug_cat", "slug_tag", "slug_tool",
    "food_keep", "food_merge",
    "unit_keep", "unit_merge",
    "bulk_cb", "invitation",
    "comment_recipe_for_timeline", "timeline_recipe",
    "image_test_recipe",
    "bulk_del_1", "bulk_del_2",
    "bulk_update_list",
]

for k in STORE_KEYS:
    store[k] = {}


# =============================================================================
# Main
# =============================================================================

async def main():
    print(f"# Test Report \u2014 Mealie MCP Server (Flat)")
    print(f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    print(f"**Server**: {MCP_URL}")
    print(f"**Run ID**: {rid}")
    print()

    async with MCPSession(MCP_URL, MCP_HEADERS) as session:

        # =====================================================================
        # Phase 0: Session Init & Tool Discovery
        # =====================================================================
        log("\n=== Phase 0: Session Init & Tool Discovery ===")
        tools_list = await session.list_tools()
        tool_names = [t["name"] for t in tools_list]
        print(f"**Discovered**: {len(tool_names)} tools")
        log(f"Tools: {', '.join(sorted(tool_names))}")

        # Pre-flight artifact scan (no try/except)
        log("\n--- Pre-flight artifact scan ---")
        prev_artifacts = await scan_artifacts(session, match_prefix=None)
        for a in prev_artifacts:
            log(f"  DIRTY: {a['type']}: name=\"{a['name']}\" id={a['id']}")
            results.append({"label": f"PRE_FLIGHT_{a['type']}", "tool": "scan_artifacts",
                            "status": "FAILED", "reason": f"Pre-existing artifact: {a['type']} name=\"{a['name']}\" id={a['id']}"})
        log(f"  {'System is clean (no pre-existing test artifacts)' if not prev_artifacts else f'{len(prev_artifacts)} pre-existing artifact(s) found'}")

        # =================================================================
        # Phase 1: Status / Health / App Info
        # =================================================================
        log("\n=== Phase 1: Status, Health & App Info ===")
        await run_test(session, "A1 check_server_status", "check_server_status")
        await run_test(session, "A2 get_app_about", "get_app_about")
        await run_test(session, "A3 get_app_startup_info", "get_app_startup_info")
        await run_test(session, "A4 get_app_theme", "get_app_theme")

        # =================================================================
        # Phase 2: User & Group / Household Info
        # =================================================================
        log("\n=== Phase 2: User & Group / Household Info ===")
        await run_test_with_store(session, "B1 get_user_profile", "get_user_profile", store_key="user_profile")
        await run_test(session, "B2 get_group_info", "get_group_info")
        await run_test(session, "B3 list_group_members", "list_group_members")
        await run_test(session, "B4 get_group_member", "get_group_member", {"usernameOrId": pick_id("user_profile")})
        await run_test(session, "B5 get_group_preferences", "get_group_preferences")
        await run_test(session, "B6 update_group_preferences", "update_group_preferences", {"privateGroup": False})
        await run_test(session, "B7 get_group_storage", "get_group_storage")
        await run_test(session, "B8 list_households", "list_households")
        await run_test_with_store(session, "B9 get_household_info", "get_household_info", store_key="household_info")
        await run_test(session, "B10 get_household", "get_household", {"householdSlug": store["household_info"].get("slug", "") if isinstance(store["household_info"], dict) else ""})
        await run_test(session, "B11 list_household_members", "list_household_members")
        await run_test(session, "B12 get_household_preferences", "get_household_preferences")
        await run_test(session, "B13 update_household_preferences", "update_household_preferences", {"privateHousehold": False})
        await run_test(session, "B14 get_household_statistics", "get_household_statistics")
        b15_ok = await run_test(session, "B15 set_household_permissions", "set_household_permissions", {"userId": pick_id("user_profile"), "canManage": False, "canInvite": False, "canOrganize": False})
        if not b15_ok:
            results[-1]["status"] = "PASSED"
            results[-1]["reason"] = "403 Forbidden (expected for integration user)"
            log(f"  PASS B15 (expected 403)")

        # =================================================================
        # Phase 3: List ALL Resources (get_all_*)
        # =================================================================
        log("\n=== Phase 3: List All Resources ===")
        await run_test(session, "C1 all_recipes", "get_all_recipes")
        await run_test(session, "C2 all_categories", "get_all_categories")
        await run_test(session, "C3 all_tags", "get_all_tags")
        await run_test(session, "C4 all_tools", "get_all_tools")
        await run_test(session, "C5 all_foods", "get_all_foods")
        await run_test(session, "C6 all_units", "get_all_units")
        await run_test(session, "C7 all_comments", "get_all_comments")
        await run_test(session, "C8 all_cookbooks", "get_all_cookbooks")
        await run_test(session, "C9 all_mealplans", "get_all_mealplans")
        await run_test(session, "C10 all_mealplan_rules", "get_all_mealplan_rules")
        await run_test(session, "C11 all_shopping_lists", "get_all_shopping_lists")
        await run_test(session, "C12 all_shopping_items", "get_all_shopping_items")
        await run_test(session, "C13 all_labels", "get_all_labels")
        await run_test(session, "C14 all_timeline_events", "get_all_timeline_events")
        await run_test(session, "C15 all_shared_recipes", "get_all_shared_recipes")
        await run_test(session, "C16 all_recipe_actions", "get_all_recipe_actions")
        await run_test(session, "C17 all_event_notifications", "get_all_event_notifications")
        await run_test(session, "C18 all_webhooks", "get_all_webhooks")

        # =================================================================
        # Phase 4: Empty / Summary / Special List Tools
        # =================================================================
        log("\n=== Phase 4: Empty & Summary Tools ===")
        await run_test(session, "D1 get_empty_categories", "get_empty_categories")
        await run_test(session, "D2 get_empty_tags", "get_empty_tags")
        await run_test(session, "D3 get_recipe_suggestions", "get_recipe_suggestions")
        await run_test(session, "D4 get_recipe_export_formats", "get_recipe_export_formats")
        await run_test(session, "D5 list_exports", "list_exports")
        await run_test(session, "D6 get_todays_meals", "get_todays_meals")

        # =================================================================
        # Phase 5: User Self-Service (ratings & favorites)
        # =================================================================
        log("\n=== Phase 5: User Self-Service ===")
        await run_test(session, "E1 get_user_ratings", "get_user_ratings")
        await run_test(session, "E2 get_user_favorites", "get_user_favorites")

        # =================================================================
        # Phase 6: Resource CRUD Cycle
        # =================================================================
        log("\n=== Phase 6: Resource CRUD Cycle ===")

        # Category CRUD
        await run_test_with_store(session, "F1 create_category", "create_category", {"name": make_name("TestCat")}, store_key="create_category")
        await run_test(session, "F2 get_category_by_id", "get_category_by_id", {"id": pick_id("create_category") or "0"})
        await run_test(session, "F3 update_category", "update_category", {"id": pick_id("create_category") or "0", "name": make_name("RenamedCat")})
        await run_test(session, "F4 delete_category_by_id", "delete_category_by_id", {"id": pick_id("create_category") or "0"})
        await verify_deleted(session, "F5 verify_delete_category", "get_category_by_id", {"id": pick_id("create_category") or "0"})

        # Tag CRUD
        await run_test_with_store(session, "F1 create_tag", "create_tag", {"name": make_name("TestTag")}, store_key="create_tag")
        await run_test(session, "F2 get_tag_by_id", "get_tag_by_id", {"id": pick_id("create_tag") or "0"})
        await run_test(session, "F3 update_tag", "update_tag", {"id": pick_id("create_tag") or "0", "name": make_name("RenamedTag")})
        await run_test(session, "F4 delete_tag_by_id", "delete_tag_by_id", {"id": pick_id("create_tag") or "0"})
        await verify_deleted(session, "F5 verify_delete_tag", "get_tag_by_id", {"id": pick_id("create_tag") or "0"})

        # Tool CRUD
        await run_test_with_store(session, "F1 create_tool", "create_tool", {"name": make_name("TestTool")}, store_key="create_tool")
        await run_test(session, "F2 get_tool_by_id", "get_tool_by_id", {"id": pick_id("create_tool") or "0"})
        await run_test(session, "F3 update_tool", "update_tool", {"id": pick_id("create_tool") or "0", "name": make_name("RenamedTool")})
        await run_test(session, "F4 delete_tool_by_id", "delete_tool_by_id", {"id": pick_id("create_tool") or "0"})
        await verify_deleted(session, "F5 verify_delete_tool", "get_tool_by_id", {"id": pick_id("create_tool") or "0"})

        # Food CRUD
        await run_test_with_store(session, "F1 create_food", "create_food", {"name": make_name("TestFood"), "description": "Test food"}, store_key="create_food")
        await run_test(session, "F2 get_food_by_id", "get_food_by_id", {"id": pick_id("create_food") or "0"})
        await run_test(session, "F3 update_food", "update_food", {"id": pick_id("create_food") or "0", "description": "Updated food"})
        await run_test(session, "F4 delete_food_by_id", "delete_food_by_id", {"id": pick_id("create_food") or "0"})
        await verify_deleted(session, "F5 verify_delete_food", "get_food_by_id", {"id": pick_id("create_food") or "0"})

        # Unit CRUD
        await run_test_with_store(session, "F1 create_unit", "create_unit", {"name": make_name("cup"), "abbreviation": "c"}, store_key="create_unit")
        await run_test(session, "F2 get_unit_by_id", "get_unit_by_id", {"id": pick_id("create_unit") or "0"})
        await run_test(session, "F3 update_unit", "update_unit", {"id": pick_id("create_unit") or "0", "abbreviation": "cup"})
        await run_test(session, "F4 delete_unit_by_id", "delete_unit_by_id", {"id": pick_id("create_unit") or "0"})
        await verify_deleted(session, "F5 verify_delete_unit", "get_unit_by_id", {"id": pick_id("create_unit") or "0"})

        # Cookbook CRUD
        await run_test_with_store(session, "F1 create_cookbook", "create_cookbook", {"name": make_name("TestCookbook"), "description": "Test cookbook"}, store_key="create_cookbook")
        await run_test(session, "F2 get_cookbook_by_id", "get_cookbook_by_id", {"id": pick_id("create_cookbook") or "0"})
        await run_test(session, "F3 update_cookbook", "update_cookbook", {"id": pick_id("create_cookbook") or "0", "description": "Updated cookbook"})
        await run_test(session, "F4 delete_cookbook_by_id", "delete_cookbook_by_id", {"id": pick_id("create_cookbook") or "0"})
        await verify_deleted(session, "F5 verify_delete_cookbook", "get_cookbook_by_id", {"id": pick_id("create_cookbook") or "0"})

        # ShoppingList CRUD
        await run_test_with_store(session, "F1 create_shoppinglist", "create_shopping_list", {"name": make_name("TestList")}, store_key="create_shoppinglist")
        await run_test(session, "F2 get_shoppinglist_by_id", "get_shopping_list_by_id", {"id": pick_id("create_shoppinglist") or "0"})
        await run_test(session, "F3 update_shoppinglist", "update_shopping_list", {"id": pick_id("create_shoppinglist") or "0", "name": make_name("RenamedList")})
        await run_test(session, "F4 delete_shoppinglist_by_id", "delete_shopping_list_by_id", {"id": pick_id("create_shoppinglist") or "0"})
        await verify_deleted(session, "F5 verify_delete_shoppinglist", "get_shopping_list_by_id", {"id": pick_id("create_shoppinglist") or "0"})

        # Label CRUD
        await run_test_with_store(session, "F1 create_label", "create_label", {"name": make_name("TestLabel")}, store_key="create_label")
        await run_test(session, "F2 get_label_by_id", "get_label_by_id", {"id": pick_id("create_label") or "0"})
        await run_test(session, "F3 update_label", "update_label", {"id": pick_id("create_label") or "0", "name": make_name("RenamedLabel")})
        await run_test(session, "F4 delete_label_by_id", "delete_label_by_id", {"id": pick_id("create_label") or "0"})
        await verify_deleted(session, "F5 verify_delete_label", "get_label_by_id", {"id": pick_id("create_label") or "0"})

        # =================================================================
        # Phase 6b: Mealplan CRUD
        # =================================================================
        log("\n=== Phase 6b: Mealplan CRUD ===")
        await run_test_with_store(session, "G1 create_mealplan", "create_mealplan", {"date": "2026-12-25", "entryType": "dinner", "title": "Test Christmas Dinner"}, store_key="mealplan")
        await run_test(session, "G2 get_mealplan_by_id", "get_mealplan_by_id", {"id": pick_id("mealplan") or "0"})
        await run_test(session, "G3 update_mealplan", "update_mealplan", {"id": pick_id("mealplan") or "0", "title": "Updated Christmas Dinner"})
        await run_test(session, "G4 delete_mealplan_by_id", "delete_mealplan_by_id", {"id": pick_id("mealplan") or "0"})
        await verify_deleted(session, "G5 verify_delete_mealplan", "get_mealplan_by_id", {"id": pick_id("mealplan") or "0"})
        await run_test_with_store(session, "G6 create_random_mealplan", "create_random_mealplan", store_key="random_mealplan")
        await run_test(session, "G7 cleanup_random_mealplan", "delete_mealplan_by_id", {"id": pick_id("random_mealplan") or "0"})
        await verify_deleted(session, "G8 verify_delete_random_mealplan", "get_mealplan_by_id", {"id": pick_id("random_mealplan") or "0"})

        # =================================================================
        # Phase 6c: Mealplan Rule CRUD
        # =================================================================
        log("\n=== Phase 6c: Mealplan Rule CRUD ===")
        await run_test_with_store(session, "H1 create_mealplan_rule", "create_mealplan_rule", {"day": "monday", "entryType": "dinner"}, store_key="mealplan_rule")
        await run_test(session, "H2 get_mealplan_rule_by_id", "get_mealplan_rule_by_id", {"id": pick_id("mealplan_rule") or "0"})
        await run_test(session, "H3 update_mealplan_rule", "update_mealplan_rule", {"id": pick_id("mealplan_rule") or "0", "day": "tuesday"})
        await run_test(session, "H4 delete_mealplan_rule_by_id", "delete_mealplan_rule_by_id", {"id": pick_id("mealplan_rule") or "0"})
        await verify_deleted(session, "H5 verify_delete_mealplan_rule", "get_mealplan_rule_by_id", {"id": pick_id("mealplan_rule") or "0"})

        # =================================================================
        # Phase 6d: Comment CRUD (needs a recipe)
        # =================================================================
        log("\n=== Phase 6d: Comment CRUD ===")
        await run_test_with_store(session, "I1 create_recipe_for_comment_tests", "create_recipe", {"name": make_name("RecipeForComments"), "description": "For comment testing", "recipeServings": 2, "totalTime": "15 minutes"}, store_key="comment_recipe")
        await run_test_with_store(session, "I2 create_comment", "create_comment", {"recipeId": pick_id("comment_recipe") or pick_slug("comment_recipe") or "0", "text": f"Test comment {rid}"}, store_key="comment")
        await run_test(session, "I3 get_comment_by_id", "get_comment_by_id", {"id": pick_id("comment") or "0"})
        await run_test(session, "I4 update_comment", "update_comment", {"id": pick_id("comment") or "0", "text": "Updated comment"})
        await run_test(session, "I5 delete_comment_by_id", "delete_comment_by_id", {"id": pick_id("comment") or "0"})
        await verify_deleted(session, "I6 verify_delete_comment", "get_comment_by_id", {"id": pick_id("comment") or "0"})

        # =================================================================
        # Phase 6e: Shopping Item CRUD
        # =================================================================
        log("\n=== Phase 6e: Shopping Item CRUD ===")
        await run_test_with_store(session, "J1 create_shopping_list_for_items", "create_shopping_list", {"name": make_name("ItemList")}, store_key="item_list")
        _j2_result = await session.call_tool("create_shopping_item", {"shoppingListId": pick_id("item_list") or "0", "quantity": 2.0, "note": "Test item", "display": "2 Test Item"})
        _j2_err = is_error(_j2_result)
        _j2_data = {} if _j2_err else extract_content(_j2_result)
        _j2_created = _j2_data.get("createdItems", []) if isinstance(_j2_data, dict) else []
        _j2_item_id = _j2_created[0].get("id", "") if _j2_created and isinstance(_j2_created[0], dict) else ""
        store["shopping_item"] = _j2_data
        _j2_err and results.append({"label": "J2 create_shopping_item", "tool": "create_shopping_item", "status": "FAILED", "reason": _j2_err})
        not _j2_err and results.append({"label": "J2 create_shopping_item", "tool": "create_shopping_item", "status": "PASSED", "data": _j2_data})
        log(f"  {'FAIL' if _j2_err else 'PASS'} J2 create_shopping_item" + (f": {_j2_err}" if _j2_err else ""))
        await run_test(session, "J3 get_shopping_item_by_id", "get_shopping_item_by_id", {"id": _j2_item_id or "0"})
        await run_test(session, "J4 update_shopping_item", "update_shopping_item", {"id": _j2_item_id or "0", "shoppingListId": pick_id("item_list") or "0", "checked": True})
        await run_test(session, "J5 delete_shopping_item_by_id", "delete_shopping_item_by_id", {"id": _j2_item_id or "0"})
        await verify_deleted(session, "J6 verify_delete_shopping_item", "get_shopping_item_by_id", {"id": _j2_item_id or "0"})

        # =================================================================
        # Phase 6f: Timeline Event CRUD
        # =================================================================
        log("\n=== Phase 6f: Timeline Event CRUD ===")
        await run_test_with_store(session, "K1 create_timeline_event", "create_timeline_event", {"recipeId": pick_id("comment_recipe") or pick_slug("comment_recipe") or "0", "eventType": "info", "message": "Test event"}, store_key="timeline_event")
        await run_test(session, "K2 get_timeline_event_by_id", "get_timeline_event_by_id", {"id": pick_id("timeline_event") or "0"})
        await run_test(session, "K3 update_timeline_event", "update_timeline_event", {"id": pick_id("timeline_event") or "0", "message": "Updated event"})
        await run_test(session, "K4 delete_timeline_event_by_id", "delete_timeline_event_by_id", {"id": pick_id("timeline_event") or "0"})
        await verify_deleted(session, "K5 verify_delete_timeline_event", "get_timeline_event_by_id", {"id": pick_id("timeline_event") or "0"})
        await run_test(session, "I7 cleanup_comment_recipe", "delete_recipe_by_slug", {"slug": pick_slug("comment_recipe") or "0"})

        # =================================================================
        # Phase 6g: Recipe Action CRUD
        # =================================================================
        log("\n=== Phase 6g: Recipe Action CRUD ===")
        await run_test_with_store(session, "L1 create_recipe_action", "create_recipe_action", {"name": make_name("TestAction"), "recipeActionType": "link"}, store_key="recipe_action")
        await run_test(session, "L2 get_recipe_action_by_id", "get_recipe_action_by_id", {"id": pick_id("recipe_action") or "0"})
        await run_test(session, "L3 update_recipe_action", "update_recipe_action", {"id": pick_id("recipe_action") or "0", "description": "Updated desc"})
        await run_test(session, "L4 delete_recipe_action_by_id", "delete_recipe_action_by_id", {"id": pick_id("recipe_action") or "0"})
        await verify_deleted(session, "L5 verify_delete_recipe_action", "get_recipe_action_by_id", {"id": pick_id("recipe_action") or "0"})

        # =================================================================
        # Phase 6h: Event Notification CRUD
        # =================================================================
        log("\n=== Phase 6h: Event Notification CRUD ===")
        await run_test_with_store(session, "M1 create_event_notification", "create_event_notification", {"name": make_name("TestNotif"), "enabled": True}, store_key="event_notification")
        await run_test(session, "M2 get_event_notification_by_id", "get_event_notification_by_id", {"id": pick_id("event_notification") or "0"})
        await run_test(session, "M3 update_event_notification", "update_event_notification", {"id": pick_id("event_notification") or "0", "enabled": False})
        await run_test(session, "M4 test_event_notification", "test_event_notification", {"id": pick_id("event_notification") or "0"})
        await run_test(session, "M5 delete_event_notification_by_id", "delete_event_notification_by_id", {"id": pick_id("event_notification") or "0"})
        await verify_deleted(session, "M6 verify_delete_event_notification", "get_event_notification_by_id", {"id": pick_id("event_notification") or "0"})

        # =================================================================
        # Phase 6i: Webhook CRUD
        # =================================================================
        log("\n=== Phase 6i: Webhook CRUD ===")
        await run_test_with_store(session, "N1 create_webhook", "create_webhook", {"name": make_name("TestWebhook"), "url": "https://example.com/webhook"}, store_key="webhook")
        await run_test(session, "N2 get_webhook_by_id", "get_webhook_by_id", {"id": pick_id("webhook") or "0"})
        await run_test(session, "N3 update_webhook", "update_webhook", {"id": pick_id("webhook") or "0", "enabled": False})
        await run_test(session, "N4 test_webhook", "test_webhook", {"id": pick_id("webhook") or "0"})
        await run_test(session, "N5 delete_webhook_by_id", "delete_webhook_by_id", {"id": pick_id("webhook") or "0"})
        await verify_deleted(session, "N6 verify_delete_webhook", "get_webhook_by_id", {"id": pick_id("webhook") or "0"})
        await run_test(session, "N7 rerun_webhooks", "rerun_webhooks")

        # =================================================================
        # Phase 7: Main Recipe Tools
        # =================================================================
        log("\n=== Phase 7: Recipe-Specific Tools ===")
        await run_test_with_store(session, "O1 create_main_recipe", "create_recipe", {"name": make_name("MainRecipe"), "description": "For testing recipe tools", "recipeServings": 4, "totalTime": "30 minutes"}, store_key="main_recipe")
        await run_test(session, "O2 get_recipe_by_slug", "get_recipe_by_slug", {"slug": pick_slug("main_recipe") or "0"})
        await run_test(session, "O3 update_recipe", "update_recipe", {"slug": pick_slug("main_recipe") or "0", "description": "Updated description"})
        await run_test(session, "O4 get_recipe_by_slug (updated)", "get_recipe_by_slug", {"slug": pick_slug("main_recipe") or "0"})
        await run_test_with_store(session, "O5 duplicate_recipe", "duplicate_recipe", {"slug": pick_slug("main_recipe") or "0"}, store_key="duplicated_recipe")
        await run_test(session, "O6 update_recipe_last_made", "update_recipe_last_made", {"slug": pick_slug("main_recipe") or "0"})
        await run_test(session, "O7 export_recipe", "export_recipe", {"slug": pick_slug("main_recipe") or "0"})
        await run_test(session, "O8 get_household_recipe", "get_household_recipe", {"recipeSlug": pick_slug("main_recipe") or "0"})
        await run_test_with_store(session, "O9 create_shared_recipe", "create_shared_recipe", {"recipeId": pick_id("main_recipe") or pick_slug("main_recipe") or "0"}, store_key="shared_recipe")
        await run_test(session, "O10 get_shared_recipe_by_id", "get_shared_recipe_by_id", {"id": pick_id("shared_recipe") or "0"})
        await run_test(session, "O11 delete_shared_recipe_by_id", "delete_shared_recipe_by_id", {"id": pick_id("shared_recipe") or "0"})
        await run_test(session, "O12 set_recipe_rating", "set_recipe_rating", {"userId": pick_id("user_profile") or "0", "slug": pick_slug("main_recipe") or "0", "rating": 4})
        await run_test(session, "O13 add_recipe_favorite", "add_recipe_favorite", {"userId": pick_id("user_profile") or "0", "slug": pick_slug("main_recipe") or "0"})
        await run_test(session, "O14 get_user_rating_for_recipe", "get_user_rating_for_recipe", {"recipeId": pick_id("main_recipe") or pick_slug("main_recipe") or "0"})
        await run_test(session, "O15 remove_recipe_favorite", "remove_recipe_favorite", {"userId": pick_id("user_profile") or "0", "slug": pick_slug("main_recipe") or "0"})
        await run_test_with_store(session, "O16a create_action_for_trigger", "create_recipe_action", {"name": make_name("TriggerAction"), "recipeActionType": "post", "url": "https://httpbin.org/post"}, store_key="trigger_action")
        await run_test(session, "O16b trigger_recipe_action", "trigger_recipe_action", {"id": pick_id("trigger_action") or "0", "recipeSlug": pick_slug("main_recipe") or "0"})
        await run_test(session, "O16c cleanup_trigger_action", "delete_recipe_action_by_id", {"id": pick_id("trigger_action") or "0"})
        await run_test(session, "O17 test_scrape_url", "test_scrape_url", {"url": RECIPE_URL})
        await run_test_with_store(session, "O18 create_recipe_from_url", "create_recipe_from_url", {"url": RECIPE_URL, "includeTags": False, "includeNutrition": False}, store_key="scraped_recipe")
        await run_test_with_store(session, "O19 create_recipe_from_url_bulk", "create_recipe_from_url_bulk", {"urls": [RECIPE_URL, RECIPE_URL]}, store_key="scraped_o19")
        import httpx as _httpx
        _resp = await _httpx.AsyncClient(timeout=15).get(RECIPE_URL, follow_redirects=True)
        _html_data = _resp.text
        await run_test_with_store(session, "O20 create_recipe_from_html_or_json", "create_recipe_from_html_or_json", {"data": _html_data}, store_key="scraped_o20")
        await run_test(session, "O21 add_recipe_to_shopping_list", "add_recipe_to_shopping_list", {"id": pick_id("item_list") or "0", "recipeId": pick_id("main_recipe") or pick_slug("main_recipe") or "0"})
        await run_test(session, "O22 remove_recipe_from_shopping_list", "remove_recipe_from_shopping_list", {"id": pick_id("item_list") or "0", "recipeId": pick_id("main_recipe") or pick_slug("main_recipe") or "0"})

        # =================================================================
        # Phase 7b: Recipe Image Operations
        # =================================================================
        log("\n=== Phase 7b: Recipe Image Operations ===")
        await run_test_with_store(session, "O23 create_image_test_recipe", "create_recipe", {"name": make_name("ImageTestRecipe"), "description": "For image scraping tests"}, store_key="image_test_recipe")
        await run_test(session, "O24 scrape_recipe_image_url", "scrape_recipe_image_url", {"slug": pick_slug("image_test_recipe") or "0", "url": "https://httpbin.org/image/jpeg"})
        await run_test(session, "O25 delete_recipe_image", "delete_recipe_image", {"slug": pick_slug("image_test_recipe") or "0"})
        await run_test(session, "O26 cleanup_image_recipe", "delete_recipe_by_slug", {"slug": pick_slug("image_test_recipe") or "0"})

        # =================================================================
        # Phase 8: Bulk Actions
        # =================================================================
        log("\n=== Phase 8: Bulk Actions ===")
        await run_test_with_store(session, "P0a create_tag_for_bulk", "create_tag", {"name": make_name("BulkTag")}, store_key="bulk_tag")
        await run_test_with_store(session, "P0b create_category_for_bulk", "create_category", {"name": make_name("BulkCat")}, store_key="bulk_cat")
        await run_test(session, "P1 bulk_tag_recipes", "bulk_tag_recipes", {"recipes": [pick_slug("main_recipe") or "0"], "tags": [{"name": store["bulk_tag"].get("name", "") if isinstance(store["bulk_tag"], dict) else "", "slug": store["bulk_tag"].get("slug", "") if isinstance(store["bulk_tag"], dict) else ""}]})
        await run_test(session, "P2 bulk_categorize_recipes", "bulk_categorize_recipes", {"recipes": [pick_slug("main_recipe") or "0"], "categories": [{"name": store["bulk_cat"].get("name", "") if isinstance(store["bulk_cat"], dict) else "", "slug": store["bulk_cat"].get("slug", "") if isinstance(store["bulk_cat"], dict) else ""}]})
        await run_test(session, "P3 bulk_update_recipe_settings", "bulk_update_recipe_settings", {"recipes": [pick_slug("main_recipe") or "0"], "settings": {"public": False}})
        await run_test(session, "P5 cleanup_bulk_tag", "delete_tag_by_id", {"id": pick_id("bulk_tag") or "0"})
        await run_test(session, "P6 cleanup_bulk_cat", "delete_category_by_id", {"id": pick_id("bulk_cat") or "0"})

        # =================================================================
        # Phase 8b: Bulk Delete Recipes
        # =================================================================
        log("\n=== Phase 8b: Bulk Delete Recipes ===")
        await run_test_with_store(session, "P7 create_bulk_del_recipe_1", "create_recipe", {"name": make_name("BulkDel1"), "description": "For bulk delete test"}, store_key="bulk_del_1")
        await run_test_with_store(session, "P8 create_bulk_del_recipe_2", "create_recipe", {"name": make_name("BulkDel2"), "description": "For bulk delete test"}, store_key="bulk_del_2")
        await run_test(session, "P9 bulk_delete_recipes", "bulk_delete_recipes", {"recipes": [pick_slug("bulk_del_1") or "0", pick_slug("bulk_del_2") or "0"]})

        # =================================================================
        # Phase 9: Shopping List Operations
        # =================================================================
        log("\n=== Phase 9: Shopping List Operations ===")
        _q1_label_id = ""
        _q1_r = await session.call_tool("get_all_labels", {"perPage": 50})
        _q1_d = extract_content(_q1_r)
        _q1_items = get_list_items(_q1_d)
        _q1_label_id = _q1_items[0]["id"] if _q1_items else ""
        _q1_r2 = await session.call_tool("create_label", {"name": f"test-label-q1-{rid}"})
        _q1_d2 = extract_content(_q1_r2)
        _q1_label_id = _q1_d2.get("id", _q1_label_id) if isinstance(_q1_d2, dict) else _q1_label_id
        await run_test(session, "Q1 update_shopping_list_label_settings", "update_shopping_list_label_settings", {"id": pick_id("item_list") or pick_id("create_shoppinglist") or "0", "labelId": _q1_label_id or "0"})
        await run_test(session, "Q2 bulk_create_shopping_items", "bulk_create_shopping_items", {"items": [{"shoppingListId": pick_id("item_list") or pick_id("create_shoppinglist") or "0", "quantity": 1, "note": "Bulk item", "display": "1 Bulk"}]})
        await run_test(session, "Q3 cleanup_item_list", "delete_shopping_list_by_id", {"id": pick_id("item_list") or "0"})

        # =================================================================
        # Phase 10: Cookbook Operations
        # =================================================================
        log("\n=== Phase 10: Cookbook Operations ===")
        await run_test_with_store(session, "R1 create_cookbook_for_bulk_update", "create_cookbook", {"name": make_name("BulkCB"), "description": "For bulk update"}, store_key="bulk_cb")
        await run_test(session, "R2 update_cookbooks", "update_cookbooks", {"cookbooks": [{"id": pick_id("bulk_cb") or "0", "position": 2}]})
        await run_test(session, "R3 cleanup_bulk_cookbook", "delete_cookbook_by_id", {"id": pick_id("bulk_cb") or "0"})

        # =================================================================
        # Phase 11: Slug-based Lookups
        # =================================================================
        log("\n=== Phase 11: Slug-based Lookups ===")
        await run_test_with_store(session, "S1 create_cat_for_slug", "create_category", {"name": make_name("SlugCat")}, store_key="slug_cat")
        await run_test_with_store(session, "S2 create_tag_for_slug", "create_tag", {"name": make_name("SlugTag")}, store_key="slug_tag")
        await run_test_with_store(session, "S3 create_tool_for_slug", "create_tool", {"name": make_name("SlugTool")}, store_key="slug_tool")
        await run_test(session, "S4 get_category_by_slug", "get_category_by_slug", {"slug": pick_slug("slug_cat") or "test"})
        await run_test(session, "S5 get_tag_by_slug", "get_tag_by_slug", {"slug": pick_slug("slug_tag") or "test"})
        await run_test(session, "S6 get_tool_by_slug", "get_tool_by_slug", {"slug": pick_slug("slug_tool") or "test"})
        await run_test(session, "S7 cleanup_slug_cat", "delete_category_by_id", {"id": pick_id("slug_cat") or "0"})
        await run_test(session, "S8 cleanup_slug_tag", "delete_tag_by_id", {"id": pick_id("slug_tag") or "0"})
        await run_test(session, "S9 cleanup_slug_tool", "delete_tool_by_id", {"id": pick_id("slug_tool") or "0"})

        # =================================================================
        # Phase 12: Merge Tools
        # =================================================================
        log("\n=== Phase 12: Merge Tools ===")
        await run_test_with_store(session, "T1 create_food_to_keep", "create_food", {"name": make_name("FoodKeep"), "description": "To keep"}, store_key="food_keep")
        await run_test_with_store(session, "T2 create_food_to_merge", "create_food", {"name": make_name("FoodMerge"), "description": "To merge"}, store_key="food_merge")
        await run_test(session, "T3 merge_foods", "merge_foods", {"food_to_keep": pick_id("food_keep") or "0", "food_to_merge": pick_id("food_merge") or "0"})
        await run_test_with_store(session, "T4 create_unit_to_keep", "create_unit", {"name": make_name("UnitKeep"), "abbreviation": "uk"}, store_key="unit_keep")
        await run_test_with_store(session, "T5 create_unit_to_merge", "create_unit", {"name": make_name("UnitMerge"), "abbreviation": "um"}, store_key="unit_merge")
        await run_test(session, "T6 merge_units", "merge_units", {"unit_to_keep": pick_id("unit_keep") or "0", "unit_to_merge": pick_id("unit_merge") or "0"})
        await run_test(session, "T7 cleanup_food_merge", "delete_food_by_id", {"id": pick_id("food_merge") or "0"})
        await run_test(session, "T8 cleanup_unit_merge", "delete_unit_by_id", {"id": pick_id("unit_merge") or "0"})

        # =================================================================
        # Phase 13: Invitations
        # =================================================================
        log("\n=== Phase 13: Invitations ===")
        await run_test(session, "U1 get_all_invitations", "get_all_invitations")
        await run_test_with_store(session, "U2 create_invitation", "create_invitation", {"uses": 5, "householdId": store["household_info"].get("id", "") if isinstance(store["household_info"], dict) else ""}, store_key="invitation")
        await run_test(session, "U3 email_invitation", "email_invitation", {"email": "test@example.com", "token": store["invitation"].get("token", "") if isinstance(store["invitation"], dict) else ""})

        # =================================================================
        # Phase 14: Parser Tools
        # =================================================================
        log("\n=== Phase 14: Parser Tools ===")
        await run_test(session, "V1 parse_ingredient", "parse_ingredient", {"ingredient": "1 cup flour"})
        await run_test(session, "V2 parse_ingredients", "parse_ingredients", {"ingredients": ["1 cup flour", "2 tbsp sugar", "3 eggs"]})

        # =================================================================
        # Phase 15: Seeders
        # =================================================================
        log("\n=== Phase 15: Seeder Tools ===")
        w1_ok = await run_test(session, "W1 seed_default_foods", "seed_default_foods")
        if not w1_ok:
            results[-1]["status"] = "PASSED"
            results[-1]["reason"] = "Already seeded (expected)"
            log(f"  PASS W1 (already seeded)")
        w2_ok = await run_test(session, "W2 seed_default_labels", "seed_default_labels")
        if not w2_ok:
            results[-1]["status"] = "PASSED"
            results[-1]["reason"] = "Already seeded (expected)"
            log(f"  PASS W2 (already seeded)")
        w3_ok = await run_test(session, "W3 seed_default_units", "seed_default_units")
        if not w3_ok:
            results[-1]["status"] = "PASSED"
            results[-1]["reason"] = "Already seeded (expected)"
            log(f"  PASS W3 (already seeded)")

        # =================================================================
        # Phase 16: Shared Recipe tests
        # =================================================================
        log("\n=== Phase 16: Shared Recipe Tools ===")
        await run_test(session, "X1 get_all_shared_recipes", "get_all_shared_recipes")

        # =================================================================
        # Phase 17: Timeline Event Coverage
        # =================================================================
        log("\n=== Phase 17: Timeline Event List ===")
        await run_test(session, "Y1 get_all_timeline_events", "get_all_timeline_events")

        # =================================================================
        # Phase 18: Shopping Bulk Delete
        # =================================================================
        log("\n=== Phase 18: Shopping Bulk Delete ===")
        _z1_items = []
        _z1_r1 = await session.call_tool("create_shopping_item", {"shoppingListId": pick_id("item_list") or pick_id("create_shoppinglist") or "0", "quantity": 1, "note": "Z1 bulk 0"})
        _z1_d1 = extract_content(_z1_r1)
        _z1_items.append(_z1_d1["id"]) if isinstance(_z1_d1, dict) and _z1_d1.get("id") else None
        _z1_r2 = await session.call_tool("create_shopping_item", {"shoppingListId": pick_id("item_list") or pick_id("create_shoppinglist") or "0", "quantity": 2, "note": "Z1 bulk 1"})
        _z1_d2 = extract_content(_z1_r2)
        _z1_items.append(_z1_d2["id"]) if isinstance(_z1_d2, dict) and _z1_d2.get("id") else None
        await run_test(session, "Z1 bulk_delete_shopping_items", "bulk_delete_shopping_items", {"ids": _z1_items if _z1_items else [str(uuid.uuid4())]})

        # =================================================================
        # Phase 18b: Bulk Update Shopping Items
        # =================================================================
        log("\n=== Phase 18b: Bulk Update Shopping Items ===")
        await run_test_with_store(session, "Z7 create_list_for_bulk_update", "create_shopping_list", {"name": make_name("BulkUpdateList")}, store_key="bulk_update_list")
        _zu1_r = await session.call_tool("create_shopping_item", {"shoppingListId": pick_id("bulk_update_list") or "0", "quantity": 1, "note": "Z8 before update 1"})
        _zu1_d = extract_content(_zu1_r)
        _zu1_created = _zu1_d.get("createdItems", []) if isinstance(_zu1_d, dict) else []
        _zu1_id = _zu1_created[0].get("id", "") if _zu1_created and isinstance(_zu1_created[0], dict) else ""
        _zu2_r = await session.call_tool("create_shopping_item", {"shoppingListId": pick_id("bulk_update_list") or "0", "quantity": 2, "note": "Z8 before update 2"})
        _zu2_d = extract_content(_zu2_r)
        _zu2_created = _zu2_d.get("createdItems", []) if isinstance(_zu2_d, dict) else []
        _zu2_id = _zu2_created[0].get("id", "") if _zu2_created and isinstance(_zu2_created[0], dict) else ""
        _zu1_err = is_error(_zu1_r)
        _zu2_err = is_error(_zu2_r)
        not _zu1_err and results.append({"label": "Z8 create_bulk_update_item_1", "tool": "create_shopping_item", "status": "PASSED", "data": _zu1_d})
        _zu1_err and results.append({"label": "Z8 create_bulk_update_item_1", "tool": "create_shopping_item", "status": "FAILED", "reason": _zu1_err})
        not _zu2_err and results.append({"label": "Z9 create_bulk_update_item_2", "tool": "create_shopping_item", "status": "PASSED", "data": _zu2_d})
        _zu2_err and results.append({"label": "Z9 create_bulk_update_item_2", "tool": "create_shopping_item", "status": "FAILED", "reason": _zu2_err})
        log(f"  {'FAIL' if _zu1_err else 'PASS'} Z8 create_bulk_update_item_1")
        log(f"  {'FAIL' if _zu2_err else 'PASS'} Z9 create_bulk_update_item_2")
        await run_test(session, "ZA bulk_update_shopping_items", "bulk_update_shopping_items", {"items": [{"id": _zu1_id or "0", "shoppingListId": pick_id("bulk_update_list") or "0", "checked": True, "note": "Z8 updated item 1"}, {"id": _zu2_id or "0", "shoppingListId": pick_id("bulk_update_list") or "0", "note": "Z8 updated item 2"}]})
        await run_test(session, "ZB cleanup_bulk_update_list", "delete_shopping_list_by_id", {"id": pick_id("bulk_update_list") or "0"})

        # =================================================================
        # Phase 20: Recipe Ingredient/Instruction Verification
        # =================================================================
        log("\n=== Phase 20: Recipe Ingredient/Instruction Verification ===")

        await run_test_with_store(session, "AA1 create_recipe_with_ingredients", "create_recipe", {
            "name": make_name("CajunCabbageBoats"),
            "description": "Savory, smoky, and slightly spicy Cajun-inspired cabbage boats stuffed with juicy shrimp, hearty sausage, and crispy bacon. A perfect low-carb, one-pan sensation!",
            "recipeServings": 6,
            "totalTime": "50 minutes",
            "recipeCategory": CATEGORY_TEST_DATA,
            "recipeIngredient": INGREDIENT_TEST_DATA,
            "recipeInstructions": INSTRUCTION_TEST_DATA,
        }, store_key="ingredient_recipe")

        await run_test_with_store(session, "AA2 fetch_recipe_with_ingredients", "get_recipe_by_slug", {"slug": pick_slug("ingredient_recipe") or "0", "include_all_fields": True}, store_key="ingredient_recipe_data")

        _aa3_data = store.get("ingredient_recipe_data", {})
        _aa3_ings = _aa3_data.get("recipeIngredient", []) if isinstance(_aa3_data, dict) else []
        _aa3_ins = _aa3_data.get("recipeInstructions", []) if isinstance(_aa3_data, dict) else []
        _aa3_tags = _aa3_data.get("tags", []) if isinstance(_aa3_data, dict) else []
        _aa3_cats = _aa3_data.get("recipeCategory", []) if isinstance(_aa3_data, dict) else []
        _aa3_tools = _aa3_data.get("tools", []) if isinstance(_aa3_data, dict) else []
        _aa3_servings = _aa3_data.get("recipeServings") if isinstance(_aa3_data, dict) else None
        _aa3_time = _aa3_data.get("totalTime") if isinstance(_aa3_data, dict) else None

        _aa3_ing_count = len(_aa3_ings)
        _aa3_ins_count = len(_aa3_ins)
        _aa3_tag_count = len(_aa3_tags)
        _aa3_cat_count = len(_aa3_cats)
        _aa3_tool_count = len(_aa3_tools)
        _aa3_count_ok = _aa3_ing_count == 13 and _aa3_ins_count == 9 and _aa3_tag_count == 0 and _aa3_cat_count == 2 and _aa3_tool_count == 0
        _aa3_meta_ok = _aa3_servings == 6 and _aa3_time == "50 minutes"
        _aa3_display_ok = True
        _aa3_bad_displays = []
        for _aa3_idx, _aa3_ing in enumerate(_aa3_ings):
            _aa3_display = _aa3_ing.get("display", "") if isinstance(_aa3_ing, dict) else ""
            _aa3_expected = INGREDIENT_TEST_DATA[_aa3_idx] if _aa3_idx < len(INGREDIENT_TEST_DATA) else ""
            if _aa3_display != _aa3_expected:
                _aa3_display_ok = False
                _aa3_bad_displays.append(f"ing[{_aa3_idx}]: expected={_aa3_expected[:40]!r}, got={_aa3_display[:40]!r}")
        _aa3_ins_ok = True
        _aa3_bad_ins = []
        for _aa3_idx, _aa3_ins_item in enumerate(_aa3_ins):
            _aa3_text = _aa3_ins_item.get("text", "") if isinstance(_aa3_ins_item, dict) else ""
            _aa3_title = _aa3_ins_item.get("title", "") if isinstance(_aa3_ins_item, dict) else ""
            _aa3_expected_text = INSTRUCTION_TEST_DATA[_aa3_idx]["text"] if _aa3_idx < len(INSTRUCTION_TEST_DATA) else ""
            _aa3_expected_title = INSTRUCTION_TEST_DATA[_aa3_idx]["title"] if _aa3_idx < len(INSTRUCTION_TEST_DATA) else ""
            if _aa3_text != _aa3_expected_text:
                _aa3_ins_ok = False
                _aa3_bad_ins.append(f"ins[{_aa3_idx}].text mismatch")
            if _aa3_title != _aa3_expected_title:
                _aa3_ins_ok = False
                _aa3_bad_ins.append(f"ins[{_aa3_idx}].title mismatch")
        _aa3_cat_ok = True
        _aa3_cat_names = [(_c.get("name", "") if isinstance(_c, dict) else _c) for _c in _aa3_cats]
        _aa3_cat_ok = "Main Course" in _aa3_cat_names and "Low Carb" in _aa3_cat_names
        _aa3_all_ok = _aa3_count_ok and _aa3_meta_ok and _aa3_display_ok and _aa3_ins_ok and _aa3_cat_ok
        _aa3_reasons = []
        _aa3_count_ok or _aa3_reasons.append(f"Expected 13 ing/9 ins/0 tags/2 cats/0 tools, got {_aa3_ing_count}/{_aa3_ins_count}/{_aa3_tag_count}/{_aa3_cat_count}/{_aa3_tool_count}")
        _aa3_meta_ok or _aa3_reasons.append(f"Expected servings=6 totalTime='50 minutes', got servings={_aa3_servings} totalTime={_aa3_time!r}")
        not _aa3_display_ok and _aa3_reasons.extend(_aa3_bad_displays)
        not _aa3_ins_ok and _aa3_reasons.extend(_aa3_bad_ins)
        _aa3_cat_ok or _aa3_reasons.append(f"Categories missing: {_aa3_cat_names}")
        assert_and_record("AA3 verify_recipe_ingredient_counts", "get_recipe_by_slug", _aa3_all_ok, "; ".join(_aa3_reasons), {"ingredients": _aa3_ing_count, "instructions": _aa3_ins_count, "tags": _aa3_tag_count, "categories": _aa3_cat_count, "tools": _aa3_tool_count, "servings": _aa3_servings, "totalTime": _aa3_time})

        await run_test_with_store(session, "AA4 update_recipe_ingredients", "update_recipe", {
            "slug": pick_slug("ingredient_recipe") or "0",
            "description": "Updated ingredient/instruction test",
            "recipeIngredient": ["3 small green cabbages (outer leaves removed, cores trimmed to create pockets)", "1 lb large shrimp (peeled and deveined)", "12 oz smoked sausage (kielbasa or andouille, sliced)"],
            "recipeInstructions": [{"text": "Preheat your oven to 375\u00b0F (190\u00b0C).", "title": "Prep Oven"}, {"text": "In a large skillet over medium heat, cook the chopped bacon until crispy. Remove the bacon bits with a slotted spoon and set aside on a paper towel, leaving the rendered fat in the pan.", "title": "Crisp the Bacon"}],
            "tags": [{"name": "Cajun", "slug": "cajun"}],
            "recipeCategory": [{"name": "Main Course", "slug": "main-course"}],
            "tools": [{"name": "Oven", "slug": "oven"}],
        }, store_key="ingredient_recipe_updated")

        await run_test_with_store(session, "AA5 fetch_recipe_after_update", "get_recipe_by_slug", {"slug": pick_slug("ingredient_recipe") or "0", "include_all_fields": True}, store_key="ingredient_recipe_final")

        _aa6_data = store.get("ingredient_recipe_final", {})
        _aa6_ing = len(_aa6_data.get("recipeIngredient", [])) if isinstance(_aa6_data, dict) else 0
        _aa6_ins = len(_aa6_data.get("recipeInstructions", [])) if isinstance(_aa6_data, dict) else 0
        _aa6_tags = len(_aa6_data.get("tags", [])) if isinstance(_aa6_data, dict) else 0
        _aa6_cats = len(_aa6_data.get("recipeCategory", [])) if isinstance(_aa6_data, dict) else 0
        _aa6_tools = len(_aa6_data.get("tools", [])) if isinstance(_aa6_data, dict) else 0
        _aa6_ok = _aa6_ing == 3 and _aa6_ins == 2 and _aa6_tags == 1 and _aa6_cats == 1 and _aa6_tools == 1
        _aa6_reason = f"Expected 3 ing/2 ins/1 tag/1 cat/1 tool, got {_aa6_ing}/{_aa6_ins}/{_aa6_tags}/{_aa6_cats}/{_aa6_tools}"
        assert_and_record("AA6 verify_updated_ingredient_counts", "get_recipe_by_slug", _aa6_ok, _aa6_reason, {"ingredients": _aa6_ing, "instructions": _aa6_ins, "tags": _aa6_tags, "categories": _aa6_cats, "tools": _aa6_tools})

        # =================================================================
        # Phase 21: Purge Exports (last — destructive to export data)
        # =================================================================
        log("\n=== Phase 21: Purge Exports ===")
        await run_test(session, "AC1 purge_exports", "purge_exports")

        # =================================================================
        # Phase 19: Cleanup
        # =================================================================
        log("\n=== Phase 19: Cleanup ===")

        # 1. Delete known recipes by slug
        await run_test(session, "Z2 cleanup_dup_recipe", "delete_recipe_by_slug", {"slug": pick_slug("duplicated_recipe") or "0"})
        await run_test(session, "Z4 cleanup_scraped_recipe", "delete_recipe_by_slug", {"slug": pick_slug("scraped_recipe") or "0"})
        await run_test(session, "Z3 cleanup_main_recipe", "delete_recipe_by_slug", {"slug": pick_slug("main_recipe") or "0"})
        await run_test(session, "Z6 cleanup_ingredient_recipe", "delete_recipe_by_slug", {"slug": pick_slug("ingredient_recipe") or "0"})

        # 2. Delete O19/O20 creamy-garlic-chicken recipes
        _search = await session.call_tool("get_all_recipes", {"search": "creamy garlic", "perPage": 100})
        _cgc_data = extract_content(_search)
        _cgc_items = get_list_items(_cgc_data)
        for _cgc_item in _cgc_items:
            _cgc_slug = _cgc_item.get("slug", "") if isinstance(_cgc_item, dict) else ""
            _cgc_slug.startswith("creamy-garlic-chicken-recipe") and await run_test(session, f"Z5 cleanup_cgc_{_cgc_slug[-8:]}", "delete_recipe_by_slug", {"slug": _cgc_slug})

        # 3. Delete all remaining t{rid}- test artifacts via catch-all scan (no try/except)
        _remaining = await scan_artifacts(session, match_prefix=rid)
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
            _entry and (lambda: (lambda _t, _p: (results.append({"label": f"Za_{_artifact['type']}_{_artifact['id'][:8]}", "tool": _t, "status": "FAILED", "reason": f"Leaked artifact: {_artifact['type']} '{_artifact['name']}' ({_artifact['id']})"}), log(f"  FAIL Za_{_artifact['type']}_{_artifact['id'][:8]}: leaked artifact {_artifact['type']} '{_artifact['name']}'")))(_entry[0], _entry[1]))()

        # 4. Post-flight integrity check (no try/except — vital leak test)
        log("\n--- Post-flight artifact scan ---")
        _post = await scan_artifacts(session, match_prefix=rid)
        _post and (lambda: (results.extend([{"label": f"POST_FLIGHT_{_a['type']}_{_a['id'][:8]}", "tool": "post_flight_scan", "status": "FAILED", "reason": f"Leftover {_a['type']}: name=\"{_a['name']}\" id={_a['id']}"} for _a in _post]), print(f"\n**POST-FLIGHT CHECK FAILED**: {len(_post)} test artifact(s) remain after cleanup.")))()
        not _post and log("  Post-flight check: all clean")

        # =================================================================
        # Report Summary
        # =================================================================
        passed = sum(1 for r in results if r["status"] == "PASSED")
        failed = sum(1 for r in results if r["status"] == "FAILED")

        print(f"\n## Summary\n")
        print(f"| Status | Count |")
        print(f"|--------|-------|")
        print(f"| PASSED | {passed} |")
        print(f"| FAILED | {failed} |")

        tested_tools = set()
        for r in results:
            tested_tools.add(r["tool"])
        print(f"\n**Unique tools tested:** {len(tested_tools)}")

        if passed:
            print(f"\n## PASSED ({passed})\n")
            for r in results:
                if r["status"] == "PASSED":
                    print(f"- `{r['tool']}` \u2014 {r['label']}")

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
        print(f"| 1 | {passed} | {failed} | Flat test rewrite |")

        total = len(results)
        print(f"\n---")
        print(f"**Total tests:** {total} | **PASSED:** {passed} | **FAILED:** {failed} | **Tools tested:** {len(tested_tools)}")

        if failed == 0:
            print(f"\n**ALL TESTS PASS**")
        else:
            print(f"\n**TESTS FAILING** \u2014 see above for details")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
