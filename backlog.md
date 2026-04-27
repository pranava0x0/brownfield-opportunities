# Backlog

Ideas and enhancements. Priorities: **high** = next, **med** = soon, **low** = nice-to-have.

---

## v1 follow-ups (data completeness)

- **[high] Expand beyond top-100.** Lift the limit to all 2,114 NPL Superfund sites with acreage. Will likely need state-sharded JSON + lazy load to keep payload under ~1MB per shard.
- **[high] Sites without acreage.** ~A few hundred features lack `GIS_AREA` or have non-acre units (Miles, null). Currently dropped on the floor. Add a fallback bucket so those sites still appear (sorted alphabetically or by ORIGINAL_CREATION_DATE), with acreage shown as "N/A".
- **[high] EPA Brownfields (ACRES).** ~40k sites from EPA's Assessment, Cleanup and Redevelopment Exchange System. Distinct from Superfund — usually smaller, urban, and further along in cleanup. Pull from Envirofacts (table names: `BF_ASSESSMENT_PROPERTY`, `BF_CLEANUP_PROPERTY`) or the public ACRES export.
- **[med] State environmental agency sites.** Each state has its own brownfield/voluntary cleanup program (NY State Superfund, CA DTSC EnviroStor, TX VCP, etc.). Aggregate via a connector framework — one normalizer per source.
- **[med] RCRA Corrective Action sites.** EPA Resource Conservation and Recovery Act sites under corrective action — another large universe of contaminated industrial properties.
- **[low] DOD FUDS (Formerly Used Defense Sites).** USACE-administered. Big, often rural, sometimes acquirable.

## Site-level enrichment (Owner / encumbrances / history)

- **[high] Current owner.** Not in EPA data. Source options:
  - County recorder offices (per-county scraping; messy, no standard schema)
  - **ReportAll USA / Regrid / Loveland Tech** — paid parcel APIs covering ~3,000 US counties
  - State assessor open data (varies wildly)
  - Strategy: start with a single high-value state (e.g. NJ — has a free statewide parcel layer)
- **[high] Historical owners.** County deed history. Same access constraints as above; some title-search vendors expose APIs.
- **[high] Encumbrances.** Liens, easements, environmental covenants (institutional controls). EPA's *Superfund Institutional Controls Tracking System (ICTS)* publishes some of this; needs investigation.
- **[med] Remediation detail.** Current site only carries NPL status code. Add: Record of Decision (ROD) summary, current cleanup phase, remedy type, lead party (PRP/EPA/state), Five-Year Review status. EPA SEMS has these in adjacent tables.
- **[low] Site-specific contamination profile.** Contaminants of concern, media affected (groundwater/soil/sediment), exposure pathways. SEMS has it.

## Infrastructure proximity (the data-center thesis)

All deferred from v1. Compute at refresh time, bake into JSON.

- **[high] Transmission lines + substations.** [HIFLD Open](https://hifld-geoplatform.opendata.arcgis.com/) Electric Power Transmission Lines + Electric Substations layers. Nearest-neighbor distance via shapely + rtree.
- **[high] Available transmission capacity.** Going beyond "is there a wire nearby" — **FERC Form 715 / OASIS / regional ISO interconnection queue position**. This is the actual gating factor for data-center siting; hyperscalers care about MW available, not line count.
- **[high] Major roads + interstate access.** HIFLD Primary Roads. Nearest-distance + drive-time from nearest interstate exit.
- **[high] Rail.** HIFLD North American Rail Network. Distance to nearest active line + classification (Class I/II/III).
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

- **[high] Polygon overlays on map.** Currently we flatten polygons to a centroid marker. Render the actual site boundary on zoom-in.
- **[med] State filter, status filter, acreage range slider.** Faceted filtering on both map and table.
- **[med] Search box.** Free-text search by site name / city / county.
- **[med] URL state sharing.** `?site=<EPA_ID>` deep-links to a specific site's detail panel.
- **[med] CSV export.** "Download filtered set as CSV" button on the table.
- **[low] Print/PDF site card.** For pitch decks.
- **[low] Light theme toggle.** Currently dark-only.

## Performance / hosting

- **[med] Tile self-hosting.** OSM tile policy discourages heavy production use. If the dashboard gets traffic, switch to a free vector-tile provider (Protomaps + free tiles, or MapTiler free tier).
- **[med] State-sharded JSON.** When the dataset grows past ~500 sites, shard `sites.json` by state and lazy-load on map pan.
- **[low] PWA / offline cache.** Service worker for repeat visits.

## Engineering hygiene

- **[high] Tests for refresh.py.** Mock the EPA API response; assert normalize() handles all unit variants and missing fields.
- **[med] Schema validation.** Pydantic model for the output JSON; CI fails if schema drifts.
- **[med] Diff log.** When `refresh.py` runs, write a `data/changes.md` summary of which sites were added/removed/changed since last run.
