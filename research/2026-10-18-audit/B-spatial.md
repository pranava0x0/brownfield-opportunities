# Audit B: spatial and enrichment sources (read-only, 2026-10-18)

Method: live `curl -4` probes (UA `brownfield-audit/1.0`, 1.5 s spacing, `--max-time 30`). ArcGIS errors checked for the HTTP-200 `error` key. Field coverage measured over `docs/data/*.json`. Independent point checks against source services. Validator: `scripts/validate_against_sources.py --only infra --sample 6 --seed 1018`, exit 0, 88/96 OK, 8 SKIP, 0 FAIL. The 8 SKIPs are boxes needing more than 45 mi (`validate_against_sources.py:412`). The validator checked the infra distance fields only.

## Cross-cutting defect: polygon containment ignores multipart features (affects NRI, IRA, OZ, tribal, climate, ISO)

- `connectors/spatial.py:PolygonIndex.add_polygon` treats `rings[0]` as the only exterior. ESRI multipart features arrive as a flat ring list. Each part after the first is either ignored by the exterior test or subtracted as a hole.
- Proof, New Castle County DE (FIPS 10003), NRI layer: 5 rings. Ring 3 (9,226 vertices, area -0.117) is the mainland and the only ring that contains the point. `containing()` tests ring 0 only, so the point returns None.
- 388 of 3,232 NRI county polygons are multipart. The problem is concentrated in coastal and island-rich geography.
- Live check: `NRI point query at DEN000304044` returns New Castle County "Relatively High". Our `fema-nri.json` has no NRI fields for that site (tombstone only).
- Impact in the shipped data: NRI unmatched for 474 of 1,908 Superfund sites (24.8%). Worst: DE 25/25, NJ 73/155, FL 62/93, NY 43/126, WA 33/67, CA 32/115, TX 22/70, MD 20/26, MA 21/41.
- Other connectors calling `add_polygon` with full ring lists: `ira_energy_community.py:285,334`, `opportunity_zone.py:250`, `tribal_areas.py:82`, `climate_zone.py:201`, `iso_rto.py:215`. The undercount is unmeasured there, but the same mechanism applies.
- Fix: split rings into exteriors and holes by orientation (signed area), index each exterior with its own holes, and add a per-state coverage assertion against the source's feature count.

## 1. infra-proximity (HIFLD transmission, gas, power plants; TIGER roads and rail; OSM substations; FEMA NFHL flood)

- URLs: transmission `services1.arcgis.com/Hp6G80Pky0om7QvQ/.../Electric_Power_Transmission_Lines/FeatureServer/0` (HTTP 200, `dataLastEditDate` 2023-09-05, 52,244 features). Gas `services2.arcgis.com/FiaPA4ga0iQKduv3/.../Natural_Gas_Interstate_and_Intrastate_Pipelines_1` (200, data edit 2025-07-01). Power plants `services2.../Power_Plants_in_the_US` (200, the layer is `PowerPlants_US_EIA`, data edit 2025-07-01, `capacity_basis` maximum summer). Roads `tigerweb.../Transportation/MapServer/2` (200, "January 1, 2026"). Rail `.../MapServer/9` (200, 111,627 features). Overpass `overpass-api.de/api/interpreter` (first status call timed out, a query succeeded on retry). NFHL `hazards.fema.gov/.../NFHL/MapServer/28/query` (intermittent connection resets, a retry returned 200).
- Publishers: HIFLD (DHS, post-2025 reorganization, hub still answers 200), Census TIGER, OpenStreetMap, FEMA.
- Coverage (of 46,759): transmission 98.9%, highway 97.1%, rail 98.3%, gas 96.2%, substation 99.1%, power plant 99.5%, flood assessed 91.1% (42,576). 4,183 flood rows are `not_assessed`. SFHA true 4,422.
- Metadata gaps: `source_metadata.*` has `snapshot_basis: legacy_cache_unknown_retrieval_date`, `count_reconciled: false`, and `source_snapshot_at` null for transmission, roads, rail, gas, and power plants. Flood is `legacy_coordinate_unverified`. Real retrieval dates are unknown.
- Derived-quantity caveats: 44.1% of nearest-substation picks are `distribution` or `minor_distribution` (20,423 of 46,349). 7,061 of 34,048 kV-tagged substations are under 69 kV. HIFLD transmission is patchy on sub-transmission. Median nearest-line distance is 1.1 mi, and only 0.55% of sites are 50 mi or more from a line.
- Spot checks: validator 88/96 reproduce; the 8 SKIPs are structural (box too large). Sites WI0001954841 and others reproduce distances under a 1.6x box.
- Verdict: VALID-WITH-CAVEAT.
- Most important fix: record real retrieval dates per layer; reassess or relabel the 4,183 `not_assessed` and legacy-coordinate flood rows; restrict the substation grid-access signal to transmission-class substations (or label it as distribution-inclusive).

