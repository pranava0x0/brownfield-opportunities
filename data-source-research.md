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
| NY | NYSGIS_GPO `NYS_Tax_Parcels_Public/FeatureServer/0` | — | ✗ rejected. Layer 0 is **municipal boundaries** (NAME/GNIS/POP/SWIS), not parcels; the public NY parcel product carries **no owner name** (owner is county-restricted). |
| MA | MassGIS `Massachusetts_Property_Tax_Parcels/FeatureServer/0` | `OWNER1` / `LOT_SIZE`+`LOT_UNITS` / `LOC_ID` | ✗ deferred. Owner present, but lot size is `LOT_SIZE` with a **per-record `LOT_UNITS` (A=acres / S=sq ft)** — mixed units the connector's single `acreage_field` can't scale. Add only after the query handles LOT_UNITS. |

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
