# CLAUDE.md — Universal Development Principles

> Distilled from patterns across multiple projects. Apply universally; skip sections irrelevant to the current project type.

---

## Agent Workflow: Explore → Plan → Code → Verify

Never blindly write code. Always follow this loop:

1. **Explore** — Search the codebase. Find relevant files, understand existing patterns before touching anything.
2. **Plan** — Assess the blast radius (how many files touched, how long it takes). For significant changes, present 2–3 high-level approaches with pros/cons and ask for human approval before writing code.
3. **Code** — Implement following the rules below.
4. **Verify** — Run tests. Fix all failures before declaring the task complete.

**Read before edit:** Always read a file before editing it, even if it was read earlier in the conversation.

**Ask for options first.** On non-trivial tasks, propose approaches before writing code. The human needs to evaluate options — don't assume the first plausible approach is the right one.

---

## Communication Style

- **Concise output.** No filler, no apologies, no moralizing. Skip generic advice.
- **Show your work.** Use short internal monologues to break down complex problems.
- **Fail loud.** Never use catch-all exception handlers that silently swallow errors. Always raise or log explicitly.

---

## Architecture Principles

- **No over-engineering.** Only make changes directly requested or clearly necessary. Keep solutions simple.
- **Single source of truth.** Constants, configs, and shared types derive from one place.
- **Modular design.** Separate concerns: data fetching, processing, storage, and presentation are distinct layers.
- **Idempotent operations.** Re-running any operation should be safe and produce the same result. Use `INSERT OR IGNORE` patterns, cache checks, or deduplication by unique key.
- **Static when possible.** Prefer baked-in data over runtime backends when the data update cycle allows it.
- **Cost-optimized.** Stay on free tiers and use the cheapest resources that meet requirements.
- **CLI-first.** Build CLI entry points before UI. Agents can invoke CLIs directly to self-validate output, closing the feedback loop without human intervention.
- **Minimize page weight and request count.** Audit total payload size and number of requests. Content-focused sites should be lightweight — aim for fewest requests and smallest payload possible.
- **Tree-shake and code-split.** Don't bundle every controller/feature for every page. Use code-splitting and lazy loading so pages only load the code they actually need.
- **Benchmark against best-in-class.** Compare your site/app against well-optimized reference points. If the simplest site in your org is orders of magnitude lighter, your build process needs review.
- **Document subsystems.** Maintain a `docs/` folder with notes on non-obvious subsystems, design decisions, and correct CLI invocations. One line of documentation prevents repeated mistakes.

---

## Error Resilience

- **Never let a single item failure crash the pipeline.** Wrap individual record processing in try/except. Log and continue.
- **Log aggressively.** Every request, parse, API call, cache hit/miss, and filter decision should be logged.
- **Cache everything.** Re-runs should be fast and cheap. Multi-layer caching where appropriate.
- **Validate everything.** Invalid responses from external services → log and skip, never crash.
- **Track errors visibly.** Use an `issues.md` file or errors array — failures must be visible, not silent.

---

## Security & Credential Handling

- **Never commit secrets.** API keys, tokens, and passwords must never appear in committed code.
- Read credentials from environment variables only (e.g., `os.environ["API_KEY"]`). Halt with a clear error if missing.
- Never log or print credential values.
- Always `.gitignore`: `.env`, `.env.local`, `credentials.json`, `secrets/`, `node_modules/`, `__pycache__/`, `dist/`, `*.pyc`.
- Before committing: `git diff --cached | grep -iE "apikey|password|token|secret"`.
- **Respect user privacy choices.** Don't circumvent ad blockers or privacy tools by proxying tracking SDKs through your own domain. This erodes user trust.

---

## Testing & Validation

- **Write tests alongside code, not as an afterthought.** Every new module or bug fix includes corresponding tests.
- Write a regression test for every bug fix.
- Validate output data against expected schemas before writing to disk.
- **Cover edge cases, not just happy paths:**
  - Empty input: `[]`, `{}`, `""`
  - Null/undefined for every optional field
  - Boundary values (first/last page, exact date boundaries, zero counts)
  - Combined states (e.g., multiple filters active simultaneously)
- Run the full test suite before committing to catch regressions.
- **Never ship test files to production.** Ensure build pipelines exclude test files, dev fixtures, and debug artifacts from production bundles. Use build exclusions and CI checks to enforce this.

---

## Git Discipline

- **Commit often** at natural checkpoints — small, focused commits over large monolithic ones.
  - After each new module/feature is built
  - After fixing a bug or resolving a failing test
  - After updating documentation
- Write descriptive commit messages explaining *what* and *why*.
- Never commit large binary files, downloaded data, or API keys.

---

## Data Handling