## 2. fema-nri (FEMA National Risk Index, county polygons)

- URL: `services.arcgis.com/XG15cJAlne2vxtgt/.../National_Risk_Index_Counties/FeatureServer/0` (200, `NRI_Counties_Prod`, data edit 2025-12-16). Count 3,232, `maxRecordCount` 2000, pagination at 1000 verified. Connector paginates correctly.
- `source_url` still points at `hazards.fema.gov/nri/` (dead per data-source-research §; provenance uses point queries instead).
- Coverage: `nri_risk_rating` 35,783 (76.5%); `nri_wildfire_rating` 76.5%; `nri_risk_score` 76.2%. Generated 2026-06-08.
- Spot checks (3 random sites, independent point query): PA 98.09 Relatively High, SC 93.96 Relatively Moderate, VT 52.32 Relatively Low. Rating, score and wildfire rating all match exactly. Values where matched are correct.
- Defect (see cross-cutting): 24.8% of Superfund sites unmatched, zero on DE, heavy on coastal states.
- Caveat: county-level NRI applied to a point; flood and heat are explicitly scoped; coastal sites near multipart counties silently lose climate penalties (neutral, not wrong, but a false absence).
- Verdict: INVALID (join). Values where present are VALID.
- Most important fix: multipart-aware `PolygonIndex`, then rebuild and report coverage by state against the source's 3,232 counties.

## 3. opportunity-zone (HUD Qualified Opportunity Zones)

- URL: `services.arcgis.com/VTyQ9soqVukalItT/.../Opportunity_Zones/FeatureServer/13` (200, data edit 2026-02-24, `GEOID10`, `STATE`, `COUNTY`). Publisher HUD. Designations are 2018, stable for ten years.
- Coverage: 16,090 sites in an OZ (34.4%), 5,589 rural. Generated 2026-05-17. The OZ fields are in the coordinate-pending list for 25 invalidated IDs (`evidence-invalidations.json`).
- Spot checks: three sites reported False; OZ point queries return zero features. That is consistent but not a positive test. No positive hit was independently re-measured.
- Caveat: 34% of the corpus in an OZ is plausible for low-income brownfield clustering but unverified. Tracts are mostly single-part, so the multipart defect has smaller impact here.
- Verdict: VALID-WITH-CAVEAT.
- Most important fix: rerun after the `PolygonIndex` fix and re-measure the 25 pending IDs.

## 4. ira-energy-community (DOE/NETL energy communities)

- URLs: `arcgis.netl.doe.gov/server/rest/services/Hosted/2024_Coal_Closure_Energy_Communities/FeatureServer/0` (200) and `.../2024_MSAs_NonMSAs_that_are_Energy_Communities/FeatureServer/0` (200). NETL-hosted, 2024 vintage, no edit date exposed. Publisher DOE NETL.
- `source_url` is `energycommunities.gov`, which is DNS-dead per data-source-research (provenance replaced it with a point query).
- Coverage: 14,790 qualify (31.6%): 3,236 coal closure, 11,554 fossil-fuel employment. Generated 2026-06-08.
- Spot checks: three non-qualifying sites return empty results from both NETL layers, consistent with False. No positive hit independently re-measured.
- Defect risk: the FFE layer is county-level and many coastal counties are multipart, so undercount is likely (unmeasured). This is the same `PolygonIndex` defect.
- Verdict: VALID-WITH-CAVEAT (possible undercount).
- Most important fix: multipart-aware index, then measure FFE coverage against an independent county list.

## 5. iso-rto (EIA RTO regions)

- URL: `services3.arcgis.com/dNDFv7tc3OwOgyit/.../RTO_Regions/FeatureServer/0/query`. Live response is HTTP 200 with body `error: 499 Token Required`. Both `arcgis` and `ArcGIS` casings fail the same way. The connector cannot refresh.
- Publisher EIA (atlas.eia.gov). Data generated 2026-06-05 and frozen.
- Coverage: 45,051 (96.3%): non-RTO 25,693, MISO 7,146, SPP 4,034, PJM 3,721, ISO-NE 1,814, ERCOT 1,103. Plausible but unverified against a current source.
- Same multipart defect applies to state-level RTO polygons (unmeasured).
- Verdict: STALE (refresh broken; token-walled).
- Most important fix: replace with a public EIA download or the EIA open-data equivalent, or freeze the output with an explicit vintage banner.

