"""Parsing and seed contracts."""

from __future__ import annotations

from ..expect import require
from ..harness import Scenario, scenario


@scenario("utilities", "ingredient_parser",
          ["parse_ingredient", "parse_ingredients"])
def ingredient_parser(s: Scenario) -> None:
    parsed = s.call("parse ingredient", "parse_ingredient",
                    {"ingredient": "1 cup flour, sifted"}).data
    s.check("parser returns the input", lambda: require("1 cup flour" in str(parsed), parsed))
    s.check("parser extracts a quantity",
            lambda: require((parsed.get("ingredient") or {}).get("quantity") == 1,
                            parsed.get("ingredient")))
    s.check("parser extracts a unit",
            lambda: require(((parsed.get("ingredient") or {}).get("unit") or {}).get("name") == "cup",
                            parsed.get("ingredient")))

    batch = s.call("parse ingredients", "parse_ingredients",
                   {"ingredients": ["2 eggs", "1 tbsp sugar"]}).data
    s.check("batch parser returns every input",
            lambda: require(
                len(batch.get("results") or batch.get("ingredients")
                    or batch.get("items") or []) == 2
                if isinstance(batch, dict) else isinstance(batch, list),
                batch,
            ))


@scenario("utilities", "seed_defaults",
          ["seed_default_foods", "seed_default_labels", "seed_default_units",
           "list_all_foods", "list_all_labels", "list_all_units"])
def seed_defaults(s: Scenario) -> None:
    if not s.run.tenant or "tenant" not in s.run.clients:
        for tool in ("seed_default_foods", "seed_default_labels", "seed_default_units"):
            s.skip_tool(f"seed {tool}", tool,
                        "seeds shared group data; requires an isolated audit tenant")
        return

    s.call("seed tenant foods", "seed_default_foods", {"locale": "en-US"},
           account="tenant")
    s.call("seed tenant labels", "seed_default_labels", {}, account="tenant")
    s.call("seed tenant units", "seed_default_units", {}, account="tenant")

    for tool, label in (("list_all_foods", "foods"),
                        ("list_all_labels", "labels"),
                        ("list_all_units", "units")):
        page = s.call(f"list tenant {label}", tool,
                      {"page": 1, "perPage": 1}, account="tenant").data
        s.check(f"seeded {label} are visible in the tenant",
                lambda data=page: require((data.get("total") or 0) >= 1, data))
