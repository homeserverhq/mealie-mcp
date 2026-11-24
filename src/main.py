from __future__ import annotations
import datetime as dt
import os
import re
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Optional

from fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from toon_mcp import json_to_toon

from .client import MealieClient, _normalize_date

_current_user_token: ContextVar[Optional[str]] = ContextVar("current_user_token", default=None)

ALLOW_ALL_AGGREGATE = os.getenv("ALLOW_ALL_AGGREGATE", "false").lower() in ("true", "1", "yes")
IS_STATEFUL = os.getenv("IS_STATEFUL", "false").lower() in ("true", "1", "yes")


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                _current_user_token.set(token)
        await self.app(scope, receive, send)


mcp = FastMCP("Mealie-mcp-server")

_client: Optional[MealieClient] = None

def get_client() -> MealieClient:
    global _client
    if _client is None:
        _client = MealieClient()
    return _client

def get_user_token() -> Optional[str]:
    return _current_user_token.get()

# =============================================================================
# Pydantic Contract Models
# =============================================================================

class CreateRecipeParam(BaseModel):
    name: str
    description: str = ""
    recipeServings: float = 0
    totalTime: str = ""
    prepTime: str = ""
    cookTime: str = ""
    performTime: str = ""
    recipeYield: str = ""
    recipeYieldQuantity: float = 0
    orgURL: str = ""
    recipeCategory: list[CategoryObjectInput] = []
    tags: list[TagObjectInput] = []
    tools: list[ToolObjectInput] = []
    recipeIngredient: list[str] = Field(default=[], description="Ingredient strings (e.g. '1 cup flour, sifted').")
    recipeInstructions: list[str] = Field(default=[], description="Instruction step strings (e.g. 'Preheat oven to 350F').")
    nutrition: Optional[NutritionInput] = None
    settings: Optional[RecipeSettingsParam] = None
    notes: list[RecipeNoteParam] = []
    image: str = ""

class TagObjectInput(BaseModel):
    """Tag object for bulk tag operations. Slug is used to find existing tags; if not found, a new tag is created with the given name and slug. Duplicate slugs in the same request are collapsed."""
    name: str = Field(description="Tag name.")
    slug: str = Field(description="Tag slug for lookup and creation.")

class CategoryObjectInput(BaseModel):
    """Category object for bulk categorize operations. Slug is used to find existing categories; if not found, a new category is created with the given name and slug. Duplicate slugs in the same request are collapsed."""
    name: str = Field(description="Category name.")
    slug: str = Field(description="Category slug for lookup and creation.")

class BulkRecipeSettingsInput(BaseModel):
    """Settings fields for bulk update. All fields optional - only provided fields are updated on each recipe."""
    public: Optional[bool] = Field(default=None, description="true = public, false = private.")
    show_nutrition: Optional[bool] = Field(default=None, description="true = show nutrition, false = hide.")
    show_assets: Optional[bool] = Field(default=None, description="true = show assets, false = hide.")
    landscape_view: Optional[bool] = Field(default=None, description="true = landscape, false = portrait.")
    disable_comments: Optional[bool] = Field(default=None, description="true = comments disabled, false = enabled.")
    locked: Optional[bool] = Field(default=None, description="true = locked, false = editable.")

class ToolObjectInput(BaseModel):
    """Tool object for recipe operations. Slug is used to find existing tools; if not found, a new tool is created with the given name and slug. Duplicate slugs in the same request are collapsed."""
    name: str = Field(description="Tool name.")
    slug: str = Field(description="Tool slug for lookup and creation.")

class NutritionInput(BaseModel):
    """Nutrition information for a recipe. All fields optional. Values are numeric strings without units."""
    calories: Optional[str] = Field(default=None, description="Numeric string, no units (e.g. '250').")
    carbohydrateContent: Optional[str] = Field(default=None, description="Grams as numeric string (e.g. '32').")
    cholesterolContent: Optional[str] = Field(default=None, description="Milligrams as numeric string (e.g. '55').")
    fatContent: Optional[str] = Field(default=None, description="Grams as numeric string (e.g. '12.5').")
    fiberContent: Optional[str] = Field(default=None, description="Grams as numeric string (e.g. '3').")
    proteinContent: Optional[str] = Field(default=None, description="Grams as numeric string (e.g. '18').")
    saturatedFatContent: Optional[str] = Field(default=None, description="Grams as numeric string (e.g. '4').")
    sodiumContent: Optional[str] = Field(default=None, description="Milligrams as numeric string (e.g. '480').")
    sugarContent: Optional[str] = Field(default=None, description="Grams as numeric string (e.g. '8').")
    transFatContent: Optional[str] = Field(default=None, description="Grams as numeric string (e.g. '0.5').")
    unsaturatedFatContent: Optional[str] = Field(default=None, description="Grams as numeric string (e.g. '6').")

class RecipeSettingsParam(BaseModel):
    """Recipe settings. Only provided fields are updated."""
    public: Optional[bool] = Field(default=None, description="true = public, false = private.")
    showNutrition: Optional[bool] = Field(default=None, description="true = show nutrition, false = hide.")
    showAssets: Optional[bool] = Field(default=None, description="true = show assets, false = hide.")
    landscapeView: Optional[bool] = Field(default=None, description="true = landscape, false = portrait.")
    disableComments: Optional[bool] = Field(default=None, description="true = comments disabled, false = enabled.")
    locked: Optional[bool] = Field(default=None, description="true = locked, false = editable.")

class RecipeNoteParam(BaseModel):
    """Recipe note."""
    title: str = Field(default="", description="Title of the note.")
    text: str = Field(default="", description="Text content of the note.")