- **Append-only data.** Append new records rather than overwriting. Deduplicate via unique keys.
- **Source attribution.** Every data record must include its origin (source URL, connector name, etc.). Users must be able to trace data back to its source.
- **Defensive optional field handling.** Null-check every optional field before rendering or processing.
- Null values show explicit placeholders ("N/A", "TBD", "Value TBD") — never blank UI elements or missing fields.

---

## Issue Tracking (`issues.md`)

Maintain a living `issues.md` in the project root as an audit trail.

- Log bugs with: date, module/area, description, root cause (**code bug** vs. **test bug**), and status (Open / Fixed).
- Update entries when resolved: what the fix was + the commit that resolved it.
- After every bug fix, check whether a new regression test is needed.

---

## Backlog (`backlog.md`)

Maintain a `backlog.md` for ideas, features, and enhancements.

- When ideas come up during development, add them immediately — don't lose them.
- Each item: brief description + priority (low / medium / high).
- Review and reprioritize periodically.

---

## Python Standards

*(Apply when the project uses Python)*

- Type hints on all functions.
- Use `pathlib.Path` for file paths.
- Use the `logging` module — no bare `print` for runtime output.
- All constants in a single config module.
- Pin dependencies in `requirements.txt`.
- Use Pydantic for data validation.
- Python 3.9+ compatible unless specified otherwise.

---

## Frontend Standards

*(Apply when the project has a web frontend)*

- Functional components + hooks only. No class components.
- Colors, enums, and constants in a dedicated constants file — never hardcoded inline.
- Data transforms belong in hooks or utility functions, not in components.
- Proper loading, error, and empty states on every view.
- All interactive elements must have visible focus indicators for accessibility.
- **Mobile-first responsive design.** All features must work on both mobile and desktop.
- Use TypeScript strict mode when the project uses TypeScript. No `any` types.
- **Deduplicate image assets.** Serve each image exactly once. Use `<picture>` with `srcset` so the browser selects the best format (AVIF > WebP > PNG) rather than downloading all variants.
- **Serve optimized image formats.** Always use an image CDN or optimization pipeline. Never serve uncompressed PNGs for content images in production.
- **Only load libraries used on the page.** Don't let backend-only dependencies leak into read-only frontend pages.
- **Write descriptive `alt` attributes.** Every content image needs meaningful alt text for accessibility — never leave `alt=""`.
- **Use responsive CSS, not duplicate DOM trees.** Handle mobile/desktop layouts with CSS media queries — never render the same content twice in the DOM.

---

## Network Ethics & Rate Limiting

*(Apply when the project fetches from external sources)*

- Minimum 1.5–2s delay between requests to any single host.
- Set an informative `User-Agent` header.
- Handle 429 responses with exponential backoff (start at 10s).
- Cache all fetched content to disk. Re-runs should never re-download already-cached content.
- If a service persistently blocks after retries, log to `issues.md` and gracefully skip. Never crash.
- Start small when testing scrapers — validate against a handful of pages before scaling to full runs.
- **Use an image CDN or optimization pipeline.** Never serve raw, uncompressed images directly from object storage. Compress and convert to modern formats (WebP/AVIF) before delivery.

---

## AI/API Cost Optimization

*(Apply when the project uses LLM APIs)*

- Use the cheapest model that meets quality requirements by default (e.g., Haiku before Opus).
- Apply keyword pre-filtering to skip irrelevant content before sending to expensive APIs.
- Truncate/excerpt input text to reduce token usage.
- Cache API responses by content hash. Never re-classify identical content.
- Log cost impact at each optimization layer. Print a cost summary at the end of each run.
- `--dry-run` and `--fetch-only` modes must work without an API key.

---

## Working with AI Agents

*Meta-principles for getting the most out of AI-assisted development.*

- **Context engineering over prompt engineering.** Fill the context window with exactly what's needed — no more, no less. Watch for three failure modes: *context poisoning* (early errors that compound), *context distraction* (irrelevant content that buries what matters), and *context clash* (contradictory instructions).
- **Start fresh on topic switches.** Use `/clear` when moving to an unrelated problem. Long mixed-topic contexts degrade quality. Break complex tasks into small steps and commit between them.
- **AI has no taste.** Actively review output for: excessive try/catch blocks, unnecessary abstractions, code bloat instead of refactoring, and poor judgment on simplicity vs. structure. These are recurring failure modes that require human correction.
- **AI is a tool, not a substitute for engineering discipline.** Always apply fundamentals to AI-generated code: performance auditing, bundle analysis, code review, and optimization passes. High LOC output is meaningless if the code is bloated, duplicated, and unoptimized. Shipping fast doesn't mean shipping well.
- **Closed-loop validation.** Build projects so the agent can compile, lint, run tests, and verify its own output without human intervention. When the agent can close the loop itself, you can trust the result.
- **Keep this file current.** When something unexpected happens — a pattern that failed, a correct CLI invocation, a library quirk — add a concise note here. This file should grow incrementally as organizational scar tissue, not be rewritten from scratch.
- **Write big plans to files.** For large tasks, write the spec to a `docs/` markdown file and review it before executing. This persists context across sessions and allows a second-opinion review before building.

