"""Comments, cookbooks, labels, and timeline contracts."""

from __future__ import annotations

from ..expect import require
from ..harness import Scenario, scenario
from .helpers import (cookbook_fixture, find_by, label_fixture,
                      recipe_fixture)


@scenario("comments", "comment_crud",
          ["create_recipe", "create_comment", "list_all_comments",
           "get_comment_by_id", "update_comment", "delete_comment_by_id",
           "delete_recipe_by_slug"])
def comment_crud(s: Scenario) -> None:
    recipe = recipe_fixture(s, "comment-recipe")
    text = s.fixture("comment-body")
    created = s.call("create comment", "create_comment",
                     {"recipeId": recipe["id"], "text": text})
    comment_id = str(created.data.get("id") or "")
    s.check("comment create returns an id", lambda: require(bool(comment_id), created.data))
    if not comment_id:
        return
    s.own(comment_id)
    s.cleanup("delete_comment_by_id", {"id": comment_id}, "cleanup comment")

    found = find_by(s, "list_all_comments", "id", comment_id)
    s.check("comment appears in its list", lambda: require(found is not None, "missing"))
    got = s.call("get comment", "get_comment_by_id",
                 {"id": comment_id, "include_all_fields": True}).data
    s.check("comment text round-trips",
            lambda: require(got.get("text") == text, got.get("text")))

    updated = text + "-updated"
    s.call("update comment", "update_comment",
           {"id": comment_id, "text": updated})
    after = s.call("get updated comment", "get_comment_by_id",
                   {"id": comment_id, "include_all_fields": True}).data
    s.check("comment update is persisted",
            lambda: require(after.get("text") == updated, after.get("text")))

    s.call("delete comment", "delete_comment_by_id", {"id": comment_id})
    s.forget_cleanup("delete_comment_by_id", {"id": comment_id})
    s.expect_error("deleted comment is gone", "get_comment_by_id",
                   {"id": comment_id}, contains=("404", "not found"))


@scenario("cookbooks", "cookbook_crud",
          ["create_cookbook", "list_all_cookbooks", "get_cookbook_by_id",
           "update_cookbook", "update_cookbooks", "delete_cookbook_by_id",
           "list_all_recipes"])
def cookbook_crud(s: Scenario) -> None:
    fixture = cookbook_fixture(s)
    book_id = fixture["id"]
    found = find_by(s, "list_all_cookbooks", "id", book_id)
    s.check("cookbook appears in its list", lambda: require(found is not None, "missing"))

    got = s.call("get cookbook", "get_cookbook_by_id",
                 {"id": book_id, "include_all_fields": True}).data
    s.check("cookbook name round-trips",
            lambda: require(got.get("name") == fixture["name"], got.get("name")))

    updated = fixture["name"] + "-updated"
    s.call("update cookbook", "update_cookbook",
           {"id": book_id, "name": updated})
    after = s.call("get updated cookbook", "get_cookbook_by_id",
                   {"id": book_id, "include_all_fields": True}).data
    s.check("cookbook update is persisted",
            lambda: require(after.get("name") == updated, after.get("name")))

    bulk_name = fixture["name"] + "-bulk"
    s.call("bulk update cookbooks", "update_cookbooks",
           {"cookbooks": [{"id": book_id, "name": bulk_name}]})
    after_bulk = s.call("get bulk-updated cookbook", "get_cookbook_by_id",
                        {"id": book_id, "include_all_fields": True}).data
    s.check("bulk cookbook update is persisted",
            lambda: require(after_bulk.get("name") == bulk_name,
                            after_bulk.get("name")))

    empty = s.call("list recipes in an empty cookbook", "list_all_recipes",
                   {"cookbook": fixture["data"].get("slug", ""), "page": 1, "perPage": 5})
    s.check("empty cookbook filter is a valid request",
            lambda: require(not empty.is_error, empty.error))

    s.call("delete cookbook", "delete_cookbook_by_id", {"id": book_id})
    s.forget_cleanup("delete_cookbook_by_id", {"id": book_id})
    s.expect_error("deleted cookbook is gone", "get_cookbook_by_id",
                   {"id": book_id}, contains=("404", "not found"))


@scenario("labels", "label_crud",
          ["create_label", "list_all_labels", "get_label_by_id",
           "update_label", "delete_label_by_id"])
def label_crud(s: Scenario) -> None:
    fixture = label_fixture(s)
    label_id = fixture["id"]
    found = find_by(s, "list_all_labels", "id", label_id)
    s.check("label appears in its list", lambda: require(found is not None, "missing"))

    got = s.call("get label", "get_label_by_id",
                 {"id": label_id, "include_all_fields": True}).data
    s.check("label colour round-trips",
            lambda: require(got.get("color") == "#336699", got.get("color")))

    updated = fixture["name"] + "-updated"
    s.call("update label", "update_label",
           {"id": label_id, "name": updated, "color": "#884422"})
    after = s.call("get updated label", "get_label_by_id",
                   {"id": label_id, "include_all_fields": True}).data
    s.check("label update is persisted",
            lambda: require(after.get("name") == updated and after.get("color") == "#884422",
                            after))

    s.call("delete label", "delete_label_by_id", {"id": label_id})
    s.forget_cleanup("delete_label_by_id", {"id": label_id})
    gone = s.run.client.call("get_label_by_id", {"id": label_id})
    s.check("deleted label is not readable",
            lambda: require(gone.is_error, "deleted label is still readable"))
    remaining = s.call("list labels after delete", "list_all_labels",
                       {"page": 1, "perPage": 200})
    remaining_items = s.items("labels after delete decode", remaining)
    s.check("deleted label is absent from the list",
            lambda: require(not any(item.get("id") == label_id
                                    for item in remaining_items),
                            "deleted label still listed"))


@scenario("timeline", "timeline_event_crud",
          ["create_recipe", "create_timeline_event", "list_all_timeline_events",
           "get_timeline_event_by_id", "update_timeline_event",
           "delete_timeline_event_by_id", "delete_recipe_by_slug"])
def timeline_event_crud(s: Scenario) -> None:
    recipe = recipe_fixture(s, "timeline-recipe")
    message = s.fixture("timeline-message")
    created = s.call("create timeline event", "create_timeline_event", {
        "recipeId": recipe["id"],
        "eventType": "info",
        "message": message,
    })
    event_id = str(created.data.get("id") or "")
    s.check("timeline event create returns an id",
            lambda: require(bool(event_id), created.data))
    if not event_id:
        return
    s.own(event_id)
    s.cleanup("delete_timeline_event_by_id", {"id": event_id},
              "cleanup timeline event")

    found = find_by(s, "list_all_timeline_events", "id", event_id)
    s.check("timeline event appears in its list",
            lambda: require(found is not None, "missing"))
    got = s.call("get timeline event", "get_timeline_event_by_id",
                 {"id": event_id, "include_all_fields": True}).data
    s.check("timeline message round-trips",
            lambda: require(got.get("subject") == message, got.get("subject")))

    updated = message + "-updated"
    s.call("update timeline event", "update_timeline_event",
           {"id": event_id, "message": updated})
    after = s.call("get updated timeline event", "get_timeline_event_by_id",
                   {"id": event_id, "include_all_fields": True}).data
    s.check("timeline update is persisted",
            lambda: require(after.get("subject") == updated, after.get("subject")))

    s.call("delete timeline event", "delete_timeline_event_by_id",
           {"id": event_id})
    s.forget_cleanup("delete_timeline_event_by_id", {"id": event_id})
    s.expect_error("deleted timeline event is gone", "get_timeline_event_by_id",
                   {"id": event_id}, contains=("404", "not found"))
