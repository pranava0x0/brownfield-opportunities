# Adversarial review: Explore tab and its lenses

Method: ran the real `docs/evidence-categories.js` under node on the merged corpus (46,759 sites). Scripts in `scratchpad/audit/`.

## (a) Holes, ranked by severity

1. **The lenses change nothing.** `assessSite(input, lens = "dc", today)` (evidence-categories.js:34) never reads `lens`. `dc` and `gen` outputs are identical for all sampled sites (0 of 233 every-200th, plus spot checks of `mfg`). The buttons (index.html:223-225) and `?lens=` only relabel. The per-use scoring was in the removed dc-score.js.

2. **No shortlist is reachable.** Sort is alphabetical (app.js:7069, stats line 7072). Headers are not sortable (index.html:241-243). Filters act on one category at a time. Grid = evidence + Medium confidence returns 18,946 sites (40%), in alphabetical order. Grid Medium AND land Medium (1,890 sites) cannot be expressed in the UI.

3. **Most columns are unknown.** Full corpus, `dc` lens:
   - Land Unknown 89.6% (41,882). ACRES (36,003) has no acreage field.
   - Fiber Unknown 100%. Fiber evidence exists on 0 records.
   - Six of 12 categories are hard-coded Unknown for every site (fiber, grid_capacity, water_reliability, water_rights, demand, regulatory).
   - Hazards Unknown 90.5%.
   - Only 4,535 sites (9.7%) have grid, land and logistics all known.
   - "High" confidence (index.html:233) matches nothing; no code path returns High.

4. **Medium on boundary artifacts.** Land is Medium whenever acreage and a profile URL exist (4,850 sites). Confirmed:
   - FUDS-F10OR0208 NORTHWEST MANEUVER AREA: 8,049,525 ac, Medium.
   - FUDS-F10AK0027 PORT HEIDEN: 1,035,875 ac, Medium.
   - OKD980629844 TAR CREEK: 310,173 ac, Medium. CLAUDE.md records Oklahoma DEQ's figure as 25,600 ac.
   - WI0001954841 FOX RIVER: 1,129,744 ac, Medium.
   Here Medium means "a source published a number", not "usable land".

5. **Hazards ignore most of their data.** Only `in_sfha === true` yields a finding (4,422 sites). The 38,150 `in_sfha === false` sites show Unknown. FEMA NRI fields (76% populated) are never read. The flood layer's metadata is `legacy_coordinate_unverified` (infra-proximity.json, `source_metadata.flood_zone`), so even the one finding rests on unverified values.

6. **Proximity read as grid.** "Mapped line · 1.4 mi · 138 kV" states distance and voltage, not capacity. Substation Medium confidence rests on OSM geometry its own metadata calls "bounding-box center; not a surveyed connection point." 20,393 sites have a substation closer than the nearest line.

7. **Thresholds unsourced; one attribution wrong.** dc-score.js's acreage curve, voltage classes (138/230/500 kV) and ≥500 MW grid-inheritance gate have no citations. dc-score.js:457-461 credits a "federal fast lane" (superfund/brownfield ≥100 ac, grid ≤2 mi, outside SFHA) to EO 14318. The EO summaries I found describe a >100 MW AI-load test, not acres or miles. Primary text unverified.

8. **Largest population cannot pass a land test.** ACRES (77% of corpus) has no acreage, so any land screen silently drops it. No lens reports the drop.

## (b) Government criteria

| Use | Criterion | Threshold | Source | URL |
|---|---|---|---|---|
| Solar, utility | Acreage; capacity | ≥35 ac; ≥5 MW | EPA RE-Powering screening, Aug 2021 | https://www.epa.gov/re-powering/5-data-documentation-mapping-and-screening-criteria-renewable-energy-generation |
| Solar, utility | Transmission; graded roads | ≤10 mi; ≤10 mi | same | same |
| Wind, utility | Acreage; transmission; roads | ≥1,200 ac; ≤5 mi; ≤10 mi (5.5 m/s at 80 m) | same | same |
| Biopower | Acreage; transmission; road; rail | ≥6 ac; ≤10 mi; ≤3 mi; ≤8 mi | same | same |
| Solar land use | PV land per MWac, direct / total | 7.3 / 8.9 ac (2012 plants) | NREL/TP-6A20-56290, secondary summary | https://www.ourenergypolicy.org/resources/land-use-requirements-for-solar-power-plants-in-the-united-states/ |
| Data centers | Qualifying AI load | >100 MW new load | EO 14318 (23 Jul 2025), WH fact sheet | https://www.whitehouse.gov/fact-sheets/2025/07/fact-sheet-president-donald-j-trump-accelerates-federal-permitting-of-data-center-infrastructure/ |
| Data centers | National load | 176 TWh (2023, 4.4%); 325–580 TWh by 2028 | LBNL 2024 DC Energy Usage Report | https://energyanalysis.lbl.gov/publications/2024-lbnl-data-center-energy-usage-report |
| Federal-land DCs | 16 sites, 4 finalized Jul 2025 | No numeric criteria on the DOE page | DOE | https://www.energy.gov/node/4850502 |
| Flood | SFHA = 1%-annual-chance zones | Insurance required if any part is in SFHA | FEMA | https://fema.gov/flood-zones |

No federal acreage or distance threshold exists for data centers or manufacturing. EPA's 35 ac floor is also below the 36–45 ac that 5 MW needs at NREL intensities.

## (c) Simple screen per lens

Each criterion is pass, fail, or "not assessed". Unknown never counts as pass or fail.

- **Data center.** Grid min(line, substation) ≤10 mi; road ≤10 mi; not in SFHA (all borrowed from EPA or FEMA); load ≥100 MW reported as "not assessed". 32,499 sites pass, 26,479 of them brownfield with no land test. Adding acreage ≥100 leaves 1,318. The screen needs a land test to discriminate.
- **Generation (solar).** Acreage ≥35, transmission ≤10 mi, road ≤10 mi, not in SFHA. 2,048 sites before the flood test. Wind (≥1,200 ac, ≤5 mi): 517 sites.
- **Manufacturing.** No federal threshold found. Placeholder rail ≤8 mi (EPA biomass, borrowed) passes 36,899 sites, so it does not discriminate. Needs a sourced land floor.

Interface: replace the alphabetical list with pass/fail counts per screen; show "not assessed"; exclude land values above their state's area; keep Medium for acreage only when the source covers the parcel.

## Limits

- The NREL PDF did not load (nrel.gov unresolved from the sandbox). The 7.3/8.9 figures are secondary.
- EO 14318 primary text was not machine-readable.
- The node run mirrors the browser's fill-if-empty join but not `sanitizeGeographicEvidence` or evidence invalidations.
