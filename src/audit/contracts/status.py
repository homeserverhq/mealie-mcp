"""Status, auth, and public app-information contracts."""

from __future__ import annotations

from ..expect import require
from ..harness import Scenario, scenario
from ..mcp_client import AuditClient


@scenario("status", "health_and_auth",
          ["check_server_status", "list_all_categories"])
def health_and_auth(s: Scenario) -> None:
    status = s.call("check_server_status", "check_server_status").data
    s.check("valid credentials report connected",
            lambda: require(status.get("status") == "connected", status))
    s.check("valid credentials report the backend status",
            lambda: require(status.get("backend_response") == 200, status))
    s.check("status identifies the authenticated user",
            lambda: require(bool(status.get("username")), status))

    anonymous = AuditClient(token="", require_token=False)
    try:
        anon_status = anonymous.call("check_server_status", {}).data
        s.check("missing credentials are unauthenticated",
                lambda: require(anon_status.get("status") == "unauthenticated",
                                anon_status))
        anon_call = anonymous.call("list_all_categories", {"page": 1, "perPage": 1})
        s.check("missing credentials are rejected on a data call",
                lambda: require(anon_call.is_error, anon_call.text[:300]))
    finally:
        anonymous.close()

    invalid = AuditClient(token="not-a-valid-mealie-key", require_token=False)
    try:
        invalid_status = invalid.call("check_server_status", {}).data
        s.check("invalid credentials are not reported as connected",
                lambda: require(invalid_status.get("status") != "connected",
                                invalid_status))
        invalid_call = invalid.call("list_all_categories", {"page": 1, "perPage": 1})
        s.check("invalid credentials are rejected on a data call",
                lambda: require(invalid_call.is_error, invalid_call.text[:300]))
        s.check("invalid-token error does not leak the valid token",
                lambda: require(
                    s.run.client.token not in invalid_call.text,
                    "valid token appears in the error text",
                ))
    finally:
        invalid.close()

    tools = s.run.client.tools()
    s.check("tools/list is available without a data mutation",
            lambda: require(len(tools) == 175, f"got {len(tools)} tools"))


@scenario("status", "public_app_info",
          ["get_app_about", "get_app_startup_info", "get_app_theme"])
def public_app_info(s: Scenario) -> None:
    about = s.call("get app about", "get_app_about").data
    s.check("app about reports a production flag",
            lambda: require(isinstance(about.get("production"), bool), about))
    s.check("app about reports a version",
            lambda: require(str(about.get("version", "")).startswith("v"), about))

    startup = s.call("get app startup info", "get_app_startup_info").data
    s.check("startup info reports first-login state",
            lambda: require(isinstance(startup.get("isFirstLogin"), bool), startup))

    theme = s.call("get app theme", "get_app_theme").data
    s.check("theme exposes light and dark colours",
            lambda: require(
                any(key.startswith("light") for key in theme)
                and any(key.startswith("dark") for key in theme),
                sorted(theme),
            ))
