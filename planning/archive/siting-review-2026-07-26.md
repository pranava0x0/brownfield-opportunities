# Comprehensive siting review — nuclear reactors, data centers, both
**2026-07-25/26 session** · branch `jam/reactor-datacenter-siting-d9b716`

A full review of what the dashboard offers each siting job-to-be-done, how that holds up
against July-2026 market reality (4 research passes), what this session changed, and what
remains. Companion docs: [jtbd-ux-plan.md](jtbd-ux-plan.md) (UX spec),
[data-source-research.md](data-source-research.md) §19-30 (new probes).

---

## 1. What the tool covers per job, and how 2026 evidence rates it

### Job A — "Site a data center"
**Coverage:** DC lens (0-100; transmission 16 / voltage 14 / substation 12 / grid-inheritance 8 /
acreage 20 / gas 10 / logistics 6 / readiness 14, minus flood/climate/regulatory penalties),
DC capacity tiers (edge→mega), Rankings tab, EPA RE-Powering DC-candidate flag, EO 14318
fast-lane badge, state incentive + regulation tables, OZ/IRA financial signals, retired +
planned-retirement plant joins.
**2026 verdict (JLL/CBRE/Area Development, LBNL):** the tool's emphasis is *directionally
right and newly validated* — speed-to-power is now the #1 screen (median interconnection
queue 55 months; ~13% of queued capacity ever completes; transformer lead 160+ weeks), and
grid-inheritance (retired/retiring-plant interconnects) is precisely the queue-skip the
market is paying for. Gaps: (a) water is now the #2 constraint and the DC/Gen lenses carry
no water-availability signal (only flood/drought-rating penalties) — WRI Aqueduct remains
the top scoring-input backlog item; (b) community/moratorium risk moves monthly ($130B in
projects blocked/delayed in Q1 2026 alone) — our regulation table needs the faster audit
cadence it got this session; (c) campus scale: gigawatt campuses are the new hyperscale
normal — tier thresholds should be revisited against 2026 sizing (backlogged).

### Job B — "Site power generation / a reactor"
**Coverage:** Generation lens (acreage-dominant, grid-export, ISO/RTO, grid-reuse of retired
interconnects); Nuclear Siting tab: 14 military installations scored (water 40 / transmission
22 / substation 16 / workforce 15 / fiber 7, acreage as threshold, water-rights multiplier,
USGS seismic flags); reactor classes (AP1000/APR1400/AP300/micro); retired-industrial (658)
+ planned-retirements (90 plants / 75.6 GW) overlays; **NEW this session: the 68-site
civilian nuclear pipeline rendered as map overlay + tab section** (was data-only since
2026-06-30).
**2026 verdict:** DOE's coal-to-nuclear methodology (394 coal sites screened; 80%
SMR-suitable; 33 large-reactor candidates; 15-35% construction savings from reused
grid/cooling/civil infrastructure) validates exactly the water/land/transmission trio the
tool scores. The federal-sites landscape moved fast and the tab was stale — fixed this
session (see §3). Remaining gap: workforce is analyst-curated, not quantitative (LEHD/LODES
enrichment stays the top nuclear-lens backlog item); 7Q10 low-flow backfill still open.

### Job C — "Both" (compute + generation co-siting)
**Coverage:** nuclear-adjacency credit in the DC lens (AWS/Susquehanna pattern), grid-reuse
MAX(retired, planned-retirement) pathways, reference-campuses overlay (10 real deals),
behind-the-meter gas signal (pipeline distance), IRA energy-community bonus (the +10pp ITC
lever behind Conesville/Homer City), civilian-nuclear popup now cross-links nearby tracked
brownfields (455 proximity matches).
**2026 verdict:** co-siting is no longer a niche — ~30% of planned US DC capacity intends
behind-the-meter generation (56 GW), projected 38% onsite-primary by 2030. The JTBD strip
routes this as a first-class job (DC ↔ Generation lenses one click apart). The Savannah
River selection (1 GW DC + 2 GW generation) is the template deal now visible in the
Nuclear Siting tab copy.

### Job D — "Research a specific site" (unchanged, healthy)
Map/table/search/detail panel with suitability at top, documents, enforcement, owner
provenance, AI summaries. No changes needed this session beyond data freshness.

## 2. Data coverage after this session's backfills