## 6. tribal-areas (Census TIGERweb AIANNHA)

- URL: `tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/AIANNHA/MapServer/{layer}/query` (200; layer 0 = Alaska Native Regional Corporations). Census TIGERweb is current and authoritative. No edit date (rolling service).
- Coverage: 2,122 positive-only records (the file records hits, not negatives, by design).
- Spot check: sample record AK6210022426 matches Doyon ANRC (geoid 0220010).
- Caveat: AIANNHA means mapped consultation context, not land title. Reservations are heavily multipart, so the `PolygonIndex` defect likely undercounts positives.
- Verdict: VALID-WITH-CAVEAT (undercount risk).
- Most important fix: multipart-aware index; re-measure reservation-area hits.

## 7. climate-zone (Building America / IECC county climate zones)

- URL: `services8.arcgis.com/s3xegrS2bQ4HS3tU/.../Building_America_and_IECC_Climate_Zones_by_U_S__County_Boundaries_(Detailed)/FeatureServer/0`. Live (200), `dataLastEditDate` 2021-03-25.
- Provenance problem: the hosting org `s3xegrS2bQ4HS3tU` is a third-party ArcGIS org with 55 services, including test items such as `01162025_Kojo_Test_DHS_ShuttleBuses_Replica`. It is not PNNL or DOE. `source_url` cites PNNL BASC.
- Coverage: 45,543 (97.4%). Top values 5A, 4A, 6A.
- Caveat: county zones applied to point sites; same multipart defect.
- Verdict: INVALID (provenance). Values may be correct but the citation and copy are not verifiable from the hosted replica.
- Most important fix: source the zone list from the PNNL/BASC county file directly, cite that file, and re-verify.

## 8. water-proximity + streamgages (USGS NWIS)

- URLs: `waterservices.usgs.gov/nwis/site` (200) and `/nwis/stat` (200). New `api.waterdata.usgs.gov/ogcapi/v0/collections` (200).
- Legacy retirement (WebSearch, USGS blog and USDOI bulletin): legacy WaterServices degrades from November 2026 and is decommissioned about 22 February 2027. Migration to `api.waterdata.usgs.gov` is expected before January 2027.
- `streamgages.json`: 8,730 gages, generated 2026-09-12. `water-proximity.json`: 45,937 sites (98.2%) with flow, generated 2026-09-12. Statistic is mean of annual means. `supply_assessment: unassessed`.
- Derived-quantity caveat: mean annual flow is not a permittable 7Q10 low flow. Distance is to a gage, not to water. The connector note already says it screens and never clears. Robust for screening, misleading if shown as availability.
- Spot check: not run in this pass (budget).
- Verdict: VALID-WITH-CAVEAT, plus a time-bound migration risk.
- Most important fix: port `build_streamgages_overlay.py` to the OGC API before November 2026, and keep the mean-flow disclosure on every surface.

## 9. parcel-owner (state parcel layers)

- Endpoints checked (metadata, HTTP 200 with JSON): NC `services.nconemap.gov/secure/.../NC1Map_Parcels/FeatureServer/1`; WI `uadnrmaps.wi.gov/.../EN_County_Tax_Parcels...MapServer/0`; NJ `services2.arcgis.com/XVOqAjTOJ5P6ngMu/.../Parcels_Composite_NJ_WM/FeatureServer/0` (edit 2026-08-18); VT `services1.arcgis.com/BkFxaEFNwHqX3tAw/...VTPARCELS...` (edit 2026-08-13); CT `services3.arcgis.com/3FL1kr7L4LvwA2Kb/...Connecticut_CAMA_and_Parcel_Layer_2024` (edit 2025-09-10); MA `services1.arcgis.com/hGdibHYSPO59RG1h/...Massachusetts_Property_Tax_Parcels` (edit 2026-08-05); FL `services9.arcgis.com/Gh9awoU677aKree0/.../Florida_Statewide_Cadastral` (live); CO `gis.colorado.gov/.../Colorado_Public_Parcels` (live); IA `services3.arcgis.com/kd9gaiUExYqUbnoq/.../Iowa_Parcels_2017` (edit 2024-05-10, 2017 vintage).
- Montana: `gisservicemt.gov/.../MSDI_Framework/Parcels/MapServer/0` returns an HTML page ("Montana State Library Blank..."), both metadata and query. The endpoint is dead for refresh. The output still holds 506 Montana records from cache.
- Minnesota: `pca-gis02.pca.state.mn.us/.../parcels_open_data_counties/MapServer/0` returns HTTP 200; JSON content not confirmed.
- Coverage (of 46,759): `current_owner` 7,270 (15.5%); `parcel_acreage` 5,112 (10.9%); `parcel_id` 10.6%. Output holds 11,463 records. Owner source counts include Florida 1,817, MA 891, MN 790, WI 782, NC 771, IA 634, CO 587, MT 506, NJ 430, VT 329, CT 304.
- Caveats: state-level coverage with many blank owners; vintage varies (Iowa 2017); fill-if-empty join is correct per the file's own contract.
- Verdict: VALID-WITH-CAVEAT for loaded states; MT source STALE/dead.
- Most important fix: disable or repoint Montana, confirm Minnesota returns features, and surface per-state source vintage.

