"""User self-service, group/household, and admin contracts."""

from __future__ import annotations

from ..expect import require
from ..harness import Scenario, scenario
from .helpers import find_by, recipe_fixture


@scenario("user_self", "profile_ratings_and_favorites",
          ["get_user_profile", "set_recipe_rating",
           "get_user_rating_for_recipe", "list_user_ratings",
           "add_recipe_favorite", "list_user_favorites",
           "remove_recipe_favorite", "create_recipe",
           "delete_recipe_by_slug"])
def profile_ratings_and_favorites(s: Scenario) -> None:
    profile = s.call("get user profile", "get_user_profile", {}).data
    s.check("profile returns the authenticated user",
            lambda: require(profile.get("username") == s.run.adapter.profile.get("username"),
                            profile.get("username")))
    s.check("default profile hides token metadata",
            lambda: require("tokens" not in profile and "cacheKey" not in profile,
                            sorted(profile)))
    full = s.call("get full user profile", "get_user_profile",
                  {"include_all_fields": True}).data
    s.check("full profile is still a valid user object",
            lambda: require(bool(full.get("username")), full))

    recipe = recipe_fixture(s, "rating-recipe")
    user_id = str(profile.get("id") or "")
    s.check("profile exposes a user id", lambda: require(bool(user_id), profile))

    s.call("set recipe rating", "set_recipe_rating",
           {"userId": user_id, "slug": recipe["slug"], "rating": 4})
    rating = s.call("get rating for recipe", "get_user_rating_for_recipe",
                    {"recipeId": recipe["id"]}).data
    s.check("rating round-trips",
            lambda: require(rating.get("rating") == 4, rating))
    ratings = s.call("list user ratings", "list_user_ratings", {})
    rating_items = s.items("ratings decode", ratings)
    s.check("rating appears in the user's ratings",
            lambda: require(any(item.get("recipeId") == recipe["id"]
                                for item in rating_items), rating_items))

    s.call("add recipe favorite", "add_recipe_favorite",
           {"userId": user_id, "slug": recipe["slug"]})
    favorites = s.call("list user favorites", "list_user_favorites", {})
    favorite_items = s.items("favorites decode", favorites)
    s.check("favorite appears in the user's favorites",
            lambda: require(any(item.get("recipeId") == recipe["id"]
                                for item in favorite_items), favorite_items))
    s.call("remove recipe favorite", "remove_recipe_favorite",
           {"userId": user_id, "slug": recipe["slug"]})
    favorites_after = s.call("list user favorites after removal",
                             "list_user_favorites", {})
    favorite_values = s.items("favorites after removal decode", favorites_after)
    s.check("removed favorite disappears",
            lambda: require(not any(item.get("recipeId") == recipe["id"]
                                    for item in favorite_values), favorite_values))


@scenario("group_household", "tenant_scoped_reads",
          ["get_group_info", "get_group_preferences", "get_group_storage",
           "list_group_members", "get_group_member", "list_households",
           "get_household", "get_household_info", "get_household_recipe",
           "list_household_members", "get_household_preferences",
           "get_household_statistics", "create_recipe",
           "delete_recipe_by_slug"])
