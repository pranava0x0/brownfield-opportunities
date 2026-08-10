# design.md — Brownfield Opportunities

> The visual and interaction design system for the dashboard. Captures the
> tokens, components, responsive rules, and editorial conventions accumulated
> across v1.0 → v1.11. Companion to `CLAUDE.md` (which covers the data
> pipeline). Source of truth for the look-and-feel; when something here drifts
> from [docs/style.css](docs/style.css) or [docs/app.js](docs/app.js), the
> code wins and this file is wrong.

---

## 1. Product positioning

Two sentences, because every design call below derives from them:

1. This is an **editorial atlas**, not a SaaS dashboard. Buyers, developers,
   journalists, and analysts use it to investigate ~47,000 federal
   contaminated-site records. Closest competitors in spirit are FT / Bloomberg
   / Greater Greater Washington, not Salesforce / Tableau.
2. The **map is the product**. Chrome must stay small. Filters, KPI cards,
   detail panel — anything that isn't the map — earns its pixels by helping
   the user understand or narrow what they're looking at.

Implications that show up below:
- Serif display type for headlines (editorial gravitas).
- Sources cited in the footer (editorial accountability).
- Bottom-sheet detail on phones (don't cover the map).
- Tabular numerals everywhere (FT-style metric density).
- No web fonts, no backdrop-blur (perf as a design constraint).

---

## 2. Design tokens

All tokens live as CSS custom properties on `:root`, overridden by
`[data-theme="dark"]`. JS reads them via `cssColor()` /
`getComputedStyle(html).getPropertyValue(varName)` so every surface (markers,
legend dots, inset boxes, basemap polygons, pill backgrounds) re-paints
correctly when the theme toggle flips. **Never hardcode a hex anywhere outside
`:root` / `[data-theme="dark"]`.** See [style.css:7-92](docs/style.css:7).

### 2.1 Color — surfaces & text

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#f1f2f4` | `#0d121a` | Page background |
| `--bg-elev` | `#fafafb` | `#131923` | Hero strip, footer |
| `--surface` | `#ffffff` | `#161c26` | Cards, panels, table head, legend |
| `--surface-2` | `#f4f5f7` | `#1d2531` | Inputs, tab bar bg, summary card |
| `--border` | `#d8dde6` | `#2c3645` | Hairlines |
| `--border-strong` | `#b8c0cc` | `#3b4757` | Sticky-head divider, drag handle |
| `--text` | `#15212e` | `#e8eaef` | Body |
| `--text-soft` | `#3b4655` | `#b9c2d0` | Table cells, dd values |
| `--muted` | `#6b7480` | `#94a0b1` | Labels, captions, "not available" |
| `--accent` | `#1c5e9e` | `#7eb6e8` | Links, focus rings, primary CTA |
| `--accent-strong` | `#0e4378` | `#a4cdf2` | Hover state, skip link bg |
| `--accent-soft` | `rgba(28,94,158,0.08)` | `rgba(126,182,232,0.12)` | Selected row, hovered cell |

Naming convention: surfaces stack from `bg` → `bg-elev` → `surface` →
`surface-2`. If you need another tier, push out, don't rename.

### 2.2 Color — semantic palettes

Two independent palettes that must never be conflated:

**NPL status pills** (status of cleanup) — `--status-{final, deleted, proposed, other}`. Used **only** in the STATUS column of the table and the NPL pill in the detail panel. Never used for markers, legend, or anywhere else.

| Code | Token | Light | Dark | Meaning |
|---|---|---|---|---|
| `F` | `--status-final` | `#b8332f` | `#ef5050` | Final on NPL |
| `D` | `--status-deleted` | `#8a94a3` | `#94a0b1` | Deleted (cleaned up) |
| `P` | `--status-proposed` | `#b8821a` | `#d4a93f` | Proposed |
| `N` / `O` | `--status-other` | `#3f7a3f` | `#5fa45f` | Not on NPL / Other |

**Program palette** (which program owns the record) — `--program-{superfund, brownfield, fuds, brac}`. Used for map markers (one dot per program — never per-status), legend rows, and the 4px top stripe of the detail panel (`--detail-stripe`, set inline by `selectSite()`).

| Program | Light | Dark |
|---|---|---|
| Superfund | `#b8332f` | `#ef5050` |
| Brownfield (ACRES) | `#1c5e9e` | `#7eb6e8` |
| FUDS | `#6f3691` | `#b47ad8` |
| BRAC | `#c46a14` | `#e6a040` |

**Readiness token** — `--readiness-ready` (`#2f7a4d` / `#6cc18a`). Distinct
from `--status-other` so "site is transactable today" (Cleanup Complete,
Active Reuse, Hyperscale-ready) reads as its own signal, not an NPL shade.
Reused across three outline pills: `.cleanup-pill`, `.reuse-pill`,
`.dc-tier-pill.ready`.

**Why two palettes, not one:** the same site (e.g. Portland Harbor) can be
both Superfund-program and NPL-Final-status; the user needs to read those
independently. Conflating them was the original v1.5 mistake — markers
colored by status mixed three reds across two programs on the legend.

### 2.3 Color — basemap

`--map-{ocean, land, state-stroke, county-stroke, marker-stroke}` plus
`--inset-{bg, stroke}` for the cartographic insets. Re-painted on theme swap
by `refreshBasemapColors()` (re-styles the GeoJSON layers; never via CSS
`filter: brightness/contrast` because that recomposites every pan/zoom frame
on mobile).

### 2.4 Typography

Three system stacks, zero web fonts. Wire policy: a Google Fonts link adds
~50KB and a render-blocking RTT we don't need.

```css
--font-sans:  -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui,
              "Helvetica Neue", Arial, sans-serif;
--font-serif: "Charter", "Source Serif 4", "Source Serif Pro",
              "Iowan Old Style", "Apple Garamond", "Palatino", "Georgia",
              "Times New Roman", serif;
--font-mono:  ui-monospace, "SF Mono", "JetBrains Mono", Menlo,
              Consolas, monospace;
```

`font-feature-settings: "ss01", "cv11", "tnum"` on `:root` turns on tabular
numerals globally. Anything numeric (KPIs, table cells, legend counts, doc
size, distances, coords, dates) reads in tabular figures.

| Role | Family | Size | Weight | Letter-spacing | Used on |
|---|---|---|---|---|---|
| H1 (brand) | serif | 20 / 17 mob | 700 | -0.01em | `.brand h1` |
| H2 (hero, detail) | serif | 24 / 18 mob | 700 | -0.015em | `.hero h2`, `.detail h2` |
| H3 (section label) | sans | 10.5 | 600 | 0.12em | `.detail h3` (uppercase) |
| Eyebrow | sans | 10 | 600 | 0.14em | `.hero-eyebrow` (uppercase) |
| KPI number | serif | 22 / 18 mob | 700 | -0.01em, tnum | `.kpi-num` |
| KPI label | sans | 9.5 | 600 | 0.1em | `.kpi-label` (uppercase) |
| Body | sans | 14 | 400 | — | `body`, `dd` |
| Caption / muted | sans | 11–13 | 400 | — | `.muted`, `.kpi-sub`, `.muted-cell` (italic) |
| Pill | sans | 9.5–10.5 | 600–700 | 0.04–0.06em | `.pill` (uppercase for outline variants only) |
| Table head | sans | 11 | 600 | 0.06em | `th` (uppercase) |
| Table cell | sans | 13 / 12 mob | 400 / 500 first col | — | `td` |

Why serif headlines: editorial signal. The product is investigative, not
SaaS — Charter is the same family the FT, Bloomberg Businessweek, and
ProPublica use for display.

### 2.5 Spacing scale

No explicit spacing token system — values are inlined as `px`. The de facto
scale is **4 / 6 / 8 / 10 / 12 / 14 / 16 / 18 / 22 / 24 / 28**. If you find
yourself typing `7px` or `13px`, round to the nearest step unless you have a
reason (e.g. `acreage-note` margin-left: 8px is fine; the KPI internal
padding `10px 12px` is fine).

Rationale for not extracting a `--space-2` ladder: there are ~30 values in
the codebase, the scale is naturally clustered, and a one-time refactor would
churn every component file for ~0 future maintenance benefit. Keep it
explicit until that math changes.

### 2.6 Radii & shadows

```
--shadow:      0 4px 18px rgba(15, 23, 42, 0.08);   /* detail panel, toast */
--shadow-soft: 0 1px 2px rgba(15, 23, 42, 0.06);    /* tab bg, leaflet bar  */
```

Border radii: **4** (chips, tax-incentive block), **6** (small inputs,
zoom buttons, focus ring), **8** (icon buttons, tabs, KPI deck, summary
card, persona buttons, toast), **14** (mobile bottom-sheet top), **999**
(pills). Dark theme uses heavier shadows
(`rgba(0,0,0,0.5)`) because contrast against `--bg #0d121a` needs more.

### 2.7 Motion

Three transition durations: **90ms** (table row hover), **120ms** (button /
input hover, color swaps), **200ms** (detail panel slide-in/out, with custom
cubic-bezier `(.2,.8,.2,1)` for ingress and `(.4,0,.2,1)` for egress). Toast
180ms ease-out. **No motion above 300ms.** No CSS animations on hot paths
(pan/zoom must stay 60fps).

`prefers-reduced-motion` is **not yet wired** — a known gap. When added, kill
the detail-panel transform transition and the toast fade.

---

## 3. Layout architecture

The page is a top-to-bottom flex column on `body` with `overflow: hidden` so
the map view can absolute-position itself to fill the remainder.

```
┌────────────────────────────────────────────────────────┐  ──┐
│  topbar    [search] [count] [filters] [csv] [☾] [tabs] │    │ chrome ~52px
├────────────────────────────────────────────────────────┤  ──┤
│  hero    H2 "Every federally-tracked..."   ┌──KPI──┐   │    │ ~140px
│          dek                               │ deck  │   │    │ (hidden <640px)
├────────────────────────────────────────────────────────┤  ──┤
│  filters  [program] [state] [npl] [acreage] [persona]  │    │ collapsed by
│                                                        │    │ default
├────────────────────────────────────────────────────────┤  ──┤
│                                                        │    │
│            map  (or table view, mutually               │    │ flex: 1
│                  exclusive — `.view.active`)           │    │
│                                                        │    │
│                                          [legend]      │    │
├────────────────────────────────────────────────────────┤  ──┤
│  footer   sources · refreshed · github                 │    │ ~32px
└────────────────────────────────────────────────────────┘  ──┘

  Aside (detail panel) — overlay:
   - Desktop: 440px right rail, 100vh, slides right→left
   - Mobile:  full width, 65vh bottom sheet, slides bottom→top
```

`<main>` uses `position: relative; flex: 1; overflow: hidden` so the map
`<div>` can `position: absolute; inset: 0`. Swapping views toggles
`.view.active` (display: block) on `#view-map` / `#view-table`.

### 3.1 Topbar

`flex` row, wraps on narrow widths. Order on desktop: brand → search →
count → filters btn → export btn → **share-link btn (⎘)** → theme btn →
map/table tabs. Search has `flex: 1 1 240px; max-width: 360px` so it grows
into available space without swallowing the toolbar. The `.search-count`
is **outside** the search input wrapper so a long count string ("23,447 of
46,778 in California · 412k ac (389k w/ acreage)") can ellipsis-truncate
without compressing the input.

The search element is now a `.search-wrap` container holding:
- `<label class="search">` with the visible input
- `<ul id="search-typeahead" role="listbox">` absolutely-positioned
  dropdown that opens when ≥2 chars are typed (capped at 8 results, ranked
  name-prefix > name-contains > city/state-contains). Arrow keys navigate,
  Enter / mousedown picks → `window.__selectSite(id)`. Escape clears.
  Lets users jump directly to a known site without the tab-switch + scroll
  hunt path.

The share-link button (`#share-link`) calls `navigator.clipboard.writeText
(window.location.href)` and fires a toast confirming the copy. URL state
already round-trips every active filter (see `syncUrl()`), so the share
button is just discoverability — it tells users the page is permalinkable.

On mobile (`<640px`): `flex-wrap: wrap` pushes controls onto a second row;
`.search { flex: 1; order: -1 }` puts the search bar on top, full width.
Search input bumps to `font-size: 16px` to suppress iOS auto-zoom.

### 3.2 Hero strip

Editorial intro band between topbar and filters. Two columns on desktop
(`minmax(0, 1.4fr) minmax(0, 1fr)`): left = eyebrow + serif H2 + dek; right
= 4-cell KPI deck. Bg is `--bg-elev` to read as elevated content rather than
chrome.

At `<1024px` (tablet): collapses to one column, KPI deck flows below copy.

At `<640px` (mobile): the entire hero copy is hidden (`.hero-copy { display: none }`) so the map gets the real estate; the KPI deck becomes a
horizontal scroll-snap carousel:

```css
.kpi-deck {
  overflow-x: auto; scroll-snap-type: x mandatory;
  grid-template-columns: repeat(N, minmax(120px, 1fr));
}
.kpi { scroll-snap-align: start; }
```

### 3.3 KPI deck

Four cells, computed from the in-memory `sites` array on every filter
change (no extra HTTP):

1. **Sites tracked** — total record count
2. **Acres tracked** — sum of `s.acreage` across records with reported area
3. **Datacenter-ready** — sites with `data_center_reuse_candidate === true`
4. **Hyperscale-ready** — sites scoring ≥hyperscale via `computeDcScore()`

Each cell:
- `kpi-label` (uppercase, 9.5px, `min-height: 2.4em` so 1-line and 2-line
  labels visually align across the row)
- `kpi-num` (serif, 22px, tnum)
- `kpi-sub` (10.5px muted; the strong variant `.kpi-sub-strong` for
  qualifying criteria like "≥50 ac · power · water")

Desktop: `kpi-sub` truncates on one line (`text-overflow: ellipsis`,
requires `display: block` — see § 8.3 ellipsis pitfall). Dynamic subtexts
(total / acreage) get `title` written by `updateKpiDeck()` via `setSub()`;
static ones (DC criteria, hyperscale criteria) have `title` in `index.html`.
Mobile: `white-space: normal` so all the criteria are readable.

**Click-to-filter shortcuts.** Two cells are interactive:
- `[data-kpi="hyperscale"]` → toggles `filterState.dcTier = "hyperscale"`
  (writes `?dc_tier=hyperscale` after debounce, lights the persona
  button's `aria-pressed`)
- `[data-kpi="dc"]` → toggles `filterState.dcCandidate`
  (writes `?dc_candidate=1`)

Both carry `role="button"`, `tabindex="0"`, keyboard activation
(Enter / Space), `.kpi-actionable` class for the cursor+hover affordance,
and `.kpi-active` when engaged. The other two cells (total / acreage)
are overview metrics, not filterable predicates — intentionally inert.
Reset clears both via `refreshKpiActiveStates()`.

### 3.4 Filters strip

Collapsed by default (`hidden` attribute on `#filters`). The gear icon-button
in the topbar carries an `aria-expanded` toggle that flips the `[hidden]`
attribute and updates the chip count.

Five filter fieldsets, all flex-wrapping:
- **Program** (checkbox fieldset, one per `PROGRAM_LEGEND` entry)
- **State** (native `<select>` with full names, territories in `<optgroup>`)
- **NPL Status** (checkbox fieldset, `populateStatusFilter()` rebuilds from
  `STATUS_LEGEND` and the live data)
- **Min acreage** (log-scale slider with `<datalist>` ticks + a
  `.acreage-ticks-labels` row showing `1 / 10 / 100 / 1k / 10k / 100k / 1M`)
- **Data-center tier** (persona buttons — one per `DC_TIERS` rung)

Plus a "Reset" `text-btn` that re-checks **every** `PROGRAM_LEGEND.program`
(never a hardcoded subset — see § 8.2). Filter chip on the gear shows the
count of active filters; uses `[hidden]` + `display: none` (see § 8.1).

### 3.5 Map

Leaflet on Canvas (no marker clustering — decimation does the job lighter).
Bottom-right corner: a flat `.legend` control. Bottom of map: cartographic
insets (rectangles + labels) for AK / HI / PR / VI / Pacific. No raster
tiles — states as filled GeoJSON polygons in the `tilePane` canvas, counties
lazy-loaded past `COUNTY_MIN_ZOOM = 7`. See [CLAUDE.md "Vector basemap"](CLAUDE.md).

### 3.6 Table

Single full-width `<table>`. Seven columns: Site, Program, State, Acreage,
Status, City, County. Paginated at 250 rows in the DOM with an
IntersectionObserver-driven auto-append (`.table-sentinel`). Sticky header
row uses `position: sticky; top: 0` with a `border-bottom: 1px solid
--border-strong` divider. Sorted column heads tint to `--accent` and gain a
`▲` / `▼` glyph via `::after { content: " " attr(data-sort-glyph) }`.

### 3.7 Detail panel (aside)

Right-side overlay, 440px wide capped at `min(440px, 92vw)`. 4px top
program-color stripe via `::before { background: var(--detail-stripe) }`
which `selectSite()` sets inline. Two-tab strip below the title:
**Overview** (everything structured) vs **Summary** (the AI narrative card).
`resetDetailTabs()` reads the session-scoped `_lastDetailTab` variable —
default `"overview"` on fresh load, otherwise restores the last tab the
user explicitly clicked. A user reading AI summaries across multiple
sites doesn't have to re-click Summary on every selection; page reload
resets the preference.

Content inside Overview, in order:
1. Title `<h2>` + location `<p class="muted">`
2. Tab strip
3. KV grid: Program (with pills), Acreage (+optional FUDS no-boundary note),
   Status, ID, Federal Facility, Region, Address, Coords, Last Updated
4. Sub-sites block (when present)
5. Owner & encumbrances KV grid
6. Federal documents block (lazy; coverage grows as `epa-superfund-docs`
   batches land)
7. FUDS details (only when `program === "fuds"`)
8. State data-center tax incentive block
9. Infrastructure proximity KV grid (universal mi distances + qualitative
   EPA RE-Powering signals + DC candidate criteria sub-line)
10. ECHO enforcement block (when present; nonzero formal actions / penalties
    get red highlight via `.violation`)
11. **Nearby sites** block (`<details>` element, up to 5 sites within 25 mi
    via Haversine on `lat_real`/`lon_real`, sorted ascending). Hidden when
    no neighbours fall within the radius. Each entry is a button → `selectSite`,
    so users evaluating adjacent parcels can pivot without map-pan + click.
12. Source profile link

Closes via the × button (top-right), Escape key, or clicking the map. Close
restores `[hidden]` + `aria-hidden="true"`.

Mobile (`<640px`): converts to a bottom sheet —
`top: auto; bottom: 0; width: 100%; height: 65vh; border-radius: 14px 14px 0 0`.
A `::after` pseudo-element draws the iOS-style drag handle. The slide
transition swaps from `translateX(110%)` to `translateY(110%)`. Bottom
padding uses `calc(20px + env(safe-area-inset-bottom))` for notched phones.

### 3.8 Footer

Slim source-citation strip on `--bg-elev` so it reads as part of the
editorial frame rather than chrome. Left: comma-separated source links
(EPA Superfund, EPA ACRES, USACE FUDS, DOD BRAC, EPA RE-Powering). Right:
last refresh date + GitHub link. Both flex with `min-width: 0;
overflow: hidden; text-overflow: ellipsis` so a long source list compresses
gracefully on narrow viewports.

---

## 4. Components

### 4.1 Buttons

| Variant | Use | Spec |
|---|---|---|
| `.icon-btn` | Topbar (filters, export, theme) | 32×32, border, surface-2 bg, rounded-8 |
| `.tab` | Map/Table, detail Overview/Summary | bg-transparent → bg-surface on `.active`, shadow-soft on active |
| `.text-btn` | "Reset" link | accent color, underlined, no bg |
| `.close` | Detail panel × | 32×32, transparent, hover bg surface-2 |
| `.persona-btn` | Data-center tier presets | bordered rounded-8, label + threshold subtext, fill on `.active` |

Hit target: every interactive control is ≥32×32px. Focus state is a 2px
accent outline with 2px offset, applied via `:focus-visible` (not `:focus`)
so mouse users don't see it.

### 4.2 Pills

Single base `.pill { padding: 1px 8px; border-radius: 999px; font-size: 10.5px; font-weight: 600 }`. Variants:

- **Status** — `data-status="F|D|P|N"` → solid bg from `--status-*`, white text
- **Program** — `data-program="superfund|..."` → solid bg from `--program-*`, white text
- **`.dc-pill`** — outline only, accent color, uppercase, "DC candidate"
- **`.dc-tier-pill`** — outline accent (edge / colo) or `.ready` outline
  green (hyperscale / mega), uppercase
- **`.cleanup-pill`**, **`.reuse-pill`** — outline green, uppercase

When stacked on a single line (in the detail panel's Program cell) they read
left-to-right as: program → cleanup → reuse → DC candidate → DC tier. Each
later pill is a stronger readiness signal so the visual ladder makes sense
left-to-right.

### 4.3 `.kv-chip`

Smaller outline chip rendered inline within a `<dd>` to surface a secondary
value (today: transmission-line voltage `230 kV` next to the distance).
Anchored to text baseline with `vertical-align: 1px`. The `.ready` variant
recolors to `--readiness-ready` when the value clears a hyperscale gate
(≥230 kV).

### 4.4 Tax incentive block

A 4-radius card with a 3px accent left-border that lives in the detail
panel between FUDS details and infrastructure proximity. Houses a clickable
`.tax-chip` (tier 1 filled green / tier 2 accent outline / tier 3 muted
outline) anchored to the source URL plus a meta line describing the
program + investment threshold + sunset / status.

### 4.5 Summary card (AI narrative)

In the detail panel's Summary pane. `--surface-2` bg with a 3px accent
**left-border** (`border-left: 3px solid var(--accent)`) — the editorial
convention for "this is generated content, not primary-source data."
Followed by an empty state when no summary on file yet, or the body
paragraphs + a meta line with the model and generation date.

### 4.6 Toast

Lazily mounted `#toast` div, centered horizontally at `bottom: 24px`.
Fades in via `.toast.visible`, auto-fades after 4s. **One toast at a time**
— don't grow into a queue. Used today for "site not found" and reserved for
future non-blocking status (e.g. ACRES hydration progress).

### 4.7 Map legend

Custom Leaflet control at `bottomright`. One row per program present in the
currently-loaded data (Superfund only on first paint; rows appear as
ACRES / FUDS / BRAC lazy-loads complete and `rerenderLegend()` re-runs).
Each row: 10px colored dot · program label · per-program count (tabular).
A `legend-foot` line clarifies "Marker size ∝ acreage (log)". The legend is
intentionally NPL-status-free; that detail belongs in the table pill /
detail panel only.

### 4.8 Inset region labels

`L.divIcon` labels (`.inset-label`) anchored to each inset box's top-left
corner. Background `--surface`, top-rounded `4 4 0 0` so they read as tabs
on top of the inset rectangle. Marked `pointer-events: none` so they don't
intercept marker clicks.

### 4.9 Detail-panel KV grid

```
<dl class="kv">                  /* grid-template-columns: 130px 1fr; */
  <dt>Acreage</dt>                /* muted, 12px */
  <dd>1,234 <span class="acreage-note">Boundary not digitized in USACE source.</span></dd>
</dl>
```

`<dd>` is `--text-soft` regular; `<dd class="muted-cell">` is `--muted`
italic for "not available" placeholders. Sub-lines (`.dd-criteria`,
`.acreage-note`) sit inside the `<dd>` as siblings — `selectSite()`
mutates only the leading text node (`firstChild.nodeValue = ...`) so the
sub-line span survives subsequent renders.

Mobile collapses the column to 110px to keep dd values readable.

---

## 5. Responsive strategy

Three breakpoints, mobile-first in intent though desktop-first in source
order (CSS-cascade convenience):

| Range | Name | Strategy |
|---|---|---|
| `≥1025px` | Desktop | Full hero with 2-col grid, KPI row of 5, filters wrap to 1 row, side-rail detail panel, all four detail accordions open by default |
| `641–1024px` | Tablet | Hero collapses to 1 col (KPI deck flows below), topbar / hero / filters tighter padding |
| `≤640px` | Mobile | Hero copy hidden, KPI deck collapses behind a disclosure with a 2-number summary chip, topbar wraps + tightens, **filters strip becomes a bottom sheet** with dim backdrop, detail panel becomes bottom sheet, **four detail sections become accordions collapsed by default**, table hides City + County columns, footer source list collapses behind a "Sources" chip |

### 5.1 Mobile UX patterns (v1.12)

The mobile pass tightened chrome from ~340px to ~580px of map real estate
on a 375×667 viewport. Five components reach for the same disclosure
primitive (`<details>` / `<summary>`) plus one bottom-sheet primitive:

- **KPI disclosure** (`#kpi-disclosure`). Summary strip on mobile shows the
  two strongest numbers ("46.8K sites · 821 DC candidates"); expanding
  reveals the full 5-cell carousel. `wireKpiDisclosure()` uses matchMedia
  to set `open` based on viewport — closed on mobile, open on desktop —
  and stops auto-toggling once the user has manually interacted in the
  session (recorded via `dataset.userToggled`).
- **Footer sources disclosure** (`.footer-sources-disclosure`). Mirror of
  the same pattern: inline list on desktop, tappable "Sources" chip on
  mobile that expands the list below the footer line.
- **Filters bottom sheet**. The `#filters` element is the same DOM on
  both layouts — desktop CSS keeps it as an inline strip; mobile CSS
  re-styles it into a slide-up sheet (`position: fixed; bottom: 0;
  border-radius: 14px 14px 0 0`). A new `#filters-backdrop` overlay dims
  the map. Reset + Done action row pinned to the bottom of the sheet via
  `position: fixed`. The sheet's header + footer + backdrop are
  `display: none` above 640px.
- **Detail-panel accordions** (`.d-section` × 4). Owner & encumbrances,
  Federal documents, Infrastructure proximity, Enforcement & compliance
  each wrap in `<details data-section="X">`. `DETAIL_SECTION_PREFS` is a
  module-level `Map` that records the user's open/close choice per
  section; `applyDetailSectionDefaults()` runs after every `selectSite()`
  to replay the user's preference, falling back to "closed on mobile,
  open on desktop." Survives jumping between sites in a session; resets
  on reload.
- **Table column hiding**. On mobile, columns 6 (City) and 7 (County)
  drop to `display: none` — values still live in the detail panel. The
  Program pill in column 2 loses its filled background and reads as a
  small uppercase label colored by program, so the cell fits in ~64px.

The `<details>` primitive is preferred over a JS-driven accordion because:
(a) it's native, keyboard-accessible, screen-reader-friendly out of the
box, and (b) toggling `open` doesn't trigger a re-render of the inner
content the way a `[hidden]` swap would. The `[hidden]` trap (§ 8.1)
still applies to `<details>` elements that we also `[hidden]`-toggle (the
docs and ECHO sections show/hide based on data availability) — verify
`.d-section[hidden] { display: none }` stays in the stylesheet.

### 5.2 Mobile patterns to follow

Why these breakpoints: 1024 is the practical iPad landscape boundary;
640 is the practical phone-portrait boundary. No need for a 4th tier —
desktop scales fine above 1280 because `.hero-inner { max-width: 1280px;
margin: 0 auto }` caps the readable width.

Container queries: **not used**. The page has a single fixed layout
hierarchy so media queries against viewport width are sufficient. If a
genuinely independent component lands (e.g. an embed widget) container
queries become the right tool.

### 5.3 Mobile patterns to follow

- **Bottom sheet, not slide-over**, for detail panels and filters. A full-height
  overlay covers the map and breaks the "tap marker → read info → keep
  panning" loop. The drag handle is decorative — there's no actual drag
  gesture yet (a Tier 2 backlog item).
- **Carousel, not stacked grid**, for the KPI deck. Stacking pushes the
  map below the fold; horizontal scroll-snap keeps it accessible without
  taking the space.
- **Hide hero copy, keep KPI deck.** The H2 + dek are nice-to-have framing
  on desktop; on a phone the user already knows what they opened.
- **Bump input font-size to 16px on iOS** to suppress the auto-zoom
  on focus.
- **Lean on CSS, never duplicate DOM trees** for mobile/desktop layouts.
  A `<section class="hero-copy">` that's `display: none` on mobile is fine;
  rendering a second mobile-only block of copy is not.

---

## 6. Cartographic system

US-only, intentionally — Canada and Mexico literally don't exist on the
map. `maxBounds: L.latLngBounds([18, -127], [51, -65])` with
`maxBoundsViscosity: 1.0` and `minZoom: 4` together prevent panning out of
the lower-48 + a strip below for the insets. `fitBounds(US_BOUNDS)` on
init.

### 6.1 Vector basemap

No raster tile provider. Two GeoJSON layers in Leaflet's `tilePane`:

- **States** — `docs/data/us-states.json` (~87KB), filled polygons via
  `L.geoJSON()` with `--map-land` fill and `--map-state-stroke` (bold).
  Non-CONUS states (AK / HI / PR) are filtered out at draw-time — their
  markers are remapped into the insets, so the real-world polygons are
  visually redundant.
- **Counties** — `docs/data/us-counties-topo.json` (~822KB TopoJSON),
  lazy-loaded the first time the user crosses `COUNTY_MIN_ZOOM = 7`,
  decoded via `topojson.feature()`, attached/detached as the user crosses
  the threshold.

`refreshBasemapColors()` re-paints both layers on theme swap by re-styling
the GeoJSON layers (never via CSS `filter` on the tile pane — that
recomposites every frame).

### 6.2 Markers

Canvas-rendered circle markers, **one dot per program**, sized by
`log(acreage)`. Decimation at low zoom keeps the visible count manageable:

| Zoom | Keep |
|---|---|
| ≤4 | 1 in 16 |
| ≤5 | 1 in 8 |
| ≤6 | 1 in 2 |
| ≥7 | all |

Hash-based stable sampling (`shouldDecimateOut(id, keepEvery)`) so the
visible subset doesn't reshuffle on zoom changes.

### 6.3 Cartographic insets

Rectangles + labels at the bottom of the map for AK / HI / PR-USVI /
GU-MP-AS-FM. `applyInsetRemap()` linearly remaps each record's lat/lon
into the box at ingest time; the original is preserved on `lat_real` /
`lon_real` so the detail panel and CSV export show real coords. Adding a
new state to an existing inset = one entry in `INSETS[].states`.

---

## 7. Accessibility

| Concern | Implementation |
|---|---|
| Skip to content | `<a class="skip-link">` is the first focusable element; visually hidden until focused, slides in at `top: 8px` |
| Landmarks | `<header role="banner">` · `<nav aria-label="Toolbar">` · `<main id="main" tabindex="-1" role="main">` · `<aside role="complementary">` · `<footer role="contentinfo">` |
| Focus indicators | `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px }` on every interactive element |
| Detail panel | `aria-hidden` synced to the `hidden` attribute by `closeDetail()` and `selectSite()` |
| Tabs | `role="tablist"` / `role="tab"` / `role="tabpanel"` / `aria-controls` / `aria-selected` on both the map-vs-table tabs and the detail Overview-vs-Summary tabs |
| Live region | `<span id="search-count" aria-live="polite">` so result counts announce |
| Filters | `<fieldset>` + `<legend>` for each grouped control (Program, NPL Status, Data-center tier) |
| Search | `placeholder="Search sites…"` short; `aria-label` / `title` carry the longer description |
| Touch | `touch-action: manipulation` on all interactive elements; Leaflet initialized with `tap: false` to avoid duplicate touch+click |
| Color contrast | All text/bg pairs ≥4.5:1 in both themes (verified via the audited tokens above) |
| Reduced motion | **Not yet wired** — known gap |

---

## 8. Common pitfalls (the "scar tissue" list)

These are encoded in the codebase already; if you're tempted to undo them,
read the rationale first.

### 8.0 Disclose uncertainty; never silently correct it (2026-08-09)

Two surfaces added after the corpus audit, both built on the same principle:
**the interface must not present a value as more certain than it is, and must
not invent a better value it cannot source.**

- **Location-confidence note** (`#d-coord-note`, under Coordinates). 118 sites
  plot more than a mile outside their own stated state, 17 sit on typed-in
  whole degrees, 3,728 share a coordinate with two or more others. Every one
  of them was drawn on the map looking exactly as authoritative as a surveyed
  parcel. The note says so in plain language — *"Source places this in CT
  (10.4 mi outside MA), not in MA."* We deliberately do **not** move or hide
  the marker: the state attribute and the geometry come from independent paths
  inside EPA ACRES / USACE FUDS, we have no better source, and a fabricated
  coordinate would be worse than a flagged one.
- **Sources & evidence** (`#d-evidence-block`). One row per claim the record
  carries: publisher, dataset, layer, how the value was derived, the as-of
  date of *that* file, and a link resolving to this site at the source.
  Derived values (`coord_flags`, `summary`) are labelled "This project
  (derived)" with the connector path, so computed fields never read as agency
  data.

Two implementation constraints worth keeping:

1. **Both reuse the sibling-span pattern** (`d-acreage-note`) rather than
   adding `<dt>/<dd>` pairs — `selectSite()` rewrites only the leading text
   node so the span survives. ~1 node each against a 5,000-node first-paint
   budget; the evidence table itself (~150 nodes) is built lazily on first
   expand and torn down on site change.
2. **Evidence must be sized to the claim.** A verification box smaller than
   the distance it evidences returns nothing and reads as a refutation — see
   `radiusFor()`. A negative claim ("not in an Opportunity Zone") is correctly
   evidenced by an empty result and must say so via `expectsFeatures`.

### 8.1 The `[hidden]` trap

`display: inline-flex | block | flex` on an element that also uses the
`hidden` attribute will silently override the implicit `display: none`,
and the element renders despite `hidden` being set. Bit us three times
(detail panel, filter chip, acreage note).

**Always** ship a `[hidden] { display: none }` rule alongside any
`display: ...` override. Examples in code: `.chip-count[hidden]`,
`.acreage-note[hidden]`, `.dd-criteria[hidden]`, `.dpane[hidden]`,
`.summary-meta[hidden]`, `#d-echo-block[hidden]`, `.filters[hidden]`.

The detail panel takes a different path — it sets `visibility: hidden`
plus `transform: translateX(110%)` on `[hidden]` instead of `display: none`
so the slide-out animation can play.

### 8.2 Anything that enumerates programs MUST iterate `PROGRAM_LEGEND`

The Reset button, `populateStatusFilter()`, `applyUrlSelection()`'s
pending-promise wait, the persona-button generator — all of them must
iterate from `PROGRAM_LEGEND` (or `DC_TIERS` for the persona case) rather
than hardcoding `["superfund", "brownfield"]`. When v1.7 added FUDS and
BRAC, four call sites silently dropped them. Same pattern applies to
`DC_TIERS` for any future readiness rung.

### 8.3 `text-overflow: ellipsis` needs a non-inline display

`overflow: hidden` and `text-overflow: ellipsis` silently no-op on
`display: inline`. The `.kpi-sub` `<span>` defaulted to inline and the
truncated text bled across the column boundary into the next KPI cell
(UAT-006). Always set `display: block | inline-block | flex | grid` on the
element you're ellipsizing.

### 8.4 No CSS `filter` on hot paths

Specifically: no `backdrop-filter: blur()` on the map legend or any
map-overlay element. No `filter: brightness/contrast` on `.leaflet-tile-pane`
to retheme. Both recomposite every pan/zoom frame and tank mobile perf.
The vector basemap + CSS-var `refreshBasemapColors()` pattern is the
intentional answer.

### 8.5 No web fonts

The system serif stack (`Charter`, `Source Serif 4`, …) is intentional.
Adding a Google Fonts link costs a render-blocking RTT + ~50KB for a small
typographic upgrade that the system stack already approximates. If
typography ever lands on a brand refresh, audit Charter availability on
target browsers before introducing a fetch.

### 8.6 No `display: ...` override on a `<dd>` you also style as `muted-cell`

If you add `display: block` (or anything) to a `<dd>` with an inline note
or criteria sub-line inside it, make sure the sub-line element still
respects `[hidden]` (§ 8.1). The `dd-criteria` / `acreage-note` /
`d-dc-criteria` spans all rely on this.

### 8.7 Pills do NOT fall back to PROGRAM in the STATUS column

`makeRow()`'s STATUS cell renders the NPL pill for Superfund, the
eligibility text for FUDS, and an em-dash `<span class="muted-cell">—</span>`
for ACRES / BRAC. Never fall back to `data-program` here — that's how
v1.11.1 shipped with every FUDS / BRAC / ACRES row showing an identical
pill in the PROGRAM and STATUS columns (UAT-009). Regression-locked by
`test_table_status_column_no_program_duplication`.

### 8.8 IntersectionObserver callbacks need a scroll-position guard

`isIntersecting === true` is necessary but not sufficient for "user
scrolled near the bottom." During the Map→Table tab swap (and in headless
contexts where layout settles over multiple paint passes), the observer
can fire several times before the sentinel's position stabilizes — each
firing calls `appendNextPage()` and prefetches another 250 rows.
2026-05-11 UAT found the table rendering 2,000 rows (8×) on a clean
default sort, ballooning DOM to ~18,907 nodes. The fix in
`setupTableInfiniteScroll()` adds an explicit
`wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight > 400` check
that bails when the user hasn't actually scrolled near the bottom.
Regression-locked by `test_table_intersection_observer_does_not_overfire`
+ `test_intersection_observer_appends_when_user_scrolls` (the latter
guards that the guard doesn't block real user-driven pagination).

### 8.9 Anything that enumerates KPI cells must whitelist actionable ones

`wireKpiClicks()` iterates the KPI deck but only wires cells where
`data-kpi ∈ {hyperscale, dc}`. Adding a new KPI without updating the
`ACTIONABLE` map will leave it visually-similar but inert. When a future
filterable KPI ships (e.g. "Tier-1 incentive states only"), drop its
`data-kpi` slug into the map and `toggleKpiFilter()` switch, then add a
matching entry to `filterState` and `refreshKpiActiveStates()`. Same
drift-safe pattern as `PROGRAM_LEGEND` / `DC_TIERS` (§ 8.2).

---

## 9. Editorial voice

The dashboard reads like investigative reporting, not SaaS. Rules of thumb:

- **Cite primary sources.** Every data point traces to a federal source.
  The footer lists them. The detail panel's "Source profile" link goes to
  the canonical EPA / USACE / DOD page.
- **Surface "why".** Boolean badges like "DC candidate" carry their
  qualifying criteria inline as italic `.dd-criteria` sub-lines
  ("≥50 acres · electric transmission · water service area"). The KPI
  subtext does the same.
- **Title-case CAPS source data on the way in.** EPA / USACE ship cities,
  counties, addresses, and site names in ALL CAPS or with placeholder
  sentinels (`-- Not Defined --`, `_NULL_`). `prettyPlace()` and
  `prettyName()` run in `ingestSites()` so the rendered values are
  presentable; raw source preserved on `*_raw` for debugging. The acronym
  whitelist (`NAME_KEEP_UPPER`) is load-bearing — when a new dataset adds
  acronyms it doesn't recognize, add them there.
- **"Adjacent", not "0.0 mi".** The `infra-proximity` connector rounds
  distances to 0.1 mi; any value under 0.05 lands as 0.0, which is "passes
  through / borders the boundary," not missing. `fmt.miles()` renders
  `n < 0.05` as `"Adjacent"`. The same threshold is hardcoded in the
  static-summary builder. If a third surface needs to render distance,
  align with this threshold.
- **"Not available", not blank.** Optional fields render `Not available`
  in italic muted (`.muted-cell`) — never an empty `<dd>`. Out-of-CONUS
  records that the infra connector intentionally doesn't cover render
  `"Remote — outside continental US"` instead.
- **No emojis.** Outline pills do the badge work. The page is a federal
  data product; emojis would read as flippant.
- **Lower-case for prose, upper-case for labels.** Eyebrows, KPI labels,
  table heads, and outline-pill text are uppercase with 0.04–0.14em
  letter-spacing. Section headings (`detail h3`) too. Everything else is
  sentence case.
- **AI content is visibly distinguished.** The Summary card has a 3px
  accent left-border and a meta line crediting the model — the editorial
  convention for marking generated content.

---

## 10. Performance constraints on design

Design decisions that look like aesthetic choices but are actually perf
choices:

| Choice | Reason |
|---|---|
| System fonts only | One render-blocking RTT + ~50KB saved |
| No backdrop-blur | Recomposites on every pan/zoom frame |
| No `filter:` on tile pane | Same |
| CSS-var theme + JS re-paint | Theme swap doesn't trigger a full re-style cascade |
| Canvas markers, not SVG | 47k SVG nodes melt mobile |
| Marker decimation 1/16 at zoom 4 | 60fps pan at country zoom |
| Paginated table (250 rows) | DOM stays ~2.7k nodes vs 265k pre-pagination |
| Lazy-load non-Superfund programs | First paint stays at ~170KB gz |
| Lazy-load counties past zoom 7 | 822KB TopoJSON doesn't block first paint |
| `contain: layout paint` on table-wrap + detail | Bounds invalidation cost when rows append / panel re-renders |
| `priority: "low"` on enrichment fetches | Browsers deprioritize behind first-paint resources |
| `<link rel="preload">` for sites.json + us-states.json | Race the JSON behind defer-loaded JS |
| Single in-flight promise per program lazy-load | De-dup parallel toggles |

If a design proposal trades any of these for visual polish, it needs to
either (a) prove the proposal works on a mid-range Android phone over a
throttled connection, or (b) get explicit sign-off that perf cost is
acceptable.

---

## 11. What's intentionally NOT in the design

Decisions made by *omission*:

- **No marker clustering.** Decimation + canvas rendering handles 47k
  markers; `leaflet.markercluster` would add weight for marginal UX gain.
- **No tile provider.** Vector basemap is lighter, fully theme-able, and
  intentionally US-only.
- **No multi-toast queue.** If a queued-toast pattern becomes necessary,
  swap in a real library.
- **No drag-to-resize on the bottom sheet.** Two heights (peek 65vh /
  max 75vh) cover the use case. A drag gesture is Tier 2 backlog.
- **No backend.** Everything ships static. Saved searches, alerts, and
  a public API are backlog items pending a backend.
- **No infinite zoom.** `maxBounds` + `minZoom: 4` keep the user in US-only
  territory. No Antarctica, no off-globe.
- **No "site portfolio / watchlist" yet.** localStorage-based portfolio is
  backlog. The design system has reserved real estate for it (a third tab
  alongside Map / Table) when it ships.
- **No date-range slider.** Listing dates exist on records but the use
  case ("show me sites listed since 2010") hasn't surfaced in user
  feedback. The filter strip is intentionally short.

---

## 12. Pointers

- **Tokens, components, media queries:** [docs/style.css](docs/style.css)
- **Rendering, ingestion, filter logic:** [docs/app.js](docs/app.js)
- **Markup skeleton:** [docs/index.html](docs/index.html)
- **Data pipeline & connector design:** [CLAUDE.md](CLAUDE.md)
- **Open bugs & UAT regressions:** [issues.md](issues.md)
- **Backlog (feature + UX ideas):** [backlog.md](backlog.md)
- **Test coverage:** [tests/e2e/test_smoke.py](tests/e2e/test_smoke.py)
  (50 Playwright tests guard every regression listed in § 8)
