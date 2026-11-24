"""Field-projection contracts, including the aggregate gate and user privacy."""

from __future__ import annotations

import os

from ..expect import require
from ..harness import Scenario, scenario
from .helpers import recipe_fixture


@scenario("projection", "recipe_and_user_projection",
          ["create_recipe", "get_recipe_by_slug", "list_all_recipes",
           "delete_recipe_by_slug", "get_user_profile", "list_users"])
def recipe_and_user_projection(s: Scenario) -> None:
    gate = os.getenv("ALLOW_ALL_AGGREGATE", "false").lower() in ("1", "true", "yes")
    fixture = recipe_fixture(s, "projection-recipe")

    default = s.call("get recipe default projection", "get_recipe_by_slug",
                     {"slug": fixture["slug"]}).data
    full = s.call("get recipe full projection", "get_recipe_by_slug",
                  {"slug": fixture["slug"], "include_all_fields": True}).data
    s.check("single-record get honors include_all_fields",
            lambda: require(
                "createdAt" in full and "createdAt" not in default,
                f"default={sorted(default)} full={sorted(full)}",
            ))
    s.check("full projection keeps the slug and name",
            lambda: require(full.get("slug") == fixture["slug"]
                            and full.get("name") == fixture["name"], full))

    default_list = s.find_in_pages(
        "list_all_recipes",
        lambda item: item.get("slug") == fixture["slug"],
        {"search": fixture["name"]}, per_page=200,
    )
    gate_list = s.find_in_pages(
        "list_all_recipes",
        lambda item: item.get("slug") == fixture["slug"],
        {"search": fixture["name"], "include_all_fields": True}, per_page=200,
    )
    default_item = next((item for item in default_list
                         if item.get("slug") == fixture["slug"]), {})
    gate_item = next((item for item in gate_list
                      if item.get("slug") == fixture["slug"]), {})
    s.check("aggregate list returns the fixture",
            lambda: require(bool(default_item) and bool(gate_item),
                            f"default={bool(default_item)} full={bool(gate_item)}"))
    if gate:
        s.check("aggregate list honors include_all_fields when enabled",
                lambda: require(
                    "createdAt" in gate_item and "createdAt" not in default_item,
                    f"default={sorted(default_item)} full={sorted(gate_item)}",
                ))
    else:
        s.check("aggregate list intentionally ignores include_all_fields when disabled",
                lambda: require(
                    set(gate_item) == set(default_item)
                    and "createdAt" not in gate_item,
                    f"default={sorted(default_item)} full={sorted(gate_item)}",
                ))

    profile = s.call("default profile projection", "get_user_profile", {}).data
    s.check("default profile hides tokens and cacheKey",
            lambda: require("tokens" not in profile and "cacheKey" not in profile,
                            sorted(profile)))
    full_profile = s.call("full profile projection", "get_user_profile",
                          {"include_all_fields": True}).data
    s.check("full profile includes token metadata",
            lambda: require("tokens" in full_profile and "cacheKey" in full_profile,
                            sorted(full_profile)))

    users = s.call("default admin user list", "list_users",
                   {"page": 1, "perPage": 200})
    user_items = s.items("admin users decode", users)
    s.check("default admin user list hides token metadata for every record",
            lambda: require(all("tokens" not in item and "cacheKey" not in item
                                for item in user_items), "metadata leaked"))
