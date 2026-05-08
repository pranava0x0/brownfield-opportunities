# Backlog

Ideas and enhancements. Priorities: **high** = next, **med** = soon, **low** = nice-to-have.

---

## Data-center suitability scoring (tiered plan, researched 2026-05-07)

**Goal.** Move the dashboard from "is this site a brownfield?" to "is this site a viable data-center site?" — a scored, persona-filterable view across all ~47k records. Today we have a single Boolean `data_center_reuse_candidate` flag (EPA RE-Powering, ≥50 ac + power + water, ~776 Superfund sites) plus universal `transmission_mi` / `rail_mi` / `highway_mi` distances. The thesis is that post-remediation industrial land with grid + water + fiber + favorable state tax is gold for AI buildouts; this section turns it into an actionable rubric.

**Supersedes** the older "Data Center Opportunity Dashboard (pivot)" section further down. Items marked with **[exists]** are already in this backlog elsewhere — recording them here too so the tier ordering is complete.

### Industry-standard thresholds (anchor for every filter / score)

Sourced from Datacenters.com, LightBox, EPA Brownfields, USPE Global, Equinix, Introl, ASHRAE 169, FEMA P-2192, S&P Global, Ramboll (cited inline in research notes). Encode these as `DC_TIERS` constants:

| Tier | Acreage | Power (HV transmission within) | Voltage class | Water | Climate / risk excludes |
|---|---|---|---|---|---|
| **Edge / inference** | ≥5 ac | ≤1 mi | ≥69 kV | optional (closed-loop OK) | FEMA Zone V; SDC E/F |
| **Colocation / general** | ≥25 ac | ≤1 mi | ≥138 kV | desirable; ≤2 mi to municipal | FEMA Zone A/AE/V; WHP Very High |
| **Hyperscale (100 MW+)** | ≥100 ac (matches EPA threshold) | ≤1 mi | ≥230 kV | required for evap; ≤1 mi or in PWS service area | + WRI Aqueduct BWS ≥3 (high-stress) |
| **AI mega-campus (500 MW+)** | ≥500 ac | ≤1 mi | ≥500 kV OR gas pipeline ≤2 mi (BTM viability) | flexible (closed-loop trend, e.g. Microsoft 2025+) | + non-attainment counties (NAAQS) for backup-gen permitting |

Reference figures: WUE industry avg = 1.8 L/kWh ≈ 276,000 gal/day per MW evap-cooled; rack power 100kW (NVIDIA GB200) → 600 kW (Vera Rubin 2026); typical interconnection-queue wait 5 yr (CAISO 9 yr); buildable share of acreage is 30–40% after buffers.

### ~~Tier 0 — Quick wins (zero new fetches, hours not days)~~ Done 2026-05-07 (PR #3)

All five Tier 0 items shipped together as the v1.12 data-center suitability scoring v0. Audit confirmed 2026-05-08 — 280 unit tests + 5 dedicated e2e tests passing; 250 hyperscale-ready sites surfaced in the live KPI; persona filter narrows the visible set with `?dc_tier=` URL round-trip; DC tier pill + kV chip + tax incentive chip render in the detail panel.

- ~~**[high] Voltage class on the existing transmission proximity result.**~~ Done — `connectors/infra_proximity.py` extracts `VOLTAGE` (Double, kV) with `VOLT_CLASS` fallback via `VOLT_CLASS_TO_KV` map; HIFLD null sentinel `-999999` collapses to None. `transmission_kv` populated on 46,211 / 46,211 records that have `transmission_mi` (100% coverage of in-range sites). Cache key includes `out_fields` so the v1.10 cache (no attributes) doesn't shadow the v1.12 fetch.
- ~~**[high] DC suitability score v0 from existing fields.**~~ Done — `computeDcScore(s)` in [app.js](docs/app.js:327) reads `acreage` + `transmission_mi` + `transmission_kv`, iterates `DC_TIERS` highest-down, returns `null | edge | colo | hyperscale | mega`. Sites without `transmission_kv` cap at edge (≥138 kV unverified). Renders as a `.dc-tier-pill` next to the existing `Cleanup Complete` / `Active Reuse` / `DC candidate` pills; hyperscale+ gets the green `.ready` variant.
- ~~**[high] Static state DC tax incentive lookup table.**~~ Done — `STATE_DC_INCENTIVES` in [app.js](docs/app.js:361) covers all 50 states + DC. **Audited 2026-05-08** — 16 rows corrected against primary sources (NC threshold $150M→$75M, OH payroll floor added, CT thresholds added, FL HB 7031, IA 2025 rollback, MN moved to Tier 3 / `partially_repealed`, UT moved to Tier 2, OK `under_reform`, AR Act 548, CO `pending_legislation`); `verified_at` field added to every row (16 verified, 35 inherited from initial pass and flagged for future audit). `renderStateIncentive(s)` surfaces a per-state chip with program name + min investment + sunset year + status note (`active` / `expanded` / `under_reform` / `restricted` / `restrictive` / `partially_repealed` / `pending_legislation` / `none` / `no_state_sales_tax`). The "Tier 1 incentive states only" *filter facet* was scoped out — per-state filter already lets users hit it directly; revisit if a user requests bulk-tier filtering.

