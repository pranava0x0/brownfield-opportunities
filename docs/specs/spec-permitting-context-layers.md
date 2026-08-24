# Spec 12: Permitting-Context Layers — Coal Screens (shipped), Air-Quality Gate, and the Precedent Surface

**Status:** Coal permitting screens shipped 2026-08-24; air-quality gate blocked on free EPA AQS credentials; precedent surface proposed
**Priority:** High (Impact: 4/5, Size: 3/5, Completeness: 4/5)
**Target Version:** v1.15.x–v1.16
**Lead Component:** `scripts/build_coal_nepa.py`, `docs/data/coal-nepa.json`, `docs/app.js` (`_coalNepaSectionHtml`), future `epa_aqs` integration

---

## 1. Executive Summary & Value Proposition

Speed-to-power is the #1 siting screen (LBNL: 55-month median queue), and
the slowest gates after interconnection are environmental review and air
permitting. The platform's siting surfaces carried grid/water/rail/finance
signals but zero permitting context. This spec closes that gap surface by
surface, starting where deals are hottest: the 18-plant coal repowering
catalog.

## 2. Shipped (2026-08-24): coal permitting screens

`build_coal_nepa.py` runs each cataloged plant through seven nepa-mcp
sources (IPaC, tribal, NRHP, PAD-US point, USACE district, NFHL zones,
NEPAssist) → `coal-nepa.json` (18/18 plants, 126/126 queries ok). The Coal
drawer renders a "Permitting screen" chip row — drawer-lazy, retryable, and
its loader deliberately does NOT call `recordRefreshDate` (a file whose
loader may never run must not drive the displayed date).

The screens genuinely differentiate: Cheswick carries 11 NRHP listed
properties and 253 mapped flood zones within 2 miles (urban Allegheny
valley); Bull Run shows 15 listed species; Craig shows zero mapped flood
zones. Deliberate scope cuts: NOAA/EFH lenses excluded (catalog is
interior/eastern — add per-site when a Pacific plant enters), GBIF excluded
(occurrence counts are noise in a permitting summary).

**Not a score input.** Screening counts must never feed
`_regulatoryPenalty`-style terms — a count is context for a human, and a
riverine coal plant near mapped flood zones is EXPECTED (they were sited on
water intake). The limitation text ships in the artifact.

## 3. Air-quality / NAAQS nonattainment gate (next, credential-blocked)

**Why it matters:** behind-the-meter gas turbines and multi-hundred-MW
diesel backup fleets are the coal-conversion and DC bridge-power play — and
NAAQS nonattainment/maintenance status determines whether NSR/PSD
permitting for them is a season or a multi-year fight. This constrains the
DC lens's `gas_pipeline_mi` value and the whole generation lens, invisibly
today.

**Design (two tiers):**
- **Tier A (curated, via nepa-mcp `epa_aqs`)** once `EPA_AQS_EMAIL` +
  `EPA_AQS_API_KEY` exist (free): `analyze_air_quality_baseline` per coal
  plant + Hanford parcel → drawer chip "Air quality: attainment /
  nonattainment (pollutant)". ~30 sites, cached.
- **Tier B (corpus-wide, direct EPA Green Book)** — EPA publishes NAAQS
  nonattainment AREAS as a small national polygon set; a
  `connectors/nonattainment.py` on `PolygonIndex` (same shape as
  opportunity-zone) stamps `nonattainment_pollutants: [str]` on all 46,759
  sites. This is a REAL bulk layer, unlike per-ROI screens. Scoring: a
  display flag first; any score term needs its own spec revision with the
  weight-sum rule.

## 4. The precedent surface (`eis_boundaries`)

The Hanford map packages already collect EPA's EIS-boundary layer — "what
environmental reviews already happened here" is the most reusable NEPA
signal there is (a neighboring completed EIS means data, baselines, and an
agency record to tier from; NEPATEC text search is Spec 01's deep half).
Roadmap: per-coal-plant `eis_boundaries` pull (18 point queries) → drawer
line "N EIS boundaries within 5 mi" linking the map package; then the same
for the nuclear-civilian 29 via Spec 10's R2 generic CLI.

## 5. State-regime column for the coal catalog

The catalog spans 13 states; siting regimes differ more than geology:
certificate-of-need states, EFSEC-style one-stop siting councils (WA/OR/NY),
county-permit states (TX). A curated `siting_regime` + `siting_regime_url`
per catalog row (18 rows, annual re-audit with the STATE_DC_* rhythm) tells
a developer which door the repowering application enters. Follows the
provenance contract; validated like every curated column.

## 6. Verification

- Shipped: `test_coal_drawer_renders_nepa_permitting_screen` (chips, lazy
  load, re-entry guard, real Cheswick NRHP count); builder covered by the
  Spec 10 engine tests.
- Air-quality tier B gets the standard connector suite + a
  `nonattainment` provenance row before any UI ships.
- Every new chip carries its limitation string in the artifact, not just
  the UI — non-browser consumers (llms.txt readers) must see the caveat.