| Layer | Before | After | Notes |
|---|---|---|---|
| FEMA flood zone | 52.6% (24,614) | **72.5% (33,887)** committed; final tranche targeting ~100% of reachable sites ran overnight | in_sfha count 2,170 → 3,176; the remaining ~10k were fetched by the budget-10100 run (commit checkpointed separately) |
| Parcel owner states | 7 (NC/MT/WI/NJ/VT/CT/MA — exhausted) | **11** (+FL, CO, IA, MN — verified live 2026-07-26) | ~4.7k new candidate sites; FL needed a new fixed sq-ft→acres multiplier; IA owner-only (2017 vintage, labeled); MN opt-in counties, non-commercial-use term noted |
| Parcel dead ends (documented, don't re-probe) | NY, PA, CA | +MI, IL, MO, KS, AZ (no statewide), OH + IN (no owner field), TX (token-walled — host migrated to feature.geographic.texas.gov) | data-source-research.md §19-30 |
| Civilian nuclear pipeline | 67 sites (2026-06-30, never rendered) | **68 sites, refreshed 2026-07-26, rendered** (map ⚛ overlay + tab section) | +Belews Creek ESP; V.C. Summer/TMI/Palisades/Clinch River statuses updated |

Structural dead-ends unchanged (ACRES acreage 100%, FUDS acreage 66%, off-grid AK infra).

## 3. Research integration (4 Sonnet agents, 2026-07-26)

**Nuclear/federal programs** → dashboard edits: AFCEC-26-R-0002 award still pending (Jan-2026
target passed); program expanded to Alaska (AFCEC-26-R-0006: JBER, Eielson, Clear SFS,
~4,700 ac); ANPI (AF/Space Force) already paired vendors to 3 bases (Radiant→Buckley,
eVinci→Malmstrom, Antares→JBSA); DOE selected Amentum for Savannah River (1 GW DC + ~2 GW
gen, Jul 2026); V.C. Summer FID by 2028-03-31; TVA Clinch River first-ever advanced-reactor
CP recommendation (hearing 2026-08-13); Duke Belews Creek ESP accepted 2026-02-08; Army
Janus vendor awards still pending ("this summer"); EO 14299-14302 define the Army/DOE
non-NRC authorization pathways. Army's separate conventional-DC leases: Fort Bliss
(Carlyle) + Dugway (CyrusOne).

**State DC regulation (quarterly re-audit)** → table edits (applied in app.js):
NY **added restrictive** (EO 62, 2026-07-14 — first statewide permit pause, 50 MW+, up to
1 yr); VA **downgraded restrictive→cautionary** (moratorium died; what passed is a noise/
siting-assessment + generator standard); OK **removed** (its law is a cost-causation tariff
— the excluded category; moratorium SB1488 died; left as a watch comment); VT + FL
**confirmed cautionary** with refreshed citations. Excluded-by-design (protective tariffs,
not siting blockers): TX SB6, OR POWER Act, OK HB2992, VA cost-allocation bills, OH AEP
tariff (under OMA legal challenge — recheck next quarter). **Incentives:** AZ (3-yr) and
IL (2-yr) both PAUSED new applications effective 2026-07-01 → new `paused` status in
STATE_DC_INCENTIVES.

**JTBD/market criteria** → drove the UX: speed-to-power #1; JTBD quick-start strip; grid-
inheritance framed as queue-skip; DOE C2N citations added to Retired Sites; PJM (new Cycle
process, 1-2 yr target) + ERCOT (Batch Zero, Jun 2026) reform nuance noted; rail reframed
as a prerequisite gate for manufacturing. Deferred to backlog: WRI Aqueduct water stress
(re-raised to top), DC_TIERS gigawatt-era recalibration, OZ+IRA combined headline filter.

**Parcel probes** → §2 above.

## 4. What shipped this session (see git log for the precise commits)

1. Flood backfill tranches: 52.6% → 59.4% → 72.5% → (final tranche overnight).
2. Parcel registry +4 states, `acreage_multiplier` mechanism, 2 new unit tests, FL/CO/IA/MN
   backfill run, research-doc probe log §19-30.
3. Civilian nuclear pipeline data refreshed (68 sites) + rendered: ⚛ map overlay, legend row,
   popups with nearby-brownfield cross-links, Nuclear Siting tab civilian section.
4. JTBD quick-start strip (Data center / Power generation / Nuclear reactor / Factory) —
   one-click routing to the right view+lens, dismissible.
5. Regulation + incentive tables re-audited to July 2026 (NY/VA/OK; AZ/IL paused).
6. Copy: queue-skip framing, DOE C2N numbers, AFCEC/ANPI/SRS status, mfg rail-gate phrasing.

## 5. Open items (converted to backlog entries)

- **[high]** WRI Aqueduct water-stress penalty for DC/Gen lenses (water = #2 constraint).
- **[high]** Workforce enrichment (LEHD/LODES) — the missing quantitative layer for mfg + nuclear.
- **[med]** DC_TIERS recalibration for the gigawatt-campus era.
- **[med]** OZ + IRA combined "deal economics" filter (JTBD #5 from research).
- **[med]** DOE federal AI-DC sites (SRS/INL/ORNL/Paducah) as a small curated overlay; ANPI
  bases as scored Nuclear Siting rows (needs infra joins + analyst fields).
- **[med]** PJM/ERCOT queue-reform context chip on rankings rows in those territories.
- **[low]** Track AFCEC-26-R-0002 award; Janus vendor awards ("this summer" 2026); Clinch
  River CP hearing outcome (2026-08-13); Palisades restart date; quarterly regulation re-audit
  due ~2026-10.
