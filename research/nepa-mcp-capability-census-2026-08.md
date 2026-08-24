# nepa-mcp 0.1.1 — live capability census and production reuse guide

**Probed:** 2026-08-24, by loading every server module of the pinned isolated
install (`uv run --python 3.12 --with nepa-mcp==0.1.1`) and enumerating its
callables — not by reading the docs site. The published catalog is generated
from the live `tools/list` contract and will drift between releases; this
census is the ground truth for what 0.1.1 actually exposes, recorded so the
next builder never re-pays the discovery.

Companion documents: [nepa-mcp-integration-spec.md](../nepa-mcp-integration-spec.md)
(architecture + tiers), [nepatec-reindustrialization.md](nepatec-reindustrialization.md)
(text-corpus angle), and the three production builders on
[`scripts/nepa_screening.py`](../scripts/nepa_screening.py).

---

## 1. The 19 servers, with every impl function that matters

Each MCP `*_tool` wrapper returns a JSON **string**; the underlying impl
functions (listed below) return **dicts** and are what the batch builders
call. Buffer parameter naming is inconsistent across servers — noted where
it bites.

| Server | Impl functions (signature essentials) | Credentials | Production use here |
|---|---|---|---|
| `ipac` | `get_ipac_resources_in_roi(lat, lon, buffer_miles=25)` | — | Janus, Hanford, coal |
| `tribal` | `get_tribal_lands_in_roi(lat, lon, buffer_miles)` | — | Janus, Hanford, coal (+ the bulk `tribal-areas` connector was validated against it) |
| `nrhp` | `get_nrhp_properties_in_roi(lat, lon, buffer_miles)` | — | Janus, Hanford, coal |
| `padus` | `get_padus_in_roi(lat, lon, buffer_miles)` — impl name differs from the tool's `get_padus_protected_areas_in_roi` | — | All three (0.1-mi point context only — ROI calls unreliable at width, 2026-08-21 probe) |
| `usace` | `analyze_usace_jurisdiction(lat, lon, buffer_miles)` + district/region/subregion singles | — | All three. District + delineation region ONLY — never wetland presence or CWA jurisdiction |
| `nepa_assist` | `query_nepa_assist(lat, lon, buffer_miles, project_name)` | — | All three (report deep-link surfaces in UI) |
| `noaa` | `get_noaa_critical_habitat_in_roi(lat, lon, buffer_miles)` — **West Coast NMFS critical habitat** | — | **Hanford (new)** — the consulting-agency lens IPaC does not cover |
| `efh` | `get_salmon_efh_in_roi` / `get_efh_areas_in_roi` / `get_hapc_in_roi` / `get_hms_cps_groundfish_efh_in_roi` | — | **Hanford (new)** — salmon EFH by HUC-8; Magnuson-Stevens hook fires even for unlisted runs |
| `pcsrf` | `get_critical_habitat_in_roi` / `get_efh_in_roi` / `get_pcsrf_projects_in_roi` / `get_species_ranges_in_roi` | — | Not yet — recovery-project context; candidate for a Columbia/Snake mitigation-context layer |
| `esa_ranges` | `get_esa_species_ranges_in_roi(lat, lon, buffer)` | — | Not yet — NMFS species RANGES (coarser than critical habitat) |
| `gbif` | `get_gbif_occurrences_in_roi(lat, lon, buffer_miles, threatened_only=True, min_year=…)` + county variant | — | **Hanford (new)** — presence-only evidence; absence of records = absence of observers |
| `fema_nfhl` | `get_flood_zones(lat, lon, radius_miles=100)` / `get_levees` / `get_water_areas` / `analyze_flood_risk` — **note `radius_miles`, not `buffer_miles`** | — | **Hanford + coal (new)** for curated sites only; the 46,759-site corpus keeps its own 91.1%-coverage backfill |
| `blm` | `get_blm_land_use_plans_in_roi` / `get_blm_national_monuments_in_roi` / `get_blm_wilderness_areas_in_roi` | — | Not yet — the western FUDS tail's land-use-plan context |
| `gis` | `summarize_roi_buffer` / `calculate_roi_area_tool` / `get_roi_geojson_tool` | — | Indirectly (map composer ROI feature) |
| `tigerweb_counties` | `get_counties_in_roi` | — | Never — `connectors/county_lookup.py` is offline and free |
| `census` | `get_census_data(lat, lon, …)` — ACS socioeconomics | `CENSUS_API_KEY` | **Blocked** — key absent; Spec 02's Tier B1 waits on it. Unavailable stays visible, never a zero |
| `epa_aqs` | `analyze_air_quality_baseline` / `get_air_quality_monitors` / `get_annual_air_quality` | `EPA_AQS_EMAIL` + `EPA_AQS_API_KEY` | **Blocked** — keys absent; the nonattainment gate (Spec 12) waits on them |
| `cfr` | `cfr_resolve_citation` / `cfr_resolve_executive_order` / `cfr_resolve_fr_citation` / `cfr_history` / `cfr_rulemaking` / `cfr_compare_versions` / `cfr_browse_structure` | — | Not yet — Spec 09's automated federal re-audit half |
| `map_composer` | `collect_all_layers(lat, lon, buffer, layers, include_species)` / `list_available_layers` / `compose_environmental_map` (Folium — never a product surface) | — | Janus (12 layers), Hanford (14 incl. `eis_boundaries`) |