def tenant_scoped_reads(s: Scenario) -> None:
    profile = s.run.adapter.profile
    group = s.call("get group info", "get_group_info", {}).data
    s.check("group info returns the caller's group",
            lambda: require(group.get("slug") == profile.get("groupSlug"), group.get("slug")))
    prefs = s.call("get group preferences", "get_group_preferences", {}).data
    s.check("group preferences are an object",
            lambda: require(isinstance(prefs, dict), prefs))
    storage = s.call("get group storage", "get_group_storage", {}).data
    s.check("group storage reports usage",
            lambda: require(isinstance(storage, dict), storage))

    members = s.call("list group members", "list_group_members", {})
    member_items = s.items("group members decode", members)
    s.check("group members include the caller",
            lambda: require(any(item.get("username") == profile.get("username")
                                for item in member_items), member_items))
    member = s.call("get group member", "get_group_member",
                    {"usernameOrId": profile.get("username")}).data
    s.check("get group member returns the caller",
            lambda: require(member.get("username") == profile.get("username"), member))

    households = s.call("list households", "list_households", {})
    household_items = s.items("households decode", households)
    s.check("household list is non-empty",
            lambda: require(bool(household_items), household_items))
    household = s.call("get household", "get_household",
                       {"householdSlug": profile.get("householdSlug")}).data
    s.check("get household returns the caller's household",
            lambda: require(household.get("slug") == profile.get("householdSlug"),
                            household.get("slug")))
    info = s.call("get household info", "get_household_info", {}).data
    s.check("household info is an object",
            lambda: require(isinstance(info, dict), info))
    prefs = s.call("get household preferences", "get_household_preferences", {}).data
    s.check("household preferences are an object",
            lambda: require(isinstance(prefs, dict), prefs))
    stats = s.call("get household statistics", "get_household_statistics", {}).data
    s.check("household statistics are an object",
            lambda: require(isinstance(stats, dict), stats))

    recipe = recipe_fixture(s, "household-recipe")
    household_recipe = s.call("get household recipe", "get_household_recipe",
                              {"recipeSlug": recipe["slug"]}).data
    s.check("household recipe lookup returns the fixture",
            lambda: require(str(household_recipe.get("recipeId") or "") == recipe["id"],
                            household_recipe))
    members = s.call("list household members", "list_household_members", {})
    member_values = s.items("household members decode", members)
    s.check("household members include the caller",
            lambda: require(any(item.get("username") == profile.get("username")
                                for item in member_values), member_values))


@scenario("group_household", "tenant_preference_and_permission_updates",
          ["get_group_preferences", "update_group_preferences",
           "get_household_preferences", "update_household_preferences",
           "set_household_permissions", "get_user_profile"])
def tenant_preference_and_permission_updates(s: Scenario) -> None:
    tenant = s.run.tenant
    if not tenant or "tenant" not in s.run.clients:
        s.skip_tool("update group preferences", "update_group_preferences",
                    "requires an isolated audit tenant")
        s.skip_tool("update household preferences", "update_household_preferences",
                    "requires an isolated audit tenant")
        s.skip_tool("set household permissions", "set_household_permissions",
                    "requires an isolated audit tenant")
        return

    group = s.call("tenant group preferences", "get_group_preferences", {},
                   account="tenant").data
    original_private = bool(group.get("privateGroup"))
    s.call("toggle tenant group privacy", "update_group_preferences",
           {"privateGroup": not original_private}, account="tenant")
    changed = s.call("tenant group preferences after update",
                     "get_group_preferences", {}, account="tenant").data
    s.check("group preference update is persisted",
            lambda: require(changed.get("privateGroup") is (not original_private),
                            changed.get("privateGroup")))
    s.call("restore tenant group privacy", "update_group_preferences",
           {"privateGroup": original_private}, account="tenant")

    household = s.call("tenant household preferences", "get_household_preferences", {},
                       account="tenant").data
    original_hh = bool(household.get("privateHousehold"))
    s.call("toggle tenant household privacy", "update_household_preferences",
           {"privateHousehold": not original_hh}, account="tenant")
    changed_hh = s.call("tenant household preferences after update",
                        "get_household_preferences", {}, account="tenant").data
    s.check("household preference update is persisted",
            lambda: require(changed_hh.get("privateHousehold") is (not original_hh),
                            changed_hh.get("privateHousehold")))
    s.call("restore tenant household privacy", "update_household_preferences",
           {"privateHousehold": original_hh}, account="tenant")

    member_id = str(tenant.get("member_user_id") or "")
    s.call("set household permissions", "set_household_permissions",
           {"userId": member_id, "canManage": True, "canManageHousehold": True,
            "canInvite": False, "canOrganize": True}, account="tenant")
    member = s.call("get member after permissions", "get_user_by_id",
                    {"userId": member_id, "include_all_fields": True}).data
    s.check("permission update is persisted",
            lambda: require(member.get("canOrganize") is True
                            and member.get("canManage") is True, member))


