# Program data source audit (A)

Date: 2026-10-18. Read-only audit of the connectors and output files in `docs/data/`. Live checks were run with `curl`/`urllib`, a `User-Agent` of `brownfield-audit/1.0`, and a 1.5 s pause between requests. ArcGIS error objects were checked on every query. Scratch files are in the scratchpad `audit/` folder. Importing `connectors.*` may have refreshed `__pycache__`; no repo file was edited.

## 1. EPA NPL (`superfund-npl.json`, `sites.json`)
- Endpoint: `services.arcgis.com/cJ9YHowT8TU7DUyn/.../FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0` (EPA). Current: lastEditDate 2026-10-17.
- Ours: 1,908 records, generated 2026-09-25. Live: 2,114 features = 1,908 unique EPA_IDs. Exact set match (no missing or extra ids).
- Spot check 5/5: name, state, centroid and acreage match the live feature (e.g. Iron Horse Park 438.5 ac = GIS_AREA 438.47).
- `sites.json` is a byte-identical mirror of `superfund-npl.json`.
- Semantics: acreage is EPA's boundary polygon. Boundary artifacts are real: Tar Creek 310,173 ac (Ottawa County outline; Oklahoma DEQ says 25,600 ac). Harbor Oil 156,219 ac with state null (EPA profile: 4.2 ac). Central City/Clear Creek 252,409 ac. Lat/lon is the bbox midpoint, not a centroid.
- 14 live features have a null `NPL_STATUS_CODE`. Ours carry a status for those ids, apparently inherited from sibling features. Minor.
- Verdict: VALID-WITH-CAVEAT. Fix: flag acreage that exceeds the EPA profile figure or county area, and show the profile acreage beside it.

## 2. EPA ACRES (`epa-acres.json`)
- Endpoint: `services.arcgis.com/cJ9YHowT8TU7DUyn/.../All%20ACRES%20Properties%208_30_2021/FeatureServer/0`. FROZEN: name and editingInfo both say 2021-08-31.
- Ours: 36,003 records, generated 2026-05-12. Live: 36,003. Exact match.
- Spot check 5/5: name, state and lat/lon match exactly (live point geometry equals LATITUDE/LONGITUDE_MEASURE).
- The source has no acreage at all. Coordinates are point geocodes. 5,434 brownfield sites share a coordinate with another site; the most-shared point (44.86361, -93.02911) has 97 sites.
- County is filled offline from TIGER; about 51% of records needed it.
- Verdict: STALE (the upstream is a five-year-old snapshot). Coordinates are valid as the source's own geocodes. Fix: label the UI "EPA ACRES snapshot, Aug 2021", and find a live ACRES source.

## 3. ACRES cleanup (`acres-cleanup.json`)
- Endpoint: `services.arcgis.com/cJ9YHowT8TU7DUyn/.../ACRES_cleanups_10_19_21/FeatureServer/0`. FROZEN: 2021-11-02.
- Ours: 105. Live: 110. The 5 missing rows (Property_IDs 250415–250419) have no record in the main ACRES layer, so dropping them is correct. Status counts match for the other 105 (ours Closed 73, Open 32; live Closed 73, Open 37 including the 5 orphans).
- Semantics: `cleanup_status` is the CA_Status of a cooperative agreement, not the site's cleanup status. 70 of 110 rows are CA_Type "Section 128(a) State/Tribal" grants. The connector docstring says the values are Completed / In Progress / Not Started, but the live values are only Closed and Open.
- Coverage is 105 of 36,003 ACRES properties (0.3%).
- Verdict: INVALID as a site-cleanup status (valid as a grant-agreement status). Fix: rename to `grant_ca_status`, correct the docstring, and do not show it as cleanup status.

## 4. DOD FUDS (`dod-fuds.json`)
- Endpoints: `services7.arcgis.com/n1YM8pTrFmm7L4hs/.../fuds/FeatureServer/1` (points) and `/4` (polygons). USACE. Current: both edited 2026-10-07.
- Ours: 8,821 unique ids. Live layer 1: 10,123 rows, 10,109 unique PKs. Every one of our 8,821 has live coordinates, and the id sets match exactly.
- 1,301 live rows (1,288 unique PKs) are dropped for null or zero lat/lon. Of the dropped PKs: 118 Eligible, 43 Categorical Exclusion, 907 Ineligible, 233 blank. Top states NY 211, FL 188, TX 161. None are shown or flagged on the dashboard.
- Spot check 5/5: name, state, coordinates and owner text match. Camp Bouse acreage 349,070.5 equals the L4 polygon area.
- Semantics: lat/lon is the L4 polygon centroid when a polygon exists, otherwise the L1 point. For Camp Bouse that moves the marker about 9 mi from the USACE point (34.028 vs 33.917).
- Owner prettifier: "Blm:" is not uppercased, and repeated free text is kept ("State of Arizona, State of Arizona").
- Verdict: VALID-WITH-CAVEAT. Fix: keep the coordinate-less properties as "location unknown" rows instead of dropping them, and add BLM to the owner acronym list.

## 5. DOD BRAC (`dod-brac.json`)
- Endpoint: `services.arcgis.com/hRUr1F8lE8Jq2uJo/.../milbases/FeatureServer/0`, where `BRAC_SITE='YES'`. Layer edited 2021-06-10.
- Ours: 27. Live: 27. Spot check 5/5 exact (name, state, polygon acreage, centroid).
- Semantics: acreage is the whole installation footprint (Lone Star AAP 15,318 ac), not redevelopable land. The lat/lon is the bbox center.
- Verdict: VALID-WITH-CAVEAT. Fix: label acreage "installation footprint".