## 2. Map Composer: 32 layers, 5 profiles

Profiles (verbatim from `list_available_layers()`): `screening`, `biological`,
`water`, `lands`, `full`. Layers worth knowing beyond the Janus 12:

- **`eis_boundaries`** — EPA-registered EIS project boundaries. This is the
  NEPA-precedent layer: "what environmental reviews already happened near
  this point." Now part of every Hanford package and asserted by
  `test_generated_geojson_packages_exist_and_carry_metadata`.
- `wetland_regions` / `wetland_subregions` — USACE delineation-method
  context. **Multi-state polygons** — see the fit-bounds trap in §4.
- `lwcf_lands`, `national_trails`, `usfs_roadless_areas`,
  `blm_wilderness_study_areas`, `blm_rights_of_way`, `grsg_habitat`,
  `sagebrush_focal_areas`, `wild_horse_hma` — western-siting exclusion
  context, unused so far; the microreactor lens's Alaska/mountain-west tail
  is the natural customer.
- `nhd_*` (7 hydrography layers), `fire_perimeters`, `counties`.

## 3. Live response shapes (0.1.1), captured at the Columbia Generating Station point

Recorded because the normalizers in `nepa_screening.py` are written against
these exact shapes and an upgrade WILL move them:

- `noaa`: `{habitats: [{common_name, scientific_name, listed_entity,
  listing_status, ch_status, unit…}], total, species_count,
  designation_count, named_unit_count, warnings}` — at CGS it returned
  Upper Columbia spring-run Chinook (Endangered, Final CH) + steelhead.
- `efh.get_salmon_efh_in_roi`: `{watersheds: [{huc_8, huc_8_name, state,
  chinook_efh, coho_efh, pink_efh, all_efh}], total, warnings}` — HUC-8
  flag rows, not polygons.
- `fema_nfhl.get_flood_zones`: `{zones: […], total_zones, summary:
  {sfha_count, sfha_percentage, zone_counts}, truncated, warnings}` — zero
  zones at Hanford points because **most of Hanford is unmapped in NFHL**;
  unmapped is not flood-free, and every UI surface must keep saying so.
- `gbif`: `{occurrences: [{scientific_name, common_name, threat_status,
  year…}], total_occurrences, unique_species, summary:
  {by_threat_status}}` — 304 records / 13 species at CGS with
  `threatened_only=True, min_year=2000`.

## 4. Production lessons (three builders in, all reusable)

1. **One shared engine, three thin builders.** All generic machinery —
   IPv4 pin, 1.5 s/host throttle monkeypatch, bounded timeouts, disk cache,
   explicit-unavailable caching, normalizers, the source-matrix loop, map
   packages — lives in `scripts/nepa_screening.py`. `build_janus_nepa.py`,
   `build_hanford_e2e.py`, and `build_coal_nepa.py` own only their roster,
   source list, buffers, and payload. A fourth screening product is
   ~200 lines of curation, not a fork.
2. **Fit screening maps to the ROI feature, never the layer union.** USACE
   districts and wetland delineation regions are multi-state polygons; a
   `getBounds()` over the combined FeatureCollection zooms the map to half
   the country (observed: zoom 4 on a 5-mile Hanford screen).
   `_screeningFitBounds()` in app.js fits the `Region of Interest` feature.
3. **Buffer names differ by server** (`buffer_miles` vs `radius_miles` vs
   extra args like NEPAssist's project name). The `SourceDef.invoke`
   adapter exists precisely so this never leaks past one lambda.
4. **Batch cost reality:** the Hanford tabular pass (9 parcels × 10
   sources = 90 queries) ran ~6 minutes warm-host; the 14-layer map pass
   ~9 minutes. The per-host 1.5 s floor holds because ONE process runs at a
   time — never run two builders concurrently, aggregate rate doubles.
5. **Screens are keyed by the frontend's existing join key** (`plant_name`
   for coal, parcel id for Hanford) so the UI join is one Map lookup.
6. **NRHP returns listed properties only** and its point-location service
   is sparse; a zero at a place with an obvious landmark (B Reactor) means
   layer sparsity, not absence. The UI copy carries this.

## 5. What is still deliberately NOT built

- **Per-site screening over the 46,759-record corpus** — 10 sources ×
  46,759 × 1.5 s ≈ 8 days of wall clock per full pass. Tier C, unchanged.
  Screens stay curated-catalog-sized (9–32 sites).
- **`map_composer` Folium HTML as a product surface** — still a second,
  worse map. Only `collect_all_layers` GeoJSON is consumed.
- **census / epa_aqs work** — both free keys, both absent. The rule stands:
  unavailability stays visible; it is never converted into a zero.
- **pcsrf / esa_ranges / blm layers** — cataloged above, adopted only when
  a product question needs them (candidates listed per-spec in docs/specs/).
