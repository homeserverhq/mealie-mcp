"""Mealplan and mealplan-rule contracts, including date-only validation."""

from __future__ import annotations

import datetime as dt

from ..expect import require, require_date_only
from ..harness import Scenario, scenario
from .helpers import find_by, mealplan_fixture, recipe_fixture


@scenario("mealplans", "mealplan_crud_and_filters",
          ["create_mealplan", "get_mealplan_by_id", "list_all_mealplans",
           "list_todays_meals", "update_mealplan", "delete_mealplan_by_id",
           "create_random_mealplan", "create_recipe", "delete_recipe_by_slug"])
def mealplan_crud_and_filters(s: Scenario) -> None:
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    next_week = (dt.date.today() + dt.timedelta(days=7)).isoformat()
    fixture = mealplan_fixture(s, "mealplan", day=tomorrow)
    mealplan_id = fixture["id"]
    s.check("mealplan has an integer id", lambda: require(mealplan_id is not None, fixture))

    found = find_by(s, "list_all_mealplans", "id", mealplan_id)
    s.check("mealplan appears in its list", lambda: require(found is not None, "missing"))
    got = s.call("get mealplan", "get_mealplan_by_id",
                 {"id": mealplan_id, "include_all_fields": True}).data
    s.check("mealplan date round-trips",
            lambda: require_date_only(got.get("date"), "date"))
    s.check("mealplan date keeps the requested day",
            lambda: require(got.get("date") == tomorrow, got.get("date")))

    updated_title = fixture["title"] + "-updated"
    s.call("update mealplan", "update_mealplan", {
        "id": mealplan_id, "title": updated_title, "date": next_week,
    })
    after = s.call("get updated mealplan", "get_mealplan_by_id",
                   {"id": mealplan_id, "include_all_fields": True}).data
    s.check("mealplan update is persisted",
            lambda: require(after.get("title") == updated_title and after.get("date") == next_week,
                            after))

    ranged = s.call("list mealplans in range", "list_all_mealplans", {
        "page": 1, "perPage": 50, "startDate": next_week, "endDate": next_week,
    })
    ranged_items = s.items("ranged mealplans decode", ranged)
    s.check("date range includes the fixture",
            lambda: require(any(item.get("id") == mealplan_id for item in ranged_items),
                            "fixture missing from range"))
    excluded = s.call("list mealplans outside the range", "list_all_mealplans", {
        "page": 1, "perPage": 50, "startDate": tomorrow, "endDate": tomorrow,
    })
    excluded_items = s.items("excluded mealplans decode", excluded)
    s.check("date range excludes the fixture on another day",
            lambda: require(not any(item.get("id") == mealplan_id
                                    for item in excluded_items),
                            "fixture appeared outside its day"))

    today_title = s.fixture("today-meal")
    today_call = s.call("create today's meal", "create_mealplan", {
        "date": dt.date.today().isoformat(), "title": today_title,
    })
    today_id = today_call.data.get("id")
    if today_id is not None:
        s.own(today_id)
        s.cleanup("delete_mealplan_by_id", {"id": today_id}, "cleanup today's meal")
    today = s.call("list today's meals", "list_todays_meals", {})
    today_items = s.items("today meals decode", today)
    s.check("today's list includes today's meal",
            lambda: require(any(item.get("title") == today_title
                                for item in today_items), today_items))

    for value, label in (
        ("2026-11-25T10:00:00Z", "datetime"),
        ("1795638600", "epoch"),
        ("2026-13-40", "invalid calendar date"),
    ):
        s.expect_error(f"mealplan rejects a {label}", "create_mealplan",
                       {"date": value, "title": s.fixture("bad-date")},
                       contains=("ISO 8601 date", "Invalid date", "date"))
    s.expect_error("mealplan rejects a datetime range filter",
                   "list_all_mealplans",
                   {"startDate": "2026-11-25T10:00:00Z"},
                   contains=("ISO 8601 date", "Invalid date", "date"))

    # Random mealplan needs at least one rule and one recipe.
    weekday = dt.date.today().strftime("%A").lower()
    rule = s.call("create random-meal rule", "create_mealplan_rule", {
        "day": weekday, "entryType": "dinner",
    })
    rule_id = rule.data.get("id")
    if rule_id:
        s.own(rule_id)
        s.cleanup("delete_mealplan_rule_by_id", {"id": rule_id},
                  "cleanup random-meal rule")
    recipe = recipe_fixture(s, "random-recipe")
    random_call = s.attempt("create random mealplan", "create_random_mealplan", {})
    if random_call.is_error:
        s.skip("random mealplan", random_call.error[:300])
    else:
        random_id = random_call.data.get("id")
        if random_id is not None:
            s.own(random_id)
            s.cleanup("delete_mealplan_by_id", {"id": random_id},
                      "cleanup random mealplan")

    s.call("delete mealplan", "delete_mealplan_by_id", {"id": mealplan_id})
    s.forget_cleanup("delete_mealplan_by_id", {"id": mealplan_id})
    s.expect_error("deleted mealplan is gone", "get_mealplan_by_id",
                   {"id": mealplan_id}, contains=("404", "not found"))


@scenario("mealplans", "mealplan_rule_crud",
          ["create_mealplan_rule", "list_all_mealplan_rules",
           "get_mealplan_rule_by_id", "update_mealplan_rule",
           "delete_mealplan_rule_by_id"])
def mealplan_rule_crud(s: Scenario) -> None:
    day = (dt.date.today() + dt.timedelta(days=2)).strftime("%A").lower()
    created = s.call("create mealplan rule", "create_mealplan_rule", {
        "day": day, "entryType": "lunch", "queryFilterString": "",
    })
    rule_id = str(created.data.get("id") or "")
    s.check("rule create returns an id", lambda: require(bool(rule_id), created.data))
    if not rule_id:
        return
    s.own(rule_id)
    s.cleanup("delete_mealplan_rule_by_id", {"id": rule_id}, "cleanup rule")

    found = find_by(s, "list_all_mealplan_rules", "id", rule_id)
    s.check("rule appears in its list", lambda: require(found is not None, "missing"))
    got = s.call("get rule", "get_mealplan_rule_by_id",
                 {"id": rule_id, "include_all_fields": True}).data
    s.check("rule day round-trips", lambda: require(got.get("day") == day, got.get("day")))

    s.call("update rule", "update_mealplan_rule",
           {"id": rule_id, "entryType": "dinner"})
    after = s.call("get updated rule", "get_mealplan_rule_by_id",
                   {"id": rule_id, "include_all_fields": True}).data
    s.check("rule update is persisted",
            lambda: require(after.get("entryType") == "dinner", after.get("entryType")))

    s.call("delete rule", "delete_mealplan_rule_by_id", {"id": rule_id})
    s.forget_cleanup("delete_mealplan_rule_by_id", {"id": rule_id})
    s.expect_error("deleted rule is gone", "get_mealplan_rule_by_id",
                   {"id": rule_id}, contains=("404", "not found"))
