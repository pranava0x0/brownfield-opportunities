# Plan & Backlog

This is the single planning doc for the project. `issues.md` stays the bug log (defects only — file new bugs there, not here). Full history through 2026-09-25 is archived verbatim at `planning/archive/backlog-2026-04-to-2026-09-25.md`; four superseded plan docs (JTBD UX, mobile UX, the 2026-07-26 siting review, the unified-rankings/PWR-siting plan) moved to `planning/archive/` alongside it — their still-open ideas are folded into this file.

Priorities: **high** = next, **med** = soon, **low** = nice-to-have. Last updated 2026-09-25.

## 1. Where things stand (2026-09-25)

**Tabs (11, in order):**

- **Explore** — default landing view since 2026-09-12; list-first, sourced evidence-category findings per site (replaced the 0–100 suitability scores).

- **Map** — vector US basemap, program markers, curated overlays (retired plants, reference campuses, coal, DOE sites, ports, nuclear pipeline, microreactor commitments).

- **Table** — full corpus, sortable/filterable, paginated 250 rows/page.

- **Retired Sites** — 658 GHGRP stopped-reporting heavy-industrial/mining sites as stranded-grid reuse candidates.

- **Coal Reinvestment** — 18-plant curated coal-conversion catalog, corpus proximity join, NEPA permitting screens.

- **Nuclear Siting** — 14 military installations screened for AP1000/APR1400/AP300-class reactors, plus the 68-site civilian nuclear pipeline.

- **Microreactors** — 12-vendor fleet, 32 named commitments, and a siting screen over the full corpus that deliberately inverts the grid-proximity signal.

- **DOE Sites** — five-site federal-land dossier explorer (Hanford, SRS, Portsmouth, Paducah, WIPP).

- **Maritime Siting** — port/shipyard proximity for floating-nuclear and coastal-generation siting.

- **Nickel Refining** — import-route and domestic-feedstock siting screens for a nickel refinery; the corpus's first water-flow layer.

- **Data & methods** — evidence sources, schema, provenance (the former "About" tab).

**Data freshness** (checked live today via `scripts/check_upstream_freshness.py` where the script covers a source; other rows read `generated_at` directly):

| Dataset | Our date | Upstream signal | Cadence | Status |
|---|---|---|---|---|
| superfund-npl / sites.json | 2026-09-25 | upstream edited 2026-09-19 | weekly (cron broken) | Current |
| epa-acres | 2026-05-12 | frozen "8_30_2021" snapshot, unmoved since 2021-08-31 | annual, blocked | **Blocked — see §5** |
| dod-fuds | 2026-09-12 | upstream edited 2026-09-04 | weekly (cron broken) | Current |
| dod-brac | 2026-05-12 | frozen 2021 snapshot | rare | Current (vs. frozen source) |
| epa-redev | 2026-09-12 | upstream edited 2026-07-24 | weekly (cron broken) | Current |
| infra-proximity: transmission/gas/power-plant (HIFLD) | not stamped per-layer | 2023-09 / 2025-07 / 2025-07 | ad hoc | **Unknown — metadata gap, see Now #9** |
| infra-proximity: highway/rail (TIGER), substations (OSM), flood (FEMA NFHL) | — | continuously edited, no single vintage | judgment call | Current by design, no fixed cadence |
| opportunity-zone | 2026-05-17 | upstream 2026-02-24 | Treasury designations, ~10 yr stable | Current |
| ira-energy-community | 2026-06-08 | upstream 2025-07 (both layers) | annual DOE update | Current |
| fema-nri | 2026-06-08 | upstream 2025-12-16 | annual | Current |
| eia-retired-plants / planned-retirements(-proximity) / ap1000-sites | 2026-09-25 (bumped today) | Aug-2026 EIA-860M workbook | monthly | Current |
| parcel-owner | 2026-09-09 | 11 states registered, no single upstream date | resumable, ad hoc | Due — more states possible |
| epa-echo | 2026-06-19 | full refresh running now | resumable | Refreshing |
| epa-superfund-docs | 2026-08-05 | doc-list refresh running now | resumable | Refreshing |
| ai-summary | 2026-08-05 | derived from echo/docs/redev/infra | regen after each dependency lands | Due once today's refreshes land |
| coal-conversions(-proximity) / federal-clean-energy | 2026-08-23 / 2026-08-24 | curated, quarterly re-audit target | quarterly | Due ~2026-11 |
| hanford/srs/portsmouth/paducah/wipp-e2e (DOE Sites) | 2026-08-25 | curated dossiers, fast-moving | quarterly, flagged high | Due |
| microreactor-fleet / nuclear-civilian-sites | 2026-08-21 / 2026-07-26 | curated | periodic | Due for a re-check |
| port-proximity / ports / shipyards | 2026-08-27/28 | NTAD live pull + curated shipyard list | periodic | Current |
| water-proximity / streamgages | 2026-09-12 | USGS gages, legacy service retiring Q1 2027 | national rebuild ~65 min | Current, migration due — see Next #6 |
| nickel-anchors(-proximity) / tribal-areas | 2026-09-12 / 2026-08-21 | curated / TIGERweb AIANNHA | quarterly / stable | Current |
| STATE_DC_INCENTIVES / STATE_DC_REGULATION (frontend constants, not a data file) | incentives 2026-07-26; regulation re-checked 2026-09-25 | 50-state + DC tax/regulatory sweep | quarterly | Incentives **due ~2026-10 — see Now #14** |

**Pipeline and test health:**

- Weekly GitHub Actions "Refresh site data" cron has failed every run for 17+ consecutive weeks (every week since at least 2026-05-25). Current known triggers: Overpass 429/504 on the substation layer, `iso-rto`'s source now token-walled (ArcGIS 499), `CENSUS_API_KEY` unset in CI, and `ai-summary` with no `ANTHROPIC_API_KEY` in CI — the last one is now correctly refused rather than silently blanking a file, thanks to the empty-write guard landed 2026-09-08 (`853e58c`), which also covers all four producer inventories and 17 enrichment files (357,911 records) against a zero-record write. That guard is what unblocks the `refresh.yml` restructure below.

