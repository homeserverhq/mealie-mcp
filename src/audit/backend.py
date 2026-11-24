"""Direct Mealie REST client used for truth checks and fixture safety.

The audit's MCP client observes what a consumer sees. This backend client is
used only for independent verification: record counts, ID snapshots, audit
tenant setup, public share checks, and fixture-prefix residue.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

RESOURCES: dict[str, dict[str, Any]] = {
    "recipe": {"path": "/api/recipes", "fields": ("name", "slug")},
    "category": {"path": "/api/organizers/categories", "fields": ("name", "slug")},
    "tag": {"path": "/api/organizers/tags", "fields": ("name", "slug")},
    "tool": {"path": "/api/organizers/tools", "fields": ("name", "slug")},
    "food": {"path": "/api/foods", "fields": ("name", "slug")},
    "unit": {"path": "/api/units", "fields": ("name", "abbreviation")},
    "comment": {"path": "/api/comments", "fields": ("text",)},
    "cookbook": {"path": "/api/households/cookbooks", "fields": ("name", "slug")},
    "mealplan": {"path": "/api/households/mealplans", "fields": ("title", "text")},
    "mealplan_rule": {"path": "/api/households/mealplans/rules", "fields": ("day",)},
    "shopping_list": {"path": "/api/households/shopping/lists", "fields": ("name",)},
    "shopping_item": {"path": "/api/households/shopping/items", "fields": ("note", "display")},
    "label": {"path": "/api/groups/labels", "fields": ("name",)},
    "timeline_event": {"path": "/api/recipes/timeline/events", "fields": ("message", "subject")},
    "shared_recipe": {"path": "/api/shared/recipes", "fields": (), "paginated": False},
    "recipe_action": {"path": "/api/households/recipe-actions", "fields": ("title", "name")},
    "event_notification": {"path": "/api/households/events/notifications", "fields": ("name",)},
    "webhook": {"path": "/api/households/webhooks", "fields": ("name", "url")},
    "invitation": {"path": "/api/households/invitations", "fields": (), "paginated": False},
    "user": {"path": "/api/admin/users", "fields": ("username", "fullName", "email")},
    "group": {"path": "/api/admin/groups", "fields": ("name", "slug")},
    "household": {"path": "/api/admin/households", "fields": ("name", "slug")},
}


class LocalListener:
    """Tiny HTTP listener used to verify outbound webhook/action calls."""

    def __init__(self, port: int = 8099):
        self.port = port
        self.events: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _handler(self):
        events = self.events

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("content-length", "0") or 0)
                body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
                events.append({"path": self.path, "body": body[:2000]})
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def do_GET(self) -> None:  # noqa: N802
                events.append({"path": self.path, "body": ""})
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args: Any) -> None:
                return

        return Handler

    def start(self) -> "LocalListener":
        self._server = ThreadingHTTPServer(("0.0.0.0", self.port), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    @property
    def url(self) -> str:
        return os.getenv(
            "MEALIE_AUDIT_CALLBACK_URL",
            f"http://{os.getenv('AUDIT_CONTAINER_NAME', 'mealie-mcp-audit')}:{self.port}/hook",
        )


def _total(payload: Any) -> int:
    if isinstance(payload, dict):
        value = payload.get("total")
        return value if isinstance(value, int) else len(payload.get("items") or [])
    if isinstance(payload, list):
        return len(payload)
    return 0


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return [item for item in (payload.get("items") or []) if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


class MealieBackend:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("MEALIE_BASE_URL", "")).rstrip("/")
        self.token = token or os.getenv("API_KEY", "") or os.getenv("MEALIE_API_KEY", "")
        if not self.base_url:
            raise SystemExit("Set MEALIE_BASE_URL before running the audit.")
        if not self.token:
            raise SystemExit("Set API_KEY (or MEALIE_API_KEY) before running the audit.")
        self.client = httpx.Client(timeout=60.0)

    def _headers(self, token: str | None = None) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token or self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, token: str | None = None,
                 **kwargs: Any) -> httpx.Response:
        response = None
        for _ in range(4):
            response = self.client.request(
                method, f"{self.base_url}{path}", headers=self._headers(token),
                **kwargs,
            )
            if response.status_code != 429:
                break
            try:
                retry_after = float(response.headers.get("retry-after", "5"))
            except (TypeError, ValueError):
                retry_after = 5.0
            time.sleep(max(1.0, min(retry_after, 30.0)))
        if response is None:
            raise RuntimeError(f"{method} {path} produced no response")
        if response.status_code >= 400:
            raise RuntimeError(
                f"{method} {path} failed: {response.status_code} {response.text[:300]}"
            )
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"text": response.text}

    # -- reads -------------------------------------------------------------

    def list_page(self, resource: str, page: int = 1, per_page: int = 200,
                  **params: Any) -> dict[str, Any]:
        spec = RESOURCES[resource]
        query = dict(params)
        if spec.get("paginated", True):
            query.update({"page": page, "perPage": per_page})
        response = self._request("GET", spec["path"], params=query)
        payload = self._json(response)
        return {
            "items": _items(payload),
            "total": _total(payload),
            "payload": payload,
        }

    def list_all(self, resource: str, **params: Any) -> list[dict[str, Any]]:
        spec = RESOURCES[resource]
        if not spec.get("paginated", True):
            return _items(self._json(self._request("GET", spec["path"], params=params)))
        items: list[dict[str, Any]] = []
        page = 1
        while page <= 50:
            result = self.list_page(resource, page, 200, **params)
            items.extend(result["items"])
            if not result["items"] or len(items) >= result["total"]:
                break
            page += 1
        return items

    def count(self, resource: str, **params: Any) -> int:
        spec = RESOURCES[resource]
        if not spec.get("paginated", True):
            return len(self.list_all(resource, **params))
        return self.list_page(resource, 1, 1, **params)["total"]

    def get(self, path: str, token: str | None = None, **params: Any) -> Any:
        return self._json(self._request("GET", path, token=token, params=params))

    def get_by_id(self, resource: str, record_id: str) -> dict[str, Any] | None:
        path = f"{RESOURCES[resource]['path']}/{record_id}"
        try:
            payload = self.get(path)
        except RuntimeError as exc:
            if " 404 " in str(exc):
                return None
            raise
        if isinstance(payload, dict):
            if "id" in payload:
                return payload
            for value in payload.values():
                if isinstance(value, dict) and "id" in value:
                    return value
        return None

    # -- snapshots ---------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        ids: dict[str, list[str]] = {}
        names: dict[str, list[str]] = {}
        for resource, spec in RESOURCES.items():
            counted = self.count(resource)
            counts[resource] = counted
            if resource in ("user", "group", "household"):
                records = self.list_all(resource)
                ids[resource] = sorted(str(item.get("id")) for item in records if item.get("id"))
                names[resource] = sorted(
                    str(item.get(spec["fields"][0], "")) for item in records
                )
        return {"counts": counts, "ids": ids, "names": names}

    def residue(self, prefix: str) -> dict[str, Any]:
        found: dict[str, int] = {
            resource: 0 for resource, spec in RESOURCES.items()
            if spec.get("fields")
        }
        examples: dict[str, list[str]] = {}
        errors: dict[str, str] = {}
        needle = prefix.casefold()
        for resource, spec in RESOURCES.items():
            fields = spec.get("fields") or ()
            if not fields:
                continue
            try:
                items = self.list_all(resource)
            except Exception as exc:
                errors[resource] = str(exc)[:200]
                continue
            matches: list[str] = []
            for item in items:
                text = " | ".join(str(item.get(field, "")) for field in fields).casefold()
                if needle in text:
                    matches.append(
                        str(item.get("slug") or item.get("id") or item.get(fields[0], ""))
                    )
            if matches:
                found[resource] = len(matches)
                examples[resource] = matches[:5]
        return {"prefix": prefix, "counts": found, "examples": examples,
                "errors": errors}

    # -- tenant ------------------------------------------------------------

    def create_group(self, name: str) -> dict[str, Any]:
        response = self._request("POST", "/api/admin/groups", json={"name": name})
        return self._json(response)

    def create_household(self, name: str, group_id: str) -> dict[str, Any]:
        response = self._request(
            "POST", "/api/admin/households",
            json={"name": name, "groupId": group_id},
        )
        return self._json(response)

    def create_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", "/api/admin/users", json=payload)
        return self._json(response)

    def login(self, username: str, password: str) -> str:
        response = self.client.post(
            f"{self.base_url}/api/auth/token",
            data={"username": username, "password": password},
            headers={"Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"login failed: {response.status_code} {response.text[:200]}")
        return str(response.json().get("access_token") or "")

    def self_profile(self, token: str) -> dict[str, Any]:
        payload = self.get("/api/users/self", token=token)
        return payload if isinstance(payload, dict) else {}

    def group(self, group_id: str) -> dict[str, Any]:
        payload = self.get(f"/api/admin/groups/{group_id}")
        return payload if isinstance(payload, dict) else {}

    def households(self) -> list[dict[str, Any]]:
        return self.list_all("household")

    def delete_path(self, path: str) -> None:
        self._request("DELETE", path)

    def public_get(self, path: str) -> httpx.Response:
        return self.client.get(f"{self.base_url}{path}",
                               headers={"Accept": "application/json"})

    def close(self) -> None:
        self.client.close()
