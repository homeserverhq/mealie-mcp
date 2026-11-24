"""Small self-tests for the audit harness and Mealie helpers.

Run with ``python -m src.audit.selftest``.
"""

from __future__ import annotations

import ast
import base64
import json
from pathlib import Path

from toon_mcp import json_to_toon

from .adapter import _decode_jwt
from .expect import (require_date_only, require_duration, require_page,
                     require_absolute_url)
from .mcp_client import _parse_sse, decode_items
from src.main import (_jsonable, NutritionInput, RecipeNoteParam,
                      RecipeSettingsParam)


def test_sse_crlf() -> None:
    body = (
        'event: message\r\n'
        'data: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\r\n\r\n'
    )
    messages = _parse_sse(body)
    assert messages and messages[0]["id"] == 1
    assert messages[0]["result"]["tools"] == []


def test_toon_decode() -> None:
    items = [{"id": "1", "name": "fixture"}]
    encoded = json_to_toon(items)
    decoded = decode_items({"items": encoded}, "list_fixture")
    assert decoded == items
    assert decode_items({"items": []}, "list_fixture") == []


def test_page_shape() -> None:
    payload = {
        "items": json_to_toon([{"id": "1"}]),
        "page": 1,
        "per_page": 2,
        "total": 3,
        "total_pages": 2,
    }
    items, page, per_page, total, total_pages = require_page(payload, "list_x")
    assert items == [{"id": "1"}]
    assert (page, per_page, total, total_pages) == (1, 2, 3, 2)
    nested = {"items": json_to_toon({"page": 1, "items": []})}
    try:
        require_page(nested, "list_x")
    except AssertionError:
        pass
    else:
        raise AssertionError("nested page object was accepted")


def test_dates_and_durations() -> None:
    assert require_date_only("2026-11-25", "date")
    assert require_duration("PT45M", "totalTime")
    assert require_duration("P1DT2H", "totalTime")
    for bad in ("2026-11-25T10:00:00Z", "25-11-2026", "1795638600"):
        try:
            require_date_only(bad, "date")
        except AssertionError:
            pass
        else:
            raise AssertionError(f"invalid date accepted: {bad}")
    assert require_absolute_url("https://mealie.example.com/g/home/r/x", "recipeUrl")


def test_jwt_decode() -> None:
    payload = {"sub": "abc", "id": "abc", "name": "MCP"}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    token = f"header.{encoded}.signature"
    decoded = _decode_jwt(token)
    assert decoded["sub"] == "abc"
    assert decoded["name"] == "MCP"


def main() -> int:
    tests = [test_sse_crlf, test_toon_decode, test_page_shape,
             test_dates_and_durations, test_jwt_decode,
             test_jsonable_nested_models, test_create_recipe_is_transactional]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)} self-tests passed")
    return 0



def test_jsonable_nested_models() -> None:
    """The exact regression: nested Pydantic models must be JSON-safe."""
    payload = _jsonable({
        "settings": RecipeSettingsParam(public=True, showNutrition=True),
        "notes": [RecipeNoteParam(title="Tip", text="Body")],
        "nutrition": NutritionInput(calories="520", proteinContent="18"),
    })
    assert payload["settings"]["public"] is True
    assert payload["notes"][0]["title"] == "Tip"
    assert payload["nutrition"]["calories"] == "520"
    json.dumps(payload)


def test_create_recipe_is_transactional() -> None:
    """A failed follow-up write must delete the just-created recipe."""
    source = Path("src/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    create = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_recipe"
    )
    found_cleanup = False
    for node in ast.walk(create):
        if not isinstance(node, ast.ExceptHandler):
            continue
        for child in ast.walk(node):
            if (isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "delete_recipe_by_slug"):
                found_cleanup = True
    assert found_cleanup, "create_recipe has no orphan cleanup on failure"


if __name__ == "__main__":
    raise SystemExit(main())
