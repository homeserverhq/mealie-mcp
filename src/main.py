import datetime as dt
import os
import sys
from contextvars import ContextVar
from typing import Any, Optional

from fastmcp import FastMCP, Context
from pydantic import BaseModel
from toon_mcp import json_to_toon

from .client import MealieClient

_current_user_token: ContextVar[Optional[str]] = ContextVar("current_user_token", default=None)

ALLOW_ALL_AGGREGATE = os.getenv("ALLOW_ALL_AGGREGATE", "false").lower() in ("true", "1", "yes")


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
    recipeCategory: list = []
    tags: list = []
    tools: list = []
    recipeIngredient: list = []
    recipeInstructions: list = []
    nutrition: dict = {}
    settings: dict = {}
    notes: list = []
    extras: dict = {}
    image: str = ""

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
    recipeCategory: Optional[list] = None
    tags: Optional[list] = None
    tools: Optional[list] = None
    recipeIngredient: Optional[list] = None
    recipeInstructions: Optional[list] = None
    nutrition: Optional[dict] = None
    settings: Optional[dict] = None
    notes: Optional[list] = None
    extras: Optional[dict] = None
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
    aliases: list = []

class UpdateFoodParam(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pluralName: Optional[str] = None
    aliases: Optional[list] = None

class CreateUnitParam(BaseModel):
    name: str
    abbreviation: str = ""
    pluralName: str = ""
    pluralAbbreviation: str = ""
    description: str = ""
    fraction: bool = False
    useAbbreviation: bool = False
    aliases: list = []

class UpdateUnitParam(BaseModel):
    name: Optional[str] = None
    abbreviation: Optional[str] = None
    pluralName: Optional[str] = None
    pluralAbbreviation: Optional[str] = None
    description: Optional[str] = None
    fraction: Optional[bool] = None
    useAbbreviation: Optional[bool] = None
    aliases: Optional[list] = None

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

class CreateMealplanParam(BaseModel):
    date: str
    entryType: str = "dinner"
    title: str = ""
    recipeId: str = ""
    text: str = ""

class UpdateMealplanParam(BaseModel):
    date: Optional[str] = None
    entryType: Optional[str] = None
    title: Optional[str] = None
    recipeId: Optional[str] = None
    text: Optional[str] = None

class CreateShoppingListParam(BaseModel):
    name: str
    extras: dict = {}

class UpdateShoppingListParam(BaseModel):
    name: Optional[str] = None
    extras: Optional[dict] = None

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
    extras: dict = {}

class UpdateShoppingItemParam(BaseModel):
    quantity: Optional[float] = None
    note: Optional[str] = None
    display: Optional[str] = None
    checked: Optional[bool] = None
    position: Optional[int] = None
    foodId: Optional[str] = None
    labelId: Optional[str] = None
    unitId: Optional[str] = None
    extras: Optional[dict] = None

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

# =============================================================================
# Recipes
# =============================================================================

@mcp.tool()
async def get_all_recipes(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    search: str = "",
    cookbook: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipes in your Mealie instance.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
        search: Search query to filter recipes by name or description.
        cookbook: Filter recipes by cookbook slug.
    """
    data = await get_client().get_all_recipes(
        get_user_token(),
        page=page, perPage=perPage, search=search, cookbook=cookbook,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_recipe_by_slug(
    slug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single recipe by its slug.
    Args:
        slug: The unique slug of the recipe (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_recipe_by_slug(slug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
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
    recipeCategory: list = [],
    tags: list = [],
    tools: list = [],
    recipeIngredient: list = [],
    recipeInstructions: list = [],
    nutrition: dict = {},
    settings: dict = {},
    notes: list = [],
    extras: dict = {},
    image: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new recipe.
    Args:
        name: Name of the recipe (required).
        description: Description of the recipe.
        recipeServings: Number of servings.
        totalTime: Total cooking time (e.g. "30 minutes").
        prepTime: Preparation time.
        cookTime: Cooking time.
        performTime: Active/performance time.
        recipeYield: Yield amount text.
        recipeYieldQuantity: Yield quantity number.
        orgURL: Original URL the recipe was sourced from.
        recipeCategory: List of category IDs or names.
        tags: List of tag IDs or names.
        tools: List of tool IDs or names.
        recipeIngredient: List of ingredient objects with quantity, unit, note, food, display fields.
        recipeInstructions: List of instruction objects with text and optional position, title fields.
        nutrition: Nutrition information object.
        settings: Recipe settings object.
        notes: List of note objects.
        extras: Custom key-value pairs for extended data.
        image: Image URL to scrape.
    """
    params = CreateRecipeParam(
        name=name, description=description, recipeServings=recipeServings,
        totalTime=totalTime, prepTime=prepTime, cookTime=cookTime,
        performTime=performTime, recipeYield=recipeYield,
        recipeYieldQuantity=recipeYieldQuantity, orgURL=orgURL,
        recipeCategory=recipeCategory, tags=tags, tools=tools,
        recipeIngredient=recipeIngredient, recipeInstructions=recipeInstructions,
        nutrition=nutrition, settings=settings, notes=notes,
        extras=extras, image=image,
    )
    data = await get_client().create_recipe(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )
    if isinstance(data, dict):
        return {"slug": data.get("slug", ""), "id": data.get("id", ""), "status": "created"}
    slug = str(data)
    recipe = await get_client().get_recipe_by_slug(slug, get_user_token())
    if isinstance(recipe, dict):
        return {"slug": recipe.get("slug", slug), "id": recipe.get("id", ""), "status": "created"}
    return {"slug": slug, "status": "created"}

@mcp.tool()
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
    recipeCategory: list = None,
    tags: list = None,
    tools: list = None,
    recipeIngredient: list = None,
    recipeInstructions: list = None,
    nutrition: dict = None,
    settings: dict = None,
    notes: list = None,
    extras: dict = None,
    image: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing recipe.
    Args:
        slug: The unique slug of the recipe to update (required).
        name: Name of the recipe.
        description: Description of the recipe.
        recipeServings: Number of servings.
        totalTime: Total cooking time.
        prepTime: Preparation time.
        cookTime: Cooking time.
        performTime: Active/performance time.
        recipeYield: Yield amount text.
        recipeYieldQuantity: Yield quantity number.
        orgURL: Original URL the recipe was sourced from.
        recipeCategory: List of category IDs or names.
        tags: List of tag IDs or names.
        tools: List of tool IDs or names.
        recipeIngredient: List of ingredient objects.
        recipeInstructions: List of instruction objects.
        nutrition: Nutrition information object.
        settings: Recipe settings object.
        notes: List of note objects.
        extras: Custom key-value pairs.
        image: Image URL to scrape.
    """
    params = UpdateRecipeParam(
        name=name, description=description, recipeServings=recipeServings,
        totalTime=totalTime, prepTime=prepTime, cookTime=cookTime,
        performTime=performTime, recipeYield=recipeYield,
        recipeYieldQuantity=recipeYieldQuantity, orgURL=orgURL,
        recipeCategory=recipeCategory, tags=tags, tools=tools,
        recipeIngredient=recipeIngredient, recipeInstructions=recipeInstructions,
        nutrition=nutrition, settings=settings, notes=notes,
        extras=extras, image=image,
    )
    return await get_client().patch_recipe(
        slug, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_recipe_by_slug(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a recipe by its slug.
    Args:
        slug: The unique slug of the recipe to delete (required).
    """
    return await get_client().delete_recipe_by_slug(slug, get_user_token())

@mcp.tool()
async def duplicate_recipe(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Duplicate an existing recipe.
    Args:
        slug: The slug of the recipe to duplicate (required).
    """
    return await get_client().duplicate_recipe(slug, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool()
async def update_recipe_last_made(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Update the 'last made' timestamp for a recipe.
    Args:
        slug: The slug of the recipe (required).
    """
    return await get_client().update_recipe_last_made(slug, get_user_token())

@mcp.tool()
async def bulk_update_recipe_settings(
    recipes: list,
    settings: dict = {},
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk update settings for multiple recipes.
    Args:
        recipes: List of recipe slugs (required).
        settings: Settings dict to apply to all recipes (required).
    """
    return await get_client().bulk_update_recipe_settings(recipes, settings, get_user_token())

@mcp.tool()
async def get_recipe_suggestions(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get recipe suggestions based on available foods and tools."""
    return await get_client().get_recipe_suggestions(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool()
async def create_recipe_from_url(
    url: str,
    includeTags: bool = True,
    includeNutrition: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a recipe by scraping a URL.
    Args:
        url: The URL of the recipe to scrape (required).
        includeTags: Whether to include tags from the scraped data. Defaults to True.
        includeNutrition: Whether to include nutrition data. Defaults to False.
    """
    result = await get_client().create_recipe_from_url(
        url, get_user_token(), includeTags=includeTags, includeNutrition=includeNutrition
    )
    if isinstance(result, str):
        return {"slug": result}
    return result if isinstance(result, dict) else {"result": result}

@mcp.tool()
async def create_recipe_from_url_bulk(
    urls: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk create recipes by scraping multiple URLs.
    Args:
        urls: List of recipe URLs to scrape (required).
    """
    return await get_client().create_recipe_from_url_bulk(urls, get_user_token())

@mcp.tool()
async def create_recipe_from_html_or_json(
    data: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a recipe from raw HTML or JSON-LD data.
    Args:
        data: HTML content or JSON-LD recipe data (required).
    """
    result = await get_client().create_recipe_from_html_or_json(data, get_user_token())
    if isinstance(result, str):
        return {"slug": result}
    return result if isinstance(result, dict) else {"result": result}

@mcp.tool()
async def test_scrape_url(
    url: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Test-scrape a URL to see what data would be extracted (debug endpoint).
    Args:
        url: The URL to test-scrape (required).
    """
    result = await get_client().test_scrape_url(url, get_user_token())
    return {"result": result}

@mcp.tool()
async def scrape_recipe_image_url(
    slug: str,
    url: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Scrape an image URL into a recipe.
    Args:
        slug: The slug of the recipe (required).
        url: The image URL to scrape (required).
    """
    return await get_client().scrape_recipe_image_url(slug, url, get_user_token())

@mcp.tool()
async def delete_recipe_image(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a recipe's image.
    Args:
        slug: The slug of the recipe (required).
    """
    return await get_client().delete_recipe_image(slug, get_user_token())

@mcp.tool()
async def get_recipe_export_formats(
    ctx: Context = None
) -> dict[str, Any]:
    """Get available export formats and templates for recipes."""
    return await get_client().get_recipe_export_formats(get_user_token())

@mcp.tool()
async def export_recipe(
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Export a recipe in a specific format.
    Args:
        slug: The slug of the recipe to export (required).
    """
    return await get_client().export_recipe(slug, get_user_token())

@mcp.tool()
async def bulk_tag_recipes(
    recipes: list,
    tags: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk assign tags to recipes.
    Args:
        recipes: List of recipe IDs or slugs to tag (required).
        tags: List of tag objects with id or name (required).
    """
    return await get_client().bulk_tag_recipes(recipes, tags, get_user_token())

@mcp.tool()
async def bulk_categorize_recipes(
    recipes: list,
    categories: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk assign categories to recipes.
    Args:
        recipes: List of recipe IDs or slugs to categorize (required).
        categories: List of category objects with id or name (required).
    """
    return await get_client().bulk_categorize_recipes(recipes, categories, get_user_token())

@mcp.tool()
async def bulk_delete_recipes(
    recipes: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk delete recipes.
    Args:
        recipes: List of recipe slugs to delete (required).
    """
    await get_client().bulk_delete_recipes(recipes, get_user_token())
    return {"status": "deleted", "count": len(recipes)}

@mcp.tool()
async def bulk_export_recipes(
    recipes: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk export recipes.
    Args:
        recipes: List of recipe slugs to export (required).
    """
    result = await get_client().bulk_export_recipes(recipes, get_user_token())
    return {"status": "exported", "result": result}

@mcp.tool()
async def list_exports(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all bulk export data files."""
    data = await get_client().list_exports(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"exports": data if isinstance(data, list) else []}

@mcp.tool()
async def purge_exports(
    ctx: Context = None
) -> dict[str, Any]:
    """Purge all bulk export data files."""
    return await get_client().purge_exports(get_user_token())

# =============================================================================
# Categories
# =============================================================================

@mcp.tool()
async def get_all_categories(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe categories.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_categories(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_category_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single category by its ID.
    Args:
        id: The unique ID of the category (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_category_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_category_by_slug(
    slug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single category by its slug.
    Args:
        slug: The unique slug of the category (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_category_by_slug(slug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_empty_categories(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List categories that have no associated recipes."""
    data = await get_client().get_empty_categories(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"items": json_to_toon(data)}

@mcp.tool()
async def create_category(
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new category.
    Args:
        name: Name of the category (required).
    """
    params = CreateCategoryParam(name=name)
    return await get_client().create_category(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_category(
    id: str,
    name: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing category.
    Args:
        id: The ID of the category to update (required).
        name: New name for the category.
    """
    params = UpdateCategoryParam(name=name)
    return await get_client().update_category(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_category_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a category by its ID.
    Args:
        id: The unique ID of the category to delete (required).
    """
    return await get_client().delete_category_by_id(id, get_user_token())

# =============================================================================
# Tags
# =============================================================================

@mcp.tool()
async def get_all_tags(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe tags.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_tags(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_tag_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tag by its ID.
    Args:
        id: The unique ID of the tag (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_tag_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_tag_by_slug(
    slug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tag by its slug.
    Args:
        slug: The unique slug of the tag (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_tag_by_slug(slug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_empty_tags(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List tags that have no associated recipes."""
    data = await get_client().get_empty_tags(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"items": json_to_toon(data)}

@mcp.tool()
async def create_tag(
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new tag.
    Args:
        name: Name of the tag (required).
    """
    params = CreateTagParam(name=name)
    return await get_client().create_tag(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_tag(
    id: str,
    name: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing tag.
    Args:
        id: The ID of the tag to update (required).
        name: New name for the tag.
    """
    params = UpdateTagParam(name=name)
    return await get_client().update_tag(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_tag_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a tag by its ID.
    Args:
        id: The unique ID of the tag to delete (required).
    """
    return await get_client().delete_tag_by_id(id, get_user_token())

# =============================================================================
# Tools
# =============================================================================

@mcp.tool()
async def get_all_tools(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe tools.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_tools(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_tool_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tool by its ID.
    Args:
        id: The unique ID of the tool (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_tool_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_tool_by_slug(
    slug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tool by its slug.
    Args:
        slug: The unique slug of the tool (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_tool_by_slug(slug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_tool(
    name: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new tool.
    Args:
        name: Name of the tool (required).
    """
    params = CreateToolParam(name=name)
    return await get_client().create_tool(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_tool(
    id: str,
    name: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing tool.
    Args:
        id: The ID of the tool to update (required).
        name: New name for the tool.
    """
    params = UpdateToolParam(name=name)
    return await get_client().update_tool(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_tool_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a tool by its ID.
    Args:
        id: The unique ID of the tool to delete (required).
    """
    return await get_client().delete_tool_by_id(id, get_user_token())

# =============================================================================
# Foods
# =============================================================================

@mcp.tool()
async def get_all_foods(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all ingredient foods.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_foods(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_food_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single food by its ID.
    Args:
        id: The unique ID of the food (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_food_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_food(
    name: str,
    description: str = "",
    pluralName: str = "",
    aliases: list = [],
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new ingredient food.
    Args:
        name: Name of the food (required).
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

@mcp.tool()
async def update_food(
    id: str,
    name: str = None,
    description: str = None,
    pluralName: str = None,
    aliases: list = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing food.
    Args:
        id: The ID of the food to update (required).
        name: New name for the food.
        description: New description.
        pluralName: New plural name.
        aliases: New list of aliases.
    """
    params = UpdateFoodParam(
        name=name, description=description, pluralName=pluralName, aliases=aliases
    )
    return await get_client().update_food(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_food_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a food by its ID.
    Args:
        id: The unique ID of the food to delete (required).
    """
    return await get_client().delete_food_by_id(id, get_user_token())

@mcp.tool()
async def merge_foods(
    food_to_keep: str,
    food_to_merge: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Merge two foods together.
    Args:
        food_to_keep: ID of the food to keep (required).
        food_to_merge: ID of the food to merge into the kept food (required).
    """
    return await get_client().merge_foods(food_to_keep, food_to_merge, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

# =============================================================================
# Units
# =============================================================================

@mcp.tool()
async def get_all_units(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all ingredient units.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_units(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_unit_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single unit by its ID.
    Args:
        id: The unique ID of the unit (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_unit_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_unit(
    name: str,
    abbreviation: str = "",
    pluralName: str = "",
    pluralAbbreviation: str = "",
    description: str = "",
    fraction: bool = False,
    useAbbreviation: bool = False,
    aliases: list = [],
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new ingredient unit.
    Args:
        name: Name of the unit (required).
        abbreviation: Abbreviation for the unit.
        pluralName: Plural name of the unit.
        pluralAbbreviation: Plural abbreviation.
        description: Description of the unit.
        fraction: Whether to display as fraction.
        useAbbreviation: Whether to use abbreviation in display.
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

@mcp.tool()
async def update_unit(
    id: str,
    name: str = None,
    abbreviation: str = None,
    pluralName: str = None,
    pluralAbbreviation: str = None,
    description: str = None,
    fraction: bool = None,
    useAbbreviation: bool = None,
    aliases: list = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing unit.
    Args:
        id: The ID of the unit to update (required).
        name: New name.
        abbreviation: New abbreviation.
        pluralName: New plural name.
        pluralAbbreviation: New plural abbreviation.
        description: New description.
        fraction: Whether to display as fraction.
        useAbbreviation: Whether to use abbreviation.
        aliases: New list of aliases.
    """
    params = UpdateUnitParam(
        name=name, abbreviation=abbreviation, pluralName=pluralName,
        pluralAbbreviation=pluralAbbreviation, description=description,
        fraction=fraction, useAbbreviation=useAbbreviation, aliases=aliases
    )
    return await get_client().update_unit(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_unit_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a unit by its ID.
    Args:
        id: The unique ID of the unit to delete (required).
    """
    return await get_client().delete_unit_by_id(id, get_user_token())

@mcp.tool()
async def merge_units(
    unit_to_keep: str,
    unit_to_merge: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Merge two units together.
    Args:
        unit_to_keep: ID of the unit to keep (required).
        unit_to_merge: ID of the unit to merge into the kept unit (required).
    """
    return await get_client().merge_units(unit_to_keep, unit_to_merge, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

# =============================================================================
# Comments
# =============================================================================

@mcp.tool()
async def get_all_comments(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe comments.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_comments(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_comment_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single comment by its ID.
    Args:
        id: The unique ID of the comment (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_comment_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_comment(
    recipeId: str,
    text: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new comment on a recipe.
    Args:
        recipeId: The ID of the recipe to comment on (required).
        text: The comment text (required).
    """
    params = CreateCommentParam(recipeId=recipeId, text=text)
    return await get_client().create_comment(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_comment(
    id: str,
    text: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing comment.
    Args:
        id: The ID of the comment to update (required).
        text: New text for the comment.
    """
    params = UpdateCommentParam(text=text)
    return await get_client().update_comment(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_comment_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a comment by its ID.
    Args:
        id: The unique ID of the comment to delete (required).
    """
    return await get_client().delete_comment_by_id(id, get_user_token())

# =============================================================================
# Cookbooks
# =============================================================================

@mcp.tool()
async def get_all_cookbooks(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all cookbooks.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_cookbooks(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_cookbook_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single cookbook by its ID.
    Args:
        id: The unique ID of the cookbook (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_cookbook_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
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
        name: Name of the cookbook (required).
        description: Description of the cookbook.
        position: Display position. Defaults to 0.
        public: Whether the cookbook is public. Defaults to False.
        queryFilterString: Filter string for cookbook content.
    """
    params = CreateCookbookParam(
        name=name, description=description, position=position,
        public=public, queryFilterString=queryFilterString
    )
    return await get_client().create_cookbook(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
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
        id: The ID of the cookbook to update (required).
        name: New name.
        description: New description.
        position: New display position.
        public: Whether the cookbook is public.
        queryFilterString: New filter string.
    """
    params = UpdateCookbookParam(
        name=name, description=description, position=position,
        public=public, queryFilterString=queryFilterString
    )
    return await get_client().update_cookbook(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_cookbook_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a cookbook by its ID.
    Args:
        id: The unique ID of the cookbook to delete (required).
    """
    return await get_client().delete_cookbook_by_id(id, get_user_token())

@mcp.tool()
async def update_cookbooks(
    cookbooks: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk reorder or update cookbooks.
    Args:
        cookbooks: List of cookbook objects with id, position, etc. (required).
    """
    return await get_client().update_cookbooks(cookbooks, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

# =============================================================================
# Mealplans
# =============================================================================

@mcp.tool()
async def get_all_mealplans(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    startDate: str = "",
    endDate: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """List all mealplan entries.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
        startDate: Filter entries from this date (YYYY-MM-DD).
        endDate: Filter entries until this date (YYYY-MM-DD).
    """
    data = await get_client().get_all_mealplans(
        get_user_token(), page=page, perPage=perPage,
        start_date=startDate, end_date=endDate,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_mealplan_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single mealplan entry by its ID.
    Args:
        id: The unique ID of the mealplan entry (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_mealplan_by_id(str(id), get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_todays_meals(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get today's mealplans."""
    data = await get_client().get_todays_meals(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"meals": data if isinstance(data, list) else []}

@mcp.tool()
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
        date: Date of the mealplan entry (YYYY-MM-DD) (required).
        entryType: Type of meal (breakfast, lunch, dinner, side). Defaults to "dinner".
        title: Title of the mealplan entry.
        recipeId: ID of the associated recipe.
        text: Additional text for the entry.
    """
    data = {"date": date, "entryType": entryType, "title": title}
    if recipeId:
        data["recipeId"] = recipeId
    if text:
        data["text"] = text
    return await get_client().create_mealplan(
        data, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def create_random_mealplan(
    date: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a random mealplan entry using configured rules.
    Args:
        date: Date for the mealplan entry (YYYY-MM-DD). Defaults to today.
    """
    if not date:
        date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return await get_client().create_random_mealplan({"date": date}, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool()
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
        id: The ID of the mealplan entry to update (required).
        date: New date (YYYY-MM-DD).
        entryType: New meal type (breakfast, lunch, dinner, side).
        title: New title.
        recipeId: New recipe ID.
        text: New additional text.
    """
    params = UpdateMealplanParam(
        date=date, entryType=entryType, title=title,
        recipeId=recipeId, text=text
    )
    return await get_client().update_mealplan(
        str(id), params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_mealplan_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a mealplan entry by its ID.
    Args:
        id: The unique ID of the mealplan entry to delete (required).
    """
    return await get_client().delete_mealplan_by_id(str(id), get_user_token())

# =============================================================================
# Mealplan Rules
# =============================================================================

@mcp.tool()
async def get_all_mealplan_rules(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all mealplan rules.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_mealplan_rules(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_mealplan_rule_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single mealplan rule by ID.
    Args:
        id: The unique ID of the mealplan rule (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_mealplan_rule_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_mealplan_rule(
    day: str,
    entryType: str = "dinner",
    queryFilterString: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new mealplan rule.
    Args:
        day: Day of the week (monday, tuesday, etc.) (required).
        entryType: Type of meal (breakfast, lunch, dinner, side). Defaults to "dinner".
        queryFilterString: Filter string for recipe selection.
    """
    params = CreateMealplanRuleParam(day=day, entryType=entryType, queryFilterString=queryFilterString)
    return await get_client().create_mealplan_rule(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_mealplan_rule(
    id: str,
    day: str = None,
    entryType: str = None,
    queryFilterString: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing mealplan rule.
    Args:
        id: The ID of the mealplan rule to update (required).
        day: New day of the week.
        entryType: New meal type.
        queryFilterString: New filter string.
    """
    params = UpdateMealplanRuleParam(day=day, entryType=entryType, queryFilterString=queryFilterString)
    return await get_client().update_mealplan_rule(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_mealplan_rule_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a mealplan rule by its ID.
    Args:
        id: The unique ID of the mealplan rule to delete (required).
    """
    return await get_client().delete_mealplan_rule_by_id(id, get_user_token())

# =============================================================================
# Shopping Lists
# =============================================================================

@mcp.tool()
async def get_all_shopping_lists(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all shopping lists.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_shopping_lists(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_shopping_list_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single shopping list by its ID.
    Args:
        id: The unique ID of the shopping list (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_shopping_list_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_shopping_list(
    name: str,
    extras: dict = {},
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new shopping list.
    Args:
        name: Name of the shopping list (required).
        extras: Custom key-value pairs for extended data.
    """
    params = CreateShoppingListParam(name=name, extras=extras)
    return await get_client().create_shopping_list(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_shopping_list(
    id: str,
    name: str = None,
    extras: dict = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing shopping list.
    Args:
        id: The ID of the shopping list to update (required).
        name: New name.
        extras: New custom key-value pairs.
    """
    params = UpdateShoppingListParam(name=name, extras=extras)
    return await get_client().update_shopping_list(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_shopping_list_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a shopping list by its ID.
    Args:
        id: The unique ID of the shopping list to delete (required).
    """
    return await get_client().delete_shopping_list_by_id(id, get_user_token())

@mcp.tool()
async def update_shopping_list_label_settings(
    id: str,
    labelId: str = "",
    fontSize: float = 12.0,
    fontFamily: str = "Arial",
    ctx: Context = None
) -> dict[str, Any]:
    """Update label settings for a shopping list.
    Args:
        id: The ID of the shopping list (required).
        labelId: The label ID to associate.
        fontSize: Font size for labels. Defaults to 12.0.
        fontFamily: Font family for labels. Defaults to "Arial".
    """
    import uuid
    payload = {"id": str(uuid.uuid4()), "shoppingListId": id, "fontSize": fontSize, "fontFamily": fontFamily}
    payload["labelId"] = labelId if labelId else str(uuid.uuid4())
    return await get_client().update_shopping_list_label_settings(id, payload, get_user_token())

@mcp.tool()
async def add_recipe_to_shopping_list(
    id: str,
    recipeId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Add recipe ingredients to a shopping list.
    Args:
        id: The ID of the shopping list (required).
        recipeId: The ID of the recipe whose ingredients to add (required).
    """
    return await get_client().add_recipe_to_shopping_list(id, recipeId, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool()
async def remove_recipe_from_shopping_list(
    id: str,
    recipeId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Remove recipe ingredients from a shopping list.
    Args:
        id: The ID of the shopping list (required).
        recipeId: The ID of the recipe whose ingredients to remove (required).
    """
    return await get_client().remove_recipe_from_shopping_list(id, recipeId, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

# =============================================================================
# Shopping Items
# =============================================================================

@mcp.tool()
async def get_all_shopping_items(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all shopping list items.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_shopping_items(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_shopping_item_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single shopping list item by its ID.
    Args:
        id: The unique ID of the shopping item (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_shopping_item_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
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
    extras: dict = {},
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new shopping list item.
    Args:
        shoppingListId: The ID of the shopping list (required).
        quantity: Item quantity. Defaults to 0.
        note: Note describing the item.
        display: Display text for the item.
        checked: Whether the item is checked off.
        position: Display position. Defaults to 0.
        foodId: ID of the associated food.
        labelId: ID of the associated label.
        unitId: ID of the associated unit.
        extras: Custom key-value pairs.
    """
    params = CreateShoppingItemParam(
        shoppingListId=shoppingListId, quantity=quantity, note=note,
        display=display, checked=checked, position=position,
        foodId=foodId, labelId=labelId, unitId=unitId, extras=extras
    )
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    payload = {k: v for k, v in payload.items() if not (isinstance(v, str) and v == "" and k in ("foodId", "labelId", "unitId"))}
    return await get_client().create_shopping_item(
        payload, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_shopping_item(
    id: str,
    quantity: float = None,
    note: str = None,
    display: str = None,
    checked: bool = None,
    position: int = None,
    foodId: str = None,
    labelId: str = None,
    unitId: str = None,
    extras: dict = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing shopping list item.
    Args:
        id: The ID of the shopping item to update (required).
        quantity: New quantity.
        note: New note.
        display: New display text.
        checked: Whether the item is checked off.
        position: New display position.
        foodId: New food ID.
        labelId: New label ID.
        unitId: New unit ID.
        extras: New custom key-value pairs.
    """
    params = UpdateShoppingItemParam(
        quantity=quantity, note=note, display=display, checked=checked,
        position=position, foodId=foodId, labelId=labelId,
        unitId=unitId, extras=extras
    )
    return await get_client().update_shopping_item(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_shopping_item_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a shopping list item by its ID.
    Args:
        id: The unique ID of the shopping item to delete (required).
    """
    return await get_client().delete_shopping_item_by_id(id, get_user_token())

@mcp.tool()
async def bulk_create_shopping_items(
    items: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk create shopping list items.
    Args:
        items: List of shopping item objects (required).
    """
    return await get_client().bulk_create_shopping_items(items, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool()
async def bulk_update_shopping_items(
    items: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk update shopping list items.
    Args:
        items: List of shopping item objects with id fields (required).
    """
    return await get_client().bulk_update_shopping_items(items, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool()
async def bulk_delete_shopping_items(
    ids: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Bulk delete shopping list items by IDs.
    Args:
        ids: List of shopping item IDs to delete (required).
    """
    return await get_client().bulk_delete_shopping_items(ids, get_user_token())

# =============================================================================
# Labels
# =============================================================================

@mcp.tool()
async def get_all_labels(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all multi-purpose labels.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_labels(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_label_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single label by its ID.
    Args:
        id: The unique ID of the label (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_label_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_label(
    name: str,
    color: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new label.
    Args:
        name: Name of the label (required).
        color: Color hex code for the label.
    """
    params = CreateLabelParam(name=name, color=color)
    return await get_client().create_label(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_label(
    id: str,
    name: str = None,
    color: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing label.
    Args:
        id: The ID of the label to update (required).
        name: New name.
        color: New color hex code.
    """
    params = UpdateLabelParam(name=name, color=color)
    return await get_client().update_label(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_label_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a label by its ID.
    Args:
        id: The unique ID of the label to delete (required).
    """
    return await get_client().delete_label_by_id(id, get_user_token())

# =============================================================================
# Recipe Timeline Events
# =============================================================================

@mcp.tool()
async def get_all_timeline_events(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe timeline events.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_timeline_events(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_timeline_event_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single timeline event by its ID.
    Args:
        id: The unique ID of the timeline event (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_timeline_event_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_timeline_event(
    recipeId: str,
    eventType: str,
    message: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new recipe timeline event.
    Args:
        recipeId: The ID of the recipe (required).
        eventType: Type of event (system, info, comment) (required).
        message: Event message text.
    """
    params = CreateTimelineEventParam(recipeId=recipeId, eventType=eventType, message=message)
    return await get_client().create_timeline_event(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_timeline_event(
    id: str,
    eventType: str = None,
    message: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing timeline event.
    Args:
        id: The ID of the timeline event to update (required).
        eventType: New event type (system, info, comment).
        message: New event message.
    """
    params = UpdateTimelineEventParam(eventType=eventType, message=message)
    return await get_client().update_timeline_event(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_timeline_event_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a timeline event by its ID.
    Args:
        id: The unique ID of the timeline event to delete (required).
    """
    return await get_client().delete_timeline_event_by_id(id, get_user_token())

# =============================================================================
# Shared Recipes
# =============================================================================

@mcp.tool()
async def get_all_shared_recipes(
    include_all_fields: bool = False,
    recipeId: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """List all shared recipe tokens.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        recipeId: Filter by recipe ID.
    """
    data = await get_client().get_all_shared_recipes(
        get_user_token(), recipe_id=recipeId,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_shared_recipe_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a shared recipe by its public token ID.
    Args:
        id: The public token ID of the shared recipe (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_shared_recipe_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_shared_recipe(
    recipeId: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a share token for a recipe.
    Args:
        recipeId: The ID of the recipe to share (required).
    """
    params = CreateSharedRecipeParam(recipeId=recipeId)
    return await get_client().create_shared_recipe(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_shared_recipe_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a shared recipe token.
    Args:
        id: The token ID of the shared recipe to delete (required).
    """
    return await get_client().delete_shared_recipe_by_id(id, get_user_token())

# =============================================================================
# Recipe Actions
# =============================================================================

@mcp.tool()
async def get_all_recipe_actions(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all recipe actions.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_recipe_actions(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_recipe_action_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single recipe action by its ID.
    Args:
        id: The unique ID of the recipe action (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_recipe_action_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_recipe_action(
    name: str,
    recipeActionType: str,
    description: str = "",
    url: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new recipe action.
    Args:
        name: Name of the action (required).
        recipeActionType: Type of action (link, post) (required).
        description: Description of the action.
        url: URL for the action (required for post type).
    """
    payload = {"name": name, "recipeActionType": recipeActionType, "description": description}
    if url:
        payload["url"] = url
    return await get_client().create_recipe_action(
        payload, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_recipe_action(
    id: str,
    name: str = None,
    recipeActionType: str = None,
    description: str = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing recipe action.
    Args:
        id: The ID of the recipe action to update (required).
        name: New name.
        recipeActionType: New action type (link, post).
        description: New description.
    """
    return await get_client().update_recipe_action(
        id, dict(filter(lambda x: x[1] is not None,
            [("name", name), ("recipeActionType", recipeActionType), ("description", description)])),
        get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_recipe_action_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a recipe action by its ID.
    Args:
        id: The unique ID of the recipe action to delete (required).
    """
    return await get_client().delete_recipe_action_by_id(id, get_user_token())

@mcp.tool()
async def trigger_recipe_action(
    id: str,
    recipeSlug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Trigger a recipe action against a specific recipe.
    Args:
        id: The ID of the recipe action to trigger (required).
        recipeSlug: The slug of the recipe to trigger the action on (required).
    """
    return await get_client().trigger_recipe_action(id, recipeSlug, get_user_token())

# =============================================================================
# Event Notifications
# =============================================================================

@mcp.tool()
async def get_all_event_notifications(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all event notification rules.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_event_notifications(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_event_notification_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single event notification by ID.
    Args:
        id: The unique ID of the event notification (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_event_notification_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_event_notification(
    name: str,
    enabled: bool = True,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new event notification rule.
    Args:
        name: Name of the notification (required).
        enabled: Whether the notification is enabled. Defaults to True.
    """
    params = CreateEventNotificationParam(name=name, enabled=enabled)
    return await get_client().create_event_notification(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_event_notification(
    id: str,
    name: str = None,
    enabled: bool = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing event notification.
    Args:
        id: The ID of the event notification to update (required).
        name: New name.
        enabled: Whether the notification is enabled.
    """
    params = UpdateEventNotificationParam(name=name, enabled=enabled)
    return await get_client().update_event_notification(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_event_notification_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete an event notification by its ID.
    Args:
        id: The unique ID of the event notification to delete (required).
    """
    return await get_client().delete_event_notification_by_id(id, get_user_token())

@mcp.tool()
async def test_event_notification(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Test an event notification by sending a test event.
    Args:
        id: The ID of the event notification to test (required).
    """
    return await get_client().test_event_notification(id, get_user_token())

# =============================================================================
# Webhooks
# =============================================================================

@mcp.tool()
async def get_all_webhooks(
    include_all_fields: bool = False,
    page: int = 1,
    perPage: int = 50,
    ctx: Context = None
) -> dict[str, Any]:
    """List all webhooks.
    Args:
        include_all_fields: When False (default), each item contains only commonly used fields. Set to True to include all fields.
        page: Page number for pagination. Defaults to 1.
        perPage: Number of items per page. Defaults to 50.
    """
    data = await get_client().get_all_webhooks(
        get_user_token(), page=page, perPage=perPage,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool()
async def get_webhook_by_id(
    id: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single webhook by ID.
    Args:
        id: The unique ID of the webhook (required).
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_webhook_by_id(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def create_webhook(
    name: str,
    url: str,
    enabled: bool = True,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new webhook.
    Args:
        name: Name of the webhook (required).
        url: The URL to send webhook events to (required).
        enabled: Whether the webhook is enabled. Defaults to True.
    """
    params = CreateWebhookParam(name=name, url=url, enabled=enabled)
    return await get_client().create_webhook(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def update_webhook(
    id: str,
    name: str = None,
    url: str = None,
    enabled: bool = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing webhook.
    Args:
        id: The ID of the webhook to update (required).
        name: New name.
        url: New webhook URL.
        enabled: Whether the webhook is enabled.
    """
    params = UpdateWebhookParam(name=name, url=url, enabled=enabled)
    return await get_client().update_webhook(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def delete_webhook_by_id(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a webhook by its ID.
    Args:
        id: The unique ID of the webhook to delete (required).
    """
    return await get_client().delete_webhook_by_id(id, get_user_token())

@mcp.tool()
async def test_webhook(
    id: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Test a webhook by sending a test event.
    Args:
        id: The ID of the webhook to test (required).
    """
    return await get_client().test_webhook(id, get_user_token())

@mcp.tool()
async def rerun_webhooks(
    ctx: Context = None
) -> dict[str, Any]:
    """Rerun all failed webhook deliveries."""
    return await get_client().rerun_webhooks(get_user_token())

# =============================================================================
# Invitations
# =============================================================================

@mcp.tool()
async def get_all_invitations(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all household invitation tokens."""
    data = await get_client().get_all_invitations(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"invitations": data if isinstance(data, list) else []}

@mcp.tool()
async def create_invitation(
    uses: int,
    groupId: str = "",
    householdId: str = "",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a household invitation token.
    Args:
        uses: Maximum number of times the invitation can be used (required).
        groupId: Group ID to associate with the invitation.
        householdId: Household ID to associate with the invitation.
    """
    return await get_client().create_invitation(
        {"uses": uses, "groupId": groupId or None, "householdId": householdId or None},
        get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool()
async def email_invitation(
    email: str,
    token: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Email an invitation to a user.
    Args:
        email: The email address to send the invitation to (required).
        token: The invitation token to send (required).
    """
    return await get_client().email_invitation(
        {"email": email, "token": token}, get_user_token()
    )

# =============================================================================
# User Self-Service
# =============================================================================

@mcp.tool()
async def get_user_profile(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the currently logged-in user's profile."""
    return await get_client().get_user_profile(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_user_ratings(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get all ratings from the currently logged-in user."""
    return await get_client().get_user_ratings(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool()
async def get_user_rating_for_recipe(
    recipeId: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current user's rating for a specific recipe.
    Args:
        recipeId: The ID of the recipe (required).
    """
    return await get_client().get_user_rating_for_recipe(recipeId, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_user_favorites(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get all favorite recipes from the currently logged-in user."""
    return await get_client().get_user_favorites(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool()
async def set_recipe_rating(
    userId: str,
    slug: str,
    rating: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Set or update a rating for a recipe.
    Args:
        userId: The ID of the user (required).
        slug: The slug of the recipe (required).
        rating: Rating value (1-5) (required).
    """
    await get_client().set_recipe_rating(userId, slug, rating, get_user_token())
    return {"status": "rated", "slug": slug, "rating": rating}

@mcp.tool()
async def add_recipe_favorite(
    userId: str,
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Add a recipe to the user's favorites.
    Args:
        userId: The ID of the user (required).
        slug: The slug of the recipe (required).
    """
    await get_client().add_recipe_favorite(userId, slug, get_user_token())
    return {"status": "favorited", "slug": slug}

@mcp.tool()
async def remove_recipe_favorite(
    userId: str,
    slug: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Remove a recipe from the user's favorites.
    Args:
        userId: The ID of the user (required).
        slug: The slug of the recipe (required).
    """
    await get_client().remove_recipe_favorite(userId, slug, get_user_token())
    return {"status": "unfavorited", "slug": slug}

# =============================================================================
# Group / Household Info
# =============================================================================

@mcp.tool()
async def get_group_info(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current user's group information."""
    return await get_client().get_group_info(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def list_group_members(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all members of the current group."""
    return await get_client().list_group_members(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool()
async def get_group_member(
    usernameOrId: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a specific group member by username or ID.
    Args:
        usernameOrId: The username or ID of the member (required).
    """
    return await get_client().get_group_member(usernameOrId, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_group_preferences(
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current group's preferences."""
    return await get_client().get_group_preferences(get_user_token())

@mcp.tool()
async def update_group_preferences(
    privateGroup: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Update the current group's preferences.
    Args:
        privateGroup: Whether the group is private.
    """
    return await get_client().update_group_preferences(
        {"privateGroup": privateGroup}, get_user_token()
    )

@mcp.tool()
async def get_group_storage(
    ctx: Context = None
) -> dict[str, Any]:
    """Get group storage statistics."""
    return await get_client().get_group_storage(get_user_token())

@mcp.tool()
async def list_households(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all households in the group."""
    return await get_client().list_households(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool()
async def get_household(
    householdSlug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a specific household by its slug.
    Args:
        householdSlug: The slug of the household (required).
    """
    return await get_client().get_household(householdSlug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_household_info(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current user's household information."""
    return await get_client().get_household_info(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def get_household_recipe(
    recipeSlug: str,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a recipe scoped to the current household.
    Args:
        recipeSlug: The slug of the recipe (required).
    """
    return await get_client().get_household_recipe(recipeSlug, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool()
async def list_household_members(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all members of the current household."""
    return await get_client().list_household_members(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool()
async def get_household_preferences(
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current household's preferences."""
    return await get_client().get_household_preferences(get_user_token())

@mcp.tool()
async def get_household_statistics(
    ctx: Context = None
) -> dict[str, Any]:
    """Get household statistics."""
    return await get_client().get_household_statistics(get_user_token())

@mcp.tool()
async def update_household_preferences(
    privateHousehold: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Update the current household's preferences.
    Args:
        privateHousehold: Whether the household is private.
    """
    return await get_client().update_household_preferences(
        {"privateHousehold": privateHousehold}, get_user_token()
    )

@mcp.tool()
async def set_household_permissions(
    userId: str,
    canManage: bool = False,
    canInvite: bool = False,
    canOrganize: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Set household permissions for a user.
    Args:
        userId: The ID of the user to set permissions for (required).
        canManage: Whether the user can manage the household.
        canInvite: Whether the user can invite others.
        canOrganize: Whether the user can organize recipes.
    """
    return await get_client().set_household_permissions(
        {"userId": userId, "canManage": canManage, "canInvite": canInvite, "canOrganize": canOrganize},
        get_user_token()
    )

@mcp.tool()
async def get_app_about(
    ctx: Context = None
) -> dict[str, Any]:
    """Get general application information (version, demo status, etc.)."""
    return await get_client().get_app_about(get_user_token())

@mcp.tool()
async def get_app_startup_info(
    ctx: Context = None
) -> dict[str, Any]:
    """Get application startup information."""
    return await get_client().get_app_startup_info(get_user_token())

@mcp.tool()
async def get_app_theme(
    ctx: Context = None
) -> dict[str, Any]:
    """Get the current application theme settings."""
    return await get_client().get_app_theme(get_user_token())

# =============================================================================
# Domain Utilities
# =============================================================================

@mcp.tool()
async def parse_ingredient(
    ingredient: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Parse a single ingredient string into structured data.
    Args:
        ingredient: The ingredient text to parse (required).
    """
    return await get_client().parse_ingredient(ingredient, get_user_token())

@mcp.tool()
async def parse_ingredients(
    ingredients: list,
    ctx: Context = None
) -> dict[str, Any]:
    """Parse multiple ingredient strings into structured data.
    Args:
        ingredients: List of ingredient strings to parse (required).
    """
    data = await get_client().parse_ingredients(ingredients, get_user_token())
    return {"results": data} if isinstance(data, list) else data

@mcp.tool()
async def seed_default_foods(
    ctx: Context = None
) -> dict[str, Any]:
    """Seed default foods into the database."""
    return await get_client().seed_default_foods(get_user_token())

@mcp.tool()
async def seed_default_labels(
    ctx: Context = None
) -> dict[str, Any]:
    """Seed default labels into the database."""
    return await get_client().seed_default_labels(get_user_token())

@mcp.tool()
async def seed_default_units(
    ctx: Context = None
) -> dict[str, Any]:
    """Seed default units into the database."""
    return await get_client().seed_default_units(get_user_token())

@mcp.tool()
async def check_server_status(
    ctx: Context = None
) -> dict[str, Any]:
    """Check connectivity to the Mealie backend."""
    import httpx
    client = get_client()
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.get(f"{client.base_url}/api/app/about")
            return {"status": "connected", "backend_response": response.status_code}
    except Exception as e:
        return {"status": "disconnected", "error": str(e)}

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
    app = mcp.http_app(path=path)
    app = AuthMiddleware(app)
    print(f"Starting Mealie MCP server on http://{host}:{port}{path}")
    import uvicorn
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
