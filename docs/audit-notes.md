# Mealie MCP Audit Notes

## Repository

- **Repo:** `mealie-mcp`
- **Server:** FastMCP 3.4.2, streamable HTTP with SSE responses
- **Tools:** 175 across 25 resource domains
- **Transport:** stateless HTTP by default (`IS_STATEFUL=false`)
- **Auth:** identity passthrough; the caller's Mealie API token is forwarded
- **Backend:** Mealie v3.20.1 at `http://mealie-app:9000`
- **Storage:** PostgreSQL (`mealiedb`), primary group `Home`, household `Family`

## Execution environment

- The semantic audit runs against a temporary container built from this repo:
  `mealie-mcp:audit` on `mealie_int-mealie-net`.
- Production `mealie-mcp` is not restarted by the audit.
- `ALLOW_ALL_AGGREGATE=false` is the production setting; the audit also verifies
  `true`, stateful mode, and schema-only mode without a token.
- The audit key belongs to the admin user `shbadmin_mealie`. It is used only as
  an environment variable and is never written into the repository.
- The semantic audit creates a disposable tenant (group, household, admin user,
  member user) for isolation and group-scoped tests, then deletes it.

## Baseline before the audit

| Resource | Count |
|---|---:|
| recipes, categories, tags, tools, foods, units | 0 |
| comments, cookbooks, mealplans, rules | 0 |
| shopping lists/items, labels, timeline events | 0 |
| shares, actions, notifications, webhooks | 0 |
| users | 5 |
| groups / households | 1 / 1 |

The instance was effectively empty, so every mutation in the audit is an
audit-owned fixture. The five pre-existing users are never modified.

## Decisions

1. **Standard list envelope.** Every paginated list returns a top-level
   `items` array plus `page`, `per_page`, `total`, and `total_pages`. Before
   the audit, 20 list tools returned the whole Mealie page object as a TOON
   string inside `items`, and admin list tools returned a raw page with no
   standard metadata.
2. **Bounded pagination.** `page < 1` and `perPage` outside `1–200` are
   rejected. Mealie treats `perPage=-1` as "return everything" and `perPage=0`
   as an empty page; both are context-size hazards.
3. **Date classes.** Mealplan date fields are date-only (`YYYY-MM-DD`);
   recipe time fields are ISO 8601 durations (`PT45M`). Datetimes, epochs,
   and invalid calendar dates are rejected for date-only fields.
4. **Aggregate projection is intentional.** `ALLOW_ALL_AGGREGATE=false`
   forces `include_all_fields=False` on aggregate lists. This is a
   context-size gate, not a bug. Single-record `get_*` always honors the flag.
   The behavior is documented in every list schema and asserted in both modes.
5. **User privacy.** Default user reads and lists omit `tokens` and `cacheKey`.
   Single-record `get_user_by_id` and `get_user_profile` honor
   `include_all_fields`; aggregate lists remain gated.
6. **Audit tenant.** Cross-tenant visibility, group/household preferences,
   permissions, seeds, and webhooks are exercised in a disposable tenant.
   Tenant deletion also removes seeded foods, labels, and units.
7. **External capabilities.** URL scraping, image scraping, Apprise delivery,
   and SMTP email are explicit skips. They depend on public services and are
   not exercised against the live internet from the audit container.
8. **Owned-ID safety.** Every delete/update target is a record or slug created
   by the run, except the caller's own user id for reversible
   rating/favorite/profile operations. Slug renames are followed immediately
   so cleanup targets the live record.

## Product fixes

