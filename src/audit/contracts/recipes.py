"""Recipe contracts: CRUD, bulk actions, import/export, and URLs."""

from __future__ import annotations

import json

from ..expect import (find_item, require, require_absolute_url,
                      require_contains_path, require_no_raw_binary)
from ..harness import Scenario, scenario
from .helpers import (assert_recipe_urls, category_fixture, find_by,
                      recipe_fixture, tag_fixture, tool_fixture)


@scenario("recipes", "recipe_crud",
          ["create_recipe", "get_recipe_by_slug", "list_all_recipes",
           "update_recipe", "delete_recipe_by_slug", "duplicate_recipe",
           "update_recipe_last_made", "list_recipe_suggestions"])
def recipe_crud(s: Scenario) -> None:
    group_slug = str(s.run.adapter.profile.get("groupSlug") or "home")
    fixture = recipe_fixture(s, "recipe")
    slug = fixture["slug"]

    full = s.call("get recipe full", "get_recipe_by_slug",
                  {"slug": slug, "include_all_fields": True}).data
    s.check("get recipe returns the fixture",
            lambda: require(full.get("slug") == slug, full.get("slug")))
    s.check("recipe ingredients round-trip",
            lambda: require(len(full.get("recipeIngredient") or []) == 2, full.get("recipeIngredient")))
    s.check("recipe instructions round-trip",
            lambda: require(len(full.get("recipeInstructions") or []) == 2,
                            full.get("recipeInstructions")))
    assert_recipe_urls(s, full, group_slug)

    found = find_by(s, "list_all_recipes", "slug", slug, search=fixture["name"])
    s.check("recipe search finds the fixture",
            lambda: require(found is not None, "search returned no fixture"))

    updated_name = fixture["name"] + "-updated"
    update_call = s.call("update recipe", "update_recipe",
                         {"slug": slug, "name": updated_name,
                          "description": "updated description",
                          "totalTime": "PT45M"})
    new_slug = str(update_call.data.get("slug") or slug)
    s.check("recipe update returns its current slug",
            lambda: require(bool(new_slug), update_call.data))
    if new_slug != slug:
        # Mealie regenerates the slug when the name changes; follow it so the
        # cleanup and subsequent reads target the live record.
        s.own(new_slug, update_call.data.get("id"))
        s.forget_cleanup("delete_recipe_by_slug", {"slug": slug})
        s.cleanup("delete_recipe_by_slug", {"slug": new_slug},
                  "cleanup updated recipe")
        slug = new_slug
    after = s.call("get updated recipe", "get_recipe_by_slug",
                   {"slug": slug, "include_all_fields": True}).data
    s.check("recipe update is persisted",
            lambda: require(after.get("name") == updated_name,
                            f"name={after.get('name')!r}"))
    s.check("recipe duration is stored",
            lambda: require(after.get("totalTime") == "PT45M",
                            after.get("totalTime")))

    last_made = s.call("update recipe last made", "update_recipe_last_made",
                       {"slug": slug})
    s.check("last-made response is not an error", lambda: require(not last_made.is_error, last_made.error))

    duplicate = s.call("duplicate recipe", "duplicate_recipe", {"slug": slug})
    dup_slug = str(duplicate.data.get("slug") or "")
    s.check("duplicate returns a new slug",
            lambda: require(bool(dup_slug) and dup_slug != slug, duplicate.data))
    if dup_slug:
        s.own(dup_slug, duplicate.data.get("id"))
        s.cleanup("delete_recipe_by_slug", {"slug": dup_slug}, "cleanup duplicate recipe")

    suggestions = s.call("list recipe suggestions", "list_recipe_suggestions", {})
    s.items("recipe suggestions decode", suggestions)

    s.call("delete recipe", "delete_recipe_by_slug", {"slug": slug})
    s.forget_cleanup("delete_recipe_by_slug", {"slug": slug})
    s.expect_error("deleted recipe is gone", "get_recipe_by_slug",
                   {"slug": slug}, contains=("404", "not found"))