## 6. EPA RE-Powering (`epa-redev.json`)
- Endpoint: `services.arcgis.com/cJ9YHowT8TU7DUyn/.../RedevelopmentAppSitePoints/FeatureServer/0`. Current: edited 2026-07-24. The layer name is now "Superfund Site Points", so the connector's name is stale.
- Ours: 1,904. Live: 1,904. Spot check 5/5 exact (name, state, lat/lon, acres to rounding). `data_center_reuse_candidate` recomputes exactly from the record (validator: 1,904/1,904).
- Verdict: VALID. Fix: update the layer name in the docs.

## 7. EPA ECHO enforcement (`epa-echo.json`)
- Endpoint: `echodata.epa.gov/echo/echo_rest_services.get_facilities?p_pid=<EPA_ID>` then `get_qid`. Live EPA service.
- Ours: 1,906 records. Registry ids: 1,897 with an id. 1,892 are in the cached ECHO responses, and 5 are not in the cache at all.
- Shared ids: 22 ECHO registry ids are bound to two or more Superfund sites (46 site records). Example: 110000476583 is bound to both MID980794440 and PAD004351003.
- Ossineke (MID980794440): ours binds 110000476583 with 5 inspections in five years. The current p_pid search and the cached response both return 110009292247, which has 0 inspections and 0 formal actions. 110000476583 does not appear in the cache.
- Name conflicts: of the 1,892 bound records, 399 (21%) have an ECHO facility name that differs from the NPL name. 70 of those carry formal actions or penalties. Examples: Reynolds Metals → FedEx Ground (ORD009412677, $38,403 formal actions plus penalties); Fort Wainwright → Doyon Utilities privatized emission units ($466,603); Palmerton Zinc Pile → Befesa Zinc ($10.2 M, the operator of the adjacent plant, arguable).
- Spot check 5/5 found the same registry id when the search was rerun, but the enforcement counts disagreed on Ossineke.
- Verdict: INVALID for attributing enforcement to the site. The p_pid join is many-to-one in places and name-unverified. Fix: accept a match only when the ECHO facility name agrees with the NPL name (or the ZIP or address agrees), flag shared registry ids, show the matched facility name in the UI, and re-fetch the 5 unresolved ids.

## 8. EPA Superfund documents (`epa-superfund-docs.json`)
- Endpoints: `cumulis.epa.gov/supercpad/SiteProfiles/index.cfm` (docdata) and `semspub.epa.gov/src/cachejson/...`. EPA. Current service.
- Ours: 1,887 sites, 1,810 with at least one document, 12,202 documents. No live count is possible because the docs are not indexed by a single service.
- Liveness: all four document URLs I tried timed out (HEAD and GET, 45–90 s each) from this environment. The result is inconclusive, not a confirmed dead link.
- The SF_SITE_ID hop (EPA pretty page to cumulis) was not spot-checked.
- Verdict: VALID-WITH-CAVEAT (liveness not verified). Fix: rerun a document-URL sample from a host with stable semspub access.

## 9. coord-quality (`coord-quality.json`, derived)
- No endpoint; derived from the NPL/ACRES/FUDS records and `us-states.json`.
- 3,991 records: brownfield 3,524, FUDS 460, Superfund 7. Flags: state_mismatch 118, shared_point 3,728, low_precision 190, placeholder 17, outside_us 2.
- Corpus check: 5,970 sites sit at 1,747 shared coordinates. The shared_point flag covers 3,728 of them, and the rule threshold is not written in the record.
- state_mismatch gaps: median about 1.6 mi, with a single outlier at 427 mi.
- I did not independently recompute the flag counts.
- Verdict: VALID (derived). Fix: document the shared_point threshold in the record.

## Site-research differences (`docs/data/site-research.json`)
- 33 dossiers, 125 validation rows: confirmed 55, unverifiable 50, differs 20.
- Differs by field: acreage 15, county 2, npl_status 1, coordinates 1, address 1.
- Causes:
  - Boundary scope vs the EPA profile's stated area: 12 acreage (AK6210022426, AL7210020742, CA1570024504, CA7210020676, ID4890008952, NVD980813646, OKD980629844, OR6213820917, SC1890008989, TN1890090003, TX4890110527, ORD071803985), plus 1 coordinates (OKD980629844) and 2 county (COD980717557, MOD981507585; single-valued county vs multi-county boundary).
  - Research-side unit error: 1 (WA3890090076). The note says the shipped 154.3 is square miles carried as acres. The live GIS_AREA_UNITS is "Acres" with 154.26, so our value is correct and the note is wrong.
  - Immaterial rounding: 1 (NY7890008975, 5,266.3 vs 5,265).
  - Null shipped value, research found a figure: 1 (FUDS-C03VA1071, USACE says 1,740 ac).
  - Portion-level vs site-level status: 1 (CA7210020676, Fort Ord partial deletion; the site-level status is correct).
  - Alias in the address field, not cleaned: 1 (ORD071803985).
- Takeaway: 13 of the 20 differences trace to EPA polygon scope. One is a research error and should be corrected.

## Cross-cutting
- Vintage: NPL, FUDS and RE-Powering are current. ACRES, ACRES cleanup and BRAC are 2021 snapshots. ECHO and docs are live services.
- The validator (`scripts/validate_data.py --fail-on NEVER`) passes all structural, geo, infra and derived checks. It cannot see any issue above, because it checks internal consistency and not source semantics.
