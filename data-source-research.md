# Data-source query log

Verified API probes against candidate data sources, with what each one found.
Purpose: stop future agents (and fan-out subagents) from re-running the same
discovery sweeps or re-trying known dead ends. **Before probing a federal
GIS endpoint, check here first.** When you run a new probe, append it —
same format: date, exact query, finding, verdict.

Companion docs: structural dead-ends live in CLAUDE.md ("Structural data
gaps"); actionable follow-ups live in backlog.md.

---

## 2026-06-10 — "available land per site" research pass

### 1. EPA RedevelopmentAppSitePoints — full field schema

```
curl "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/RedevelopmentAppSitePoints/FeatureServer/0?f=json"
```

**Found:** 35 fields. No acres-in-reuse / available-acres field — only total
`Acres`. Fields the connector does NOT yet pull that may matter later:
`Site_ID` (SEMS site id — a free EPA_ID↔SF_SITE_ID crosswalk for ~1.9k sites;
the epa-superfund-docs connector currently scrapes HTML for this hop),
`NPL_Stat_1`, `Constructi` (construction-complete status), `ReusePlanN` /
`ReusePlanU` (reuse-plan name + URL), `SRP_Doc_Link` / `SRP_Doc_Name`,
`Snapshot_Link`. Already pulled but dropped in normalize: `RAU_Status`.

**Verdict:** no direct "available acres" here, but `RAU_Status` and the
`Site_ID` crosswalk are unwired quick wins.

### 2. RAU_Status (Sitewide Ready for Anticipated Use) value survey

```
curl ".../RedevelopmentAppSitePoints/FeatureServer/0/query?where=1%3D1&outFields=RAU_Status&returnGeometry=false&f=json&resultRecordCount=2000"
```

**Found:** 488 "Meets the Measure" · 444 "Does Not Meet the Measure" ·
43 "Does Not Meet the Measure (Retracted)" · 7 "Meets the Measure (Formerly
Retracted)" · 18 null. Values are also already present in the local fetch
cache (`data/cache/epa-redev_*.json`) — wiring it through is zero new HTTP.

**Verdict:** the single best public per-site land-availability signal for
Superfund. SWRAU = EPA's own formal "all land ready for anticipated use"
performance measure. Backlog item filed.

### 3. EPA GeoPlatform org — service enumeration

```
curl "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services?f=json"
# then filter names by /redev|reuse|RAU|superfund|NPL|brownfield|acres/i
```

**Found:** 2,282 services on the org (it hosts the whole EPA GeoPlatform, not
just redevelopment). Relevant hits:

