# JTBD UX plan — 2026-07-26

Goal (user ask): make the dashboard's views **simple and focused around jobs-to-be-done** for
nuclear-reactor siting, data-center siting, and both. Grounded in 2026 market research
(JLL/CBRE/Area Development: **speed-to-power is now the #1 screen**; LBNL Queued Up 2025:
median interconnection queue 55 months, only ~13% of queued capacity ever completes —
an existing interconnection is the single highest-leverage fact about a site).

Three features, scoped to ship in one session. Constraints at the bottom are hard rules.

---

## Feature A — JTBD quick-start strip

A slim strip that answers "what are you siting?" in one click. New users see it; one
click routes to the right view+lens; dismissible.

- **Markup**: `<nav id="jtbd-strip" class="jtbd-strip" aria-label="Quick start">` placed in
  `index.html` immediately after the closing `</details>` of `#kpi-disclosure`, inside
  `<header>`. Content: a short lead-in `<span class="jtbd-lead">What are you siting?</span>`
  plus 4 job buttons + 1 dismiss button:
  - `<button class="jtbd-chip" data-jtbd="dc">🖥 Data center</button>` → activate Rankings tab (`#tab-candidates`) + DC lens
  - `<button class="jtbd-chip" data-jtbd="gen">⚡ Power generation</button>` → Rankings + Generation lens
  - `<button class="jtbd-chip" data-jtbd="reactor">⚛ Nuclear reactor</button>` → Nuclear Siting tab (`#tab-ap1000`)
  - `<button class="jtbd-chip" data-jtbd="mfg">🏭 Factory</button>` → Rankings + Manufacturing lens
  - `<button id="jtbd-dismiss" class="jtbd-dismiss" aria-label="Hide quick start">×</button>`
- **Behavior** (`wireJtbdStrip()` in app.js, called from boot):
  - Routing must reuse the EXISTING tab-activation + lens-set code paths (find the click
    handlers for `.tab` and `[data-cand-lens]` and call the same functions — do not
    duplicate tab logic). Lens change must update `candidatesState.lens` + the lens button
    active states + rebuild the view + sync `?lens=` exactly as a manual lens click does.
    Simplest robust approach: programmatically `.click()` the real tab button and lens button.
  - Dismiss: sets `localStorage.jtbdDismissed = "1"` and hides the strip (attribute
    `hidden` + the `[hidden]{display:none}` guard — see constraints). On boot, if
    `localStorage.jtbdDismissed === "1"`, hide before first paint (no flash).
  - Clicking any job chip ALSO dismisses is **wrong** — keep the strip visible after use
    (users try multiple jobs); only × hides it.
- **Style**: one row, small chips (match `.persona-row` / `.cand-filter` visual language),
  horizontal scroll on mobile (like the KPI carousel), visible focus rings, both themes
  via existing CSS vars. Keep total added DOM ≤ ~20 nodes.
- **Tests** (`tests/e2e/test_jtbd_strip.py`, follow existing e2e conventions —
  `page.goto` + `wait_for_function("window.__APP_READY__ === true")`):
  1. strip renders with 4 chips;
  2. clicking `[data-jtbd="gen"]` lands on Rankings with `?lens=gen` and the gen lens button active;
  3. clicking `[data-jtbd="reactor"]` activates `#view-ap1000`;
  4. dismiss hides it and it stays hidden after reload;
  5. `tests/e2e/` DOM-size guard still passes (see constraints).

## Feature B — Civilian nuclear pipeline: map overlay + Nuclear Siting section

The data has been on disk since 2026-06-30 and never rendered: `docs/data/nuclear-civilian-sites.json`
(67 sites; fields: id, name, state, county, city, lat, lon, status, inl_category
[dark_green 4 / light_green 14 / blue 8 / yellow 29 / red 10 / post_study 2], reactor_type,
units_planned, mwe_per_unit, col_status, owner_operator, market, iso_rto, notes, nrc_url)
and `docs/data/nuclear-brownfield-proximity.json` (`{generated_at, radius_mi, brownfield_dataset,
records}` — per-nuclear-site lists of Superfund sites within 50 mi). This is backlog item
"[high] Frontend Nuclear Sites tab (or overlay layer)".

