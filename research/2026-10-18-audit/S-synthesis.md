# Synthesis: simple screens, six tabs, fewer clicks (2026-10-18)

Hole ids: F Explore, G Nuclear/Micro, H Coal/Retired/DOE, I Maritime/Nickel (report letter + rank).
Rank: criteria met (desc), unknowns (asc), one tie-breaker; shown as "4 of 5 met" with ✓ ✗ ?. Acreage flagged by `check_acreage_artifacts.py` (90 sites) = ?. Land = `acreage` else `parcel_acreage`; null = ?. `in_sfha` null or not_assessed = ?.

## 1. Screens

Shared criteria (defined once, reused):

| id | Label | Rule (field) | Source | Tag |
|---|---|---|---|---|
| GRID | Line ≥115 kV ≤5 mi | `transmission_kv`≥115 and `transmission_mi`≤5 (same asset; no substation borrowing) | HIFLD Electric Power Transmission Lines | P |
| GRID10 | Line ≤10 mi | `transmission_mi`≤10 | EPA RE-Powering screening criteria, 2021 (epa.gov/re-powering/5-data-documentation-mapping-and-screening-criteria-renewable-energy-generation) | R |
| ROAD | Road ≤10 mi | `highway_mi`≤10 | same EPA page | R (solar), P elsewhere |
| FLOOD | Outside flood zone | `in_sfha`=false | FEMA NFHL, fema.gov/flood-zones | R |
| WATER | Gage ≤10 mi | `water_gage_mi`≤10; `water_flow_cfs` shown, "annual mean, not 7Q10" | USGS NWIS | P |
| RAIL | Rail ≤1 mi | `rail_mi`≤1 | Census TIGER Railroads | P |
| PORT | Port ≤10 mi | `port_mi`≤10, measured to port polygon edge | BTS NTAD Principal Ports (USACE) | P (definition R) |
| POP | No city ≥25,000 within 10 mi | Census places | 10 CFR 100.3, 100.21 (law.cornell.edu/cfr/text/10/100.21) | P |

POP is the one new data source: Census Vintage 2024 city/town estimates (census.gov/data/tables/time-series/demo/popest/2020s-total-cities-and-towns.html) joined to the 2024 Gazetteer places file (coordinates; already used for nickel anchors). Decisive: population is the first NRC siting screen and the dashboard has none (G4). The real test needs the LPZ, so it stays P.

