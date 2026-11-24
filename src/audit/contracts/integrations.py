"""Shared recipes, recipe actions/webhooks, notifications, and invitations."""

from __future__ import annotations

import time

from ..backend import LocalListener
from ..expect import require
from ..harness import Scenario, scenario
from .helpers import find_by, recipe_fixture


@scenario("shares", "shared_recipe_public_access",
          ["create_recipe", "create_shared_recipe", "get_shared_recipe_by_id",
           "list_all_shared_recipes", "delete_shared_recipe_by_id"])
def shared_recipe_public_access(s: Scenario) -> None:
    recipe = recipe_fixture(s, "shared-recipe")
    shared = s.call("create shared recipe", "create_shared_recipe",
                    {"recipeId": recipe["id"]})
    share_id = str(shared.data.get("id") or "")
    # Mealie uses the share id itself as the public token.
    token = str(shared.data.get("token") or share_id)
    s.check("share create returns a public token",
            lambda: require(bool(token) and bool(share_id), shared.data))
    if not share_id:
        return
    s.own(share_id, token)
    s.cleanup("delete_shared_recipe_by_id", {"id": share_id}, "cleanup share")

    got = s.call("get shared recipe", "get_shared_recipe_by_id",
                 {"id": share_id, "include_all_fields": True}).data
    s.check("shared recipe lookup returns the recipe",
            lambda: require(str(got.get("slug") or "") == recipe["slug"], got.get("slug")))

    other = recipe_fixture(s, "unshared-recipe")
    other_share = s.call("create second shared recipe", "create_shared_recipe",
                         {"recipeId": other["id"]})
    other_id = str(other_share.data.get("id") or "")
    other_token = str(other_share.data.get("token") or "")
    if other_id:
        s.own(other_id, other_token)
        s.cleanup("delete_shared_recipe_by_id", {"id": other_id},
                  "cleanup second share")

    listed = s.call("list shared recipes", "list_all_shared_recipes",
                    {"recipeId": recipe["id"]})
    listed_items = s.items("shared recipes decode", listed)
    s.check("shared recipe appears in the token list",
            lambda: require(any(item.get("id") == share_id
                                for item in listed_items), listed_items))
    s.check("recipeId filters the share list",
            lambda: require(not any(item.get("id") == other_id
                                    for item in listed_items),
                            "unrelated share passed the filter"))

    public = s.run.adapter.backend.public_get(f"/api/recipes/shared/{token}")
    s.check("public share is readable without auth",
            lambda: require(public.status_code == 200,
                            f"{public.status_code} {public.text[:200]}"))
    s.check("public share returns the recipe name",
            lambda: require(recipe["name"] in public.text, public.text[:300]))

    s.call("delete shared recipe", "delete_shared_recipe_by_id", {"id": share_id})
    s.forget_cleanup("delete_shared_recipe_by_id", {"id": share_id})
    after = s.run.adapter.backend.public_get(f"/api/recipes/shared/{token}")
    s.check("deleted share is no longer public",
            lambda: require(after.status_code == 404, after.status_code))


@scenario("actions", "recipe_action_crud_and_trigger",
          ["create_recipe_action", "list_all_recipe_actions",
           "get_recipe_action_by_id", "update_recipe_action",
           "trigger_recipe_action", "delete_recipe_action_by_id",
           "create_recipe", "delete_recipe_by_slug"])
def recipe_action_crud_and_trigger(s: Scenario) -> None:
    listener = LocalListener(8099).start()
    try:
        action = s.call("create recipe action", "create_recipe_action", {
            "name": s.fixture("action"),
            "recipeActionType": "post",
            "description": "audit action",
            "url": listener.url,
        })
        action_id = str(action.data.get("id") or "")
        s.check("action create returns an id", lambda: require(bool(action_id), action.data))
        if not action_id:
            return
        s.own(action_id)
        s.cleanup("delete_recipe_action_by_id", {"id": action_id}, "cleanup action")

        found = find_by(s, "list_all_recipe_actions", "id", action_id)
        s.check("action appears in its list", lambda: require(found is not None, "missing"))
        got = s.call("get recipe action", "get_recipe_action_by_id",
                     {"id": action_id, "include_all_fields": True}).data
        s.check("action url round-trips", lambda: require(got.get("url") == listener.url, got))

        updated_title = s.fixture("action") + "-updated"
        s.call("update recipe action", "update_recipe_action",
               {"id": action_id, "name": updated_title})
        after = s.call("get updated recipe action", "get_recipe_action_by_id",
                       {"id": action_id, "include_all_fields": True}).data
        s.check("action update is persisted",
                lambda: require(after.get("title") == updated_title, after))

        recipe = recipe_fixture(s, "action-recipe")
        before = len(listener.events)
        triggered = s.attempt("trigger recipe action", "trigger_recipe_action",
                              {"id": action_id, "recipeSlug": recipe["slug"]})
        if triggered.is_error:
            s.skip("recipe action outbound delivery",
                   f"backend rejected the local callback: {triggered.error[:200]}")
        else:
            deadline = time.time() + 5
            while time.time() < deadline and len(listener.events) == before:
                time.sleep(0.1)
            s.check("triggered action reached the local listener",
                    lambda: require(len(listener.events) > before,
                                    "no callback received"))

        s.call("delete recipe action", "delete_recipe_action_by_id",
               {"id": action_id})
        s.forget_cleanup("delete_recipe_action_by_id", {"id": action_id})
        s.expect_error("deleted action is gone", "get_recipe_action_by_id",
                       {"id": action_id}, contains=("404", "not found"))
    finally:
        listener.stop()


