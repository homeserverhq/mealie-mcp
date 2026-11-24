"""Shopping list and shopping item contracts, including bulk operations."""

from __future__ import annotations

from ..expect import require
from ..harness import Scenario, scenario
from .helpers import (find_by, label_fixture, recipe_fixture,
                      shopping_list_fixture)


@scenario("shopping", "shopping_list_crud",
          ["create_shopping_list", "list_all_shopping_lists",
           "get_shopping_list_by_id", "update_shopping_list",
           "update_shopping_list_label_settings",
           "add_recipe_to_shopping_list", "remove_recipe_from_shopping_list",
           "delete_shopping_list_by_id", "create_recipe"])
def shopping_list_crud(s: Scenario) -> None:
    fixture = shopping_list_fixture(s)
    list_id = fixture["id"]
    found = find_by(s, "list_all_shopping_lists", "id", list_id)
    s.check("shopping list appears in its list", lambda: require(found is not None, "missing"))

    got = s.call("get shopping list", "get_shopping_list_by_id",
                 {"id": list_id, "include_all_fields": True}).data
    s.check("shopping list name round-trips",
            lambda: require(got.get("name") == fixture["name"], got.get("name")))

    updated = fixture["name"] + "-updated"
    s.call("update shopping list", "update_shopping_list",
           {"id": list_id, "name": updated})
    after = s.call("get updated shopping list", "get_shopping_list_by_id",
                   {"id": list_id, "include_all_fields": True}).data
    s.check("shopping list update is persisted",
            lambda: require(after.get("name") == updated, after.get("name")))

    label = label_fixture(s, "shopping-label")
    s.call("update shopping list label settings",
           "update_shopping_list_label_settings",
           {"id": list_id, "labelId": label["id"], "fontSize": 14.0,
            "fontFamily": "Arial"})

    recipe = recipe_fixture(s, "shopping-recipe")
    added = s.call_any("add recipe to shopping list",
                       "add_recipe_to_shopping_list",
                       {"id": list_id, "recipeId": recipe["id"]})
    s.check("adding a recipe to a list succeeds",
            lambda: require(not added.is_error, added.error))
    if not added.is_error:
        items = s.call("list shopping items after recipe add",
                       "list_all_shopping_items", {"page": 1, "perPage": 200})
        item_values = s.items("shopping items after recipe add decode", items)
        s.check("recipe ingredients create shopping items",
                lambda: require(any(isinstance(item, dict)
                                    and item.get("shoppingListId") == list_id
                                    for item in item_values),
                                "no items for the list"))
        removed = s.call_any("remove recipe from shopping list",
                             "remove_recipe_from_shopping_list",
                             {"id": list_id, "recipeId": recipe["id"]})
        s.check("removing a recipe from a list succeeds",
                lambda: require(not removed.is_error, removed.error))

    s.call("delete shopping list", "delete_shopping_list_by_id", {"id": list_id})
    s.forget_cleanup("delete_shopping_list_by_id", {"id": list_id})
    s.expect_error("deleted shopping list is gone", "get_shopping_list_by_id",
                   {"id": list_id}, contains=("404", "not found"))


@scenario("shopping", "shopping_item_crud_and_bulk",
          ["create_shopping_list", "create_shopping_item",
           "list_all_shopping_items", "get_shopping_item_by_id",
           "update_shopping_item", "delete_shopping_item_by_id",
           "bulk_create_shopping_items", "bulk_update_shopping_items",
           "bulk_delete_shopping_items", "delete_shopping_list_by_id"])
def shopping_item_crud_and_bulk(s: Scenario) -> None:
    shopping_list = shopping_list_fixture(s, "item-list")
    list_id = shopping_list["id"]
    note = s.fixture("shopping-item")

    created = s.call("create shopping item", "create_shopping_item", {
        "shoppingListId": list_id, "note": note, "quantity": 2,
        "display": note,
    })
    created_items = created.data.get("createdItems") or []
    item_id = str(created_items[0].get("id") or "") if created_items else ""
    s.check("shopping item create returns an id",
            lambda: require(bool(item_id), created.data))
    if not item_id:
        return
    s.own(item_id)
    s.cleanup("delete_shopping_item_by_id", {"id": item_id},
              "cleanup shopping item")

    found = find_by(s, "list_all_shopping_items", "id", item_id)
    s.check("shopping item appears in its list",
            lambda: require(found is not None, "missing"))
    got = s.call("get shopping item", "get_shopping_item_by_id",
                 {"id": item_id, "include_all_fields": True}).data
    s.check("shopping item note round-trips",
            lambda: require(got.get("note") == note, got.get("note")))

    s.call("update shopping item", "update_shopping_item", {
        "id": item_id, "shoppingListId": list_id,
        "note": note + "-updated", "checked": True,
    })
    after = s.call("get updated shopping item", "get_shopping_item_by_id",
                   {"id": item_id, "include_all_fields": True}).data
    s.check("shopping item update is persisted",
            lambda: require(after.get("note") == note + "-updated"
                            and after.get("checked") is True, after))

    bulk_notes = [s.fixture(f"bulk-item-{i}") for i in range(3)]
    bulk = s.call("bulk create shopping items", "bulk_create_shopping_items", {
        "items": [{"shoppingListId": list_id, "note": n, "display": n}
                  for n in bulk_notes],
    })
    bulk_items = s.items("bulk shopping items create decode", bulk)
    for item in bulk_items:
        if isinstance(item, dict) and item.get("id"):
            s.own(item["id"])
            s.cleanup("delete_shopping_item_by_id", {"id": item["id"]},
                      "cleanup bulk shopping item")
    created_items = s.call("list shopping items after bulk create",
                           "list_all_shopping_items", {"page": 1, "perPage": 200})
    created_values = s.items("bulk shopping items decode", created_items)
    ids = [item.get("id") for item in created_values
           if isinstance(item, dict) and item.get("note") in bulk_notes]
    s.check("bulk create makes every requested item",
            lambda: require(len(ids) == 3, f"created {len(ids)} of 3"))

    if ids:
        s.call("bulk update shopping items", "bulk_update_shopping_items", {
            "items": [{"id": item_id_, "checked": True} for item_id_ in ids],
        })
        updated_values = s.call("list shopping items after bulk update",
                                "list_all_shopping_items", {"page": 1, "perPage": 200})
        values = s.items("bulk shopping items update decode", updated_values)
        s.check("bulk update marks every item checked",
                lambda: require(all(item.get("checked") is True
                                    for item in values if item.get("id") in ids),
                                "an item was not updated"))
        deleted = s.call("bulk delete shopping items", "bulk_delete_shopping_items",
                         {"ids": ids})
        for item_id_ in ids:
            s.forget_cleanup("delete_shopping_item_by_id", {"id": item_id_})
        s.check("bulk delete reports the number deleted",
                lambda: require(deleted.data.get("count") in (3, None) or
                                len(deleted.data.get("ids") or []) == 3,
                                deleted.data))

    s.call("delete shopping item", "delete_shopping_item_by_id", {"id": item_id})
    s.forget_cleanup("delete_shopping_item_by_id", {"id": item_id})
    s.expect_error("deleted shopping item is gone", "get_shopping_item_by_id",
                   {"id": item_id}, contains=("404", "not found"))