| Screen | Criteria | Tie-break | Sites all met (of 46,759) | Closes | UI method statement |
|---|---|---|---|---|---|
| Data center | GRID; LAND ≥100 ac (P; AF lease offers ran 193-3,000 ac, SAM.gov AFCEC-26-R-0002); FLOOD; ROAD | nearest line | 1,237 | F1-4, F6, F8 | "No federal data-center site standard exists. Four checks on public layers; unknown never passes." |
| Power generation (solar) | LAND ≥35 ac (R); GRID10; ROAD; FLOOD. All R | acreage | 1,800 | F1-3, F7, F8 | "EPA RE-Powering utility-solar thresholds: 35 ac, line and road within 10 mi, plus FEMA flood." |
| Manufacturing | None. No federal threshold exists; rail ≤8 mi passes 36,899 sites. Remove the lens | n/a | n/a | F1 | n/a |
| Large PWR (AP1000/APR1400) | POP; SEISMIC `usgs_pgam`≤0.30 g (AP1000 certified design, 10 CFR 52 App. D); WATER mean flow ≥100× consumptive 31.1 cfs (APR1400 39.0, derived) at gage ≤25 mi (P; Vogtle EIS-0476 demand); GRID at ≥230 kV; LAND ≥500 ac (P; offered acres where leased) | nearest line | per list | G1, G2, G4, G5 | "Population, earthquake, water, grid and land checks. Design-envelope screen, not an NRC site finding." |
| SMR (AP300) | POP; SEISMIC (0.30 g, conservative); WATER ≥100× 9.2 cfs (derived); GRID ≥115 kV; LAND ≥100 ac | nearest line | per list | G1, G4, G5 | Same, SMR demand and land |
| Microreactor | SELECTED (`janus_site` or program roster, R: army.mil, 2026-08-26); FLOOD; LAND ≥5 ac (P; Westinghouse 5 MWe on 2 ac); GRID `transmission_mi`≤5 (P, Army "grid maturity") | nearest line | 5 selected of 9 | G3, G7 | "Army's published criteria, checked where data exists. Selection is the Army's, not ours." |
| Coal-plant reuse (EIA-860M, all 281 coal plants ≥100 MW with a retirement record: 239 retired, 42 planned) | RETIRED (Retired sheet, R); POI FREE (no operating unit at Plant ID; 150 of 239 pass; P); ≥230 kV ≤2 mi at EIA lat/lon (P); FLOOD (NFHL query at plant point) | MW desc | per list | H1-5 | "EIA-860M status, free interconnection point, grid and flood. No dollar values." |
| Retired industrial (GHGRP) | STOPPED REPORTING since ≤2021 (R, EPA GHGRP; last year in data 2023); CLOSURE RECORD (EIA retired plant ≤1 mi; else ?); GRID; BROWNFIELD RECORD ≤1 mi (`tracked_site_mi`) | last year, older first | per list | H6, H7 | "Stopped GHGRP reporting is not confirmed closure. Closure needs a second record." |
| Port-adjacent (replaces Maritime) | PORT; LAND ≥100 ac; GRID; FLOOD | port edge distance | 160 | I1, I5, I6, I9 | "Principal port within 10 mi plus land, grid, flood. Channel depth not assessed." |
| Nickel refinery | LAND ≥300 ac (P; Westwin 480, Long Harbour 371); RAIL; GRID; WATER; FEED: PORT or `nickel_feedstock_mi`≤100 | acreage | 37 (port-only feed) | I1-4, I8 | "Five checks from analogs Westwin and Long Harbour. Land is mostly unknown; water is mean flow." |

Counts use the merged corpus and the artifact rule. 37,461 of 46,759 sites (80%) have unknown land, so most rows read "3 of 4 met, 1 unknown"; group headers show this instead of 23,630 flat rows.

Dropped: floating-nuclear and coastal-generation lenses (NUREG-0502 is a 1978 manufacturing review); stranded-asset dollars; queue fast-track; inverted-grid microreactor lens (G3); INL civilian tiers (COL status becomes a column).

## 2. Tab architecture

| Tab | Decision |
|---|---|
| Explore | Keep, rename **Screens**. Selector: Data center, Solar, Nickel, Port-adjacent, Retired industrial. Default = Data center, ranked |
| Map | Keep |
| Table | Drop (5,391 words, no controls). Export CSV from Screens |
| Retired Sites | Merge into Screens |
| Coal Reinvestment | Keep as **Coal plants** (universe is EIA plants) |
| Nuclear Siting | Merge into **Nuclear** (class selector: Large PWR, SMR, Microreactor) |
| Microreactors | Merge into Nuclear; fleet/commitments table becomes a collapsed "Deployment catalog" |
| DOE Sites | Keep. Fix the vocabulary (below) |
| Maritime Siting | Drop. Port screen moves into Screens; ports and yards stay as Map layers |
| Nickel Refining | Merge into Screens |
| Data & methods | Keep; auto-lists every method card |

**Target tabs (6): Screens, Map, Coal plants, Nuclear, DOE Sites, Data & methods.** Each ranked view: selector, method card (rules with ✓✗?, R/P tags, source links), ranked list, detail. The phone tab strip drops from 11 tabs to 6.

Build order: (1) `scripts/build_screens.py` evaluates criteria offline with `Corpus.merged` fill-if-empty semantics and writes `docs/data/screens.json` (id, name, state, program, per-criterion code); a test recomputes it. (2) Screens tab and method cards. (3) EIA coal builder. (4) Census POP join. (5) Merge nuclear. (6) Delete.