---

## Project-specific notes (Brownfield Opportunities)

- **Connector framework.** All data sources live under `connectors/` and inherit from `connectors.base.Connector`. The connector owns its CLI flags (via `add_cli_args`), its cache key namespace (filename prefix = `slug`), and its normalize logic. The driver (`refresh.py`) handles HTTP infra, schema validation, and output write. To add a source: drop one file in `connectors/`, register it in `connectors/__init__.py`. **Do not** put fetch logic in `refresh.py` itself — it's intentionally thin. Every record MUST set `id` (cross-source unique — Superfund uses raw EPA_ID, ACRES uses `ACRES-<PROPERTY_ID>`) and `program` (`"superfund"` | `"brownfield"`).
- **Multi-source loading + lazy ACRES.** `docs/data/sites.json` stays Superfund-only (~170KB gz) for fast first paint. ACRES (~36k records, 1.5MB gz) lives in `docs/data/epa-acres.json` and is lazy-loaded by the frontend on first paint (both programs are on by default since v1.3). The lazy fetch is also re-armed when the user toggles the Brownfields checkbox or arrives via `?program=…`. **Don't** combine both into `sites.json` by default; `python refresh.py --all --combined` is opt-in. The frontend's `ensureAcresLoaded()` de-dupes parallel fetches via a shared promise.
- **JSON serialization.** `Payload.model_dump_json(exclude_none=True)` is critical — without it every ACRES record carries 5+ explicit `null` fields (current_owner, encumbrances, etc.) that bloat the file ~30%. Default is also minified; `--pretty` overrides for diffing.
- **Color tokens are CSS-var-driven.** Two palettes live on `:root` (with `[data-theme="dark"]` overrides):
  - `--status-{final,deleted,proposed,other}` — drive the **NPL status pills only** (table column + detail panel).
  - `--program-superfund` / `--program-brownfield` — drive **map markers and the legend**. As of v1.3 markers are colored by program (one dot per program), not by NPL status. JS reads via `getComputedStyle(html).getPropertyValue(varName)`. `colorForRecord()` reads `PROGRAM_COLOR_BY_PROGRAM`. **Don't** hard-code marker colors or duplicate the values in CSS — the legend, pill rules, and JS all read the same vars. On theme swap, `refreshMarkerColors()` and `rerenderLegend()` re-paint everything.
