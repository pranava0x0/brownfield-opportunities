# Backlog

Ideas and enhancements. Priorities: **high** = next, **med** = soon, **low** = nice-to-have.

---

## v1.11.2 — Continue ECHO + docs coverage (2026-05-05+)

The v1.11.2 commit fixed the ECHO connector and shipped 380 of 1,787 Final/Deleted Superfund sites with enforcement data (vs the broken 0 records in v1.11). Continued coverage is gated by upstream API throttling, so this is staged work, not a single sprint:

- **[high] Finish the ECHO F/D backfill (1,407 sites remaining).** ECHO bot-detection trips after sustained 1.5 s/call cadence — the connector now backs off correctly via the `_EchoBotBlocked` retry path, but the wall-clock cost compounds (16 bot-blocks × 30 s = 8 min of pure backoff in the first 380 sites). Future runs should either (a) raise the per-call delay specifically for ECHO to ~3 s, halving the bot-block rate, or (b) split into nightly cron batches of `--echo-limit 200 --echo-skip <prev>` to stay under the threshold.
- **[high] Finish the EPA superfund-docs backfill (~1,700 sites remaining).** `cumulis.epa.gov` was hitting the 60 s `REQUEST_TIMEOUT_S` on roughly every other request during the 2026-05-05 batch — net 10 new records over 30 min of wall clock. Same staging strategy: nightly cron batches with `--docs-limit 100 --docs-skip <prev>`, or run during off-peak hours when EPA's app servers are less loaded.
- **[high] Run the ai-summary connector once `epa-echo` + `epa-superfund-docs` are both >50% covered.** The summary prompt MERGES every enrichment file we have on disk into the model's context — running ai-summary today against 21% ECHO coverage would generate ~1,400 summaries that don't mention enforcement. Better to wait until the upstream coverage is meaningful, then run with `--ai-limit 0` (cache-aware so re-runs are free for unchanged inputs).
- **[low] ECHO non-Superfund coverage.** The connector currently only enriches Superfund records (`run_order = 250` reads `superfund-npl.json`). FUDS / ACRES / BRAC sites don't have an EPA_ID equivalent for ECHO's `p_pid` filter — would need a name + state fuzzy match (`p_fn` + `p_st`) which is unreliable. Defer until an actual user asks for non-Superfund enforcement data.

---

## ~~v1.11.1 — Bug-fix pass + UX polish (2026-05-05)~~ Done

Three defects closed:

- ~~**[high] `?site=FUDS-/BRAC-` showed a premature "not found" toast.**~~ Done 2026-05-05 — `applyUrlSelection()` now `Promise.allSettled`s every in-flight program-data fetch (ACRES / FUDS / BRAC) before declaring an ID unknown; boot order rearranged so the lazy-load promises are populated *before* `applyUrlSelection()` runs. Same drift-risk pattern as the Reset handler (UAT-007).
- ~~**[high] CSV export silently dropped every enrichment field.**~~ Done 2026-05-05 — extracted `CSV_COLUMNS` to a curated 40-field schema mirroring the detail panel (FUDS / BRAC / owner / universal infra distances / EPA RE-Powering qualitative buckets / ECHO enforcement / document count). `pickCsvField()` walks dotted paths (`enforcement.formal_actions_5yr`) and supports a `.length` shortcut for array sizes.
- ~~**[high] Site names rendered ALL CAPS in table, marker tooltip, and detail title.**~~ Done 2026-05-05 — new `prettyName()` helper runs in `ingestSites()` with an EPA/DOD acronym whitelist (NIKE, AFB, NRDA, PCB, USDOE, USACE, USDA, USFS, BLM, NPS, …) seeded from a frequency scan of the dataset. Raw preserved on `s.name_raw`.

Demoted from this pass — call out for future work:

