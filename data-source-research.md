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

## Reusable probe patterns

- ArcGIS service inventory: `https://<host>/arcgis/rest/services?f=json`
  (+ `/​<folder>?f=json`); layer schema: `…/FeatureServer/<n>?f=json`;
  row count: `…/query?where=1%3D1&returnCountOnly=true&f=json`;
  value survey: `…/query?where=1%3D1&outFields=<col>&returnGeometry=false&f=json&resultRecordCount=2000`.
- Field-coverage survey of an on-disk enrichment file: count non-null per key
  across `json.load(open('docs/data/<file>.json'))['sites']`.
- When fanning out discovery agents: give each ONE host/org to enumerate and
  this file's table format to return — and have them check this log first.