## 10. census-workforce (ACS 5-year)

- URL: `api.census.gov/data/{ACS_YEAR}/acs/acs5/profile`. Without a key, the request returns 302 to `api.census.gov/data/missing_key.html`, so no data is returned.
- No `docs/data/census-workforce.json` exists. The connector is registered in `connectors/__init__.py:11,77`.
- CLAUDE.md states `CENSUS_API_KEY` is now required. The nickel lens already dropped workforce scoring because the field was never populated.
- Verdict: INVALID (not shipped; no output).
- Most important fix: fail loud when `CENSUS_API_KEY` is absent, or remove the registration until a key is provisioned.

## Other probes

- HIFLD hub `hifld-geoplatform.opendata.arcgis.com` returns 200. NCCS mirror `maps.nccs.nasa.gov` returns no response (000), consistent with data-source-research.
- Parcel and NRI spot checks were 3 sites each. The validator covered infra only.
- Agents spawned: none. Tool calls used: about 46.

## Summary table

| source | publisher | verdict | vintage | coverage | biggest issue | fix |
|---|---|---|---|---|---|---|
| infra-proximity (transmission, gas, power plant, roads, rail, OSM substations, NFHL) | HIFLD, Census TIGER, OSM, FEMA | VALID-WITH-CAVEAT | HIFLD transmission edit 2023-09; gas and plants 2025-07; roads and rail 2026-01; retrieval dates unknown | 96–99% per distance; flood 91.1% assessed | Unknown retrieval dates; 44% of substation picks are distribution-class; 4,183 legacy flood rows unverified | Record real fetch dates; reassess or relabel legacy flood rows; restrict substation signal to transmission-class |
| fema-nri | FEMA (hosted on ArcGIS Online) | INVALID (join); values VALID | Data edit 2025-12-16; output generated 2026-06-08 | 76.5% | Multipart counties silently unmatched (DE 25/25, 24.8% of Superfund) | Multipart-aware `PolygonIndex`; rebuild and report coverage per state |
| opportunity-zone | HUD | VALID-WITH-CAVEAT | Designations 2018; layer edit 2026-02-24 | 34.4% (16,090) | Shared index defect may undercount; 25 IDs pending | Fix index; re-measure pending IDs |
| ira-energy-community | DOE NETL | VALID-WITH-CAVEAT | 2024 layers; no edit date | 31.6% (14,790) | FFE county multipart undercount likely (unmeasured); `energycommunities.gov` cited but dead | Fix index; measure FFE coverage independently |
| iso-rto | EIA | STALE | Generated 2026-06-05, frozen | 96.3% | Source now returns error 499 Token Required; cannot refresh | Replace with public EIA download or freeze with vintage banner |
| tribal-areas | Census TIGERweb (AIANNHA) | VALID-WITH-CAVEAT | Current TIGERweb, rolling | 2,122 positives | Multipart reservations likely undercounted | Multipart-aware index; re-measure |
| climate-zone | Third-party ArcGIS org (cited as PNNL) | INVALID (provenance) | Data edit 2021-03-25 | 97.4% | Hosted in a personal org with test items; cited PNNL is not the source | Source from PNNL/BASC county file and cite it |
| water-proximity + streamgages | USGS | VALID-WITH-CAVEAT | Generated 2026-09-12; legacy API retiring Feb 2027 | 98.2% flow | Mean annual flow read as availability; legacy endpoint retiring | Migrate to api.waterdata.usgs.gov before Nov 2026; keep mean-flow disclosure |
| parcel-owner | State GIS (11 states) | VALID-WITH-CAVEAT (MT STALE) | Varies by state; Iowa 2017; NJ, VT, MA edited Aug 2026 | Owner 15.5%; parcel acreage 10.9% | Montana endpoint returns HTML (dead); MN unconfirmed | Disable or repoint MT; confirm MN; show per-state vintage |
| census-workforce | US Census ACS | INVALID (absent) | ACS 5-year; key required | 0 (no output) | Without `CENSUS_API_KEY` returns redirect, no data, no loud failure | Fail loud or unregister until key provisioned |