- **[med] Out-of-CONUS infra placeholder.** Carried over from the v1.10.1 audit. 395 FUDS (AK + Pacific) and 142 ACRES (AK) records have blank dashes in the detail-panel infra rows because `MAX_DISTANCE_MI=100` drops them. Two paths: (a) frontend placeholder `"Remote — outside continental US"` (~10 lines, no data change); (b) extend `infra_proximity` to include AK DOT&PF + AK railroad layers as a fourth source.
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
- **[low] Per-record reasoning for the data-center candidate flag.** Today the `data_center_reuse_candidate` boolean is opaque ("Yes" / "No"). Once we have universal infra distances, surface the reasoning ("≥50 ac · power within 1mi · water within 0.5mi") so users can see why a site qualifies.

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
  - **Federal civilian real property** ([GSA FRPP Public Dataset](https://catalog.data.gov/dataset/fy-2024-federal-real-property-profile-frpp-public-dataset)) — annual CSV of all federal civilian real estate by agency: ownership status (`Owned` / `Leased` / `Other`), use code, square footage. DOD assets are excluded for security, so this *won't* help BRAC/FUDS but *will* help when we add federal civilian (e.g. legacy DOE / NRC / GSA-controlled contaminated sites). Cleanest single-file source we found.
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

- **"Construction Complete" (CC) milestone** — SEMS milestone date: cleanup work is physically done, deletion paperwork underway. Typically 1–5 years before formal NPL Deletion. Source: EPA SEMS REST API — investigate `https://sems.epa.gov/rest/sites/{EPA_ID}` for milestone table. New `epa_sems_readiness.py` enrichment connector; set `run_order = 250`.
- **"Ready for Anticipated Use" (RAU)** — EPA's per-Operable-Unit formal determination that the site can support its planned future use. A site can be RAU while still on the NPL (e.g., if cleanup continues in one corner but the main parcel is cleared). RAU date published in SEMS and in the EPA site-profile Redevelopment tab. More granular than NPL Deletion — distinguishes partial vs. whole-site readiness.
- **BRAC LIFOC (Lease in Furtherance of Conveyance)** — federal government leases land to a developer while cleanup finishes; deed transfer on completion. Developer can start site planning and sometimes vertical construction. Lease start date = actionable now for sophisticated acquirers. Source: same per-Service PDF scrape as the full BRAC item.
- **ACRES assessment complete, cleanup not started** — brownfields where environmental assessment is done (contamination scope known, cost estimate in hand) but cleanup hasn't started. These are "developer-fundable cleanups" — the acquirer funds remediation as part of the deal. `ACRES_assessments_*` layer `Assessment_Completion_Date` populated + no `Cleanup_Completion_Date` = this tier.

**Tier 3 — "Long pipeline": cleanup ongoing or not yet scoped**

- **FUDS "Eligible" + `has_projects = true`** — USACE is actively investigating or cleaning. Timeline unclear but progressing. At 8,822 FUDS records with 2,874 having active projects, this is a large pipeline pool.
- **NPL status "F" (Final, active)** — on the NPL, cleanup underway. Wide range from years-to-completion to decades.
- **NPL status "P" (Proposed)** — newly proposed, cleanup not yet started.

### Anticipated future land use — what the site will be used for when ready

- **EPA SEMS AFL (Anticipated Future Land Use) code** — per-site code set by EPA project manager: `Industrial/Commercial`, `Recreational/Open Space`, `Residential`, `Unknown`. Available via SEMS REST API (same endpoint as milestone data above). Cross-program Superfund sites only; bake into `epa_sems_readiness.py`.
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

- **[high] SEMS REST API for Superfund milestones + AFL code.** Investigate `https://sems.epa.gov/rest/` for Construction Complete date, RAU date (per OU), and AFL code across all 1,908 NPL sites. If the endpoint is clean and unauthenticated, new `epa_sems_readiness.py` enrichment connector (`run_order = 250`, reads `superfund-npl.json`). Emits `docs/data/sems-readiness.json` with `[{epa_id, construction_complete_date, rau_date, rau_ou_id, anticipated_land_use, reuse_projects: [...]}]`. Join client-side in `ensureSemsReadinessLoaded()`. If SEMS REST proves unreliable, fall back to the site profile Redevelopment tab scrape for the same data.

- **[high] EPA site profile Redevelopment tab scrape.** New enrichment pass inside `epa_superfund_docs.py` (or a separate `epa_superfund_redev.py` connector, `run_order = 210`). For each NPL site with a `profile_url`, fetch the Redevelopment tab HTML and regex-extract: AFL description, RAU date + OU scope, reuse accomplishment name/type/date/developer name if available, and IC summary. Cache by `(epa_id, "redev_tab")` using the existing `http_get_text` disk-cache pattern. Output joins into `sems-readiness.json` or a separate `docs/data/epa-redev-tab.json`. Prioritize Final + Deleted NPL sites first (`--redev-status F,D`); Proposed sites are low-signal.

- **[med] FUDS current_owner normalization to readiness proxy.** The `current_owner` raw-code normalization already in backlog ("`PRIV:*` → `"Private"`") is a prerequisite. Once normalized, a FUDS record with a non-federal owner + `fuds_status = "Eligible"` (meaning remediation obligations met) maps cleanly to Tier 1. No new fetches — just use existing `current_owner` once the normalization ships.

- **[low] BRAC LRA reuse plan manual curation.** 27 BRAC sites is small enough to hand-curate: for each site, look up the LRA name, reuse plan headline (e.g., "Great Park Irvine — mixed-use / recreation"), and percent acreage transferred (from `bracpmo.navy.mil`). Store as a static lookup in `connectors/dod_brac.py` (similar to how `NPL_STATUS_LABELS` works for Superfund). Zero ongoing maintenance needed — BRAC is a closed list.

### Schema additions (all optional / nullable)

Add to `SiteRecord` in `schema.py`:
```
readiness_tier: Literal["available", "construction_complete", "lifoc", "assessment_complete", "cleanup_in_progress", "no_data"] | None
construction_complete_date: str | None   # YYYY-MM-DD; Superfund CC milestone
rau_date: str | None                     # YYYY-MM-DD; earliest OU RAU date
anticipated_land_use: str | None         # Superfund AFL label, e.g. "Industrial/Commercial"
cleanup_complete_date: str | None        # YYYY-MM-DD; ACRES CA_Status=Completed date
reuse_projects: list[dict] | None        # [{name, type, date, developer}] — scraped
transfer_complete: bool | None           # FUDS/BRAC: title passed to non-federal entity
```
`readiness_tier` is derived, not source-supplied — set by a `compute_readiness_tier()` function in `refresh.py` after all enrichments run.

### UI changes

- **[high] "Cleanup Complete" badge in detail panel.** Zero new data required. For `s.status === "D"` (NPL Deletion), render a green "Cleanup Complete" pill alongside the NPL status pill. One CSS rule + two lines of JS in `selectSite()`. Quick win that makes the most actionable Superfund sites immediately legible.

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

- **[high] Pre-build search index at ingest time.** `siteMatchesQuery()` joins `[name, city, county, state]` into a temporary string on every call. With 47k sites, every keystroke triggers 47k string concatenations + 47k `includes()` tests. Fix: at `ingestSites()` time, write `s._searchKey = [s.name, s.city, s.county, s.state].join(" ").toLowerCase()` once per record, then `siteMatchesQuery()` reads `s._searchKey.includes(q)`. Zero behavior change; eliminates per-keystroke allocations entirely.

- **[high] Cache `refitMapToFilters()` bbox — eliminate O(n) min/max scan.** After every filter change `refitMapToFilters()` collects all visible lat/lons into two arrays, then calls `Math.min`/`Math.max`. That's two full 47k-element sweeps per filter toggle. Fix: maintain a `visibleBBox = {minLat, maxLat, minLon, maxLon}` object updated at the same time `tableState.filtered` is rebuilt in `refreshTableForFilter()`. Pass it directly to `refitMapToFilters()` so the function never needs to re-scan.

- **[med] Replace `sites.some(s => s.program === X)` with a `loadedPrograms` Set.** Each lazy loader calls `sites.some(...)` to check whether the program already loaded, scanning up to 47k entries. Fix: maintain a module-level `const loadedPrograms = new Set()` and update it in `ingestSites()`. Each loader checks `loadedPrograms.has("brownfield")` — O(1). Same pattern as `sitesById`.

- **[med] Move `decimateKeep(zoom)` outside the marker-visibility loop.** `applyMarkerVisibility()` calls `decimateKeep(zoom)` once per marker (47k+ calls), but `zoom` doesn't change inside the loop. Fix: call it once before the loop — `const keepEvery = decimateKeep(zoom)` — then pass it to `shouldDecimateOut()`. No behavior change.

- **[med] Batch enrichment property assignment.** The five enrichment merge loops (`ensureRedevLoaded`, `ensureEchoLoaded`, `ensureInfraLoaded`, `ensureInfraLoaded`, `ensureSuperfundDocsLoaded`) each assign properties one-by-one inside an `if`-chain. Replacing with `Object.assign(existing, { field1: rec.field1, ... })` reduces the number of property descriptor lookups and makes the merge logic easier to scan.

- **[med] Cache `updateCountText()` inputs from `refreshTableForFilter()`.** `updateCountText()` iterates all filtered sites to count visible entries and sum acreage. It's called on every filter change immediately after `refreshTableForFilter()` has already built `tableState.filtered`. Fix: compute `filteredCount` and `filteredAcreageSum` once inside `refreshTableForFilter()` and pass them in, avoiding a second full-array scan.

- **[low] Event delegation for table header sort clicks.** Each `<th>` gets its own click listener on page load via `forEach`. Fix: single `addEventListener("click", ...)` on `#sites-table thead` that checks `event.target.closest("[data-sort]")`. Reduces listener count from N-columns to 1 and survives future column additions automatically.

- **[low] Cache `querySelectorAll` in `updateSortIndicators()`.** The function calls `document.querySelectorAll("#sites-table thead th")` inside a `forEach` loop, re-querying the DOM on every iteration. Fix: call it once before the loop and cache the result. One-liner.

- **[low] Pre-compile `prettyPlace`/`prettyName` regexes as module constants.** Both functions define their split regexes inline (re-parsed each call at startup). Move them to `const PLACE_SPLIT_RE = /(\s+|[-/])/g` at module scope. V8 likely caches them already, but explicit constants make the intent clearer.

- **[low] Single-pass KPI deck computation.** `updateKpiDeck()` loops `sites` once per metric (total, acres, DC candidates, state set). Merge into one `sites.reduce()` call that accumulates all four in parallel. Reduces 4 passes to 1.

### UAT 2026-04-29 #2 (high priority)

- **[med] LOD swap for the basemap above zoom 10.** State strokes still look blocky at zoom 12+. Pagination + chunked hydration moved this off the critical path; revisit when we can swap to a higher-detail GeoJSON or fade strokes at zoom > 10. *(Demoted — counties carry visible borders past zoom 7, so the simplification artifact is mostly cosmetic on infrequent deep-zoom views.)*
- ~~**[high] Re-evaluate `ensureCountiesLoaded()` on every `moveend`.**~~ Done 2026-04-29 (v1.6) — `map.on("moveend", updateCountyVisibility)` now fires for any view change, including `setView`-driven auto-zoom from `?site=` or the detail panel.
- ~~**[high] Toast / inline feedback when `?site=<id>` doesn't match.**~~ Done 2026-04-29 (v1.6) — `applyUrlSelection()` waits for `acresLoadingPromise` (so the toast doesn't fire prematurely), then `showToast(...)` with the bad ID. URL is preserved.
- ~~**[high] Fix URL-state unwind on filter clear.**~~ Verified 2026-04-29 (v1.6) — `syncUrl()` already drops keys at default; new regression test `test_url_unwinds_on_filter_clear` guards against future drift.

### UAT 2026-04-29 (high priority)

- **[high] Audit first-paint payload now that ACRES auto-loads.** Cold load = ~12 MB decoded / ~1.8 MB on the wire (sites.json 184 KB gz + epa-acres.json 1.58 MB gz + states 30 KB + leaflet/topojson/app/css). The `epa-acres.json` line item alone is 9× the original first-paint budget. Either pair with the "make ACRES opt-in" item in Frontend/UX, or split ACRES into per-state shards and lazy-fetch only the state(s) currently in view.
- **[high] Cap or virtualize markers on the canvas at low zoom.** Decimation already keeps 1/8 at zoom ≤4, but that's still ~4,700 visible markers when both programs are on — Canvas pan latency is noticeably degraded. Either tighten decimation (1/16 at zoom ≤4, 1/8 at ≤5) or switch to a viewport-clipped renderer that only adds markers within the current `getBounds()` and re-evaluates on `moveend`.

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

- **[med] Out-of-CONUS sites have no infra-proximity data — undocumented.** 395 FUDS (AK=260, HI=76, AS=31, MP=26, PW=2) and 142 ACRES (all AK) records are absent from `infra-proximity.json` because `MAX_DISTANCE_MI=100` drops them. The detail panel shows blank dashes for their transmission/rail/highway rows. Options: (a) show a `"Remote – outside continental US"` placeholder instead of a blank; (b) run an AK-specific enrichment pass using AK DOT&PF highway layer + AK railroad data from HIFLD.

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
