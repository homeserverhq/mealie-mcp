"""Organizer contracts: categories, tags, tools, foods, and units."""

from __future__ import annotations

from ..expect import find_item, require
from ..harness import Scenario, scenario
from .helpers import (category_fixture, find_by, food_fixture,
                      require_found, tag_fixture, tool_fixture,
                      unit_fixture)


def _list_and_get(s: Scenario, *, kind: str, list_tool: str, get_id: str,
                  get_slug: str | None, fixture: dict, empty_tool: str | None,
                  update_tool: str, update_args: dict, expected: str,
                  delete_tool: str) -> None:
    _, items, meta = s.page(f"list {kind}s", list_tool, {"page": 1, "perPage": 2})
    all_items = s.find_in_pages(
        list_tool, lambda item: item.get("id") == fixture["id"], per_page=200
    )
    s.check(f"{kind} list includes the fixture",
            lambda: require(any(item.get("id") == fixture["id"]
                                for item in all_items), "fixture not listed"))
    s.check(f"{kind} list reports a count", lambda: require(meta["total"] >= 1, meta))

    got = s.call(f"get {kind} by id", get_id,
                 {"id": fixture["id"], "include_all_fields": True}).data
    s.check(f"get {kind} returns the fixture",
            lambda: require(got.get("id") == fixture["id"], got))
    s.check(f"{kind} name round-trips",
            lambda: require(got.get("name") == fixture["name"], got.get("name")))

    if get_slug and fixture["data"].get("slug"):
        got_slug = s.call(f"get {kind} by slug", get_slug,
                          {"slug": fixture["data"]["slug"]}).data
        s.check(f"get {kind} by slug matches",
                lambda: require(got_slug.get("id") == fixture["id"], got_slug))

    if empty_tool:
        empty_call = s.call(f"list empty {kind}s", empty_tool, {})
        empty_items = s.items(f"empty {kind}s decode", empty_call)
        s.check(f"new {kind} is listed as unused",
                lambda: require(
                    any(item.get("id") == fixture["id"] for item in empty_items),
                    f"{kind} {fixture['id']} missing from empty list",
                ))

    s.call(f"update {kind}", update_tool, {"id": fixture["id"], **update_args})
    after = s.call(f"get updated {kind}", get_id,
                   {"id": fixture["id"], "include_all_fields": True}).data
    s.check(f"update {kind} is persisted",
            lambda: require(after.get("name") == expected,
                            f"name={after.get('name')!r}, expected {expected!r}"))

    s.call(f"delete {kind}", delete_tool, {"id": fixture["id"]})
    s.forget_cleanup(delete_tool, {"id": fixture["id"]})
    s.expect_error(f"deleted {kind} is gone", get_id,
                   {"id": fixture["id"]}, contains=("404", "not found"))


@scenario("organizers", "categories_crud",
          ["list_all_categories", "list_empty_categories",
           "get_category_by_id", "get_category_by_slug", "create_category",
           "update_category", "delete_category_by_id", "create_recipe"])
def categories_crud(s: Scenario) -> None:
    fixture = category_fixture(s)
    _list_and_get(
        s, kind="category", list_tool="list_all_categories",
        get_id="get_category_by_id", get_slug="get_category_by_slug",
        fixture=fixture, empty_tool="list_empty_categories",
        update_tool="update_category",
        update_args={"name": fixture["name"] + "-upd"},
        expected=fixture["name"] + "-upd",
        delete_tool="delete_category_by_id",
    )


@scenario("organizers", "category_usage_leaves_empty_list",
          ["create_category", "create_recipe", "list_empty_categories",
           "list_all_categories", "delete_recipe_by_slug",
           "delete_category_by_id"])
def category_usage_leaves_empty_list(s: Scenario) -> None:
    category = category_fixture(s, "used-category")
    recipe = s.call("create recipe with category", "create_recipe", {
        "name": s.fixture("categorized-recipe"),
        "recipeCategory": [{
            "name": category["name"],
            "slug": category["data"].get("slug", ""),
        }],
    })
    slug = str(recipe.data.get("slug") or "")
    if slug:
        s.own(slug, recipe.data.get("id"))
        s.cleanup("delete_recipe_by_slug", {"slug": slug}, "cleanup categorized recipe")
    listed = s.call("list all categories after use", "list_all_categories",
                    {"page": 1, "perPage": 200})
    items = s.items("categories after use decode", listed)
    s.check("used category remains in the full list",
            lambda: require(any(item.get("id") == category["id"] for item in items),
                            "category missing from full list"))
    empty = s.call("list empty categories after use", "list_empty_categories")
    empty_items = s.items("empty categories after use decode", empty)
    s.check("used category is no longer empty",
            lambda: require(not any(item.get("id") == category["id"]
                                    for item in empty_items),
                            "used category still listed as empty"))