@scenario("recipes", "recipe_bulk_actions",
          ["create_recipe", "bulk_update_recipe_settings",
           "bulk_tag_recipes", "bulk_categorize_recipes",
           "bulk_delete_recipes", "list_all_tags", "list_all_categories"])
def recipe_bulk_actions(s: Scenario) -> None:
    first = recipe_fixture(s, "bulk-1")
    second = recipe_fixture(s, "bulk-2")
    third = recipe_fixture(s, "bulk-3")

    s.call("bulk update settings", "bulk_update_recipe_settings", {
        "recipes": [first["slug"], second["slug"]],
        "settings": {"public": True, "showNutrition": True},
    })
    for label, fixture in (("first", first), ("second", second)):
        got = s.call(f"get {label} bulk-updated recipe", "get_recipe_by_slug",
                     {"slug": fixture["slug"], "include_all_fields": True}).data
        s.check(f"bulk settings applied to the {label} recipe",
                lambda data=got: require(
                    (data.get("settings") or {}).get("public") is True,
                    data.get("settings"),
                ))

    tag_name = s.fixture("bulk-tag")
    category_name = s.fixture("bulk-category")
    s.call("bulk tag recipes", "bulk_tag_recipes", {
        "recipes": [first["slug"]],
        "tags": [{"name": tag_name, "slug": tag_name.lower()}],
    })
    s.call("bulk categorize recipes", "bulk_categorize_recipes", {
        "recipes": [first["slug"]],
        "categories": [{"name": category_name, "slug": category_name.lower()}],
    })
    tagged = s.call("get tagged recipe", "get_recipe_by_slug",
                    {"slug": first["slug"], "include_all_fields": True}).data
    s.check("bulk tag is visible on the recipe",
            lambda: require(any(tag.get("name") == tag_name
                                for tag in (tagged.get("tags") or [])),
                            tagged.get("tags")))
    s.check("bulk category is visible on the recipe",
            lambda: require(any(cat.get("name") == category_name
                                for cat in (tagged.get("recipeCategory") or [])),
                            tagged.get("recipeCategory")))

    # Implicitly-created organizers are audit fixtures too.
    for tool, name in (("list_all_tags", tag_name),
                       ("list_all_categories", category_name)):
        records = s.find_in_pages(tool, lambda item, n=name: item.get("name") == n,
                                  per_page=200)
        for record in records:
            if record.get("name") == name and record.get("id"):
                s.own(record["id"])
                delete_tool = ("delete_tag_by_id" if "tags" in tool
                               else "delete_category_by_id")
                s.cleanup(delete_tool, {"id": record["id"]},
                          f"cleanup {name}")

    missing_slug = s.fixture("missing-recipe")
    s.allow(missing_slug)
    deleted = s.call("bulk delete recipes", "bulk_delete_recipes",
                     {"recipes": [second["slug"], third["slug"], missing_slug]})
    for fixture in (second, third):
        s.forget_cleanup("delete_recipe_by_slug", {"slug": fixture["slug"]})
    s.check("bulk delete reports the number actually deleted",
            lambda: require(deleted.data.get("count") == 2, deleted.data))
    s.check("bulk delete reports the missing slug separately",
            lambda: require(deleted.data.get("missing") == [missing_slug], deleted.data))
    for label, fixture in (("second", second), ("third", third)):
        s.expect_error(f"bulk-deleted {label} recipe is gone", "get_recipe_by_slug",
                       {"slug": fixture["slug"]}, contains=("404", "not found"))


@scenario("recipes", "recipe_import_export",
          ["create_recipe_from_html_or_json", "list_recipe_export_formats",
           "export_recipe", "list_exports", "create_recipe",
           "delete_recipe_by_slug"])
