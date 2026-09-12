# Infrastructure evidence: what the data can establish

Updated 2026-09-12. The atlas now presents separate findings for grid, fiber, water, land and logistics. Sites are alphabetical. There is no composite suitability score or numeric best-first order.

## Findings and confidence

A finding describes an observation: evidence found, a documented constraint, or unknown. Confidence describes support for that observation. High requires current, direct, site-specific evidence; Medium fits recent mapped context with a known source; Low fits stale, indirect or proxy evidence. Unknown findings have no confidence rating. A well-documented constraint can have high confidence; confidence is not a recommendation.

The current model does not assign High confidence: no direct verification contract is implemented yet. Keeping High in the legend and filter defines the evidence standard; an empty High result is expected. For mapped context, the model uses a 730-day source-age boundary: a known snapshot within that period can support Medium when the location is not flagged or a proxy; older, missing-date, retained or indirect evidence stays Low. This is a conservative editorial policy, not a statistically calibrated probability or a claim that infrastructure expires after two years.

Most current infrastructure observations support mapped context, not verified service. Coverage gaps remain visible and do not confer an advantage. A completed spatial search is not proof that the source inventory is complete.

## Grid

Transmission features come from a public HIFLD-derived ArcGIS layer. Substations come from OpenStreetMap through Overpass. Dates, coverage and equipment definitions differ. Substations may include distribution or railway traction assets. Public points and lines cannot establish spare MW, a permissible connection route, interconnection rights or a utility commitment.

Distance is measured from the site's reported point. Curated military installations can inherit a cleanup-site reference point. Neither is the same as a surveyed project footprint. No mapped feature within the search radius means no match in that search, not off-grid status.

[Infrastructure records](data/infra-proximity.json) · [OpenStreetMap](https://www.openstreetmap.org/)

## Fiber

There is no joined nationwide enterprise fiber serviceability inventory. Analyst adjectives and regional carrier presence cannot establish service at a parcel. The 14 curated military installation ratings lacked dedicated fiber citations and must remain unknown until evidence is attached.

Seek a carrier response for the actual parcel covering capacity, construction cost and route diversity. Residential broadband availability can provide context, but does not prove an enterprise circuit or two independent paths.

The first regional pilot identifies MassBroadband 123's operating middle-mile footprint for one Franklin County record. It establishes regional network context only. Route distance, parcel service, carrier, capacity, latency and independent paths remain unresolved.

## Water

USGS monitoring locations and flow statistics provide stream context. The nearest gage may be in another catchment. Annual mean discharge does not establish drought supply, accessible intake or unallocated water. Storage, existing withdrawals and historical design requirements must be kept separate from spare capacity.

A supply assessment requires source-matched low-flow or firm-yield analysis against project demand, intake feasibility, water quality and an allocation or supply agreement. NPDES permits authorize regulated discharge; they do not establish withdrawal rights. The Arnold reservoir citation describes a historical design requirement, not measured current or spare water supply.

[Water context records](data/water-proximity.json) · [USGS Water Data](https://waterdata.usgs.gov/) · [EPA NPDES basics](https://www.epa.gov/npdes/npdes-permit-basics)

The first network pilot links one site point to USGS NLDI flowline `10294630` and WBD HUC12 `010802030402` (Lower Green River). This establishes network identity, not intake access, reliable flow, project demand or entitlement.

## Land, logistics and other tabs

Reported acreage may cover a whole installation, cleanup site or matched cadastral parcel. It does not establish ownership, developable area or availability. Roads and rail nearby do not establish access, a spur, load limits or a freight agreement.

Explore and shared-corpus use views draw from Superfund, ACRES, FUDS and BRAC records. Nuclear installations, vendor commitments, coal assets and DOE dossiers are separate curated populations. Former military use does not establish current federal ownership; nearby generation does not establish a customer load; a supply-chain point does not establish available material.

## Nickel locations

Supply-chain locations retain their own identities, sources and project status. They do not establish available material or purchase contracts. Ford Glendale's LFP conversion is excluded from nickel demand; discontinued Beulah is excluded from proximity matching. Mixed-chemistry plants remain context with unknown nickel volume. Retained historical records keep their original audit dates. See the repository's September 12 nickel source assessment for all 16 records and unresolved claims.

## Coal and retired industry

Ceasing EPA greenhouse-gas reporting does not establish closure or an available property. Coal catalog pathways are reported screening categories, not verified suitability. DOE coal-to-nuclear study findings and modeled savings apply to that study's scope, not automatically to other industrial sites or data centers. A retired interconnection or nearby switchyard does not establish transferable rights, spare capacity or queue exemption; a proposed reuse needs utility or grid-operator review.

## Freshness and reproducibility

Each source has its own coverage, source date and processing date. The header reports the newest loaded artifact; it does not certify that every source was rechecked that day. Detail panels and CSV exports retain findings, confidence, reasons and sources. Missing evidence is labeled explicitly.

The source repository contains the detailed dataset and UX audits under `research/`, including the September 12 infrastructure review. Read the data records and their source metadata before making a project-specific judgment.
