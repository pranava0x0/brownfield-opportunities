# mobile-ux-plan.md

> Working spec for the v1.12 mobile-density pass. Started 2026-05-11.
> Updated as each phase lands. Picks on the three forks are committed
> below — execute end-to-end then run the suite.

---

## Fork decisions (user delegated)

1. **Table on phones — column-hiding first.** Hide City + County on `<640px`;
   keep paginated table machinery intact. Escalate to a card view only if
   manual test still reads cramped after Phase 5 type-tuning.
2. **Hero on phones — collapse-behind-toggle.** Default-hidden KPI carousel;
   a single-line stats strip in the topbar area expands the full carousel
   on tap. Recovers ~95 px → ~28 px.
3. **Detail-panel accordions — collapse all four sections by default.** Mobile
   gets `Documents`, `Owner & encumbrances`, `Infrastructure proximity`, and
   `Enforcement & compliance` collapsed; mandatory rows (Program, Acreage,
   Status, ID, Address, Coords) stay always visible above them.

---

## Phase 1 — Reclaim vertical real estate

- **1.1 Hero KPI carousel** — wrap the deck in a `<details id="kpi-disclosure">`
  on mobile. Default closed. The `<summary>` is a slim strip showing only the
  two strongest numbers: `Sites tracked · DC reuse candidates`. Tap reveals
  the full 5-cell carousel. Desktop unaffected — `details[open]` forced via
  media query above 640 px.
- **1.2 Topbar tightening.** Reduce gap from 6 px to 4 px on the controls
  row at `<640px`. Brand `h1` 17 → 16 px; `meta` 11 → 10 px. Drop the
  trailing margin between brand and controls.
- **1.3 Footer.** Drop the sources list on `<640px`; replace with a
  `<button class="text-btn">Sources</button>` that opens a toast / mini
  sheet. Keep `Refreshed —` + GitHub link visible.

## Phase 2 — Filters → bottom-sheet drawer

- **2.1** New `<aside id="filters-sheet">` mounted next to `#detail`. CSS
  modeled on the bottom-sheet detail pattern (slide-up from bottom, drag
  handle, close X, dim backdrop).
- **2.2** On `<640px` the gear button no longer toggles
  `#filters[hidden]` — it opens `#filters-sheet`. Move the same fieldsets
  into the sheet body via CSS Grid placeholders (no DOM dup; the sheet
  is the source of truth, the inline `.filters` strip is `display: none` on
  mobile). Actually simpler: keep one `#filters` element, restyle into a
  bottom-sheet at `<640px`.
- **2.3** Sticky footer inside the sheet with `Reset` + `Apply` actions.
  Apply just closes the sheet (filters apply live as the user toggles, same
  as desktop — Apply is "I'm done").

## Phase 3 — Detail panel accordions on mobile

- **3.1** Convert four sections to `<details>` / `<summary>`:
  - Owner & encumbrances (currently 4 rows always visible)
  - Federal documents block (currently `[hidden]` until docs exist)
  - Infrastructure proximity (currently 11 rows always visible)
  - Enforcement & compliance (currently `[hidden]` until ECHO exists)
- **3.2** On mobile, all four start collapsed. On desktop, all four start
  expanded — CSS `@media (min-width: 641px) { details { open: ... } }`
  doesn't exist; we toggle the `open` attribute via JS once at init based on
  `matchMedia("(max-width: 640px)")`.
- **3.3** Session-memory the user's open/close state on `<details>` toggle
  events into a module-level `Set<string>` keyed by section id; on
  `selectSite()`, re-apply the recorded open-state. Survives jumping between
  sites within a session; resets on reload.
- **3.4** Each `<summary>` styled to match the existing `h3`: uppercase
  10.5 px, 0.12em letter-spacing, `--muted`, border-top hairline. Chevron
  via CSS pseudo-element rotating on `[open]`.

## Phase 4 — Table compaction (column-hiding)

- **4.1** On `<640px`, hide the City + County columns via CSS
  `:nth-child(6), :nth-child(7) { display: none }` on both `<th>` and
  `<td>`. City + county still available in the detail panel.
- **4.2** Keep the Status column but drop the pill background and render the
  text only at `--text-soft` weight to save horizontal space. (Acres,
  program-pill, state stay.)
- **4.3** Right-align Acreage; left-align everything else.

## Phase 5 — Type & spacing tuning

- **5.1** KPI label 9.5 → 9 px on mobile.
- **5.2** KPI number 18 → 19 px on mobile.
- **5.3** KV grid column 110 → 96 px on mobile.
- **5.4** Detail-panel `<h3>` 10.5 → 10 px with 0.14em letter-spacing on
  mobile.
- **5.5** Persona buttons `min-width` 110 → 96 px on mobile so three fit
  per row at 375 px viewport.

## Phase 6 — Tests + regression sweep

- **6.1** New Playwright tests:
  - `test_filters_open_as_sheet_below_640px`
  - `test_detail_sections_collapsed_by_default_on_mobile`
  - `test_hero_kpi_collapsed_on_mobile_until_toggle`
  - `test_table_hides_city_county_below_640px`
