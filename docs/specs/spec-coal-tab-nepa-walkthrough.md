# Spec 13b: Coal Reinvestment Tab — NEPA Walkthrough & Citations Upgrade

**Status:** Ready. Supersedes/absorbs the backlog item "Coal Reinvestment permitting screen — needs more detail (2026-08-24)".
**Lead components:** `scripts/build_coal_nepa.py`, `docs/data/coal-nepa.json`, `docs/app.js` (coal drawer), `docs/data/coal-conversions.json`.

## Target users

- **The repowering developer** (IPP or infra-fund deal lead) deciding
  whether a retired/retiring plant earns a site visit. Cares about POI
  transfer, gas supply, water rights, and what kills deals late:
  wetlands, historic districts, EJ litigation exposure.
- **The energy domain expert / consultant** writing the phase-0 fatal-flaw
  memo. Wants the screen's evidence exportable and traceable to the
  querying tool, buffer, and retrieval date.
- **The state/local economic developer** pitching the site. Wants the
  honest constraint list before the developer finds it themselves.

## Jobs to be done (ranked)

1. "Is the interconnection real and transferable, and by when?" —
   answered today by the catalog row (status, MW, queue_transfer flags).
2. "What will the environmental review actually hinge on HERE?" — today:
   seven bare chips ("IPaC 15", "Flood 253") with no reading guide. **The
   gap this spec closes.**
3. "Which permits, from whom, in what order?" — today: nothing per-plant.
   Hanford-style pathway table, state-specific.
4. "What did comparable conversions face?" — the `eis_boundaries` map
   layer shows WHERE prior EIS-level reviews happened near the plant;
   deeper precedent needs NEPATEC (spec 13c).
5. "Can I hand this to my board?" — per-plant printable dossier view.

## What ships

### Data (`build_coal_nepa.py` v2)
- **Upgrade 7 → 8 sources** (add `gbif` presence-context; keep the
  Pacific-marine pair out — every catalog plant is East/interior).
- **Map packages per plant** (the 14 Map Composer layers, incl.
  `eis_boundaries`): `docs/data/coal-nepa-maps/<plant-slug>.geojson`,
  drawer-lazy like the tabular screen; "Show N features on map" button in
  the drawer using `_screeningFitBounds` (ROI-fit rule).
- **`permitting_pathways` per plant-STATE**: a shared federal set (NEPA
  trigger only if a federal handle exists — most private repowering has
  NONE, and saying so is the headline; CWA 404, ESA §7 when federal
  nexus) + one state row per catalog state (PA DEP, TX TCEQ/PUCT, OH
  OPSB ≥50 MW, WV DEP, MT DEQ + MFSA, …). Curated once per STATE (11
  states), joined per plant — not 18 hand-written tables.
- **Finding-interpretation strings** per source (`reading` field): one
  plain-English sentence turning a count into a meaning ("253 mapped
  flood zones within 2 mi is EXPECTED for a riverine plant — it was
  sited on its intake; the question is which zones touch the laydown
  and switchyard areas, not whether zones exist").

### UI (coal drawer restructure, DOE-grammar)
Drawer section order becomes: valuation/profile (unchanged) →
**"Permitting picture"** (NEW: the pathway table + a one-line federal-
nexus verdict: "No federal handle identified — NEPA likely does not
attach; state review governs" vs "Federal nexus: <X> — NEPA screening
below applies") → **Environmental screen** (existing chips upgraded to
the three-column table used by DOE Sites: Source / Finding+reading /
Retrieved, each source name linking its tool) → map button → nearby
corpus records → citations row. Limitations move to the tab-bottom
methodology block (today they sit inside the drawer).

## UI/UX ease

- Click depth: plant row → drawer = 1 click (unchanged); every NEW
  element lives inside the drawer the user already opened. Zero new
  tabs/toggles.
- The federal-nexus verdict is the drawer's first permitting sentence —
  the single highest-value fact for a developer (no federal handle = no
  NEPA = state-clock only).
- Disclaimers: the "screening, not siting" strip moves to the tab bottom
  with the methodology; the drawer keeps ONE inline qualifier on the
  screen table header ("buffer context, not the plant parcel").

## Readability / simple English

- Never render a bare count without its `reading` sentence.
- "Permitting picture", "What the review will hinge on" — no "source
  matrix" or "normalizer" language anywhere user-facing.
- Every `reading` sentence is curated + cited (it's an editorial claim);
  AI-drafted readings carry the same `narrative_note` disclosure pattern
  as DOE Sites, rendered once at the tab bottom.

## Contracts / guards

- `coal-nepa.json` stays drawer-lazy and OUT of the refresh-date list.
- New pathway rows: per-row `source_url` + `verified_at`; register the
  file in `CURATED_PROVENANCE_FILES` (it is NOT there today — only
  coal-conversions is); pr_gate citation liveness gains the pathway and
  reading URLs.
- e2e: drawer shows pathway table for a PA plant and a TX plant (state
  divergence); nexus verdict renders both ways; map button fits ROI;
  8-row screen table; limitations at bottom.
- Builder: same merge-existing evidence-preservation semantics as the
  DOE builders (the PR #22 class); never concurrent with other builders.

## Sizing

Builder v2 ~1 day (sources + maps are engine calls; the state pathway
research is the real work — 11 states × ~3 rows, all citable from state
siting-board pages). UI ~half day. The map packages add ~18 × ~1-2 MB
lazy files — acceptable, same class as the DOE geojson dirs.
