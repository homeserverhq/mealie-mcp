"""Error taxonomy and destructive semantics contracts."""

from __future__ import annotations

from ..expect import require
from ..harness import Scenario, scenario
from .helpers import category_fixture, food_fixture, recipe_fixture

MISSING_UUID = "11111111-1111-4111-8111-111111111111"


@scenario("errors", "not_found_validation_and_delete_twice",
          ["create_category", "get_category_by_id", "update_category",
           "delete_category_by_id", "create_mealplan", "create_recipe",
           "update_recipe", "delete_recipe_by_slug", "bulk_delete_recipes",
           "bulk_delete_shopping_items", "create_food", "merge_foods",
           "delete_food_by_id", "list_all_categories"])
def not_found_validation_and_delete_twice(s: Scenario) -> None:
    fixture = category_fixture(s, "error-category")
    category_id = fixture["id"]

    s.expect_error("malformed UUID is rejected", "get_category_by_id",
                   {"id": "not-a-uuid"},
                   contains=("400", "uuid", "valid", "422"))
    s.expect_error("valid but unknown UUID reports not found",
                   "get_category_by_id", {"id": MISSING_UUID},
                   contains=("404", "not found"))
    s.expect_error("update with no fields is rejected", "update_category",
                   {"id": category_id},
                   contains=("At least one field", "field", "required"))
    s.expect_error("create without a required field is rejected",
                   "create_category", {},
                   contains=("required", "validation", "missing", "Field"))

    s.call("delete error fixture", "delete_category_by_id", {"id": category_id})
    s.expect_error("second delete reports not found", "delete_category_by_id",
                   {"id": category_id}, contains=("404", "not found"))
    s.expect_error("deleted record is not gettable", "get_category_by_id",
                   {"id": category_id}, contains=("404", "not found"))
    s.expect_error("deleted record is not updatable", "update_category",
                   {"id": category_id, "name": fixture["name"] + "-late"},
                   contains=("404", "not found"))

    s.expect_error("invalid meal type is rejected", "create_mealplan",
                   {"date": "2026-11-25", "entryType": "brunch"},
                   contains=("Invalid entryType", "breakfast", "lunch", "dinner"))
    s.expect_error("empty bulk recipe delete is rejected", "bulk_delete_recipes",
                   {"recipes": []}, contains=("at least one", "recipes"))
    s.expect_error("empty bulk shopping delete is rejected",
                   "bulk_delete_shopping_items", {"ids": []},
                   contains=("at least one", "ids"))
    food = food_fixture(s, "merge-self-food")
    s.expect_error("merging a food with itself is rejected", "merge_foods",
                   {"food_to_keep": food["id"], "food_to_merge": food["id"]},
                   contains=("must differ", "food"))

    recipe = recipe_fixture(s, "error-recipe")
    s.expect_error("recipe update with no fields is rejected", "update_recipe",
                   {"slug": recipe["slug"]},
                   contains=("At least one field", "field"))
    s.allow("does-not-exist")
    s.expect_error("unknown recipe update is rejected", "update_recipe",
                   {"slug": "does-not-exist", "name": "x"},
                   contains=("404", "not found"))
