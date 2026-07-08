# Mealie MCP Server

This repository contains a Model Context Protocol (MCP) server that acts
as a secure, multi-tenant proxy between an AI Assistant and the Mealie
backend API. It exposes **175 MCP tools** covering 25 resource domains
with full CRUD, meal planning, recipe scraping, and bulk operations.

## ✨ Features

- **🔑 Identity Passthrough** — Extracts the `Authorization: Bearer <token>`
  header from incoming HTTP requests and forwards it to the Mealie API
  without server-side authentication.
- **👥 Multi-Tenancy** — Uses Python `contextvars` to maintain thread-safe
  user identity isolation, ensuring all AI-driven actions are scoped to
  the authenticated user's permissions.
- **📊 Full Mealie Coverage** — 175 tools mapped to Mealie API endpoints
  across 25 resource domains.
- **⚡ TOON Optimization** — Bulk list responses are automatically compressed
  using TOON (Token-Optimized Object Notation) to reduce token consumption
  and maximize context window efficiency.
- **🚀 Efficient Gets** — GET responses return only commonly used fields by
  default. Full objects are available via an `include_all_fields` flag.
- **🧪 Comprehensive Testing** — 247 automated tests covering all tool
  domains, run via the test runner pipeline.

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MEALIE_BASE_URL` | Yes | Docker-internal URL of the Mealie server (e.g. `http://mealie-app:9000`). |
| `MCP_SERVER_PORT` | Yes | Port number the MCP server listens on |
| `ALLOW_ALL_AGGREGATE` | No | When `true`, aggregate listing tools honor the `include_all_fields` parameter. When `false` (default), the parameter is silently forced to `False` for aggregate list operations. |
| `IS_STATEFUL` | No | When `true`, uses stateful Streamable HTTP with session tracking. When `false` (default), uses stateless mode. |
| `MEALIE_PUBLIC_URL` | No | Public-facing URL of the Mealie server when served behind a reverse proxy (e.g. `https://mealie.example.com`). All URLs in API responses are rewritten to use this hostname instead of `MEALIE_BASE_URL`. Defaults to `MEALIE_BASE_URL`. |

## 📦 Installation & Local Development

1. Ensure you have Python 3.12+ installed.
2. Install dependencies:
    ```bash
    pip install fastmcp httpx pydantic uvicorn toon-mcp-server
    ```
3. Run the server:
    ```bash
    export MEALIE_BASE_URL=http://localhost:8053
    export MEALIE_PUBLIC_URL=https://mealie.example.com
    export MCP_SERVER_PORT=80
    python -m src.main
    ```

## 🐳 Docker Deployment

Build and run the server using Docker:

