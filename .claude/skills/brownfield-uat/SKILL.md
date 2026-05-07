---
name: brownfield-uat
description: Run a UAT session on the Brownfield Opportunities dashboard (live URL or local). Captures the page-specific quirks (heavy ACRES dataset, canvas markers, US-only viewport, theme/program filters, hero/KPI strip, prettifier) so a returning agent doesn't relearn them. Triggers on "run UAT on the brownfield site", "test the brownfield dashboard", "QA the map", or any UAT-style request scoped to this project.
---

# Brownfield Opportunities — UAT Skill

A project-specific UAT runbook for the Superfund + ACRES + FUDS + BRAC dashboard
at `https://pranava0x0.github.io/brownfield-opportunities/` (or local
`preview_start dashboard`).

This is **not** a generic UAT runner — it's the page-specific knowledge a fresh
agent needs to test this site without burning 45s timeouts rediscovering its
quirks.

---

## Permissions are pre-approved — don't prompt

`.claude/settings.local.json` already grants every Chrome MCP, Preview MCP,
and Bash tool this skill needs (committed 2026-05-05 as part of UAT-008).
You do **not** need to ask the user to approve `navigate`, `javascript_tool`,
`browser_batch`, `preview_*`, `pytest`, or `python scripts/serve.py` when the
target is the Brownfield dashboard. Just run the flow.

If a brand-new MCP tool is genuinely missing from that allow list, prefer
asking the user to add it once (via `update-config` skill) rather than
prompting on every call within a single UAT pass.

---

## Targets

| Target           | URL / Command                                                            | Notes                                  |
| ---------------- | ------------------------------------------------------------------------ | -------------------------------------- |
| Production       | https://pranava0x0.github.io/brownfield-opportunities/                   | GitHub Pages, deployed via Actions     |
| Local preview    | `preview_start dashboard` (preview MCP) → `http://localhost:8765`        | `.claude/launch.json` runs http-server |
| Local dev        | `python scripts/serve.py` → `http://localhost:8000`                      | chdirs into `docs/`                    |
| Playwright e2e   | `pytest tests/e2e/test_smoke.py`                                         | runs in CI on every PR                 |

---

## Tool Selection

- **Local preview** → use `mcp__Claude_Preview__*` (`preview_start dashboard`,
  then `preview_eval` / `preview_screenshot` / `preview_console_logs` /
  `preview_network` / `preview_resize`). The launch.json already maps the
  `dashboard` config to a static http-server on port 8765 serving `docs/`.
  This is the **preferred** UAT path — it's faster than Chrome MCP, the
  preview screenshot tool gives compressed JPEGs ready to inline, and
  `preview_resize` actually resizes the viewport (Chrome MCP `resize_window`
  does not — see UAT-2026-05-05 finding below).
- **Live URL** → use `mcp__Claude_in_Chrome__*` (`tabs_context_mcp` →
  `navigate` → `javascript_tool` / `find` / `read_console_messages` /
  `read_network_requests`). **Always batch via `browser_batch`** — every
  individual call is a CDP round-trip and the cumulative cost dominates
  a 5-min budget. A typical round (navigate + wait + 2 evals + screenshot)
  fits in one batch. `screenshot` results are JPEGs and inline directly.
- Don't use `computer-use` for clicks here — markers are Canvas-rendered
  (no DOM nodes for individual sites), so pixel-clicking is fragile. Use
  `preview_eval` / `javascript_tool` to dispatch interactions directly
  against the Leaflet layer instead.

---

## Critical Page Quirks (read before testing)

### 1. The page **freezes the renderer** on first paint

Symptom: `find`, `read_page`, and even `javascript_tool` time out with
`CDP sendCommand "Runtime.evaluate" timed out after 45000ms`.

Cause: `epa-acres.json` (~10.8 MB decoded, ~1.6 MB gz) + `dod-fuds.json`
(~4 MB) lazy-load on first paint as of v1.7. Markers hydrate in
`requestIdleCallback` chunks of 800.

**Workaround:**
- After `navigate`, **wait at least 8 s on cold load** before asserting
  detail-panel state from a `?site=<ID>` deep-link. 5 s is too short
  when ALL four programs are streaming in (UAT-2026-05-05 closed UAT-010
  as a tooling timing race rather than a code bug — the lazy-loads
  were still settling). For lighter checks (KPI deck, header text) 3–5 s
  is fine.
