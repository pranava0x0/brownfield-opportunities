# Plan: Unified rankings table + PWR-generalized nuclear siting (2026-07-02)

Two evaluations requested: (1) how to combine the **Table** and **DC
Candidates** tabs, adding a **manufacturing** ranking; (2) whether the
**AP1000** tab's evaluation can be improved for **PWRs generally**, with a
deeper treatment of **water** (availability, rights).

---

## Part 1 — Combining Table + DC Candidates (+ Manufacturing ranking)

### Current state

Both tabs already source the same set — `tableState.filtered` (v1.21 made the
candidates view obey the global filter model). What differs is presentation:

| | Table tab | DC Candidates tab |
|---|---|---|
| Sort | any column, user-chosen | score desc, fixed |
| Columns | name/program/state/status/acreage/… | rank/score/tier/kV/substation/plant/gas/signals |
| Row renderer | `makeRow()` | `makeCandidateRow()` |
| Pagination | 250-row IntersectionObserver | `CANDIDATES_PAGE` IntersectionObserver |
| View-local state | sort key/dir | lens (`?lens=gen`) |

So the two tabs are one table engine implemented twice, differing only in
column set and default sort. The backlog already anticipated this ("merge the
candidates view into the Table as a 'Power signals' column preset").

### Options

**A. Full merge — one "Table" tab with view presets.** A preset switcher
(Browse · Rank: Data Center · Rank: Generation · Rank: Manufacturing) drives
a config-driven column list; rank presets pin sort to score desc and add
rank/score/signals columns. One row renderer, one observer, one sentinel.
- Pros: single surface; filters visibly global; adding a lens = adding a
  preset row in a config array (drift-safe iteration, the UAT-007 lesson);
  kills ~200 lines of duplicated table machinery.
- Cons: the biggest frontend refactor since v1.6 pagination — sort semantics,
  URL state (`?view=`), `ensureRowRendered`, e2e coverage (~15 tests touch
  the two tabs). Real regression surface.

**B. Shared engine, keep both tabs.** Factor `makeRow`/`makeCandidateRow`
into one column-config renderer but leave the tab split. Engineering-only
win; users still see two tables whose relationship is unclear.

**C. Rename DC Candidates → "Rankings", add lenses there.** Add a
Manufacturing lens button next to Data Center / Generation; Table stays the
raw-browse surface.
- Pros: smallest change (a button + a lens function + URL value
  `?lens=mfg`); tab name stops implying DC-only; the Browse/Rank distinction
  (user-sorted vs score-sorted) is arguably worth keeping as two tabs.
- Cons: table-machinery duplication remains.

### Recommendation

**C now, A as the destination.** Do the cheap rename + third lens immediately
(it unblocks the manufacturing ranking), and schedule the full merge (A) as
its own PR once the manufacturing lens has settled — merging while also
adding a lens couples a UX refactor to a scoring launch. B is strictly
dominated (all of A's work discipline, none of its UX payoff).

### Manufacturing lens v0 (no new data needed)

`computeManufacturingScore` in dc-score.js, same contract (0–100, gate on
`transmission_mi != null`, weights sum to 100). Per
`manufacturing-reuse-opportunities.md`, manufacturing inverts two DC
assumptions — **rail becomes primary** and **mid-size acreage is the sweet
spot** (a peaked curve, not monotonic):

| Component | Wt | Curve intent |
|---|---|---|
| rail | 22 | ≤0.5 mi full · 5 mi ~half · 20 mi → 0 (spur economics) |
| acreage | 18 | peaked: rises to plateau ~100–500 ac, decays slowly past 2,000 (mega-sites aren't a mfg fit) |
| transmission | 16 | DC curve relaxed — 50–300 MW loads tolerate 69–138 kV |
| substation | 12 | as DC lens |
| gas | 12 | process heat (steel, chemicals, e-fuels) |
| highway | 10 | inbound/outbound trucking |
| readiness/incentives | 10 | SWRAU + OZ + 48C energy-community allocation priority (45X is location-neutral; no “stack”) |
| **Total** | **100** | flood/climate/regulatory stay subtractive, per the existing pattern |

When the **Census LEHD/LODES workforce layer** (already top of backlog)
lands, take 20 points (rail −4, acreage −4, transmission −4, gas −2,
highway −2, readiness −4) and give them to a workforce component — noted now
so the v0→v1 rebalance is pre-agreed and the weight-table test just changes
one row.

---

## Part 2 — AP1000 tab → PWR-general siting; deeper water treatment

### What holds up today

The Vogtle-anchored demand figures (per-unit 26.8 MGD withdrawal / 20.1 MGD
consumptive), per-site USGS gauge validation, threshold-not-ranked acreage,
and unscored geohazard flags are all sound and citation-grade. The
improvements below generalize the *frame*, they don't redo that work.

### 2a. Parameterize the reactor class

The score hardcodes one design. The screen differs by class mainly through
**thermal rejection** (water demand scales ~linearly with MWth net of
efficiency) and **land/export needs**:

| Class | MWe | Consumptive (≈ scaled from Vogtle) | Min developable acres | Export voltage need |
|---|---|---|---|---|
| AP1000 | 1,117 | ~31 cfs / unit | 500 | ≥345 kV ideal |
| Large PWR ×2 units | 2,234 | ~62 cfs | 800 | 500 kV |
| AP300-class SMR | 330 | ~9 cfs | ~100 | 138–230 kV fine |
| Microreactor (Janus) | 1–20 | ≪1 cfs (often air-cooled) | <20 | distribution-level |

> **Source-audit correction (2026-07-05):** the Army Janus announcement is
> vendor-neutral and does not specify output, cooling technology, or water
> demand. The implementation therefore leaves those fields unassessed and
> holds water constant so it cannot affect relative site rank.

Concretely: a `REACTOR_CLASSES` table in `ap1000-score.js` (renamed
`nuclear-score.js`), each entry `{mwe, consumptive_cfs, min_acres,
volt_anchor_shift}`; the water and voltage curves read the class instead of
constants. UI: a class selector in the tab header (like the candidates lens
buttons). The interesting output: Davis-Monthan and Edwards, `severe` water
for an AP1000, re-enter the viable set for an air-coolable SMR — which is
exactly what the Army's Janus program (9 of our 14 sites) is proposing.
Rename the tab "Nuclear Siting" when this lands.

### 2b. Water availability — from 5-bucket rating to computed margin

Replace the analyst `water_adequacy` bucket as the *primary* signal with a
computed **water margin**: `reliable low flow ÷ class consumptive demand`.

- **Numerator:** per-site `water_low_flow_cfs` — the **7Q10** (lowest 7-day
  average flow with 10-year recurrence) or drought-of-record flow at the
  supply gauge, NOT the annual mean currently quoted in `water_note`. The
  2012 Ocmulgee drought (854 cfs vs ~2,800 mean) that demoted Robins is the
  argument: means overstate reliability ~3×. USGS publishes the daily series
  needed to compute 7Q10 via the same curl-able RDB endpoints already logged
  in `data-source-research.md` §16–17 — scriptable, no agents needed.
- **Tiers (proposed):** margin ≥30× → 1.0; ≥10× → 0.8; ≥3× → 0.5; ≥1× →
  0.2; <1× → 0. Anchor sanity check: NRC accepted Vogtle at ~1% of *average*
  Savannah discharge (~2 % of 7Q10) — a ≥30× 7Q10 margin is comfortably
  inside precedent.
- Keep `water_adequacy` as the analyst override/fallback (reservoir-supplied
  sites like Arnold's Woods Reservoir are storage-buffered and score better
  than their inflow gauge implies), and keep every figure cited in
  `ap1000-water-validation.md`.

### 2c. Water RIGHTS — the legally-obtainable dimension (new)

Availability ≠ obtainability. A structured per-site rights assessment:

- **`water_rights_regime`** (state-level): **riparian / regulated-riparian**
  (eastern states — permit from the state, generally obtainable if flow
  supports it), **prior appropriation** (western states — "first in time,
  first in right"; in a **fully-appropriated basin** a new ~22,400
  acre-ft/yr consumptive right is effectively unobtainable at any price
  short of buying senior agricultural rights), **hybrid** (CA, TX).
  Sources: [FJC overview](https://www.fjc.gov/content/376802/water-and-law-sidebar-books-overview-surface-water-use-rights-united-states),
  [National Ag Law Center](https://nationalaglawcenter.org/overview/water-law/).
- **`water_rights_note`** (site-level): the specific gatekeeper — TVA §26a
  approval for the five TVA-reservoir sites; ACF-compact allocation exposure
  for Georgia sites; California SWRCB permit queue for Edwards; Arizona's
  fully-appropriated Tucson AMA for Davis-Monthan (groundwater-managed —
  new large consumptive surface right essentially unavailable).
- **Scoring:** a *multiplier* on the water component (1.0 obtainable / 0.6
  contested-or-compact / 0.2 fully-appropriated), not a separate weight —
  rights without water and water without rights are both worthless, so the
  interaction is multiplicative, matching how the current Fort Campbell
  "marginal" rating already folds in reach.
- This is an analyst-curated table (like `STATE_DC_INCENTIVES`) with per-row
  citations and a `verified_at` — annual re-audit, since western basins are
  actively re-adjudicating.

### 2d. Cooling-technology flag (not scored)

`dry_cooling_viable` per class: hybrid/dry cooling cuts consumptive use
~80–95 % at a few % capacity penalty ([WNA cooling overview](https://world-nuclear.org/information-library/current-and-future-generation/cooling-power-plants),
[Stanford dry-cooling review](http://large.stanford.edu/courses/2018/ph241/duboc2/)).
For the AP1000 the natural-draft tower is part of the certified design
record, so treat dry cooling as a flag ("SMR-with-dry-cooling could bypass
the water screen here"), consistent with the seismic/flood flags-not-scores
decision.

### 2e. Two cheap PWR-general additions

- **Population proximity flag:** NRC 10 CFR 100.21 requires a low-population
  zone and population-center distance. Census county centroids we already
  ship can flag "population center <10 mi" as an unscored siting flag.
- **ISO/RTO already landed (PR #15)** — when the class selector arrives, the
  generation lens's `iso_rto` logic can be shared instead of re-derived.

### Sequencing

1. **Rankings rename + manufacturing lens v0** (Part 1C) — small PR.
2. **Water rights table + rights multiplier + 7Q10 backfill** (2b + 2c) —
   one curation pass over 14 sites; USGS fetch is scriptable.
3. **Reactor-class parameterization + tab rename** (2a + 2d + 2e).
4. **Full Table/Rankings merge** (Part 1A) — last, on its own.

---

## Sources

- [FJC — Overview of surface water use rights](https://www.fjc.gov/content/376802/water-and-law-sidebar-books-overview-surface-water-use-rights-united-states)
- [National Agricultural Law Center — Water law overview](https://nationalaglawcenter.org/overview/water-law/)
- [OSU — Comparing water rights frameworks (AR/OK/TX/NM/GA/AL/FL)](https://extension.okstate.edu/fact-sheets/whose-water-is-it-anyway)
- [California SWRCB — Water rights process](https://www.waterboards.ca.gov/waterrights/board_info/water_rights_process.html)
- [NRC — Environmental review process](https://www.nrc.gov/reactors/new-reactors/how-we-regulate/regs-guides-comm/erp) · [NUREG-1555 ESRP](https://www.nrc.gov/reading-rm/doc-collections/nuregs/staff/sr1555/toc/ch10/index.html)
- [World Nuclear Association — Cooling power plants](https://world-nuclear.org/information-library/current-and-future-generation/cooling-power-plants)
- [Stanford — Dry cooling as an alternative for nuclear plants](http://large.stanford.edu/courses/2018/ph241/duboc2/)
- [UCS — "Got Water?" nuclear water-use brief](https://www.ucs.org/sites/default/files/2019-10/20071204-ucs-brief-got-water.pdf)
- [Westinghouse AP300](https://westinghousenuclear.com/new-plants/ap300-smr/) · [AP1000](https://westinghousenuclear.com/new-plants/ap1000-pwr/overview/)
- Existing project records: `ap1000-water-validation.md` (Vogtle demand figures), `data-source-research.md` §16–17 (USGS RDB endpoints)