- Unit tests: **826 passed, 14 failed, 7 skipped** (`.venv/bin/python -m pytest tests/ --ignore=tests/e2e -q`, run today). All 14 failures are the same `FileNotFoundError: node` — this machine has no Node.js on PATH, and `tests/test_evidence_categories.py` shells out to `node -e ...` to exercise `docs/evidence-categories.js` directly. Not a code defect; install Node locally to run that file's tests (CI presumably has it — nothing else in the suite depends on it).

- e2e (Playwright) suite could not run on this machine — browsers aren't installed here.

- Live sample check against the source services (2026-09-25, `scripts/validate_against_sources.py --only attrs infra --sample 24 --seed 925`, 96 sites): 96/96 records match their owning FeatureServer on name, state, coordinates and acreage; 368/384 infrastructure distances re-measured independently match, and the other 16 were skipped by design (stored distances of 26–48 mi need too large a query box). No mismatches. Offline `validate_data.py`: 29 pass, 12 warn (the documented upstream-quality set), 0 fail across 43 checks.

- Refreshes run on 2026-09-25: `superfund-npl` re-pulled (record-identical to 2026-09-12, promoted with today's stamp); EIA-860M moved to the August 2026 workbook with its three products and `ap1000-sites.json` rebuilt; full EPA ECHO and Superfund document-list refreshes started (results land later the same day). `dod-fuds` and `epa-redev` were already current against upstream and were not re-pulled.

## 2. Now (next two weeks)

**Prerequisite on this machine (found 2026-09-25):** the Xcode license is not accepted (so `/usr/bin/git` and `/usr/bin/python3` fail), there is no GitHub credential or `gh`, and no Node.js or Playwright browsers. Until fixed, nothing can be pushed, the daily research routine can only commit locally, and the Node-backed unit tests and the e2e suite cannot run here. Fix: `sudo xcodebuild -license accept`, install Homebrew then `gh` + `node`, `gh auth login`, and `.venv/bin/python -m playwright install chromium`.

1. **[high]** Choose the landing page and the simplified site card (options presented 2026-09-25; see §7). Current Explore opens on 46,759 alphabetical rows, and its first mobile card starts 54% of the way down the screen. The site detail panel runs 4.4 desktop screens with identifiers first and repeats the infrastructure numbers in two sections. Size: M once a direction is picked.

2. **[high]** Flag Superfund acreage that is really a county outline. Five NPL sites ship an acreage within 5% of their whole county's area (Tar Creek OK, Madison County Mines MO, Newton County Mine Tailings MO, Southwest Jefferson County Mining MO, Central City/Clear Creek CO), and Harbor Oil (a Portland oil-recycling facility) ships 156,219 acres, 53% of Multnomah County. For these the site point is also the county center, so every infrastructure distance is measured from the wrong place (Tar Creek's point is 10.5 mi from the mining area; Oklahoma DEQ gives 25,600 ac, not 310,173). Add a `validate_data.py` WARN check (acreage ≥ 50% of the containing county), a detail-panel note, and treat those rows' land and distance findings as unassessed. Size: S–M.

3. **[high]** Restructure `.github/workflows/refresh.yml` with `continue-on-error` so a partial connector run still commits what it refreshed. The blocking guard (empty-write protection, `853e58c`) is now in place — this is the pipeline fix with the biggest payoff for the least work, and it's been the top carried item since 2026-08-11 (issues.md same date). Add `id` + `continue-on-error: true` to the refresh step, commit step, then a trailing step that fails the job if refresh failed. Still supervised — watch the first restructured run. Size: S.

4. **[high]** Find a current EPA ACRES source. Confirmed today: the "All ACRES Properties 8_30_2021" FeatureServer we pull is a frozen Aug-2021 snapshot and hasn't moved upstream since. 36,003 brownfield records (the largest single program) are five years stale. Search EPA's ArcGIS hub for a newer `All_ACRES_Properties_*` service, or email `helpdesk@acrebs.epa.gov`. Size: S–M.

5. **[high]** Replace the token-walled `iso-rto` source. `RTO_Regions` on `services3.arcgis.com` now returns 499 at both the query and service root; `docs/data/iso-rto.json` is frozen at 2026-06-05 (still serves fine, only refresh is blocked). One partial candidate probed (`RTO_Regions_and_Hubs_WFL1` — public, but 20 per-RTO layers and no NYISO/ISO-NE) needs more source discovery before it's a drop-in. Size: M. issues.md 2026-08-25.

6. **[high]** Register `CENSUS_API_KEY` and `EPA_AQS_API_KEY` (both free). Unblocks the already-built `census-workforce` connector (Spec 02, code+tests done) and Spec 12's air-quality/NAAQS gate, and removes one of the three remaining structural CI cron failures. Ten-minute signup; see the decision in §7 on whether to keep or drop these connectors if the keys aren't registered. Size: S.

7. **[med]** Chunk + back off the Overpass substation queries in `infra_proximity.py`. Hitting 429/504 under load; `FLOOD_TRANSIENT_HTTP_CODES` already exists in the same file but isn't applied to this layer. Open since 2026-08-11. Size: S.

8. **[med]** Fix the `ensureNuclearSitesLoaded()` attempt-token race. Two call sites (boot fan-out + tab activation) can race and clear a genuine load failure, flaking `test_nuclear_civilian.py`/`test_evidence_panel.py` roughly 1 run in 2. Deliberately left off the Microreactors branch that found it — the fix is gating the failure-reset on the attempt token, same as the proximity path already does. Size: S. issues.md 2026-08-21.

9. **[med]** Stamp `source_snapshot_at` in `infra-proximity.json`'s `source_metadata` for the three HIFLD layers (transmission, gas pipelines, power plants). Confirmed today via a live run of `scripts/check_upstream_freshness.py`: all three show no per-layer snapshot date, so the freshness checker can't tell current from stale and defaults to STALE. Likely a metadata gap, not a real data gap — worth confirming either way. Size: S.

10. **[med]** Add a sanity clamp to `epa_redev.py` acreage before the RAU/acreage join becomes unconditional. `MNN000509136` ships 11,014,908 acres (8,114× the NPL value); currently harmless only because `ensureRedevLoaded()` is fill-if-null and Superfund acreage is never null — luck, not design. Size: S. issues.md 2026-08-09.

11. **[med]** Add an acreage-only registry path to `connectors/parcel_owner.py` for Maine. MEGIS's statewide layer has real acreage (`Shape__Area`, metres, converts cleanly) but no owner field, so it fails the registry's owner-required contract today. Acreage reads "Unknown" for all but 75/898 Maine sites, which matters directly for the Nickel tab's 300-acre land test. Size: S.

