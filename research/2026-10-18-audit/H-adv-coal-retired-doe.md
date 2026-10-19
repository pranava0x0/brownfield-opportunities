# Adversarial review: Coal Reinvestment, Retired Sites, DOE Sites (2026-10-18)

Read-only on the repo. Checked against shipped JSON, builders, app.js, and sources found by search. "Secondary" = not read at primary source.

## (a) Holes, ranked by severity

1. **Coal table answers the wrong question.** `renderCoalTable()` sorts by nameplate MW descending (app.js:4849). The top rows include W.A. Parish and Cumberland, both operating with `queue_transfer_eligible: false`. There is no readiness sort, so "best near-term" is not answerable here.

2. **Stranded value has no government basis and misapplies distance.** `calculate_stranded_asset_valuation()` (build_coal_conversions.py ~318) = MW×$180k + $25M water + $12M rail + $8M civil. No constant is cited. INL/RPT-22-67964 gives 15–35% of overnight capex for one 1,200 MWe case, not $/MW. The value is applied to operating plants and to Montour, a gas-converted plant with an occupied POI. The proximity layer multiplies by exp(−0.25·mi): a parcel 5 mi from Homer City gets 29% of the plant's value, and two Cheswick ACRES parcels at 0.6 mi show about $126M each. That value belongs to the plant, not the parcel.

3. **Status errors.**
   - *Naughton*: labeled `planned_retirement` 2026, `queue_transfer_eligible: true`. Search coverage says PacifiCorp is converting Naughton 1–2 to gas in 2026. The catalog's own rule (gas-converted POI is occupied) makes eligibility false.
   - *Craig*: the note says DOE Order 202-26-31 keeps Unit 1 available "through 2026-09-26". Today is 2026-10-18 and search found no renewal. The row is past its own end date.

4. **Selection bias, unreconciled sources.** The project's EIA files hold 140 retired coal-fuel plants (70,656 MW) and 42 planned coal retirements (48,704 MW). The 18 rows are about 9% of that. By name match, 15 of 18 are absent from `eia-retired-plants.json`, including Homer City and Bull Run (both listed as retired 2023). Craig is 2028 in the catalog and 2029 in `planned-retirements.json`. Cumberland is "operating" in the catalog and 2034 in the EIA file. None of this is flagged.

5. **Fast-track has no source.** `coal_conversion_queue_fasttrack` is distance alone (≤1.5 mi). It flags two Cheswick brownfield parcels. No cited rule grants queue position from proximity. The FERC surplus-service rule could not be verified at primary source; a 2018 pre-Order-2023 secondary summary says surplus service lapses at plant retirement, with a limited early-retirement exception.

6. **"Stopped reporting" is not closure.** The overlay's own docstring defines `valid_reason` as "closed / idled / dropped below threshold". 40 CFR 98.2(i) lets a facility exit by staying under 15,000 tCO2e for three years or 25,000 for five (secondary; eCFR redirected). Counterexample: GM Detroit-Hamtramck is listed as stopped after 2021, and a GM Authority table still shows it building Escalade IQ (secondary). `ghgrp_latest_year` is 2023, though RY2024 reports were due March 2025. EPA's September 2025 proposal and the October 14, 2026 interim rule (RY2025 deadline moved to March 10, 2027) make some gaps administrative. The overlay does not say whether the 2024 release was pulled.

7. **Retired tab has no ranking.** `buildRetiredView()` (app.js:4496) computes counts only. I did not read the list renderer below line 4520, so I cannot confirm whether it sorts.

8. **DOE fit cells against sources.**
   - *Portsmouth SODI, microreactor = anchored.* The vocabulary (build_hanford_e2e.py:513) says anchored means "already committed/operating on the parcel". The only nuclear interest is Oklo's option and right of first refusal from SODI, dated February 1, 2024. No powerhouse exists, and Oklo's target is 2030. An option is not a committed use. Strong at most.
   - *SRS AI lease area, data center = strong/land.* A secondary summary of the solicitation lists readiness, financial viability, permitting, and utility interconnection agreements as the evaluation factors. Under DOE's own criteria the binding constraint is power and permitting, not land.
   - *Paducah AI campus, anchored, 600 acres.* The July 2026 award and pending Kentucky PSC approval check out. DOE's release says about 785 acres leased. The 600-acre figure comes from a Brookfield spokesperson and disagrees with DOE.
   - SRS (selected to negotiate, no lease) is rated strong while Paducah (award plus lease) is rated anchored. Defensible, but no published rule is cited.

9. **No published DOE criteria.** The four-type matrix and every rating are authored. The Cleanup to Clean Energy launch page (energy.gov/node/4831701) has no site criteria.

## (b) Criteria table

| Criterion | Threshold | Source | URL | Used today? |
|---|---|---|---|---|
| Retirement status codes | RE/OS = retired | EIA-860M | https://www.eia.gov/electricity/data/eia860m | Partly; coal rows hand-set |
| POI occupancy | 0 operating units at same Plant ID | EIA-860M Plant ID | same | No |
| Nameplate | ≥100 MW | project EIA threshold | repo | Yes |
| Switchyard voltage | ≥230 kV within 2 mi | HIFLD via infra-proximity | repo | Yes, not gated |
| Long-run flow | annual mean, context only | USGS NWIS | https://waterservices.usgs.gov | Yes |
| Land | ≥300 ac | project precedent | repo | No government basis |
| Financing | EIR → Energy Dominance Financing | DOE LPO | https://www.energy.gov/edf/title-17-energy-infrastructure-reinvestment-eir-financing | No |
| DOE evaluation factors | readiness, finance, permitting, interconnection | DOE AI-DC solicitation (secondary) | https://www.ashurstperkinscoie.com/en/insights/department-of-energy-solicits-proposals-for-ai-data-centers-and-co-located-power/ | No |
| GHGRP off-ramp | <15,000 t × 3 yr or <25,000 t × 5 yr | 40 CFR 98.2(i) (secondary) | https://ccdsupport.com/confluence/x/7YIrI | No |
| Coal reuse capex | 15–35% of overnight capex | INL/RPT-22-67964 | https://gain.inl.gov/content/uploads/4/2024/11/INL-RPT-22-67964-Investigating-Benefits-and-Challenges-C2N.pdf | Cited, not used as input (correct) |

## (c) Proposed screens

**Coal (all EIA retired and planned plants, by script):**
1. Status from EIA-860M (RE/OS retired; planned year from Operating sheet). Gate: zero OP units at the same Plant ID.
2. Nameplate ≥100 MW.
3. Switchyard ≥230 kV within 2 mi (already computed in infra-proximity).
4. USGS annual mean flow as context.
5. Show MW, kV, acres, and water. Show dollars only with cited unit costs.
6. Drop fast-track until a cited queue rule exists.

**Retired (GHGRP):** Label rows "stopped reporting, last year Y". Call a site closed only with an independent record (EIA retirement, state permit surrender, or demolition). Rank only sites with an EIA match within 1 mi and nameplate ≥100 MW.

**DOE sites:** Each constraint maps to DOE's published factors. "Anchored" requires a signed lease, award, or operating use. Under that rule, Portsmouth SODI microreactor drops to strong or conditional.
