# Adversarial review: Nuclear Siting (A) and Microreactors (B)

Read-only; repo unchanged. INL/RPT-22-67964 and INL/MIS-24-80216 PDFs were unreadable, so their criteria are unverified.

## (a) Holes, by severity

1. **No shortlist exists.** `buildAp1000View` sorts alphabetically (app.js:5500). Nothing is scored, filtered or ranked. Switching class changes no table cell: `assessSite(s,"nuclear")` ignores class, which only affects the land sentence (app.js:5294-5301). Water, water_rights and fiber are `unknown` for all 14 sites, so the binding AP1000 constraint is blank everywhere.

2. **Land threshold tests the wrong quantity.** It uses installation-level `developable_acreage`, which all 14 sites pass (Robins 2,000; Edwards 100,000). Offered AF lease acreage (`af_rflp_acres`) fails 500 ac at Robins 265, Davis-Monthan 300, Arnold 274 and JBMDL 193. The 500 ac figure is unsourced. Janus has two thresholds: 20 ac in `REACTOR_CLASSES.micro` (siting-context.js:30) and 5 ac in `MICRO_MIN_ACRES` (line 36).

3. **Janus is stale, and the grid thesis contradicts the Army's criteria.** The Aug 26 2026 announcement (army.mil/article/294897) names five sites, and only Drum is confirmed on army.mil; the other four come from secondary reporting. Criteria: "mission requirements, power demand, grid maturity, and safety and environmental considerations." The dashboard still lists Wainwright, Holston, JBLM and Redstone as candidates. The five selected sites sit 0.1–4.2 mi from transmission. The removed inverted-grid lens placed its top 200 at a median of 11.2 mi, against a corpus median of 0.6 mi.

4. **No population, EPZ or site-specific seismic screen.** The UI uses no population fields. Government criteria the dashboard omits include 10 CFR 100.21 (population-center distance ≥1.33× LPZ), 100.3 (population center ~25,000), RG 4.7 Rev. 4 (population density, Appendix A for advanced reactors) and 50.33(g) (~10-mi EPZ default). Seismic `usgs_exceeds_sse` compares ASCE 7-22 design PGA to a 0.30 g threshold that appears only in a code comment (`build_ap1000_sites.py:538`). 10 CFR 100.23(d) requires a site-specific SSE. The flags (Wainwright 0.46 g, JBLM 0.59 g) are shown but never screened.

5. **Water is Vogtle-scaled and unscreened.** AP1000 consumptive 31.1 cfs/unit is from the Vogtle FEIS. APR1400 and AP300 are linear MWe scaling. No site has a low-flow value. Robins compares a 2012 annual mean (854 cfs) to 42 cfs demand. Fort Hood reports 22% of Belton system yield, which is not an allocation.

6. **Civilian tiers use 2024 licensing status, and two of four dark-green rows are terminated COLs.** Dark-green means "COL issued or can be reinstated" (builder docstring, from INL/MIS-24-80216). The NRC list shows Levy terminated (2018) and V.C. Summer terminated (2019). Notes still say "COL reinstatement feasible" and "fastest path given prior licensing." The tier screens no water, population, seismic or transmission. Drift: the docstring says 65 + 2 post-study, but the file has 68 with 3 post-study.

7. **Dead and misleading code.** `ap1000-score.js` and `microreactor-score.js` are unloaded. `ap1000-score.js` redeclares `const REACTOR_CLASSES`, which throws if re-enabled beside `siting-context.js`. The microreactor "ranked" list (app.js:5727) is alphabetical. The "Missing grid evidence" filter (app.js:5729) is not gated on `_infraChecked`, so before the infra join it matches every site.

## (b) Criteria table

| Criterion | Threshold | Source | URL | Used? |
|---|---|---|---|---|
| Population-center distance | ≥1.33× LPZ; ~25,000 residents | 10 CFR 100.21, 100.3 | https://www.law.cornell.edu/cfr/text/10/100.21 | No |
| Population density | Fixed 20-mi check; App. A alternatives | RG 4.7 Rev. 4 | https://www.govinfo.gov/content/pkg/FR-2024-02-29/html/2024-04223.htm | No |
| EPZ | ~10 mi default; performance-based option | 50.33(g), 50.160 (secondary) | https://www.morganlewis.com/blogs/upandatom/2023/11/nrc-provides-emergency-preparedness-flexibility-for-smrs-and-advanced-reactors | No |
| SSE | Site-specific, 100.23(d) | 10 CFR 100.23 | https://www.law.cornell.edu/cfr/text/10/100.23 | Partial: PGA vs uncited 0.30 g |
| Cooling water | 31.1 cfs/unit consumptive | Vogtle EIS-0476 | https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf | Partial: annual mean only |
| Janus criteria | Mission, power demand, grid maturity, safety | army.mil/294897 | https://www.army.mil/article/294897/army_selects_fort_drum_for_janus_program_microreactor | No; grid inverted |
| Coal screen | Pop. >500/sq mi incl. 4-mi buffer (secondary) | INL/RPT-22-67964 | https://gain.inl.gov/content/uploads/4/2024/11/INL-RPT-22-67964-Investigating-Benefits-and-Challenges-C2N.pdf | No |
| COL status | Issued / terminated | NRC COL list | https://www.nrc.gov/reactors/new-reactors/large-lwr/col-holder | Used, with errors |
| Land, AP1000 | 500 ac | none | none | Yes, unsourced |

## (c) Proposed screens

Each criterion is regulatory (R) or proxy (P). Proxies are not compliance findings.

- **Large PWR:** (1) P: no place >25,000 within 10 mi. (2) P: low flow ≥30× the 31.1 cfs demand, with 30× labelled internal. (3) R: site-specific SSE; P: ASCE PGA below the certified design basis, sourced first. (4) P: ≥230 kV within 5 mi. (5) P: offered or parcel acreage.
- **SMR/AP300:** same structure, EPZ scaled under 50.160, demand 9.2 cfs.
- **Microreactor:** Army's four criteria. (1) federal land, (2) documented power demand, (3) grid maturity, which conflicts with the current thesis and must be argued explicitly, (4) P: FEMA flood and population within 10 mi.
- **Civilian:** (1) COL issued, (2) P: population, (3) P: low-flow cooling, (4) P: seismic, (5) P: transmission. Report pass counts out of five, replacing the INL tier.