```bash
docker build -t mealie-mcp:latest .
docker run -d --name mealie-mcp \
    -e MEALIE_BASE_URL="http://mealie-app:9000" \
    -e MEALIE_PUBLIC_URL="https://mealie.example.com" \
    -e MCP_SERVER_PORT=80 \
    mealie-mcp:latest

The MCP server serves at `http://mealie-mcp:80/mcp` (Streamable HTTP).
```

## ⚠️ Important Notes

- **📋 `include_all_fields`** — The `include_all_fields` parameter (available
  on all `get_*` and `list_*` tools) controls whether all available fields
  are included in responses. Defaults to `False` for performance; set to
  `True` only when additional fields are needed.
- **🔒 `ALLOW_ALL_AGGREGATE`** — Controls whether aggregate listing tools
  respect the `include_all_fields` parameter. When set to `false` (default),
  all aggregate list operations silently return only default fields
  regardless of the caller's request.
- **⚡ TOON Compression** — All bulk list responses are automatically
  compressed using TOON to reduce token consumption by 30–60%.
- **📝 Required Fields & Defaults** — Each `create_*` tool requires specific
  key fields (e.g. `name` for resources). All other fields default to
  empty strings or reasonable values. The owner/user assignment field is
  automatically set to the authenticated user for most resources.

## 🛠️ API Tool Mapping

The server implements 175 MCP tools organized into the following categories:

### 📋 Recipe CRUD & Core (9 tools)

- `list_all_recipes` — List all recipes with pagination and search
- `get_recipe_by_slug` — Get a single recipe by slug
- `create_recipe` — Create a new recipe
- `update_recipe` — Update an existing recipe
- `delete_recipe_by_slug` — Delete a recipe by slug
- `duplicate_recipe` — Duplicate a recipe
- `update_recipe_last_made` — Update the last-made date
- `bulk_update_recipe_settings` — Bulk update recipe settings
- `list_recipe_suggestions` — List recipe suggestions

### 🌐 Recipe Import & Scrape (6 tools)

- `create_recipe_from_url` — Create a recipe by scraping a URL
- `create_recipe_from_url_bulk` — Bulk create recipes from URLs
- `create_recipe_from_html_or_json` — Create from HTML/JSON-LD
- `test_scrape_url` — Test URL scraping
- `scrape_recipe_image_url` — Scrape image URL into a recipe
- `delete_recipe_image` — Delete a recipe image

### 📦 Recipe Export & Bulk (7 tools)

- `list_recipe_export_formats` — List export formats
- `export_recipe` — Export a single recipe
- `bulk_tag_recipes` — Bulk assign tags to recipes
- `bulk_categorize_recipes` — Bulk assign categories
- `bulk_delete_recipes` — Bulk delete recipes
- `list_exports` — List bulk export data files
- `purge_exports` — Purge all export data

### 📂 Categories (7 tools)

- `list_all_categories` — List all categories
- `get_category_by_id` — Get category by ID
- `get_category_by_slug` — Get category by slug
- `list_empty_categories` — List empty categories
- `create_category` — Create a category
- `update_category` — Update a category
- `delete_category_by_id` — Delete a category

### 🏷️ Tags (7 tools)

- `list_all_tags` — List all tags
- `get_tag_by_id` — Get tag by ID
- `get_tag_by_slug` — Get tag by slug
- `list_empty_tags` — List empty tags
- `create_tag` — Create a tag
- `update_tag` — Update a tag
- `delete_tag_by_id` — Delete a tag

### 🔧 Tools (6 tools)

- `list_all_tools` — List all tools
- `get_tool_by_id` — Get tool by ID
- `get_tool_by_slug` — Get tool by slug
- `create_tool` — Create a tool
- `update_tool` — Update a tool
- `delete_tool_by_id` — Delete a tool

### 🥘 Foods (6 tools)

- `list_all_foods` — List all foods
- `get_food_by_id` — Get food by ID
- `create_food` — Create a food
- `update_food` — Update a food
- `delete_food_by_id` — Delete a food
- `merge_foods` — Merge two foods

### 📐 Units (6 tools)

- `list_all_units` — List all units
- `get_unit_by_id` — Get unit by ID
- `create_unit` — Create a unit
- `update_unit` — Update a unit
- `delete_unit_by_id` — Delete a unit
- `merge_units` — Merge two units

### 💬 Comments (5 tools)

- `list_all_comments` — List all comments
- `get_comment_by_id` — Get comment by ID
- `create_comment` — Create a comment
- `update_comment` — Update a comment
- `delete_comment_by_id` — Delete a comment

### 📖 Cookbooks (6 tools)

- `list_all_cookbooks` — List all cookbooks
- `get_cookbook_by_id` — Get cookbook by ID
- `create_cookbook` — Create a cookbook
- `update_cookbook` — Update a cookbook
- `delete_cookbook_by_id` — Delete a cookbook
- `update_cookbooks` — Bulk update cookbooks

### 📅 Mealplans (7 tools)

- `list_all_mealplans` — List all mealplans
- `get_mealplan_by_id` — Get mealplan by ID
- `list_todays_meals` — List today's meals
- `create_mealplan` — Create a mealplan
- `create_random_mealplan` — Create random mealplan
- `update_mealplan` — Update a mealplan
- `delete_mealplan_by_id` — Delete a mealplan

### ⚙️ Mealplan Rules (5 tools)

- `list_all_mealplan_rules` — List all mealplan rules
- `get_mealplan_rule_by_id` — Get mealplan rule by ID
- `create_mealplan_rule` — Create a mealplan rule
- `update_mealplan_rule` — Update a mealplan rule
- `delete_mealplan_rule_by_id` — Delete a mealplan rule

### 🛒 Shopping Lists (8 tools)

- `list_all_shopping_lists` — List all shopping lists
- `get_shopping_list_by_id` — Get shopping list by ID
- `create_shopping_list` — Create a shopping list
- `update_shopping_list` — Update a shopping list
- `delete_shopping_list_by_id` — Delete a shopping list
- `update_shopping_list_label_settings` — Update label settings
- `add_recipe_to_shopping_list` — Add recipe ingredients
- `remove_recipe_from_shopping_list` — Remove recipe ingredients

### 🛍️ Shopping Items (8 tools)

- `list_all_shopping_items` — List all shopping items
- `get_shopping_item_by_id` — Get shopping item by ID
- `create_shopping_item` — Create a shopping item
- `update_shopping_item` — Update a shopping item
- `delete_shopping_item_by_id` — Delete a shopping item
- `bulk_create_shopping_items` — Bulk create items
- `bulk_update_shopping_items` — Bulk update items
- `bulk_delete_shopping_items` — Bulk delete items

### 🏷️ Labels (5 tools)

- `list_all_labels` — List all labels
- `get_label_by_id` — Get label by ID
- `create_label` — Create a label
- `update_label` — Update a label
- `delete_label_by_id` — Delete a label

### ⏱️ Recipe Timeline Events (5 tools)

- `list_all_timeline_events` — List all timeline events
- `get_timeline_event_by_id` — Get timeline event by ID
- `create_timeline_event` — Create a timeline event
- `update_timeline_event` — Update a timeline event
- `delete_timeline_event_by_id` — Delete a timeline event

### 🔗 Shared Recipes (4 tools)

- `list_all_shared_recipes` — List all share tokens
- `get_shared_recipe_by_id` — Get shared recipe by token
- `create_shared_recipe` — Create a share token
- `delete_shared_recipe_by_id` — Delete a share token

### 🎬 Recipe Actions (6 tools)

- `list_all_recipe_actions` — List all recipe actions
- `get_recipe_action_by_id` — Get recipe action by ID
- `create_recipe_action` — Create a recipe action
- `update_recipe_action` — Update a recipe action
- `delete_recipe_action_by_id` — Delete a recipe action
- `trigger_recipe_action` — Trigger a recipe action

### 🔔 Event Notifications (6 tools)

- `list_all_event_notifications` — List all notifiers
- `get_event_notification_by_id` — Get notifier by ID
- `create_event_notification` — Create a notifier
- `update_event_notification` — Update a notifier
- `delete_event_notification_by_id` — Delete a notifier
- `test_event_notification` — Test a notifier

### 🌐 Webhooks (7 tools)

- `list_all_webhooks` — List all webhooks
- `get_webhook_by_id` — Get webhook by ID
- `create_webhook` — Create a webhook
- `update_webhook` — Update a webhook
- `delete_webhook_by_id` — Delete a webhook
- `test_webhook` — Test a webhook
- `rerun_webhooks` — Rerun scheduled webhooks

### 📧 Invitations (3 tools)

- `list_all_invitations` — List invitation tokens
- `create_invitation` — Create an invitation token
- `email_invitation` — Email an invitation

### 👤 Users (12 tools)

- `get_user_profile` — Get own profile
- `list_user_ratings` — List own ratings
- `get_user_rating_for_recipe` — Get rating for recipe
- `list_user_favorites` — List own favorites
- `set_recipe_rating` — Set a recipe rating
- `add_recipe_favorite` — Add recipe to favorites
- `remove_recipe_favorite` — Remove recipe from favorites
- `create_user` — Create a new user (admin)
- `get_user_by_id` — Get user by ID (admin)
- `update_user` — Update a user (admin)
- `delete_user` — Delete a user (admin)
- `list_users` — List all users (admin)

### 🏠 Groups (11 tools)

- `get_group_info` — Get group details
- `list_group_members` — List group members
- `get_group_member` — Get group member by ID
- `get_group_preferences` — Get group preferences
- `update_group_preferences` — Update group preferences
- `get_group_storage` — Get group storage statistics
- `create_group` — Create a new group (admin)
- `get_group_by_id` — Get group by ID (admin)
- `update_group` — Update a group (admin)
- `delete_group` — Delete a group (admin)
- `list_groups` — List all groups (admin)

### 🏡 Households (14 tools)

- `list_households` — List all households
- `get_household` — Get household by ID
- `get_household_info` — Get household info
- `get_household_recipe` — Get recipe within household context
- `list_household_members` — List household members
- `get_household_preferences` — Get household preferences
- `update_household_preferences` — Update household preferences
- `get_household_statistics` — Get household statistics
- `set_household_permissions` — Set household permissions
- `create_household` — Create a new household (admin)
- `get_household_by_id` — Get household by ID (admin)
- `update_household` — Update a household (admin)
- `delete_household` — Delete a household (admin)
- `list_all_households` — List all households (admin)

### 🛠️ Domain Utilities (9 tools)

- `parse_ingredient` — Parse an ingredient string
- `parse_ingredients` — Parse multiple ingredients
- `seed_default_foods` — Seed default foods
- `seed_default_labels` — Seed default labels
- `seed_default_units` — Seed default units
- `check_server_status` — Check backend connectivity
- `get_app_about` — Get app about info
- `get_app_startup_info` — Get app startup info
- `get_app_theme` — Get app theme settings