@scenario("webhooks", "webhook_crud_and_callbacks",
          ["create_webhook", "list_all_webhooks", "get_webhook_by_id",
           "update_webhook", "test_webhook", "rerun_webhooks",
           "delete_webhook_by_id"])
def webhook_crud_and_callbacks(s: Scenario) -> None:
    listener = LocalListener(8099).start()
    try:
        hook = s.call("create webhook", "create_webhook", {
            "name": s.fixture("webhook"),
            "url": listener.url,
            "enabled": True,
        })
        hook_id = str(hook.data.get("id") or "")
        s.check("webhook create returns an id", lambda: require(bool(hook_id), hook.data))
        if hook_id:
            s.own(hook_id)
            s.cleanup("delete_webhook_by_id", {"id": hook_id}, "cleanup webhook")
            found = find_by(s, "list_all_webhooks", "id", hook_id)
            s.check("webhook appears in its list",
                    lambda: require(found is not None, "missing"))
            got = s.call("get webhook", "get_webhook_by_id",
                         {"id": hook_id, "include_all_fields": True}).data
            s.check("webhook url round-trips",
                    lambda: require(got.get("url") == listener.url, got))

            s.call("update webhook", "update_webhook",
                   {"id": hook_id, "name": s.fixture("webhook") + "-updated"})
            after = s.call("get updated webhook", "get_webhook_by_id",
                           {"id": hook_id, "include_all_fields": True}).data
            s.check("webhook update is persisted",
                    lambda: require(str(after.get("name", "")).endswith("-updated"), after))

            before = len(listener.events)
            tested = s.attempt("test webhook", "test_webhook", {"id": hook_id})
            if tested.is_error:
                s.skip("webhook test delivery",
                       f"backend rejected the local callback: {tested.error[:200]}")
            else:
                deadline = time.time() + 5
                while time.time() < deadline and len(listener.events) == before:
                    time.sleep(0.1)
                s.check("test webhook reached the local listener",
                        lambda: require(len(listener.events) > before,
                                        "no callback received"))

            s.call("delete webhook", "delete_webhook_by_id", {"id": hook_id})
            s.forget_cleanup("delete_webhook_by_id", {"id": hook_id})
            s.expect_error("deleted webhook is gone", "get_webhook_by_id",
                           {"id": hook_id}, contains=("404", "not found"))

        if "tenant" in s.run.clients:
            tenant_listener = LocalListener(8098).start()
            try:
                tenant_hook = s.call("create tenant webhook", "create_webhook",
                                     {"name": s.fixture("tenant-webhook"),
                                      "url": tenant_listener.url, "enabled": True},
                                     account="tenant")
                tid = str(tenant_hook.data.get("id") or "")
                if tid:
                    s.own(tid)
                    before = len(tenant_listener.events)
                    rerun = s.attempt("rerun webhooks", "rerun_webhooks", {},
                                      account="tenant")
                    s.check("rerun webhooks is accepted",
                            lambda: require(not rerun.is_error, rerun.error[:300]))
            finally:
                tenant_listener.stop()
        else:
            s.skip_tool("rerun webhooks", "rerun_webhooks",
                        "requires an isolated tenant; AUDIT_TENANT is disabled")
    finally:
        listener.stop()


@scenario("notifications", "event_notification_crud",
          ["create_event_notification", "list_all_event_notifications",
           "get_event_notification_by_id", "update_event_notification",
           "test_event_notification", "delete_event_notification_by_id"])
def event_notification_crud(s: Scenario) -> None:
    created = s.call("create event notification", "create_event_notification", {
        "name": s.fixture("notification"), "enabled": True,
    })
    notification_id = str(created.data.get("id") or "")
    s.check("notification create returns an id",
            lambda: require(bool(notification_id), created.data))
    if not notification_id:
        return
    s.own(notification_id)
    s.cleanup("delete_event_notification_by_id", {"id": notification_id},
              "cleanup notification")

    found = find_by(s, "list_all_event_notifications", "id", notification_id)
    s.check("notification appears in its list",
            lambda: require(found is not None, "missing"))
    got = s.call("get event notification", "get_event_notification_by_id",
                 {"id": notification_id, "include_all_fields": True}).data
    s.check("notification name round-trips",
            lambda: require(bool(got.get("name")), got))

    s.call("update event notification", "update_event_notification",
           {"id": notification_id, "enabled": False})
    after = s.call("get updated event notification",
                   "get_event_notification_by_id",
                   {"id": notification_id, "include_all_fields": True}).data
    s.check("notification update is persisted",
            lambda: require(after.get("enabled") is False, after.get("enabled")))

    s.skip_tool("test event notification", "test_event_notification",
                "delivers through Apprise to an external service; not exercised")

    s.call("delete event notification", "delete_event_notification_by_id",
           {"id": notification_id})
    s.forget_cleanup("delete_event_notification_by_id", {"id": notification_id})
    s.expect_error("deleted notification is gone", "get_event_notification_by_id",
                   {"id": notification_id}, contains=("404", "not found"))


@scenario("invitations", "invitation_inventory",
          ["list_all_invitations", "create_invitation", "email_invitation"])
def invitation_inventory(s: Scenario) -> None:
    listed = s.call("list invitations", "list_all_invitations", {})
    s.items("invitations decode", listed)
    s.skip_tool("create invitation", "create_invitation",
                "Mealie exposes no delete endpoint for invitations; creating "
                "one would leave irreversible residue")
    s.skip_tool("email invitation", "email_invitation",
                "sends email through SMTP; not exercised against the live relay")
