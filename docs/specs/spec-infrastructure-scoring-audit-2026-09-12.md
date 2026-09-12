# Infrastructure and scoring assessment — 2026-09-12

Status: Approach B implemented and verified on `vibe/infrastructure-evidence-categories`. Approach C now has one deliberately small water/fiber pilot and one asset-specific grid verification; national expansion remains out of scope. The assessment below preserves the pre-change findings.

## Assessment

The data is useful for finding mapped infrastructure near a reported site
point. The current scores sometimes turn that evidence into stronger claims
about electrical access, isolation, water availability, and reusable capacity.
Those claims need correction before changing weights or refreshing everything.

This assessment includes current Git state, published-file coverage, connector
and scorer inspection, executable defect reproductions, existing tests, and
primary-source research. It is not a parcel survey or an engineering clearance.

## Git and existing work

- Fetched origin with pruning. Local main and origin/main both point to
  `6f7dbfa657b0cf26220e3942929e71a5e6f7aa98`; ahead/behind is 0/0.
- Initially no tracked edits, untracked files, or stashes in the main checkout.
- No open PRs. Latest merged PR #27 adds nickel scoring and streamgage water
  context; its unit, data-integrity, and e2e checks succeeded. PR #26 added
  maritime scoring. Reviewed recent PR inventory through #13 and open issues.
- Local `jam/brownfield-sites-research-tab-e0ad97` ends at `1fd2f79`, also
  checked out in the clean detached `.claude/worktrees/specs-research-code-review-fc9bf8`
  worktree. Its maritime work is represented by merged PR #26; its tree predates
  the nickel additions. Raw commit hashes differ after squash merging. Do not
  merge the old branch into current main to recover newer work.
- Ignored caches and refresh logs exist. Sampled flood-backfill and refresh-progress
  logs describe historical cached runs; they do not establish current source
  freshness. No credential values were inspected.
- Existing September 8 accuracy review and freshness spec contain useful leads,
  but their broad accuracy conclusions exceed the validator's independence.
- Open issues #28–35 already cover parcel backfill, waterbody distance, low-flow
  statistics, workforce, and nickel source gaps. Reuse those rather than duplicate.

## Current published coverage

Joined by ID over 46,759 producer records. Presence means non-null, not confirmed
capacity, access, accuracy, or freshness.

| Field | Records present | Percent |
|---|---:|---:|
| Transmission distance | 46,211 | 98.8% |
| Transmission voltage, including inferred classes | 46,211 | 98.8% |
| Substation distance | 46,328 | 99.1% |
| Substation voltage | 34,042 | 72.8% |
| Rail distance | 45,955 | 98.3% |
| Primary-road distance | 45,397 | 97.1% |
| Gas-pipeline distance | 44,977 | 96.2% |
| Power-plant distance | 46,496 | 99.4% |
| FEMA SFHA flag, including false | 42,572 | 91.0% |
| Nearby streamgage mean discharge | 45,946 | 98.3% |
| Producer acreage | 4,875 | 10.4% |
| Parcel acreage | 5,112 | 10.9% |
| Producer acreage or parcel fallback | 9,386 | 20.1% |

Producer files were generated May 12; infrastructure July 27; parcel and water
files September 9. These are processing timestamps. A cache rebuild can produce
a new timestamp while retaining old source data.

## Confirmed defects and material concerns

### P1 — Search radius does not fulfill the 100-mile contract

`connectors/spatial.py` defaults to eight 0.25-degree rings. Longitude spans fewer
miles at higher latitudes. At a query point (60, -150), a point at (60, -147.7)
is 79.453 miles away by haversine. Both PointIndex and a SegmentIndex containing
a short line at that longitude return None with default arguments. The infra
connector advertises 100 miles but uses those defaults.

This is an executable synthetic reproduction, not a measured count of affected
published rows. Rebuild and comparison are needed to quantify corpus impact.
It matters beyond missing distances: microreactor scoring interprets absent grid
distances as off-grid and awards maximum isolation credit.

### P1 — Voltage belongs to a different asset

`docs/dc-score.js:_effectiveGridAccess` substitutes a nearer substation when the
line is more than two miles farther away. If substation voltage is absent, it
retains the distant line's voltage. Reproduction: line 30 miles / 500 kV and
substation 0.2 miles / unknown becomes an effective 0.2 miles / 500 kV.

6,222 published rows trigger the distance substitution; 1,979 have unknown
substation voltage and a known line voltage. The helper serves DC, generation,
and manufacturing. Nearby assets need separate identities and measurements.
180 rows have a substation distance but no transmission distance; current public
entry points return no score before considering that evidence.