| Service | Geometry | Notes |
|---|---|---|
| `FAC_Superfund_Site_Boundaries_EPA_Public` | polygon | **2,114 features** ≈ full NPL coverage; keyed `EPA_ID`, has `GIS_AREA`+units |
| `FAC_Superfund_Institutional_Control_Boundaries_EPA_Public` | polygon | **165 features only** — IC digitization is structurally sparse |
| `FAC_Superfund_Operable_Unit_Boundaries_EPA_Public` | polygon | **239 features only** — same sparsity |
| `Superfund_Sites_In_Reuse` | point | No acres field; keys by SEMS `Site_ID`, not EPA_ID |
| `ACRES_cleanups_10_19_21` | — | 110 features, frozen Oct-2021 (known dead end, CLAUDE.md gap #6) |
| `Brownfield_Properties_Over_100_Acres_view` | — | curated subset, not a data source |
| `FRS_INTERESTS_ACRES` / `FRS_INTERESTS_SEMS_NPL` | — | FRS facility-interest joins, unexplored |

Counts came from `…/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json`.

**Verdict:** site-boundary polygons are available in one clean layer (useful
if we ever want polygons without re-paginating the NPL FeatureServer), but
IC/OU layers are too sparse for a "site minus restricted area" computation.
Don't revisit ICs without evidence EPA backfilled the layer.

### 4. FWS National Wetlands Inventory REST

```
curl "https://fwsprimary.wim.usgs.gov/server/rest/services/Wetlands/MapServer?f=json"
```

**Found:** live and public, `maxRecordCount` 1000. (The `layers` array came
back empty in the root probe — query sublayer 0 directly when implementing;
the service responds.)

**Verdict:** viable per-site bbox-query source for the proposed
`developable-land` connector (wetland-fraction subtraction). Live-verified
2026-06-10.

### 5. EPA geodata server (geodata.epa.gov)

```
curl "https://geodata.epa.gov/arcgis/rest/services?f=json"
curl "https://geodata.epa.gov/arcgis/rest/services/OSWER?f=json"
```

**Found:** folder list (AgSTAR, OSWER, OEI, OW, regions…) but the OSWER
folder contains only `EPA6kQuads` — **the SEMS spatial layers do NOT live
here**; they live on the ArcGIS Online org in (3).

**Verdict:** dead end for Superfund spatial data; don't re-probe.

---

## 2026-06-10 — scoring-v3 local data surveys (no HTTP — run against `docs/data/*.json`)

### 6. infra-proximity.json field coverage

**Found (46,760 records):** `substation_kv` 34,070 · `transmission_kv` 46,211 ·
`substation_mi` 46,328 · `power_plant_*` 46,496 · `flood_zone`/`in_sfha` 9,900
(backfill in progress) · zero records have transmission_mi set with null
transmission_kv *and* a substation_kv — so a kv-fallback chain is pointless,
but substation_kv as a *quality* signal was unused (fixed in v1.20).

### 7. substation_kv class distribution

**Found:** <69 kV (distribution-class): **7,087** · 69–114: 8,684 ·
115–229: 15,756 · ≥230: 2,543 · null: 12,690. Motivated the v1.20
distribution-class substation discount.

### 8. eia-retired-plants.json proximity/recency distribution

**Found (7,620 records):** 573 sites ≤1 mi of a ≥100 MW retired plant
(MW min/median/max = 100 / 249 / 2,151.8); **3,299 sites in the 1–3 mi band**
(previously scored 0 — motivated the v1.20 half-credit band); retirement
years spread 2002–2025 with big mass pre-2013 (motivated the recency decay).

---

## 2026-06-19 — retired heavy-industrial assets (smelters / mills / manufacturing)

Goal: surface retired industrial sites NOT in our data (aluminum smelters,
steel/paper mills, etc.). These carry the largest stranded grid interconnects
in the country — an aluminum smelter is ~300–700 MW of continuous load — so a
retired one is a top-tier DC-conversion candidate (the Alcoa / Century pattern).

### 9. EPA GHGRP via Envirofacts REST — **WORKS, recommended programmatic source**

`https://data.epa.gov/efservice/PUB_DIM_FACILITY/<filter>/ROWS/a:b/JSON` is
LIVE (probed 2026-06-19). Returns per-facility rows with `latitude`,
`longitude`, `city`, `state`, `facility_name`, `naics_code`, `year`,
`program_name`. ~8,000 large emitters/yr since 2010. **Closure is inferable by
report-dropout**: a facility reporting through year N then absent afterward is
very likely idled/closed. Verified counts (distinct facilities, geocoded):
iron/steel mills NAICS **331110 → 68 facilities, 2016–2023**; cement **327310
→ 9**; paperboard **322130 → 7**. **Quirk:** NAICS **331313** (primary
aluminum) returns HTTP 500 on the `/NAICS_CODE/331313/` filter (other NAICS are
fine) — query aluminum via FLIGHT subpart C or parent `3313`, not this code.
Filter syntax: `…/PUB_DIM_FACILITY/NAICS_CODE/<code>/ROWS/0:400/JSON`. Best path
for the broad "retired manufacturing plant" universe (steel / cement / paper /
chemicals / glass). A connector would diff years per facility and emit those
whose last report year < latest GHGRP year, with sector + a crude MW proxy.

### 10. USGS primary aluminum smelters — **curated overlay, highest MW/site**

Authoritative source is USGS Mineral Commodity Summaries (annual PDF,
`pubs.usgs.gov/periodicals/mcs2026/mcs2026-aluminum.pdf` — WebFetch can't parse
the PDF and the Read tool needs `poppler`; use `pdftotext`). Small universe:
2025 = 6 operating smelters in 5 states, 2 idled (Hawesville KY since 2022,
New Madrid MO since 2024). Recently closed: New Madrid MO (Jan 2024, 263k tpy),
Wenatchee WA (idled 2015 → closed 2021), Massena East NY (2015), Ravenswood WV
(idled 2009 → closed 2015). Best as a hand-curated `docs/data/retired-
industrial.json` overlay (same pattern as `reference-campuses.json`) — ~15–20
rows, lat/lon + status + capacity + MW + closure year + source. Highest
signal-per-row of any option here.

### 11. WARN Act plant-closure notices — recent closures, geocoding required

Federal/state WARN notices list company + address + date for plant closings
(~last 2 yr coverage). Aggregators exist (warnfirehose.com — 85k notices, API
gated to paid; warntracker.com — partial free); many state DOL pages publish
free (CA EDD, NY DOL) but fragmented and addresses need geocoding. Good for VERY
recent closures; lower priority than GHGRP (already geocoded + national).

### 12. Not yet probed (candidates for next pass)
- **EPA TRI** via Envirofacts — same report-dropout method, lower threshold →
  broader (~21k facilities), more small sites.
- **EPA FRS** (Facility Registry Service) — master facility list; some rows
  carry an operating-status field + NAICS; filter inactive + industrial NAICS.
- **USGS Mineral Operations** ArcGIS layer — active mines & mineral plants with
  status; check for a public FeatureServer.

---

## 2026-06-19 — parcel OWNER verification via public state cadastral layers

CLAUDE.md gap #7 said nationwide parcel-owner data is "impossible publicly"
(true — no single free source). But MANY states publish a free statewide
parcels layer with owner NAMES via ArcGIS REST, queryable by point. Spot-check
proved this is very much possible state-by-state.

### 13. NC OneMap statewide parcels — **WORKS, no token needed**

`https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer`
— layer **0 = points (centroids), layer 1 = POLYGONS** (use layer 1 for
point-in-polygon owner lookup; querying layer 0 by point returns nothing —
that was the first-try miss). Point query:
`…/1/query?geometry=<lon>,<lat>&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=ownname,gisacres,parno&returnGeometry=false&f=json`.
Despite the `secure/` path it needs **no token** for Query. Fields: `ownname`
(owner), `mailadd`/`mcity` (mailing addr), `gisacres`, `parno` (parcel id),
`cntyname`. **Validation:** Ore Knob Mine Superfund → `ownname`="REEVES THOMAS
G & EVELYN", `gisacres`=147.1 vs our acreage 148.2 (right parcel). A 40-site NC
batch (superfund+FUDS) hit **38/40 (95%)** named owners — DOMTAR PAPER CO,
CHEMTRONICS, AKZO NOBEL, CLARIANT, GE SUBSIDIARY, WARREN COUNTY, individuals.
The 2 misses: a federal megasite (Camp Lejeune — military reservation isn't in
county parcels) + 1 off-parcel point. **ACRES brownfields hit lower** — their
coords are address-geocodes that sometimes land just off the parcel polygon.
Built into `connectors/parcel_owner.py` (`STATE_PARCEL_SOURCES["NC"]`).

### 14. TX StratMap parcels (TxGIO) — endpoint host unresolved from sandbox

StratMap aggregates ~245 appraisal districts statewide. Endpoint per search:
`https://feature.tnris.org/arcgis/rest/services/Parcels/stratmap25_land_parcels_48/MapServer/0`
— but `feature.tnris.org` (and a guessed `feature.txgio.org`) did **not resolve
via DNS** from the dev sandbox (TNRIS→TxGIO rename, 2025). Could be a sandbox
network restriction or a host change. Stubbed (commented) in the registry —
confirm the live host in the deploy env before enabling. Owner field per
StratMap schema is `OWNER_NAME`.

### 15. The per-state registry approach (the plan)

No nationwide source, but the connector's `STATE_PARCEL_SOURCES` registry makes
coverage incremental: one verified `{base, owner_field, source}` entry per
state. Next states to verify (states with known free statewide layers): TX
(StratMap, host TBD), and any state whose GIS portal hosts a parcels
FeatureServer with an owner field — probe each with the point-query pattern
above + `outFields=*` to discover its owner field name before adding. Federal
megasites and ACRES address-geocodes are the structural miss classes.

---

## 2026-06-25 — AP1000 water-availability validation (14 installations)

Full per-site validation with verbatim quotes + verdicts lives in
[`ap1000-water-validation.md`](ap1000-water-validation.md). Reusable findings:

### 16. USGS NWIS streamflow — use the RDB endpoints, NOT the JS portal — **WORKS**
- `waterdata.usgs.gov/monitoring-location/<id>/` is JavaScript-rendered → returns
  nothing to WebFetch/curl. Five separate agents each burned tokens rediscovering
  this. Use the machine-readable RDB endpoints instead:
  - Drainage area + site metadata: `https://waterservices.usgs.gov/nwis/site/?format=rdb&sites=<GAUGE>&siteOutput=expanded` (field `drain_area_va`).
  - Annual mean discharge (cfs): `https://waterservices.usgs.gov/nwis/stat/?format=rdb&sites=<GAUGE>&statReportType=annual&statTypeCd=mean&parameterCd=00060`.
  Plain tab-delimited text — scriptable, exact, **no LLM needed** for the numbers.
- **Regulated rivers often publish stage-only at the convenient gauge** (Cape Fear
  @ Fayetteville 02104000; Cumberland @ Clarksville 03436500) → step to the
  nearest discharge gauge (Lillington 02102500; Nashville 03431500) and reason
  about drainage-area scaling.
- Gauge IDs validated (site → USGS gauge): Holston AAP `03487500`; Redstone
  `03575500`/`03575750`; Benning `02341460`; Robins `02213700`/`02213000`; Drum
  `04260500`; Wainwright `15514000`/`15515500`; JBLM `12089500`; Bragg `02102500`
  (Cape Fear) / `02103000` (Little R, too small); Campbell `03431500`; Arnold
  `03579100`/`03580750`.

### 17. AP1000 water demand — Vogtle 3&4 EIS; NRC servers time out, use the DOE mirror
- Per AP1000 unit (natural-draft cooling tower): **~26.8 MGD (41.5 cfs) withdrawal;
  ~20.1 MGD (31.1 cfs / ~22,400 acre-ft/yr) consumptive.** Two units: 53.6 / 40.2
  MGD; max 83.2 MGD (129 cfs); Georgia EPD permit cap 74 MGD. Main cooling is
  **natural-draft**, not mechanical-draft (mechanical is the auxiliary SWS only).
- **`nrc.gov/docs` times out frequently** — the DOE EIS-0476 mirror reproduces the
  NUREG-1872 text verbatim and is reliable:
  https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf
  (AP1000 DCD Ch 9.2: https://www.nrc.gov/docs/ML0715/ML071580932.pdf).

### Agent-efficiency post-mortem (token spend)
- 5 research agents (~520K tokens total; ~186K for the 2 the user flagged)
  validated 14 sites + the AP1000 spec. The result was high-value (4 source/rating
  corrections, citation-grade), so the spend was largely warranted — but **~25–30%
  was avoidable**: each agent independently rediscovered the USGS RDB endpoints +
  the DOE mirror. Now that §16/§17 log the gauge IDs + endpoints, the flow/drainage
  numbers are deterministically fetchable with `curl` — a future validation should
  script those and reserve a single agent for qualitative quote-finding only.

---

## 2026-07-02 — GHGRP per-facility citation URLs + EIA-860M planned retirements

| Query | Finding | Verdict |
|---|---|---|
| `ghgdata.epa.gov/ghgp/service/facilityDetail/<year>?id=<fid>&ds=E&et=&popup=true` | HTTP **404** with both the latest GHGRP year and the facility's own last-report year — the FLIGHT detail service is not addressable this way. | ✗ don't use |
| `enviro.epa.gov/envirofacts/ghg/facility-detail/<facility_id>` | HTTP **200**, human-readable Envirofacts GHG facility page, keyed by the same `facility_id` our `GHGRP-<id>` overlay ids carry. | ✓ canonical per-facility citation link |
| EIA-860M **Operating** sheet, `Planned Retirement Year/Month` columns | 134 dispatchable generators with announced retirement dates; grouped by Plant ID and filtered ≥100 MW → **90 plants / 75,573 MW**, 2026–2043, with lat/lon + BA code. Same cached workbook as the Retired sheet (`51f37f3890e1b51e.bin`, archive URL). | ✓ powers `planned-retirements.json` |

Also verified: joining the retired-industrial overlay to the tracked corpus by
1-mile Haversine (bbox prefilter) links 214/658 sites — enough to make the
tracked record the default parcel-availability evidence surface.

---

## 2026-07-05 — parcel registry expansion (owner + developable acreage)

### 18. Statewide parcel layers — NJ / VT / CT added; NY / MA rejected

Discovery via the ArcGIS-Online search API (`arcgis.com/sharing/rest/search?q=<state>+statewide+parcels+owner&f=json`, filter results to `Feature Service` owned by the state GIS org), then confirmed each candidate by reading `<layer>?f=json` field metadata + a live point-intersect and a `where=<owner> IS NOT NULL` sample. All queryable with **no token**.

| State | Service (official owner) | owner / acreage / id fields | Verdict |
|---|---|---|---|
| NJ | NJOGIS `Parcels_Composite_NJ_WM/FeatureServer/0` | `OWNER_NAME` / `CALC_ACRE` / `PAMS_PIN` | ✓ added. Point HIT at a Camden site: CALC_ACRE 1.92, PIN `0408_1279.01_8`. **Owner is frequently BLANK** in the MOD-IV composite → many NJ records are acreage-only (the parcel_acreage-without-owner path). |
| VT | VCGI `FS_VCGI_OPENDATA_Cadastral_VTPARCELS_poly_standardized_parcels_SP_v1/FeatureServer/0` | `OWNER1` / `ACRESGL` / `MAPID` | ✓ added. Sample owner "WEST NANCY". ACRESGL = grand-list acres (0 → dropped by the >0 guard). |
| CT | CT GIS Office `Connecticut_CAMA_and_Parcel_Layer_2024/FeatureServer/0` | `Owner` / `Land_Acres` / `Parcel_ID` | ✓ added. Sample "CACCHIONE ROBERT" / 1.13 ac / `134-41A`. |
| MA | MassGIS `Massachusetts_Property_Tax_Parcels/FeatureServer/0` | `OWNER1` / `LOT_SIZE`+`LOT_UNITS` / `LOC_ID` | ✓ added (2026-07-05, same day). Lot size is `LOT_SIZE` with a **per-record `LOT_UNITS`** whose values are the full words **"Acres" (2.28M) / "Sq. Ft." (264k)** — NOT `A`/`S`. Handled by the connector's new `acreage_units_field` + `acreage_units_map` (`{"ACRES":1.0,"SQ. FT.":1/43560}`); unknown unit → no acreage. |
| NY | NYSGIS_GPO `NYS_Tax_Parcels_Public/FeatureServer/0` | — | ✗ rejected. Layer 0 is **municipal boundaries** (NAME/GNIS/POP/SWIS), not parcels; the public NY parcel product carries **no owner name** (owner is county-restricted). |

Point misses on the ACRES address-geocodes are the documented off-parcel class (same as NC) — Superfund/FUDS polygon-derived coords hit more reliably. PA has **no** statewide parcel layer (county-by-county) — search returned only unrelated services.

## Reusable probe patterns

- USGS streamflow without the JS portal: `waterservices.usgs.gov/nwis/site/?format=rdb&sites=<id>&siteOutput=expanded` (drainage area) + `…/nwis/stat/?format=rdb&sites=<id>&statReportType=annual&statTypeCd=mean&parameterCd=00060` (annual mean cfs). A federal PDF that NRC serves slowly often has a DOE/energy.gov mirror.
- Parcel owner by point (ArcGIS): `<parcels_layer>/query?geometry=<lon>,<lat>&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&returnGeometry=false&f=json` — use the POLYGON layer, not a centroid/point layer.
- ArcGIS service inventory: `https://<host>/arcgis/rest/services?f=json`
  (+ `/​<folder>?f=json`); layer schema: `…/FeatureServer/<n>?f=json`;
  row count: `…/query?where=1%3D1&returnCountOnly=true&f=json`;
  value survey: `…/query?where=1%3D1&outFields=<col>&returnGeometry=false&f=json&resultRecordCount=2000`.
- Field-coverage survey of an on-disk enrichment file: count non-null per key
  across `json.load(open('docs/data/<file>.json'))['sites']`.
- When fanning out discovery agents: give each ONE host/org to enumerate and
  this file's table format to return — and have them check this log first.

## 2026-07-26 — parcel registry expansion round 2 (FL / CO / IA / MN added; 8 states rejected/blocked)

Worked the priority list ranked by count of owner-less sites: MI, FL, IL, MO, OH,
IN, TX (retry), AZ, MN, IA, KS, CO. 4 verified, 8 rejected/blocked — list
exhausted. Discovery via ArcGIS Online sharing search
(`arcgis.com/sharing/rest/search?f=json&q=...`) and targeted web search, then
confirmed each candidate by reading `<layer>?f=json` field metadata + a live
point-intersect query against a real site coordinate from this repo's own
`docs/data/sites.json` / `epa-acres.json`. (Probes run by a Sonnet research
agent, 2026-07-26; registry rows landed in `connectors/parcel_owner.py` the
same day with an `acreage_multiplier` extension for FL's fixed sq-ft units.)

### 19. Michigan — REJECTED, no statewide ownership layer

`https://www.mcgi.state.mi.us/arcgis/rest/services?f=json` → 22 folders
(BaseMap, BOE, DCH, DEQ, DHHS, DHS, DNR, DTMB, E911, EGLE, LEO, MDCR, MDE,
MDOS, MDOT, MEDC, MPSCS, MSHDA, MSP, TAMC, Utilities, WAMC), none contain
parcels. `https://gis-michigan.opendata.arcgis.com/api/feed/dcat-us/1.1.json`
→ 731 datasets, 30 "parcel"-titled, all DNR public-land management
(Commercial Forest Parcels, Mineral Leases, Mineral Lease Nominations, DNR
Parcels) — zero general private-ownership coverage. **Verdict:** no statewide
source exists publicly; don't re-probe without new evidence.

### 20. Florida — WORKS, statewide, no token

`https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0?f=json`
→ FDOR Cadastral 2025, 121 fields, `OWN_NAME` (owner), `LND_SQFOOT` (land area
in **square feet**, DOR NAL fixed convention — not acres), `PARCEL_ID`. Point
query at ACRES-233121 (Opa-locka) → `OWN_NAME`="GSI OPA LOCKA OWNER LLC",
`LND_SQFOOT`=16834; ACRES-13489 (Clearwater) → "CLEARWATER, CITY OF". Two of
five test points landed off-parcel (same ACRES address-geocode miss class as
NC/NJ). **Verdict:** added to `STATE_PARCEL_SOURCES["FL"]` with
`acreage_multiplier = 1/43560` (new optional registry key for layers with a
fixed non-acre unit and NO per-record units column; the MA
`acreage_units_field` mechanism can't express this).

### 21. Colorado — WORKS, statewide, no token, cleanest schema of the batch

`https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0?f=json`
→ "Colorado_Public_Parcel_Composite" (Governor's OIT), 34 fields, `owner`,
`landAcres` (native acres, no conversion needed), `parcel_id`, `countyName`.
3/3 live point queries hit: Denver-area Superfund site → owner "DE JESUS
PASILLAS MARIA AND" / 0.73 ac; Lakewood ACRES site → "DEPARTMENT OF
TRANSPORTATION" / 0.277 ac; Fort Collins → "CITY OF FORT COLLINS" (landAcres
null for this one — govt-exempt parcel, same null pattern as VT). **Verdict:**
added to `STATE_PARCEL_SOURCES["CO"]` — no caveats beyond the routine
null-guard already in the connector.

### 22. Iowa — WORKS but data is 2017 vintage; no clean acreage field

`https://www.arcgis.com/sharing/rest/content/items/d653c8836f344d17af8ee45d2176760f?f=json`
→ "Iowa Statewide Parcel Data, 2017" (Iowa Dept. of Homeland Security &
Emergency Management, mirrored by a U. Iowa ArcGIS account), service:
`https://services3.arcgis.com/kd9gaiUExYqUbnoq/arcgis/rest/services/Iowa_Parcels_2017/FeatureServer/0`.
Fields: `DEEDHOLDER` (owner), `STATEPARID`, `COUNTYNAME`, only `Shape__Area`
for size (service SR is Web Mercator wkid 3857 — area is distorted by
~sec(lat)^2, unusable as acreage without a cos(lat) correction this connector
doesn't do). 3/3 live point queries hit: West Des Moines → "IOWA CONCRETE
PRODS CO"; Waterloo → "RITTER GARY C"; Ottumwa → "Carpenter  Gary" (note
double-space in source data). **Verdict:** added to
`STATE_PARCEL_SOURCES["IA"]` owner+parcel_id only (no acreage_field); the
source label carries the 2017 vintage so UI provenance is honest.

### 23. Kansas — BLOCKED, county-fragmented (+ host 503 at probe time)

ArcGIS Online title search `title:"Kansas" AND title:"Parcels"` → only
individual county accounts (`ckcoks`=Cherokee, `oscoks`=Osage, `sucoks`
=Sumner, `ursgis_coffeycountyks`=Coffey), plus a DASC-owned "County GIS
Websites" resource pointer confirming the state delegates to counties.
`https://services.kansasgis.org/arcgis1/rest/services?f=json` → HTTP 503
(Service Unavailable) on 2 attempts 3s apart — transient outage, doesn't
change the fragmentation finding. **Verdict:** no statewide source; same class
as PA/IL/MO/AZ.

### 24. Texas — retry: host migrated, schema great, Query token-walled

DNS/reachability retest: `feature.tnris.org` → `curl` HTTP 000 (dead — real
retirement, not a sandbox artifact); new host `feature.geographic.texas.gov`
→ HTTP 200, live service directory with a `Parcels` folder containing
`stratmap_land_parcels_48_most_recent` (MapServer). Metadata
(`.../Parcels/stratmap_land_parcels_48_most_recent/MapServer/0?f=json`) shows
`owner_name`, `gis_area`+`gis_area_unit` (real per-record units field),
`prop_id`, `capabilities: Query,Map`. Live query
(`.../MapServer/0/query?where=1=1&outFields=owner_name&resultRecordCount=1&f=json`)
→ `{"error":{"code":400,...,"message":"Requested operation is not supported
by this service."}}` on 3 separate attempts (point-intersect, count-only,
plain list; with and without browser UA/Referer headers). A sibling versioned
service (`stratmap25_land_parcels_48`) returns `"Token Required"` (code 499)
for the same call. **Verdict:** still blocked — TxGIO now requires an
authenticated token for anonymous Query despite advertising the capability
publicly. This SUPERSEDES the 2026-06-19 "host didn't resolve" theory; the
host is fine now, the access policy is the blocker.

### 25. Minnesota — WORKS but opt-in coverage + non-commercial license caveat

`https://www.arcgis.com/sharing/rest/content/items/dac59d514baf4d2c84491cd8ce4d2bf9?f=json`
→ "Minnesota parcels open data counties" (MPCA account), service
`https://pca-gis02.pca.state.mn.us/arcgis/rest/services/base/parcels_open_data_counties/MapServer/0`.
Item snippet: "compilation of county parcel data from Minnesota counties that
have opted-in... intended for non-commercial use." Schema follows the MN GAC
Parcel Data Standard: `owner_name`, `acres_poly` (GIS-computed, reliable),
`acres_deed` (legal-recorded, frequently 0), `state_pin`. 3/3 live point
queries hit: Minneapolis → "Hennepin Co Regional Rr Auth" / 2.03 ac; South St.
Paul → "Schadegg Properties Ii Llc" / 5.515 ac; St. Cloud → "Sanvik
Development Llc" (acres_poly null this time). **Verdict:** added to
`STATE_PARCEL_SOURCES["MN"]` — this dashboard is a free non-revenue
public-interest tool, which fits the "non-commercial use" term; revisit if the
project's posture ever changes. Opt-in coverage means non-covered counties
tombstone like any other no-match.

### 26. Ohio — statewide layer exists, REJECTED for no owner field

`https://services2.arcgis.com/MlJ0G8iWUyC7jAmu/arcgis/rest/services/OhioStatewidePacels_full_view/FeatureServer/0`
(OGRIP "Ohio Statewide Parcels Public View"): 21-field schema has
`MailAddressAll` but NO discrete owner-name field. Live query at 3 sites
confirmed the conflation: Painesville → "5 GREENWAY PL | SUITE #10 HOUSTON
77046" (address, no name); New Straitsville → "KNAPP GARY L JR NEW
STRAITSVILLE 43766" (name, no street); Elyria → "100 CAMPUS DRIVE FLORHAM
PARK 07932" (address only). **Verdict:** unusable as owner_field —
inconsistent format, no separate name attribute in the public view.

### 27. Indiana — statewide layer exists, REJECTED for no owner field

`https://gisdata.in.gov/server/rest/services/Hosted/Parcel_Boundaries_of_Indiana_Current/FeatureServer/0?f=json`
→ 31 fields, all geometry/address/tax-district (prop_add,
dlgf_prop_class_code, tax_county/township/city/school/library/special), zero
owner attribute. Checked the full `Hosted` folder (29 parcel/assessment-
adjacent services) and a second layer (`Parcels_2023`, 10 fields) — both
owner-less. **Verdict:** Indiana's public spatial layer is boundaries-only;
owner/CAMA data isn't joined in.

### 28. Illinois — REJECTED, no statewide layer

`https://clearinghouse.isgs.illinois.edu/arcgis/rest/services?f=json` → HTTP
404 (no live ArcGIS REST directory at the state clearinghouse). ArcGIS Online
title search → only scattered municipal/county services (Cook County, DeKalb,
Valmeyer test datasets), no state-level consolidation. **Verdict:** no
statewide source; consistent with Illinois's historically county-protective
parcel-data policy (Cook County commercial-resale litigation history).

### 29. Missouri — REJECTED, no statewide layer

MSDIS (University of Missouri) hosts imagery/PLSS/administrative boundaries,
not parcels-with-owner. Only owner-bearing statewide service found:
`https://ogi.oa.mo.gov/arcgis/rest/services/OA/FMDCrealEstate_StateOwnedParcels/MapServer`
— Missouri STATE-OWNED real estate only (Office of Administration). General
parcel-owner access is via paid aggregators only (Regrid, AcreValue,
Acres.com). **Verdict:** no statewide source.

### 30. Arizona — REJECTED, only state trust land is statewide

`https://azgeo.az.gov/arcgis/rest/services/asld/StateTrustParcels/FeatureServer/0`
— Arizona State Land Department Trust land only (~9% of AZ land area), not
general private ownership. Counties (Maricopa, Pinal, etc.) run independent
servers with inconsistent schemas and no state-level aggregator was found.
**Verdict:** no general statewide source; county-fragmented like PA/IL/MO/KS.

---

## §31 — DOE national-lab document hosts (probed 2026-08-09)

Logged while gathering [research/doe-lab-brownfield-reuse.md](research/doe-lab-brownfield-reuse.md). Host quirks
only; the findings live in that note.

| Host / URL | Result | Notes |
|---|---|---|
| `docs.nrel.gov`, `www.nrel.gov` | **DNS ENOTFOUND** | Did not resolve at all from this sandbox. Not a 404 — no A record returned. |
| `docs.nlr.gov` | **200** | Serves the same NREL documents. NREL PDFs dated 2026 carry the footer "National Laboratory of the Rockies" and cite `maps.nlr.gov/speed-to-power` *or* `maps.nrel.gov/speed-to-power`. Treat `nlr.gov` as the working host; verify before hardcoding either. |
| `eta-publications.lbl.gov` | **403 to WebFetch, 200 to curl** | Needs a browser User-Agent. Same class of bot-filtering as `hazards.fema.gov`. |
| `orsage.ornl.gov` | 200 but **JS-rendered shell** | No content to scrape. The OR-SAGE siting criteria are in Appendix A of the C2N PDF (INL/RPT-22-67964) instead. |
| `inl.gov/content/uploads/...` | **200** | Direct PDF, no UA needed. |
| `osti.gov/biblio/<id>` | **200** | Reliable landing page for any lab report when the lab's own host is unreachable — use as the fallback citation. |
| `energycommunities.gov` | **DNS: no answer** | Formerly cited in `provenance.js`; replaced with a point-containment query against the NETL Hosted FeatureServer we already call. |
| `hazards.fema.gov/nri/` | **301 → fema.gov RAPT, then 403** | NRI landing page folded into the Resilience Analysis and Planning Tool and bot-filters. Replaced with a point query against the NRI county FeatureServer. |

**Extraction note:** several of these PDFs come back as raw binary through
WebFetch. `pypdf` is already available in this environment and extracts them
fine (`pdftotext` is not installed) — decode locally rather than re-fetching.

## §32 — PNNL `nepa-mcp` (PermitAI NEPA MCP Toolkit), probed 2026-08-21

Evaluated for integration; full analysis and the tiered proposal live in
[nepa-mcp-integration-spec.md](nepa-mcp-integration-spec.md). Host / packaging
findings only here.

| Query | Result | Notes |
|---|---|---|
| `pypi.org/project/nepa-mcp/` via WebFetch | **Error page, no content** | The PyPI HTML project page returned "A required part of this site couldn't load" to WebFetch. **Use the JSON API instead** — `curl -s https://pypi.org/pypi/<name>/json` returned complete metadata (author, license, `requires_dist`, full long-description, release list) on the first try. Faster and more parseable than the HTML page for any PyPI probe. |
| WebSearch `"NEPA-MCP PyPI PNNL"` | **Missed it entirely** | Returned generic MCP/PyPI tooling. The package is findable by exact name, not by description. Searching `PNNL NEPA MCP` surfaced the *PermitAI* program pages (SearchNEPA / WriteNEPA / InsightsNEPA / DraftNEPABench) but never the package. **Go to the JSON API with a guessed name before searching.** |
| Name variants probed | `nepa-mcp` **200**, `nepa_mcp` **200** (normalizes to the same project); `nepamcp`, `pnnl-nepa-mcp`, `nepa-mcp-server` all **404** | |
| `raw.githubusercontent.com/pnnl/nepa-mcp/v0.1.1/docs/mcp-tool-catalog.md` | **200** | The complete 19-server / 46-tool inventory, generated from each server's live `tools/list` contract. Fetch this rather than reading the README's prose summary — and re-fetch on any version bump, since it is generated and will drift. |

**Packaging constraint worth remembering:** `nepa-mcp` requires **Python ≥ 3.12**
and pins `fastmcp==3.4.4` plus `shapely` / `pyproj`. This repo's floor is
Python 3.9+ and the machine default is 3.9.6, so it can never be a
`requirements.txt` entry — it runs out-of-process as an MCP server on
`/Users/pranava/.local/bin/python3.12`. `pipx` is **not** installed here.

**Do not re-probe** the 12 agency endpoints it wraps by hand — the catalog names
them (BLM, Census, eCFR/GPO, NOAA Fisheries, EPA AQS/NEPAssist, FEMA NFHL, GBIF,
USFWS IPaC, NPS NRHP, USGS PAD-US, Census TIGERweb, USACE). Several overlap
endpoints already logged above.
