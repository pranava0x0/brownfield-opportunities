# Grid, fiber and water: dataset and tab audit

2026-09-12. This section preserves the pre-implementation source assessment. Approach B subsequently repaired the datasets and category UI; see the implementation ledger and final validation below.
Companion to [the implementation assessment](../docs/specs/spec-infrastructure-scoring-audit-2026-09-12.md).

## Main finding

Mapped infrastructure coverage is high, but evidence of usable service is sparse.
The current rankings conflate the two. Replace 0–100 totals with category findings
and confidence in each finding. First fix wrong source interpretations and retain
enough metadata to explain what was measured.

## 1. Grid datasets

| Dataset | Source and actual snapshot | What it establishes | What remains unknown |
|---|---|---|---|
| Transmission | [HIFLD ArcGIS layer](https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0), data edit September 5, 2023 | Mapped line geometry and reported voltage | Distribution coverage, spare capacity, feasible connection, rights, current physical status |
| Substations | OpenStreetMap Overpass, raw cache May 17, 2026 | Contributor-mapped nodes/ways, sometimes voltage and role | Completeness, owner-confirmed service, capacity and connection terms |
| Power plants | [HIFLD/EIA mirror](https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Power_Plants_in_the_US/FeatureServer/0), data edit July 1, 2025 | Facility location, fuel and maximum summer capacity | Available power, transferable interconnection, project service commitment |
| Retired/planned plants | [EIA-860M](https://www.eia.gov/electricity/data/eia860m/) | Preliminary generator inventory and status | Rights retained after retirement, capacity available to this candidate |

The published infrastructure file's July 27 generation date is not a source
snapshot date. Individual source vintages and OSM attribution are missing from
its generic envelope. Plant schema edited August 2026 does not mean its data
updated then.

Cached transmission features: 52,244. Cached plants: 13,446. Both match the live
service count today. There is no demonstrated feature-count shortfall. However,
ingestion lacks stable ordering, ID deduplication, expected-count reconciliation
and transfer-limit checks. Equal counts also do not establish identical content.

### Substations: classification is being discarded

Raw OSM cache: 77,967 elements, 77,965 unique. 20,368 have no voltage. Replaying
the current nearest-asset method over site points gives:

| Nearest asset role | Candidate records |
|---|---:|
| Unspecified | 18,023 |
| Distribution | 17,556 |
| Transmission | 3,506 |
| Minor distribution | 2,865 |
| Industrial | 1,729 |
| Traction | 488 |
| Gas | 10 |

These are replay counts by selected role, not a national inventory census.
Other role values and unmatched sites account for the remainder. The connector
discards role, name, operator and ID before publication. See
`connectors/infra_proximity.py:727–755` and the
[OSM role definitions](https://wiki.openstreetmap.org/wiki/Key:substation).
They must not all become equivalent evidence of a transmission connection.

Published voltage is missing for 12,286 of 46,328 substation matches; another
7,059 have less than 69 kV. Alaska has 821 sites, 547 substation matches and only
54 voltages. Query regions omit Guam, Northern Mariana Islands and American
Samoa; only one of Guam's 62 sites has a published match, and none of MP's 53
or AS's 33 does. Overpass queries omit relations too.

The eight-ring spatial search also misses some assets inside its advertised
100-mile range. Missing therefore cannot prove isolation. Current microreactor
scoring nevertheless awards full isolation and an 'off-grid' label.

### Voltage and plant capacity

The DC/generation/manufacturing grid helper substitutes substation distance but
borrows an unrelated line's voltage for 1,979 published records. Preserve the
distance and voltage of the same asset. The class fallbacks `UNDER 100 → 69`
and `DC → 500` are also invalid exact-value assumptions. They are latent in the
present transmission cache: all 52,244 cached records have positive numeric
voltages, so do not claim that the fallback caused current published values.

HIFLD `Total_MW` means maximum summer capacity. Installed nameplate capacity is
another field, `Install_MW`. None of the published proximity rows carries
`power_plant_retired`; code paths inspecting that flag cannot establish operation.
Retain source plant/generator IDs, status and explicit capacity type.

EIA's current page lists **July 2026 data, released August 26**. Both producer
scripts still select April. The existing freshness script finds only June
because it probes archive paths; July is under `/eia860m/xls/`, not
`/eia860m/archive/xls/`. Repair discovery using actual published links and test
both paths. EIA explicitly says its preliminary capacities are not facility
commitments.

## 2. Fiber datasets

### What the project has

- No national fiber connector or site-level fiber join for the 46,759-site corpus.
- All 14 Nuclear Siting records have analyst ratings: six excellent, five good,
  two moderate, one limited. **Zero have `fiber_source_url`.**
- `docs/app.js:_ap1000SourceFor` substitutes `acreage_source` for missing fiber
  citations. Those links often point to general installation or Wikipedia pages.
  A displayed citation is not necessarily evidence for fiber.
- `scripts/build_ap1000_sites.py` hardcodes ratings from metro proximity and
  presumed DISN service. These do not establish commercial service at an offered
  parcel, carrier diversity, dark fiber, capacity, latency or resilience.
- DOE dossiers have some regional narrative context. Portsmouth expressly lacks
  a confirmed reservation connection; Paducah cites a developer claim and labels
  aggregator evidence separately; Hanford cites regional network context. SRS and
  WIPP omit fiber claims. Keep these distinctions.

### Public sources worth using

The earlier report's 'fiber is not a gap we can close' is too categorical.
Complete national commercial backbone geometry was not established in this
audit. Regional and source-specific evidence is still available.

| Source | Useful evidence | Limits / integration rule |
|---|---|---|
| [FCC National Broadband Map](https://help.bdc.fcc.gov/hc/en-us/articles/13532984820379-What-s-on-the-National-Broadband-Map) | Provider-reported availability, technology and advertised speeds at mapped serviceable locations | Not backbone routing, enterprise capacity, performance, dark fiber or redundant paths; require address/location identity, never nearest-address substitution |
| [NTIA middle-mile awards](https://broadbandusa.ntia.gov/funding-programs/enabling-middle-mile-broadband-infrastructure-program/award-recipients) | Awarded projects and route context | Award is not construction completion or live service; retain status |
| [MassBroadband 123 maps](https://broadband.masstech.org/map-gallery) | Public cable routes and points of interconnection | Regional network maps here are dated January 2014; require current operator verification |
| [ESnet maps](https://www.es.net/engineering-services/the-network/network-maps/) | DOE research-network connectivity and topology | Science-network access is not commercial access for an adjacent development parcel |
| [The Quilt network directory](https://www.thequilt.net/about-us/the-quilt-participants/) | Find accountable regional network operators | Discovery source, not proof a candidate parcel is served |

MCNC and GCI operator pages also surfaced useful regional leads, but full-page
retrieval returned 403 and 404 respectively for the attempted URLs. Do not promote
search excerpts into newly verified parcel claims. Obtain stable operator pages
or public records in the implementation pass.

Recommended fiber evidence fields: location/parcel identity, provider/network,
source URL, source date, claimed technology, service status, evidence scope
(parcel / facility / corridor / regional), and unknown capacity/route diversity.
Leave unassessed sites explicitly Unknown. Do not synthesize fiber miles from
schematic national network maps.

## 3. Water datasets

| Dataset | Present coverage | Meaning |
|---|---|---|
| USGS selected-gage catalog | 8,730 gages | Active stream/discharge inventory with mean annual flow at least 5 cfs; filtered monitoring population |
| Site-to-gage join | 45,946 / 46,759 sites | Qualifying catalog gage within 50 miles |
| Distant matches | 9,361 more than 10 miles away | Weak site relevance until catchment and water-source identity are established |
| Short records | 5,574 sites linked to gages with fewer than ten years; 16,768 fewer than thirty | Unequal observation histories hidden by published join |
| Nuclear curated water | 14 records with water labels | Analyst interpretation; no correctly typed quantitative low-flow value found |

Matched counts by program: Superfund 1,891/1,908; brownfield 35,741/36,003;
FUDS 8,288/8,821; BRAC 26/27. Missing gage matches include AK 279, GU 61,
MP 53, AS 33 and VI 23. Catalog coverage excludes unsupported regions and
low-flow/small-stream gages by design. It excludes lake/reservoir shorelines,
groundwater wells, municipal or reclaimed-water contracts and intake assets.

### Data and interpretation defects

1. **Robins:** `water_low_flow_cfs=854` is actually the 2012 annual mean, 854.1,
   in retained `ap1000-water-evidence/usgs/02213000-annual-mean.rdb.txt:118`.
   The scorer treats it as low/drought flow. Retype it and remove it from the
   low-flow calculation. The related 42/854 percentage is approximately 4.9%,
   not the 7.3% in the note.
2. **Arnold:** a claimed current withdrawal of 22.4 billion gallons/year comes
   from a historical preconstruction requirements estimate in the cited
   [Arnold article](https://www.arnold.af.mil/News/Article-Display/Article/3163926/woods-reservoir-completed-70-years-ago-this-month/).
   Existing reservoir use is not measured current withdrawal or spare supply.
3. **Nickel:** gage distance multiplied by annual mean drives a 24-point term.
   It has no basin identity, intake route, drought yield, demand or allocation.
   That term ranks monitoring geography, not demonstrated water suitability.
4. **Freshness:** the streamgage builder stamps today's `verified_at` on cached
   responses, loses first/last observation years, and joins omit even record
   length, drainage area and verification date. Preserve actual retrieval and
   observation periods. 483 gages lack drainage area.
5. **Partial data:** failed statistics batches continue without making the whole
   build incomplete; merge retains obsolete gages indefinitely. Region-scoped
   preservation needs explicit status and successful-replacement semantics.
6. **Geographic metadata:** gage 12355000, Flathead River at Flathead British
   Columbia, is tagged AK because builder stores requested state rather than
   returned geographic identity.
7. **Rights:** 'obtainable' classifications and 'effectively unlimited' notes
   exceed project-specific evidence. An [NPDES permit](https://www.epa.gov/npdes/npdes-permit-basics)
   concerns pollutant discharge; it does not establish intake rights, water
   capacity or transferable entitlement. Current detail-panel copy implies those.

### Better water evidence

Use three separate questions: **source/access**, **reliability**, **entitlement**.
Current gage data supports regional hydrologic context only. Confidence in supply
must reflect the link to the site's actual source, statistic and demand.

- [USGS NHDPlus HR](https://www.usgs.gov/national-hydrography/nhdplus-high-resolution)
  provides flowlines, waterbodies and catchments for basin-aware work; retain its
  regional coverage limitations.
- [USGS StreamStats](https://pubs.usgs.gov/publication/fs20173046) can provide
  applicable gaged/ungaged low-flow estimates. Preserve region, method, statistic,
  observation period and uncertainty. Do not assume uniform national 7Q10 coverage.
- Utility contracts, withdrawal permits and published intake assessments are
  separate sources for availability. Discharge compliance is a different category.
- Current builder uses WaterServices. USGS announces retirement in Q1 2027;
  [migration planning](https://waterdata.usgs.gov/blog/api-waterservices-decom)
  is needed before relying on future unattended refreshes.

## 4. Which sites and tabs use this evidence?

| Tab / dataset | Population | Grid / fiber / water basis |
|---|---|---|
| DC, generation, manufacturing | Shared 46,759 cleanup/federal records | Shared grid proximity; current totals omit fiber and supply-water assessment |
| Microreactor candidates | Filtered shared corpus | Grid distance inverted to isolation; plant presence treated as demand; no fiber/water assessment |
| Microreactor fleet/commitments | Separate 12 vendors / 32 commitments | Curated project evidence; not infrastructure-verified corpus candidates |
| Nuclear Siting / AP1000 | Separate 14 military installations | Grid copied through cleanup-site proxy IDs; analyst water, fiber, workforce, land |
| Maritime | Shared corpus near selected ports/shipyards | Grid plus logistics proximity; no demonstrated berth connection or supply-water assessment |
| Nickel | Shared corpus with land/port/rail filters | Grid plus selected-gage proxy and 16 supply-chain anchors; no fiber |
| Coal | Separate 18 curated assets | Curated switchyard/water/rail and valuation assumptions; proximity does not validate rights |
| Federal opportunities | Separate 10 curated sites | Narrative project evidence and reservation coordinates |
| DOE dossiers | Five reservations, including Hanford | More detailed narrative/land-unit evidence, not parcel-uniform infrastructure data |

All 14 Nuclear Siting grid values come from selected cleanup-site reference points,
not proposed development parcel boundaries. Measurements must disclose that basis.
Arnold's 25,000 'developable' acres and the cited 274-acre solicitation refer to
different land scopes; neither should silently replace the other.

Former military program membership is not current federal ownership or a reactor
authorization pathway. Yet micro scoring gives FUDS 85% licensing credit and
BRAC full credit. [USACE's FUDS description](https://www.usace.army.mil/Missions/Environmental/Formerly-Used-Defense-Sites/)
supports historical-use context, not that conclusion.

Also found `microRankedSites()` repopulates the whole corpus when active filters
produce an empty array. Fix it alongside category filtering; empty must stay empty.

## 5. Recommended delivery sequence

1. Repair demonstrated misinterpretations and preserve source types/IDs, coverage
   and dates. Add regression tests first. Refresh changed sources in staging and
   reconcile source counts, program IDs and retained fields before publication.
2. Replace totals and rank order with named category findings and High / Medium /
   Low confidence in each supported finding. Unknown is explicit. Consistent rules
   serve tabs, detail panels, filters and CSV exports. Keep exact measurements as
   evidence with geometry and uncertainty, not as a composite ranking.
3. Update Data/Info with this dataset inventory and clear limitations. Provide
   sources beside each category, explanation of confidence, and missing facts.
4. Add regional fiber and basin-aware water sources incrementally; incomplete
   coverage is explicit. Never turn an award, schematic route, nearby utility,
   monitoring gage or grid line into a service commitment.

Tests must cover typed annual mean versus low flow; unrelated citations; asset
roles; geographic coverage gaps; cache age; partial fetches; voltage pairing;
unknown fields; proxy coordinates; empty filters; late data joins; and absence of
0–100 ranks in tables, drawers, tooltips and exports. Verify mobile rendering,
keyboard navigation and existing first-paint DOM limits.

## Evidence limits and checks

Full existing unit suite: 743 passed. Focused infra/water/spatial/freshness set:
120 passed. Corpus validator: 27 pass, 12 warn, no failures. Live geometry sample:
119 of 128 checks agreed, nine skipped, across eight records per program. The
validator shares the production spatial algorithm and cannot independently
certify it. No new regression tests, production data changes or browser changes
have been made in this assessment phase.

This is a dataset and code-path audit plus targeted source checks. It does not
verify every curated claim, every infrastructure asset, or every candidate
parcel. The identified gaps are enough to reject precise overall rankings and
define a concrete repair and category-assessment implementation.


## Approach B implementation follow-through

The pre-change findings above are retained as the audit trail. The [implementation ledger and C assessment](../docs/specs/spec-infrastructure-scoring-audit-2026-09-12.md#implementation-ledger) records the completed repairs. [Grid rebuild validation](grid-rebuild-validation-2026-09-12.md) gives exact before/after coverage and independent live checks; [UX/UAT](ux-uat-2026-09-12.md) covers four viewport sizes and loading measurements.

- Physical-radius/antimeridian errors repaired; same-asset voltage, source snapshots and equipment roles retained.
- Core producer data and July EIA inventory refreshed. Coordinate-dependent evidence rebuilt or explicitly invalidated. Civilian nuclear and microreactor coordinate joins regenerated.
- USGS annual statistics retain their period and acquisition dates; unsupported supply/rights/fiber claims removed across the 14 curated installations.
- Categories replace numeric suitability totals. Missing evidence stays Unknown; mapped context does not become available capacity or transferable rights.
- All 36,782 feedstock matches now identify their own anchor and citation. A distinct nearest buyer cannot supply the feedstock citation.
- Corpus validation returns 27 pass, 12 warn, zero failures and two informational checks. Warnings preserve source disagreements, shared/low-precision coordinates, orphan joins and stale draft summaries; they are not silently corrected into confident findings.
- Citation liveness: 117 unique curated URLs checked, zero definitively dead, two blocked/throttled (BTS NTAD and NRC fuel-cycle page). A resolving link does not validate every claim on the page.