### P1 — Missing data can become positive evidence

Microreactor scoring treats a checked record with both grid distances absent as
confirmed isolation. A record alone does not prove complete upstream coverage
or a successful search of every layer. Nickel grants 40% voltage credit for
unknown voltage. Maritime grants partial land credit for unknown acreage and
full voltage-quality multiplier for unknown substation voltage. DC land instead
gets zero for unknown acreage. These conventions make scores inconsistent and
can hide evidence gaps.

The connector also suppresses sub-1 kV voltage while retaining its distance.
Scorers that discount known low voltage but do not discount unknown voltage can
therefore treat a known low-voltage feature more favorably after suppression.
Preserve observed values and classify suitability separately.

### P1 — Validation is not independent enough

`scripts/validate_against_sources.py:_measure` constructs the same SegmentIndex
used by the connector. It independently fetches source geometry, but it can
reproduce the same algorithmic bug. Its query is not paginated and does not
check `exceededTransferLimit`. Distances requiring boxes over 45 miles are
skipped. Null cases get a six-mile box, which cannot establish absence within
100 miles. The previous review's sampled agreement cannot certify the whole
dataset or these excluded cases.

### P2 — Asset classes become invented measurements

`VOLT_CLASS_TO_KV` maps `UNDER 100` to 69 and `DC` to 500. Neither category
establishes that exact voltage; 69 is not a lower bound for 'under 100'.
Separate observed numeric voltage, bounded class, and current type. An HVDC
corridor also does not establish a usable AC connection point.

### P2 — Proximity earns capacity and availability claims

Grid-inheritance scoring uses plant distance, nameplate MW, fuel, and retirement
year. Those establish neither parcel identity nor transferable rights or spare
capacity. The About tab currently says nearby plants imply inheritable
interconnection. Replace this with nearby-generation context; require explicit
evidence for any stronger reuse claim. A nearer substation than mapped line is
not itself an 'impossible' geographic condition.

### P2 — Water evidence answers a narrower question than the score

Nickel scoring multiplies distance to a streamgage by annual mean discharge.
That can rank a site near a gage across a watershed boundary while penalizing a
lakefront site far from gages. It measures nearby monitoring context. It does
not measure intake distance, low-flow reliability, withdrawal rights, or
process-specific water sufficiency. Keep those dimensions explicit and unknown
until hydrologically relevant data exists.

### P2 — Refresh can preserve stale evidence

Flood results are seeded by site ID and reused without querying; the code says
the FEMA answer for a fixed coordinate does not change between runs. Flood maps
can change, and site coordinates can also change. Preserve snapshot age and
coordinate identity, and invalidate deliberately. Partial/skipped-layer refresh
must preserve unrelated verified fields and must not advertise a full refresh.

### Coordinate quality limits all proximity claims

Current offline validator reports 118 points more than one mile outside their
reported state, 3,728 records in repeated-coordinate groups, and 190 low-precision
coordinates. Proximity calculations can be numerically consistent around the
wrong point. Surface these flags alongside scoring coverage; do not silently
correct coordinates from another unverified source.

## Scoring direction after user feedback

The user asked for separate categories and High / Medium / Low confidence,
questioning whether 85 meaningfully differs from 84. Agreed: these datasets
cannot justify that degree of comparative precision. Replace the composite
score and its hidden numeric ordering, rather than rebucketing it into labels.

Use Grid, Fiber, Water, Land and Logistics categories, with Demand, Feedstock
and Regulatory Pathway where relevant to the selected tab. Each category has:

- **Finding:** descriptive evidence or documented constraint; Unknown when the
  question cannot be assessed. Examples: 'Mapped substation nearby' or 'Water
  allocation not established'.
- **Evidence confidence:** High / Medium / Low, attached to the exact claim.
  High requires current, site-specific primary evidence of that claim; Medium
  can describe traceable mapped context with known limitations; Low describes
  weak proxies, unresolved conflicts or old evidence. No evidence renders
  Unknown, not an invented confidence classification.
- **Why:** source, source date, reference geometry, missing facts, and next
  verification needed. A precise distance can support mapped proximity while
  capacity remains Unknown.

Confidence is not suitability. A confirmed constraint can have High confidence.
Do not aggregate confidence grades into a replacement overall score. No overall
'High confidence site' label. Sort by name by default, with explicit category
filters and user-selected measured fields. Do not keep 0–100 sorting behind
category badges, in exports, or in detail drawers.

For example, a site with a mapped substation and no supply study would show:

| Category | Finding | Confidence in this finding | Unresolved |
|---|---|---|---|
| Grid proximity | Mapped substation nearby | Medium | Site connection, spare capacity, voltage if unreported |
| Grid capacity | Unknown | — | Utility study or documented service commitment |
| Fiber | Unknown | — | Serviceable parcel, carrier, capacity, diverse routes |
| Water | Regional streamflow context only | Low for site supply | Intake, basin match, low flow, allocated supply |

This is an illustrative design, not an assessed real site. Confidence definitions
are project governance rules, not statistical probabilities.

Methods considered: weighted composites with uncertainty can be transparent but
retain the comparison problem the user identified; constraint-first categorical
screens fit this task better; pairwise weighting or learned ranking adds complexity
without better evidence. Retain project-specific threshold filters only when the
project's demand and applicable evidence are known, with an Unknown group.

These are proposed design choices, not an externally validated universal siting
formula. Primary sources support separating evidence, constraints, and uncertainty:

- [OECD/JRC composite-indicator handbook](https://www.oecd.org/en/publications/handbook-on-constructing-composite-indicators-methodology-and-user-guide_9789264043466-en.html)
  addresses composite-indicator construction. Its [technical working paper](https://one.oecd.org/document/STD/DOC%282005%293/En/pdf)
  treats missing data, weighting, and robustness/sensitivity as explicit steps.
- [DOE National Transmission Needs Study](https://www.energy.gov/oe/national-transmission-needs-study)
  examines capacity constraints and congestion. A distance-to-line field cannot
  substitute for those assessments.
- [NRC brownfield siting considerations](https://www.nrc.gov/reactors/new-reactors/advanced/new-app/general-guidance/brownfield)
  describes potentially reusable infrastructure alongside site-specific technical
  investigations. Proximity alone cannot clear a nuclear site.
- [FERC generator interconnection](https://www.ferc.gov/electric-transmission/generator-interconnection)
  is the starting point for interconnection requirements; specific utility/RTO
  replacement procedures must be checked before asserting retained rights.
- [USGS StreamStats](https://pubs.usgs.gov/publication/fs20173046) distinguishes
  mean flow and low-flow statistics and supports estimates at selected stream
  locations. Basin-aware follow-up is preferable to treating nearest-gage mean
  discharge as local water supply.

## Implementation approaches for approval

| Approach | Scope | Tradeoff |
|---|---|---|
| A. Dataset repair first | Repair demonstrated bugs, provenance and source refresh; hide misleading totals until category model ships | Smaller first release; temporarily less comparison functionality |
| B. Category-first evidence assessment (recommended) | Dataset repair plus remove totals/ranks, add shared category findings/confidence, filters, exports and updated Data/Info explanations | Complete response to user's concern; roughly 20–35 source/test/doc files plus generated outputs, subject to detailed edit plan |
| C. Category assessment plus new nationwide layers | B plus waterbody/basin joins, low-flow expansion and regional fiber ingestion | Largest scope; regional source limitations and service rights still remain |

For B, implement in stages on a new `vibe/` branch from current main:

1. Add reproducing tests, then fix distance coverage and asset provenance.
2. Audit cache/source manifests, repair partial-refresh behavior, fetch changed
   layers with completeness checks, and rebuild affected overlays in staging.
   Diff IDs, coverage, distances, source dates, and changed assessments before
   replacing published files. Do not merely relabel cached data as fresh.
3. Replace numeric ranking with versioned category rules; expose missing evidence
   without rewarding it; remove unsupported inheritance/isolation claims. Review
   category changes across every affected tab and test confidence sensitivity to
   source quality, missing evidence, conflicts and aging.
4. Update Data/Info, evidence panels, tooltips, and scoring explanations from the
   same component definitions. Explain distance geometry, source vintage, inferred
   values, unassessed capacity, and project-specific constraints.
5. Test short ArcGIS pages with transfer-limit flags, empty/error responses,
   high-latitude and exact-radius searches, invalid numbers, partial refreshes,
   asset/voltage pairing, unknown components, delayed loaders, category consistency,
   empty filters and removal of numeric rankings from every output. Run full unit and applicable browser suites, corpus validation,
   writing checks, mobile rendering and first-paint DOM checks.

## Validation performed before implementation

- 120 focused infra/spatial/water/freshness tests passed.
- Offline corpus validation: 27 pass, 12 warn, 0 fail, 2 info.
- Synthetic radius and cross-asset voltage reproductions demonstrate gaps that
  those passing tests do not cover.
- Full unit suite: 743 passed, one existing urllib3/LibreSSL warning.
- Live source remeasurement: 119/128 OK, nine skipped over 32 sampled sites.
  This uses the existing validator and inherits its limitations described above.
- Live metadata check: four STALE, nine 'current', four UNKNOWN. Superfund source
  edit is September 12; FUDS September 4; redevelopment July 24. The EIA probe
  found June while the connector selects April; direct verification of the
  official publication page found July 2026, released August 26. The probe
  misses the current `/xls/` path by searching only `/archive/xls/`. These
  sources and the EIA discovery logic need updating.
  Transmission still reports September 2023 and plants/gas July 2025 data edits.
  'Current' means no newer edit reported by that endpoint, not current physical
  infrastructure or proven freshness of a historical cached response.
- The list above records pre-implementation checks. See the implementation ledger below for subsequent changes.
- Parallel dataset and tab findings are in
  [the grid, fiber and water assessment](../../research/infra-grid-fiber-water-audit-2026-09-12.md).

## Implementation ledger

| Workstream | Implementation | Verification / limit |
|---|---|---|
| Grid geometry and assets | Physical-radius search; agency/OSM IDs or explicitly local fingerprints; same-asset voltage; retain voltage class and equipment role | Synthetic radius/boundary tests, pagination checks, independent remeasurement; geometry does not prove capacity |
| Freshness | Live Superfund/FUDS/redevelopment promotion; July 2026 EIA workbook shared by generators; cached infrastructure replay | Stable core IDs; source dates separate from compilation dates; transmission/plant physical currency remains limited by source |
| Water | USGS record period and mean statistic; regional/failed states; cache-only replay; corrected Canadian state identities and Virgin Islands coverage | Retained gage means/IDs; no invented intake distance or low-flow statistic |
| Curated nuclear sites | Remove unsupported fiber/water-adequacy/rights labels; correct Robins annual mean and Arnold historical requirement | Sources, offered parcels, reactor assumptions and seismic context remain inspectable |
| Coordinate dependencies | 321 exact source-coordinate changes; 25 over one meter invalidate non-rebuilt geographic joins | Explicit dependency manifest; preserve core ownership/identity; late-load and failure browser regressions |
| Category rules | Versioned findings/confidence/why/sources; explicit Unknown; alphabetical default; no runtime numerical scorers | Independent categories, invalid values, date aging, same-asset voltage, empty-filter and CSV tests |
| UI | Explore first; five visible category findings; shorter guidance; category filters; consistent drawer/exports; source guide | Phone/tablet/desktop screenshots, keyboard/empty/error paths and source links |
| Loading | Core readiness separate from map-marker readiness; optional detail/catalog datasets deferred; initial Table DOM deferred; mobile legend/metrics collapsed | Compare first-insight readiness, decoded bytes, heap and retained DOM; local-server timing does not predict mobile network time |

High confidence is deliberately unused by the current infrastructure rules: the attached sources do not provide current, direct project-specific verification. Medium mapped context requires a known snapshot within 730 days and no flagged coordinate/proxy problem; older, retained, indirect or undated context is Low. This is an explicit governance threshold, not a probability or calibrated accuracy model. A missing observation stays Unknown.

## What changes for Approach C

B makes C safer to add, but does not remove its evidence requirements:

1. **Water: start with network-connected sources.** Add waterbody/flowline geometry and catchment/network identity before expanding low-flow statistics. A gage in the same administrative region or nearby basin is insufficient. Store the selected reach, connection method, reference period, statistic and exclusions. Compare reliable yield with the specific project's withdrawal and consumption assumptions. Keep allocation and intake feasibility separate.
2. **Fiber: use regional pilots.** No audited nationwide enterprise serviceability source was found. FCC availability, proposed grant routes, research networks and carrier presence answer different questions. Ingest one auditable regional route/service source with an explicit footprint and lifecycle first; leave other regions Unknown. Carrier confirmation is still needed for parcel service and route independence.
3. **Grid: prioritize equipment validation over more distance layers.** Preserve AC/DC, voltage classes, traction/distribution/transmission roles and lifecycle. Add utility/interconnection evidence only when it identifies the same asset and project. Nearby retired MW cannot become reusable capacity.
4. **Refresh dependencies before expanding coverage.** Coordinate versioning and per-layer manifests are now load-bearing. New joins need assessed coordinates, source snapshots, completeness status, partial-refresh preservation and invalidation tests. Plan migration from legacy USGS Water Services before its announced Q1 2027 retirement.
5. **Budget data by user action.** New nationwide layers should be precomputed and partitioned or loaded by relevant view/region. Do not place full geometry or repeated source metadata into every site's initial payload. Keep map markers deferred and share source/asset metadata by reference.

Recommended C sequence: basin-connected water pilot, regional fiber pilot, then utility-specific grid verification. Each should demonstrate a meaningful new finding on real sites before national expansion. Confidence should change only for the claim the new evidence supports.


## Final data and release checks

Core IDs remain 46,759: 1,908 Superfund, 36,003 ACRES, 8,821 FUDS and 27 BRAC records. The refreshed redevelopment source contained 49 zero-acreage sentinels; they now remain unknown, with producer regression tests preventing recurrence. Civilian nuclear distances and Janus fleet coordinates were rebuilt after dependent coordinates changed.

The final grid rebuild adds 26 transmission, 21 substation and 18 plant matches. Water has 45,937 qualifying gage matches, 641 completed searches without a qualifying gage and 181 unsupported locations. These counts describe catalog/search coverage, not serviceability. Nickel now carries per-type matched anchor IDs and shared provenance for all 36,782 feedstock observations.

Final review also repaired dropped FUDS/BRAC land citations, duplicate Nuclear CSV headers, category filter URL/export consistency, coal connection-rights claims and a map activation race that overwrote explicit parcel navigation. Regression tests cover each failure. High confidence remains unavailable pending direct verification evidence.

The offline corpus gate reports **27 pass, 12 warn, 0 fail, 2 info**. Remaining warnings include 19 orphan joins, state/county coordinate disagreements, 3,728 records sharing coordinates, low-precision or placeholder coordinates, 6,238 line/substation disagreements, redevelopment disagreements, 40 draft AI inconsistencies and seven opportunity-zone/county differences. These do not disappear because the artifact was rebuilt; the UI retains uncertainty and invalidates affected geographic fields.

The curated-link gate checked **117 unique URLs: zero definitively dead, two blocked/throttled** (BTS NTAD and NRC fuel-cycle facilities). Eight targeted live infrastructure checks passed. Neither check certifies every curated claim or nationwide completeness.

Four-width UAT shows initial requests **49 → 24**, DOM nodes **4,981 → 1,519**, decoded resources **77.54 → 68.91 MB** and approximate heap **286–304 → 167–199 MB**. Estimated gzip remains about **6.40 MB**, and seven visited views retain 13,815 DOM nodes. The remaining performance priority is partitioning large core data and releasing inactive view DOM; local timing is not field mobile performance.


The [16-record nickel source assessment](../../research/nickel-catalog-source-audit-2026-09-12.md) found an unrelated Ford citation, the Kentucky plant's LFP conversion, Talon's September 10 Humboldt/Beulah decision and mixed chemistry at Spring Hill. Corrected source/status fields and exclusions change 3,036 demand distances and 2,030 overall nearest-anchor names. This adds a requirement for C: lifecycle, chemistry and verified role must gate demand matches before any new proximity layer can affect an assessment. A resolving citation alone is insufficient.


### Completed verification

- `python3 -m pytest tests/ --ignore=tests/e2e -q`: **828 passed**; one existing urllib3/LibreSSL environment warning.
- `python3 -m pytest tests/e2e -q -n 2`: **261 passed** in 443.29 seconds on the final implementation. Earlier failures were reproduced and corrected; no tests were skipped to obtain this result.
- Corpus: **27 pass, 12 warn, 0 fail, 2 info**. Writing: **0 banned, 17 advisory findings**. JavaScript syntax and `git diff --check` pass.
- Four-width visual UAT, forced loader failures/delays, category exports, coordinate invalidation and deep links verified. The final browser suite includes the corrected empty/loading distinction and map-target races.
- Final `git fetch origin --prune` confirms upstream main still `6f7dbfa657b0cf26220e3942929e71a5e6f7aa98`; open PR inventory remains empty. Work stays on the local implementation branch; no remote publication performed.

Approach B is complete. Approach C's first gated pilots are implemented:

- `ACRES-245389` carries an official USGS NLDI reach (`10294630`) and WBD HUC12 (`010802030402`, Lower Green River). This changes the water finding from nearest-gage context to network identity, while low flow, intake, demand and rights remain Unknown.
- The same Franklin County record carries MassBroadband 123 operating regional-network context. It does not claim a route reaches the parcel, enterprise service, capacity or diverse paths.
- Portsmouth's DOE dossier now identifies X-530, the X-515 330 kV tie-line and Don Marquis Substation from the DOE operating contract. The UI labels asset scope and leaves spare capacity, new-parcel service and rights unresolved.

These are pilots, not national coverage. Expansion requires reproducible source snapshots, explicit footprints and evidence that the new layer changes a real finding without changing unrelated confidence.

Implementation commit: `b90e724` (82 source, data, UI and test files). The companion documentation commit records the assessment, source audits, UAT and remaining C work.