12. **[med]** Wire `scripts/check_upstream_freshness.py` into CI ahead of the real refresh, so a cron run skips or flags stale-source connectors instead of pulling on a blind timer. The script exists and runs clean standalone (verified today, 10 current / 3 stale-flagged / 4 unknown-by-design). Ties directly into item 1. Size: S. Spec 13d.

13. **[low]** Fix the ~38 static summaries that omit acreage for sub-1-acre sites. Formatter bug in `build_static_summary()` (treats 0.1–0.9 ac as falsy), reproduces byte-for-byte on regen. Open since 2026-08-11. Size: S.

14. **[med]** Quarterly `STATE_DC_INCENTIVES` re-audit, due ~2026-10. `STATE_DC_REGULATION` was re-checked 2026-09-25: Vermont removed (S.205 died when the legislature adjourned 2026-05-29; H.727's veto override failed the same day), NY/VA/FL confirmed. Watch list: NY's Responsible Data Center Development Act still awaits the governor; municipal moratoria (for example New Haven's 12-month pause) sit below this table's state-level threshold. Size: M.

## 3. Next (this quarter)

1. **[med]** Research routine phase 2: dossiers for curated entities (coal plants, DOE parcels, civilian nuclear sites, microreactor commitments), not only corpus sites, so a tab row can show its latest cited developments. Today those rows are corrected by hand through their builder scripts (the 2026-09-25 fact-check changed eight of them).

2. **[med]** Retire or rewrite the static template summaries (`ai-summary`, 1,908 Superfund sites). They restate raw fields ("transmission lines 1.4 miles away"), repeat boundary-artifact acreages, and still say "Flagged as a data-center reuse candidate", which the 2026-09-12 evidence contract dropped everywhere else. A cited dossier already hides the template for its site; the rest need either evidence-contract wording or removal.

3. **[high]** Basin-connected water pilot (Approach C, 2026-09-12): waterbody/flowline/catchment identity, source-matched low-flow statistic, record period, explicit intake/allocation unknowns. Extends the existing water-flow work rather than duplicating it.

4. **[high]** Regional enterprise fiber pilot: published coverage, route lifecycle, and parcel-level service evidence — kept distinct from FCC availability data and proposed-grant routes, which are weaker signals.

5. **[high]** Recompute the geographic joins `docs/data/evidence-invalidations.json` flags for the 25 producer points that moved materially. The manifest is authoritative until each dependency is rebuilt and verified.

6. **[high]** Migrate off the legacy USGS Water Services connector ahead of its announced Q1 2027 retirement, preserving the statistic/period contracts and cache replay.

7. **[high]** Single-site reuse dossier (Spec 01, Ready, no code started) — one view synthesizing land/control, infrastructure, environmental baseline, prior studies/permits, workforce/community, and delivery path per site.

8. **[high]** Derive the full ~550-plant coal-conversion universe from EIA-860M instead of hand-curating 18 (Spec 04 §7.1) — the highest-ranked open follow-up on the shipped Coal Reinvestment engine.

9. **[high]** DOE Sites: replace representative points with real parcel polygons where public (Spec 11, H1) — monument boundary, MAPR park unit, NPL operable-unit polygons, EA-1915 conveyance parcels.

10. **[high]** Quarterly re-audit of the four newest DOE Sites dossiers (SRS/Portsmouth/Paducah/WIPP) — the fastest-moving curated rows in the repo (negotiation-stage leases, pending state approvals, unsigned agreements).

11. **[med]** Finish wiring `census-workforce` once `CENSUS_API_KEY` exists (Spec 02) — connector and tests are already built, only the secret is missing.

12. **[med]** EPA RE-Powering 190,000-site screened universe + substation-distance cross-validation (Spec 06, Ready) — roughly a 100x coverage increase from a source already trusted, plus an independent check on `substation_mi`.

13. **[med]** ISO interconnection-queue dynamics + automated eCFR regulatory-change tracker (Spec 09, Ready, no code started).

14. **[med]** cumulis schedule-page scrape for Superfund milestones (Construction Complete / SWRAU / Five-Year Review dates) — Tier 2 of the "development readiness" signal taxonomy, still unbuilt.

15. **[med]** ACRES cleanups-layer join (`ACRES_cleanups_*`) for a real cleanup-status signal on brownfields, not just the program label.

16. **[med]** Air-quality/NAAQS nonattainment gate once `EPA_AQS_API_KEY` exists (Spec 12).

17. **[med]** Generic `build_nepa_screens.py --catalog` CLI, then screen the remaining curated overlays (nuclear-civilian-sites, federal-clean-energy, reference-campuses) with coal/Hanford-style permitting chips (Spec 10, R1/R2).

18. **[med]** Utility-specific capacity/connection evidence keyed to the actual asset and proposed parcel — don't reuse retired-plant MW as a proxy for capacity rights (Approach C).

19. **[med]** Fix `port_proximity.py`'s shipyard search radius — the default ring-search caps effective reach below the connector's own advertised 150 mi, so roughly 600 sites get no `shipyard_mi` at all and some get a farther yard than the true nearest.

20. **[med]** Federal Register API connector for NPL-deletion and BRAC-conveyance signals — an earlier, stronger readiness signal than polling `npl_status_code`.

21. **[low]** Partition or precompute compact evidence payloads if measured mobile first-insight time stays high (Approach C) — current work already defers unused datasets and markers.

22. **[low]** File the `nepa-mcp` upstream proposals from Spec 13c: the `load_server_module` re-front PR (our `purge_server_src_namespace` is the shim + test case), the coverage-metadata issue, and the NEPATEC-document-server discussion.

## 4. Later and ideas

Grouped by theme. Every still-open idea carried forward from the pre-2026-09-25 backlog and the four archived plan docs lives somewhere below, in Appendix A, or in §5.

### Data sources
- **[med]** State voluntary-cleanup-program (VCP) connectors. Each state runs its own brownfield/VCP universe outside federal data — often *closer* to shovel-ready than NPL sites because voluntary cleanups are developer-initiated. NY BCP's Socrata dataset (`data.ny.gov/resource/ir93-7qzi.json`) is a proven, no-auth path; add CA DTSC EnviroStor, TX TCEQ VCP, and NJ HDSRF when they publish similarly machine-readable endpoints.

- **[med]** RCRA Corrective Action sites. A large contaminated-industrial universe (tens of thousands of facilities) outside both NPL and ACRES; EPA ECHO and EnviroAtlas both expose it.

- **[med]** UST/LUST underground-storage-tank database. The single largest brownfield category by count — mostly former gas stations with moderate, sub-$1M cleanup costs and attractive urban-infill locations. Start with EPA OUST's LUST Trust Fund tracking data.

- **[med]** ACRES grant history (`BF_GRANT_AWARD`/`BF_GRANT_RECIPIENT`). A site that received federal cleanup funding recently is closer to ready than one without; show as a "federal funding" section in the detail panel.

- **[med]** Superfund Institutional Controls (ICTS) — deed restrictions and environmental easements per site. This is the single most important encumbrance a buyer needs to know about and we don't surface it anywhere yet.

- **[med]** Five-Year Review (5YR) status per NPL site. A failing 5YR is a materially different acquisition risk than a passing one; the data lives in the same SEMS surface as the existing document connector.

- **[med]** EJSCREEN community-demographics layer — census-block-level demographic and pollution-burden scores, useful both for grant-prioritization context and as a detail-panel "community context" section.

- **[low]** TRI (Toxic Release Inventory) and RMP (Risk Management Plan) proximity rings as risk-precursor context around a selected site — not new markers, just a ring on the detail map.

- **[low]** BLM Abandoned Mine Lands and DOI orphan oil & gas wells — large-count, low-per-site-value federal-land universes (Pennsylvania alone has ~27k documented orphan wells); worth clustering visually rather than adding per-site markers if ever built.

- **[med]** BRAC parcel-level transfer/deed status via a per-Service PDF scrape (Navy `bracpmo.navy.mil`, Army AEC, Air Force AFCEC) — the only public path to the actual ~500-1,000 parcel records behind the 27 BRAC installation dots; multi-week effort, small closed universe.

- **[med]** GSA FRPP + SAM.gov/disposal.gsa.gov listings as a first-class "actually offered" federal-parcel overlay, instead of the per-row deep-links that exist today.

- **[med]** More `STATE_PARCEL_SOURCES` registry rows. 11 states registered today; Texas's host migrated behind a token wall since the last probe and needs re-checking, and any state GIS portal with a parcels FeatureServer exposing an owner field is a one-row addition.

- **[low]** Nickel tab: distance to an actual water body, not just to a gage — `water_gage_mi` locates the flow figure, not the shoreline, so a Great Lakes site with no gage nearby reads as nothing in range. NHD small-scale waterbodies (~20k polygons) would fix this cheaply.

- **[low]** Nickel tab: `nickel_acid_mi` (distance to bulk sulfuric acid) is computed by the connector but never rendered anywhere — no detail row, no CSV column, no provenance entry. Either add one or drop the field; a field no surface reads quietly rots.

- **[low]** Workforce by industry, not headcount — Census CBP county employment in NAICS 325 (chemicals) and 331 (primary metal) would make the workforce signal mean what site-selection criteria actually cite. Needs `CENSUS_API_KEY`, same unlock as the Spec 02 connector.

- **[low]** Curated comparable-transactions feed — recent brownfield-to-DC/reactor conversions, manually maintained, the same pattern as `reference-campuses.json`.

### Siting / evidence surfaces
- **[med]** Development-readiness tiers as a first-class filter. `readiness_tier` (cleanup-complete / construction-complete / LIFOC / assessment-complete) is drafted in the schema notes from the 2026-05-04 research pass; the cumulis-scrape and ACRES-cleanups joins in §3 #14-15 are the data prerequisite, and a `READINESS_LEGEND`-style filter section is the UI half.

- **[med]** EPA site-profile Redevelopment-tab scrape for RAU (Ready for Anticipated Use) dates and reuse-accomplishment narrative — the richest single public source for Superfund readiness data, HTML-only, same rate-limited scrape pattern as the existing document connector.

- **[med]** Remediation-timeline visualization in the detail panel (SI → RI/FS → ROD → RD/RA → Construction Complete → Deleted), once the milestone dates above are on disk.

- **[med]** Radius/"near me" address search — geocode via Nominatim (no key) and filter the corpus by Haversine distance, with the radius drawn on the map.

- **[med]** Second federal-site dossier beyond DOE Sites — INL or Oak Ridge/ETTP, both already curated in `federal-clean-energy.json` as flagship sites (Spec 11, H3).

- **[med]** DOE NEPA-action tracker per Hanford parcel — poll the DOE NEPA reading room for new CX/EA/EIS actions and stamp `nepa_review_document_url` per parcel so `availability` stays evidence-backed between manual audits (Spec 11, H2).

- **[med]** OR-SAGE hazard/exclusion layers recast as evidence-category flags. The ten ORNL OR-SAGE parameters (seismic PGA, slope, wetlands, protected lands, population density, and others) are still a sound, GIS-computable data-fetch idea — only the now-superseded Spec 03's scoring-penalty integration is dead. Re-target the join at `evidence-categories.js` instead of the retired score files.

- **[low]** Narrow microreactor vendor-to-site matching to the one defensible criterion available today — the published no-grid-required claim (Antares R1, BWXT Pele) against `microreactorIsOffGrid()` — rather than the general fit-score idea in the now-superseded Spec 07, since every other spec that would drive a real match is unpublished for 11 of 12 vendors.

- **[low]** BRAC Local Redevelopment Authority (LRA) reuse-plan manual curation — 27 sites, a closed list, worth a one-time hand-curation pass rather than a scraper.

- **[low]** Unverified-figure re-checks on the DOE Sites dossiers: Portsmouth's diverging campus job figures (10k/2k DOE vs. 35k/2.5k FAST-41 scope, presented unreconciled), Paducah's 2031-vs-2032 completion date, and WIPP's fill percentage (42%, dated Apr-2023) and workforce count (~1,100, dated Jun-2017).

- **[low]** Bathymetry/channel-depth layer for the Maritime tab's offshore-nuclear screen — no public source identified yet despite the 1970s Offshore Power Systems precedent citing a 70 ft deep-water threshold.

- **[low]** Expand the curated shipyard list past 16 via MARAD's PDF annual survey (~154 active private yards, most too small to be relevant, but a systematic pass could surface a few more heavy-fabrication yards).

- **[low]** Named 2026 floating-nuclear pilots (Bluecore Energy at Port of Long Beach, Core Power + Port of Corpus Christi) as map context, once there's enough of a track record to justify a dedicated curated overlay.

- **[low]** Point the shipyard evidence link at the matched yard's own `source_url` instead of a generic MARAD landing page.

- **[low]** Add `port-proximity.json` to `validate_against_sources.py`'s evidence-roster so the link checker actually exercises `port_mi`/`shipyard_mi`.

- **[low]** Watchlist/portfolio (localStorage site-starring, no backend) for BD workflows tracking a candidate shortlist.

- **[low]** Side-by-side comparison view for 2-3 sites — no competing public tracker has this.

- **[low]** Public read API / embed widget over `docs/data/*.json` for external developers and news/brokerage embeds.

- **[low]** Saved search + email alert on new matching sites — needs a thin backend (Cloudflare Worker + a free email-sending tier).

- **[low]** Print/PDF site card for pitch decks.

### UX / performance
- **[med]** Header/navigation IA rethink, as its own research + design pass, not a quick tweak. The 11-tab bar reads as three different kinds of thing — corpus views (Map/Table/Explore), curated single-purpose analyses (Retired/Coal/Nuclear/Microreactors/DOE/Maritime/Nickel), and reference (Data & methods) — with no visual grouping between them. Table vs. Explore overlap is unresolved, "back to map" affordances are inconsistent across curated tabs, and Explore's status as the default landing view is worth re-confirming now that curated content has grown this much. See §7.

- **[low/med]** Revisit the JTBD quick-start strip now that its three routes duplicate paths already reachable from Explore/Rankings lens buttons and the Nuclear Siting tab directly — fold into the IA rethink rather than deciding in isolation.

- **[low]** Loading-progress chip during ACRES marker hydration (chunked hydration already killed the freeze; this would help slow mobile connections specifically).

- **[low]** Render actual site-boundary polygons on zoom-in instead of flattened centroid markers — would need the per-fragment geometry kept on disk (currently dropped after the multi-polygon merge).

- **[low]** Portrait-mobile map crop — `fitBounds` over the wider-than-tall `US_BOUNDS` clips the West Coast off-screen on a narrow portrait viewport.

- **[low]** Tile self-hosting (Protomaps or MapTiler free tier) if traffic grows past what the current vector basemap comfortably serves.

- **[low]** PWA/offline cache via a service worker for repeat visits.

- **[low]** Pre-compile `prettyPlace`/`prettyName` regexes as module constants instead of inline literals — minor, V8 likely already caches them.

- **[low]** Single-pass KPI-deck computation — merge the four separate `sites` scans in `updateKpiDeck()` into one `reduce()`.

### Engineering hygiene
- **[med]** Run `check_writing.py` in CI, not only in `pr_gate.sh` — a PR opened without running the local gate ships banned phrasing unchecked today.

- **[med]** Extend `scripts/select_tests.py` coverage as the suite grows. The impacted-test selector maps changed files to the tests that can observe them and fails open on anything unrecognized; a new test file needs an explicit rule or it only ever runs via the full suite.

- **[low]** Assert `OVERLAY_SCHEMA_FILES.keys() ⊆ OVERLAY_FILES` (and the same for `CURATED_PROVENANCE_FILES`) in `validate_data.py` — a one-line guard that makes the 2026-08-24 half-registration trap structurally impossible instead of just documented.

- **[low]** Triage the remaining `citation-meta` WARNs in user-visible copy (`python3 scripts/check_writing.py --only citation-meta`) — each is a judgment call between adding a link and adding the phrase to the allowlist.

- **[low]** Two AI-slop shapes `check_writing.py` still can't catch: bland unpatterned prose, and one-off awkward jargon. Neither is regex-detectable; if this keeps recurring, the fix is a review checklist or an LLM pass, not more regexes.

- **[low]** Install Node.js on this dev machine so `tests/test_evidence_categories.py` can run locally without the `node` shell-out failing — all 14 local unit-test failures found today are exactly this one environment gap.

## 5. Blocked, dead ends, and decided-against

- **EPA ACRES acreage — 0/36,003 populated.** The source FeatureServer has no acreage column; the per-property PPF page now redirects to EPA's SSO login. data-source-research.md.

- **DOD FUDS acreage — 66% missing.** Layers 3/7 have polygons but cover cleanup-zone subsets, not the full property; joining them would systematically understate acreage. CLAUDE.md "ACRES + FUDS acreage gaps are dead-ends."

- **Nationwide parcel owner/acreage data.** No public nationwide parcel dataset exists; commercial-only (Regrid/Landgrid, ~$30k+/yr). Per-state cadastral registration (11 states today) is the only viable free path.

- **Electric utility service-territory polygons.** HIFLD's layer went private 2025-08-26; the NASA NCCS mirror 503s, the ArcGIS sharing-API item is inaccessible, and PUDL's GeoParquet alternative needs `pyarrow` (breaks the pure-Python spatial architecture) and is a county-level reconstruction, not true service-area polygons.

- **Nationwide fiber-backbone routes.** No public dataset ships fiber as polylines; FCC's National Broadband Map is address-level binary at ~80 GB bulk, and OSM `cable=fiber` covers under 10% of the US backbone. This is why the fiber item in §3 is scoped as a small regional pilot, not a national layer.

- **SEMS REST API / AFL (Anticipated Future Land Use) codes.** Confirmed dead ends — SEMS-internal fields, FOIA-only, not exposed on any public page or FeatureServer.

- **`iso-rto`'s 1,709 AK/HI/PR/territory records.** Structurally outside any organized electricity market — not a backfill candidate.

- **DERA/DERP and USACE FOST deed records.** PDF-only, no central index, scattered across 38+ USACE districts.

- **A single composite 0–100 suitability score.** Decided against and removed 2026-09-12 (PR #36) — replaced by sourced evidence categories. See Appendix A specs 03/05/07 and `docs/specs/spec-infrastructure-scoring-audit-2026-09-12.md`.

- **Per-site ESA/wetlands/NRHP/air-quality screens over the full corpus.** ~19 hours per layer — the same shape as the flood-backfill trap; refused in `nepa-mcp-integration-spec.md`.

- **Adding `nepa-mcp` to `requirements.txt`.** Needs Python 3.12; this project floors at 3.9. Kept as an isolated `uv`-pinned agent-time tool instead.

- **PAD-US national protected-areas connector.** Deferred after a size/reliability probe; Janus uses bounded 0.1-mile point context with one explicit timeout instead.

## 6. Daily site-refresh queue

The 2 pm research routine (`brownfield-daily-site-research`: at most 20 minutes and one Sonnet subagent per run) works down this list. Each run takes 2 sites and covers each one fully: news, local permits, authorizations, filings and documents for the site area, and checks of the fields the site shows against sources. Results are merged into `docs/data/site-research.json` by `scripts/site_research.py` (schema-checked; every development cited) and appear in the site's detail panel: a "Researched …" line on Overview and the dossier on the Summary tab, which replaces the template summary for that site. Coverage is narrow on purpose: each site the routine touches gets a full pass, and most of the 46,759 sites will not have a dossier for a long time.

Rules the routine follows:
- Order: dossiers past `next_review` (`scripts/site_research.py due`) first, then `queued` and `retry` rows top-down.
- Next review: +30 days when a development in the last 90 days was found, otherwise +90 days.
- Keep at least 10 `queued` rows. Refill pools, in order: (1) tracked sites named in a permit or article found during research; (2) corpus sites within 1 mile of a curated asset (coal plants, plants retiring by 2028, confirmed data-center deals, DOE sites); (3) DOE and DoD federal-facility NPL sites; (4) Superfund sites whose shipped acreage looks like a boundary artifact; (5) a random sample by state.
- Field differences go in the dossier. A difference with one cause across many sites also gets an item in section 3.
- The routine works in its own worktree (`.claude/worktrees/routine-site-research`, branch `routine/site-research`), commits there, and pushes when credentials allow. It never merges to main.

| # | Status | Site id | Name | St | Why queued | Last researched | Next due |
|---|---|---|---|---|---|---|---|
| 1 | queued | KY8890008982 | Paducah Gaseous Diffusion Plant (USDOE) | KY | DOE picked it for an AI computing campus (Jul 2026); Kentucky PSC approval pending | — | — |
| 2 | queued | SC1890008989 | Savannah River Site (USDOE) | SC | AI/energy lease selection (Amentum, Jul 2026); no lease signed yet | — | — |
| 3 | queued | ACRES-240696 | Bessemer Campus Expansion Site | AL | 1.2 mi from Project Marvel (QTS confirmed Jul 2026); rezonings and utility filings likely | — | — |
| 4 | queued | ID4890008952 | Idaho National Engineering Laboratory (USDOE) | ID | AI-infrastructure land offer and DOME reactor tests; shipped 1.08M acres needs a check | — | — |
| 5 | queued | TN1890090003 | Oak Ridge Reservation (USDOE) | TN | Reindustrialization and AI/nuclear projects nearby (Clinch River permit pending) | — | — |
| 6 | queued | ACRES-140164 | Springdale Boat Ramp and Parking Lot | PA | 0.2 mi from the Cheswick data-center site | — | — |
| 7 | queued | ACRES-157082 | Colstrip City Shop | MT | 0.7 mi from Colstrip; data-center deal at the plant (Sabey/Atlas) | — | — |
| 8 | queued | WI0001954841 | Fox River NRDA/PCB Releases | WI | Shipped 1,129,744 acres looks like a boundary artifact | — | — |
| 9 | queued | WA3890090076 | Hanford 100-Area (USDOE) | WA | Hanford reuse projects (Cereza solar sale, Cascade Xe-100) | — | — |
| 10 | queued | ACRES-118982 | Watercrest/Cheswick Business Park | PA | 0.7 mi from Cheswick Generating Station | — | — |
| 11 | queued | ACRES-111146 | G & R Auto Sales | NC | 0.2 mi from Meta's Forest City campus | — | — |
| 12 | queued | MID980994354 | Tittabawassee River, Saginaw River & Bay | MI | Shipped 726,763 acres looks like a boundary artifact | — | — |
| 13 | queued | AK6210022426 | Fort Wainwright | AK | Army Janus microreactor finalist (no vendor yet); shipped 919,896 acres | — | — |
| 14 | queued | ACRES-137763 | Universal Transmission | PA | 1.4 mi from NorthPoint Keystone Trade Center campus | — | — |
| 15 | queued | FUDS-C03VA1071 | Ordnance General Supply | VA | 1.4 mi from the QTS Richmond campus | — | — |
| 16 | queued | TX4890110527 | Pantex Plant (USDOE) | TX | DOE/NNSA site; energy and land-use activity nearby | — | — |
| 17 | queued | NVD980813646 | Carson River Mercury Site | NV | Shipped 411,014 acres looks like a boundary artifact | — | — |
| 18 | done 2026-09-25 | OKD980629844 | Tar Creek (Ottawa County) | OK | Pilot. Shipped acreage (310,173 ac) is county-sized; DEQ says 25,600 ac | 2026-09-25 | 2026-12-24 |

### Run log
- 2026-09-25 · pilot run in session · Tar Creek (OKD980629844) · 3 developments · 2 field differences (acreage, coordinates) · not pushed: no GitHub credentials on this machine

## 7. Decisions needed from Pranava

- **Landing page (options presented 2026-09-25).** A: a light "Start" page (search, what-are-you-siting entry points, the investigations as cards, a dated "what changed" feed from the research routine), with Explore/Map/Table grouped as the Atlas. B: map-first, but a state-level choropleth that drills into per-state lists instead of 46,759 points. C: keep Explore and fix its first screen (no alphabetical default, compact cards). D: search-first. Recommendation: A now, B's state drill-down later.

- **How research routine commits reach the site.** Default: the routine pushes `routine/site-research` and keeps one rolling PR open for review. Alternative: auto-merge after checks pass, once a few weeks of dossiers have been reviewed.

- **IA and landing decision.** Is Explore still the right default now that curated tabs have grown to 11? Should the tab bar visually group corpus views (Map/Table/Explore), curated analyses (Retired/Coal/Nuclear/Microreactors/DOE/Maritime/Nickel), and reference (Data & methods) instead of presenting all 11 as peers?

- **Table vs. Explore overlap.** Both are tabular/list views over the same corpus with separate code paths. Merge, or keep both with clearer differentiation?

- **Auto-commit policy for `refresh.yml`.** Once `continue-on-error` lands (Now #3), should a partially-successful run auto-commit what it refreshed, or should the commit step still require zero connector failures? Who reviews a partial-success commit before it ships?

- **`CENSUS_API_KEY` / `EPA_AQS_API_KEY`.** Register both (unblocks `census-workforce` and the NAAQS gate), or formally drop those connectors from `--all` and stop the CI noise? Same question for `ANTHROPIC_API_KEY` in CI — keep `ai-summary` static/keyless in the cron, or add the secret so narrative regens happen automatically too?

- **`iso-rto` replacement.** Accept the partial candidate source now (missing NYISO/ISO-NE coverage) and ship a known gap, or hold out for a full replacement and leave the connector unable to refresh in the meantime?

- **Git history rewrite status.** A 2026-08-09 checkpoint recorded a staged-but-unpublished rewrite stripping `Co-Authored-By` trailers from 203 commits (`backup-pre-coauthor-strip` tag still exists). Confirm whether that was ever published, was abandoned, or is now moot — this machine currently has no GitHub credentials either way, so nothing can be pushed until auth is fixed.

- **JTBD quick-start strip.** Keep it, demote it to a first-visit-only prompt, or fold it into the IA rethink above — its three routes now duplicate paths reachable from Explore/Rankings lens buttons and the Nuclear Siting tab directly.

- **Coal Reinvestment universe.** Once the full ~550-plant EIA-860M-derived universe lands (Next #8), should it replace the 18-plant curated catalog outright, or should the curated set stay as a "verified/marquee" layer on top of the derived one?

## 8. Recently done (since 2026-08-20)

- **2026-08-21** — NEPA MCP Tier A installed (isolated `nepa-mcp==0.1.1` via `uv`); Janus screening (6 source screens, 12 map layers, 9 installations); tribal-area containment (TIGERweb AIANNHA, 2,122 sparse-positive hits). `fc4bd2b`, `6b6634c`, `c835907`, `1b6437e`, `d1f2e94`, `e1e7fb3`.

- **2026-08-21** — `refresh.py` empty-inventory guard for the four producer connectors. `6b6634c`.

- **2026-08-21** — Microreactors tab + inverted-grid-isolation siting screen (12-vendor fleet, 32 commitments). `fc4bd2b`. Tab and data are live; the scoring lens was superseded 2026-09-12.

- **2026-08-23** — Coal Reinvestment engine shipped, then fixed same day after 3 red CI guards + several functional bugs found in review; federal clean-energy overlay; curated-row citation corrections after a 24-check primary-source review. `9df4ee8`, `faeae8a`, `bdcddbb`; `scripts/pr_gate.sh` created.

- **2026-08-23** — Executive ranked roadmap + 9 detailed specs written, re-grounded against the Aug-2026 industry sweep. `225c238`.

- **2026-08-24** — Shared NEPA screening engine (`nepa_screening.py`) extracted, 3 production consumers (Janus, Hanford, coal); Hanford E2E dossier tab; coal-tab permitting screens. `06a0c0f`.

- **2026-08-24** — Header/filters redesign + enrichment-loader race fixes + Hanford sourcing pass; DOE Sites v2 restructure (five-site dossier explorer). `a00e382`, `85857b9`.

- **2026-08-25** — `eia-retired-plants` connector fixed (dead `/xls/` download path → `/archive/xls/`, had been broken since ~June). `f5a50f7`. DOM-budget determinism fix, writing linter, plain-English DOE Sites copy rewrite. `1c6825f`.

- **2026-08-27** — Maritime Siting tab: port/shipyard proximity, floating-nuclear and coastal-generation lenses. `986e031`. Tab and data live; lenses superseded 2026-09-12.

- **2026-09-08** — Empty-write guard extended to all 17 enrichment files (357,911 records protected against a blanking write). `853e58c`.

- **2026-09-08** — Nickel Refining tab + the corpus's first water-flow layer (USGS streamgages, two siting lenses). `6f7dbfa` (PR #27).

- **2026-09-12** — Suitability scores replaced by sourced evidence categories (`docs/evidence-categories.js`); legacy `*-score.js` files no longer loaded; Explore (list-first, category findings) became the default landing view. `c56eea2` (PR #36) — the major architecture change this quarter.

- **2026-09-15** — `infra-proximity` MapServer object-ID fix; resolved the cron's recurring TIGERweb highway-layer crash. `e07bed5`.

- **2026-09-25** — Data: `superfund-npl` re-pulled (record-identical, timestamp promoted); EIA-860M moved to the August 2026 workbook and its products rebuilt; full ECHO and Superfund document-list refreshes run.

- **2026-09-25** — Planning: this file became the single plan; old backlog and four superseded plan docs archived to `planning/archive/`.

- **2026-09-25** — Per-site research: `docs/data/site-research.json` contract (schema + `scripts/site_research.py` + validator checks + detail-panel rendering), a Tar Creek pilot dossier, and the daily 2 pm research routine working down §6.

- **2026-09-25** — Fixes: `check_upstream_freshness.py` no longer crashes on infra's bookkeeping metadata; `refresh.py --output` no longer overwrites `data/changes.md`. `refresh.py` now refuses truncated writes (under 90% of the prior file) unless `--allow-shrink`; ECHO backs off on HTTP 429/503 after a throttled refresh wrote 557 of 1,906 sites (caught before commit). Curated-tab fact-check: Janus vendor awards, Palisades restart pause, QTS at Bessemer, Fairless Works construction, Bull Run fusion license, Kemmerer contractor change and NRC hearing dates applied; Vermont dropped from the regulation table.

## Appendix A — Specs index

18 spec files in `docs/specs/`.

| Spec file | Purpose | Status | Notes |
|---|---|---|---|
| spec-cleanup-to-clean-energy-and-mine-lands.md | DOE Cleanup-to-Clean-Energy / CEML federal-land overlay | Done | v1 shipped 2026-08-23, live on the map and DOE-adjacent tabs. |
| spec-coal-reindustrialization-engine.md | Coal-to-nuclear / coal-to-DC conversion catalog + proximity join | Partly done | v1 (Coal Reinvestment tab) shipped 2026-08-23. Open non-score follow-ups in §3 #8 and §4; the score-integration follow-up in the spec's own §7 is superseded. |
| spec-coal-tab-nepa-walkthrough.md | Coal tab NEPA walkthrough + citations upgrade | Ready | Not yet built; supersedes the old "Coal permitting screen needs more detail" item. |
| spec-hanford-doe-parcel-explorer.md | Multi-site federal-land dossier explorer | Done | v2 (DOE Sites: Hanford+SRS+Portsmouth+Paducah+WIPP) shipped 2026-08-24. Follow-ups in §3 #9-10 and §4. |
| spec-infra-data-freshness-and-efficient-refresh.md | Upstream-freshness audit + efficient refresh gating | Partly done | `scripts/check_upstream_freshness.py` shipped and verified working today (§1). CI gating still open — §2 #12. |
| spec-infrastructure-scoring-audit-2026-09-12.md | Assessment behind the evidence-categories migration | Partly done | Approach B (evidence categories) implemented and verified. Approach C (water/fiber pilots, invalidated-join recompute) partly done — §3 #3-6. |
| spec-microreactor-demand-matching.md | Demand-ladder → vendor-compatibility spatial join | Superseded | Core mechanism is `microreactor-score.js`'s scoring, retired 2026-09-12. Narrow off-grid-claim filter salvageable — §4. |
| spec-microreactor-tab-nepa-walkthrough.md | Microreactors tab NEPA-source walkthrough + citations | Ready | Not yet built; unaffected by the scoring change if its "ranked-site preview" reads off evidence categories rather than the retired score. |
| spec-nepa-mcp-gap-analysis.md | What nepa-mcp is missing; upstream proposals | Done (analysis) | Analysis complete 2026-08-24. Filing the actual upstream PRs is still open — §3 #22. |
| spec-nepa-screening-engine.md | Shared reusable NEPA screening engine | Done | v1 shipped 2026-08-24, 3 production consumers. Follow-ups (generic CLI, screen remaining overlays) — §3 #17. |
| spec-nepa-surfaces-expansion-plan.md | Master sequencing doc for specs 13a-13d | Partly done | Sub-specs shipped or ready per their own rows; still the valid sequencing reference, not superseded. |
| spec-orsage-siting-criteria.md | ORNL OR-SAGE 10-parameter siting-criteria layer | Superseded | Core deliverable is a score-penalty function against the retired score files. Data-layer idea (hazard/exclusion flags) recast as an evidence-category candidate — §4. |
| spec-permitting-context-layers.md | Permitting-context layers: coal screens, air-quality gate, precedent surface | Partly done | Coal screens shipped 2026-08-24; air-quality gate blocked on `EPA_AQS_API_KEY` (§2 #6); precedent surface still proposed. |
| spec-queue-dynamics-and-regulatory-reaudit.md | LBNL interconnection-queue data + automated eCFR regulatory tracker | Ready | No code started; no scoring dependency. §3 #13. |
| spec-repowering-universe-and-substation-validation.md | EPA RE-Powering 190k-site universe + substation cross-validation | Ready | No code started; no scoring dependency. §3 #12. |
| spec-reuse-dossier-and-nepa-precedent.md | Single-site reuse dossier + industrial-precedent engine | Ready | No code started (`connectors/nepa_precedent.py`, `docs/dossier.js` don't exist). Ranked #1 in the Aug-2026 roadmap. §3 #7. |
| spec-water-stress-and-cooling-intake.md | WRI Aqueduct + USGS 7Q10 water-stress/cooling-intake layer | Superseded | Scoring mechanism targets the retired score files. Data prerequisites absorbed into the Approach C water pilot — §3 #3. |
| spec-workforce-socioeconomic-intelligence.md | Census ACS/LEHD workforce + socioeconomic layer | Partly done | `connectors/census_workforce.py` built, registered, and tested; blocked on `CENSUS_API_KEY`. `lehd_commute.py` half not started. §3 #11. |

## Appendix B — Reference docs

- **design.md** — the visual/interaction design system: tokens, components, responsive rules, editorial conventions.

- **data-source-research.md** — verified API-probe log; read before probing a new federal GIS endpoint or spawning a discovery fan-out.

- **manufacturing-reuse-opportunities.md** — 7-sector manufacturing-reuse analysis behind the Rankings Manufacturing lens.

- **nepa-mcp-integration-spec.md** — nepa-mcp 0.1.1 integration scope, approved safe boundaries, six use-case scenarios.

- **ap1000-water-validation.md** — citation-grade water-availability validation for the 14 Nuclear Siting installations.

- **uat.md** — UAT session log; page-specific quirks and the most recent run's findings.

- **docs/infrastructure-data-guide.md** — what the evidence layers can and cannot establish (grid, fiber, water, land, logistics); no composite score, sites are alphabetical.

- **issues.md** — the bug log; not part of this planning consolidation.

- **research/doe-lab-brownfield-reuse.md** — DOE national-lab literature on brownfield reuse and large-load siting criteria.

- **research/doe-sites-curation-2026-08.md** — provenance log for the SRS/Portsmouth/Paducah/WIPP dossier curation.

- **research/grid-rebuild-validation-2026-09-12.md** — infrastructure recompute and validation against refreshed core coordinates.

- **research/industry-topical-2026-08.md** — August 2026 industry-sweep notes (bookmarks + trade press + primary sources) behind the Aug-2026 spec revisions.

- **research/infra-accuracy-review-2026-09.md** — infrastructure-accuracy review prompted by the nickel-candidate sites, corpus-wide in scope.

- **research/infra-grid-fiber-water-audit-2026-09-12.md** — pre-implementation source assessment for grid/fiber/water, companion to the scoring-audit spec.

- **research/nepa-mcp-capability-census-2026-08.md** — live capability census of nepa-mcp 0.1.1 (19 servers, 46 tools, 32 GIS layers).

- **research/nepatec-reindustrialization.md** — NEPATEC patterns for brownfield reindustrialization; motivates the reuse-dossier spec.

- **research/nickel-candidate-sites-2026-09.md** — candidate US nickel-refinery/smelter sites generated from the nickel lenses.

- **research/nickel-catalog-source-audit-2026-09-12.md** — bounded citation audit of the nickel catalog's claims.

- **research/nickel-refining-siting-2026-09.md** — nickel refining/smelting siting requirements research.

- **research/nickel-supply-chain-geography-2026-09.md** — US nickel supply-chain geography, companion to the siting research.

- **research/ux-uat-2026-09-12.md** — infrastructure-assessment UX and performance audit behind the Explore-as-default change.