def recipe_import_export(s: Scenario) -> None:
    name = s.fixture("imported-recipe")
    payload = json.dumps({
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": name,
        "description": "imported by the audit",
        "recipeIngredient": ["1 cup flour"],
        "recipeInstructions": [{"@type": "HowToStep", "text": "Mix"}],
    })
    imported = s.call("import recipe from JSON-LD", "create_recipe_from_html_or_json",
                      {"data": payload})
    slug = str(imported.data.get("slug") or "")
    s.check("import returns a recipe slug", lambda: require(bool(slug), imported.data))
    if slug:
        s.own(slug, imported.data.get("id"))
        s.cleanup("delete_recipe_by_slug", {"slug": slug}, "cleanup imported recipe")

    formats = s.call("list export formats", "list_recipe_export_formats", {}).data
    s.check("export formats include raw and zip",
            lambda: require("json" in formats and "zip" in formats, formats))

    fixture = recipe_fixture(s, "export-recipe")
    exported = s.call("export recipe", "export_recipe", {"slug": fixture["slug"]})
    text = json.dumps(exported.data)
    s.check("exported recipe contains its name",
            lambda: require(fixture["name"] in text, text[:500]))
    require_no_raw_binary(exported.text, "export recipe")

    exports = s.call("list exports", "list_exports", {})
    s.items("exports decode", exports)


@scenario("recipes", "recipe_image_and_external_capabilities",
          ["create_recipe", "delete_recipe_image", "scrape_recipe_image_url",
           "create_recipe_from_url", "create_recipe_from_url_bulk",
           "test_scrape_url", "delete_recipe_by_slug", "purge_exports"])
def recipe_image_and_external_capabilities(s: Scenario) -> None:
    fixture = recipe_fixture(s, "image-recipe")
    s.call_any("delete missing recipe image", "delete_recipe_image",
               {"slug": fixture["slug"]})

    s.skip_tool("scrape recipe image", "scrape_recipe_image_url",
                "requires an external image host; not exercised against the "
                "public internet")
    s.skip_tool("import recipe from URL", "create_recipe_from_url",
                "requires an external recipe site; skipped to avoid network "
                "side effects")
    s.skip_tool("bulk import recipes from URLs", "create_recipe_from_url_bulk",
                "requires external recipe sites; skipped to avoid network "
                "side effects")
    s.skip_tool("test scrape URL", "test_scrape_url",
                "requires an external recipe site; skipped to avoid network "
                "side effects")
    s.skip_tool("purge exports", "purge_exports",
                "global destructive endpoint; the audit does not create bulk "
                "export files it could safely purge")


@scenario("recipes", "recipe_full_nested_payload",
          ["create_recipe", "get_recipe_by_slug", "update_recipe",
           "delete_recipe_by_slug", "list_all_recipes"])