## 3. Interaction cuts

| Task | Before | After |
|---|---|---|
| Data-center shortlist | 4+ clicks, still 18,946 alphabetical rows | 0 (default screen, ranked); switch screen 1 |
| Generation / factory | 4+, lens buttons inert | 1 (solar); factory: honest "no screen" |
| First base for AP1000 | 2 + 4 screens, water Unknown everywhere | 1 (open Nuclear); ranked, 1 screen |
| Best coal plant | 1 + 1-2 screens, sorted by MW | 1; ranked by readiness |
| DOE parcel for SMR | 2 | 2 (unchanged) |
| Facts on one site | 3 + 1-4 screens | 3 + 1; five Unknown cards become one line; drop the repeated Infrastructure block |
| How is it ranked | 1 + 2 screens, nothing per use | 0; method card is the first element |
| Data freshness | partial | 0; header shows "Data 2026-09-25 · Research 2026-10-18" |
| Page load | 25 requests, 68.9 MB decoded before ready | `screens.json` first; infra, water, ACRES load on detail open |

One disclaimer line under the method card replaces caveats on 8 surfaces. Mobile: method card collapses to one line; first row above 600 px (Coal 912, DOE 1,246 now).

## 4. Data corrections now (verified findings only)

Code/pipeline:
1. `connectors/spatial.py` `PolygonIndex.add_polygon`: only `rings[0]` is an exterior; split by signed area. Rebuild NRI, IRA, OZ, tribal, climate, ISO. NRI missing for 24.8% of Superfund (DE 25/25).
2. `docs/siting-context.js` `REACTOR_CLASSES.micro.water_basis`: "has not paired reactor designs with installations" → "Army paired 5 vendors with 5 installations on 2026-08-26; cooling is vendor-specific". worldnuclearnews: us-army-selects-five-microreactor-vendors-to-power-bases.
3. Same file, `ap1000.water_basis`: "as-built record" → "2008 FEIS design-basis projection for proposed units"; mark `apr1400`, `ap300` numbers `estimated: true`. EIS-0476 PDF.
4. `census-workforce` connector: fail loud without `CENSUS_API_KEY` or unregister.
5. Flood: treat 4,183 `not_assessed` rows as ?. Record real fetch dates in `source_metadata`.