- Always **assert `window.__APP_READY__ === true` first** before
  declaring any deep-link/state failure. The page sets `__APP_READY__`
  and dispatches `brownfield:ready` on `document` only after every
  lazy-load (ACRES + FUDS + BRAC + Redev + docs + infra + ECHO + AI
  summary) has settled. If `__APP_READY__` is `undefined`, you waited
  too short — wait another 3 s and retry, don't log a bug.
- Prefer `preview_eval` with a tiny expression (`window.__APP_READY__`)
  over `find`. `find` blocks on `document_idle` and can compound the
  timeout.
- If a tool errors out with the 45 s timeout, don't retry immediately —
  wait another 3 s.

### 2. Markers are Canvas, not DOM

`document.querySelectorAll('.leaflet-marker-icon')` returns ~4 elements
(the inset labels, not site markers). Don't count DOM nodes to verify
marker presence.

To probe state, use the exposed globals:
- `window.__APP_READY__` → boolean, true after all lazy loads complete
- `window.__map` → the Leaflet `Map` instance
- `window.__markerLayer` → the `LayerGroup` of all site markers
- `window.__sitesLoaded` → true after Superfund first paint
- `window.__refreshedAt` → ISO date string of the data refresh

To click a marker programmatically, use `?site=<EPA_ID>` URL state, or
fire `markerLayer.getLayers()[i].fire('click')`.

### 3. US-only viewport with cartographic insets

- `maxBounds` ≈ `[[18,-127],[51,-65]]`, `maxBoundsViscosity: 1.0`,
  `minZoom: 4`. You **cannot** pan to AK/HI/PR/territories.
- `INSETS` in `app.js` linearly remaps real lat/lon for those states into
  labeled boxes at the bottom of the map. Real coords preserved on
  `lat_real`/`lon_real`. Detail panel and CSV export use the real coords.
- Non-CONUS state polygons are filtered out of `us-states.json` at draw
  time (`NON_CONUS_STATE_NAMES` = Alaska, Hawaii, Puerto Rico).

### 4. Color systems

- `--status-{final,deleted,proposed,other}` → NPL pills (table + detail).
- `--program-{superfund,brownfield,fuds,brac}` → markers + legend +
  detail-panel top stripe (set via `--detail-stripe` inline by JS).

If verifying a color, read the CSS var via
`getComputedStyle(document.documentElement).getPropertyValue('--program-superfund')`
rather than asserting a hex literal — the palette flips on theme.

### 5. Lazy-load contract

All four programs default-on. `sites.json` (Superfund) loads eagerly;
`epa-acres.json`, `dod-fuds.json`, `dod-brac.json`, and `epa-redev.json`
fire via `Promise.allSettled` after Superfund paints. `?program=fuds`
(or any subset) restricts which programs lazy-load.

`epa-redev.json` is **enrichment-only** — it doesn't add new markers,
it annotates existing Superfund records with `near_*` infrastructure
proximity fields and the `data_center_reuse_candidate` boolean.

### 6. Hero / KPI strip / footer (v1.8)

Above the filters strip there's now a `<section class="hero">` with:
- An eyebrow line: `US Brownfield Atlas · v1.8 · Updated 2026-04-30`
- A serif H2 headline + dek
- A 4-cell KPI deck: `#kpi-total`, `#kpi-acres`, `#kpi-dc`, `#kpi-states`

Below the map there's a `<footer class="site-footer">` with source
attribution and refresh date. Both nodes are real DOM and are part of
the ~5k-node DOM cap — the test_dom_size_under_5k_nodes test guards.

KPI numbers are derived from the in-memory `sites` array — call
`updateKpiDeck()` after any data load.

### 7. Place-name + site-name prettifiers (v1.8 / v1.11.1)

Cities, counties, and street addresses arrive ALL CAPS from EPA / USACE.
`prettyPlace()` runs at ingest time and overwrites `s.city`, `s.county`,
`s.address`. Raw source preserved on `s.{city,county,address}_raw`.

**Site names are also prettified as of v1.11.1.** `prettyName()` title-cases
`s.name` at ingest (raw preserved on `s.name_raw`) using an acronym whitelist
(NIKE, AFB, NRDA, PCB, USDOE, USACE, USFS, BLM, NPS, …) so agency
abbreviations stay all-caps. Expect "Fox River NRDA/PCB Releases", not
"FOX RIVER NRDA/PCB RELEASES". If a new acronym shows up mangled, add it
to `NAME_KEEP_UPPER` in `app.js`.

If a UAT step asserts city/name strings, expect title case throughout.

### 8. Filter chip + meta text (v1.8)