- **[med] Backfill `verified_at` for the 35 unverified `STATE_DC_INCENTIVES` rows.** The 2026-05-08 audit verified 16 rows against primary sources but left 35 at aggregator-grade (`verified_at: null`). High-stakes unverified rows: AZ / NV / TN (Tier 1 — large investment thresholds claimed without statute citation); MI's 2050 sunset (suspiciously precise); IL's 2029 sunset; WI / IN / KY / WV / WA / OR — all listed with no investment threshold, which is more likely "table author didn't research" than "program genuinely has no minimum." Approach: walk the unverified rows in batches of ~10, anchor each on the [NCSL snapshot](https://www.ncsl.org/fiscal/policy-snapshot-data-center-incentives) plus state DOR / EDC primary URL, update structured fields + URL + `verified_at: "YYYY-MM-DD"`. Don't create new rows speculatively — Tier 3 absences are correct unless the row was already in the table. ~2 hours total. **Cadence:** re-audit Tier 1 + Tier 2 rows annually (legislative sessions land in Q1-Q2 each year and produce status drift faster than the data itself).
- ~~**[high] Persona filter presets in the filter UI.**~~ Done — four buttons (Edge/Colo/Hyperscale/AI mega) in `#f-personas`, generated from `PERSONA_PRESETS = [...DC_TIERS].reverse()` so future tiers drop in via the same drift-safe legend-iteration pattern as `PROGRAM_LEGEND` (UAT-007 lesson). Click toggles `filterState.dcTier`; debounced `syncUrl()` writes `?dc_tier=` (200ms after click). Reset clears it. The acreage slider stays independent — persona filter narrows by *computed score*, not by mutating `minAcreage`.
- ~~**[high] KPI cell: hyperscale-ready count.**~~ Done — `#kpi-hyperscale` in [index.html](docs/index.html:72), computed from in-memory `sites` post-lazy-load; 250 sites at audit time. Subtext: "≥100 ac · ≥230 kV · ≤1 mi" (drops the "water service area" wording since the score doesn't currently gate on water — that was a v0 simplification, revisit when Tier 1 layers land).

### Tier 1 — High-signal new layers (1–2 days each)

Each adds one connector or extends `infra-proximity`. All free, no auth (or instant free-tier signup).

- **[high] HIFLD natural-gas pipelines → `gas_pipeline_mi`.** Source: `https://hifld-geoplatform.hub.arcgis.com/datasets/geoplatform::natural-gas-interstate-and-intrastate-pipelines/about`. Polylines, EIA-sourced, free, no auth. Reuse `connectors/spatial.py:SegmentIndex` exactly like transmission. Threshold: `<2 mi` enables behind-the-meter gas turbines (Stargate Texas pattern: VoltaGrid 2.3 GW BTM gas + GE Vernova 29 turbines). Adds one field to `infra-proximity.json`. Use the `hifld-geoplatform.hub.arcgis.com` ArcGIS Hub path — the legacy `gii.dhs.gov/HIFLD` portal shut down 2025-08-26, **don't use those URLs**.

- **[high] EIA Atlas → `iso_rto` region attribution.** Source: `https://atlas.eia.gov/datasets/eia::rto-regions/explore` — GeoJSON of PJM / MISO / ERCOT / CAISO / SPP / NYISO / ISO-NE polygons + non-RTO areas. Point-in-polygon assign each site a string `iso_rto`. Surface in the detail panel and as a filter facet. CAISO interconnection queue is now **9 yr** average vs. 5 yr nationally — non-CAISO is a meaningful filter for "speed-to-power".

- **[high] FEMA National Risk Index (NRI) → composite climate-risk fields.** Source: `https://www.fema.gov/about/openfema/data-sets/national-risk-index-data` — bulk CSV at census-tract resolution, ~150 MB, all 50 states. **One layer covers hurricane / tornado / wildfire / drought / earthquake / hail.** Per-hazard `*_EALT` fields (annualized expected loss) — carry these unaggregated so the frontend can re-weight for DC sensitivities (downweight hail/winter weather, upweight wildfire/drought/heat). Tract-level join via `connectors/county_lookup.py` extension to tract-level TIGER polygons (or pip-install `pygris` for the lookup). New `connectors/fema_nri.py`, `run_order=300`. **This is the single highest-value-per-dev-hour layer** — replaces ~5 separate hazard layers we'd otherwise build.

- **[high] USGS seismic API → `sdc` (A–F).** Source: `https://earthquake.usgs.gov/ws/designmaps/asce7-22.json?latitude=...&longitude=...&riskCategory=III&siteClass=D`. Returns SDS, SD1, and the derived SDC. Per-site live REST, ~1 s/call, no key. 47 k sites × 1.5 s = ~20 hr — overnight enrichment connector. Use Risk Category III (DCs are "substantial hazard to life on failure"), Site Class D default. Threshold: SDC ≥ D = significant structural cost premium; SDC ≥ E = often disqualifying. New `connectors/usgs_seismic.py`, `run_order=320`.

- **[high] ASHRAE climate zone → `climate_zone`.** Source: Building America / IECC Climate Zones by U.S. County, ~3,200 rows ArcGIS Hub CSV. Trivial join via existing `connectors/county_lookup.py:CountyIndex`. ~50 KB lookup table baked in. Fields: zone (1–8) + suffix (A humid / B dry / C marine). Industry sweet spot: 3B / 4B / 5B / 6B (dry climates → free-cooling-friendly).

### Tier 2 — Medium-signal new layers (3–5 days each)

- **[high] Audubon OSM substations → `substation_mi`.** HIFLD substations have been auth-walled since 2022 (DHS/CEII) and the HIFLD Open portal shut down 2025-08-26. Free alternative: Audubon ArcGIS Hub publishes an OSM-derived substations FeatureServer at `https://data-library-audubon.hub.arcgis.com/content/7ddd8bf991eb483d8f172fda75903b1b`. Filter to `voltage ≥ 69000` (HV-only). Coverage ~70–80% of US HV substations (vs. legacy HIFLD's ~99%) — document as a known gap. Backup: OSM Overpass API direct query, rate-limited, tile by state. Add to `infra-proximity.json` as a fourth `SegmentIndex` (point-to-point, not polyline).

- **[high] LBNL Queued Up + `gridstatus` → queued MW within 50 mi.** Source (a) LBNL Queued Up 2025 Edition annual Excel at `https://emp.lbl.gov/queues` — project-level rows from 7 ISO/RTOs + 49 non-ISO BAs (~97% US capacity), county/state-level. Source (b) `gridstatus` Python lib (Apache 2.0, `pip install gridstatus`) — live `iso.get_interconnection_queue()` for CAISO / MISO / ERCOT / NYISO / PJM / ISO-NE / SPP. NYISO/PJM/MISO ship lat-lon; CAISO/ERCOT/SPP are county-only. Aggregate to `queued_mw_50mi` per site. Use LBNL for non-ISO regions, gridstatus for ISO regions. New `connectors/queue_capacity.py`, `run_order=310`. **MW available is the actual gating factor for DC siting** — stronger signal than "is there a wire nearby."

- **[high] EIA Form 861 + HIFLD service territory → `electricity_rate_cents_kwh`.** Two-step: (a) HIFLD `Electric_Retail_Service_Territories` (NASA mirror at `https://maps.nccs.nasa.gov/mapping/rest/services/hifld_open/energy/FeatureServer/26` — the most reliable post-HIFLD-shutdown endpoint). Polygons keyed by `ID` (matches EIA `Utility_Number`). (b) EIA Open Data API `electricity/retail-sales` — `https://api.eia.gov/v2/electricity/retail-sales/data?api_key=<KEY>` with free key (instant signup). Cross-walk: site lat/lon → service-territory polygon → `Utility_Number` → EIA industrial-sector rate. Fall back to state-average industrial rate when polygon coverage misses. New `connectors/utility_rates.py`, `run_order=330`. Industrial rates are the right sector — not residential.

- **[med] NOAA NCEI 1991-2020 climate normals → `cdd65` / `hdd65`.** Bulk CSV download at `https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020/` — ~7,300 stations with `ANN-CLDD-BASE65` field. IDW point-sample to site lat/lon using 5 nearest stations. Tiers: CDD<2,000 = excellent (Pacific NW, Upper Midwest); 2,000–3,500 = moderate; >3,500 = poor (Sun Belt). New `connectors/noaa_normals.py`, `run_order=340`. ~10 MB compressed cache. HDD comes free in the same product.

- **[med] FEMA NFHL flood zones → `flood_zone`.** Source: `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer` layer 28 (Flood Hazard Zones). Per-site `intersects` query returns `FLD_ZONE` (`A`/`AE`/`AH`/`AO`/`A99`/`V`/`VE`/`X`/`D`). Excludes A/AE/AH/AO/V/VE for hyperscale (1% annual chance — Special Flood Hazard Area). ~25% of CONUS isn't NFHL-mapped → null is informative ("unmapped"), not a clear pass. Per-site live REST, overnight enrichment job for 47 k records. Apply the **TIGERweb page-size quirk** rule: `page_size=1000` with geometry. New `connectors/fema_flood.py`, `run_order=350`.

- **[med] USFS Wildfire Hazard Potential 2023 raster → `wildfire_class`.** Source: `https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential` — 270 m raster, 5 classes (Very Low → Very High). Bulk GeoTIFF (~1 GB) + `rasterio.sample()` is faster than per-site REST `identify` (which would be 47 k × 1.5 s = 20 hr). Use the GeoTIFF path. Threshold: exclude class 5 (Very High); flag class 4 (High) for hardened design. ~8% of CONUS land in classes 4–5. Will need to add `rasterio` to `requirements.txt` — first non-pure-Python dep; flag for review. CONUS-only (skip AK/HI).

- **[med] WRI Aqueduct 4.0 baseline water stress → `water_stress_score`.** Source: `https://www.wri.org/data/aqueduct-water-risk-atlas` — HydroBASINS sub-basin polygon shapefile, ~80 MB. Field `bws_score` (0–5 categorical). Threshold: `≥3` (>40% withdrawal/supply ratio) = high-stress flag, exclude or require closed-loop cooling. Carry 2030/2040 projections too — they're free with the baseline pull. Reuse `connectors/spatial.py` polygon point-in-polygon pattern. **Crucial for the AI mega-campus tier** since they're ~1–5 M gal/day each. New `connectors/wri_aqueduct.py`, `run_order=325`.

- **[med] EPA AQS PM2.5 county aggregate → `pm25_ugm3`.** Source: `https://aqs.epa.gov/aqsweb/airdata/download_files.html` — pre-aggregated `annual_conc_by_monitor` CSV per year, ~20 MB. Aggregate by county, average over last 3–5 years. Threshold: EPA NAAQS annual standard 9 µg/m³ (lowered 2024). Flag counties >12 µg/m³ as "outside-air economizer needs significant filtration." For unmonitored counties, use nearest-monitor IDW or flag as "unmonitored." New `connectors/epa_aqs.py`, `run_order=345`. Same county-FIPS join pattern as ASHRAE zone.

- **[med] EPA Green Book NAAQS attainment → `attainment_status`.** Source: `https://www.epa.gov/green-book/green-book-gis-download` — per-pollutant zipped Shapefiles + PHISTORY CSV. Per-county nonattainment status by pollutant. **Crucial for backup-generator permitting** (non-attainment counties trigger NSR for new generator stacks → multi-month permit drag). New `connectors/epa_greenbook.py`, `run_order=345`. Tiny dataset; trivial county join.

### Tier 3 — Composite scoring + UI rebuild (after Tier 1+2 lands)

- **[high] `compute_dc_score(s)` v1 — weighted multi-criteria score.** Replace the v0 frontend score with a weighted rubric. Per-persona weight tables — what matters for AI mega-campus (power capacity, gas pipeline, water stress) is different from edge inference (latency, fiber, smaller acreage). Output: `dc_score: 0–100` per site, plus `dc_score_breakdown: {power: 0–25, water: 0–15, climate: 0–15, ...}` so the detail panel can show *why*. Keep it pure-functional / deterministic — buyers must be able to reason about scoring. **Persona presets**: `hyperscale_default`, `ai_mega_campus`, `edge_inference`, `crypto_hpc`. Each is a static weight dict in `app.js` — no ML.

- **[high] Detail panel "Data Center Suitability" section.** New `#d-dc-block` between the existing `#d-infra-block` (universal infrastructure distances) and the documents block. Shows: (a) tier badge (Edge/Colo/Hyperscale/Mega/None) with the matched threshold inline, (b) score breakdown by category as a 4–6 row mini-table, (c) state tax incentive chip + URL, (d) ISO/RTO + interconnection queue MW, (e) climate-risk row aggregated from FEMA NRI fields, (f) deal-blockers (flood zone, SDC ≥ E, WHP class 5, non-attainment) listed as red flags. Hidden when the site doesn't meet even Edge tier or when no DC data is available. **Don't** dump every field — synthesize like the AI summary block does. Use the v1.11 tab strip pattern (Overview / Summary tabs); add a third "DC Score" tab if it gets long enough to warrant.

- **[high] Persona filter UI.** Above the persona-tier buttons from Tier 0, add a "Profile" dropdown: `Hyperscale (default)` · `AI mega-campus` · `Edge / inference` · `Crypto / HPC`. Switching the profile recomputes scores for all sites and re-renders the table sort. URL state: `?profile=ai_mega`. Default profile from `localStorage` so a returning user keeps their persona.

- **[med] Map: filled markers for top-quartile DC scores.** Tier 1 hyperscale-ready sites get a filled circle with a halo; sub-tier sites stay as the existing dot. Don't add a new color — use the existing program color but add a 2px outer stroke. Drives "where in the US is the dense set of viable sites" at a glance. Implement only after Tier 1+2 layers land.

- **[med] KPI deck: 4-cell DC view.** Replace one of the existing KPI cells (probably `#kpi-states`) with `#kpi-power-ready` (count of sites within 1 mi of ≥230 kV transmission), `#kpi-water-ready` (count near a water source for evap or in PWS service area), `#kpi-tax-tier1` (count in Tier 1 incentive states). Hyperscale-ready remains as `#kpi-hyperscale` (Tier 0).

### Tier 4 — Nice-to-have / advanced (defer until users request)

- **[low] USGS NHD water bodies → `water_body_mi`.** For evap-cooling proximity (vs. PWS service area). NHD HighRes is enormous; the right cut is `NHDWaterbody` filtered to `FType=390` (LakePond) AND `AreaSqKm > 1.0`, plus `NHDFlowline` filtered to perennial streams (`FCode IN (46006, 55800)`). Bulk download by HUC-4. NHD itself was retired 2023-10-01 — data still available, future updates flow through 3DHP. Useful for the AI mega-campus tier but also genuine source-of-truth complexity (millions of features). Defer until evap-cooling proximity becomes a binding filter.

- **[low] EPA Community Water System Service Area Boundaries → `pws_service_id`.** Source: `https://www.epa.gov/ground-water-and-drinking-water/community-water-system-service-area-boundaries` — EPA released a national modeled dataset in 2024 covering ~44 k CWS systems (~99% of CWS-served population). Polygon shapefile keyed by federal `PWSID`. Stronger signal than "near a water main" because PWSID also lets us cross-walk SDWIS for capacity / violation data. The existing `near_water_supply` Redev field is a Superfund-only buckets ("Yes — 1 mile") proxy; this would be a precise replacement for all programs.

- **[low] FAA airports → `airport_dist_mi`.** Source: `https://adds-faa.opendata.arcgis.com/` — Airports + Runways layers, free, no auth. Filter `Runways.LENGTH > 3200` ft; flag sites <3 mi from a qualifying runway endpoint (FAA Part 77 imaginary-surface conflict — cooling tower / gen-set exhaust triggers Form 7460-1 review). Low priority because most contaminated industrial sites are already away from active airports; mostly a flag-not-exclude field.

- **[low] NREL NSRDB → `solar_ghi_kwh_m2_day`.** Source: `https://developer.nrel.gov/docs/solar/nsrdb/nsrdb_data_query/` — free API key, ~1000 calls/hr. Threshold `>5 kWh/m²/day` annual GHI = solar-attractive. Only matters if the dashboard claims behind-the-meter PPA viability. Defer.

- **[low] NREL Wind Toolkit → `wind_cf_pct`.** Source: `https://developer.nrel.gov/docs/wind/wind-toolkit/` — same key. Threshold `>35%` 100 m hub-height capacity factor = wind-attractive (Great Plains corridor IA→TX). Defer with NSRDB.

- **[low] PeeringDB IXP locations → `ixp_dist_mi` (fiber proxy).** Source: `https://www.peeringdb.com/api/ix` — free anonymous read, ~120 US IXPs with `latitude`/`longitude` on linked `fac` endpoint. Proxy for "fiber-rich metro" since IXPs sit at major carrier hotels. Not a real long-haul fiber map but the best free proxy — the cleanest public layer doesn't exist (GeoTel / FiberLocator are paid-only, ~$5–25 k/yr). Pair with FCC BDC fiber-served address density per H3 cell for a second proxy.

### Tier 5 — Defer / no clean public source

- **Long-haul fiber routes.** No clean public layer. GeoTel / FiberLocator / NA Fiber Map are paid. Best free proxies are PeeringDB IXP + FCC BDC last-mile (above). Don't promise fiber proximity until at least one paid source is funded.
- **Real-time available transmission capacity (FERC OASIS).** Fragmented across per-provider portals with no central bulk API. FERC Form 715 is CEII-restricted. Both are dead ends. Use queued-MW proxy via LBNL + gridstatus (Tier 2) instead.
- **Water rights (Western US).** State-by-state, no machine-readable national source. Defer until a single-state customer pilot funds the per-state work.
- **Local zoning / land use.** Most counties don't publish machine-readable zoning. The "manual-check-needed" item already in the older "Data Center Opportunity Dashboard (pivot)" section stays accurate.
- **Anticipated Future Land Use (AFL) codes.** Already confirmed dead end 2026-05-05 — SEMS-internal field, FOIA-only.

### Suggested implementation order

A two-week MVP path that turns this into a usable scoring view:

1. **Week 1 — Tier 0 + start Tier 1.** Voltage-class extension, frontend score v0, state-incentive lookup table, persona filter buttons, hyperscale KPI cell. Then `gas_pipeline_mi` (HIFLD reuse), `iso_rto` (EIA Atlas point-in-polygon), ASHRAE zone (county-FIPS lookup). All zero-paid-deps; the FEMA NRI bulk pull starts overnight.
2. **Week 2 — Finish Tier 1.** USGS seismic API enrichment (overnight job), FEMA NRI tract-level fields, detail panel `#d-dc-block` v1 surfacing everything that landed. Stop here for a release; ship the scoring as v1.12.
3. **Following sprint — Tier 2.** Audubon substations, LBNL queue capacity, EIA utility rates, climate normals. Add `compute_dc_score` v1 with weighted rubric and persona presets.
4. **Defer Tier 3 UI rebuild** until Tier 2 lands — designing the detail-panel section before the full data is on disk would force rework.

### Schema additions

Add to `SiteRecord` in `schema.py` (all optional / nullable — `extra="forbid"` keeps drift loud):

```python
# Tier 0 — voltage class on existing transmission proximity
transmission_kv: float | None  # nominal kV of nearest HIFLD line; null when source is null

# Tier 1 — high-signal layers
gas_pipeline_mi: float | None        # miles to nearest HIFLD natural-gas pipeline
iso_rto: str | None                  # PJM | MISO | ERCOT | CAISO | SPP | NYISO | ISO-NE | non-RTO
sdc: Literal["A", "B", "C", "D", "E", "F"] | None  # USGS ASCE 7-22 Seismic Design Category
climate_zone: str | None             # ASHRAE 169 zone, e.g. "5B" / "3A"

# FEMA NRI — composite climate-risk per hazard (annualized expected loss in USD)
nri: dict | None                     # {hurricane_ealt, tornado_ealt, wildfire_ealt, drought_ealt,
                                     #  earthquake_ealt, hail_ealt, ...} — frontend re-weights for DC

# Tier 2 — medium-signal layers
substation_mi: float | None          # miles to nearest HV (≥69 kV) substation (OSM/Audubon)
queued_mw_50mi: float | None         # MW queued for interconnection within 50 mi (LBNL + gridstatus)
electricity_rate_cents_kwh: float | None  # EIA Form 861 industrial-sector rate
cdd65: int | None                    # annual cooling-degree-days base 65°F (NOAA normals)
hdd65: int | None                    # annual heating-degree-days base 65°F
flood_zone: str | None               # FEMA NFHL FLD_ZONE; null = unmapped (informative)
wildfire_class: int | None           # USFS WHP 2023 class 1–5
water_stress_score: int | None       # WRI Aqueduct BWS 0–5
pm25_ugm3: float | None              # 5-yr average PM2.5 from EPA AQS
attainment_status: dict | None       # per-pollutant: {ozone: "attainment", pm25: "nonattainment", ...}

# Tier 3 — derived / score
dc_score: int | None                 # 0–100, computed at runtime from the above
dc_tier: Literal["edge", "colo", "hyperscale", "mega"] | None  # derived bucket
```

### Frontend constants to add (single source of truth)

In `app.js`:
- `DC_TIERS` — the threshold table from the top of this section.
- `STATE_DC_INCENTIVES` — full 50-state + DC lookup.
- `PERSONA_WEIGHTS` — per-persona weight dict for `compute_dc_score`.
- `ISO_RTO_LABELS` — display labels for `iso_rto` values.

All are static; no fetches. `READINESS_LEGEND` pattern (Reset handler iterates the legend, UAT-007) applies — when a new persona ships, `Reset` and `populateProfileFilter` pick it up for free.

### Cost summary

Everything in Tier 0–2 is **free, no auth or one-time free signup**. Two paid fallbacks flagged for later:
- Regrid / Landgrid Parcel API (~$0.001–0.01 / parcel) for owner data — already in backlog.
- GeoTel / FiberLocator (~$5–25 k/yr) for true long-haul fiber routes — only if a paying customer cites fiber as a binding filter.

The single new dep introduced: **`rasterio`** (for USFS WHP raster sampling, Tier 2). First non-pure-Python connector dep — flag for review when the PR lands. WRI Aqueduct, FEMA NRI, NHD all stay in the existing `connectors/spatial.py` polygon pattern with no new C extensions.

---

## ~~Static summary quality pass (audited 2026-05-05)~~ Fixed 2026-05-05

Systematic review of all 1,787 generated static summaries found 9 recurring issues. Grouped by impact — fix the HIGH items before re-running at scale.

**[high] Apostrophe title-case bug — 20 sites.** `str.title()` treats `'` as a word boundary, producing `Beck'S Lake`, `Sigmon'S Septic Tank Service`. Replace `w.title()` in `_pretty_text()` with a regex-based variant: split on word-start boundaries only (e.g. `re.sub(r"(?<!['\w])(\w)", lambda m: m.group().upper(), text.lower())`), or use `string.capwords(w)` per word which handles apostrophes correctly.

**[high] Prepositions kept uppercase — 87 sites.** The `len(core) <= 2 and core.isupper()` rule in `_pretty_text()` is too broad: it preserves `OF`, `IN`, `AT`, `AN`, `BY`, `TO` (prepositions) the same way it preserves state codes and acronyms, producing `University OF Minnesota`, `Kokomo, IN (Currently on the Final NPL)` mid-sentence, `Town OF Bedford`. Fix: add an explicit `STOP_WORDS = {"of", "in", "at", "an", "by", "to", "for", "the", "and", "or"}` set and lowercase those unconditionally _before_ the acronym/length check. State codes (2-char) should go in `_NAME_KEEP_UPPER` explicitly so the ≤2-char catch-all can be removed.

**[high] "CO." kept uppercase — 179 sites.** "Company" abbreviation `CO.` strips to core `CO` which hits the ≤2-char rule and stays as `CO.` rather than becoming `Co.` — looks like the state abbreviation for Colorado. Fix is the same as above: kill the ≤2-char catch-all and whitelist state postal codes explicitly. `CO.` would then fall through to `w.title()` → `Co.` correctly.

**[high] "No Violation Identified" noise in enforcement block — 80 sites.** When the only ECHO signal is `current_compliance: "No Violation Identified"` with zero formal actions, zero penalties, and no violation date, the enforcement sentence reads `ECHO enforcement: compliance: No Violation Identified.` — a clean record surfaced as if it were a risk. Fix in `build_static_summary()`: suppress the enforcement block entirely when `formal_actions_5yr == 0` and `penalties_5yr_usd == 0` and `last_violation_date` is null. A clean compliance status is better shown as a brief inline positive note only if ECHO data exists at all (e.g. "No enforcement actions on record (ECHO).").

**[high] Grammar: "is a EPA" — 11 sites.** The lead sentence uses `"a"` before `program_label`, but labels starting with a vowel sound ("EPA Superfund", "ARNG", "USCG") need `"an"`. Fix: check `program_label[0].lower() in "aeiou"` in `build_static_summary()` and swap to `"an"` accordingly.

**[med] 0-acre anomaly — 70 sites.** Sites where the source acreage field is literally `0` or rounds to zero produce `a 0-acre EPA Superfund` which looks like a data error. Fix: treat `acreage == 0` the same as `acreage is None` — omit the acreage token entirely and let the sentence read `Genzale Plating Co. is an EPA Superfund (NPL) in Franklin Square, NY (Final NPL).`

~~**[med] "0.0 mi" for adjacent infrastructure — 213 sites.**~~ Done 2026-05-06 (v1.11.4) — `_fmt_distance()` now returns `"adjacent"` when `v < 0.05` and `f"{v:.1f} miles away"` otherwise, with all three infra clauses sharing the same shape. Frontend `fmt.miles()` mirrors the rule (renders `"Adjacent"` so it reads as a value, not placeholder text). 206 of 1,787 static summaries now read `transmission lines adjacent` / `rail adjacent` / `highway adjacent`; zero `on-site` strings remain.

~~**[med] DC reuse parenthetical repeated verbatim on 776 sites.**~~ Done 2026-05-06 (v1.11.4) — trimmed to `"Flagged as a data-center reuse candidate."` in `build_static_summary()`. The criteria still surface in three lower-noise places: the KPI-deck subtext, the legend pill tooltip, and the new detail-panel `.dd-criteria` sub-line (see entry below).

**[low] Status phrasing is verbose — all 1,787 sites.** `"(Currently on the Final NPL)"` is 26 chars; `"(Deleted from the Final NPL)"` is 28 chars. Shorter: `"(Final NPL)"` / `"(Deleted from NPL)"`. Reduces avg summary length ~10 chars with no information loss. Low priority since the text is still correct and readable.

---

## ~~Static summary prose rewrite (2026-05-05)~~ Done

After the 9-issue quality pass, `build_static_summary()` was rewritten from a colon-separated field dump to natural flowing sentences:

- ~~**Lead sentence**~~ Done — "X is a Y-acre Program in City, ST, currently on the Final NPL." (acreage omitted when null or 0; article "a"/"an" correct; NPL status shortened to "Final NPL" / "Deleted from NPL").
- ~~**Infrastructure**~~ Done — "Infrastructure proximity: transmission lines 0.8 miles from the boundary, rail 7.0 miles, and highway 31.9 miles." Oxford-comma-joined via `_join_list()`; "on-site" when `< 0.05 mi` via `_fmt_distance()` (avoids "0.0 miles" display bug). Only infra types with data are listed.
- ~~**DC reuse**~~ Done — "The site meets EPA RE-Powering criteria as a data-center reuse candidate." (parenthetical "(≥50 ac + power + water)" trimmed — criteria visible in legend/panel).
- ~~**Owner**~~ Done — "Current owner: X (per USACE FUDS)." when source provides it.
- ~~**Documents**~~ Done — "N federal documents on file (Category A, Category B, and Category C)." Correct singular/plural; Oxford-comma list.
- ~~**Enforcement**~~ Done — "EPA ECHO records show N formal enforcement actions in the past 5 years and $X in penalties." Block suppressed entirely for clean records (zero formal actions + zero penalties).
- ~~**Disclaimer**~~ Done — All summaries end with "AI-generated summary from federal records." so the generated nature is always attributed.
- ~~**Sparse fallback**~~ Done — When no infra/docs/enforcement data is available, a natural sentence "No infrastructure proximity, document, or enforcement data is available…" replaces an empty block.
All 1,787 F+D summaries regenerated (964 KB). Helpers extracted: `_fmt_distance(v)`, `_join_list(items)`.

---

## Continue ECHO + docs coverage (2026-05-05+)

The v1.11.2 commit fixed the ECHO connector and shipped 380 of 1,787 Final/Deleted Superfund sites with enforcement data. Batches 2–5 (2026-05-05/06) added 796 more sites, bringing ECHO coverage to **1,176/1,787 (65.8%)**. A parallel docs batch (2026-05-05/06, ran overnight) processed 100 sites and yielded 86 with documents (14 had no EPA docs on file); merged with prior 88 gives **155/1,787 (8.7%)**. Continued coverage is gated by upstream API throttling, so this is staged work, not a single sprint:

- **[high] Continue ECHO backfill (611 sites remaining).** Next run: `--echo-skip 1176 --echo-limit 200`. ECHO bot-detection backs off correctly but adds ~2 min overhead per 200 sites. At 200 sites/day, full coverage takes ~3 more batches (~3 days). Bot-block rate can be halved by raising the per-call delay to ~3 s in the connector.
- **[high] Continue docs backfill (~1,632 sites remaining).** Each uncached site takes ~3 min (EPA servers throttle at ~1 req/min). 100-site batch = ~4 hrs. Next run: `--docs-skip 155 --docs-limit 100` (skip=155 because sort orders may diverge; run from fresh + merge). Merge pattern: load HEAD JSON, load new-batch JSON, merge by ID (new supersedes old), commit. Long-term, consider bumping `REQUEST_TIMEOUT_S` from 60 s → 90 s to reduce empty-response retries.
- **[med] Regenerate ai-summary after each ECHO/docs batch.** Static summaries are cache-aware (`_fingerprint()` hashes the enrichment fields). Run `python3 refresh.py --source ai-summary --ai-static --ai-status F,D --ai-limit 0` after each batch; only sites whose ECHO/docs data changed will be regenerated (~200 per ECHO batch, ~3–5 s total). Already done: 1,176 sites now include enforcement context in their summaries.
- **[low] ECHO non-Superfund coverage.** The connector currently only enriches Superfund records (`run_order = 250` reads `superfund-npl.json`). FUDS / ACRES / BRAC sites don't have an EPA_ID equivalent for ECHO's `p_pid` filter — would need a name + state fuzzy match (`p_fn` + `p_st`) which is unreliable. Defer until an actual user asks for non-Superfund enforcement data.

---

## ~~v1.11.1 — Bug-fix pass + UX polish (2026-05-05)~~ Done

Three defects closed:

- ~~**[high] `?site=FUDS-/BRAC-` showed a premature "not found" toast.**~~ Done 2026-05-05 — `applyUrlSelection()` now `Promise.allSettled`s every in-flight program-data fetch (ACRES / FUDS / BRAC) before declaring an ID unknown; boot order rearranged so the lazy-load promises are populated *before* `applyUrlSelection()` runs. Same drift-risk pattern as the Reset handler (UAT-007).
- ~~**[high] CSV export silently dropped every enrichment field.**~~ Done 2026-05-05 — extracted `CSV_COLUMNS` to a curated 40-field schema mirroring the detail panel (FUDS / BRAC / owner / universal infra distances / EPA RE-Powering qualitative buckets / ECHO enforcement / document count). `pickCsvField()` walks dotted paths (`enforcement.formal_actions_5yr`) and supports a `.length` shortcut for array sizes.
- ~~**[high] Site names rendered ALL CAPS in table, marker tooltip, and detail title.**~~ Done 2026-05-05 — new `prettyName()` helper runs in `ingestSites()` with an EPA/DOD acronym whitelist (NIKE, AFB, NRDA, PCB, USDOE, USACE, USDA, USFS, BLM, NPS, …) seeded from a frequency scan of the dataset. Raw preserved on `s.name_raw`.

Demoted from this pass — call out for future work:

- ~~**[med] Out-of-CONUS infra placeholder.**~~ Done 2026-05-07 (path a) — `setMileCell()` renders `"Remote — outside continental US"` when `s._inset` is truthy. Path b (AK-specific enrichment) still open if a user requests AK-specific infra distances.
- **[med] Connector-side site-name normalization.** Today's `prettyName()` runs at frontend ingest. Per-source connector-side normalization with explicit acronym whitelists (Superfund EPA-name conventions vs. FUDS USACE-name conventions vs. BRAC installation-name conventions) would push the prettified form into the canonical JSON files so downstream consumers don't have to reimplement the heuristic. Defer until a non-frontend consumer materializes.
- **[med] Dynamic CSV column set.** Today the CSV column list is curated/static. A dynamic variant — derive the column set from the union of populated keys in the visible rows — would adapt automatically when new enrichment fields land but creates variable-schema annoyance for spreadsheet workflows that diff exports across runs. Stable schema beats dynamic for now.

---

## ~~v1.10.1 — Audit-driven data-completeness fixes (2026-05-04)~~ Done

Five gaps from the 2026-05-04 systematic null-rate audit closed in one pass:

- ~~**[high] Superfund documents at scale.**~~ Done 2026-05-04 — `epa-superfund-docs` re-run with `--docs-limit 500 --docs-status F,D` lifts coverage from 7 / 1,908 sites (0.4%) to ~500 of the largest Final/Deleted NPL sites by acreage. Also hardened the connector against single-blip `cumulis.epa.gov` / `semspub.epa.gov` connection timeouts (was aborting the whole batch on the first network hiccup); `requests.ConnectionError` / `requests.Timeout` now log-and-skip per site, same as transient HTTP codes.
- ~~**[high] ACRES county fill via offline TIGER spatial join.**~~ Done 2026-05-04 — new `connectors/county_lookup.py` decodes `docs/data/us-counties-topo.json` into a 0.5°-cell point-in-polygon index; `EpaAcres._fill_missing_county()` runs after normalize. Lifts ACRES county coverage from 48.8% to 99.7% (18,322 / 18,421 missing records filled). Pure Python — no shapely/rtree dep, no Census Geocoder calls. ~5 sec total runtime cost. Disambiguates same-named counties across states by validating the polygon's FIPS-derived state against the record's `state` field.
- ~~**[high] FUDS detail-panel "Boundary not digitized" note.**~~ Done 2026-05-04 — `#d-acreage-note` renders an inline italic note when `s.program === "fuds" && s.acreage == null` so users know the 5,832 missing-acreage FUDS records are a USACE digitization gap, not missing data on our side. Hidden for FUDS-with-acreage and for non-FUDS programs.
- ~~**[med] FUDS `current_owner` raw-code cleanup.**~~ Done 2026-05-04 — `connectors/dod_fuds.py:_pretty_owner()` maps the six tier prefixes (PRIV/LOCAL/FED/STATE/TRIBE/OTHER) to clean labels at normalize time. 7,573 records get readable owner strings ("Private", "Federal — Air Force", "Local government — City") instead of the raw `"PRIV: PRIVATE   "` syntax. Multi-tier entries joined with " / "; agency acronyms (USFS / BLM / NPS / etc.) preserved through title-casing.
- ~~**[low] Remove unused `proximity` field from `schema.py`.**~~ Done 2026-05-04 — the v1.7-era catch-all dict, fully superseded by `transmission_mi` / `rail_mi` / `highway_mi` in v1.10. Schema's `extra="forbid"` now actively rejects the legacy field name (regression-tested in `test_legacy_proximity_field_rejected`).

Still open from the audit:

- **[high] ACRES acreage gap (0/36,003 populated, 100% missing).** No path opened. Action: email `helpdesk@acrebs.epa.gov` for a bulk PPF extract OR fund a one-shot Regrid / Landgrid Parcel API enrichment ($36–$360 estimated). Until then the KPI deck acreage total excludes all 36k brownfields.
- **[med] Out-of-CONUS infra placeholder.** 395 FUDS (AK / Pacific) and 142 ACRES (AK) records have blank dashes in the detail-panel infra rows because `MAX_DISTANCE_MI=100` correctly drops them. Recommended a `"Remote — outside continental US"` placeholder. Defer until either the AK-specific HIFLD/DOT&PF layers ship as a fourth `infra_proximity` source or a user complains.

---

## ~~v1.10 — Universal infrastructure-proximity (2026-05-04)~~ Done

The data-center thesis depth play. Until v1.10 only the ~1,905 Superfund sites enriched by `epa-redev` carried infrastructure-proximity context (transmission / highway / rail / water). v1.10 lights up the same context — at higher precision (mile-level distance, not bucketed labels) — across all ~47k records.

- ~~**[high] Universal HIFLD + Census TIGER infrastructure-proximity enrichment.**~~ Done 2026-05-04 — new `connectors/infra_proximity.py`. Reads every per-program JSON (Superfund / ACRES / FUDS / BRAC), fetches three public layers (HIFLD `Electric_Power_Transmission_Lines` ~52k polylines, Census TIGERweb Primary Roads `MTFCC='S1100'` ~17.6k features, Census TIGERweb Railroads ~111k features), computes nearest-segment distance via a pure-Python spatial grid index (`connectors/spatial.py`), emits `docs/data/infra-proximity.json` keyed by `id`. ~98% coverage on transmission alone; near-100% with rail+highway combined. Distances >100 mi dropped (out-of-CONUS / remote AK).
- ~~**[high] Pure-Python spatial grid index.**~~ Done 2026-05-04 — `connectors/spatial.py:SegmentIndex` buckets polyline segments into 0.25°-cell grid; query expands outward in Chebyshev rings with an early-exit when the best distance is shorter than the inner edge of the next ring. Local equirectangular projection (cos(lat) at the query point) for distance math. No shapely/rtree dependency — keeps the project's runtime requirements at `requests + pydantic`.
- ~~**[high] Connector `run_order` for enrichment dependency ordering.**~~ Done 2026-05-04 — `Connector.run_order` (default 100) lets enrichment connectors that read other connectors' per-program JSON files run after their producers in `refresh.py --all`. Bumped `epa-superfund-docs` to 200 (was running before `superfund-npl` finished — latent bug from v1.9), `infra-proximity` to 300.
- ~~**[high] Detail-panel cross-program infra rows.**~~ Done 2026-05-04 — three new rows in `#d-infra-block`: "Transmission line" / "Rail line" / "Highway", each rendering "X.X mi" via the new `fmt.miles` helper and `setMileCell` (which swaps the `muted-cell` class so populated values look like real data, not placeholder). The legacy EPA RE-Powering qualitative rows sit below the new rows for the ~1.9k Superfund sites where they're populated; the labels are now explicit so users don't confuse the two data lineages.

Demoted from this pass — call out for future work:

- **[high] Substations (HIFLD electric power substations).** Searched 2026-05-04: the canonical national HIFLD substations endpoint at `services.arcgis.com/G4S1dGvn7PIgYd6Y/.../HIFLD_electric_power_substations` is regional-only (NJ/PA, 128 features). The other "HIFLD Electric Substations" endpoints either return empty metadata or are auth-walled. Action: identify a stable national source (OpenStreetMap power=substation extracts via OpenInfraMap is the obvious commercial-free fallback) and add as a fourth layer to `infra_proximity`. Defer to v1.11.
- **[high] Available transmission capacity (FERC Form 715 / OASIS / ISO interconnection queue).** "Distance to nearest wire" is necessary but not sufficient — hyperscalers care about MW available. Per-ISO interconnection queues (PJM/MISO/CAISO/ERCOT/SPP/NYISO/ISO-NE) are publishable as the next layer. Each ISO has its own format; will need per-ISO normalization. Defer until v1.11.
- **[med] Water-body proximity (NHD).** `epa-redev` carries `near_water_supply` qualitatively. Universal water-body proximity would unlock cooling-availability filters across all programs. NHD HighRes is enormous (millions of features); a viable cut is "Major Rivers + Reservoirs" only. Defer.
- **[med] Fiber proximity / colo presence.** No clean public dataset. Best near-term proxy: distance to nearest long-haul fiber landing point + presence of a colocation facility within 50mi (Data Center Map, paid).
- ~~**[low] Per-record reasoning for the data-center candidate flag.**~~ Done 2026-05-06 (v1.11.4) — detail panel's "Data center candidate" `<dd>` carries an italicized `.dd-criteria` sub-line (`≥50 acres · electric transmission · water service area`) that shows when the boolean is `true` and stays hidden otherwise. The rule today is the qualitative EPA RE-Powering buckets (`near_electric_transmission` + `near_water_supply` start with "Yes", `acreage ≥ 50`); a future swap to mileage thresholds against the universal `transmission_mi` / water-body data would change only the criteria string.

---

## ~~v1.9 — Federal acreage / ownership / documents (2026-05-03)~~ Done

Three federal-data enrichments landed in one pass:

- ~~**[high] FUDS polygon-layer acreage swap.**~~ Done 2026-05-03 — `connectors/dod_fuds.py` now joins layer 1 (~10k points) with layer 4 (~3k polygons) by `DODFUDSPROPERTYIDPK`. Acreage computed via Shoelace + cos(lat) (`connectors.geom.polygon_acreage`); polygon-centroid lat/lon used when available. ~3k previously-null FUDS records gained acreage. Largest sites (e.g. 8M acre Northwest Maneuver Area, OR) verified against historical USACE records. Same property's multi-parcel polygons get rings concatenated before area calc so we sum across fragments.
- ~~**[high] EPA Superfund federal documents enrichment.**~~ Done 2026-05-03 — new `connectors/epa_superfund_docs.py`. Three-hop walk: EPA pretty page → SF_SITE_ID (extracted via regex, since EPA_ID and SF_SITE_ID are unrelated and there's no public cross-walk), → cumulis docdata HTML → curated collection IDs (Key Documents, SPP Decision Documents, SPP Public Available Documents, SPP Technical Reports and Studies, SPP Enforcement and Settlement Documents — Administrative Records skipped as low-signal docket dumps), → `semspub.epa.gov/src/cachejson/<region>/<type>/<colid>` JSON for the document records. Output: `docs/data/epa-superfund-docs.json` with `[{epa_id, documents: [...]}]`, joined client-side by `ensureSuperfundDocsLoaded()`. Resumable batched coverage via `--docs-limit N --docs-skip M`.
- ~~**[high] Owner provenance citation.**~~ Done 2026-05-03 — schema gains `current_owner_source: str | None`. FUDS records that already carried `CURRENTOWNER` now also carry `current_owner_source: "USACE FUDS"` so the detail panel can show "Current owner: …" + a separate "Owner source: USACE FUDS" row. Future ACRES PPF / Regrid integrations should set their own label.
- ~~**[high] Detail panel: Federal documents block.**~~ Done 2026-05-03 — `renderDocuments(s)` in `app.js` shows up to N most-recent documents (title → semspub link, date · category, page count, file size). Hidden when no documents are present. "All site documents on EPA →" deep-link points at the canonical cumulis docdata page so users can pivot to full coverage even on un-enriched sites.
- ~~**[high] Shared polygon math module.**~~ Done 2026-05-03 — `connectors/geom.py` exposes `polygon_area_sq_meters`, `polygon_acreage`, `envelope_center`. BRAC + FUDS both use it. BRAC re-exports as static methods for back-compat with existing tests.

Demoted from this pass — call out for future work:

- **[med] ACRES PPF (Property Profile) acreage + owner.** Researched 2026-05-03; the public-facing PPF URL `acres6.epa.gov/acres/cms/PropertyProfileReports/Output/<PROPERTY_ID>.html` redirects to EPA's WAM SSO (Oracle OAM) — login-only. The backlog note that called this a scrape is outdated. Two real paths now: (a) email helpdesk@acrebs.epa.gov for a bulk extract of the PPF table; (b) commercial fallback via Regrid / Landgrid Parcel API. Defer until either path is funded.
- **[med] Other federal "related articles" sources beyond EPA SEMS.** Federal Register notices by docket, EPA News Releases tagged by site, GAO reports, OIG reports. Lower volume per site than SEMS; defer until SEMS coverage is at 100% of Final/Deleted NPL.
- **[med] BRAC parcel-level transfer history (Navy/Army/AF PDFs).** Still the only public path for BRAC parcel-level deed/conveyance status, and still a multi-week per-Service scrape. Defer.

---

## ~~v1.8 — Editorial design refresh (2026-04-30)~~ Done

Visual rebuild driven by datacenterbans.com / FT / NYT data-journalism reference points. All shipped in one pass:

- ~~**[high] Editorial type system.**~~ Done 2026-04-30 — system-serif display stack (`Charter` → `Source Serif 4` → fallbacks; no web-font fetch), tabular-numerals everywhere, refined size scale (h1 20px serif, body 14px sans, micro 11px tracked).
- ~~**[high] Refined palette.**~~ Done 2026-04-30 — `--accent` moved from Microsoft-blue `#1f6fcf` to deeper navy `#1c5e9e`. Surfaces warmed (`--bg: #f1f2f4`), `--bg-elev` introduced for hero/footer chrome. Dark-mode `--accent` lifted to `#7eb6e8` for AA contrast. Program palette desaturated to feel "policy editorial" not "marketing SaaS".
- ~~**[high] Hero strip + KPI deck.**~~ Done 2026-04-30 — slim editorial intro between topbar and filters: eyebrow (`US Brownfield Atlas · v1.8 · Updated YYYY-MM-DD`), serif H2 headline, dek, plus a 4-cell KPI deck (`#kpi-total`, `#kpi-acres`, `#kpi-dc`, `#kpi-states`) computed from in-memory `sites` (no extra fetches). Hero copy hides on mobile so the map keeps its real estate; KPI deck becomes a horizontal scroll-snap carousel.
- ~~**[high] Footer with sources.**~~ Done 2026-04-30 — `<footer class="site-footer">` cites all five data sources (EPA Superfund, EPA ACRES, USACE FUDS, DOD BRAC, EPA RE-Powering) plus refresh date and a GitHub link. Single hairline divider above; no marketing chrome.
- ~~**[high] Filter chip count on gear button.**~~ Done 2026-04-30 — `#filters-chip` shows a small badge with the active-filter count. Hides itself when no filters are applied (with the `[hidden] { display: none }` rule that the legacy `display: inline-flex` was overriding — see UAT-001).
- ~~**[high] Detail panel polish.**~~ Done 2026-04-30 — 4px program-color top stripe (set inline as `--detail-stripe` CSS var by `selectSite()`), serif H2, tighter `kv` grid, "DC candidate" pill next to the program pill when the redev enrichment flagged the site.
- ~~**[high] Tighter map legend.**~~ Done 2026-04-30 — flat card (no backdrop-blur, which was recompositing on every pan/zoom frame), per-program counts on the right edge as tabular numerals.
- ~~**[high] Place-name prettifier.**~~ Done 2026-04-30 — `prettyPlace()` title-cases `s.city`, `s.county`, `s.address` at ingest time. Source preserved on `s.{city,county,address}_raw`. Closed the long-standing "City column shouts in ALL CAPS" issue without re-running connectors. Sentinels (`-- Not Defined --`, `_NULL_`) collapse to `null`.
- ~~**[high] Accurate per-program meta text.**~~ Done 2026-04-30 — `updateMetaText()` reads per-program counts from `sites` instead of the hardcoded "X Superfund + Y brownfields" template that mislabeled the breakdown after FUDS/BRAC also lazy-loaded.
- ~~**[high] Sort glyph on table headers.**~~ Done 2026-04-30 — active sort column gets a ▲/▼ glyph via `data-sort-glyph` attr + `[aria-sort]::after` rule.
- ~~**[high] Tablet column-stacking for hero.**~~ Done 2026-04-30 — `<1024px` collapses the two-column hero (copy + KPI deck) to one column.

Demoted from this pass — call out for future work:

- **[med] Site name prettifier.** Names are still ALL CAPS ("FOX RIVER NRDA/PCB RELEASES"). Title-casing risks mangling acronyms (NRDA, PCB, USDOE, AAP). Defer until we have a per-source whitelist or a stronger heuristic.
- **[med] Portrait-orientation map crop.** On mobile portrait, fitBounds over US_BOUNDS (wider than tall) shows only the eastern US; West Coast clips off the right. Tighten bounds when `width/height < 0.8`, or switch to a slightly wider `dst` window for the lower-48.
- **[low] Footer: per-source row counts.** "EPA Superfund (1,908) · ACRES (36,003) · FUDS (8,821) · BRAC (27)" would let users see which dataset they're looking at without opening the legend. Risk: footer height grows on mobile.

---

## ~~Top priority — Federal-site expansion + EPA data-center reuse layer~~ Done 2026-04-29 (v1.7)

Three coordinated additions landed as a themed release:

- ~~**[high] DOD BRAC (Base Realignment and Closure).**~~ Done 2026-04-29 — `connectors/dod_brac.py` pulls 27 BRAC-flagged installations from ESRI milbases FeatureServer (`BRAC_SITE='YES'`). Polygon geometry → acreage via Shoelace formula. New `program: "brac"`, orange markers, lazy-loaded from `docs/data/dod-brac.json`.
- ~~**[high] DOD FUDS (Formerly Used Defense Sites).**~~ Done 2026-04-29 — `connectors/dod_fuds.py` pulls ~10k properties from USACE FUDS FeatureServer (services7.arcgis.com). New `program: "fuds"`, purple markers, lazy-loaded from `docs/data/dod-fuds.json`. Fields: eligibility, fuds_status, has_projects, current_owner.
- ~~**[high] EPA Superfund data-center reuse layer.**~~ Done 2026-04-29 — `connectors/epa_redev.py` enriches existing Superfund records from the RedevelopmentAppSitePoints FeatureServer (1,905 sites). Adds infrastructure-proximity fields (transmission, highway, railroad, water supply, wastewater, pop density, opportunity zone, reuse status) and computes `data_center_reuse_candidate: bool` (power + ≥50ac + water). 828/1,905 flagged as DC candidates. Detail panel shows all infrastructure fields.

Phase 2 (other federal-land contamination universes):

- **[med] BLM Abandoned Mine Lands (AML).** ~50,000+ sites on BLM-managed land — heavy metals, acid mine drainage, occasional uranium. Mostly small, remote, off-grid → low per-site data-center value, but aggregated they tell the "post-industrial West" story and a handful are real redevelopment targets (e.g. Iron Mountain Mine CA, Berkeley Pit MT — both also NPL). Source: BLM AML Inventory ArcGIS hub (`gis.blm.gov/AMLPublic/`). New connector + `program: "blm-aml"`. Cross-reference against Superfund EPA_IDs to avoid double-counting.
- **[med] DOI orphan oil & gas wells.** IIJA-funded plugging program publishes a federal-lands orphan-well inventory; states publish their own (Pennsylvania alone has ~27k documented). Most are tiny point features with low individual signal but enormous count, and they cluster meaningfully in Appalachia, the Permian, and the Bakken. Source: DOI Orphaned Wells Program data + state O&G commission feeds. New connector + `program: "orphan-wells"`. Consider clustering visually rather than per-site markers given the volume.

---

## v1 follow-ups (data completeness)

- ~~**[high] Expand beyond top-100.**~~ Done 2026-04-27 — all 1,908 unique NPL sites now load (~1.6MB JSON, ~200KB gzipped). Connector handles pagination through the FeatureServer's 2000-record cap.
- ~~**[high] Sites without acreage.**~~ Done 2026-04-27 — `--include-no-acreage` (default on) keeps non-areal features with `acreage: null`. Frontend renders "N/A" and uses a small marker.
- ~~**[high] EPA Brownfields (ACRES).**~~ Done 2026-04-27 — 36,003 ACRES properties now ship as a separate `docs/data/epa-acres.json` (~1.5MB gzipped). The frontend lazy-loads it when the user picks "Brownfield (ACRES)" in the program filter so first paint stays at ~170KB. Source: `All ACRES Properties 8_30_2021` ArcGIS FeatureServer hosted by EPA. The Envirofacts `BF_*` tables (`BF_PROPERTY`, `BF_GRANT_RECIPIENT`, etc.) returned "table not available" — see `issues.md` 2026-04-27.
- **[med] State environmental agency sites.** Each state has its own brownfield/voluntary cleanup program (NY State Superfund, CA DTSC EnviroStor, TX VCP, etc.). Now trivial to aggregate — one connector per source.
- **[med] RCRA Corrective Action sites.** EPA Resource Conservation and Recovery Act sites under corrective action — another large universe of contaminated industrial properties.
- **[med] State-sharded JSON.** With ACRES landed (~1.5MB gz) the lazy-load pattern handles it. Defer further sharding until per-state filtering becomes a perf bottleneck.
- **[high] ACRES dataset is from 2021.** EPA's ArcGIS hub publishes annual snapshots; a newer `All_ACRES_Properties_*` service may exist. Audit and pin to the most recent stable release. (Tracked in `issues.md`.)
- **[med] ACRES enrichment from `ACRES_assessments_*` and `ACRES_cleanups_*` layers.** Carries Award_Type, CA_Status, Assessment_Completion_Date, Cleanup_Completion_Date — would let us show real status pills for brownfields instead of just the program label.

## Site-level enrichment (Owner / encumbrances / history)

- **[high] Acreage + ownership/transfer/leasing source map.** Researched 2026-04-30 — for each program, here's where the data actually lives. Most are scrapes, not feeds.

  **Acreage** (gap-fill where the connector returns null today):
  - **Superfund** — already populated from polygon source. ~13% remain null because EPA codes them as `Miles` (linear features) or `null` (point features). Defer; not a real gap.
  - **EPA ACRES** (~36k, *all* null today) — public FeatureServer has zero acreage. ~~Two paths: (a) scrape per-property profile HTML at the PPF URL; (b) ACRES Help Desk bulk extract.~~ **Re-evaluated 2026-05-03 (v1.9)**: path (a) is dead — `acres6.epa.gov/acres/cms/PropertyProfileReports/Output/<PROPERTY_ID>.html` redirects to EPA WAM SSO (`wamssoprd.epa.gov/oam/...`), login-only. Only viable paths left: (a) email helpdesk@acrebs.epa.gov for a bulk PPF extract (one-shot, email turnaround); (b) commercial parcel-API fallback (Regrid / Landgrid). Defer until funded.
  - ~~**DOD FUDS** (~10k, all null today)~~ — **Done 2026-05-03 (v1.9)**. Layer-4 polygon join lights up acreage for ~3k records (~30% — layer 4 only covers properties with digitized boundaries). Layer 1 stays the master list; layer 4 contributes acreage + polygon centroid where present. Implementation note: source `Shape__Area` is in degrees², not m² — `connectors/geom.py:polygon_acreage` does the cos(lat) projection.
  - **DOD BRAC** — already computed via Shoelace from the milbases polygon source.

  **Current owner**:
  - **Superfund** — not in EPA data. EPA SEMS tracks PRPs (Potentially Responsible Parties), not record-title owners; PRP ≠ owner. Cross-walk to parcel data via address.
  - **EPA ACRES** — PPF page (same source as acreage above) has a `Property Ownership` block: current owner name + indicator of public/private/non-profit.
  - **DOD FUDS** — already capturing `CURRENTOWNER` (e.g. "Private", "State of California", or specific entity). Coarse but populated.
  - **DOD BRAC** — installation-level only on the milbases service; for parcel-level (each base has 5–500 parcels with different transfer status), see transfer-status item below.
  - **Cross-program commercial fallback**: [Regrid / Landgrid Parcel API](https://regrid.com/api) — ~3,000 US counties, daily ownership refresh on the Enhanced Ownership add-on. Quote-based pricing (parcels@landgrid.com). Geocode our `address` → APN → owner. ReportAll USA is the close competitor. Both are ~$0.001–0.01/parcel-lookup territory; one-time enrichment of all ~47k records is a few hundred dollars but locks us into a vendor for refreshes.

  **Transfer / leasing / deed status** (the BRAC + federal-property axis):
  - **DOD BRAC parcel-level transfer status** — each Service publishes its own:
    - Navy: [bracpmo.navy.mil](https://www.bracpmo.navy.mil/) per-base "Closure History, Property Transfer Summary & Remaining Transferred" pages. PDF tables of LIFOC / EDC / PBC / quitclaim deed by parcel, updated quarterly. Scrape per-base (27 BRAC sites; ~50 Navy bases historically).
    - Army: [Army Environmental Command BRAC](https://aec.army.mil/index.php/cleanup/brac) — quarterly "BRAC Property Disposal Report" PDFs.
    - Air Force: [AFCEC BRAC](https://www.afcec.af.mil/) Real Property Transactions PDFs.
    - No structured public feed exists. Roll-your-own: per-base scrape → normalize to `{parcel_id, transfer_type, transfer_date, grantee, deed_url}`. Heavy lift but the only public path; would convert BRAC from 27 dots to the actual ~500–1000 parcel records that drive deals.
  - **Conveyance type taxonomy** (worth baking into schema): `LIFOC` (lease in furtherance of conveyance — interim control before deed), `EDC` (Economic Development Conveyance — at-cost or profit-sharing), `PBC` (Public Benefit Conveyance — discounted to eligible entity), `Negotiated Sale`, `Public Sale`, `Quitclaim Deed`, `Federal-to-Federal Transfer`. See [DON BRAC implementation guidance (2022)](https://media.defense.gov/2022/Jun/08/2003014188/-1/-1/0/DON_BRAC_IMPLEMENTATION_GUDANCE.PDF) for definitions.
  - **DOD FUDS real-estate instruments** — USACE Real Estate (CEFMS / IRP databases) tracks deeds, easements, and licenses per FUDS property. Not in the public FeatureServer; FOIA-only. Defer.
  - **Federal civilian real property** ([GSA FRPP Public Dataset](https://catalog.data.gov/dataset/fy-2024-federal-real-property-profile-frpp-public-dataset)) — annual XLSX (no REST API) of all federal civilian real estate by agency: ownership status (`Owned` / `Leased` / `Other`), use code, square footage. **DOD assets excluded for security** — the DOD file is installation-level summaries only, not parcel-level. So this *won't* help BRAC/FUDS at parcel resolution but *will* help when we add federal civilian contaminated sites (DOE legacy, NRC, GSA-controlled). Contact: `publicfrppdata@gsa.gov`. Active listings (for-sale federal properties): `realestatesales.gov` — HTML-only, no API. Confirmed limitations 2026-05-05.
  - **Superfund Institutional Controls** — EPA's [ICTS](https://www.epa.gov/superfund/superfund-institutional-controls) lists IC instruments (deed restrictions, environmental easements) for cleanup sites. Public site has search-only UI; bulk data via FOIA or scrape.

  **Suggested phasing**: ship the FUDS polygon-layer acreage swap first (one-connector edit, lights up ~10k records), then ACRES PPF scrape for acreage + owner (rate-limited overnight job, lights up ~36k records), then BRAC parcel-level transfer-status scrape (per-Service, multi-week effort). Defer FOIA paths and paid parcel APIs until a paying customer needs the depth.

- **[high] Current owner.** Not in EPA data. Source options:
  - County recorder offices (per-county scraping; messy, no standard schema)
  - **ReportAll USA / Regrid / Loveland Tech** — paid parcel APIs covering ~3,000 US counties
  - State assessor open data (varies wildly)
  - Strategy: start with a single high-value state (e.g. NJ — has a free statewide parcel layer)
  - *See "source map" item above for per-program detail.*
- **[high] Historical owners.** County deed history. Same access constraints as above; some title-search vendors expose APIs.
- **[high] Encumbrances.** Liens, easements, environmental covenants (institutional controls). EPA's *Superfund Institutional Controls Tracking System (ICTS)* publishes some of this; needs investigation.
- **[med] Remediation detail.** Current site only carries NPL status code. Add: Record of Decision (ROD) summary, current cleanup phase, remedy type, lead party (PRP/EPA/state), Five-Year Review status. EPA SEMS has these in adjacent tables.
- **[low] Site-specific contamination profile.** Contaminants of concern, media affected (groundwater/soil/sediment), exposure pathways. SEMS has it.

## Development Readiness — identifying sites available for development (researched 2026-05-04)

The core question for any acquirer: **which sites can actually be developed, and on what timeline?** A site that's been cleaned up and transferred to a private owner is a fundamentally different opportunity than one still mid-remediation or locked in federal title. Today the dashboard has no way to answer this — NPL status "D" (Deleted) is the closest proxy but it's Superfund-only, not surfaced as a badge, and doesn't capture the other 40k+ non-Superfund records. This section maps every public signal for development readiness and proposes a phased connector + UI build-out.

### Signal taxonomy (strongest → weakest)

**Tier 1 — "Available now": cleanup complete, land transactable**

- **NPL Deletion (status "D")** — already in our data (`s.status === "D"`). ~300 of 1,908 NPL sites are Deleted = EPA formally certifies cleanup meets health/environmental standards. Strongest Superfund signal. Zero new fetches required — just a badge and filter.
- **ACRES cleanup completion** — `ACRES_cleanups_*` FeatureServer layer (same endpoint as the existing ACRES connector) carries `CA_Status = "Completed"` + `Cleanup_Completion_Date`. Not yet fetched. Applies to some fraction of the 36,003 ACRES records.
- **FUDS transferred out of federal title** — `current_owner` already partially populated. FUDS records where `current_owner` is `PRIV:*` / `STATE:*` / `LOCAL:*` and USACE has formally conveyed title have completed the remediation → disposition pipeline. These are in private-developer territory. Cross-reference `fuds_status = "Eligible"` + non-federal owner as the proxy; no new fetch needed for an initial filter.
- **BRAC conveyance complete (quitclaim deed)** — no structured feed exists; still in PDF territory (see `bracpmo.navy.mil` per-base pages). All 27 BRAC sites have partial or full deed transfers underway; some are 100% transferred (e.g., former El Toro MCAS → Great Park Irvine). Defer to the BRAC parcel-level scrape already in backlog.

**Tier 2 — "Coming soon": cleanup nearly done, land coming onto market**

- **"Construction Complete" (CC) milestone** — SEMS milestone date: cleanup work is physically done, deletion paperwork underway. Typically 1–5 years before formal NPL Deletion. Source: **cumulis.epa.gov schedule page** (`fuseaction=second.schedule&id=<SF_SITE_ID>`) — confirmed as the only public surface for CC date, SWRAU date, and all FYR dates. `sems.epa.gov/rest/` is dead (connection refused); Envirofacts `sems.*` tables HTTP 500 in practice. One additional HTTP request per site after the SF_SITE_ID hop that `epa_superfund_docs.py` already does. New `epa_sems_milestones.py` enrichment connector; set `run_order = 210` (after `epa-acres`, before `epa-echo`).
- **"Ready for Anticipated Use" (RAU)** — EPA's per-Operable-Unit formal determination that the site can support its planned future use. A site can be RAU while still on the NPL (e.g., if cleanup continues in one corner but the main parcel is cleared). RAU date published in SEMS and in the EPA site-profile Redevelopment tab. More granular than NPL Deletion — distinguishes partial vs. whole-site readiness.
- **BRAC LIFOC (Lease in Furtherance of Conveyance)** — federal government leases land to a developer while cleanup finishes; deed transfer on completion. Developer can start site planning and sometimes vertical construction. Lease start date = actionable now for sophisticated acquirers. Source: same per-Service PDF scrape as the full BRAC item.
- **ACRES assessment complete, cleanup not started** — brownfields where environmental assessment is done (contamination scope known, cost estimate in hand) but cleanup hasn't started. These are "developer-fundable cleanups" — the acquirer funds remediation as part of the deal. `ACRES_assessments_*` layer `Assessment_Completion_Date` populated + no `Cleanup_Completion_Date` = this tier.

**Tier 3 — "Long pipeline": cleanup ongoing or not yet scoped**

- **FUDS "Eligible" + `has_projects = true`** — USACE is actively investigating or cleaning. Timeline unclear but progressing. At 8,822 FUDS records with 2,874 having active projects, this is a large pipeline pool.
- **NPL status "F" (Final, active)** — on the NPL, cleanup underway. Wide range from years-to-completion to decades.
- **NPL status "P" (Proposed)** — newly proposed, cleanup not yet started.

### Anticipated future land use — what the site will be used for when ready

- **EPA SEMS AFL (Anticipated Future Land Use) code** — per-site code set by EPA project manager: `Industrial/Commercial`, `Recreational/Open Space`, `Residential`, `Unknown`. **AFL codes are not in any public API or FeatureServer** (confirmed 2026-05-05 — not in `RedevelopmentAppSitePoints`, not in `envirofacts_site`, not in cumulis HTML). SEMS-internal field, FOIA-only. Drop from `epa_sems_milestones.py` scope; remove from `anticipated_land_use` schema field. The cumulis schedule page does not carry AFL. If AFL data is ever needed, file a FOIA request for a SEMS bulk export.
- **EPA site profile Redevelopment tab** — scrape per-site at `https://www.epa.gov/superfund/[slug]` (same `http_get_text` + regex pattern as `epa_superfund_docs`). The Redevelopment tab exposes:
  - Anticipated Future Land Use description (more human-readable than the code)
  - **Site Reuse Accomplishments**: named reuse projects (e.g. "Solar farm installed 2019", "Mixed-use development – 450 units, 2022"), completion date, reuse type (industrial, residential, greenspace, renewable energy)
  - **RAU date per Operable Unit** (sometimes not in SEMS REST — the HTML page is the authoritative surface)
  - Links to redevelopment fact sheets (EPA publishes one-pagers on major reuse successes)
  - Active Institutional Controls listed (deed restriction text; link to IC instrument)
  - Five-Year Review status (passing/failing protectiveness determination)
  This is the single richest public source for Superfund readiness data. No structured API — HTML scrape only. Same rate-limit / cache / `http_get_text` pattern as `epa_superfund_docs`; target ~1,400 Final + Deleted NPL sites with known `profile_url` fields. At 1.5s/request + ~2–3 HTTP hops per site, full run ≈ 1–2 hours.
- **ACRES `Reuse_Type` field** — if present in `ACRES_cleanups_*` or `ACRES_assessments_*` layers (needs investigation). ACRES grant awards are tied to specific end-use categories (affordable housing, commercial, industrial, greenspace, recreation).
- **BRAC Local Redevelopment Authority (LRA) reuse plan** — each BRAC installation has a named LRA that filed a legally binding Reuse Plan with the DoD. Plans are public record. Too diverse in format for automated scraping; would need to be manually curated for the 27 BRAC sites (feasible one-time effort given the small count).

### Data sources — what needs to be built

- **[high] ACRES cleanups layer join for readiness tier.** Elevating the existing "[med] ACRES enrichment from `ACRES_cleanups_*` layers" item to high priority given its direct bearing on development readiness. Endpoint: same ACRES FeatureServer, different layer ID. Fields to harvest: `CA_Status` (Completed / In Progress / Not Started), `Cleanup_Completion_Date`, `Cleanup_Type`. Join to existing ACRES records by `PROPERTY_ID`. New `epa_acres_cleanup.py` enrichment connector; `run_order = 200` (after `epa-acres`). Lights up readiness tier for up to 36k brownfields at no additional data cost.

- **[high] cumulis schedule page scrape for Superfund milestones.** `sems.epa.gov/rest/` is dead; Envirofacts `sems.*` HTTP 500 in practice — confirmed 2026-05-05. The only public structured surface for CC date, SWRAU date, and FYR dates is the cumulis schedule page: `https://cumulis.epa.gov/supercpad/SiteProfiles/index.cfm?fuseaction=second.schedule&id=<SF_SITE_ID>`. New `epa_sems_milestones.py` enrichment connector (`run_order = 210`): reuse the SF_SITE_ID extraction hop that `epa_superfund_docs.py` already does (or share the mapping if that connector has cached it), then one `http_get_text` call per site and regex-extract the milestone table rows. Emits `docs/data/sems-milestones.json` with `[{epa_id, construction_complete_date, swrau_date, fyr_dates: [...]}]`. Join client-side in `ensureSemsLoaded()`. Drop AFL code from scope — it's not publicly available. Resumable via `--milestones-limit N --milestones-status F,D`.

- **[high] cumulis redevelopment tab scrape for reuse data.** Confirmed URL: `https://cumulis.epa.gov/supercpad/SiteProfiles/index.cfm?fuseaction=second.redevelop&id=<SF_SITE_ID>` (not at `epa.gov/superfund/[slug]` — the EPA pretty page just links through to cumulis). Carries: businesses on site, economic summary, reuse description (sparse, often just a paragraph). A separate `epa_superfund_redev.py` connector (`run_order = 215`); cache by `(epa_id, "redevelop_tab")`. Drop AFL description from scope — it's only in the SEMS-internal AFL code field, not on any public page. Output: `docs/data/epa-redev-tab.json` with `[{epa_id, in_reuse: bool, reuse_description: str, reuse_businesses: int, reuse_revenue_usd: int}]`. The `In_Reuse` boolean is already in `RedevelopmentAppSitePoints` (field `In_Reuse = "Yes"/"No"`) — surface that zero-fetch quick win first before building the scrape.

- **[med] FUDS current_owner normalization to readiness proxy.** The `current_owner` raw-code normalization already in backlog ("`PRIV:*` → `"Private"`") is a prerequisite. Once normalized, a FUDS record with a non-federal owner + `fuds_status = "Eligible"` (meaning remediation obligations met) maps cleanly to Tier 1. No new fetches — just use existing `current_owner` once the normalization ships.

- **[low] BRAC LRA reuse plan manual curation.** 27 BRAC sites is small enough to hand-curate: for each site, look up the LRA name, reuse plan headline (e.g., "Great Park Irvine — mixed-use / recreation"), and percent acreage transferred (from `bracpmo.navy.mil`). Store as a static lookup in `connectors/dod_brac.py` (similar to how `NPL_STATUS_LABELS` works for Superfund). Zero ongoing maintenance needed — BRAC is a closed list.

### New sources researched 2026-05-05

- **[high] Federal Register API — NPL deletion + BRAC conveyance signals.** Confirmed public JSON API; no auth. `https://www.federalregister.gov/api/v1/documents.json?conditions[term]=national+priorities+list+deletion&conditions[type][]=RULE` returns NPL deletion final rules with `publication_date`, `title`, and `abstract`. Every NPL site that exits the program gets a final rule published here — this is a stronger and earlier signal than polling `npl_status_code` via the ArcGIS FeatureServer (which can lag by months). BRAC surplus conveyance notices appear under `conditions[agencies][]=department-of-defense&conditions[term]=surplus+property+conveyance`. Pattern: weekly incremental fetch → extract EPA_ID from document title/abstract via regex → set `fr_deletion_date` on matching `sitesById` records → join client-side. New `fed_register.py` enrichment connector; `run_order = 300`. Emits `docs/data/fed-register.json` with `[{epa_id, deletion_date, fr_document_number, fr_url}]`.

- ~~**[high] `In_Reuse` flag quick win (zero new fetches).**~~ Done 2026-05-05 — `epa_redev.py` already populated `in_reuse` on the schema (string "Yes"/"No" rather than bool — kept as-is, the source ships occasional non-`Yes`/`No` values like blank strings). `selectSite()` now renders an `Active Reuse` pill (green outline, `--readiness-ready` token) next to the program pill when `s.in_reuse` matches `/^yes/i`. Regression test: `test_active_reuse_pill_for_in_reuse_site` + `test_no_reuse_pill_when_in_reuse_no`.

- **[med] NY State BCP Certificates of Completion connector.** The NY Brownfield Cleanup Program publishes a machine-readable Socrata dataset of all sites that completed remediation and received a Certificate of Completion — the strongest possible "cleanup complete + reuse ready" signal for NY state brownfields. These are a completely separate universe from EPA ACRES (state VCP, not federal). Dataset: `https://data.ny.gov/resource/ir93-7qzi.json` (SODA API, no auth, CSV/JSON/GeoJSON downloads). Fields: site ID, site name, locality, acreage, year certificate issued. ~500+ records. New `ny_bcp.py` connector; `program: "ny-bcp"`, `run_order = 100`. Cross-reference by lat/lon against existing ACRES records (`ACRES-*` IDs) to detect overlapping sites. First state-level connector; proves out the pattern for CA EnviroStor, NJ HDSRF, TX TCEQ when those publish machine-readable endpoints.

- **[low] Chicago City-Owned Land Inventory crosswalk.** Socrata dataset: `https://data.cityofchicago.org/resource/aksk-kvfp.json` (~10k city-owned parcels on the South/West sides). No environmental-status field, but spatial crosswalk against existing ACRES/FUDS markers (±0.001° lat/lon) would flag which brownfields are still on city rolls vs. transferred. The city's ChiBlockBuilder portal makes these available for acquisition. Worth a `chicago_land.py` enrichment connector only if we expand to city-surplus tracking generally; lower priority than the FR API or NY BCP.

- **[dead end confirmed] AFL (Anticipated Future Land Use) codes.** Searched all public EPA APIs and FeatureServers 2026-05-05. Not in `RedevelopmentAppSitePoints`, not in `envirofacts_site`, not in the cumulis schedule or redevelopment HTML pages. SEMS-internal field that EPA project managers enter via the SEMS UI but never expose externally. Remove `anticipated_land_use` from the `SiteRecord` schema additions planned above — there is no public data source to populate it. If AFL is ever needed, file a FOIA request for a SEMS bulk export.

- **[dead end confirmed] SEMS REST API (`sems.epa.gov/rest/`).** Connection refused on all attempts. Envirofacts `data.epa.gov/efservice/sems.*` tables are documented but HTTP 500 in practice. The authoritative programmatic path for milestone dates is the cumulis schedule page scrape (see `epa_sems_milestones.py` item above). Update any backlog items that reference `sems.epa.gov/rest/` to use the cumulis path instead.

- **[dead end confirmed] DERA/DERP and USACE FUDS deed records.** Defense Environmental Restoration Account (DERA) only publishes program-level funding summaries as PDFs — no site-level transfer records. USACE Real Estate division publishes Finding of Suitability to Transfer (FOST) documents as PDFs on individual district websites (e.g. Sacramento District, Wilmington District), but there is no central index or feed and scraping 38+ district sites is fragile. The existing FUDS FeatureServer `FUDS_STATUS` field remains the best available public proxy for remediation progress. Defer USACE deed records to a future FOIA request if a specific district partnership develops.

### Schema additions (all optional / nullable)

Add to `SiteRecord` in `schema.py`:
```
readiness_tier: Literal["available", "construction_complete", "lifoc", "assessment_complete", "cleanup_in_progress", "no_data"] | None
construction_complete_date: str | None   # YYYY-MM-DD; Superfund CC milestone (cumulis schedule scrape)
swrau_date: str | None                   # YYYY-MM-DD; Sitewide Ready for Anticipated Use (cumulis schedule)
fyr_dates: list[str] | None             # YYYY-MM-DD list; Five-Year Review dates (cumulis schedule)
cleanup_complete_date: str | None        # YYYY-MM-DD; ACRES CA_Status=Completed date
in_reuse: bool | None                   # True = site currently in active reuse (from RedevelopmentAppSitePoints.In_Reuse)
reuse_description: str | None           # plain-text reuse description (cumulis redevelop scrape)
fr_deletion_date: str | None            # YYYY-MM-DD; date of Federal Register NPL deletion rule
transfer_complete: bool | None           # FUDS/BRAC: title passed to non-federal entity
# NOTE: anticipated_land_use removed — AFL codes are not in any public API (SEMS-internal, FOIA-only; confirmed 2026-05-05)
```
`readiness_tier` is derived, not source-supplied — set by a `compute_readiness_tier()` function in `refresh.py` after all enrichments run.

### UI changes

- ~~**[high] "Cleanup Complete" badge in detail panel.**~~ Done 2026-05-05 — `selectSite()` checks `s.program === "superfund" && s.npl_status_code === "D"` and renders a green outline pill (`--readiness-ready` token, same shape as `.dc-pill` / `.reuse-pill`). Regression tests: `test_cleanup_complete_pill_for_npl_deleted` + `test_no_cleanup_pill_for_active_npl_site`.

- **[high] Development Readiness filter.** New collapsible filter section in the filters strip (below program/status checkboxes). Checkboxes: `☐ Cleanup Complete / Transferred` · `☐ Construction Complete (near-term)` · `☐ Assessment Complete` · `☐ Active Reuse Underway`. Drives `filterState.readinessTiers[]`; checked state persisted in URL as `?readiness=available,cc`. Default: all unchecked (no filter applied). Enumerate from a `READINESS_LEGEND` constant (same pattern as `PROGRAM_LEGEND` and `STATUS_LEGEND`) so the filter doesn't need updating when new tiers are added.

- **[high] Detail panel "Redevelopment Status" section.** New `#d-redev-block` in the detail panel (above infrastructure rows; below the FUDS block). Fields: readiness tier badge, Anticipated Future Land Use, RAU date, Construction Complete date, Reuse Projects list (name + type + year), Institutional Controls summary link. Hidden when no readiness data is available for the record. Show for all programs — ACRES cleanup status and FUDS transfer status deserve the same panel treatment as Superfund RAU.

- **[med] KPI deck: "Available Sites" count.** New KPI cell `#kpi-available` showing the count of records in Tier 1 readiness (cleanup complete / transferred) across all programs. Computed from the in-memory `sites` array after all lazy-loads complete. Gives users an immediate sense of the investable universe size.

- **[med] Map: readiness marker variant.** Optionally render Tier 1 sites with a distinct marker style (e.g., filled vs. ring, or a small checkmark overlay) so they're visually distinct from cleanup-in-progress sites. Implement only after filter + detail panel land — don't add visual complexity before the data is stable.

### Suggested phasing

1. **Immediate (zero new fetches):** Add "Cleanup Complete" green badge in detail panel for NPL `status = "D"` sites + FUDS sites with non-federal `current_owner` (after normalization). Add the Readiness filter checkbox skeleton, enabled only for those two signals initially. Ship as a point release.
2. **Short-term:** ACRES cleanups layer join (`epa_acres_cleanup.py`) — same connector pattern, one endpoint, lights up `readiness_tier` for the 36k ACRES records. SEMS REST API investigation — if endpoint is clean, ship `epa_sems_readiness.py` for Superfund CC + AFL. Ship both in one enrichment release.
3. **Medium-term:** EPA site profile Redevelopment tab scrape for RAU dates + reuse accomplishments. Builds on the `epa_superfund_docs` scrape pattern; run incrementally with `--redev-limit N`. Ship detail panel `#d-redev-block` at the same time so scraped data is immediately visible.
4. **Defer:** BRAC parcel-level LIFOC/deed scrape (per-Service PDF, multi-week); FUDS USACE CEFMS (FOIA-only). BRAC LRA curation is low-effort and can be done manually at any point.

## Infrastructure proximity (the data-center thesis)

Compute at refresh time, bake into JSON. Transmission, rail, and primary roads landed in v1.10 (see top-of-file). Remaining gaps:

- ~~**[high] Transmission lines.**~~ Done 2026-05-04 (v1.10) — HIFLD `Electric_Power_Transmission_Lines` (~52k polylines), nearest-segment via pure-Python `connectors/spatial.py`. Field: `transmission_mi`.
- **[high] Substations via OSM / OpenInfraMap.** HIFLD substations have been auth-walled since 2022 (DHS/CEII restriction — not a viable path). Two free alternatives:
  - **Audubon ArcGIS Hub** (`data-library-audubon.hub.arcgis.com`) publishes an OSM-derived substations FeatureServer layer — same connector pattern as existing HIFLD/TIGER layers, no Overpass setup needed. Preferred path.
  - **OSM Overpass API** (`overpass-api.de`) — query `way["power"="substation"]["voltage"~"^(69|115|138|161|230|345|500|765)"]` to filter HV-only. Free, no key, returns GeoJSON. Fallback if Audubon layer coverage proves incomplete.
  Filter to `voltage ≥ 69kV` (transmission-level) to exclude neighborhood distribution substations, which are irrelevant for data-center siting. OSM coverage of HV substations in CONUS is good; distribution-level is spottier. Add `substation_mi` to the existing `infra-proximity.json` schema — same `SegmentIndex` lookup pattern as transmission lines but point-to-point distance (substations are points, not polylines).
- **[high] Available transmission capacity (LBNL + gridstatus).** Going beyond "is there a wire nearby" — MW queued and available is the actual gating factor for data-center siting. Two free paths:
  - **LBNL "Queued Up" annual Excel** (`emp.lbl.gov/queues`) — free download, no auth, covers 97% of US installed capacity. Project-level fields include county FIPS, MW capacity, fuel type, queue status, entry/study dates. Roll up to `queued_mw_50mi` per site at refresh time. Annual cadence is fine for county-level aggregation. This is the same underlying data that interconnection.fyi surfaces — their API adds no value if you consume LBNL directly.
  - **`gridstatus` open-source library** (`pip install gridstatus`, Apache 2.0) — unified `get_interconnection_queue()` across all 7 ISOs (PJM, MISO, CAISO, ERCOT, SPP, NYISO, ISO-NE), returns a pandas DataFrame with lat/lon when the ISO provides it. More current than LBNL annual snapshots; useful for sites near ISO borders where county-level rollup is imprecise. Requires geocoding queue projects that lack coordinates.
  **Note:** FERC OASIS (real-time ATC) is fragmented across per-provider portals with no central bulk API. FERC Form 715 is CEII-restricted. Both are dead ends. interconnection.fyi paid API has no advantage over LBNL + gridstatus at zero cost.
- ~~**[high] Major roads + interstate access.**~~ Done 2026-05-04 (v1.10) — Census TIGERweb Primary Roads (`MTFCC='S1100'`, ~17.6k features). Field: `highway_mi`. Drive-time from nearest interstate exit deferred — would need OSRM / Mapbox, much heavier integration.
- ~~**[high] Rail.**~~ Done 2026-05-04 (v1.10) — Census TIGERweb Railroads layer 9 (~111k features). Field: `rail_mi`. Class I/II/III classification deferred — TIGER doesn't carry it; the HIFLD NTAD layer does (in `RROWNER1` field) but the join would double the layer-fetch cost.
- **[med] Water.** USGS NHD HighRes + waterbodies. Compute distance to: nearest surface water (cooling), nearest municipal water service area.
- **[med] Fiber proximity.** Genuine pain point — no clean public dataset.
  - FCC National Broadband Map (block-level fiber availability, indirect)
  - Crown Castle / Zayo / Lumen public route maps (PDFs, no APIs)
  - State broadband office GIS layers (varies)
  - **Best near-term proxy:** distance to nearest long-haul fiber landing point + presence of a colocation facility within 50mi (Data Center Map, paid).
- **[med] Natural gas pipelines.** HIFLD Natural Gas Pipelines. Relevant for behind-the-meter generation.
- **[med] Airport proximity.** HIFLD Aviation Facilities — for site-as-cargo-hub use cases.

## Data Center Opportunity Dashboard (pivot)

Turn this into a "Where can I site a hyperscale data center on a remediated brownfield?" tool. The angle: **post-remediation industrial land with grid + water + fiber that's already zoned heavy industrial is gold for AI buildouts, and Superfund/brownfield inventories are an under-mined source.**

- **[high] Data-center scoring model.** Weighted score per site:
  - Acreage ≥ X (configurable; default 50ac for hyperscale, 5ac for edge)
  - Remediation status (Deleted from NPL = green, on Final NPL = yellow, no SI/RI = red)
  - MW of available transmission capacity within 5mi
  - Surface-water cooling potential
  - Fiber-route proximity
  - Power cost ($/MWh) by utility territory
  - Climate suitability (cooling-degree-days, freshwater stress index)
- **[high] Filter UI for siting personas.** Toggle presets: "Hyperscale (≥100 ac)", "Inference edge (≥5 ac, <50ms to top-20 metro)", "Crypto/HPC (cheap power, remote OK)".
- **[high] Power-cost overlay.** EIA Form 861 retail rates by utility, joined to service-territory polygons.
- **[high] ISO interconnection-queue proximity.** PJM/MISO/CAISO/ERCOT/SPP/NYISO/ISO-NE queues are public; distance to nearest **active queued generation project** is a leading indicator of available capacity.
- **[med] Tax incentive layer.** Opportunity Zones (Treasury), state brownfield tax credits, federal Brownfield Tax Incentive (where still active), data-center-specific state programs (VA, AZ, GA, IA exemptions).
- **[med] Zoning overlay.** Most counties don't publish machine-readable zoning. Aggregate where available; flag manual-check-needed where not.
- **[med] Water rights & municipal capacity.** Western US: water rights are often the binding constraint, not power. Surface a per-site "water available?" field.
- **[med] PRP (Potentially Responsible Party) status.** A site with cleanup costs already settled or a willing PRP is dramatically more transactable than one with open litigation. EPA tracks PRP status in SEMS.
- **[low] Comparable transactions feed.** Recent brownfield-to-DC conversions (e.g. AWS at the old Talen Energy site, Meta's various Steel Belt redevelopments). Manually curated case-study list.
- **[low] Outreach contact card.** Per site: PRP counsel, regional EPA project manager, state brownfield program lead. Click-to-email templates.
- **[low] Timeline-to-shovel-ready.** Estimated months from "site identified" to "ready for vertical construction" given current remediation phase. Useful for capital planning.

## Frontend / UX

### UAT 2026-04-29 #2 (high priority)

- ~~**[high] Virtualize / paginate the table.**~~ Done 2026-04-29 (v1.6) — `TABLE_PAGE_SIZE = 250` with IntersectionObserver-driven sentinel auto-append. Total DOM nodes drop from ~265k to ~2,700.
- ~~**[high] Auto-fit map bounds when filters narrow the visible set.**~~ Done 2026-04-29 (v1.6) — `refitMapToFilters()` runs after each user filter change with bbox-vs-viewport heuristics. Search/slider debounced 350ms.
- ~~**[high] Replace `<select multiple>` for NPL Status with checkboxes.**~~ Done 2026-04-29 (v1.6) — fieldset of four checkboxes (`#f-status-checks input[data-status]`) with delegated change handler.
- ~~**[high] Replace state postal-code dropdown with full names.**~~ Done 2026-04-29 (v1.6) — `populateStateFilter()` renders "Alabama (AL)" sorted by full name; territories in `<optgroup label="Territories">`. Typeahead deferred — native select has prefix-match search.
- ~~**[high] Skip-to-content link + proper landmarks.**~~ Done 2026-04-29 (v1.6) — `.skip-link`, `<nav aria-label="Toolbar">`, `<main id="main" tabindex="-1" role="main">`, detail-panel `aria-hidden` synced to `hidden`.
- ~~**[high] Acreage slider needs labeled tick marks.**~~ Done 2026-04-29 (v1.6) — `<datalist>` for browser marks plus a `.acreage-ticks-labels` row showing `1 / 10 / 100 / 1k / 10k / 100k / 1M`. Numeric input deferred — labels alone proved sufficient in spot-testing.
- ~~**[high] Fix the search-input width.**~~ Done 2026-04-29 (v1.6) — `flex: 1 1 240px; max-width: 360px`; placeholder shortened to "Search sites…" with the longer description on `aria-label`/`title`. The search-count was also moved out of the input wrapper so a long count text doesn't compress the input.
- ~~**[high] Replace "N/A — see backlog" placeholder text.**~~ Done 2026-04-29 (v1.6) — replaced with "Not available" + `.muted-cell` styling.
- ~~**[high] Decode `FEDERAL_FACILITY_DETER_CODE` cleanly.**~~ Done 2026-04-29 (v1.6) — `selectSite()` reads `s.federal_facility` directly (already a clean label from the connector) and collapses upstream double-spaces.

### UAT 2026-04-29 (high priority)

- ~~**[high] Mask / remap non-CONUS state polygons.**~~ Done 2026-04-29 (v1.6) — `drawBasemap()` filters Alaska / Hawaii / Puerto Rico features out of `us-states.json` before rendering. Inset boxes carry the visual representation.
- ~~**[high] Chunk ACRES marker hydration.**~~ Done 2026-04-29 (v1.6) — `hydrateMarkersChunked()` adds 800 markers per `requestIdleCallback` tick. DOM-interactive in ~30 ms; markers light up progressively.
- **[med] Loading indicator during ACRES hydration.** With chunked hydration the main thread is no longer frozen, so the urgency dropped — but a progress chip ("Loading 36,003 brownfield sites…") would still help mobile users on slow connections. Reuse `showToast()`. *(Demoted from high priority now that the freeze is gone.)*
- ~~**[high] Programmatic `__APP_READY__` ready-signal.**~~ Done 2026-04-29 (v1.6) — `markAppReady()` sets `window.__APP_READY__` and dispatches `brownfield:ready` on `document`. E2e suite uses it.
- **[low] Make ACRES truly opt-in on first paint.** With chunked hydration the cold-load freeze is gone; the case for opt-in is now mostly bandwidth (~1.5 MB gz). Defer until we hear user feedback that the bandwidth cost matters. Workaround already exists: `?program=superfund` skips the fetch. *(Demoted from high priority.)*

### Existing items

- **[high] Polygon overlays on map.** Currently we flatten polygons to a centroid marker. Render the actual site boundary on zoom-in. Now even more useful since multi-polygon sites (Portland Harbor's 100 fragments) get merged for marker placement but the source rings are dropped — would need to keep them on disk (~+1MB raw / ~+150KB gz for simplified Superfund rings; ACRES has none).
- ~~**[high] Surface dedupe / parent-child relationships in UI.**~~ Done 2026-04-27 — `_dedupe_status_a` now attaches a compact `children: [{id, name}]` list to each parent. Detail panel renders a "Sub-sites" section listing them when present.
- ~~**[med] State filter, status filter, acreage range slider.**~~ Done 2026-04-27 — collapsible filters strip with state dropdown, NPL status multi-select, program multi-select (Superfund / Brownfield), and a log-scale acreage slider. All four filter both the table and the map markers.
- ~~**[med] Search box.**~~ Done 2026-04-27 — free-text on name / city / county / state, filters both table and markers, ESC to clear.
- ~~**[med] URL state sharing.**~~ Done 2026-04-27 — `?site=<ID>`, `?q=<query>`, `?state=<XX>`, `?status=F,P`, `?program=superfund,brownfield`, `?min_ac=<log10>` round-trip through the URL via `history.replaceState`. Legacy `?epa_id=` still works.
- ~~**[med] CSV export.**~~ Done 2026-04-27 — toolbar download button exports the currently-filtered set as CSV with date-stamped filename.
- **[low] Print/PDF site card.** For pitch decks.
- ~~**[low] Theme toggle.**~~ Done 2026-04-27 — toolbar toggle with `localStorage` persistence; honors `prefers-color-scheme` on first visit. Markers and legend re-stylize on swap (CSS-var driven).
- ~~**[low] Single source of truth for status colors.**~~ Done 2026-04-27 — colors live in `:root`/`[data-theme="dark"]` CSS vars. `colorForRecord()` reads via `getComputedStyle`; the legend reads the same vars. The dark-theme palette is a one-line swap.
- **[low] Polygon mask for non-US areas.** `maxBounds` + `minZoom` keep the user inside US-only territory, but at the edges Mexico/Canada/Cuba tiles are still visible. A US outline polygon overlay (filled with the page bg) would fully blank them out. Tradeoff: +1 fetch (~30–60KB simplified outline) and a polygon-render cost on every pan/zoom.
- **[med] Mobile filter UX.** The collapsible filters strip works on phones but it's wide; consider a bottom-sheet filter panel that mirrors the detail-panel pattern.

## Performance / hosting

### Frontend JS — code-level hot paths (audited 2026-05-05)

- ~~**[high] Pre-build search index at ingest time.**~~ Done 2026-05-05 — `ingestSites()` writes `s._searchKey = [name, city, county, state].filter(Boolean).join(" ").toLowerCase()` once per record. `siteMatchesQuery()` now reads `s._searchKey.includes(q)`. Eliminates the 47k×N per-keystroke string concatenations the audit flagged. Regression test: `test_search_index_built_at_ingest` + `test_search_filter_uses_prebuilt_index`.

- ~~**[high] Cache `refitMapToFilters()` bbox — eliminate O(n) min/max scan.**~~ Done 2026-05-05 — `refreshTableForFilter()` now computes `tableState.visibleBBox = {minLat, maxLat, minLon, maxLon, count}` while it walks the filtered set; `refitMapToFilters()` reads from it instead of re-scanning all 47k records. Every event handler that calls `refitMapToFilters()` already calls `applyFilter()` first, so the bbox is always fresh. Regression test: `test_visible_bbox_cached_on_filter`.

- ~~**[med] Replace `sites.some(s => s.program === X)` with a `loadedPrograms` Set.**~~ Done 2026-05-07 — module-level `const loadedPrograms = new Set()` populated in `ingestSites()`; `ensureAcresLoaded` / `ensureFudsLoaded` / `ensureBracLoaded` now do an O(1) `loadedPrograms.has(...)` check instead of an O(n) `sites.some(...)` scan over up to 47k records.

- ~~**[med] Move `decimateKeep(zoom)` outside the marker-visibility loop.**~~ Verified 2026-05-07 — already hoisted in `applyMarkerVisibility()` ([app.js:1112](docs/app.js:1112)) via `const keepEvery = decimateKeep(zoom)`. Backlog item was stale; only `shouldDecimateOut(id, keepEvery)` runs in the per-marker hot loop.

- ~~**[med] Batch enrichment property assignment.**~~ Done 2026-05-07 — `ensureRedevLoaded` and `ensureInfraLoaded` build a `patch = {}` per record then `Object.assign(existing, patch)`. The single-field `ensureSuperfundDocsLoaded` / `ensureEchoLoaded` / `ensureSummariesLoaded` loaders are intentionally left alone — `Object.assign` adds churn without saving lookups when there's only one or two keys.

- ~~**[med] Cache `updateCountText()` inputs from `refreshTableForFilter()`.**~~ Done 2026-05-07 — `refreshTableForFilter()` now writes `tableState.filteredAcreSum` + `tableState.filteredAcreSites` in the same pass that builds `tableState.filtered` and `tableState.visibleBBox`. `updateCountText()` reads those instead of re-scanning all 47k records — every caller already runs `refreshTableForFilter()` first via `applyFilter()`, so the cache is always fresh.

- ~~**[low] Event delegation for table header sort clicks.**~~ Done 2026-05-07 — single delegated `click` listener on `#sites-table thead` that checks `event.target.closest("th[data-sort]")`. Survives future column additions without rebinding. N column listeners → 1.

- ~~**[low] Cache `querySelectorAll` in `updateSortIndicators()`.**~~ Done 2026-05-07 — `_sortHeaders` cached on first call via `getSortHeaders()` and reused. The header set never changes for the document's lifetime.

- **[low] Pre-compile `prettyPlace`/`prettyName` regexes as module constants.** Both functions define their split regexes inline (re-parsed each call at startup). Move them to `const PLACE_SPLIT_RE = /(\s+|[-/])/g` at module scope. V8 likely caches them already, but explicit constants make the intent clearer.

- **[low] Single-pass KPI deck computation.** `updateKpiDeck()` loops `sites` once per metric (total, acres, DC candidates, state set). Merge into one `sites.reduce()` call that accumulates all four in parallel. Reduces 4 passes to 1.

### UAT 2026-04-29 #2 (high priority)

- **[med] LOD swap for the basemap above zoom 10.** State strokes still look blocky at zoom 12+. Pagination + chunked hydration moved this off the critical path; revisit when we can swap to a higher-detail GeoJSON or fade strokes at zoom > 10. *(Demoted — counties carry visible borders past zoom 7, so the simplification artifact is mostly cosmetic on infrequent deep-zoom views.)*
- ~~**[high] Re-evaluate `ensureCountiesLoaded()` on every `moveend`.**~~ Done 2026-04-29 (v1.6) — `map.on("moveend", updateCountyVisibility)` now fires for any view change, including `setView`-driven auto-zoom from `?site=` or the detail panel.
- ~~**[high] Toast / inline feedback when `?site=<id>` doesn't match.**~~ Done 2026-04-29 (v1.6) — `applyUrlSelection()` waits for `acresLoadingPromise` (so the toast doesn't fire prematurely), then `showToast(...)` with the bad ID. URL is preserved.
- ~~**[high] Fix URL-state unwind on filter clear.**~~ Verified 2026-04-29 (v1.6) — `syncUrl()` already drops keys at default; new regression test `test_url_unwinds_on_filter_clear` guards against future drift.

### UAT 2026-04-29 (high priority)

- **[high] Audit first-paint payload now that ACRES auto-loads.** Cold load = ~12 MB decoded / ~1.8 MB on the wire (sites.json 184 KB gz + epa-acres.json 1.58 MB gz + states 30 KB + leaflet/topojson/app/css). Partial mitigation 2026-05-07: every post-paint enrichment fetch (`epa-redev`, `infra-proximity`, `epa-echo`, `ai-summary`, `epa-superfund-docs`) now passes `priority: "low"` so browsers (Chrome 102+, Firefox 132+, Safari 17+) deprioritize them behind the first-paint resources. Doesn't reduce bytes — bytes problem is still real. Real fix is one of: (a) make ACRES opt-in (already in Frontend/UX backlog as `[low]` since the cold-freeze was killed by chunked hydration); (b) state-shard ACRES and lazy-fetch only the visible state(s); (c) drop unused fields from the ACRES output (audit `epa-acres.json` for null-heavy columns). Defer until a user cites the bandwidth cost.
- ~~**[high] Cap or virtualize markers on the canvas at low zoom.**~~ Partial 2026-05-07 — tightened decimation to 1/16 at zoom ≤4 (was 1/8) and 1/8 at zoom ≤5 (was 1/4). Visible-marker count at zoom 4 drops from ~5,900 to ~3,000 across all four programs. Viewport-clipped renderer (only add markers within `getBounds()` and re-evaluate on `moveend`) deferred until a user reports residual pan-lag at zoom 4.

### Existing items

- **[med] Tile self-hosting.** OSM tile policy discourages heavy production use. If the dashboard gets traffic, switch to a free vector-tile provider (Protomaps + free tiles, or MapTiler free tier).
- ~~**[med] Lazy-load ACRES.**~~ Done 2026-04-27 — `sites.json` stays Superfund-only (~170KB gz). `epa-acres.json` (~1.5MB gz) loads only when the user toggles the Brownfields program filter on (or arrives via `?program=brownfield`).
- ~~**[med] Marker decimation at low zoom.**~~ Done 2026-04-27 — at zoom ≤4 we keep 1 in 8 markers, ≤5 keeps 1 in 4, ≤6 keeps 1 in 2, ≥7 shows everything. Stable hash-based sampling so the same subset stays visible across zoom changes.
- ~~**[med] Drop-null serialization.**~~ Done 2026-04-27 — `Payload.model_dump_json(exclude_none=True)` skips placeholder fields (`current_owner`, `proximity`, etc.); minified output is the default. Saves ~30% on uncompressed payload.
- **[med] State-sharded JSON.** Already viable; defer until per-state filtering on the frontend becomes a measurable bottleneck.
- **[low] PWA / offline cache.** Service worker for repeat visits.

## Comparative analysis — gaps vs. similar trackers (2026-05-04)

Researched: EPA Cleanups in My Community, EPA ACRES portal, EPA ECHO, EPA EJSCREEN, EPA EnviroAtlas, SEMS/CERCLIS, NJDEP Contaminated Sites Explorer, CalEPA EnviroStor, NYSDEC Environmental Site Database.

### Data sources not yet in our tracker

- ~~**[med] ECHO enforcement & compliance history.**~~ Done 2026-05-04 (v1.11) — `connectors/epa_echo.py`. One HTTP call per Superfund site to `echodata.epa.gov/echo/echo_rest_services.get_facilities?p_si=<EPA_ID>` returns the headline ECHO summary (5yr inspections, formal/informal actions, penalties, last violation date, current compliance, active programs). Detail-panel "Enforcement & compliance" block highlights nonzero formal actions and nonzero penalties via the `.violation` class. Resumable batched coverage via `--echo-limit N --echo-skip M`. Deep-link to canonical DFR on echo.epa.gov for full report. Currently Superfund-only; ACRES/FUDS/BRAC could pivot via name+state lookup in a future pass.
- **[med] RCRA Corrective Action.** Already in backlog — naming it here again because ECHO and EnviroAtlas both expose it and it's one of the bigger universe-expansion opportunities (tens of thousands of sites not in EPA NPL or ACRES).
- **[med] UST (Underground Storage Tanks) database.** State UST databases track former/current petroleum storage — the single largest category of brownfield sites. Most are former gas stations with moderate (sub-$1M) cleanup costs and attractive urban infill locations. EPA's LUST/UST program aggregates state data. Distinct program = new connector + `program: "ust"`. Start with the LUST Trust Fund tracking data (EPA OUST).
- **[med] State VCP (Voluntary Cleanup Programs).** Each of the ~40 active state VCPs has thousands of sites not in federal data — NY DEC State Superfund, CA DTSC EnviroStor, TX TCEQ VCP, NJ DEP Hazardous Discharge Site Remediation Fund (HDSRF). These are often *closer to shovel-ready* than federal sites because voluntary cleanups are developer-initiated. Suggested connectors by state: CA EnviroStor ArcGIS REST → `program: "ca-vcp"`, NY DEP ESD search → `program: "ny-vcp"`. One connector per state; add when a state publishes a machine-readable endpoint.
- **[low] TRI (Toxic Release Inventory) proximity layer.** EPA TRI tracks annual chemical releases by facility. Not brownfields themselves, but a "risk precursor" — facilities near our sites that still release hazardous substances affect neighbor perceptions and sometimes share contaminated groundwater plumes. Show as a proximity ring on the site detail map rather than new markers.
- **[low] RMP (Risk Management Plans) proximity.** Similar signal: active high-risk chemical facilities near a brownfield affect acquirer risk. EPA RMP*Info API is public.

### Site-depth gaps vs. competitors

- ~~**[high] AI-generated site summary card.**~~ Done 2026-05-04 (v1.11) — `connectors/ai_summary.py` calls Claude Haiku (`claude-haiku-4-5-20251001`) to synthesize a 3-paragraph plain-English narrative per site (what it is / reuse signals / material risks). **Cached by content-hash** of the relevant fields so re-runs only re-bill when underlying data actually changes. Surfaced as a "Summary" tab in the detail panel with an accent left-border to distinguish AI-generated prose from primary-source data. `--dry-run` works without an API key (cache-only re-build). Default `--ai-limit 100 --ai-status F,D` keeps a single run cheap; cost ≈ $0.001/summary at current Haiku pricing.
- **[med] Remediation timeline visualization.** ECHO and SEMS both expose milestone dates (SI, PA, RI/FS, ROD, RD/RA, Construction Complete, Deleted). We carry `npl_status` but no milestone dates. Adding a horizontal timeline strip to the detail panel ("Listed 1983 → ROD 1991 → Construction Complete 2006 → Deleted 2012") would match the most useful pattern in CERCLIS-era tools and is unique among public-facing UIs.
- **[med] Five-Year Review (5YR) status.** EPA requires 5YRs at NPL sites to verify ongoing protectiveness. A site with a failing 5YR is a very different acquisition risk than one that passed. EPA SEMS 5YR table is in the same SEMS API used by the existing connector — one extra endpoint to pull.
- **[med] ACRES grant history.** ACRES tracks EPA brownfield grants: grantee, award amount, award date, assessment/cleanup/RLF type. A site that received $500k in cleanup funding 3 years ago is much closer to ready than one without grants. ACRES REST endpoint exposes this under `BF_GRANT_AWARD` and `BF_GRANT_RECIPIENT` views. Show in detail panel as a "Federal funding" section.
- **[med] Environmental justice / community demographics layer.** EJSCREEN (ejscreen.epa.gov/arcgis/rest/services) exposes census-block-level demographic + pollution burden scores. Useful for grant prioritization (federal brownfield grants score EJ community presence) and to surface in the detail panel as a "Community context" section. Pull nearest block's EJ index at refresh time and bake into JSON rather than fetching client-side.
- **[med] Superfund Institutional Controls (ICs).** EPA ICTS tracks deed restrictions and environmental easements per site (the legal instruments that run with the land after cleanup). This is the single most important encumbrance a buyer needs to know about. EPA ICTS REST endpoint exists; join by EPA_ID. Surface in detail panel as a "Land use restrictions" section with each IC instrument, type, and restriction text.

### UX patterns no competitor does well

- **[med] Radius / "near me" search.** Every competing tool uses address lookup for radius search; none integrate it into a filtered-map workflow. Add an optional "within X miles of [address]" filter that geocodes via Nominatim (no key) and filters `sites` by Haversine distance. Show the radius circle on the map.
- **[med] Site timeline view (table mode).** Add an optional "Timeline" sort that orders the table by `listing_date` (or milestone date when available) so users can see how the program has evolved over decades. A stacked-bar year histogram above the table showing "sites listed per decade" would match FT/NYT data-journalism standards.
- **[low] Watchlist / site portfolio.** `localStorage`-based: users can star sites and view them in a "My sites" tab. No backend required. Useful for BD workflows where a team is tracking 20 candidate sites.
- **[low] Comparison view.** Side-by-side panel for 2–3 sites: same KV fields in columns. No competing tool has this. Useful for "pick the best site in a state" workflows.
- **[low] Public read API.** Expose `docs/data/*.json` through a thin documented API (even just query-string filtering on a Cloudflare Worker or Netlify Function). Lets external developers build on our data without scraping. Opens a monetization path.
- **[low] Embed widget.** `<iframe>`-embeddable single-site card. Real estate brokers and local news outlets would use this on listing pages or contamination stories.
- **[low] Saved search + email alert.** User saves a filter set (e.g. "NJ + Final NPL + ≥50ac") and gets an email when the daily refresh produces new matching sites. Requires a thin backend (Cloudflare Worker + Resend free tier). No competing public tool has this.
- **[low] Print / PDF site card.** One-page printout of site details for pitch decks. CSS `@media print` → hide map controls, expand detail panel to full page, include a static map image. Already in backlog [low] — recording the UX pattern from competitors (none do it well).

---

## Engineering hygiene

- ~~**[high] Tests for refresh.py.**~~ Done 2026-04-27 — pytest suite covers normalize/envelope/fetch/dedupe/merge/diff/schema. As of v1.7: 117 unit tests (incl. 17 FUDS, 14 BRAC, 17 Redev) + 26 e2e.
- ~~**[high] Frontend smoke test (Playwright or similar).**~~ Done 2026-04-27 — `tests/e2e/test_smoke.py`: 26 tests covering page load, tab switch, marker click, table click, Esc close, search filtering, legend render, all four programs loading, NPL status checkboxes, state dropdown, acreage slider, pagination, DOM size, accessibility landmarks. Runs in CI on every PR.
- ~~**[high] Resolve dual-deploy ambiguity.**~~ Done 2026-04-27 — pushed `deploy.yml` + `refresh.yml`, switched Pages source to GitHub Actions via `gh api PUT pages -f build_type=workflow`.
- ~~**[med] Move `docs/serve.py` out of `docs/`.**~~ Done 2026-04-27 — moved to `scripts/serve.py`; chdirs to docs/ so still runs from repo root.
- ~~**[med] Schema validation.**~~ Done 2026-04-27 — Pydantic `Payload`/`SiteRecord` in `schema.py` with `extra="forbid"`. `refresh.py` validates before write.
- ~~**[med] Diff log.**~~ Done 2026-04-27 — `diff.py` writes `data/changes.md`; `refresh.yml` parses summary into commit message.
- ~~**[med] Defensive over-fetch guard.**~~ Done 2026-04-27 — connector logs a warning if >50% of fetched features drop during normalize.

## Data audit — gaps found 2026-05-04

Systematic null-rate analysis across all six data files (`superfund-npl.json` 1,908 records · `epa-acres.json` 36,003 · `dod-fuds.json` 8,822 · `dod-brac.json` 27 · `infra-proximity.json` 46,218 · `epa-superfund-docs.json` 7).

### Coverage gaps

- ~~**[high] Superfund documents enrichment at 0.4% coverage.**~~ Done 2026-05-04 (v1.10.1) — `--docs-limit 500 --docs-status F,D` run; coverage now ~500 of the 1,908 NPL sites (largest by acreage). Connector also hardened against single-blip `cumulis.epa.gov` connection timeouts.

- **[high] ACRES acreage: 0/36,003 records populated (0%).** The EPA ACRES FeatureServer does not expose acreage. Every ACRES record has `acreage: null`, so the acreage slider, "X ac" KPI, and acreage column are meaningless for the 36k brownfield records. Two paths remain:
  - Email `helpdesk@acrebs.epa.gov` for a bulk PPF extract (free, one-shot, ~1–2 week turnaround).
  - Commercial fallback via Regrid / Landgrid Parcel API (~$0.001–0.01/parcel; one-time enrichment of 36k records ≈ $36–360).
  Until one ships, the KPI deck acreage total excludes all 36,003 brownfields.

- ~~**[high] ACRES county: 18,421/36,003 records missing county (51.2%).**~~ Done 2026-05-04 (v1.10.1) — offline TIGER spatial join via new `connectors/county_lookup.py`. 18,322 / 18,421 missing records filled (99.5% hit rate); remaining ~99 are coastal points just outside the polygon edge. Pure-Python decode + 0.5°-cell point-in-polygon; no extra deps, no Census Geocoder API.

- ~~**[high] FUDS acreage: 5,832/8,822 records missing acreage (66.1%).**~~ Note shipped 2026-05-04 (v1.10.1) — detail panel renders "Boundary not digitized in USACE source." inline next to the Acreage row for FUDS records without polygon boundaries. The underlying gap is a USACE-side digitization issue with no automated public fix; documented as a known source limitation.

- ~~**[med] FUDS current_owner raw codes not normalized.**~~ Done 2026-05-04 (v1.10.1) — `connectors/dod_fuds.py:_pretty_owner()` cleans the six tier prefixes to readable labels at normalize time. 7,573 records now display "Private" / "Federal — Air Force" / "Local government — City" instead of the raw `"PRIV: PRIVATE   "` codes. Multi-tier entries joined with " / "; agency acronyms preserved through title-casing.

- ~~**[med] Out-of-CONUS sites have no infra-proximity data — undocumented.**~~ Done 2026-05-07 (option a) — `setMileCell()` now accepts an `offConus` flag (set when `s._inset` is truthy in `selectSite()`) and renders `"Remote — outside continental US"` instead of `"Not available"` for AK / HI / PR / VI / GU / MP / AS / FM records. The 395 FUDS + 142 ACRES out-of-CONUS records now read as a known source-side limitation rather than missing data. Option (b) — running AK-specific enrichment with AK DOT&PF + HIFLD AK railroad layers — still open if a user requests AK-specific infra distances.

- **[low] FUDS has_projects field exposes no project-level detail.** 2,874 FUDS records flag `has_projects: "yes"` with no further breakdown. USACE FUDS FeatureServer layers 2 (Projects) and 3 (Investigations) are at the same endpoint and joinable by `DODFUDSPROPERTYIDPK`. A join would surface project count, current phase, and investigation type in the detail panel. Similar pattern to the existing layer-4 acreage join.

### Schema fields with 0 records populated (gap register, verified 2026-05-04)

The following `SiteRecord` fields are defined in `schema.py`, have connectors planned, but currently have zero data in any output file:

| Field | Status | Source |
|-------|--------|--------|
| `enforcement` | Connector built (v1.11) — populated incrementally as `epa-echo --echo-limit N` runs land more sites | EPA ECHO `get_facilities` |
| `summary` / `summary_meta` | Connector built (v1.11) — populated incrementally as `ai-summary --ai-limit N` runs land more sites; requires `ANTHROPIC_API_KEY` | Claude Haiku |
| `encumbrances` | Connector not built | EPA ICTS institutional controls |
| `remediation_detail` | Connector not built | EPA SEMS milestone table |
| `historical_owners` | No clean public source | County deed history (paid) |

Note: `data_center_reuse_candidate`, `near_electric_transmission`, and Redev fields ARE populated (828 True / 1,077 False across 1,905 sites in `epa-redev.json`) — they live in the enrichment file and are joined client-side, not embedded in `superfund-npl.json` directly. The legacy `proximity` row was retired 2026-05-04 (v1.10.1) — the field was removed from `schema.py` since it was fully superseded by `transmission_mi` / `rail_mi` / `highway_mi`. Schema's `extra="forbid"` now actively rejects any reintroduction (regression-tested in `test_legacy_proximity_field_rejected`).

---

## Data quality (deferred normalizations)

- ~~**[med] Decode `FEDERAL_FACILITY_DETER_CODE`.**~~ Done 2026-04-27 — pulled from layer metadata at refresh time alongside `NPL_STATUS_CODE`.
- ~~**[med] Dedupe / nest parent-child NPL sites.**~~ Done 2026-04-27 — status-A sub-sites whose name matches a parent's prefix are dropped from the main list and tagged with `parent_epa_id`. Parent now also carries `children: [{id, name}]` for UI surfacing.
- ~~**[med] Fallback EPA site-profile URL.**~~ Done 2026-04-27 — falls back to `cumulis.epa.gov/supercpad/CurSites/csitinfo.cfm?id=<EPA_ID>` when both source fields are null.
- ~~**[low] Cosmetic acreage formatting.**~~ Done 2026-04-27 — `fmt.acres()` now uses thousands separators everywhere and hides trailing `.0`.
- **[med] Multi-polygon merge surfacing.** `_merge_by_epa_id()` collapses fragmented sites (e.g. Portland Harbor) into one record, but the source rings are dropped — when polygon overlays land, we'll need to keep the per-fragment geometry on disk.
- **[med] ACRES + Superfund cross-references.** EPA's ACRES system includes some sites that are also on the NPL. Detect via PROPERTY_NAME / EPA_ID fuzzy match and link in the UI ("Also tracked in Superfund").