| Area | Change |
|---|---|
| List envelope | Standardized `items` + pagination metadata on 20 list tools and admin lists |
| Pagination | Rejected `page < 1` and `perPage` outside `1–200` |
| Status | `check_server_status` calls `/api/users/self`; returns `unauthenticated`/`unauthorized` instead of false `connected` |
| User privacy | Stripped `tokens`/`cacheKey` by default; recursive stripping inside page items; added `include_all_fields` to user list/get |
| Recipe visibility | New recipes default to `settings.public=true`; only an explicit `public=false` makes them private |
| Label resolution | Existing categories/tags/tools are reused by slug or case-insensitive name; duplicate-key conflicts are re-fetched and reused |
| Label warnings | A failed requested label now returns `partial: true` with warnings instead of looking fully successful |
| Recipe payloads | Recursive `_jsonable()` converts nested Pydantic models (`settings`, `notes`, `nutrition`) before serialization |
| Recipe create | Made transactional: a failed follow-up write deletes the just-created recipe instead of leaving an orphan |
| Recipe URLs | Absolute `https://` URLs with the caller's actual group slug instead of a hardcoded `/g/home/` |
| Slug changes | `update_recipe` responses expose the regenerated slug; audit cleanup follows it |
| Mealplan filters | `start_date`/`end_date` are sent in the spelling Mealie expects; previously the filters were silently ignored |
| Shared recipes | `recipe_id` filter corrected; the share `id` is used as the public token |
| Timeline events | `message` maps to Mealie's required `subject` on create and update |
| Recipe actions | `name`/`recipeActionType` map to `title`/`actionType`; description is not a stored Mealie field |
| Merges | `merge_foods`/`merge_units` now keep the requested target and remove the source |
| Shopping items | Create returns `createdItems`; bulk create is normalized; bulk update recovers the required `shoppingListId` from the stored item |
| Bulk delete | Recipe bulk delete reports requested, actually deleted, and missing slugs |
| Empty writes | Empty bulk lists and empty update payloads are rejected before the backend call |
| Delete annotations | 22 delete tools no longer claim `idempotentHint=true` |
| Errors | Client errors include the HTTP status and response body, which makes 404/422 diagnosis and benign cleanup checks reliable |
| Docs | Canonical date/duration hints, aggregate-gate documentation, missing property descriptions, README and audit docs |


## Audit coverage gap: nested recipe fields

The first full audit passed 697 checks but did **not** exercise the nested
`settings`, `notes`, or `nutrition` parameters on `create_recipe` or
`update_recipe`. It called every tool, but only with the shallow happy path
(name, times, ingredients, instructions). That is why it missed a real
serialization failure:

- `create_recipe` put `NutritionInput`, `RecipeSettingsParam`, and
  `RecipeNoteParam` objects directly into the dict passed to `httpx`.
- JSON serialization failed after the minimal recipe POST had already
  succeeded.
- Each retry left another minimal duplicate. Three attempts produced three
  recipes, two of them incomplete.

Corrections:

1. Recursive `_jsonable()` serializes every nested Pydantic model and
   container before the HTTP call.
2. `create_recipe` now deletes the preliminary record if any follow-up write
   fails, so a failed call cannot leave an orphan.
3. A full-payload contract creates and updates a recipe with settings, two
   notes, nutrition, tags, categories, and tools, asserts every value
   round-trips, and asserts the recipe count moves by exactly one.
4. The audit now enforces **nested-parameter coverage**: every object or
   array-of-object input parameter on a called tool must be supplied at least
   once. There are 18 such parameters; the full run reports zero unexercised.
5. Self-tests cover nested-model serialization and assert that
   `create_recipe` contains orphan cleanup.

The three test recipes were deleted. One clean recipe was recreated with the
fixed code, including both notes and the requested settings.


## Second coverage gap: label aliases and ownership

After the nested-payload fix, a second real-world recipe still exposed two
different problems:

1. **Label alias resolution.** The caller supplied
   `{"name": "Main Course", "slug": "main"}`. The existing category was
   `Main Course` with slug `main-course`. The resolver matched only by slug, so
   it tried to create a duplicate and hit a unique-key violation. The recipe
   was created with no categories. The tool returned a warning, but the agent
   ignored it and claimed the categories were applied.
2. **Ownership vs visibility.** The recipe was owned by the MCP integration
   user `shbadmin_mealie`, while the human UI account was `shbadmin`. The
   recipe existed and was visible to same-group API calls, but “My Recipes” is
   a per-user UI filter, so it looked missing. `settings.public=false` also
   hides the recipe from logged-out/public views; it does not hide it from
   logged-in members of the same group.

Corrections:

1. The resolver matches by slug, then by case-insensitive name, and re-fetches
   after a create conflict. The supplied slug is treated as an alias, not as
   the canonical identity.
2. `create_recipe` defaults to `settings.public=true`. A private recipe
   requires an explicit `settings.public=false`.
3. Requested label failures return `partial: true` and remain in `warnings`.
4. New contracts:
   - default visibility is public, explicit false is private;
   - existing category/tag/tool is reused when only the name matches;
   - alias resolution creates no duplicate organizer;
   - a same-group second user can read a private recipe, and the owner is the
     calling token's user;
   - valid label assignment returns no warnings.
5. The audit now treats existing-data reuse and ownership/visibility as
   first-class contracts, not just greenfield fixture creation.

## Safety incident and correction

The legacy `test_runner.py` previously called `seed_default_foods`,
`seed_default_labels`, and `seed_default_units` against the **primary** Home
group and also scraped external recipes. During audit preparation this left
2,688 foods, 24 units, 34 labels, and several scraped recipes in the live
instance. All of that data was created by our test runs and was removed; the
baseline was verified back to zero.

The legacy runner was then made environment-safe:

- seeder tests were removed (the semantic audit covers them in a disposable
  tenant);
- external URL and image scrape tests were removed (the semantic audit records
  explicit capability skips);
- the HTML/JSON-LD import test now uses an embedded offline fixture;
- imported recipes and the Q1 label are cleaned up explicitly;
- merge cleanup treats an already-removed source as benign.

Final legacy result: **241/241 PASS**, no seed or scrape residue.

## Known limitations found by the audit

- **External scraping** — Mealie blocks private-network URLs
  (`InvalidDomainError`), so the audit cannot stand up a local scrape fixture.
  Public-site scraping is skipped.
- **Invitations** — there is no delete endpoint; the suite lists invitations
  but does not create one. `email_invitation` is skipped.
- **Deleted labels** — Mealie returns HTTP 500 for a missing label rather than
  404; the audit accepts any error and verifies absence from the list.
- **Recipe identity** — renaming a recipe changes its slug. Consumers must use
  the slug in the update response.
- **Favorites/ratings** — the endpoints return rating records
  (`recipeId`, `rating`, `isFavorite`), not full recipe objects.
- **Aggregate user metadata** — with the projection gate closed, aggregate user
  lists intentionally hide token metadata. Use single-record get with
  `include_all_fields=true` when the deployment allows it.

## Final results

- **Semantic audit:** 782 PASS, 0 FAIL, 8 SKIP, 175/175 tools declared and
  called, 18/18 nested object parameters exercised, zero fixture residue.
- **Residue:** 21 per-resource checks, all zero; pre-existing users, group, and
  household preserved.
- **Alternate modes:** `ALLOW_ALL_AGGREGATE=true` (35 checks), stateful mode
  (32 checks), no-token L0 (15 checks), 7 self-tests.
- **Legacy runner:** 241/241 PASS.

Justified skips: 2 invitations, 1 Apprise notification, 5 recipe external
capabilities.

## Commands

```bash
# Build the audit image
docker build -t mealie-mcp:audit .

# Start it beside Mealie
docker run -d --rm --name mealie-mcp-audit \
  --network mealie_int-mealie-net \
  -e MEALIE_BASE_URL=http://mealie-app:9000 \
  -e MEALIE_PUBLIC_URL=https://mealie.selfhostingbox.com \
  -e MCP_SERVER_PORT=80 \
  -e ALLOW_ALL_AGGREGATE=false \
  -e IS_STATEFUL=false \
  mealie-mcp:audit

# Run (API key only in the environment)
docker exec -e API_KEY="$MEALIE_API_KEY" mealie-mcp-audit \
  python -m src.audit.runner --all --quiet \
  --report docs/tool-audit.md --json docs/tool-audit.json

# Schema-only, no API key
docker exec mealie-mcp-audit python -m src.audit.runner --l0 --quiet

# Legacy smoke suite
docker exec -e API_KEY="$MEALIE_API_KEY" mealie-mcp-audit \
  python -m src.test_runner
```