def _delete_group_tree(s: Scenario, group_id: str) -> list[str]:
    """Delete every household in a group, then the group itself."""
    errors: list[str] = []
    group_call = s.run.client.call("get_group_by_id", {"groupId": group_id})
    if group_call.is_error and "404" in group_call.error:
        return errors
    households = (group_call.data.get("households") or []
                  if not group_call.is_error else [])
    for record in households:
        if record.get("id"):
            call = s.run.client.call("delete_household",
                                     {"householdId": record["id"]})
            if call.is_error and "not found" not in call.error.lower():
                errors.append(f"household {record['id']}: {call.error[:120]}")
    call = s.run.client.call("delete_group", {"groupId": group_id})
    if call.is_error and "not found" not in call.error.lower():
        errors.append(f"group: {call.error[:160]}")
    return errors


@scenario("admin", "admin_entities_crud",
          ["create_group", "list_groups", "get_group_by_id", "update_group",
           "delete_group", "create_household", "list_all_households",
           "get_household_by_id", "update_household", "delete_household",
           "create_user", "list_users", "get_user_by_id", "update_user",
           "delete_user"])
def admin_entities_crud(s: Scenario) -> None:
    group_name = s.fixture("admin-group")
    group = s.call("create admin group", "create_group", {"name": group_name}).data
    group_id = str(group.get("id") or "")
    s.check("admin group create returns an id", lambda: require(bool(group_id), group))
    if not group_id:
        return
    s.own(group_id)
    s.cleanup_fn("cleanup admin group tree",
                 lambda: _delete_group_tree(s, group_id))

    found_group = find_by(s, "list_groups", "id", group_id)
    s.check("admin group appears in the list",
            lambda: require(found_group is not None, "missing"))
    got_group = s.call("get admin group", "get_group_by_id",
                       {"groupId": group_id}).data
    s.check("admin group name round-trips",
            lambda: require(got_group.get("name") == group_name, got_group.get("name")))
    for record in got_group.get("households") or []:
        if record.get("id"):
            s.own(record["id"])
            s.cleanup("delete_household", {"householdId": record["id"]},
                      "cleanup default group household")

    updated_group = group_name + "-updated"
    s.call("update admin group", "update_group",
           {"groupId": group_id, "name": updated_group})
    after_group = s.call("get updated admin group", "get_group_by_id",
                         {"groupId": group_id}).data
    s.check("admin group update is persisted",
            lambda: require(after_group.get("name") == updated_group,
                            after_group.get("name")))

    household_name = s.fixture("admin-household")
    household = s.call("create admin household", "create_household",
                       {"name": household_name, "groupId": group_id}).data
    household_id = str(household.get("id") or "")
    s.check("admin household create returns an id",
            lambda: require(bool(household_id), household))
    if not household_id:
        return
    s.own(household_id)
    s.cleanup("delete_household", {"householdId": household_id},
              "cleanup admin household")

    household_page = s.call("list admin households", "list_all_households",
                            {"page": 1, "perPage": 200})
    household_items = s.items("admin households decode", household_page)
    s.check("admin household appears in the list",
            lambda: require(any(item.get("id") == household_id
                                for item in household_items), "missing"))
    got_household = s.call("get admin household", "get_household_by_id",
                           {"householdId": household_id}).data
    s.check("admin household name round-trips",
            lambda: require(got_household.get("name") == household_name,
                            got_household.get("name")))
    updated_household = household_name + "-updated"
    s.call("update admin household", "update_household",
           {"householdId": household_id, "name": updated_household,
            "groupId": group_id})
    after_household = s.call("get updated admin household", "get_household_by_id",
                             {"householdId": household_id}).data
    s.check("admin household update is persisted",
            lambda: require(after_household.get("name") == updated_household,
                            after_household.get("name")))

    username = f"mcpaudit_admin_{s.run.run_id}"
    user = s.call("create admin user", "create_user", {
        "username": username,
        "fullName": "MCP Audit User",
        "email": f"{username}@example.com",
        "password": f"AuditPass-{s.run.run_id}",
        "admin": False,
        "group": updated_group,
        "household": updated_household,
        "canOrganize": True,
    }).data
    user_id = str(user.get("id") or "")
    s.check("admin user create returns an id", lambda: require(bool(user_id), user))
    if not user_id:
        return
    s.own(user_id)
    s.cleanup("delete_user", {"userId": user_id}, "cleanup admin user")

    users = s.call("list admin users", "list_users",
                   {"page": 1, "perPage": 200})
    user_items = s.items("admin users decode", users)
    listed = next((item for item in user_items if item.get("id") == user_id), None)
    s.check("admin user appears in the list",
            lambda: require(listed is not None, "missing"))
    s.check("default user list hides token metadata",
            lambda: require(listed is not None
                            and "tokens" not in listed and "cacheKey" not in listed,
                            listed))
    gate = __import__("os").getenv("ALLOW_ALL_AGGREGATE", "false").lower() in (
        "1", "true", "yes"
    )
    full_users = s.call("list admin users with all fields", "list_users",
                        {"page": 1, "perPage": 200, "include_all_fields": True})
    full_items = s.items("full admin users decode", full_users)
    primary_id = str(s.run.adapter.profile.get("id") or "")
    primary_full = next((item for item in full_items if item.get("id") == primary_id), None)
    if gate:
        s.check("all-fields user list exposes token metadata when enabled",
                lambda: require(primary_full is not None and "tokens" in primary_full,
                                primary_full))
    else:
        s.check("aggregate user list keeps the privacy gate closed",
                lambda: require(primary_full is not None
                                and "tokens" not in primary_full
                                and "cacheKey" not in primary_full,
                                primary_full))
    primary_default = next((item for item in user_items if item.get("id") == primary_id), None)
    s.check("default user list hides the admin's token metadata",
            lambda: require(primary_default is not None
                            and "tokens" not in primary_default
                            and "cacheKey" not in primary_default,
                            primary_default))
    primary_single = s.call("get admin user with all fields", "get_user_by_id",
                            {"userId": primary_id,
                             "include_all_fields": True}).data
    s.check("single-record user get honors include_all_fields",
            lambda: require("tokens" in primary_single
                            and "cacheKey" in primary_single,
                            sorted(primary_single)))
    primary_single_default = s.call("get admin user default projection",
                                    "get_user_by_id", {"userId": primary_id}).data
    s.check("single-record user get hides token metadata by default",
            lambda: require("tokens" not in primary_single_default
                            and "cacheKey" not in primary_single_default,
                            sorted(primary_single_default)))

    got_user = s.call("get admin user", "get_user_by_id",
                      {"userId": user_id}).data
    s.check("admin user name round-trips",
            lambda: require(got_user.get("username") == username,
                            got_user.get("username")))
    s.call("update admin user", "update_user", {
        "userId": user_id, "username": username,
        "fullName": "MCP Audit User Updated",
        "email": f"{username}@example.com",
        "group": updated_group, "household": updated_household,
        "canOrganize": True,
    })
    after_user = s.call("get updated admin user", "get_user_by_id",
                        {"userId": user_id}).data
    s.check("admin user update is persisted",
            lambda: require(after_user.get("fullName") == "MCP Audit User Updated",
                            after_user.get("fullName")))

    s.call("delete admin user", "delete_user", {"userId": user_id})
    s.forget_cleanup("delete_user", {"userId": user_id})
    s.expect_error("deleted admin user is gone", "get_user_by_id",
                   {"userId": user_id}, contains=("404", "not found"))

    s.call("delete admin household", "delete_household",
           {"householdId": household_id})
    s.forget_cleanup("delete_household", {"householdId": household_id})
    s.expect_error("deleted admin household is gone", "get_household_by_id",
                   {"householdId": household_id}, contains=("404", "not found"))

    # Remove the auto-created household, then the group itself.
    current = s.call("get admin group before delete", "get_group_by_id",
                     {"groupId": group_id}).data
    for record in current.get("households") or []:
        if record.get("id") and record["id"] != household_id:
            s.call("delete default group household", "delete_household",
                   {"householdId": record["id"]})
            s.forget_cleanup("delete_household", {"householdId": record["id"]})
    s.call("delete admin group", "delete_group", {"groupId": group_id})
    s.expect_error("deleted admin group is gone", "get_group_by_id",
                   {"groupId": group_id}, contains=("404", "not found"))
