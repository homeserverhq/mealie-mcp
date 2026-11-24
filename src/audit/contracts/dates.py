"""Date-only, duration, and timestamp contracts."""

from __future__ import annotations

import datetime as dt

from ..expect import require, require_date_only, require_duration
from ..harness import Scenario, scenario
from .helpers import mealplan_fixture, recipe_fixture


@scenario("dates", "mealplan_dates_and_recipe_durations",
          ["create_mealplan", "get_mealplan_by_id", "delete_mealplan_by_id",
           "create_recipe", "get_recipe_by_slug", "update_recipe",
           "delete_recipe_by_slug"])
def mealplan_dates_and_recipe_durations(s: Scenario) -> None:
    day = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    meal = mealplan_fixture(s, "date-meal", day=day)
    got = s.call("get dated mealplan", "get_mealplan_by_id",
                 {"id": meal["id"], "include_all_fields": True}).data
    s.check("mealplan date is date-only", lambda: require_date_only(got.get("date"), "date"))
    s.check("mealplan date is unchanged", lambda: require(got.get("date") == day, got.get("date")))

    recipe = recipe_fixture(s, "duration-recipe", totalTime="PT45M", prepTime="PT10M")
    full = s.call("get duration recipe", "get_recipe_by_slug",
                  {"slug": recipe["slug"], "include_all_fields": True}).data
    s.check("totalTime is an ISO 8601 duration",
            lambda: require_duration(full.get("totalTime"), "totalTime"))
    s.check("prepTime is an ISO 8601 duration",
            lambda: require_duration(full.get("prepTime"), "prepTime"))
    s.call("update recipe duration", "update_recipe",
           {"slug": recipe["slug"], "cookTime": "PT30M"})
    after = s.call("get recipe after duration update", "get_recipe_by_slug",
                   {"slug": recipe["slug"], "include_all_fields": True}).data
    s.check("updated duration is stored",
            lambda: require(after.get("cookTime") == "PT30M", after.get("cookTime")))

    for value, label in (
        ("2026-11-25T10:00:00Z", "datetime"),
        ("1795638600", "epoch"),
    ):
        s.expect_error(f"date field rejects a {label}", "create_mealplan",
                       {"date": value, "title": s.fixture("bad-date")},
                       contains=("ISO 8601 date", "Invalid date", "date"))