@scenario("organizers", "tags_crud",
          ["list_all_tags", "list_empty_tags", "get_tag_by_id",
           "get_tag_by_slug", "create_tag", "update_tag",
           "delete_tag_by_id"])
def tags_crud(s: Scenario) -> None:
    fixture = tag_fixture(s)
    _list_and_get(
        s, kind="tag", list_tool="list_all_tags",
        get_id="get_tag_by_id", get_slug="get_tag_by_slug",
        fixture=fixture, empty_tool="list_empty_tags",
        update_tool="update_tag",
        update_args={"name": fixture["name"] + "-upd"},
        expected=fixture["name"] + "-upd",
        delete_tool="delete_tag_by_id",
    )


@scenario("organizers", "tools_crud",
          ["list_all_tools", "get_tool_by_id", "get_tool_by_slug",
           "create_tool", "update_tool", "delete_tool_by_id"])
def tools_crud(s: Scenario) -> None:
    fixture = tool_fixture(s)
    _list_and_get(
        s, kind="tool", list_tool="list_all_tools",
        get_id="get_tool_by_id", get_slug="get_tool_by_slug",
        fixture=fixture, empty_tool=None,
        update_tool="update_tool",
        update_args={"name": fixture["name"] + "-upd"},
        expected=fixture["name"] + "-upd",
        delete_tool="delete_tool_by_id",
    )


@scenario("organizers", "foods_crud_and_merge",
          ["list_all_foods", "get_food_by_id", "create_food",
           "update_food", "delete_food_by_id", "merge_foods"])
def foods_crud_and_merge(s: Scenario) -> None:
    fixture = food_fixture(s)
    _list_and_get(
        s, kind="food", list_tool="list_all_foods",
        get_id="get_food_by_id", get_slug=None,
        fixture=fixture, empty_tool=None,
        update_tool="update_food",
        update_args={"name": fixture["name"] + "-upd"},
        expected=fixture["name"] + "-upd",
        delete_tool="delete_food_by_id",
    )


@scenario("organizers", "food_merge",
          ["create_food", "merge_foods", "get_food_by_id",
           "delete_food_by_id", "list_all_foods"])
def food_merge(s: Scenario, kind: str = "food", create: str = "create_food",
               merge: str = "merge_foods", get: str = "get_food_by_id",
               delete: str = "delete_food_by_id",
               list_tool: str = "list_all_foods",
               keep_key: str = "food_to_keep",
               merge_key: str = "food_to_merge") -> None:
    keep = food_fixture(s, "food-keep")
    source = food_fixture(s, "food-source")
    s.call("merge foods", merge, {keep_key: keep["id"], merge_key: source["id"]})
    s.call("get food kept after merge", get, {"id": keep["id"]})
    s.expect_error("get food merged away", get, {"id": source["id"]},
                   contains=("404", "not found"))


@scenario("organizers", "units_crud",
          ["list_all_units", "get_unit_by_id", "create_unit", "update_unit",
           "delete_unit_by_id"])
def units_crud(s: Scenario) -> None:
    fixture = unit_fixture(s)
    _list_and_get(
        s, kind="unit", list_tool="list_all_units",
        get_id="get_unit_by_id", get_slug=None,
        fixture=fixture, empty_tool=None,
        update_tool="update_unit",
        update_args={"name": fixture["name"] + "-upd"},
        expected=fixture["name"] + "-upd",
        delete_tool="delete_unit_by_id",
    )


@scenario("organizers", "unit_merge",
          ["create_unit", "merge_units", "get_unit_by_id",
           "delete_unit_by_id", "list_all_units"])
def unit_merge(s: Scenario) -> None:
    keep = unit_fixture(s, "unit-keep")
    source = unit_fixture(s, "unit-source")
    s.call("merge units", "merge_units",
           {"unit_to_keep": keep["id"], "unit_to_merge": source["id"]})
    s.call("get unit kept after merge", "get_unit_by_id", {"id": keep["id"]})
    s.expect_error("get unit merged away", "get_unit_by_id",
                   {"id": source["id"]}, contains=("404", "not found"))
