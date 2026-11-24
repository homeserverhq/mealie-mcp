"""Cross-tenant visibility and concurrent token isolation contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..expect import require
from ..harness import Scenario, scenario
from ..mcp_client import AuditClient
from .helpers import recipe_fixture


@scenario("isolation", "tenant_visibility",
          ["create_recipe", "get_recipe_by_slug", "delete_recipe_by_slug",
           "add_recipe_favorite", "remove_recipe_favorite",
           "list_user_favorites", "get_user_profile", "list_all_categories"])
def tenant_visibility(s: Scenario) -> None:
    primary = recipe_fixture(s, "primary-only")
    if not s.run.tenant or "tenant" not in s.run.clients:
        s.skip("cross-tenant recipe visibility",
               "AUDIT_TENANT is disabled; only the admin key is available")
    else:
        tenant_get = s.run.clients["tenant"].call(
            "get_recipe_by_slug", {"slug": primary["slug"]}
        )
        s.check("a private recipe is invisible to another tenant",
                lambda: require(tenant_get.is_error, tenant_get.text[:300]))

        tenant_recipe = recipe_fixture(s, "tenant-only", account="tenant")
        s.expect_error("primary get tenant recipe", "get_recipe_by_slug",
                       {"slug": tenant_recipe["slug"]},
                       contains=("404", "not found"))

        profile = s.run.adapter.profile
        user_id = str(profile.get("id") or "")
        s.call("favorite primary recipe", "add_recipe_favorite",
               {"userId": user_id, "slug": primary["slug"]})
        tenant_favorites = s.run.clients["tenant"].call("list_user_favorites", {})
        tenant_items = tenant_favorites.items()
        s.check("favorites are scoped to the caller",
                lambda: require(
                    not any(item.get("slug") == primary["slug"]
                            for item in tenant_items),
                    "another user's favorite leaked",
                ))
        s.call("unfavorite primary recipe", "remove_recipe_favorite",
               {"userId": user_id, "slug": primary["slug"]})

        tenant_profile = s.run.clients["tenant"].call("get_user_profile", {})
        s.check("tenant identity is distinct",
                lambda: require(
                    tenant_profile.data.get("username")
                    == s.run.tenant.get("username"),
                    tenant_profile.data.get("username"),
                ))


@scenario("isolation", "concurrent_token_isolation",
          ["list_all_categories"])
def concurrent_token_isolation(s: Scenario) -> None:
    valid = s.run.client
    invalid = AuditClient(token="not-a-valid-mealie-key", require_token=False)
    try:
        jobs = []
        with ThreadPoolExecutor(max_workers=12) as pool:
            for _ in range(6):
                jobs.append(("valid", pool.submit(
                    valid.call, "list_all_categories", {"page": 1, "perPage": 1})))
                jobs.append(("invalid", pool.submit(
                    invalid.call, "list_all_categories", {"page": 1, "perPage": 1})))
        valid_ok = 0
        invalid_ok = 0
        invalid_errors: list[str] = []
        for label, future in jobs:
            call = future.result()
            if label == "valid":
                if not call.is_error:
                    valid_ok += 1
            else:
                if call.is_error:
                    invalid_ok += 1
                    invalid_errors.append(call.text)
        s.check("valid token calls succeed under concurrency",
                lambda: require(valid_ok == 6, f"{valid_ok}/6 succeeded"))
        s.check("invalid token calls fail under concurrency",
                lambda: require(invalid_ok == 6, f"{invalid_ok}/6 rejected"))
        s.check("invalid-token errors never contain the valid token",
                lambda: require(all(valid.token not in text
                                    for text in invalid_errors),
                                "valid token appeared in an error"))
    finally:
        invalid.close()


@scenario("isolation", "same_group_visibility",
          ["create_user", "delete_user", "get_user_by_id",
           "create_recipe", "get_recipe_by_slug", "list_all_recipes",
           "delete_recipe_by_slug"])
def same_group_visibility(s: Scenario) -> None:
    """A recipe created by the integration user is visible in the group.

    Mealie's public/private flag controls logged-out access; logged-in members
    of the same group see each other's recipes. "My Recipes" is a UI filter by
    owner, not a privacy boundary.
    """
    profile = s.run.adapter.profile
    username = f"mcpaudit_vis_{s.run.run_id}"
    password = f"AuditPass-{s.run.run_id}"
    user = s.call("create same-group user", "create_user", {
        "username": username,
        "fullName": "MCP Audit Viewer",
        "email": f"{username}@example.com",
        "password": password,
        "admin": False,
        "group": profile.get("group") or "Home",
        "household": profile.get("household") or "Family",
        "canOrganize": True,
    }).data
    user_id = str(user.get("id") or "")
    s.check("same-group user has an id", lambda: require(bool(user_id), user))
    if not user_id:
        return
    s.own(user_id)
    s.cleanup("delete_user", {"userId": user_id}, "cleanup same-group user")

    token = s.run.adapter.backend.login(username, password)
    s.run.clients["same_group"] = AuditClient(
        url=s.run.client.url, token=token
    )

    private = recipe_fixture(s, "same-group-private",
                             settings={"public": False})
    full = s.call("get private recipe owner", "get_recipe_by_slug",
                  {"slug": private["slug"], "include_all_fields": True}).data
    s.check("private recipe is owned by the calling integration user",
            lambda: require(full.get("userId") == profile.get("id"),
                            full.get("userId")))

    same_get = s.run.clients["same_group"].call(
        "get_recipe_by_slug", {"slug": private["slug"], "include_all_fields": True}
    )
    s.check("same-group user can read a private recipe",
            lambda: require(not same_get.is_error, same_get.text[:300]))

    same_list = s.run.clients["same_group"].call(
        "list_all_recipes",
        {"page": 1, "perPage": 200, "search": private["name"]},
    )
    same_items = same_list.items() if not same_list.is_error else []
    s.check("same-group list includes the private recipe",
            lambda: require(any(item.get("slug") == private["slug"]
                                for item in same_items), same_items))

    other = recipe_fixture(s, "same-group-other", account="same_group")
    primary_get = s.call("primary reads same-group recipe", "get_recipe_by_slug",
                         {"slug": other["slug"], "include_all_fields": True})
    s.check("primary can read a same-group user's recipe",
            lambda: require(not primary_get.is_error, primary_get.text[:300]))

    s.call("delete same-group recipe", "delete_recipe_by_slug",
           {"slug": other["slug"]})
    s.forget_cleanup("delete_recipe_by_slug", {"slug": other["slug"]})
    s.call("delete same-group user", "delete_user", {"userId": user_id})
    s.forget_cleanup("delete_user", {"userId": user_id})
    s.expect_error("deleted same-group user is gone", "get_user_by_id",
                   {"userId": user_id}, contains=("404", "not found"))