def recipe_full_nested_payload(s: Scenario) -> None:
    """Regression: nested Pydantic fields must serialize and round-trip.

    This is the contract that was missing when create_recipe failed for
    settings/notes/nutrition and left orphan recipes behind.
    """
    tag = tag_fixture(s, "nested-tag")
    category = category_fixture(s, "nested-category")
    recipe_tool = tool_fixture(s, "nested-tool")
    tag_obj = {"name": tag["name"], "slug": tag["data"].get("slug", "")}
    category_obj = {"name": category["name"],
                    "slug": category["data"].get("slug", "")}
    tool_obj = {"name": recipe_tool["name"],
                "slug": recipe_tool["data"].get("slug", "")}
    name = s.fixture("nested-recipe")

    baseline = s.call("recipe count before nested create", "list_all_recipes",
                      {"page": 1, "perPage": 1}).data.get("total")
    s.check("recipe baseline exposes a count",
            lambda: require(isinstance(baseline, int), baseline))

    created = s.call("create recipe with nested fields", "create_recipe", {
        "name": name,
        "description": "nested serialization regression",
        "recipeServings": 4,
        "totalTime": "PT45M",
        "recipeCategory": [category_obj],
        "tags": [tag_obj],
        "tools": [tool_obj],
        "recipeIngredient": ["1 cup flour", "2 eggs"],
        "recipeInstructions": ["Mix", "Bake"],
        "settings": {
            "public": True,
            "showNutrition": True,
            "showAssets": True,
            "disableComments": False,
            "locked": False,
        },
        "notes": [
            {"title": "Meal Prep Tip", "text": "Make the glaze ahead."},
            {"title": "Heat Level", "text": "Use more harissa for heat."},
        ],
        "nutrition": {
            "calories": "520",
            "proteinContent": "18",
            "fatContent": "12",
        },
    })
    slug = str(created.data.get("slug") or "")
    s.check("nested create returns a slug", lambda: require(bool(slug), created.data))
    if not slug:
        return
    s.own(slug, created.data.get("id"))
    s.cleanup("delete_recipe_by_slug", {"slug": slug},
              "cleanup nested recipe")

    after = s.call("recipe count after nested create", "list_all_recipes",
                   {"page": 1, "perPage": 1}).data.get("total")
    s.check("nested create adds exactly one recipe",
            lambda: require(after == baseline + 1,
                            f"before={baseline} after={after}"))

    full = s.call("get nested recipe full", "get_recipe_by_slug",
                  {"slug": slug, "include_all_fields": True}).data
    notes = full.get("notes") or []
    s.check("notes survive the nested create",
            lambda: require(
                len(notes) == 2
                and {note.get("title") for note in notes}
                == {"Meal Prep Tip", "Heat Level"},
                notes,
            ))
    settings = full.get("settings") or {}
    s.check("settings survive the nested create",
            lambda: require(
                settings.get("public") is True
                and settings.get("showNutrition") is True
                and settings.get("showAssets") is True,
                settings,
            ))
    nutrition = full.get("nutrition") or {}
    s.check("nutrition survives the nested create",
            lambda: require(
                nutrition.get("calories") == "520"
                and nutrition.get("proteinContent") == "18",
                nutrition,
            ))
    s.check("nested tags survive the create",
            lambda: require(any(item.get("name") == tag["name"]
                                for item in (full.get("tags") or [])),
                            full.get("tags")))
    s.check("nested categories survive the create",
            lambda: require(any(item.get("name") == category["name"]
                                for item in (full.get("recipeCategory") or [])),
                            full.get("recipeCategory")))
    s.check("nested tools survive the create",
            lambda: require(any(item.get("name") == recipe_tool["name"]
                                for item in (full.get("tools") or [])),
                            full.get("tools")))

    s.call("update recipe with nested fields", "update_recipe", {
        "slug": slug,
        "settings": {
            "public": False,
            "showNutrition": False,
            "showAssets": False,
            "disableComments": True,
            "locked": True,
        },
        "notes": [{"title": "Updated Note", "text": "Only one note now."}],
        "nutrition": {"calories": "610", "proteinContent": "20"},
        "recipeCategory": [category_obj],
        "tags": [tag_obj],
        "tools": [tool_obj],
    })
    updated = s.call("get nested recipe after update", "get_recipe_by_slug",
                     {"slug": slug, "include_all_fields": True}).data
    updated_notes = updated.get("notes") or []
    s.check("nested notes update is persisted",
            lambda: require(
                len(updated_notes) == 1
                and updated_notes[0].get("title") == "Updated Note",
                updated_notes,
            ))
    updated_settings = updated.get("settings") or {}
    s.check("nested settings update is persisted",
            lambda: require(
                updated_settings.get("public") is False
                and updated_settings.get("showNutrition") is False
                and updated_settings.get("locked") is True,
                updated_settings,
            ))
    updated_nutrition = updated.get("nutrition") or {}
    s.check("nested nutrition update is persisted",
            lambda: require(updated_nutrition.get("calories") == "610",
                            updated_nutrition))
    s.check("nested tags survive the update",
            lambda: require(any(item.get("name") == tag["name"]
                                for item in (updated.get("tags") or [])),
                            updated.get("tags")))

    s.call("delete nested recipe", "delete_recipe_by_slug", {"slug": slug})
    s.forget_cleanup("delete_recipe_by_slug", {"slug": slug})
    final = s.call("recipe count after nested delete", "list_all_recipes",
                   {"page": 1, "perPage": 1}).data.get("total")
    s.check("nested recipe delete returns to baseline",
            lambda: require(final == baseline,
                            f"final={final} baseline={baseline}"))


@scenario("recipes", "recipe_default_visibility",
          ["create_recipe", "get_recipe_by_slug", "delete_recipe_by_slug"])