- **Map overlay** — `ensureNuclearSitesLoaded()` in app.js, modeled line-for-line on
  `ensureReferenceCampusesLoaded()` (app.js:1556) / `ensurePlannedRetirementsLoaded()` (1682):
  - Lazy-load the JSON in the same `lazyLoads.push(...)` fan-out (app.js:876-878).
  - Markers ONLY for the promising categories: `dark_green`, `light_green`, `blue`
    (26 sites) — yellow/red/post_study stay data-only (map noise otherwise).
  - `L.divIcon` with a distinctive atom glyph ⚛ (`.nuclear-site-icon`), NOT ★ (reference
    campuses) or ◆ (retired) or ⬢ (planned retirements). Color by category via NEW CSS vars
    (light/dark pairs, follow the `.planned-retirement-icon` pattern):
    `--nuclear-ready` (dark_green), `--nuclear-feasible` (light_green), `--nuclear-restart` (blue).
  - Legend: one "Nuclear pipeline" row group added via the existing `rerenderLegend()`
    mechanism when the layer is populated (three sub-rows is too much — ONE row labeled
    "Nuclear pipeline site" using the `--nuclear-ready` color; category detail lives in the popup).
  - Popup: name; category label ("AP1000 ready" / "AP1000 feasible" / "Restart / SMR");
    status; COL status; owner/operator; units × MWe; ISO/RTO; notes (truncate ~200 chars);
    NRC/source link; then "Nearby tracked brownfields:" — top 3 from the proximity file
    (name · distance mi), each linking `?site=<id>` (same-tab navigation like the retired-
    industrial popup's tracked-site link).
  - Call `recordRefreshDate(payload.generated_at)` in the loader (MANDATORY — see CLAUDE.md
    "Last-update date"), and add BOTH new file names to the file list in
    `test_refresh_date_reflects_freshest_data_file` (only load the main one in the loader;
    proximity can lazy-load on first popup open OR load together — implementer's choice,
    but recordRefreshDate any file you fetch).
- **Nuclear Siting tab section** — in `#view-ap1000`, AFTER the existing military table
  (`#ap1000-cards`), add a lazily-built section (built on first tab activation, alongside
  `buildAp1000View()`): heading "Civilian nuclear pipeline — 67 tracked sites", one-paragraph
  lead (the INL Aug-2024 AP1000 study is the base list + restarts; cite it), then a compact
  table of the 26 promising sites: Name · ST · Category chip · Status · COL status ·
  Owner/operator · Units × MWe · ISO/RTO. Sort: dark_green, light_green, blue, then by name.
  Below the table one muted line: "41 further sites tracked in the source data (yellow/red
  tiers) — included in the data file and map search, not shown here."
  Row click or a small "map →" link: switch to Map tab centered on the site (reuse existing
  map/zoom helpers if available; `map.setView([lat,lon], 9)` is fine).