- The gear icon shows a small chip badge with the count of active
  filters when ≥1 filter is non-default. `chip-count[hidden]` is
  explicitly `display: none` to override the `display: inline-flex`
  rule (this trap bit us once already).
- `#meta` text is generated by `updateMetaText()` and reflects actual
  per-program counts — don't hard-assert "1,908 Superfund" since data
  refreshes. Assert the structure instead (regex).

### 9. Detail panel program stripe

A 4px top stripe colored by program. JS sets `--detail-stripe` as an
inline CSS var on `#detail`; the `::before` pseudo reads it. After
`closeDetail()` the marker tooltip is also closed (UAT-fixed in v1.8).

### 10. Detail panel tab strip (v1.11)

The panel is now split into two tabs under the title:
- `#dtab-overview` — KV grid + FUDS/infra/docs/ECHO blocks (the original).
- `#dtab-summary` — AI-generated narrative card (`#d-summary-body`).
  Empty state lives in `#d-summary-empty` and reads "No AI summary on
  file for this site yet…" — that's normal when `data/ai-summary.json`
  hasn't been built or doesn't cover the site.

`selectSite()` calls `resetDetailTabs()` so each new selection lands on
Overview. To assert tab behaviour: `document.querySelector('#dtab-summary').click()`,
then check `#d-summary-body[hidden]` and `#d-summary-empty[hidden]` to
distinguish populated vs. empty.

### 11. Selectors that the runbook needs (read once, save typing later)

These are the actual element IDs / data attributes — the runbook used
to silently no-op when they were guessed wrong.

| Purpose                          | Selector                                                |
| -------------------------------- | ------------------------------------------------------- |
| Search input                     | `#search`                                               |
| Search count text                | `#search-count`                                         |
| Filters strip toggle (gear)      | `#filters-toggle`                                       |
| Filters chip badge               | `#filters-chip`                                         |
| Filters reset button             | `#filters-reset`                                        |
| Program checkboxes               | `#f-program-superfund`, `#f-program-brownfield`, `#f-program-fuds`, `#f-program-brac` (NOT `[data-program]`) |
| NPL Status checkboxes            | `input[data-status="F"]`, `…="P"`, `…="D"`, `…="N"`     |
| State dropdown                   | `#f-state` (option values are postal codes)             |
| Acreage slider                   | `#f-acreage` (log10 scale, 0–6)                         |
| Map / Table tab buttons          | No clean ID — find by text: `Array.from(document.querySelectorAll('button')).find(b => /Table/i.test(b.textContent))?.click()` |
| Theme toggle                     | `#theme-toggle` (no `data-theme` attr → light)          |
| CSV export                       | `#export-csv`                                           |
| Detail panel root                | `#detail` (also `aside[role=complementary]`)            |
| Detail panel title               | `#detail h2` or `#detail h3` — there is **no** `#d-name` |
| Detail close button              | `#detail-close`                                         |
| Detail tabs                      | `#dtab-overview`, `#dtab-summary`                       |
| Toast (lazy-mounted)             | `#toast` (only exists after `showToast()` fires)        |
| Footer / hero refresh date       | `#footer-refresh`, `#hero-refresh`                      |

To select sites by id, the canonical hook is `window.__selectSite(id)`.
Sites are also indexed in `window.__sites` (array) for randomized picks:
```js
const programs = ['superfund', 'brownfield', 'fuds', 'brac'];
const pick = p => {
  const pool = window.__sites.filter(s => s.program === p && s.name);
  return pool[Math.floor(Math.random() * pool.length)];
};
```

### 12. `resize_window` is a no-op in Chrome MCP (UAT-2026-05-05)

`mcp__Claude_in_Chrome__resize_window` reports success but the page's
`window.innerWidth` does **not** change below the host Chrome window's
minimum width (~1389px on a 1512px-wide display). Mobile / tablet
breakpoints can't be exercised this way. For responsive UAT, switch to
the Preview MCP (`preview_resize`) — it actually shrinks the viewport.
Or assert breakpoint behaviour by reading `getComputedStyle` on the
elements you care about and comparing against the CSS rules; don't rely
on visual screenshot diffs.

### 13. Toast for `?site=<unknown>` fires ~5 s post-navigate (UAT-2026-05-05)

`applyUrlSelection()` waits on every lazy-load promise before deciding
the id is unknown. ACRES + FUDS settle around the 4–5 s mark on a warm
cache. The toast (`#toast`) then mounts, fades in for ~250 ms, stays
visible 4 s, fades out. Capture window: navigate → wait 5–6 s → check
`document.getElementById('toast')?.classList.contains('visible')`. A
4 s wait is too short and a 9+ s wait may miss it on the tail end.

