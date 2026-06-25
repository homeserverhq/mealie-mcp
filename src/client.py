import os
import re
import datetime as dt
from typing import Any, Optional
from urllib.parse import urlparse

import httpx


def _normalize_datetime(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}:\d{2}$', normalized):
        parsed = dt.datetime.fromisoformat(normalized)
        parsed = parsed.astimezone(dt.timezone.utc)
        return parsed.strftime('%Y-%m-%d %H:%M:%S')
    return value


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: _normalize_datetime(v) if isinstance(v, str) else v
            for k, v in payload.items()}


COMMON_FIELDS: dict[str, set[str]] = {
    "recipe": {"id", "name", "slug", "totalTime", "recipeCategory", "rating", "tags", "recipeServings"},
    "category": {"id", "name", "slug"},
    "tag": {"id", "name", "slug"},
    "tool": {"id", "name", "slug"},
    "food": {"id", "name", "slug", "description"},
    "unit": {"id", "name", "abbreviation", "description", "fraction"},
    "comment": {"id", "text", "recipeId", "userId"},
    "cookbook": {"id", "name", "description"},
    "mealplan": {"id", "date", "entryType", "title", "recipeId", "text"},
    "mealplan_rule": {"id", "day", "entryType"},
    "shopping_list": {"id", "name", "extras"},
    "shopping_item": {"id", "note", "display", "quantity", "checked", "shoppingListId", "foodId", "labelId", "unitId"},
    "label": {"id", "name", "color"},
    "timeline_event": {"id", "recipeId", "eventType", "message", "timestamp", "subject"},
    "shared_recipe": {"id", "recipeId", "token"},
    "recipe_action": {"id", "name", "actionType", "title", "url", "description"},
    "event_notification": {"id", "name", "enabled"},
    "webhook": {"id", "name", "url", "enabled", "scheduledTime"},
    "invitation": {"id", "uses", "createdAt", "groupId", "householdId"},
    "user": {"id", "username", "email", "fullName", "admin", "cacheKey"},
    "group": {"id", "name", "slug", "categories", "preferences"},
    "household": {"id", "name", "slug"},
    "member": {"id", "username", "userId", "email"},
    "rating": {"id", "recipeId", "userId", "rating", "recipeSlug"},
    "export": {"id", "filename", "type", "timestamp"},
}


def _filter_fields(data: Any, common_set: set[str]) -> Any:
    if isinstance(data, dict):
        if "items" in data and isinstance(data.get("items"), list):
            return {**data, "items": [_filter_fields(item, common_set) for item in data["items"]]}
        return _strip_nulls({k: v for k, v in data.items() if k in common_set})
    if isinstance(data, list):
        return [_filter_fields(item, common_set) for item in data]
    return data


def _strip_nulls(data: Any, strip_empty: bool = False) -> Any:
    if isinstance(data, dict):
        return {k: _strip_nulls(v, strip_empty) for k, v in data.items()
                if v is not None and (not strip_empty or v != "")}
    if isinstance(data, list):
        return [_strip_nulls(item, strip_empty) for item in data]
    return data


class MealieClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.getenv("MEALIE_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError(
                "Mealie URL required. Set MEALIE_BASE_URL env var "
                "or pass base_url."
            )
        self.public_url = os.getenv("MEALIE_PUBLIC_URL", "").rstrip("/") or self.base_url
        self.public_hostname = urlparse(self.public_url).netloc or urlparse(self.public_url).hostname or self.public_url

    def _get_headers(self, api_key: Optional[str] = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _replace_base_urls(self, data: Any) -> Any:
        """Replace internal hostname with public hostname in all URL strings."""
        if isinstance(data, dict):
            return {k: self._replace_base_urls(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._replace_base_urls(item) for item in data]
        if isinstance(data, str) and "://" in data:
            return re.sub(r'://[^/]+', f'://{self.public_hostname}', data)
        return data

    async def request(self, method: str, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._get_headers(api_key)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            if response.headers.get("content-type", "").startswith("application/json"):
                data = response.json()
                data = _strip_nulls(data, strip_empty=False) if data is not None else {}
                return self._replace_base_urls(data)
            return {"text": response.text}

    async def get(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("GET", path, api_key, **kwargs)

    async def post(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("POST", path, api_key, **kwargs)

    async def put(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("PUT", path, api_key, **kwargs)

    async def delete(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("DELETE", path, api_key, **kwargs)

    async def patch(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("PATCH", path, api_key, **kwargs)

    # =========================================================================
    # Recipes
    # =========================================================================

    async def get_all_recipes(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, search: str = "", cookbook: str = "", include_all_fields: bool = False) -> Any:
        params: dict[str, Any] = {"page": page, "perPage": perPage}
        if search:
            params["search"] = search
        if cookbook:
            params["cookbook"] = cookbook
        data = await self.get("/api/recipes", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def get_recipe_by_slug(self, slug: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/recipes/{slug}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def create_recipe(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes", api_key, json=_normalize_payload(payload))

    async def update_recipe(self, slug: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/api/recipes/{slug}", api_key, json=_normalize_payload(payload))
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def patch_recipe(self, slug: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.patch(f"/api/recipes/{slug}", api_key, json=_normalize_payload(payload))
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def delete_recipe_by_slug(self, slug: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/recipes/{slug}", api_key)

    async def duplicate_recipe(self, slug: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post(f"/api/recipes/{slug}/duplicate", api_key, json={})
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def update_recipe_last_made(self, slug: str, api_key: Optional[str] = None) -> Any:
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self.patch(f"/api/recipes/{slug}/last-made", api_key, json={"timestamp": now})

    async def get_recipe_suggestions(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/recipes/suggestions", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def create_recipe_from_url(self, url: str, api_key: Optional[str] = None, includeTags: bool = True, includeNutrition: bool = False) -> Any:
        payload: dict[str, Any] = {"url": url, "includeTags": includeTags, "includeNutrition": includeNutrition}
        return await self.post("/api/recipes/create/url", api_key, json=payload)

    async def create_recipe_from_url_bulk(self, urls: list[str], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes/create/url/bulk", api_key, json={"imports": [{"url": u} for u in urls]})

    async def create_recipe_from_html_or_json(self, data: str, api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes/create/html-or-json", api_key, json={"data": data})

    async def test_scrape_url(self, url: str, api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes/test-scrape-url", api_key, json={"url": url})

    async def scrape_recipe_image_url(self, slug: str, url: str, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/api/recipes/{slug}/image", api_key, json={"url": url})

    async def delete_recipe_image(self, slug: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/recipes/{slug}/image", api_key)

    async def get_recipe_export_formats(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/recipes/exports", api_key)

    async def export_recipe(self, slug: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/recipes/{slug}/exports", api_key, params={"template_name": "raw"})

    async def bulk_tag_recipes(self, recipes: list[str], tags: list[dict[str, Any]], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes/bulk-actions/tag", api_key, json={"recipes": recipes, "tags": tags})

    async def bulk_categorize_recipes(self, recipes: list[str], categories: list[dict[str, Any]], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes/bulk-actions/categorize", api_key, json={"recipes": recipes, "categories": categories})

    async def bulk_update_recipe_settings(self, recipes_slugs: list[str], settings: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes/bulk-actions/settings", api_key, json={"recipes": recipes_slugs, "settings": settings})

    async def bulk_delete_recipes(self, recipes: list[str], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes/bulk-actions/delete", api_key, json={"recipes": recipes})

    async def bulk_export_recipes(self, recipes: list[str], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/recipes/bulk-actions/export", api_key, json={"recipes": recipes})

    async def list_exports(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/recipes/bulk-actions/export", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["export"])
        return data

    async def purge_exports(self, api_key: Optional[str] = None) -> Any:
        return await self.delete("/api/recipes/bulk-actions/export/purge", api_key)

    # =========================================================================
    # Categories
    # =========================================================================

    async def get_all_categories(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/organizers/categories", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["category"])
        return data

    async def get_category_by_id(self, category_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/organizers/categories/{category_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["category"])
        return data

    async def get_category_by_slug(self, slug: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/organizers/categories/slug/{slug}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["category"])
        return data

    async def get_empty_categories(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/organizers/categories/empty", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["category"])
        return data

    async def create_category(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/organizers/categories", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["category"])
        return data

    async def update_category(self, category_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/api/organizers/categories/{category_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["category"])
        return data

    async def delete_category_by_id(self, category_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/organizers/categories/{category_id}", api_key)

    # =========================================================================
    # Tags
    # =========================================================================

    async def get_all_tags(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/organizers/tags", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def get_tag_by_id(self, tag_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/organizers/tags/{tag_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def get_tag_by_slug(self, slug: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/organizers/tags/slug/{slug}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def get_empty_tags(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/organizers/tags/empty", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def create_tag(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/organizers/tags", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def update_tag(self, tag_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/api/organizers/tags/{tag_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def delete_tag_by_id(self, tag_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/organizers/tags/{tag_id}", api_key)

    # =========================================================================
    # Tools
    # =========================================================================

    async def get_all_tools(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/organizers/tools", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tool"])
        return data

    async def get_tool_by_id(self, tool_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/organizers/tools/{tool_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tool"])
        return data

    async def get_tool_by_slug(self, slug: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/organizers/tools/slug/{slug}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tool"])
        return data

    async def create_tool(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/organizers/tools", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["tool"])
        return data

    async def update_tool(self, tool_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/api/organizers/tools/{tool_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["tool"])
        return data

    async def delete_tool_by_id(self, tool_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/organizers/tools/{tool_id}", api_key)

    # =========================================================================
    # Foods
    # =========================================================================

    async def get_all_foods(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/foods", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["food"])
        return data

    async def get_food_by_id(self, food_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/foods/{food_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["food"])
        return data

    async def create_food(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/foods", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["food"])
        return data

    def _strip_nested(self, d: dict[str, Any]) -> dict[str, Any]:
        skip_keys = {"createdAt", "updatedAt", "householdsWithIngredientFood"}
        result = {}
        for k, v in d.items():
            if k in skip_keys:
                continue
            if v is None:
                continue
            if isinstance(v, dict) and k in ("label", "recipe", "food", "unit", "group", "household"):
                continue
            result[k] = v
        return result

    async def update_food(self, food_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/foods/{food_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                merged.update(payload)
                data = await self.put(f"/api/foods/{food_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["food"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/foods/{food_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["food"])
        return data

    async def delete_food_by_id(self, food_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/foods/{food_id}", api_key)

    async def merge_foods(self, food_to_keep: str, food_to_merge: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put("/api/foods/merge", api_key, json={"fromFood": food_to_keep, "toFood": food_to_merge})
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["food"])
        return data

    # =========================================================================
    # Units
    # =========================================================================

    async def get_all_units(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/units", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["unit"])
        return data

    async def get_unit_by_id(self, unit_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/units/{unit_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["unit"])
        return data

    async def create_unit(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/units", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["unit"])
        return data

    async def update_unit(self, unit_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/units/{unit_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                merged.update(payload)
                data = await self.put(f"/api/units/{unit_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["unit"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/units/{unit_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["unit"])
        return data

    async def delete_unit_by_id(self, unit_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/units/{unit_id}", api_key)

    async def merge_units(self, unit_to_keep: str, unit_to_merge: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put("/api/units/merge", api_key, json={"fromUnit": unit_to_keep, "toUnit": unit_to_merge})
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["unit"])
        return data

    # =========================================================================
    # Comments
    # =========================================================================

    async def get_all_comments(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/comments", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["comment"])
        return data

    async def get_comment_by_id(self, comment_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/comments/{comment_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["comment"])
        return data

    async def create_comment(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/comments", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["comment"])
        return data

    async def update_comment(self, comment_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/comments/{comment_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                if "recipe" in existing and isinstance(existing["recipe"], dict) and "id" in existing["recipe"]:
                    merged["recipe"] = {"id": existing["recipe"]["id"]}
                merged.update(payload)
                data = await self.put(f"/api/comments/{comment_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["comment"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/comments/{comment_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["comment"])
        return data

    async def delete_comment_by_id(self, comment_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/comments/{comment_id}", api_key)

    # =========================================================================
    # Cookbooks
    # =========================================================================

    async def get_all_cookbooks(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/cookbooks", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["cookbook"])
        return data

    async def get_cookbook_by_id(self, cookbook_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/cookbooks/{cookbook_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["cookbook"])
        return data

    async def create_cookbook(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/households/cookbooks", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["cookbook"])
        return data

    async def update_cookbook(self, cookbook_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/households/cookbooks/{cookbook_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                merged.update(payload)
                data = await self.put(f"/api/households/cookbooks/{cookbook_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["cookbook"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/households/cookbooks/{cookbook_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["cookbook"])
        return data

    async def update_cookbooks(self, cookbooks: list[dict[str, Any]], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        enriched = []
        for cb in cookbooks:
            cb_id = cb.get("id")
            if cb_id:
                try:
                    existing = await self.get(f"/api/households/cookbooks/{cb_id}", api_key)
                    if isinstance(existing, dict):
                        merged = self._strip_nested(existing)
                        merged.update(cb)
                        enriched.append(merged)
                        continue
                except Exception:
                    pass
            enriched.append(cb)
        result = await self.put("/api/households/cookbooks", api_key, json=enriched)
        if isinstance(result, list):
            result = {"cookbooks": result}
        if not include_all_fields and isinstance(result, dict):
            result = _filter_fields(result, COMMON_FIELDS["cookbook"])
        return result

    async def delete_cookbook_by_id(self, cookbook_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/households/cookbooks/{cookbook_id}", api_key)

    # =========================================================================
    # Mealplans
    # =========================================================================

    async def get_all_mealplans(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, start_date: str = "", end_date: str = "", include_all_fields: bool = False) -> Any:
        params: dict[str, Any] = {"page": page, "perPage": perPage}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        data = await self.get("/api/households/mealplans", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["mealplan"])
        return data

    async def get_mealplan_by_id(self, mealplan_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/mealplans/{mealplan_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["mealplan"])
        return data

    async def get_todays_meals(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/mealplans/today", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["mealplan"])
        return data

    async def create_mealplan(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/households/mealplans", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["mealplan"])
        return data

    async def create_random_mealplan(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/households/mealplans/random", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["mealplan"])
        return data

    async def update_mealplan(self, mealplan_id: Any, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/households/mealplans/{mealplan_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                if "recipe" in existing and isinstance(existing["recipe"], dict) and "id" in existing["recipe"]:
                    merged["recipe"] = {"id": existing["recipe"]["id"]}
                merged.update(payload)
                data = await self.put(f"/api/households/mealplans/{mealplan_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["mealplan"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/households/mealplans/{mealplan_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["mealplan"])
        return data

    async def delete_mealplan_by_id(self, mealplan_id: Any, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/households/mealplans/{mealplan_id}", api_key)

    # =========================================================================
    # Mealplan Rules
    # =========================================================================

    async def get_all_mealplan_rules(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/mealplans/rules", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["mealplan_rule"])
        return data

    async def get_mealplan_rule_by_id(self, rule_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/mealplans/rules/{rule_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["mealplan_rule"])
        return data

    async def create_mealplan_rule(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/households/mealplans/rules", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["mealplan_rule"])
        return data

    async def update_mealplan_rule(self, rule_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/api/households/mealplans/rules/{rule_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["mealplan_rule"])
        return data

    async def delete_mealplan_rule_by_id(self, rule_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/households/mealplans/rules/{rule_id}", api_key)

    # =========================================================================
    # Shopping Lists
    # =========================================================================

    async def get_all_shopping_lists(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/shopping/lists", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shopping_list"])
        return data

    async def get_shopping_list_by_id(self, list_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/shopping/lists/{list_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shopping_list"])
        return data

    async def create_shopping_list(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/households/shopping/lists", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["shopping_list"])
        return data

    async def update_shopping_list(self, list_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/households/shopping/lists/{list_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                merged.update(payload)
                data = await self.put(f"/api/households/shopping/lists/{list_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["shopping_list"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/households/shopping/lists/{list_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["shopping_list"])
        return data

    async def delete_shopping_list_by_id(self, list_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/households/shopping/lists/{list_id}", api_key)

    async def update_shopping_list_label_settings(self, list_id: str, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.put(f"/api/households/shopping/lists/{list_id}/label-settings", api_key, json=[payload])

    async def add_recipe_to_shopping_list(self, list_id: str, recipe_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post(f"/api/households/shopping/lists/{list_id}/recipe", api_key, json=[{"recipeId": recipe_id}])
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["shopping_list"])
        return data

    async def remove_recipe_from_shopping_list(self, list_id: str, recipe_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post(f"/api/households/shopping/lists/{list_id}/recipe/{recipe_id}/delete", api_key)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["shopping_list"])
        return data

    # =========================================================================
    # Shopping Items
    # =========================================================================

    async def get_all_shopping_items(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/shopping/items", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shopping_item"])
        return data

    async def get_shopping_item_by_id(self, item_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/shopping/items/{item_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shopping_item"])
        return data

    async def create_shopping_item(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/households/shopping/items", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["shopping_item"])
        return data

    async def update_shopping_item(self, item_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/api/households/shopping/items/{item_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["shopping_item"])
        return data

    async def bulk_create_shopping_items(self, items: list[dict[str, Any]], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/households/shopping/items/create-bulk", api_key, json=items)
        if not include_all_fields:
            if isinstance(data, list):
                data = _filter_fields(data, COMMON_FIELDS["shopping_item"])
            elif isinstance(data, dict):
                data = _filter_fields(data, COMMON_FIELDS["shopping_item"])
        return data

    async def bulk_update_shopping_items(self, items: list[dict[str, Any]], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put("/api/households/shopping/items", api_key, json=items)
        if not include_all_fields:
            if isinstance(data, list):
                data = _filter_fields(data, COMMON_FIELDS["shopping_item"])
            elif isinstance(data, dict):
                data = _filter_fields(data, COMMON_FIELDS["shopping_item"])
        return data

    async def bulk_delete_shopping_items(self, item_ids: list[str], api_key: Optional[str] = None) -> Any:
        return await self.request("DELETE", "/api/households/shopping/items", api_key, json={"ids": item_ids})

    # =========================================================================
    # Labels
    # =========================================================================

    async def get_all_labels(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/groups/labels", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["label"])
        return data

    async def get_label_by_id(self, label_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/groups/labels/{label_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["label"])
        return data

    async def create_label(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/groups/labels", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["label"])
        return data

    async def update_label(self, label_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/groups/labels/{label_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                merged.update(payload)
                data = await self.put(f"/api/groups/labels/{label_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["label"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/groups/labels/{label_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["label"])
        return data

    async def delete_label_by_id(self, label_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/groups/labels/{label_id}", api_key)

    # =========================================================================
    # Recipe Timeline Events
    # =========================================================================

    async def get_all_timeline_events(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/recipes/timeline/events", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["timeline_event"])
        return data

    async def get_timeline_event_by_id(self, event_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/recipes/timeline/events/{event_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["timeline_event"])
        return data

    async def create_timeline_event(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        if "subject" not in payload:
            payload["subject"] = payload.get("message", "Timeline event")
        data = await self.post("/api/recipes/timeline/events", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["timeline_event"])
        return data

    async def update_timeline_event(self, event_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/recipes/timeline/events/{event_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                if "recipe" in existing and isinstance(existing["recipe"], dict) and "id" in existing["recipe"]:
                    merged["recipe"] = {"id": existing["recipe"]["id"]}
                merged.update(payload)
                data = await self.put(f"/api/recipes/timeline/events/{event_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["timeline_event"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/recipes/timeline/events/{event_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["timeline_event"])
        return data

    async def delete_timeline_event_by_id(self, event_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/recipes/timeline/events/{event_id}", api_key)

    # =========================================================================
    # Shared Recipes
    # =========================================================================

    async def get_all_shared_recipes(self, api_key: Optional[str] = None, recipe_id: str = "", include_all_fields: bool = False) -> Any:
        params = {}
        if recipe_id:
            params["recipeId"] = recipe_id
        data = await self.get("/api/shared/recipes", api_key, params=params or None)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shared_recipe"])
        return data

    async def get_shared_recipe_by_id(self, token_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/recipes/shared/{token_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shared_recipe"])
        return data

    async def create_shared_recipe(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/shared/recipes", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["shared_recipe"])
        return data

    async def delete_shared_recipe_by_id(self, token_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/shared/recipes/{token_id}", api_key)

    # =========================================================================
    # Recipe Actions
    # =========================================================================

    async def get_all_recipe_actions(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/recipe-actions", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["recipe_action"])
        return data

    async def get_recipe_action_by_id(self, action_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/recipe-actions/{action_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["recipe_action"])
        return data

    async def create_recipe_action(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        # API expects: actionType, title, url, name (optional)
        mapped = {}
        for k, v in payload.items():
            if k == "recipeActionType":
                mapped["actionType"] = v
            else:
                mapped[k] = v
        if "title" not in mapped:
            mapped["title"] = mapped.get("name", "Action")
        if "url" not in mapped:
            mapped["url"] = ""
        data = await self.post("/api/households/recipe-actions", api_key, json=mapped)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["recipe_action"])
        return data

    async def update_recipe_action(self, action_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/households/recipe-actions/{action_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                merged.update(payload)
                data = await self.put(f"/api/households/recipe-actions/{action_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["recipe_action"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/households/recipe-actions/{action_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["recipe_action"])
        return data

    async def delete_recipe_action_by_id(self, action_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/households/recipe-actions/{action_id}", api_key)

    async def trigger_recipe_action(self, action_id: str, recipe_slug: str, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/api/households/recipe-actions/{action_id}/trigger/{recipe_slug}", api_key)

    # =========================================================================
    # Event Notifications
    # =========================================================================

    async def get_all_event_notifications(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/events/notifications", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["event_notification"])
        return data

    async def get_event_notification_by_id(self, notifier_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/events/notifications/{notifier_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["event_notification"])
        return data

    async def create_event_notification(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        if "apprise_url" not in payload:
            payload["apprise_url"] = "json://"
        data = await self.post("/api/households/events/notifications", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["event_notification"])
        return data

    async def update_event_notification(self, notifier_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/households/events/notifications/{notifier_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                merged.update(payload)
                data = await self.put(f"/api/households/events/notifications/{notifier_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["event_notification"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/households/events/notifications/{notifier_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["event_notification"])
        return data

    async def delete_event_notification_by_id(self, notifier_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/households/events/notifications/{notifier_id}", api_key)

    async def test_event_notification(self, notifier_id: str, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/api/households/events/notifications/{notifier_id}/test", api_key)

    # =========================================================================
    # Webhooks
    # =========================================================================

    async def get_all_webhooks(self, api_key: Optional[str] = None, page: int = 1, perPage: int = 50, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/webhooks", api_key, params={"page": page, "perPage": perPage})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["webhook"])
        return data

    async def get_webhook_by_id(self, webhook_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/webhooks/{webhook_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["webhook"])
        return data

    async def create_webhook(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        if "scheduledTime" not in payload:
            payload["scheduledTime"] = "00:00:00"
        data = await self.post("/api/households/webhooks", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["webhook"])
        return data

    async def update_webhook(self, webhook_id: str, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            existing = await self.get(f"/api/households/webhooks/{webhook_id}", api_key)
            if isinstance(existing, dict):
                merged = self._strip_nested(existing)
                merged.update(payload)
                data = await self.put(f"/api/households/webhooks/{webhook_id}", api_key, json=merged)
                if not include_all_fields and isinstance(data, dict):
                    data = _filter_fields(data, COMMON_FIELDS["webhook"])
                return data
        except Exception:
            pass
        data = await self.put(f"/api/households/webhooks/{webhook_id}", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["webhook"])
        return data

    async def delete_webhook_by_id(self, webhook_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/households/webhooks/{webhook_id}", api_key)

    async def test_webhook(self, webhook_id: str, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/api/households/webhooks/{webhook_id}/test", api_key)

    async def rerun_webhooks(self, api_key: Optional[str] = None) -> Any:
        return await self.post("/api/households/webhooks/rerun", api_key)

    # =========================================================================
    # Invitations
    # =========================================================================

    async def get_all_invitations(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/invitations", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["invitation"])
        return data

    async def create_invitation(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/api/households/invitations", api_key, json=payload)
        if not include_all_fields and isinstance(data, dict):
            data = _filter_fields(data, COMMON_FIELDS["invitation"])
        return data

    async def email_invitation(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/households/invitations/email", api_key, json=payload)

    # =========================================================================
    # User Self-Service
    # =========================================================================

    async def get_user_profile(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/users/self", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["user"])
        return data

    async def get_user_ratings(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/users/self/ratings", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["rating"])
        return data

    async def get_user_rating_for_recipe(self, recipe_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/users/self/ratings/{recipe_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["rating"])
        return data

    async def get_user_favorites(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/users/self/favorites", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def set_recipe_rating(self, user_id: str, slug: str, rating: int, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/api/users/{user_id}/ratings/{slug}", api_key, json={"rating": rating})

    async def add_recipe_favorite(self, user_id: str, slug: str, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/api/users/{user_id}/favorites/{slug}", api_key)

    async def remove_recipe_favorite(self, user_id: str, slug: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/users/{user_id}/favorites/{slug}", api_key)

    async def get_user_favorites_by_id(self, user_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/users/{user_id}/favorites", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def get_user_ratings_by_id(self, user_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/users/{user_id}/ratings", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["rating"])
        return data

    # =========================================================================
    # Group / Household Info
    # =========================================================================

    async def get_group_info(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/groups/self", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["group"])
        return data

    async def list_group_members(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/groups/members", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["member"])
        return data

    async def get_group_member(self, username_or_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/groups/members/{username_or_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["member"])
        return data

    async def get_group_preferences(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/groups/preferences", api_key)

    async def update_group_preferences(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.put("/api/groups/preferences", api_key, json=payload)

    async def get_group_storage(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/groups/storage", api_key)

    async def list_households(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/groups/households", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["household"])
        return data

    async def get_household(self, household_slug: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/groups/households/{household_slug}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["household"])
        return data

    async def get_household_info(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/self", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["household"])
        return data

    async def get_household_recipe(self, recipe_slug: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/households/self/recipes/{recipe_slug}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["recipe"])
        return data

    async def list_household_members(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/api/households/members", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["member"])
        return data

    async def get_household_preferences(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/households/preferences", api_key)

    async def update_household_preferences(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.put("/api/households/preferences", api_key, json=payload)

    async def get_household_statistics(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/households/statistics", api_key)

    async def set_household_permissions(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.put("/api/households/permissions", api_key, json=payload)

    # =========================================================================
    # Domain Utilities
    # =========================================================================

    async def parse_ingredient(self, ingredient: str, api_key: Optional[str] = None) -> Any:
        return await self.post("/api/parser/ingredient", api_key, json={"ingredient": ingredient})

    async def parse_ingredients(self, ingredients: list[str], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/parser/ingredients", api_key, json={"ingredients": ingredients})

    async def seed_default_foods(self, api_key: Optional[str] = None) -> Any:
        return await self.post("/api/groups/seeders/foods", api_key, json={})

    async def seed_default_labels(self, api_key: Optional[str] = None) -> Any:
        return await self.post("/api/groups/seeders/labels", api_key, json={})

    async def seed_default_units(self, api_key: Optional[str] = None) -> Any:
        return await self.post("/api/groups/seeders/units", api_key, json={})

    async def get_app_about(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/app/about", api_key)

    async def get_app_startup_info(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/app/about/startup-info", api_key)

    async def get_app_theme(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/app/about/theme", api_key)