Rows:
6. `ap1000-sites.json` arnold-afb-tn: `af_rflp_site` true → false; note "no proposals received, notice 2026-06-01". arnold.af.mil Article 4505271.
7. `nuclear-civilian-sites.json` kemmerer-wy: `col_status` "nrc_construction_license_accepted" → "construction permit issued 2026-03-04". WNN: nrc-issues-construction-permit-for-first-natrium-plant.
8. Same, clinch-river-tn: "ESP approved, recommending CP" → "construction permit issued ~2026-09-29". WNN: first-construction-permit-issued-for-bwrx300-smr-in-us.
9. Same, palisades-mi: add NRC approval of the one-time amendment (Oct 2026). michiganpublic.org 2026-10-14.
10. `microreactor-fleet.json` equinix-radiant: "20-reactor purchase agreement", status Signed → "preorder agreement (2025-08-14), 20 Kaleidos units". investor.equinix.com release 1079.
11. Same, deployable-unity-inl: criticality "2026-07-01" → "June/1 July 2026 (sources differ)". energy.gov/articles/us-department-energy-meets-president-trumps-goal-delivers-third-advanced-reactor.
12. Janus: mark the five selected (Drum, Benning, Bragg, Campbell, Hood) and the four not selected.
13. `coal-conversions.json` Naughton: `planned_retirement`, `queue_transfer_eligible` true → gas conversion 2026, false. EIA-860M Aug 2026 lists NG units operating at Plant 4162.
14. Same, Homer City `nameplate_coal_mw` 1,884 → 2,012. EIA-860M Retired sheet, Plant 3122, sum 2,012 MW (retired 2023/2024). Also reference-campuses "2,000 MW".
15. Same, Conesville (reference-campuses "2,005 MW") → 2,174.8 MW. EIA-860M Plant 2840.
16. Same, Craig: single year 2028 → per unit 2026, 2028, 2029 (EIA Plant 6021); Unit 1 note "through 2026-09-26" has lapsed; planned-retirements.json says 2029. Belews Creek 2036 conflicts with its own 2040 note.
17. `reference-campuses.json` Widows Creek: "operational" → "announced"; the cited Google post is a build announcement.
18. `srs-e2e.json` srs-ai-lease-area: remove "10 tracts / 3,103 ac" and coalition names, or add a second source.
19. `paducah-e2e.json`: replace citation with the July 2026 DOE announcement; state 1.8 GW basis; acreage 600 (Brookfield spokesperson) vs ~785 (DOE release): use DOE's.
20. `portsmouth-e2e.json`: microreactor `anchored` → `strong` (Oklo option 2024-02-01 only); reconcile 8 GW lease vs 10 GW campus.
21. `wipp-e2e.json` wipp-lwa-balance: drop "as of Aug 2026"; date to Sept 2024.
22. `federal-clean-energy.json`: rename `available_acreage` → `reservation_acreage`; add award sources for SRS and Paducah.
23. `retired-industrial.json`: drop 125 Mining rows (Hecla Greens Creek operates); reword "former large-load facility" to "stopped reporting".
24. `shipyards.json`: flag Norfolk, Puget Sound, Portsmouth as `public_naval`; replace the generic MARAD citation with per-row sources.
25. CLAUDE.md claims to remove: "13/14 water ratings validated" (data says unknown); EIA `/archive/xls/` as the working path (live check: `/xls/` works, archive 503).
26. Acreage artifacts (Tar Creek 310,173 ac vs 25,600 per Oklahoma DEQ) become ? via the 90 flagged ids.

Needs verification before editing:
- Naughton/Montour POI (GEM only); Clinch River permit date; Palisades amendment date.
- AP1000 0.30 g certified PGA; Vogtle 1%-of-flow precedent; 26.8 MGD withdrawal (not in the EIS text).
- Air Force RFLP awards (Davis-Monthan, Edwards, Robins, JBMDL); SRS binding constraint (secondary source only).
- Cumberland (EIA 2028 and 2034; TVA reversed Feb 2026); Campbell and Craig 202(c) orders: add as status notes.
- Port Nickel "for sale 2026-07-19" (no readable source); GM Detroit-Hamtramck operating (secondary); Gulf Island Houma operator; Bollinger and Conrad additions.
- Hide until re-sourced: ISO/RTO (token-walled), Montana parcels (endpoint returns HTML), climate-zone (third-party host), NRI (until item 1).
- USGS legacy water API retires ~Feb 2027: migrate `build_streamgages_overlay.py` before Nov 2026. 7Q10 replacing mean flow is new data, not built.

## 5. Delete

- Unloaded code: `docs/dc-score.js`, `ap1000-score.js` (redeclares `REACTOR_CLASSES`), `microreactor-score.js`, `maritime-score.js`, `nickel-score.js`.
- `assessSite` `lens` argument, `?lens=` and the lens buttons; "High" confidence filter (no path returns it); the six always-Unknown categories (fiber, grid_capacity, water_reliability, water_rights, demand, regulatory).
- `min_acres: 20` duplicate of `MICRO_MIN_ACRES`; "Missing grid evidence" filter (not gated on `_infraChecked`).
- Stranded-value dollars, `conversion_suitability`, `coal_conversion_queue_fasttrack`, the unused decay term, the "Stranded Value" header.
- Substation as grid access (44% distribution class).
- Orphan cache `data/cache/f5fc6a369570d33f.bin`; `scripts/finish-data-refresh.sh`.
- Copy: caveats repeated on 8 surfaces; INL civilian tier legend; EO 14318 "federal fast lane" attribution (F7).