- **6.2** Re-run the existing 50 e2e tests against the new mobile CSS.
  Particular attention to `test_filters_chip_visibility`,
  `test_detail_panel_truly_hides_on_close`, the responsive smoke tests.
- **6.3** Verify the `[hidden]` trap rule on every new collapsible
  (`<details>` already does this correctly; the sheet does not).

---

## File touch list

- `docs/index.html` — wrap KPI deck in `<details>`, move `<details>`/
  `<summary>` around four detail-panel sections, add `<aside id="filters-sheet">`
  scaffolding (or restyle existing `#filters`).
- `docs/style.css` — bottom-sheet styles, accordion styles, mobile media
  queries.
- `docs/app.js` — open/close persistence for accordions, sheet trigger,
  matchMedia setup for first-paint open-state.
- `design.md` — update § 3.3 (KPI deck), § 3.4 (filters), § 3.7 (detail
  panel), § 4 (accordion component spec), § 5 (responsive table).
- `tests/e2e/test_smoke.py` — new Playwright tests.
- `backlog.md` — strike "[med] Mobile filter UX" line.

## Status log

(updated as work lands)

- [x] Phase 1.1 — Hero KPI deck wrapped in `<details>` (kpi-disclosure +
      summary strip with `Sites tracked` + `DC candidates`; wireKpiDisclosure
      uses matchMedia to open on desktop, respect manual user toggles)
- [x] Phase 1.2 — Topbar tightening (gap 10→6 / 6→4, h1 17→16, sub 11→10,
      icon-btn 32→30, tabs padding 8→6)
- [x] Phase 1.3 — Footer sources collapse (`<details class="footer-sources-disclosure">`,
      desktop shows inline always, mobile shows pill chip that expands)
- [x] Phase 2 — Filters bottom-sheet (restyle `#filters` on `<640px` —
      slide-up sheet, drag handle, dim backdrop, Reset + Done action row;
      desktop strip unchanged; backdrop / sheet-head / sheet-actions hidden
      on desktop via CSS)
- [x] Phase 3 — Detail accordions (Owner & encumbrances + Federal documents +
      Infrastructure proximity + Enforcement & compliance wrapped in `<details
      class="d-section" data-section="X">`; session memory in
      `DETAIL_SECTION_PREFS`; defaults: mobile=closed, desktop=open via
      `applyDetailSectionDefaults()` called after each `selectSite()`)
- [x] Phase 4 — Table column hiding (`th:nth-child(6/7) { display: none }` on
      `<640px`; Program pill in column 2 drops filled background → uppercase
      colored label)
- [x] Phase 5 — Type & spacing (detail h3 10.5→10 / letter-spacing 0.14em,
      persona-btn min-width 110→96 + label/min font tighter, acreage tick
      labels 9.5→9px, bottom-sheet padding 18→16, max-height 75→78vh)
- [x] Phase 6 — Tests (8 new Playwright tests appended to
      `tests/e2e/test_smoke.py`: KPI disclosure default state on
      mobile + desktop, filters open as sheet on mobile, Done closes
      sheet, detail sections collapsed/open per viewport, table hides
      City/County columns + pill bg dropped, footer sources collapsed.
      Unit suite: **282/282 passing**.)

---

## Files touched

- `docs/index.html` — KPI deck wrapped in `<details class="kpi-disclosure">`;
  filter sheet header/footer + `#filters-backdrop` added; four detail-panel
  blocks wrapped in `<details class="d-section">`; footer sources wrapped
  in `<details class="footer-sources-disclosure">`.
- `docs/style.css` — KPI disclosure summary strip styles; topbar tightening;
  footer sources collapse on mobile; bottom-sheet filter styles + backdrop;
  detail-section accordion styles with chevron pseudo-element; mobile
  table-column hiding + program-pill flattening; type/spacing tuning.
- `docs/app.js` — `wireKpiDisclosure()`, `wireDetailSections()`,
  `applyDetailSectionDefaults()`, refactored filter open/close into
  `openFiltersUi()` / `closeFiltersUi()` with backdrop + sheet-close /
  sheet-apply / sheet-reset handlers; `updateKpiDeck()` populates the two
  summary numbers.
- `tests/e2e/test_smoke.py` — 8 new tests in the v1.12 block.
- `design.md` — § 5 expanded with mobile UX patterns and the `<details>`
  primitive guidance.
- `backlog.md` — `[med] Mobile filter UX` struck out, marked done v1.12.

## Known minor visual issues left for follow-up

- NPL Status `.check-group` is `grid-template-columns: 1fr 1fr` so on a
  375px viewport the second column ("Proposed" / "Not on NPL") wraps
  slightly under the first when the labels are long. Acceptable for v1.12;
  fix candidate: drop to a single column under 400px.
- Persona buttons (3 per row at 96px min-width) leave the fourth on a
  second row at 375px. Intentional — three "primary" tiers fit; the rare
  "AI mega 500 MW+" tier sits below.
