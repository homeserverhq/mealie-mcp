"""Offset pagination contracts: bounds, totals, and page advance."""

from __future__ import annotations

from ..expect import require
from ..harness import Scenario, scenario
from .helpers import category_fixture


@scenario("pagination", "offset_pagination",
          ["create_category", "list_all_categories", "delete_category_by_id",
           "list_users"])
def offset_pagination(s: Scenario) -> None:
    fixtures = [category_fixture(s, f"page-{index}") for index in range(5)]
    ids = {fixture["id"] for fixture in fixtures if fixture["id"]}

    baseline = s.call("baseline category page", "list_all_categories",
                      {"page": 1, "perPage": 1}).data
    baseline_total = baseline.get("total") or 0
    s.check("baseline page exposes total", lambda: require(isinstance(baseline_total, int), baseline))

    pages = []
    for page_number in (1, 2, 3):
        _, items, meta = s.page(f"category page {page_number}", "list_all_categories",
                                {"page": page_number, "perPage": 2})
        pages.append((items, meta))
        s.check(f"page {page_number} respects perPage",
                lambda items=items: require(len(items) <= 2, len(items)))
        s.check(f"page {page_number} keeps the total",
                lambda meta=meta: require(meta["total"] >= baseline_total, meta))
        s.check(f"page {page_number} computes total_pages",
                lambda meta=meta: require(
                    meta["total_pages"] == (meta["total"] + 1) // 2, meta))

    first_ids = {str(item.get("id")) for item in pages[0][0]}
    second_ids = {str(item.get("id")) for item in pages[1][0]}
    s.check("page 1 and page 2 do not overlap",
            lambda: require(not (first_ids & second_ids),
                            sorted(first_ids & second_ids)))
    s.check("the fixtures span multiple pages",
            lambda: require(len(pages[2][0]) > 0, "page 3 is empty"))

    last_meta = pages[2][1]
    beyond = s.call("page beyond the end", "list_all_categories",
                    {"page": last_meta["total_pages"] + 5, "perPage": 2})
    beyond_items = s.items("beyond-end page decode", beyond)
    s.check("a page beyond the end is empty, not an error",
            lambda: require(beyond_items == [], beyond_items))

    for args, label in (
        ({"page": 0, "perPage": 2}, "zero page"),
        ({"page": 1, "perPage": 0}, "zero perPage"),
        ({"page": 1, "perPage": -1}, "negative perPage"),
        ({"page": 1, "perPage": 201}, "oversized perPage"),
    ):
        s.expect_error(f"pagination rejects {label}", "list_all_categories",
                       args, contains=("page", "perPage", "between", ">="))

    # Verifies pagination on a different resource without creating users.
    _, users_page_1, users_meta = s.page("users page 1", "list_users",
                                         {"page": 1, "perPage": 2})
    s.check("user list paginates",
            lambda: require(len(users_page_1) <= 2 and users_meta["total"] >= 1,
                            users_meta))
