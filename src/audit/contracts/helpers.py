"""Shared fixture helpers for Mealie audit contracts."""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..expect import (require, require_absolute_url, require_contains_path,
                      require_date_only)


def recipe_fixture(s, suffix: str = "recipe", account: str = "primary",
                   **extra: Any) -> dict[str, Any]:
    name = s.fixture(suffix)
    payload = {
        "name": name,
        "description": f"{name} description",
        "recipeIngredient": ["1 cup flour", "2 eggs"],
        "recipeInstructions": ["Mix", "Bake"],
        **extra,
    }
    call = s.call(f"create {suffix}", "create_recipe", payload, account=account)
    slug = str(call.data.get("slug") or "")
    record_id = str(call.data.get("id") or "")
    s.check(f"{suffix} has a slug", lambda: require(bool(slug), call.data))
    if slug:
        s.own(slug, record_id)
        s.cleanup("delete_recipe_by_slug", {"slug": slug},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "slug": slug, "id": record_id, "data": call.data}


def category_fixture(s, suffix: str = "category", account: str = "primary") -> dict[str, Any]:
    name = s.fixture(suffix)
    call = s.call(f"create {suffix}", "create_category", {"name": name}, account=account)
    record_id = str(call.data.get("id") or "")
    s.own(record_id)
    if record_id:
        s.cleanup("delete_category_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "id": record_id, "data": call.data}


def tag_fixture(s, suffix: str = "tag", account: str = "primary") -> dict[str, Any]:
    name = s.fixture(suffix)
    call = s.call(f"create {suffix}", "create_tag", {"name": name}, account=account)
    record_id = str(call.data.get("id") or "")
    s.own(record_id)
    if record_id:
        s.cleanup("delete_tag_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "id": record_id, "data": call.data}


def tool_fixture(s, suffix: str = "tool", account: str = "primary") -> dict[str, Any]:
    name = s.fixture(suffix)
    call = s.call(f"create {suffix}", "create_tool", {"name": name}, account=account)
    record_id = str(call.data.get("id") or "")
    s.own(record_id)
    if record_id:
        s.cleanup("delete_tool_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "id": record_id, "data": call.data}


def food_fixture(s, suffix: str = "food", account: str = "primary") -> dict[str, Any]:
    name = s.fixture(suffix)
    call = s.call(f"create {suffix}", "create_food",
                  {"name": name, "description": "audit food"}, account=account)
    record_id = str(call.data.get("id") or "")
    s.own(record_id)
    if record_id:
        s.cleanup("delete_food_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "id": record_id, "data": call.data}


def unit_fixture(s, suffix: str = "unit", account: str = "primary") -> dict[str, Any]:
    name = s.fixture(suffix)
    call = s.call(f"create {suffix}", "create_unit",
                  {"name": name, "abbreviation": "aud"}, account=account)
    record_id = str(call.data.get("id") or "")
    s.own(record_id)
    if record_id:
        s.cleanup("delete_unit_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "id": record_id, "data": call.data}


def label_fixture(s, suffix: str = "label", account: str = "primary") -> dict[str, Any]:
    name = s.fixture(suffix)
    call = s.call(f"create {suffix}", "create_label",
                  {"name": name, "color": "#336699"}, account=account)
    record_id = str(call.data.get("id") or "")
    s.own(record_id)
    if record_id:
        s.cleanup("delete_label_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "id": record_id, "data": call.data}


def cookbook_fixture(s, suffix: str = "cookbook", account: str = "primary",
                     **extra: Any) -> dict[str, Any]:
    name = s.fixture(suffix)
    call = s.call(f"create {suffix}", "create_cookbook",
                  {"name": name, "description": "audit cookbook", **extra},
                  account=account)
    record_id = str(call.data.get("id") or "")
    s.own(record_id)
    if record_id:
        s.cleanup("delete_cookbook_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "id": record_id, "data": call.data}


def shopping_list_fixture(s, suffix: str = "shopping-list",
                          account: str = "primary") -> dict[str, Any]:
    name = s.fixture(suffix)
    call = s.call(f"create {suffix}", "create_shopping_list", {"name": name},
                  account=account)
    record_id = str(call.data.get("id") or "")
    s.own(record_id)
    if record_id:
        s.cleanup("delete_shopping_list_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"name": name, "id": record_id, "data": call.data}


def mealplan_fixture(s, suffix: str = "mealplan", account: str = "primary",
                     day: str | None = None, **extra: Any) -> dict[str, Any]:
    date = day or dt.date.today().isoformat()
    record = {"date": date, "title": s.fixture(suffix), **extra}
    call = s.call(f"create {suffix}", "create_mealplan", record, account=account)
    record_id = call.data.get("id")
    s.own(record_id)
    if record_id is not None:
        s.cleanup("delete_mealplan_by_id", {"id": record_id},
                  f"cleanup {suffix}", account=account)
    return {"id": record_id, "date": date, "title": record["title"],
            "data": call.data}


def find_by(s, tool: str, field: str, value: Any, **args: Any) -> dict[str, Any] | None:
    items = s.find_in_pages(tool, lambda item: item.get(field) == value, args)
    for item in items:
        if item.get(field) == value:
            return item
    return None


def require_found(s, tool: str, field: str, value: Any, **args: Any) -> dict[str, Any]:
    item = find_by(s, tool, field, value, **args)
    if item is None:
        raise AssertionError(f"{tool}: no item with {field}={value!r}")
    return item


def assert_recipe_urls(s, item: dict[str, Any], group_slug: str) -> None:
    url = item.get("recipeUrl")
    s.check("recipeUrl is absolute",
            lambda: require_absolute_url(url, "recipeUrl"))
    s.check("recipeUrl uses the caller's group",
            lambda: require_contains_path(url, "recipeUrl", f"/g/{group_slug}/", "/r/"))
    if item.get("recipeImgUrl"):
        s.check("recipeImgUrl is absolute",
                lambda: require_absolute_url(item.get("recipeImgUrl"), "recipeImgUrl"))


def assert_date_roundtrip(s, value: Any, expected: str, label: str) -> None:
    s.check(label, lambda: require_date_only(value, label))
    s.check(f"{label} keeps the requested day",
            lambda: require(value == expected, f"{value!r} != {expected!r}"))