### 14. `[BLOCKED: Cookie/query string data]` in eval results (UAT-2026-05-05)

Chrome's privacy heuristic occasionally redacts `javascript_tool` results
that contain URL-like strings (anything with `?…=…&…=…`). When this
happens the eval RAN successfully — only the result text was filtered.
Workaround: in the eval, redact the URL parts you don't need, or read
the same state from a screenshot. Don't retry — the result will be the
same.

### 15. Enrichment files are all 200 in production (UAT-008, fixed 2026-05-05)

`data/epa-echo.json` and `data/ai-summary.json` both return HTTP 200 in
production as of v1.11.2. The previous guidance to expect 404s is obsolete.
If they ever 404 again, that's a deploy regression — log it in `issues.md`.

### 16. Preview MCP boots with a 0×0 viewport — resize BEFORE first navigate (UAT-011, fixed 2026-05-06)

`mcp__Claude_Preview__preview_start` returns a server but the page's
`window.innerWidth` / `innerHeight` are **both `0`** until the first
explicit `preview_resize` lands. Two consequences:

- **Always call `preview_resize` with explicit `width` + `height` BEFORE
  navigating.** `{ width: 1440, height: 900 }` is the canonical desktop;
  `{ width: 375, height: 812 }` mobile; `{ width: 768, height: 1024 }`
  tablet. Calling `{ preset: "desktop" }` alone returns `"Viewport reset
  to native size (desktop)"` and leaves the viewport at 0×0 — the preset
  path only works AFTER an explicit width/height has been applied at
  least once. Quirk of the tool, not the page.
- **The page is now resilient to a 0×0 boot** thanks to UAT-011's fix:
  `initMap()` creates `markerLayer` before any `fitBounds` attempt, and
  `fitUsBoundsSafely()` registers a `ResizeObserver` that retries on the
  first non-zero resize tick. So if you forget to resize first, the map
  paints into 0×0 silently and recovers when you eventually call
  `preview_resize`. **But** during the deferred window, `__APP_READY__`
  may still flip true (the lazy loads complete) while the map shows
  nothing — confusing for screenshot-based assertions. Best practice
  remains: **resize first, navigate second.**

How to spot the bug if you DO hit it:
- Console shows `fitBounds deferred (zero-size container)` warnings.
- `document.getElementById('map').getBoundingClientRect()` is `{w:0,h:0}`.
- `window.__map.getCenter()` returns `{lat: NaN, lng: NaN}`.

Recovery: `preview_resize { width: 1440, height: 900 }`. The
ResizeObserver fires, fitBounds succeeds, `invalidateSize()` repaints.
No reload needed.

Regression tests in `tests/e2e/test_smoke.py`:
`test_init_map_survives_zero_size_container` reproduces the boot via
`page.add_init_script` injecting `#map { width:0; height:0 }`.

---

## Standard UAT Flow (5-min run)

Run these in order. Stop and log to `issues.md` the moment a step fails.