- **Copy updates in the same view** (research-driven, keep each to 1-2 sentences, cited inline
  with links):
  1. In the `#view-ap1000` lead paragraph: update "Request for Lease (AFCEC-26-R-0002)"
     wording to note **selection pending as of July 2026** (original Jan-2026 target passed
     with no public award), and that the program **expanded to Alaska via AFCEC-26-R-0006**
     (JBER, Eielson, Clear SFS — ~4,700 ac, proposals due June 29 2026).
  2. New short "Adjacent DoD programs" note (a `<details>` like `.ap1000-help`, or 2
     sentences at the end of the lead): the Air Force/Space Force **ANPI** microreactor
     program has already paired vendors to 3 bases (Radiant → Buckley SFB CO, Westinghouse
     eVinci → Malmstrom AFB MT, Antares → Joint Base San Antonio TX; April 2026;
     https://www.ans.org/news/2026-04-13/article-7930/ and
     https://www.powermag.com/air-force-anpi-picks-put-radiant-antares-westinghouse-on-track-for-first-on%E2%80%91base-microreactors-by-2028/),
     and DOE selected Amentum for a 1 GW AI data center + ~2 GW on-site generation at
     **Savannah River Site** (July 2026;
     https://www.energy.gov/nnsa/articles/nnsa-selects-amentum-ai-data-center-and-energy-project-savannah-river-site).
- **Tests** (`tests/e2e/test_nuclear_civilian.py`):
  1. overlay loads (pattern: `test_planned_retirements_overlay_loads`) — marker layer
     populated with exactly the promising-category count from the data file;
  2. legend row "Nuclear pipeline site" appears after load;
  3. Nuclear Siting tab shows the civilian section with 26 rows;
  4. a popup for a known dark_green site (e.g. `vc-summer-sc`) contains its category label
     and at least one nearby-brownfield link (skip gracefully if that site has no neighbors
     in the proximity file — pick one that does, at data-load time in the test).
  5. `test_refresh_date_reflects_freshest_data_file` still passes WITH the new files added
     to its list.

## Feature C — JTBD copy polish elsewhere (small, surgical)

1. **Rankings help** (`.cand-help-body` in index.html): add one sentence at the top of the
   second paragraph: power access leads the weighting because speed-to-power is the #1
   2026 site-selection screen (median new interconnection ≈ 55 months per LBNL "Queued Up"
   2025; link https://emp.lbl.gov/queues) — and sites near retired/retiring plants can
   inherit an existing interconnection.
2. **Grid Inherit badge tooltip** (in the candidates Signals rendering, app.js): change the
   `title` to "Existing interconnection nearby — potential to skip the ~4.5-year median
   grid-connection queue (LBNL Queued Up 2025)". Do NOT rename the badge label.
3. **Retired Sites lead** (`.retired-lead p` in index.html): append one sentence: DOE's
   coal-to-nuclear study screened 394 coal sites and found ~80% suitable for SMRs (33 for
   large reactors), with 15-35% construction savings from reusing grid/cooling/civil
   infrastructure (link https://www.energy.gov/ne/articles/doe-report-finds-hundreds-retiring-coal-plant-sites-could-convert-nuclear).
4. **Manufacturing lens phrasing** (`.cand-help` tiers paragraph or the mfg mention):
   adjust wording so rail reads as a **prerequisite/risk gate** rather than a ranked
   driver ("rail access is a gate for heavy-materials plants"), matching Area Development's
   2026 sequential-gates framing. Copy only — weights unchanged.

---

## HARD CONSTRAINTS (violating any of these is a do-over)

1. **DOM budget**: first-paint cap is 5,000 nodes and headroom is only ~124
   (CLAUDE.md "Paginated table"). Feature A adds ≤~20 nodes; Feature B's tab section builds
   lazily on tab activation (like the existing skeleton pattern — `view-ap1000` is ~39 nodes
   at first paint and must stay under ~60). After changes, `python3 -m pytest
   tests/e2e/ -k dom_size -q` MUST pass. If over: trim the strip (drop the lead-in span).
2. **`[hidden]` trap**: every element that uses the `hidden` attribute AND has a `display:`
   override needs an explicit `[hidden]{display:none}` rule (CLAUDE.md).
3. **Don't touch**: `STATE_DC_REGULATION`, `STATE_DC_INCENTIVES`, anything in
   `docs/dc-score.js` or `docs/ap1000-score.js` (weights/scoring are handled separately
   this session), `connectors/`, `schema.py`, `refresh.py`, `docs/data/*.json` contents.
   Also don't edit `backlog.md`/`CLAUDE.md`/`AGENTS.md` (session wrap-up handles those).
4. **Don't change element ids or tab ids** — e2e tests depend on them. New ids are fine.
5. **Existing loaders' race rule does not apply** to these overlays (they don't join into
   `sitesById`) — but the popup's `?site=<id>` links must go through the existing
   `selectSite`/URL path, not a custom lookup.
6. **Theme-safe**: new colors as CSS var pairs on `:root` + `[data-theme="dark"]`; JS reads
   via `cssColor()`. No hardcoded hex in JS or inline styles.
7. **Run before declaring done**: full unit suite (`python3 -m pytest tests/ -q
   --ignore=tests/e2e`), your two new e2e files, the dom-size test, the refresh-date test,
   plus `tests/e2e/test_candidates_view.py` and (if it exists) the ap1000 e2e file.
   The e2e suite needs the local server pattern the existing tests use — read one existing
   e2e file first and copy its fixture usage. ALL must pass.
8. **Leave everything uncommitted** — report a summary of changes + test results; the
   supervising session reviews and commits.