class UpdateRecipeParam(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    recipeServings: Optional[float] = None
    totalTime: Optional[str] = None
    prepTime: Optional[str] = None
    cookTime: Optional[str] = None
    performTime: Optional[str] = None
    recipeYield: Optional[str] = None
    recipeYieldQuantity: Optional[float] = None
    orgURL: Optional[str] = None
    recipeCategory: Optional[list[CategoryObjectInput]] = None
    tags: Optional[list[TagObjectInput]] = None
    tools: Optional[list[ToolObjectInput]] = None
    recipeIngredient: Optional[list[str]] = Field(default=None, description="Ingredient strings (e.g. '1 cup flour, sifted').")
    recipeInstructions: Optional[list[str]] = Field(default=None, description="Instruction step strings (e.g. 'Preheat oven to 350F').")
    nutrition: Optional[NutritionInput] = None
    settings: Optional[RecipeSettingsParam] = None
    notes: Optional[list[RecipeNoteParam]] = None
    image: Optional[str] = None

class CreateCategoryParam(BaseModel):
    name: str

class UpdateCategoryParam(BaseModel):
    name: Optional[str] = None

class CreateTagParam(BaseModel):
    name: str

class UpdateTagParam(BaseModel):
    name: Optional[str] = None

class CreateToolParam(BaseModel):
    name: str

class UpdateToolParam(BaseModel):
    name: Optional[str] = None

class CreateFoodParam(BaseModel):
    name: str
    description: str = ""
    pluralName: str = ""
    aliases: list[str] = []

class UpdateFoodParam(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pluralName: Optional[str] = None
    aliases: Optional[list[str]] = None

class CreateUnitParam(BaseModel):
    name: str
    abbreviation: str = ""
    pluralName: str = ""
    pluralAbbreviation: str = ""
    description: str = ""
    useFraction: bool = False
    useAbbreviation: bool = False
    aliases: list[str] = []

class UpdateUnitParam(BaseModel):
    name: Optional[str] = None
    abbreviation: Optional[str] = None
    pluralName: Optional[str] = None
    pluralAbbreviation: Optional[str] = None
    description: Optional[str] = None
    useFraction: Optional[bool] = None
    useAbbreviation: Optional[bool] = None
    aliases: Optional[list[str]] = None

class CreateCommentParam(BaseModel):
    recipeId: str
    text: str

class UpdateCommentParam(BaseModel):
    text: Optional[str] = None

class CreateCookbookParam(BaseModel):
    name: str
    description: str = ""
    position: int = 0
    public: bool = False
    queryFilterString: str = ""

class UpdateCookbookParam(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    position: Optional[int] = None
    public: Optional[bool] = None
    queryFilterString: Optional[str] = None

class CookbookUpdateItemParam(BaseModel):
    """Cookbook update item for bulk operations."""
    id: str = Field(description="Cookbook UUID.")
    name: Optional[str] = Field(default=None, description="New name for the cookbook.")
    description: Optional[str] = Field(default=None, description="New description.")
    position: Optional[int] = Field(default=None, description="Display order (0 = top, ascending).")
    public: Optional[bool] = Field(default=None, description="true = public, false = private.")
    queryFilterString: Optional[str] = Field(default=None, description="Mealie filter for recipe selection.")

class CreateMealplanParam(BaseModel):
    date: str
    entryType: str = "dinner"
    title: str = ""
    recipeId: Optional[str] = None
    text: Optional[str] = None

class UpdateMealplanParam(BaseModel):
    date: Optional[str] = None
    entryType: Optional[str] = None
    title: Optional[str] = None
    recipeId: Optional[str] = None
    text: Optional[str] = None

class CreateShoppingListParam(BaseModel):
    name: str

class UpdateShoppingListParam(BaseModel):
    name: Optional[str] = None

class CreateShoppingItemParam(BaseModel):
    shoppingListId: str
    quantity: float = 0
    note: str = ""
    display: str = ""
    checked: bool = False
    position: int = 0
    foodId: str = ""
    labelId: str = ""
    unitId: str = ""

class UpdateShoppingItemParam(BaseModel):
    quantity: Optional[float] = None
    note: Optional[str] = None
    display: Optional[str] = None
    checked: Optional[bool] = None
    position: Optional[int] = None
    foodId: Optional[str] = None
    labelId: Optional[str] = None
    unitId: Optional[str] = None

class BulkCreateShoppingItem(BaseModel):
    """Shopping item for bulk creation."""
    shoppingListId: str = Field(description="Shopping list UUID to add items to.")
    quantity: float = Field(default=0, description="Quantity of the item.")
    note: str = Field(default="", description="Note for the item.")
    display: str = Field(default="", description="Display text for the item.")
    checked: bool = Field(default=False, description="true = checked (purchased), false = unchecked. Default: false.")
    position: int = Field(default=0, description="Display order (0 = top, ascending).")
    foodId: Optional[str] = Field(default=None, description="Food UUID to associate.")
    labelId: Optional[str] = Field(default=None, description="Label UUID to associate.")
    unitId: Optional[str] = Field(default=None, description="Unit UUID to associate.")

class BulkUpdateShoppingItem(BaseModel):
    """Shopping item for bulk update."""
    id: str = Field(description="Shopping item UUID to update.")
    shoppingListId: Optional[str] = Field(default=None, description="Shopping list UUID.")
    quantity: Optional[float] = Field(default=None, description="New quantity.")
    note: Optional[str] = Field(default=None, description="New note.")
    display: Optional[str] = Field(default=None, description="New display text.")
    checked: Optional[bool] = Field(default=None, description="true = checked, false = unchecked.")
    position: Optional[int] = Field(default=None, description="New display order (0 = top, ascending).")
    foodId: Optional[str] = Field(default=None, description="New food UUID.")
    labelId: Optional[str] = Field(default=None, description="New label UUID.")
    unitId: Optional[str] = Field(default=None, description="New unit UUID.")

class CreateLabelParam(BaseModel):
    name: str
    color: str = ""

class UpdateLabelParam(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None

class CreateTimelineEventParam(BaseModel):
    recipeId: str
    eventType: str
    message: str = ""

class UpdateTimelineEventParam(BaseModel):
    eventType: Optional[str] = None
    message: Optional[str] = None

class CreateSharedRecipeParam(BaseModel):
    recipeId: str

class CreateInvitationParam(BaseModel):
    uses: int
    groupId: Optional[str] = None
    householdId: Optional[str] = None

class EmailInvitationParam(BaseModel):
    email: str
    token: str

class CreateMealplanRuleParam(BaseModel):
    day: str
    entryType: str = "dinner"
    queryFilterString: str = ""

class UpdateMealplanRuleParam(BaseModel):
    day: Optional[str] = None
    entryType: Optional[str] = None
    queryFilterString: Optional[str] = None

class CreateEventNotificationParam(BaseModel):
    name: str
    enabled: bool = True

class UpdateEventNotificationParam(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None

class CreateWebhookParam(BaseModel):
    name: str
    url: str
    enabled: bool = True

class UpdateWebhookParam(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None

class CreateUserParam(BaseModel):
    """Parameters for creating a new user via admin API."""
    username: str = Field(description="Username for the new user.")
    fullName: str = Field(description="Full display name of the user.")
    email: str = Field(description="Email address for the user.")
    password: str = Field(description="Password for the user account.")
    admin: bool = Field(default=False, description="Whether the user is an admin.")
    group: Optional[str] = Field(default=None, description="Group name to assign the user to.")
    household: Optional[str] = Field(default=None, description="Household name to assign the user to.")
    canInvite: bool = Field(default=False, description="Whether the user can invite others.")
    canManage: bool = Field(default=False, description="Whether the user can manage members.")
    canManageHousehold: bool = Field(default=False, description="Whether the user can manage household settings.")
    canOrganize: bool = Field(default=False, description="Whether the user can organize tags/categories/foods.")

class UpdateUserParam(BaseModel):
    """Parameters for updating an existing user via admin API."""
    username: str = Field(description="Username for the user.")
    fullName: str = Field(description="Full display name of the user.")
    email: str = Field(description="Email address for the user.")
    admin: bool = Field(default=False, description="Whether the user is an admin.")
    group: Optional[str] = Field(default=None, description="Group name to assign the user to.")
    household: Optional[str] = Field(default=None, description="Household name to assign the user to.")
    canInvite: bool = Field(default=False, description="Whether the user can invite others.")
    canManage: bool = Field(default=False, description="Whether the user can manage members.")
    canManageHousehold: bool = Field(default=False, description="Whether the user can manage household settings.")
    canOrganize: bool = Field(default=False, description="Whether the user can organize tags/categories/foods.")

class UpdateGroupParam(BaseModel):
    """Parameters for updating an existing group via admin API."""
    id: str = Field(description="Group UUID to update.")
    name: str = Field(description="New name for the group.")

class CreateRecipeFromUrlParam(BaseModel):
    """Parameters for creating a recipe by scraping a URL."""
    url: str = Field(description="The URL of the recipe to scrape.")
    includeTags: bool = Field(default=True, description="Whether to include tags from the scraped data.")
    includeNutrition: bool = Field(default=False, description="Whether to include nutrition data.")

class UpdateShoppingListLabelSettingsParam(BaseModel):
    """Parameters for updating label settings on a shopping list."""
    id: str = Field(description="UUID for the label settings entry.")
    shoppingListId: str = Field(description="Shopping list UUID.")
    labelId: str = Field(description="Label UUID to associate.")
    fontSize: float = Field(default=12.0, description="Font size for labels.")
    fontFamily: str = Field(default="Arial", description="Font family for labels.")

class SetRecipeRatingParam(BaseModel):
    """Parameters for setting a recipe rating."""
    userId: str = Field(description="User UUID.")
    slug: str = Field(description="Recipe slug.")
    rating: int = Field(description="Rating value (1-5).")

class AddRecipeFavoriteParam(BaseModel):
    """Parameters for adding a recipe to favorites."""
    userId: str = Field(description="User UUID.")
    slug: str = Field(description="Recipe slug.")

class RemoveRecipeFavoriteParam(BaseModel):
    """Parameters for removing a recipe from favorites."""
    userId: str = Field(description="User UUID.")
    slug: str = Field(description="Recipe slug.")

class CreateRecipeActionParam(BaseModel):
    """Parameters for creating a recipe action."""
    name: str = Field(description="Name of the action.")
    recipeActionType: str = Field(description="Type of action (link, post).")
    description: str = Field(default="", description="Description of the action.")
    url: str = Field(default="", description="URL for the action.")

class UpdateRecipeActionParam(BaseModel):
    """Parameters for updating a recipe action."""
    name: Optional[str] = Field(default=None, description="New name.")
    recipeActionType: Optional[str] = Field(default=None, description="New action type (link, post).")
    description: Optional[str] = Field(default=None, description="New description.")

class SetHouseholdPermissionsParam(BaseModel):
    """Parameters for setting household permissions for a user."""
    userId: str = Field(description="User UUID to set permissions for.")
    canManage: bool = Field(default=False, description="true = manage members (add/remove/roles). Default: false.")
    canManageHousehold: bool = Field(default=False, description="true = manage household prefs/settings. Default: false.")
    canInvite: bool = Field(default=False, description="true = can invite members. Default: false.")
    canOrganize: bool = Field(default=False, description="true = organize recipes/categories/tags. Default: false.")

class CreateHouseholdParam(BaseModel):
    """Parameters for creating a new household via admin API."""
    name: str = Field(description="Name of the household.")
    groupId: Optional[str] = Field(default=None, description="Group UUID to assign the household to.")

class UpdateHouseholdParam(BaseModel):
    """Parameters for updating an existing household via admin API."""
    id: str = Field(description="Household UUID to update.")
    name: str = Field(description="New name for the household.")
    groupId: str = Field(description="Group UUID the household belongs to.")

def _jsonable(value: Any) -> Any:
    """Recursively convert Pydantic models and containers to JSON-safe data."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _validate_pagination(page: int, perPage: int) -> tuple[int, int]:
    """Bound offset pagination before it reaches the backend.

    The backend treats ``perPage=-1`` as "return everything" and ``perPage=0``
    as an empty page, so both are rejected here.
    """
    if not isinstance(page, int) or page < 1:
        raise ValueError("page must be an integer >= 1")
    if not isinstance(perPage, int) or perPage < 1 or perPage > 200:
        raise ValueError("perPage must be an integer between 1 and 200")
    return page, perPage


def _page_response(data: Any) -> dict[str, Any]:
    """Standard offset-page envelope: items plus top-level pagination."""
    if isinstance(data, dict) and "items" in data:
        return {
            "items": json_to_toon(data.get("items") or []),
            "page": data.get("page"),
            "per_page": data.get("per_page"),
            "total": data.get("total"),
            "total_pages": data.get("total_pages"),
        }
    return {"items": json_to_toon(data if isinstance(data, list) else [])}


def _list_response(data: Any) -> dict[str, Any]:
    """Standard list envelope for non-paginated collections."""
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        data = data["items"]
    return {"items": json_to_toon(data if isinstance(data, list) else [])}


def _require_nonempty(values: Any, field: str) -> Any:
    if not values:
        raise ValueError(f"{field} must contain at least one value")
    return values


def _require_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Reject empty update payloads so an update cannot silently no-op."""
    if not payload:
        raise ValueError("At least one field must be provided to update.")
    return payload


def _normalize_enum(value: str, valid: set[str], param_name: str) -> str:
    if not value:
        return value
    for v in valid:
        if v.lower() == value.lower():
            return v
    raise ValueError(f"Invalid {param_name}: {value!r}. Must be one of: {', '.join(sorted(valid))}")


# =============================================================================
# Recipes
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Recipes", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_recipes(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    search: str = "",
    cookbook: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipes in your Mealie instance.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
        search: Search query to filter recipes by name or description.
        cookbook: Filter recipes by cookbook slug.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_recipes(
        get_user_token(),
        page=page, perPage=perPage, search=search, cookbook=cookbook,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
    )
    if isinstance(data, dict) and "items" in data:
        client = get_client()
        group_slug = await client.current_group_slug(get_user_token())
        data["items"] = [
            _add_recipe_urls(item, client.public_hostname, group_slug)
            for item in data["items"]
        ]
    return _page_response(data)

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Get Recipe By Slug", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_recipe_by_slug(
    slug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single recipe by its slug.

    Args:
        slug: The unique slug of the recipe.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    result = await get_client().get_recipe_by_slug(slug, get_user_token(), include_all_fields=include_all_fields)
    return _add_recipe_urls(result, get_client().public_hostname, await get_client().current_group_slug(get_user_token()))


def _format_ingredient(i) -> dict:
    if hasattr(i, 'model_dump'):
        i = i.model_dump()
    if isinstance(i, dict):
        ing = {k: v for k, v in i.items() if v is not None}
        ing.pop("unit", None)
        ing.pop("food", None)
        ing.setdefault("referenceId", str(uuid.uuid4()))
        ing.setdefault("quantity", 0)
        ing["note"] = ing.get("display", ing.get("note", ""))
        return ing
    return {"display": str(i), "note": str(i), "quantity": 0, "referenceId": str(uuid.uuid4())}


async def _resolve_labels_by_slug(
    items: list,
    fetch_func,
    create_func,
    token: str
) -> list[dict]:
    """Resolve label objects by slug or name, creating only when absent.

    Mealie slugifies a new label from its name and ignores a supplied custom
    slug, so a slug-only match turns an alias into a duplicate-key error. Match
    by slug first, then by case-insensitive name, and re-fetch after a create
    conflict before giving up.
    """
    if not items:
        return []

    def field(obj: Any, key: str) -> str:
        value = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, "")
        return str(value or "")

    unique_items: dict[str, Any] = {}
    for item in items:
        key = field(item, "slug").lower() or field(item, "name").casefold()
        if key and key not in unique_items:
            unique_items[key] = item

    all_items = await fetch_func(token, page=1, perPage=500)
    items_list = all_items.get("items", [])

    def match(item: Any) -> dict | None:
        slug = field(item, "slug").lower()
        name = field(item, "name").casefold()
        return (
            next((x for x in items_list
                  if str(x.get("slug") or "").lower() == slug), None)
            or next((x for x in items_list
                     if str(x.get("name") or "").casefold() == name), None)
        )

    result: list[dict] = []
    for item in unique_items.values():
        found = match(item)
        if found:
            result.append({"id": found["id"], "name": found["name"],
                           "slug": found["slug"]})
            continue
        try:
            created = await create_func(
                {"name": field(item, "name"), "slug": field(item, "slug")}, token
            )
        except Exception:
            refreshed = await fetch_func(token, page=1, perPage=500)
            items_list = refreshed.get("items", [])
            found = match(item)
            if not found:
                raise
            result.append({"id": found["id"], "name": found["name"],
                           "slug": found["slug"]})
            continue
        result.append({"id": created["id"], "name": created["name"],
                       "slug": created["slug"]})
    return result

def _add_recipe_urls(recipe: dict, public_hostname: str,
                     group_slug: str = "home") -> dict:
    """Add absolute recipeUrl and recipeImgUrl values to a recipe response."""
    if not isinstance(recipe, dict):
        return recipe

    slug = recipe.get("slug", "")
    recipe_id = recipe.get("id", "")
    image = recipe.get("image", "")
    base = public_hostname if re.match(r"^https?://", public_hostname or "") else f"https://{public_hostname}"
    group = group_slug or "home"

    recipe_url = f"{base}/g/{group}/r/{slug}" if slug else None

    recipe_img_url = None
    if image and recipe_id:
        recipe_img_url = f"{base}/api/media/recipes/{recipe_id}/images/original.webp?rnd=1&version={image}"

    result = {**recipe, "recipeUrl": recipe_url}
    if recipe_img_url:
        result["recipeImgUrl"] = recipe_img_url
    return result



async def _bulk_patch_recipes(
    recipes: list,
    field_name: str,
    resolved_value: list,
    token: str
) -> dict[str, Any]:
    """Apply a field value to multiple recipes via individual PATCH calls. Bulk endpoint is a no-op in Mealie."""
    if not recipes:
        return {"status": "success", "count": 0, "failed": 0}

    success_count = 0
    failed_count = 0
    for slug in recipes:
        try:
            await get_client().patch_recipe(slug, {field_name: resolved_value}, token)
            success_count += 1
        except Exception:
            failed_count += 1

    return {
        "status": "success" if failed_count == 0 else "partial",
        "count": success_count,
        "failed": failed_count,
        "total": len(recipes)
    }


@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Recipe", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_recipe(
    name: str,
    description: str = "",
    recipeServings: float = 0,
    totalTime: str = "",
    prepTime: str = "",
    cookTime: str = "",
    performTime: str = "",
    recipeYield: str = "",
    recipeYieldQuantity: float = 0,
    orgURL: str = "",
    recipeCategory: list[CategoryObjectInput] = [],
    tags: list[TagObjectInput] = [],
    tools: list[ToolObjectInput] = [],
    recipeIngredient: list[str] = [],
    recipeInstructions: list[str] = [],
    nutrition: Optional[NutritionInput] = None,
    settings: RecipeSettingsParam = None,
    notes: list[RecipeNoteParam] = [],
    image: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new recipe.

    Args:
        name: Name of the recipe.
        description: Description of the recipe.
        recipeServings: Number of servings.
        totalTime: ISO 8601 duration (e.g. PT45M).
        prepTime: ISO 8601 duration (e.g. PT45M).
        cookTime: ISO 8601 duration (e.g. PT45M).
        performTime: ISO 8601 duration (e.g. PT45M).
        recipeYield: Yield amount text.
        recipeYieldQuantity: Yield quantity number.
        orgURL: Original URL the recipe was sourced from.
        recipeCategory: Categories for the recipe.
        tags: Tags for the recipe.
        tools: Tools for the recipe.
        recipeIngredient: Ingredient strings (e.g. '1 cup flour, sifted').
        recipeInstructions: Instruction step strings (e.g. 'Preheat oven to 350F').
        nutrition: Nutrition information.
        settings: Recipe settings. Defaults to public. Set public=False explicitly
            to create a private recipe.
        notes: Recipe notes.
        image: Image URL to scrape.
    """
    # Public is the default. The caller must explicitly set public=False to
    # create a private recipe.
    if settings is None:
        settings = RecipeSettingsParam(public=True)
    elif getattr(settings, "public", None) is None:
        settings = settings.model_copy(update={"public": True})

    params = CreateRecipeParam(
        name=name, description=description, recipeServings=recipeServings,
        totalTime=totalTime, prepTime=prepTime, cookTime=cookTime, performTime=performTime,
        recipeYield=recipeYield, recipeYieldQuantity=recipeYieldQuantity, orgURL=orgURL,
        recipeCategory=recipeCategory, tags=tags, tools=tools,
        recipeIngredient=recipeIngredient, recipeInstructions=recipeInstructions,
        nutrition=nutrition,
        settings=settings,
        notes=[n.model_dump() for n in notes] if notes else [],
        image=image
    )
    slug_raw = await get_client().create_recipe({"name": params.name}, get_user_token())
    slug = slug_raw if isinstance(slug_raw, str) else slug_raw.get("slug", "")
    if not slug:
        raise ValueError("Failed to create recipe")

    _orig_tags = params.tags
    _orig_recipeCategory = params.recipeCategory
    _orig_tools = params.tools

    try:
        recipe = await get_client().get_recipe_by_slug(slug, get_user_token(), include_all_fields=True)
        if not isinstance(recipe, dict):
            raise ValueError(f"Created recipe could not be read back: {slug}")

        recipe.update({
            "description": params.description,
            "recipeServings": params.recipeServings,
            "totalTime": params.totalTime,
            "prepTime": params.prepTime,
            "cookTime": params.cookTime,
            "performTime": params.performTime,
            "recipeYield": params.recipeYield,
            "recipeYieldQuantity": params.recipeYieldQuantity,
            "orgURL": params.orgURL,
            "recipeCategory": [],
            "tags": [],
            "tools": [],
            "nutrition": _jsonable(params.nutrition),
            "settings": _jsonable(params.settings),
            "notes": _jsonable(params.notes),
            "image": params.image,
        })

        if params.recipeIngredient is not None:
            recipe["recipeIngredient"] = [
                _format_ingredient(i)
                for i in params.recipeIngredient
            ]
        if params.recipeInstructions is not None:
            recipe["recipeInstructions"] = [{"text": i} for i in params.recipeInstructions]

        result = await get_client().update_recipe(
            slug, recipe, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
        )
    except Exception:
        # The minimal POST already created a record. Never leave an orphan when
        # the follow-up write fails.
        try:
            await get_client().delete_recipe_by_slug(slug, get_user_token())
        except Exception:
            pass
        raise

    token = get_user_token()
    _label_errors: list[str] = []
    if _orig_tags:
        try:
            resolved = await _resolve_labels_by_slug(_orig_tags, get_client().get_all_tags, get_client().create_tag, token)
            await get_client().patch_recipe(slug, {"tags": resolved}, token)
        except Exception as exc:
            _label_errors.append(f"label assignment failed: {exc}")
    if _orig_recipeCategory:
        try:
            resolved = await _resolve_labels_by_slug(_orig_recipeCategory, get_client().get_all_categories, get_client().create_category, token)
            await get_client().patch_recipe(slug, {"recipeCategory": resolved}, token)
        except Exception as exc:
            _label_errors.append(f"label assignment failed: {exc}")
    if _orig_tools:
        try:
            resolved = await _resolve_labels_by_slug(_orig_tools, get_client().get_all_tools, get_client().create_tool, token)
            await get_client().patch_recipe(slug, {"tools": resolved}, token)
        except Exception as exc:
            _label_errors.append(f"label assignment failed: {exc}")

    if _orig_tags or _orig_recipeCategory or _orig_tools:
        result = await get_client().get_recipe_by_slug(slug, token, include_all_fields=ALLOW_ALL_AGGREGATE)

    if _label_errors and isinstance(result, dict):
        result["warnings"] = _label_errors
        result["partial"] = True
    if isinstance(result, dict):
        return _add_recipe_urls(result, get_client().public_hostname, await get_client().current_group_slug(get_user_token()))
    return {"slug": slug, "status": "created"}

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Recipe", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_recipe(
    slug: str,
    name: str = None,
    description: str = None,
    recipeServings: float = None,
    totalTime: str = None,
    prepTime: str = None,
    cookTime: str = None,
    performTime: str = None,
    recipeYield: str = None,
    recipeYieldQuantity: float = None,
    orgURL: str = None,
    recipeCategory: list[CategoryObjectInput] = None,
    tags: list[TagObjectInput] = None,
    tools: list[ToolObjectInput] = None,
    recipeIngredient: list[str] = None,
    recipeInstructions: list[str] = None,
    nutrition: Optional[NutritionInput] = None,
    settings: RecipeSettingsParam = None,
    notes: list[RecipeNoteParam] = None,
    image: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing recipe.

    Args:
        slug: The unique slug of the recipe to update.
        name: Name of the recipe.
        description: Description of the recipe.
        recipeServings: Number of servings.
        totalTime: ISO 8601 duration (e.g. PT45M).
        prepTime: ISO 8601 duration (e.g. PT45M).
        cookTime: ISO 8601 duration (e.g. PT45M).
        performTime: ISO 8601 duration (e.g. PT45M).
        recipeYield: Yield amount text.
        recipeYieldQuantity: Yield quantity number.
        orgURL: Original URL the recipe was sourced from.
        recipeCategory: Categories for the recipe.
        tags: Tags for the recipe.
        tools: Tools for the recipe.
        recipeIngredient: Ingredient strings (e.g. '1 cup flour, sifted').
        recipeInstructions: Instruction step strings (e.g. 'Preheat oven to 350F').
        nutrition: Nutrition information.
        settings: Recipe settings.
        notes: Recipe notes.
        image: Image URL to scrape.
    """
    params = UpdateRecipeParam(
        name=name, description=description, recipeServings=recipeServings,
        totalTime=totalTime, prepTime=prepTime, cookTime=cookTime, performTime=performTime,
        recipeYield=recipeYield, recipeYieldQuantity=recipeYieldQuantity, orgURL=orgURL,
        recipeCategory=recipeCategory, tags=tags, tools=tools,
        recipeIngredient=recipeIngredient, recipeInstructions=recipeInstructions,
        nutrition=nutrition,
        settings=settings,
        notes=[n.model_dump() for n in notes] if notes else None,
        image=image
    )
    if not any(getattr(params, field) is not None for field in params.model_fields):
        raise ValueError("At least one field must be provided to update.")
    recipe = await get_client().get_recipe_by_slug(slug, get_user_token(), include_all_fields=True)
    if not isinstance(recipe, dict):
        raise ValueError(f"Recipe not found: {slug}")

    _update_tags = params.tags
    _update_recipeCategory = params.recipeCategory
    _update_tools = params.tools

    scalar_fields = {
        "name": params.name, "description": params.description, "recipeServings": params.recipeServings,
        "totalTime": params.totalTime, "prepTime": params.prepTime, "cookTime": params.cookTime,
        "performTime": params.performTime, "recipeYield": params.recipeYield,
        "recipeYieldQuantity": params.recipeYieldQuantity, "orgURL": params.orgURL,
        "nutrition": _jsonable(params.nutrition),
        "settings": _jsonable(params.settings),
        "notes": _jsonable(params.notes),
        "image": params.image,
    }
    recipe.update({k: v for k, v in scalar_fields.items() if v is not None})

    if params.recipeIngredient is not None:
        recipe["recipeIngredient"] = [
            _format_ingredient(i)
            for i in params.recipeIngredient
        ]
    if params.recipeInstructions is not None:
        recipe["recipeInstructions"] = [{"text": i} for i in params.recipeInstructions]

    if _update_tags is not None:
        recipe["tags"] = []
    if _update_recipeCategory is not None:
        recipe["recipeCategory"] = []
    if _update_tools is not None:
        recipe["tools"] = []

    result = await get_client().update_recipe(
        slug, recipe, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

    token = get_user_token()
    _label_errors: list[str] = []
    if _update_tags is not None:
        try:
            resolved = await _resolve_labels_by_slug(_update_tags, get_client().get_all_tags, get_client().create_tag, token)
            await get_client().patch_recipe(slug, {"tags": resolved}, token)
        except Exception as exc:
            _label_errors.append(f"label assignment failed: {exc}")
    if _update_recipeCategory is not None:
        try:
            resolved = await _resolve_labels_by_slug(_update_recipeCategory, get_client().get_all_categories, get_client().create_category, token)
            await get_client().patch_recipe(slug, {"recipeCategory": resolved}, token)
        except Exception as exc:
            _label_errors.append(f"label assignment failed: {exc}")
    if _update_tools is not None:
        try:
            resolved = await _resolve_labels_by_slug(_update_tools, get_client().get_all_tools, get_client().create_tool, token)
            await get_client().patch_recipe(slug, {"tools": resolved}, token)
        except Exception as exc:
            _label_errors.append(f"label assignment failed: {exc}")

    if _update_tags is not None or _update_recipeCategory is not None or _update_tools is not None:
        try:
            result = await get_client().get_recipe_by_slug(
                slug, token, include_all_fields=ALLOW_ALL_AGGREGATE
            )
        except Exception as exc:
            _label_errors.append(f"refresh after label assignment failed: {exc}")

    if _label_errors and isinstance(result, dict):
        result["warnings"] = _label_errors
        result["partial"] = True
    if isinstance(result, dict):
        return _add_recipe_urls(result, get_client().public_hostname, await get_client().current_group_slug(get_user_token()))
    return result

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Recipe By Slug", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_recipe_by_slug(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a recipe by its slug.

    Args:
        slug: The unique slug of the recipe to delete.
    """
    await get_client().delete_recipe_by_slug(slug, get_user_token())
    return {"success": True, "message": "Recipe deleted successfully"}

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Duplicate Recipe", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def duplicate_recipe(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Duplicate an existing recipe.

    Args:
        slug: The slug of the recipe to duplicate.
    """
    return await get_client().duplicate_recipe(slug, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Recipe Last Made", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_recipe_last_made(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Update the 'last made' timestamp for a recipe.

    Args:
        slug: The slug of the recipe.
    """
    return await get_client().update_recipe_last_made(slug, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Bulk Update Recipe Settings", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def bulk_update_recipe_settings(
    recipes: list[str],
    settings: BulkRecipeSettingsInput,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk update settings for multiple recipes (partial update).

    Args:
        recipes: List of recipe slugs.
        settings: Settings to apply to each recipe.
    """
    _require_nonempty(recipes, "recipes")
    if not recipes or not settings:
        return {"status": "error", "message": "recipes and settings are required"}

    settings_dict = settings.model_dump(exclude_none=True)
    if not settings_dict:
        return {"status": "error", "message": "at least one settings field must be provided"}

    return await get_client().bulk_update_recipe_settings(recipes, settings_dict, get_user_token())

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List Recipe Suggestions", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_recipe_suggestions(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get recipe suggestions based on available foods and tools.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    return _list_response(await get_client().get_recipe_suggestions(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Recipe From Url", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
)
async def create_recipe_from_url(
    url: str,
    includeTags: bool = True,
    includeNutrition: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a recipe by scraping a URL.

    Args:
        url: The URL of the recipe to scrape.
        includeTags: true = include scraped tags, false = skip. Default: true.
        includeNutrition: true = include scraped nutrition, false = skip. Default: false.
    """
    params = CreateRecipeFromUrlParam(url=url, includeTags=includeTags, includeNutrition=includeNutrition)
    result = await get_client().create_recipe_from_url(
        params.url, get_user_token(), includeTags=params.includeTags, includeNutrition=params.includeNutrition,
        include_all_fields=ALLOW_ALL_AGGREGATE
    )
    if isinstance(result, str):
        return {"slug": result}
    return result if isinstance(result, dict) else {"result": result}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Create Recipe From Url Bulk", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
)
async def create_recipe_from_url_bulk(
    urls: list[str],
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk create recipes by scraping multiple URLs.

    Args:
        urls: List of recipe URLs to scrape.
    """
    _require_nonempty(urls, "urls")
    return await get_client().create_recipe_from_url_bulk(urls, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Create Recipe From Html Or Json", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_recipe_from_html_or_json(
    data: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a recipe from raw HTML or JSON-LD data.

    Args:
        data: HTML content or JSON-LD recipe data.
    """
    result = await get_client().create_recipe_from_html_or_json(data, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)
    if isinstance(result, str):
        return {"slug": result}
    return result if isinstance(result, dict) else {"result": result}

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Test Scrape Url", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
)
async def test_scrape_url(
    url: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Test-scrape a URL to see what data would be extracted (debug endpoint).

    Args:
        url: The URL to test-scrape.
    """
    result = await get_client().test_scrape_url(url, get_user_token())
    return {"result": result}

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Scrape Recipe Image Url", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
)
async def scrape_recipe_image_url(
    slug: str,
    url: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Scrape an image URL into a recipe.

    Args:
        slug: The slug of the recipe.
        url: The image URL to scrape.
    """
    return await get_client().scrape_recipe_image_url(slug, url, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Delete Recipe Image", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_recipe_image(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a recipe's image.

    Args:
        slug: The slug of the recipe.
    """
    await get_client().delete_recipe_image(slug, get_user_token())
    return {"success": True, "message": "Recipe image deleted successfully"}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List Recipe Export Formats", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_recipe_export_formats(
    ctx: Context = None
) -> dict[str, Any]:
    """Get available export formats and templates for recipes."""
    return await get_client().get_recipe_export_formats(get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Export Recipe", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def export_recipe(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Export a recipe in a specific format.

    Args:
        slug: The slug of the recipe to export.
    """
    return await get_client().export_recipe(slug, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Bulk Tag Recipes", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def bulk_tag_recipes(
    recipes: list[str],
    tags: list[TagObjectInput],
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk assign tags to recipes.

    Args:
        recipes: List of recipe slugs to tag.
        tags: Tags to assign to recipes.
    """
    _require_nonempty(recipes, "recipes")
    if not recipes or not tags:
        return {"status": "error", "message": "recipes and tags are required"}

    resolved = await _resolve_labels_by_slug(tags, get_client().get_all_tags, get_client().create_tag, get_user_token())
    return await _bulk_patch_recipes(recipes, "tags", resolved, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Bulk Categorize Recipes", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def bulk_categorize_recipes(
    recipes: list[str],
    categories: list[CategoryObjectInput],
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk assign categories to recipes.

    Args:
        recipes: List of recipe slugs to categorize.
        categories: Categories to assign to recipes.
    """
    _require_nonempty(recipes, "recipes")
    if not recipes or not categories:
        return {"status": "error", "message": "recipes and categories are required"}

    resolved = await _resolve_labels_by_slug(categories, get_client().get_all_categories, get_client().create_category, get_user_token())
    return await _bulk_patch_recipes(recipes, "recipeCategory", resolved, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Bulk Delete Recipes", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def bulk_delete_recipes(
    recipes: list[str],
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk delete recipes.

    Args:
        recipes: List of recipe slugs to delete.
    """
    _require_nonempty(recipes, "recipes")
    return await get_client().bulk_delete_recipes(recipes, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List Exports", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_exports(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all bulk export data files.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    data = await get_client().list_exports(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return _list_response(data)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Purge Exports", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def purge_exports(
    ctx: Context = None
) -> dict[str, Any]:
    """Purge all bulk export data files."""
    return await get_client().purge_exports(get_user_token())

# =============================================================================
# Categories
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Categories", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_categories(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe categories.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_categories(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Category By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_category_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single category by its ID.

    Args:
        id: The unique ID of the category.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_category_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Category By Slug", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_category_by_slug(
    slug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single category by its slug.

    Args:
        slug: The unique slug of the category.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_category_by_slug(slug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List Empty Categories", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_empty_categories(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List categories that have no associated recipes.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    data = await get_client().get_empty_categories(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Category", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_category(
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new category.

    Args:
        name: Name of the category.
    """
    params = CreateCategoryParam(name=name)
    return await get_client().create_category(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Category", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_category(
    id: str,
    name: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing category.

    Args:
        id: The ID of the category to update.
        name: New name for the category.
    """
    params = UpdateCategoryParam(name=name)
    return await get_client().update_category(
        id, _require_update_payload(_require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True))), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Category By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_category_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a category by its ID.

    Args:
        id: The unique ID of the category to delete.
    """
    await get_client().delete_category_by_id(id, get_user_token())
    return {"success": True, "message": "Category deleted successfully"}

# =============================================================================
# Tags
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Tags", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_tags(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe tags.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_tags(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Tag By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_tag_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tag by its ID.

    Args:
        id: The unique ID of the tag.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_tag_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Tag By Slug", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_tag_by_slug(
    slug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tag by its slug.

    Args:
        slug: The unique slug of the tag.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_tag_by_slug(slug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List Empty Tags", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_empty_tags(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List tags that have no associated recipes.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    data = await get_client().get_empty_tags(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Tag", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_tag(
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new tag.

    Args:
        name: Name of the tag.
    """
    params = CreateTagParam(name=name)
    return await get_client().create_tag(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Tag", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_tag(
    id: str,
    name: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing tag.

    Args:
        id: The ID of the tag to update.
        name: New name for the tag.
    """
    params = UpdateTagParam(name=name)
    return await get_client().update_tag(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Tag By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_tag_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a tag by its ID.

    Args:
        id: The unique ID of the tag to delete.
    """
    await get_client().delete_tag_by_id(id, get_user_token())
    return {"success": True, "message": "Tag deleted successfully"}

# =============================================================================
# Tools
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Tools", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_tools(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe tools.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_tools(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Tool By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_tool_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tool by its ID.

    Args:
        id: The unique ID of the tool.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_tool_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Tool By Slug", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_tool_by_slug(
    slug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tool by its slug.

    Args:
        slug: The unique slug of the tool.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_tool_by_slug(slug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Tool", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_tool(
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new tool.

    Args:
        name: Name of the tool.
    """
    params = CreateToolParam(name=name)
    return await get_client().create_tool(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Tool", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_tool(
    id: str,
    name: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing tool.

    Args:
        id: The ID of the tool to update.
        name: New name for the tool.
    """
    params = UpdateToolParam(name=name)
    return await get_client().update_tool(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Tool By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_tool_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a tool by its ID.

    Args:
        id: The unique ID of the tool to delete.
    """
    await get_client().delete_tool_by_id(id, get_user_token())
    return {"success": True, "message": "Tool deleted successfully"}

# =============================================================================
# Foods
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Foods", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_foods(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all ingredient foods.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_foods(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Food By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_food_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single food by its ID.

    Args:
        id: The unique ID of the food.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_food_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Food", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_food(
    name: str,
    description: str = "",
    pluralName: str = "",
    aliases: list[str] = [],
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new ingredient food.

    Args:
        name: Name of the food.
        description: Description of the food.
        pluralName: Plural name of the food.
        aliases: List of alias names for the food.
    """
    params = CreateFoodParam(
        name=name, description=description, pluralName=pluralName, aliases=aliases
    )
    return await get_client().create_food(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Food", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_food(
    id: str,
    name: str = None,
    description: str = None,
    pluralName: str = None,
    aliases: list[str] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing food.

    Args:
        id: The ID of the food to update.
        name: New name for the food.
        description: New description.
        pluralName: New plural name.
        aliases: New list of aliases.
    """
    params = UpdateFoodParam(
        name=name, description=description, pluralName=pluralName, aliases=aliases
    )
    return await get_client().update_food(
        id, _require_update_payload(_require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True))), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Food By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_food_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a food by its ID.

    Args:
        id: The unique ID of the food to delete.
    """
    await get_client().delete_food_by_id(id, get_user_token())
    return {"success": True, "message": "Food deleted successfully"}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Merge Foods", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def merge_foods(
    food_to_keep: str,
    food_to_merge: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Merge two foods together.

    Args:
        food_to_keep: ID of the food to keep.
        food_to_merge: ID of the food to merge into the kept food.
    """
    if food_to_keep == food_to_merge:
        raise ValueError("food_to_keep and food_to_merge must differ")
    return await get_client().merge_foods(food_to_keep, food_to_merge, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

# =============================================================================
# Units
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Units", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_units(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all ingredient units.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_units(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Unit By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_unit_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single unit by its ID.

    Args:
        id: The unique ID of the unit.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_unit_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Unit", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_unit(
    name: str,
    abbreviation: str = "",
    pluralName: str = "",
    pluralAbbreviation: str = "",
    description: str = "",
    fraction: bool = False,
    useAbbreviation: bool = False,
    aliases: list[str] = [],
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new ingredient unit.

    Args:
        name: Name of the unit.
        abbreviation: Abbreviation for the unit.
        pluralName: Plural name of the unit.
        pluralAbbreviation: Plural abbreviation.
        description: Description of the unit.
        fraction: true = fractions (e.g. 1/2), false = decimals. Default: false.
        useAbbreviation: true = abbreviation (e.g. 'c'), false = full name. Default: false.
        aliases: List of alias names.
    """
    params = CreateUnitParam(
        name=name, abbreviation=abbreviation, pluralName=pluralName,
        pluralAbbreviation=pluralAbbreviation, description=description,
        fraction=fraction, useAbbreviation=useAbbreviation, aliases=aliases
    )
    return await get_client().create_unit(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Unit", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_unit(
    id: str,
    name: str = None,
    abbreviation: str = None,
    pluralName: str = None,
    pluralAbbreviation: str = None,
    description: str = None,
    fraction: bool = None,
    useAbbreviation: bool = None,
    aliases: list[str] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing unit.

    Args:
        id: The ID of the unit to update.
        name: New name.
        abbreviation: New abbreviation.
        pluralName: New plural name.
        pluralAbbreviation: New plural abbreviation.
        description: New description.
        fraction: true = fractions, false = decimals.
        useAbbreviation: true = abbreviation, false = full name.
        aliases: New list of aliases.
    """
    params = UpdateUnitParam(
        name=name, abbreviation=abbreviation, pluralName=pluralName,
        pluralAbbreviation=pluralAbbreviation, description=description,
        fraction=fraction, useAbbreviation=useAbbreviation, aliases=aliases
    )
    return await get_client().update_unit(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Unit By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_unit_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a unit by its ID.

    Args:
        id: The unique ID of the unit to delete.
    """
    await get_client().delete_unit_by_id(id, get_user_token())
    return {"success": True, "message": "Unit deleted successfully"}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Merge Units", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def merge_units(
    unit_to_keep: str,
    unit_to_merge: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Merge two units together.

    Args:
        unit_to_keep: ID of the unit to keep.
        unit_to_merge: ID of the unit to merge into the kept unit.
    """
    if unit_to_keep == unit_to_merge:
        raise ValueError("unit_to_keep and unit_to_merge must differ")
    return await get_client().merge_units(unit_to_keep, unit_to_merge, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

# =============================================================================
# Comments
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Comments", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_comments(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe comments.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_comments(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Comment By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_comment_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single comment by its ID.

    Args:
        id: The unique ID of the comment.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_comment_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Comment", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_comment(
    recipeId: str,
    text: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new comment on a recipe.

    Args:
        recipeId: The ID of the recipe to comment on.
        text: The comment text.
    """
    params = CreateCommentParam(recipeId=recipeId, text=text)
    return await get_client().create_comment(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Comment", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_comment(
    id: str,
    text: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing comment.

    Args:
        id: The ID of the comment to update.
        text: New text for the comment.
    """
    params = UpdateCommentParam(text=text)
    return await get_client().update_comment(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Comment By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_comment_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a comment by its ID.

    Args:
        id: The unique ID of the comment to delete.
    """
    await get_client().delete_comment_by_id(id, get_user_token())
    return {"success": True, "message": "Comment deleted successfully"}

# =============================================================================
# Cookbooks
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Cookbooks", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_cookbooks(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all cookbooks.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_cookbooks(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Cookbook By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_cookbook_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single cookbook by its ID.

    Args:
        id: The unique ID of the cookbook.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_cookbook_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Cookbook", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_cookbook(
    name: str,
    description: str = "",
    position: int = 0,
    public: bool = False,
    queryFilterString: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new cookbook.

    Args:
        name: Name of the cookbook.
        description: Description of the cookbook.
        position: Display position. Defaults to 0.
        public: true = public, false = private. Default: false.
        queryFilterString: Mealie filter for recipe selection (e.g. 'tags = tag1'). Empty = no filter.
    """
    params = CreateCookbookParam(
        name=name, description=description, position=position,
        public=public, queryFilterString=queryFilterString
    )
    return await get_client().create_cookbook(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Cookbook", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_cookbook(
    id: str,
    name: str = None,
    description: str = None,
    position: int = None,
    public: bool = None,
    queryFilterString: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing cookbook.

    Args:
        id: The ID of the cookbook to update.
        name: New name.
        description: New description.
        position: New display position.
        public: true = public, false = private.
        queryFilterString: Mealie filter for recipe selection.
    """
    params = UpdateCookbookParam(
        name=name, description=description, position=position,
        public=public, queryFilterString=queryFilterString
    )
    return await get_client().update_cookbook(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Cookbook By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_cookbook_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a cookbook by its ID.

    Args:
        id: The unique ID of the cookbook to delete.
    """
    await get_client().delete_cookbook_by_id(id, get_user_token())
    return {"success": True, "message": "Cookbook deleted successfully"}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Update Cookbooks", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_cookbooks(
    cookbooks: list[CookbookUpdateItemParam],
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk reorder or update cookbooks.

    Args:
        cookbooks: Cookbooks to update.
    """
    _require_nonempty(cookbooks, "cookbooks")
    payload = [c.model_dump(exclude_none=True) for c in cookbooks]
    return await get_client().update_cookbooks(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

# =============================================================================
# Mealplans
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Mealplans", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_mealplans(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    startDate: str = "",
    endDate: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """List all mealplan entries.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
        startDate: ISO 8601 date format (2026-06-22).
        endDate: ISO 8601 date format (2026-06-22).
    """
    page, perPage = _validate_pagination(page, perPage)
    if startDate:
        startDate = _normalize_date(startDate)
    if endDate:
        endDate = _normalize_date(endDate)
    data = await get_client().get_all_mealplans(
        get_user_token(), page=page, perPage=perPage,
        start_date=startDate, end_date=endDate,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Mealplan By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_mealplan_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single mealplan entry by its ID.

    Args:
        id: The unique ID of the mealplan entry.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_mealplan_by_id(str(id), get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List Todays Meals", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_todays_meals(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get today's mealplans.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    data = await get_client().get_todays_meals(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return _list_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Mealplan", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_mealplan(
    date: str,
    entryType: str = "dinner",
    title: str = "",
    recipeId: str = "",
    text: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new mealplan entry.

    Args:
        date: ISO 8601 date format (2026-06-22).
        entryType: Type of meal (breakfast, lunch, dinner, side). Defaults to "dinner".
        title: Title of the mealplan entry.
        recipeId: ID of the associated recipe.
        text: Additional text for the entry.
    """
    date = _normalize_date(date)
    entryType = _normalize_enum(entryType, {"breakfast", "lunch", "dinner", "side"}, "entryType")
    params = CreateMealplanParam(date=date, entryType=entryType, title=title, recipeId=recipeId or None, text=text or None)
    data = params.model_dump(exclude_unset=True, exclude_none=True)
    return await get_client().create_mealplan(
        data, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Random Mealplan", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_random_mealplan(
    date: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a random mealplan entry using configured rules.

    Args:
        date: ISO 8601 date format (2026-06-22). Defaults to today.
    """
    date = _normalize_date(date) if date else dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return await get_client().create_random_mealplan({"date": date}, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Mealplan", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_mealplan(
    id: int,
    date: str = None,
    entryType: str = None,
    title: str = None,
    recipeId: str = None,
    text: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing mealplan entry.

    Args:
        id: The ID of the mealplan entry to update.
        date: ISO 8601 date format (2026-06-22).
        entryType: New meal type (breakfast, lunch, dinner, side).
        title: New title.
        recipeId: New recipe ID.
        text: New additional text.
    """
    if date is not None:
        date = _normalize_date(date)
    if entryType is not None:
        entryType = _normalize_enum(entryType, {"breakfast", "lunch", "dinner", "side"}, "entryType")
    params = UpdateMealplanParam(
        date=date, entryType=entryType, title=title,
        recipeId=recipeId, text=text
    )
    return await get_client().update_mealplan(
        str(id), _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Mealplan By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_mealplan_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a mealplan entry by its ID.

    Args:
        id: The unique ID of the mealplan entry to delete.
    """
    await get_client().delete_mealplan_by_id(str(id), get_user_token())
    return {"success": True, "message": "Mealplan deleted successfully"}

# =============================================================================
# Mealplan Rules
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List All Mealplan Rules", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_mealplan_rules(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all mealplan rules.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_mealplan_rules(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Mealplan Rule By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_mealplan_rule_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single mealplan rule by ID.

    Args:
        id: The unique ID of the mealplan rule.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_mealplan_rule_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Mealplan Rule", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_mealplan_rule(
    day: str,
    entryType: str = "dinner",
    queryFilterString: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new mealplan rule.

    Args:
        day: Day of the week (monday, tuesday, wednesday, thursday, friday, saturday, sunday).
        entryType: Type of meal (breakfast, lunch, dinner, side). Defaults to "dinner".
        queryFilterString: Mealie filter for recipe selection (e.g. 'tags = tag1'). Empty = no filter.
    """
    day = _normalize_enum(day, {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}, "day")
    entryType = _normalize_enum(entryType, {"breakfast", "lunch", "dinner", "side"}, "entryType")
    params = CreateMealplanRuleParam(day=day, entryType=entryType, queryFilterString=queryFilterString)
    return await get_client().create_mealplan_rule(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Mealplan Rule", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_mealplan_rule(
    id: str,
    day: str = None,
    entryType: str = None,
    queryFilterString: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing mealplan rule.

    Args:
        id: The ID of the mealplan rule to update.
        day: New day of the week (monday, tuesday, wednesday, thursday, friday, saturday, sunday).
        entryType: New meal type (breakfast, lunch, dinner, side).
        queryFilterString: Mealie filter for recipe selection.
    """
    if day is not None:
        day = _normalize_enum(day, {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}, "day")
    if entryType is not None:
        entryType = _normalize_enum(entryType, {"breakfast", "lunch", "dinner", "side"}, "entryType")
    params = UpdateMealplanRuleParam(day=day, entryType=entryType, queryFilterString=queryFilterString)
    return await get_client().update_mealplan_rule(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Mealplan Rule By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_mealplan_rule_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a mealplan rule by its ID.

    Args:
        id: The unique ID of the mealplan rule to delete.
    """
    await get_client().delete_mealplan_rule_by_id(id, get_user_token())
    return {"success": True, "message": "Mealplan rule deleted successfully"}

# =============================================================================
# Shopping Lists
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Shopping Lists", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_shopping_lists(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all shopping lists.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_shopping_lists(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Shopping List By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_shopping_list_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single shopping list by its ID.

    Args:
        id: The unique ID of the shopping list.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_shopping_list_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Shopping List", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_shopping_list(
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new shopping list.

    Args:
        name: Name of the shopping list.
    """
    params = CreateShoppingListParam(name=name)
    return await get_client().create_shopping_list(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Shopping List", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_shopping_list(
    id: str,
    name: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing shopping list.

    Args:
        id: The ID of the shopping list to update.
        name: New name.
    """
    params = UpdateShoppingListParam(name=name)
    return await get_client().update_shopping_list(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Shopping List By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_shopping_list_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a shopping list by its ID.

    Args:
        id: The unique ID of the shopping list to delete.
    """
    await get_client().delete_shopping_list_by_id(id, get_user_token())
    return {"success": True, "message": "Shopping list deleted successfully"}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Update Shopping List Label Settings", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_shopping_list_label_settings(
    id: str,
    labelId: str,
    fontSize: float = 12.0,
    fontFamily: str = "Arial",
    ctx: Context = None
) -> dict[str, Any]:
    """Update label settings for a shopping list.

    Args:
        id: The ID of the shopping list.
        labelId: The ID of an existing label to associate. Use list_all_labels() to find available labels.
        fontSize: Font size for labels. Defaults to 12.0.
        fontFamily: Font family for labels. Defaults to "Arial".
    """
    if not labelId:
        return {"error": "labelId is required. Use list_all_labels() to find available labels."}
    import uuid
    params = UpdateShoppingListLabelSettingsParam(
        id=str(uuid.uuid4()), shoppingListId=id, labelId=labelId, fontSize=fontSize, fontFamily=fontFamily
    )
    return await get_client().update_shopping_list_label_settings(id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Add Recipe To Shopping List", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def add_recipe_to_shopping_list(
    id: str,
    recipeId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Add recipe ingredients to a shopping list.

    Args:
        id: The ID of the shopping list.
        recipeId: The ID of the recipe whose ingredients to add.
    """
    return await get_client().add_recipe_to_shopping_list(id, recipeId, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Remove Recipe From Shopping List", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def remove_recipe_from_shopping_list(
    id: str,
    recipeId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Remove recipe ingredients from a shopping list.

    Args:
        id: The ID of the shopping list.
        recipeId: The ID of the recipe whose ingredients to remove.
    """
    return await get_client().remove_recipe_from_shopping_list(id, recipeId, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

# =============================================================================
# Shopping Items
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Shopping Items", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_shopping_items(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all shopping list items.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_shopping_items(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Shopping Item By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_shopping_item_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single shopping list item by its ID.

    Args:
        id: The unique ID of the shopping item.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_shopping_item_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Shopping Item", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_shopping_item(
    shoppingListId: str,
    quantity: float = 0,
    note: str = "",
    display: str = "",
    checked: bool = False,
    position: int = 0,
    foodId: str = "",
    labelId: str = "",
    unitId: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new shopping list item.

    Args:
        shoppingListId: The ID of the shopping list.
        quantity: Quantity of the item.
        note: Note describing the item.
        display: Display text for the item.
        checked: true = checked (purchased), false = unchecked. Default: false.
        position: Display position (lower values first).
        foodId: ID of the associated food.
        labelId: ID of the associated label.
        unitId: ID of the associated unit.
    """
    params = CreateShoppingItemParam(
        shoppingListId=shoppingListId, quantity=quantity, note=note,
        display=display, checked=checked, position=position,
        foodId=foodId, labelId=labelId, unitId=unitId
    )
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    payload = {k: v for k, v in payload.items() if not (isinstance(v, str) and v == "" and k in ("foodId", "labelId", "unitId"))}
    return await get_client().create_shopping_item(
        payload, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Shopping Item", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_shopping_item(
    id: str,
    shoppingListId: str = "",
    quantity: float = None,
    note: str = None,
    display: str = None,
    checked: bool = None,
    position: int = None,
    foodId: str = None,
    labelId: str = None,
    unitId: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing shopping list item.

    Args:
        id: The ID of the shopping item to update.
        shoppingListId: The shopping list this item belongs to.
        quantity: New quantity.
        note: New note.
        display: New display text.
        checked: true = checked, false = unchecked.
        position: New display position.
        foodId: New food ID.
        labelId: New label ID.
        unitId: New unit ID.
    """
    params = UpdateShoppingItemParam(
        quantity=quantity, note=note, display=display, checked=checked,
        position=position, foodId=foodId, labelId=labelId,
        unitId=unitId
    )
    payload = _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True))
    if shoppingListId:
        payload["shoppingListId"] = shoppingListId
    return await get_client().update_shopping_item(
        id, payload, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Shopping Item By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_shopping_item_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a shopping list item by its ID.

    Args:
        id: The unique ID of the shopping item to delete.
    """
    await get_client().delete_shopping_item_by_id(id, get_user_token())
    return {"success": True, "message": "Shopping item deleted successfully"}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Bulk Create Shopping Items", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def bulk_create_shopping_items(
    items: list[BulkCreateShoppingItem],
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk create shopping list items.

    Args:
        items: Shopping items to create.
    """
    _require_nonempty(items, "items")
    normalized = []
    for item in items:
        entry = item.model_dump(exclude_none=True)
        if not entry.get("note"):
            entry["note"] = entry.get("display", "")
        normalized.append(entry)
    return _list_response(await get_client().bulk_create_shopping_items(
        normalized, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE,
    ))

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Bulk Update Shopping Items", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def bulk_update_shopping_items(
    items: list[BulkUpdateShoppingItem],
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk update shopping list items.

    Args:
        items: Shopping items to update.
    """
    _require_nonempty(items, "items")
    normalized = [item.model_dump(exclude_unset=True, exclude_none=True) for item in items]
    return await get_client().bulk_update_shopping_items(normalized, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Bulk Delete Shopping Items", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def bulk_delete_shopping_items(
    ids: list[str],
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk delete shopping list items by IDs.

    Args:
        ids: List of shopping item IDs to delete.
    """
    _require_nonempty(ids, "ids")
    return await get_client().bulk_delete_shopping_items(ids, get_user_token())

# =============================================================================
# Labels
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="List All Labels", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_labels(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all multi-purpose labels.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_labels(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Label By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_label_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single label by its ID.

    Args:
        id: The unique ID of the label.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_label_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Label", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_label(
    name: str,
    color: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new label.

    Args:
        name: Name of the label.
        color: Color hex code (e.g. '#FF5733').
    """
    params = CreateLabelParam(name=name, color=color)
    return await get_client().create_label(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Label", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_label(
    id: str,
    name: str = None,
    color: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing label.

    Args:
        id: The ID of the label to update.
        name: New name.
        color: New color hex code (e.g. '#FF5733').
    """
    params = UpdateLabelParam(name=name, color=color)
    return await get_client().update_label(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Label By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_label_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a label by its ID.

    Args:
        id: The unique ID of the label to delete.
    """
    await get_client().delete_label_by_id(id, get_user_token())
    return {"success": True, "message": "Label deleted successfully"}

# =============================================================================
# Recipe Timeline Events
# =============================================================================

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="List All Timeline Events", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_timeline_events(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe timeline events.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_timeline_events(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Timeline Event By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_timeline_event_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single timeline event by its ID.

    Args:
        id: The unique ID of the timeline event.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_timeline_event_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Timeline Event", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_timeline_event(
    recipeId: str,
    eventType: str,
    message: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new recipe timeline event.

    Args:
        recipeId: The ID of the recipe.
        eventType: Type of event (system, info, comment).
        message: Event message text.
    """
    eventType = _normalize_enum(eventType, {"system", "info", "comment"}, "eventType")
    params = CreateTimelineEventParam(recipeId=recipeId, eventType=eventType, message=message)
    return await get_client().create_timeline_event(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Timeline Event", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_timeline_event(
    id: str,
    eventType: str = None,
    message: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing timeline event.

    Args:
        id: The ID of the timeline event to update.
        eventType: New event type (system, info, comment).
        message: New event message.
    """
    if eventType is not None:
        eventType = _normalize_enum(eventType, {"system", "info", "comment"}, "eventType")
    params = UpdateTimelineEventParam(eventType=eventType, message=message)
    return await get_client().update_timeline_event(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Timeline Event By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_timeline_event_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a timeline event by its ID.

    Args:
        id: The unique ID of the timeline event to delete.
    """
    await get_client().delete_timeline_event_by_id(id, get_user_token())
    return {"success": True, "message": "Timeline event deleted successfully"}

# =============================================================================
# Shared Recipes
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List All Shared Recipes", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_shared_recipes(
    include_all_fields: bool = False,
    recipeId: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """List all shared recipe tokens.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        recipeId: Filter by recipe ID.
    """
    data = await get_client().get_all_shared_recipes(
        get_user_token(), recipe_id=recipeId,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Shared Recipe By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_shared_recipe_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a shared recipe by its public token ID.

    Args:
        id: The public token ID of the shared recipe.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_shared_recipe_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Shared Recipe", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_shared_recipe(
    recipeId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a share token for a recipe.

    Args:
        recipeId: The ID of the recipe to share.
    """
    params = CreateSharedRecipeParam(recipeId=recipeId)
    return await get_client().create_shared_recipe(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Shared Recipe By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_shared_recipe_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a shared recipe token.

    Args:
        id: The token ID of the shared recipe to delete.
    """
    await get_client().delete_shared_recipe_by_id(id, get_user_token())
    return {"success": True, "message": "Shared recipe deleted successfully"}

# =============================================================================
# Recipe Actions
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List All Recipe Actions", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_recipe_actions(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe actions.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_recipe_actions(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Recipe Action By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_recipe_action_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single recipe action by its ID.

    Args:
        id: The unique ID of the recipe action.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_recipe_action_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Create Recipe Action", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_recipe_action(
    name: str,
    recipeActionType: str,
    description: str = "",
    url: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new recipe action.

    Args:
        name: Name of the action.
        recipeActionType: Type of action (link, post).
        description: Description of the action.
        url: URL for the action.
    """
    recipeActionType = _normalize_enum(recipeActionType, {"link", "post"}, "recipeActionType")
    params = CreateRecipeActionParam(name=name, recipeActionType=recipeActionType, description=description, url=url)
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    return await get_client().create_recipe_action(
        payload, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Recipe Action", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_recipe_action(
    id: str,
    name: str = None,
    recipeActionType: str = None,
    description: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing recipe action.

    Args:
        id: The ID of the recipe action to update.
        name: New name.
        recipeActionType: New action type (link, post).
        description: New description.
    """
    if recipeActionType is not None:
        recipeActionType = _normalize_enum(recipeActionType, {"link", "post"}, "recipeActionType")
    params = UpdateRecipeActionParam(name=name, recipeActionType=recipeActionType, description=description)
    return await get_client().update_recipe_action(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)),
        get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Delete Recipe Action By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_recipe_action_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a recipe action by its ID.

    Args:
        id: The unique ID of the recipe action to delete.
    """
    await get_client().delete_recipe_action_by_id(id, get_user_token())
    return {"success": True, "message": "Recipe action deleted successfully"}

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Trigger Recipe Action", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def trigger_recipe_action(
    id: str,
    recipeSlug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Trigger a recipe action against a specific recipe.

    Args:
        id: The ID of the recipe action to trigger.
        recipeSlug: The slug of the recipe to trigger the action on.
    """
    return await get_client().trigger_recipe_action(id, recipeSlug, get_user_token())

# =============================================================================
# Event Notifications
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List All Event Notifications", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_event_notifications(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all event notification rules.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_event_notifications(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Event Notification By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_event_notification_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single event notification by ID.

    Args:
        id: The unique ID of the event notification.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_event_notification_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Create Event Notification", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_event_notification(
    name: str,
    enabled: bool = True,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new event notification rule.

    Args:
        name: Name of the notification.
        enabled: true = enabled, false = disabled. Default: true.
    """
    params = CreateEventNotificationParam(name=name, enabled=enabled)
    return await get_client().create_event_notification(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Update Event Notification", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_event_notification(
    id: str,
    name: str = None,
    enabled: bool = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing event notification.

    Args:
        id: The ID of the event notification to update.
        name: New name.
        enabled: true = enabled, false = disabled.
    """
    params = UpdateEventNotificationParam(name=name, enabled=enabled)
    return await get_client().update_event_notification(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Delete Event Notification By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_event_notification_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete an event notification by its ID.

    Args:
        id: The unique ID of the event notification to delete.
    """
    await get_client().delete_event_notification_by_id(id, get_user_token())
    return {"success": True, "message": "Event notification deleted successfully"}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Test Event Notification", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
)
async def test_event_notification(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Test an event notification by sending a test event.

    Args:
        id: The ID of the event notification to test.
    """
    return await get_client().test_event_notification(id, get_user_token())

# =============================================================================
# Webhooks
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List All Webhooks", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_webhooks(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all webhooks.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    page, perPage = _validate_pagination(page, perPage)
    data = await get_client().get_all_webhooks(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return _page_response(data)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Webhook By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_webhook_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single webhook by ID.

    Args:
        id: The unique ID of the webhook.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_webhook_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Create Webhook", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_webhook(
    name: str,
    url: str,
    enabled: bool = True,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new webhook.

    Args:
        name: Name of the webhook.
        url: The URL to send webhook events to.
        enabled: true = enabled, false = disabled. Default: true.
    """
    params = CreateWebhookParam(name=name, url=url, enabled=enabled)
    return await get_client().create_webhook(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Update Webhook", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_webhook(
    id: str,
    name: str = None,
    url: str = None,
    enabled: bool = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing webhook.

    Args:
        id: The ID of the webhook to update.
        name: New name.
        url: New webhook URL.
        enabled: true = enabled, false = disabled.
    """
    params = UpdateWebhookParam(name=name, url=url, enabled=enabled)
    return await get_client().update_webhook(
        id, _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Delete Webhook By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_webhook_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a webhook by its ID.

    Args:
        id: The unique ID of the webhook to delete.
    """
    await get_client().delete_webhook_by_id(id, get_user_token())
    return {"success": True, "message": "Webhook deleted successfully"}

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Test Webhook", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
)
async def test_webhook(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Test a webhook by sending a test event.

    Args:
        id: The ID of the webhook to test.
    """
    return await get_client().test_webhook(id, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Rerun Webhooks", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
)
async def rerun_webhooks(
    ctx: Context = None
) -> dict[str, Any]:
    """Rerun all failed webhook deliveries."""
    return await get_client().rerun_webhooks(get_user_token())

# =============================================================================
# Invitations
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List All Invitations", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_invitations(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all household invitation tokens.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    data = await get_client().get_all_invitations(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return _list_response(data)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Create Invitation", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_invitation(
    uses: int,
    groupId: str = "",
    householdId: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a household invitation token.

    Args:
        uses: Maximum number of times the invitation can be used.
        groupId: Group ID to associate with the invitation.
        householdId: Household ID to associate with the invitation.
    """
    params = CreateInvitationParam(uses=uses, groupId=groupId or None, householdId=householdId or None)
    return await get_client().create_invitation(
        params.model_dump(exclude_unset=True, exclude_none=True),
        get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Email Invitation", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
)
async def email_invitation(
    email: str,
    token: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Email an invitation to a user.

    Args:
        email: The email address to send the invitation to.
        token: The invitation token to send.
    """
    params = EmailInvitationParam(email=email, token=token)
    return await get_client().email_invitation(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

# =============================================================================
# User Self-Service
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Get User Profile", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_user_profile(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the currently logged-in user's profile.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_user_profile(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="List User Ratings", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_user_ratings(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get all ratings from the currently logged-in user.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    return _list_response(await get_client().get_user_ratings(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get User Rating For Recipe", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_user_rating_for_recipe(
    recipeId: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current user's rating for a specific recipe.

    Args:
        recipeId: The ID of the recipe.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_user_rating_for_recipe(recipeId, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="List User Favorites", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_user_favorites(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get all favorite recipes from the currently logged-in user.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    return _list_response(await get_client().get_user_favorites(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Set Recipe Rating", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def set_recipe_rating(
    userId: str,
    slug: str,
    rating: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Set or update a rating for a recipe.

    Args:
        userId: The ID of the user.
        slug: The slug of the recipe.
        rating: Rating value (1-5).
    """
    params = SetRecipeRatingParam(userId=userId, slug=slug, rating=rating)
    await get_client().set_recipe_rating(params.userId, params.slug, params.rating, get_user_token())
    return {"status": "rated", "slug": slug, "rating": rating}

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Add Recipe Favorite", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def add_recipe_favorite(
    userId: str,
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Add a recipe to the user's favorites.

    Args:
        userId: The ID of the user.
        slug: The slug of the recipe.
    """
    params = AddRecipeFavoriteParam(userId=userId, slug=slug)
    await get_client().add_recipe_favorite(params.userId, params.slug, get_user_token())
    return {"status": "favorited", "slug": slug}

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Remove Recipe Favorite", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def remove_recipe_favorite(
    userId: str,
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Remove a recipe from the user's favorites.

    Args:
        userId: The ID of the user.
        slug: The slug of the recipe.
    """
    params = RemoveRecipeFavoriteParam(userId=userId, slug=slug)
    await get_client().remove_recipe_favorite(params.userId, params.slug, get_user_token())
    return {"status": "unfavorited", "slug": slug}

# =============================================================================
# Group / Household Info
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Get Group Info", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_group_info(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current user's group information.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_group_info(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="List Group Members", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_group_members(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all members of the current group.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    return _list_response(await get_client().list_group_members(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Group Member", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_group_member(
    usernameOrId: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a specific group member by username or ID.

    Args:
        usernameOrId: The username or ID of the member.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_group_member(usernameOrId, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Group Preferences", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_group_preferences(
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current group's preferences."""
    return await get_client().get_group_preferences(get_user_token())

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Group Preferences", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_group_preferences(
    privateGroup: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Update the current group's preferences.

    Args:
        privateGroup: true = private (hidden), false = public. Default: false.
    """
    return await get_client().update_group_preferences(
        {"privateGroup": privateGroup}, get_user_token()
    )

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Group Storage", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_group_storage(
    ctx: Context = None
) -> dict[str, Any]:
    """Get group storage statistics."""
    return await get_client().get_group_storage(get_user_token())

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="List Households", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_households(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all households in the group.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    return _list_response(await get_client().list_households(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Household", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_household(
    householdSlug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a specific household by its slug.

    Args:
        householdSlug: The slug of the household.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_household(householdSlug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Get Household Info", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_household_info(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current user's household information.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_household_info(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Household Recipe", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_household_recipe(
    recipeSlug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a recipe scoped to the current household.

    Args:
        recipeSlug: The slug of the recipe.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_household_recipe(recipeSlug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="List Household Members", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_household_members(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all members of the current household.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    return _list_response(await get_client().list_household_members(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Get Household Preferences", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_household_preferences(
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current household's preferences."""
    return await get_client().get_household_preferences(get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Household Statistics", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_household_statistics(
    ctx: Context = None
) -> dict[str, Any]:
    """Get household statistics."""
    return await get_client().get_household_statistics(get_user_token())

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Update Household Preferences", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_household_preferences(
    privateHousehold: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Update the current household's preferences.

    Args:
        privateHousehold: true = private (hidden), false = public. Default: false.
    """
    return await get_client().update_household_preferences(
        {"privateHousehold": privateHousehold}, get_user_token()
    )

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Set Household Permissions", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def set_household_permissions(
    userId: str,
    canManage: bool = False,
    canManageHousehold: bool = False,
    canInvite: bool = False,
    canOrganize: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Set household permissions for a user.

    Args:
        userId: The ID of the user to set permissions for.
        canManage: true = manage members (add/remove/roles). Default: false.
        canManageHousehold: true = manage household prefs/settings. Default: false.
        canInvite: true = can invite members. Default: false.
        canOrganize: true = organize recipes/categories/tags. Default: false.
    """
    params = SetHouseholdPermissionsParam(
        userId=userId, canManage=canManage, canManageHousehold=canManageHousehold,
        canInvite=canInvite, canOrganize=canOrganize
    )
    return await get_client().set_household_permissions(
        _require_update_payload(params.model_dump(exclude_unset=True, exclude_none=True)),
        get_user_token()
    )

# =============================================================================
# Admin User CRUD
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Create User", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_user(
    username: str,
    fullName: str,
    email: str,
    password: str,
    admin: bool = False,
    group: str = None,
    household: str = None,
    canInvite: bool = False,
    canManage: bool = False,
    canManageHousehold: bool = False,
    canOrganize: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new user via the admin API.

    Args:
        username: Username for the new user.
        fullName: Full display name of the user.
        email: Email address for the user.
        password: Password for the user account.
        admin: true = admin, false = regular user. Default: false.
        group: Group name to assign the user to. Default None.
        household: Household name to assign the user to. Default None.
        canInvite: true = can invite members. Default: false.
        canManage: true = manage members (add/remove/roles). Default: false.
        canManageHousehold: true = manage household prefs/settings. Default: false.
        canOrganize: true = create/edit/delete tags, categories, foods. Default: false.
    """
    params = CreateUserParam(
        username=username, fullName=fullName, email=email, password=password,
        admin=admin, group=group, household=household,
        canInvite=canInvite, canManage=canManage, canManageHousehold=canManageHousehold, canOrganize=canOrganize
    )
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    return await get_client().admin_create_user(payload, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get User By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_user_by_id(
    userId: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a user by ID via the admin API.

    Args:
        userId: The UUID of the user to retrieve.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().admin_get_user(
        userId, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Update User", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_user(
    userId: str,
    username: str,
    fullName: str,
    email: str,
    admin: bool = False,
    group: str = None,
    household: str = None,
    canInvite: bool = False,
    canManage: bool = False,
    canManageHousehold: bool = False,
    canOrganize: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing user via the admin API.

    Args:
        userId: The UUID of the user to update.
        username: Username for the user.
        fullName: Full display name of the user.
        email: Email address for the user.
        admin: true = admin, false = regular user. Default: false.
        group: Group name to assign the user to. Default None.
        household: Household name to assign the user to. Default None.
        canInvite: true = can invite members. Default: false.
        canManage: true = manage members (add/remove/roles). Default: false.
        canManageHousehold: true = manage household prefs/settings. Default: false.
        canOrganize: true = create/edit/delete tags, categories, foods. Default: false.
    """
    params = UpdateUserParam(
        username=username, fullName=fullName, email=email, admin=admin,
        group=group, household=household,
        canInvite=canInvite, canManage=canManage, canManageHousehold=canManageHousehold, canOrganize=canOrganize
    )
    current = await get_client().admin_get_user_raw(userId, get_user_token())
    payload = dict(current)
    payload.update(params.model_dump(exclude_unset=True, exclude_none=True))
    payload["tokens"] = current.get("tokens") or []
    return await get_client().put_raw(f"/api/admin/users/{userId}", get_user_token(), json=payload)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Delete User", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_user(
    userId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a user by ID via the admin API.

    Args:
        userId: The UUID of the user to delete.
    """
    return await get_client().admin_delete_user(userId, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List Users", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_users(
    page: int = 1,
    perPage: int = 50,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all users via the admin API.

    Args:
        page: Page number for pagination. Default 1.
        perPage: Number of results per page. Default 50.
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    page, perPage = _validate_pagination(page, perPage)
    return _page_response(await get_client().admin_list_users(page, perPage, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

# =============================================================================
# Admin Group CRUD
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Create Group", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_group(
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new group via the admin API.

    Args:
        name: Name of the group.
    """
    return await get_client().admin_create_group({"name": name}, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Group By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_group_by_id(
    groupId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a group by ID via the admin API.

    Args:
        groupId: The UUID of the group to retrieve.
    """
    return await get_client().admin_get_group(groupId, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Update Group", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_group(
    groupId: str,
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing group via the admin API.

    Args:
        groupId: The UUID of the group to update.
        name: New name for the group.
    """
    params = UpdateGroupParam(id=groupId, name=name)
    return await get_client().admin_update_group(groupId, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Delete Group", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_group(
    groupId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a group by ID via the admin API. Fails if group has users.

    Args:
        groupId: The UUID of the group to delete.
    """
    return await get_client().admin_delete_group(groupId, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List Groups", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_groups(
    page: int = 1,
    perPage: int = 50,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all groups via the admin API.

    Args:
        page: Page number for pagination. Default 1.
        perPage: Number of results per page. Default 50.
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    page, perPage = _validate_pagination(page, perPage)
    return _page_response(await get_client().admin_list_groups(page, perPage, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

# =============================================================================
# Admin Household CRUD
# =============================================================================

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Create Household", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_household(
    name: str,
    groupId: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new household via the admin API.

    Args:
        name: Name of the household.
        groupId: Group UUID to assign the household to. Default None.
    """
    params = CreateHouseholdParam(name=name, groupId=groupId)
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    return await get_client().admin_create_household(payload, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Get Household By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_household_by_id(
    householdId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a household by ID via the admin API.

    Args:
        householdId: The UUID of the household to retrieve.
    """
    return await get_client().admin_get_household(householdId, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Update Household", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_household(
    householdId: str,
    name: str,
    groupId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing household via the admin API.

    Args:
        householdId: The UUID of the household to update.
        name: New name for the household.
        groupId: Group UUID the household belongs to.
    """
    params = UpdateHouseholdParam(id=householdId, name=name, groupId=groupId)
    return await get_client().admin_update_household(householdId, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Delete Household", readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
)
async def delete_household(
    householdId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a household by ID via the admin API. Fails if household has users.

    Args:
        householdId: The UUID of the household to delete.
    """
    return await get_client().admin_delete_household(householdId, get_user_token())

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="List All Households", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_households(
    page: int = 1,
    perPage: int = 50,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all households via the admin API.

    Args:
        page: Page number for pagination. Default 1.
        perPage: Number of results per page. Default 50.
        include_all_fields: Default False (common fields only). Set True for all fields.
            On aggregate list calls this is honored only when ALLOW_ALL_AGGREGATE=true;
            otherwise it is intentionally ignored to bound response size.
    """
    page, perPage = _validate_pagination(page, perPage)
    return _page_response(await get_client().admin_list_households(page, perPage, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False))

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Get App About", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_app_about(
    ctx: Context = None
) -> dict[str, Any]:
    """Get general application information (version, demo status, etc.)."""
    return await get_client().get_app_about(get_user_token())

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Get App Startup Info", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_app_startup_info(
    ctx: Context = None
) -> dict[str, Any]:
    """Get application startup information."""
    return await get_client().get_app_startup_info(get_user_token())

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Get App Theme", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_app_theme(
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current application theme settings."""
    return await get_client().get_app_theme(get_user_token())

# =============================================================================
# Domain Utilities
# =============================================================================

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Parse Ingredient", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def parse_ingredient(
    ingredient: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Parse a single ingredient string into structured data.

    Args:
        ingredient: The ingredient text to parse.
    """
    return await get_client().parse_ingredient(ingredient, get_user_token())

@mcp.tool(
    tags={"primary", "mealie"}, annotations=ToolAnnotations(title="Parse Ingredients", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def parse_ingredients(
    ingredients: list[str],
    ctx: Context = None
) -> dict[str, Any]:
    """Parse multiple ingredient strings into structured data.

    Args:
        ingredients: List of ingredient strings to parse.
    """
    data = await get_client().parse_ingredients(ingredients, get_user_token())
    return {"results": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Seed Default Foods", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def seed_default_foods(
    locale: str = "en-US",
    ctx: Context = None
) -> dict[str, Any]:
    """Seed default foods into the database.

    Args:
        locale: Locale for the seeded data (e.g. "en-US"). Defaults to "en-US".
    """
    return await get_client().seed_default_foods(get_user_token(), locale=locale)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Seed Default Labels", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def seed_default_labels(
    locale: str = "en-US",
    ctx: Context = None
) -> dict[str, Any]:
    """Seed default labels into the database.

    Args:
        locale: Locale for the seeded data (e.g. "en-US"). Defaults to "en-US".
    """
    return await get_client().seed_default_labels(get_user_token(), locale=locale)

@mcp.tool(
    tags={"advanced", "mealie"}, annotations=ToolAnnotations(title="Seed Default Units", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def seed_default_units(
    locale: str = "en-US",
    ctx: Context = None
) -> dict[str, Any]:
    """Seed default units into the database.

    Args:
        locale: Locale for the seeded data (e.g. "en-US"). Defaults to "en-US".
    """
    return await get_client().seed_default_units(get_user_token(), locale=locale)

@mcp.tool(
    tags={"basic", "mealie"}, annotations=ToolAnnotations(title="Check Server Status", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def check_server_status(ctx: Context = None) -> dict[str, Any]:
    """Check connectivity and authentication against the Mealie backend."""
    token = get_user_token()
    if not token:
        return {
            "status": "unauthenticated",
            "error": "Missing Authorization bearer token",
        }
    client = get_client()
    try:
        profile = await client.get("/api/users/self", token)
        return {
            "status": "connected",
            "backend_response": 200,
            "username": (profile or {}).get("username", ""),
            "admin": bool((profile or {}).get("admin")),
        }
    except Exception as exc:
        response = getattr(exc, "response", None)
        code = getattr(response, "status_code", None)
        if code in (401, 403):
            return {
                "status": "unauthorized",
                "backend_response": code,
                "error": str(exc)[:300],
            }
        return {"status": "disconnected", "error": str(exc)[:300]}

# =============================================================================
# Entry Point
# =============================================================================

def main():
    if not os.getenv("MEALIE_BASE_URL"):
        print("ERROR: MEALIE_BASE_URL environment variable is required", file=sys.stderr)
        print("Example: export MEALIE_BASE_URL=http://mealie-app:9000", file=sys.stderr)
        sys.exit(1)

    port_env = os.getenv("MCP_SERVER_PORT")
    if not port_env:
        print("ERROR: MCP_SERVER_PORT environment variable is required", file=sys.stderr)
        print("Example: export MCP_SERVER_PORT=6059", file=sys.stderr)
        sys.exit(1)

    host = "0.0.0.0"
    port = int(port_env)
    path = "/mcp"
    if IS_STATEFUL:
        app = mcp.http_app(path=path)
    else:
        app = mcp.http_app(path=path, stateless_http=True)
    app = AuthMiddleware(app)
    print(f"Starting Mealie MCP server on http://{host}:{port}{path} (stateful={IS_STATEFUL})")
    import uvicorn
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