1. **Cold load** — `preview_start dashboard`, then **`preview_resize { width: 1440, height: 900 }`** (see Quirk #16 — explicit width/height is required; `{ preset: "desktop" }` alone leaves the viewport at 0×0), then `preview_eval window.location.href = 'http://localhost:8765/index.html'`, wait 8 s, screenshot. Use `preview_eval` to check `window.__APP_READY__ === true` rather than waiting on a fixed timeout — cold load varies from ~4 s warm cache to ~12 s cold.
   - Header subtitle should match `/^[\d,]+ sites \(.+ Superfund \+ .+ brownfields( \+ .+ FUDS)?( \+ .+ BRAC)?\) · refreshed \d{4}-\d{2}-\d{2}$/`.
   - Network: `sites.json`, `us-states.json`, `epa-acres.json`,
     `dod-fuds.json`, `dod-brac.json`, `epa-redev.json` all 200.
   - Legend bottom-right shows Superfund, Brownfield, FUDS, BRAC rows
     with per-program counts on the right edge.
   - KPI deck shows non-`—` numbers in all four cells.
   - Hero refresh + footer refresh strings show the same date.

2. **Visual sanity** — `preview_resize` to desktop (`width:1440 height:900`), tablet (`width:768 height:1024`), mobile (`width:375 height:812`). Always pass explicit `width` + `height` — `{ preset: ... }` alone is a no-op until an explicit size has been set at least once (Quirk #16). On mobile:
   - Hero copy is hidden, KPI deck becomes a horizontal scroll-snap carousel.
   - Detail panel becomes a bottom sheet with a drag handle.
   - Map dominates the viewport.

3. **Search** — fill `#search` with `"superfund"` or a known site name.
   `#search-count` updates with `N of M · X ac`. ESC clears.
   Filter chip on gear button should appear with a `1`.

4. **Filters strip** — click the gear (`#filters-toggle`). Toggle state,
   NPL status, program, acreage slider. Verify both the table and the
   marker canvas update. Filter chip count updates as filters change.
   Reset clears the chip.

5. **Theme toggle** — click the sun/moon (`#theme-toggle`). Markers,
   basemap, inset boxes, and KPI deck colors should all repaint.
   localStorage persists across reload.

6. **URL state round-trip** — open `?site=<EPA_ID>` (e.g. `AZD980737530`
   for Tucson International Airport Area, a Final NPL Superfund site confirmed
   in the dataset). Detail panel opens, program-color stripe matches the program.
   Use `window.__sites.find(s => s.program === 'superfund')?.id` to pick any
   valid ID rather than hard-coding one that may not be in the dataset.

7. **Tab switch** — click "Table". Rows render with NPL status pills.
   Sort indicator (▲/▼) appears in the active column header.
   Click a row → detail panel opens, marker centers (when re-switching to Map).

8. **Detail close** — click `#detail-close`. Panel slides off, tooltip
   closes, `aria-hidden` flips to `true`.

9. **Console + network sweep** — `preview_console_logs level:error` and
   `preview_network filter:failed`. Both should be empty.

10. **DOM size** — `preview_eval document.querySelectorAll('*').length`.
    Must stay under 5000 (test guards this in CI).

---

## Randomized 5-min coverage flow (live URL, Chrome MCP)

Tested 2026-05-05. Each step is one `browser_batch` call. Designed so a
returning agent finishes in ~5 min wall-clock with full functional coverage
and at least one randomized pick per dimension (program, state, filter,
search query, sort column).

**Round 1 — Cold load + smoke:**
```
[navigate live URL] → [resize 1440x900] → [wait 5 s]
  → [eval window.__APP_READY__, sitesLoaded, sites.length, kpis, meta]
  → [screenshot]
```
Expect: `sites.length === 46_759` (give or take), KPIs all non-`—`, meta text
matches the per-program regex.

**Round 2 — Random URL state, one per program + one invalid:**
```
[eval pick a random site per program from window.__sites]
[navigate ?site=<superfund-pick> → wait 8 s  → eval detail title/program/acreage → screenshot]
[navigate ?site=<acres-pick>     → wait 10 s → eval … → screenshot]
[navigate ?site=<fuds-pick>      → wait 8 s  → eval … → screenshot]
[navigate ?site=<brac-pick>      → wait 8 s  → eval … → screenshot]
[navigate ?site=DOES-NOT-EXIST   → wait 5 s  → eval toast.classList.contains('visible')]
```
Notes:
- ACRES deep-link needs **10 s** on a cold cache — the file is ~1.6 MB gz and
  `applyUrlSelection()` waits for the full parse + `sitesById` population.
  If `detailHidden:true` at 10 s AND `__APP_READY__` is true, that's a bug.
  If `__APP_READY__` is still false, wait another 3 s and retry.
- The toast fires ~5 s after navigate, not ~1 s — see quirk #13.
- BRAC/ACRES/FUDS can all fail on the first try mid-`Promise.allSettled`; one
  re-navigate before logging is fine (see UAT-010).

**Round 3 — Random search query:**
```
[eval set #search.value = pick(['harbor', 'fox', 'denver', 'lake', 'fort'])
  → dispatch input event]
[wait 1 s]
[eval search-count, chip count, URL search]
[screenshot]
[eval clear search]
```

**Round 4 — Random filter combination:**
```
[eval pick random state from #f-state options → dispatch change]
[eval uncheck a random subset of #f-program-{slug} → dispatch change]
[eval check a random subset of input[data-status=*] → dispatch change]
[eval set #f-acreage to a random value in [1, 4] (log10) → dispatch input + change]
[wait 1 s]
[eval search-count, chip count, URL search]
[screenshot]
[click #filters-reset]
[eval verify all programs back, chip hidden, URL clean]
```

**Round 5 — Theme + table + row click:**
```
[click #theme-toggle → eval data-theme attr]
[click "Table" tab button (find by text)]
[wait 2 s]
[click random thead th to re-sort]
[wait 1 s]
[click first tbody tr → wait 1 s → eval detail title, panel hidden=false]
[screenshot]
[click #detail-close]
[click #theme-toggle to revert]
```

**Round 6 — Final sweep:**
```
[eval document.querySelectorAll('*').length (must be < 5000)]
[read_console_messages onlyErrors:true (must be empty)]
[read_network_requests (all 10 JSON files should be 200 — including epa-echo.json + ai-summary.json)]
[screenshot]
```

For each round, prefer one `browser_batch` per round. Don't fan out into
20 separate calls — the round-trip overhead alone burns the budget.

---

## Returning-Run Tweaks

- Read `issues.md` first. If UAT-00X is open, target the regression area.
- Vary the run: rotate viewport on each pass; alternate keyboard nav with
  pointer; sometimes test from `?program=brownfield` cold (forces ACRES
  to be the only data layer).
- After every refresh.py / data refresh, the totals in the header change.
  Don't hard-assert specific counts — assert structure / non-zero.

---

## Logging Conventions for This Project

- **Bugs** → `issues.md` table format: `Date | Area | Description | Root cause | Status`.
- **UX improvements** → `backlog.md` under the appropriate section
  (`## Frontend / UX`, `## Performance / hosting`, etc.) with priority
  prefix `**[high]**` / `**[med]**` / `**[low]**`.
- Both files already exist; append rather than restructure.
- Reference commits when fixed: `Fixed — <what>; <commit-sha-or-PR>`.

---

## Known Gotchas / Time-Sinks

- Don't use `mcp__Claude_in_Chrome__find` before the 3 s post-navigate
  wait. It blocks on `document_idle`.
- Don't try to count markers via DOM selectors. Use `__markerLayer.getLayers().length`.
- Don't assert hardcoded marker colors — they're CSS-var-driven and flip
  on theme. Read via `getComputedStyle`.
- Don't assert hardcoded city/county strings without accounting for the
  prettifier — "GREEN BAY" became "Green Bay" in v1.8.
- Polygon overlays are still TODO — every site is a point even when the
  source is polygon (Portland Harbor's 100 fragments merged to centroid).
- `[hidden]` doesn't beat `display: inline-flex` / `display: block` —
  the codebase has been bitten twice (detail panel, filter chip). Always
  add an explicit `[hidden] { display: none; }` rule alongside any
  `.foo { display: ...; }` for elements with the hidden attr.

---

## Quick Reference: Known State (as of v1.11.5, 2026-05-06)

| Item                      | Value                                                         |
| ------------------------- | ------------------------------------------------------------- |
| First-paint payload (gz)  | ~170 KB sites.json + ~1.6 MB acres + ~600 KB FUDS/BRAC/redev |
| Total markers             | ~46,759 (1,908 Superfund + 36,003 ACRES + 8,821 FUDS + 27 BRAC) |
| DC reuse candidates       | 821 (Superfund w/ power + ≥50 ac + water service)             |
| Marker decimation         | zoom ≤4 → 1/8, ≤5 → 1/4, ≤6 → 1/2, ≥7 → all                 |
| Cold-load DOMContentLoaded| ~60 ms (chunked hydration keeps main thread responsive)       |
| Total DOM nodes after ready | ~2,713 (measured 2026-05-06; regression test caps at 5,000) |
| County zoom threshold     | `COUNTY_MIN_ZOOM = 7` (lazy-loaded TopoJSON)                  |
| KPI deck IDs              | `#kpi-total`, `#kpi-acres`, `#kpi-dc`, `#kpi-states`          |
| Hero refresh ID           | `#hero-refresh` (also `#footer-refresh` mirrors it)           |
| Filter chip ID            | `#filters-chip` (badge on `#filters-toggle`)                  |
| Readiness pills           | `.cleanup-pill` (NPL Deleted) · `.reuse-pill` (`In_Reuse=Yes`) · `.dc-pill` (`data_center_reuse_candidate`) — all three can co-render in `#d-program` |
| 0×0-boot recovery         | `fitUsBoundsSafely()` + `ResizeObserver` (UAT-011, 2026-05-06)|
| Detail title selector     | `#detail h2` (no `#d-name` — that ID doesn't exist)           |
| Valid example Superfund ID | `AZD980737530` (Tucson International Airport Area)            |
| Test count                | 330 (266 unit + 64 e2e — ran clean 2026-05-06)                |