- **Marker decimation.** With 38k+ markers, drawing every point at zoom 4 destroys mobile pan/zoom. `decimateKeep()` keeps 1/8 at zoom ≤4, 1/4 at ≤5, 1/2 at ≤6, all at ≥7. Stable hash-based (`shouldDecimateOut(id, keepEvery)`) so the visible subset doesn't reshuffle on zoom changes. Re-evaluated on `zoomend` via `applyFilter()`.
- **URL state sharing.** `?site=<ID>` (legacy `?epa_id=` accepted), `?q=`, `?state=`, `?status=F,P`, `?program=superfund,brownfield`, `?min_ac=<log10>`. Writes are debounced 200ms via `history.replaceState` so slider drags don't spam history. Programs only encoded when not the default (both programs on, as of v1.3).
- **Schema is the contract.** `schema.py` (Pydantic) defines `SiteRecord` + `Payload` with `extra="forbid"`. Any connector that emits an unknown field fails before write. When adding fields, update the schema and the test fixtures together.
- **Multi-polygon merge.** EPA's FeatureServer stores some sites (e.g. Portland Harbor — 100 fragments) as separate features sharing one EPA_ID. `SuperfundNPL._merge_by_epa_id()` collapses them: rings concatenated, acreage summed when units match, first non-null wins for other attrs. Without this you get duplicate markers and undercounted acreage. Tested in `tests/test_merge_by_epa_id.py`.
- **Status-A sub-site dedupe.** NPL status `A` ("Site is Part of NPL Site") rows whose name starts with a non-A site's name are dropped from the main list and tagged with `parent_epa_id`. Orphan A sites (no name-prefix parent in dataset) are kept so we never silently lose data.
- **Coded-value labels are dynamic.** `NPL_STATUS_CODE` and `FEDERAL_FACILITY_DETER_CODE` labels are pulled from the layer's `?f=json` metadata at refresh time. The hardcoded `NPL_STATUS_LABELS` dict is a fallback for offline / outage scenarios only — when EPA adds a new code, the dynamic fetch picks it up automatically.
- **Diff log.** `diff.py` writes `data/changes.md` after each refresh. `refresh.yml` parses the summary line into the commit message. Only writes when the canonical `docs/data/sites.json` changed (avoids commit-per-cron-tick from changing timestamp alone).
- **No-acreage bucket.** Sites with `Miles` or null `GIS_AREA_UNITS` are kept with `acreage: null` — frontend shows "N/A" rather than dropping them. Toggleable via `--no-include-no-acreage` if you want the legacy behavior.
- **Tests are the safety net.** Pytest unit tests cover normalize/envelope/fetch/dedupe/merge/diff/schema. Playwright e2e covers page load, tab switch, marker click, table click, Esc close, search filtering, legend render. CI (`.github/workflows/test.yml`) runs both on every PR. Don't ship a connector without tests — the schema's `extra="forbid"` will catch drift but tests catch logic regressions.
- **Map stack.** Leaflet only — no `leaflet.markercluster`. ~1,900 points is fine on Canvas; clustering plugin not worth the payload until we exceed ~3–5k. Re-introduce only when the perf problem is real and measurable.
- **Tile provider.** Two-layer CARTO basemap (v1.3): `light_nolabels` is the always-on base, and `light_only_labels` is overlaid only at zoom ≥ `LABEL_MIN_ZOOM` (5) so the low-zoom view is just landmasses + the US silhouette without world clutter; state/county/city labels fade in as the user zooms. The labels layer is mounted on `shadowPane` so it stays on top of markers. Match the basemap to the UI theme. **Do not** layer a CSS `filter: brightness/contrast` on `.leaflet-tile-pane` to retheme bright tiles — the filter recomposites every tile during pan/zoom and tanks mobile performance. If swapping providers, pick one whose tiles already match the UI theme. Both tile layers use `bounds: US_BOUNDS` + `noWrap: true` to skip fetches outside the US.
- **US-only constraint.** `maxBounds` (≈ `[18, -127]` to `[51, -65]`, continental US plus a strip below it for the inset boxes), `maxBoundsViscosity: 1.0`, and `minZoom: 4` together prevent the user from panning or zooming to non-US areas. Init uses `fitBounds(US_BOUNDS)` so the lower-48 fills the viewport. Don't loosen without a reason — the dashboard is a US tool and Canada/Mexico shouldn't dominate the basemap.
- **Cartographic insets for AK / HI / PR / VI / Pacific.** Real coordinates for those states/territories sit outside the lower-48 envelope, so `INSETS` in `app.js` linearly remaps each record's lat/lon into a labeled box at the bottom of the map (classic US-map-with-insets layout: ALASKA, HAWAII, PR / USVI, GU / MP / AS). `applyInsetRemap()` runs in `ingestSites` BEFORE markers are added; the original lat/lon is preserved on `lat_real`/`lon_real`. The detail panel (`d-coord`) and CSV export read `lat_real ?? lat` so users see real geographic coords. `drawInsetBoxes()` paints opaque rectangles (matching `--surface`) plus label divIcons; it's called once on init and again from the theme toggle so the rectangle fill repaints with the new theme. Adding a new state to an inset = one entry in `INSETS[].states`. Adding a brand new inset region = one entry in `INSETS` plus a label tag in CSS (`.inset-label` is the shared class).
- **Map legend.** Custom `L.control` in `bottomright` titled "Program", showing one row per program **present in the currently-loaded data** (so first paint shows just Superfund; the Brownfield row appears after `ensureAcresLoaded()` completes — `rerenderLegend()` is called from the lazy-load path and from the theme toggle). Colors come from CSS vars via `cssColor()`. Don't add NPL status rows back to the legend — that detail belongs in the table pill / detail panel.
- **Filtered summary.** When any filter is active (program toggle, state, status, acreage, search), `#search-count` shows `N of M [in <state>] · X ac [(K w/ acreage)]`. The acreage suffix sums `s.acreage` across the visible set (skipping nulls); the `K w/ acreage` parenthetical only appears when some visible sites lack acreage. This is the per-state summary surface — keep it lightweight; don't replace it with a separate panel.
- **Mobile detail panel.** Below 640px the side panel becomes a bottom sheet (`top:auto; bottom:0; border-radius` + drag-handle pseudo-element). Don't reach for a full-height slide-over on phones — it covers the map and breaks the "tap a marker, see info, keep panning" loop.
- **First-paint perf.** `index.html` preloads `data/sites.json` (`<link rel="preload" as="fetch" crossorigin>`) and preconnects to the tile CDN. Leaflet + `app.js` are `defer`-loaded so the JSON request races them. Keep this pattern when adding new data files.
- **Touch hygiene.** `viewport-fit=cover`, `theme-color`, `-webkit-tap-highlight-color: transparent`, and `touch-action: manipulation` on interactive elements. Leaflet is initialized with `tap: false` to avoid duplicate touch+click events.