def recipe_default_visibility(s: Scenario) -> None:
    """Default is public; only an explicit public=False makes it private."""
    default = recipe_fixture(s, "visibility-default")
    default_full = s.call("get default-visibility recipe", "get_recipe_by_slug",
                          {"slug": default["slug"], "include_all_fields": True}).data
    s.check("a recipe with no settings is public by default",
            lambda: require((default_full.get("settings") or {}).get("public") is True,
                            default_full.get("settings")))

    private = recipe_fixture(s, "visibility-private",
                             settings={"public": False})
    private_full = s.call("get private recipe", "get_recipe_by_slug",
                          {"slug": private["slug"], "include_all_fields": True}).data
    s.check("an explicit public=False makes the recipe private",
            lambda: require((private_full.get("settings") or {}).get("public") is False,
                            private_full.get("settings")))

    public = recipe_fixture(s, "visibility-public",
                            settings={"public": True})
    public_full = s.call("get public recipe", "get_recipe_by_slug",
                         {"slug": public["slug"], "include_all_fields": True}).data
    s.check("an explicit public=True keeps the recipe public",
            lambda: require((public_full.get("settings") or {}).get("public") is True,
                            public_full.get("settings")))

    for label, fixture in (("default", default), ("private", private),
                           ("public", public)):
        s.check(f"{label} recipe create has no warnings",
                lambda data=fixture["data"]: require(
                    not data.get("warnings") and not data.get("partial"), data
                ))


@scenario("recipes", "recipe_existing_label_alias",
          ["create_recipe", "get_recipe_by_slug", "delete_recipe_by_slug",
           "list_all_categories", "list_all_tags", "list_all_tools"])
def recipe_existing_label_alias(s: Scenario) -> None:
    """Reuse an existing label when the supplied slug is only an alias."""
    category = category_fixture(s, "alias-category")
    tag = tag_fixture(s, "alias-tag")
    recipe_tool = tool_fixture(s, "alias-tool")
    category_slug = str(category["data"].get("slug") or category["name"])
    tag_slug = str(tag["data"].get("slug") or tag["name"])
    tool_slug = str(recipe_tool["data"].get("slug") or recipe_tool["name"])
    alias_suffix = "-alias"

    fixture = recipe_fixture(
        s, "alias-recipe",
        recipeCategory=[{"name": category["name"],
                         "slug": category_slug + alias_suffix}],
        tags=[{"name": tag["name"], "slug": tag_slug + alias_suffix}],
        tools=[{"name": recipe_tool["name"],
                "slug": tool_slug + alias_suffix}],
    )
    s.check("alias label assignment has no warnings",
            lambda: require(
                not fixture["data"].get("warnings")
                and not fixture["data"].get("partial"),
                fixture["data"],
            ))

    full = s.call("get alias recipe", "get_recipe_by_slug",
                  {"slug": fixture["slug"], "include_all_fields": True}).data
    s.check("alias category reuses the existing record",
            lambda: require(any(item.get("id") == category["id"]
                                for item in (full.get("recipeCategory") or [])),
                            full.get("recipeCategory")))
    s.check("alias tag reuses the existing record",
            lambda: require(any(item.get("id") == tag["id"]
                                for item in (full.get("tags") or [])),
                            full.get("tags")))
    s.check("alias tool reuses the existing record",
            lambda: require(any(item.get("id") == recipe_tool["id"]
                                for item in (full.get("tools") or [])),
                            full.get("tools")))

    for tool, alias, label in (
        ("list_all_categories", category_slug + alias_suffix, "category"),
        ("list_all_tags", tag_slug + alias_suffix, "tag"),
        ("list_all_tools", tool_slug + alias_suffix, "tool"),
    ):
        records = s.find_in_pages(
            tool, lambda item, a=alias: item.get("slug") == a, per_page=200
        )
        duplicates = [item for item in records if item.get("slug") == alias]
        s.check(f"alias {label} did not create a duplicate",
                lambda duplicates=duplicates: require(not duplicates, duplicates))
