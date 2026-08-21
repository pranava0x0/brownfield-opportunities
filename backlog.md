# Backlog

Ideas and enhancements. Priorities: **high** = next, **med** = soon, **low** = nice-to-have.

---

## NEPA MCP integration — implemented core (2026-08-21)

Researched PNNL's [`nepa-mcp`](https://pypi.org/project/nepa-mcp/) 0.1.1 (PermitAI
toolkit; 19 servers / 46 tools / 32 GIS layers, BSD-3). Full analysis, capability map
and six scenarios in **[nepa-mcp-integration-spec.md](nepa-mcp-integration-spec.md)**;
host/packaging findings in `data-source-research.md` §32.

- ~~**[high] Tier A — install as an agent-time MCP server.**~~ **Done 2026-08-21.**
  Exact `nepa-mcp==0.1.1` isolated with `uv`; nine narrow Codex servers configured.
  Janus build adds six source screens and 12 map layers for nine installations.
- **[high] Tier B1 — `census-workforce` connector.** **Code and tests done; data blocked.** ACS 5-Year county socioeconomics
  to replace the hand-typed workforce rating that carries **15/100** of the Nuclear
  Siting score and that CLAUDE.md admits has "no federal GIS layer". ~3,232 counties,
  joins via the `CountyIndex` we already resolve offline. Build it against the Census
  API directly, NOT through `nepa-mcp`. Needs `CENSUS_API_KEY`; do not ship an empty file.
- ~~**[med] Tier B2 — tribal-area containment.**~~ **Done 2026-08-21.** Six TIGERweb
  AIANNHA layers, 1,071 polygons, 46,759 sites, 2,122 mapped point-context hits.
- **[med] S2 — automate the regulatory re-audit.** `cfr_compare_versions` / `cfr_history`
  diff a CFR citation between two dates, which is exactly the "has this moved since
  `verified_at`?" question `STATE_DC_REGULATION` (quarterly) and EO 14318 need. **Only
  works for federal instruments — state tax law is not in the CFR**, so
  `STATE_DC_INCENTIVES` still needs the manual 51-row sweep.
- **[low] Tier B3 — PAD-US protected areas.** National connector deferred after size/
  reliability probe. Janus uses bounded 0.1-mile point context; one explicit timeout.
- **[high] Reuse dossier.** One site view for land/control, reusable infrastructure,
  environmental baseline, prior studies/permits, workforce/community, and delivery path.
  Use known/no-hit/unavailable/project-work states. See
  `research/nepatec-reindustrialization.md`.
- **[med] NEPATEC analogue finder.** Search comparable brownfield/retired-plant actions by
  agency, review level, issue, mitigation, and outcome with page-level citations.
- **[med] Permit/evidence graph.** Dependencies, owner, status, source, dates, and gaps;
  connect PermitTEC litigation to challenged procedural nodes.
- **Refused, with reasons in the spec:** per-site ESA/wetlands/NRHP/air-quality over the
  full corpus (~19 h per layer — the flood-backfill trap), re-deriving FEMA flood data we
  already have at 91.1%, `map_composer` as a product surface, and adding `nepa-mcp` to
  `requirements.txt` (Python 3.12 floor vs our 3.9).

---

## Microreactor siting tab — follow-ups (2026-08-21)

Shipped: `docs/data/microreactor-fleet.json` (12 vendors / 32 commitments / 8-sector
demand ladder), `docs/microreactor-score.js` (the inverted-grid lens), and the
Microreactors tab. Open items that were scoped out deliberately:

- **[med] The demand ladder is a reference table, not a join.** The 55 load classes
  (Compute 1–10 MW, cement 7–25 MW, remote mines 5–20 MW, …) describe who buys a
  1–20 MWe block, but nothing connects them to a site. The natural join is
  `retired-industrial.json`, which already labels 658 facilities by NAICS sector —
  a retired cement plant sits in a known load band. It would turn "this site is
  isolated and federal" into "this site is isolated, federal, and there is a
  7–25 MW cement load next door." Blocked on nothing but scope.
- **[med] `anchor_load` uses the nearest power plant as a load proxy.** It is the
  best universal signal on disk, but it is a proxy: it detects generation, not
  demand. A real load layer (EIA-861 utility sales by county, or the Census County
  Business Patterns employment-by-NAICS table) would replace the proxy with a
  measurement. Both are public and bulk-downloadable.
- **[low] Vendor-to-site matching is not implemented.** The tab shows the fleet and
  the ranking side by side but does not say which designs fit a given site. The one
  defensible criterion available today is the published no-grid-required claim
  (Antares R1; BWXT's expeditionary Pele) against `microreactorIsOffGrid()` —
  every other spec that would drive a match (exclusion-zone footprint, security
  perimeter, water) is unpublished for 11 of the 12 vendors. Worth doing only as
  the narrow off-grid filter, not as a general fit score.
- **[low] Fleet and commitment rows carry no `verified_at`.** They are curated and
  will rot — ANPI, Janus and the pilot programme all move monthly. `STATE_DC_INCENTIVES`
  solved this with a per-row `verified_at` and a documented re-audit cadence; this
  file should do the same. Suggested cadence: quarterly, matching `STATE_DC_REGULATION`.
- **[low] Land-area, shell/enclosure and utility-filing coverage is 1/14, 1/14 and
  4/14 in the source project** and web search cannot fix it — those live in FERC
  eLibrary, state PUC dockets and NRC ADAMS. Only Westinghouse publishes a footprint
  (2 acres), which is why `MICRO_MIN_ACRES` is a judgement call rather than a
  derived figure.

---

## DOE national-lab research pass — 2026-08-09

Read the current national-lab literature on brownfield reuse and large-load
siting; findings and full citations in
[research/doe-lab-brownfield-reuse.md](research/doe-lab-brownfield-reuse.md), sources reproducible via
`bash research/sources/fetch.sh` (checksummed, PDFs gitignored).

**The headline finding is about this project.** NREL's *Data Centers Gap
Analysis* (Feb 2026) tabulates open data gaps for large-load integration and
lists, verbatim: lever "Brownfield conversion projects", data needed
"**Database of eligible brownfield conversion sites**", gap "Yes". That is
what this dashboard is. The corpus is not the gap — **our screening criteria
are homegrown while the labs have published, defensible ones**, and closing
that is the highest-value work available.

### Tier 1 — public data, pure-Python computable, big payoff

- **[high] Adopt ORNL's OR-SAGE criteria corpus-wide.** Appendix A of the
  INL/ANL/ORNL coal-to-nuclear study gives ten thresholded, GIS-computable
  siting rules — population density >500/sq mi (4-mi buffer), seismic PGA
  >0.5 g, fault standoff, landslide susceptibility, slope >18%, wetlands/open
  water, 100-yr floodplain, cooling water ≥135,000 gpm within 20 mi, protected
  lands, hazardous-facility proximity. **We already satisfy exactly one**
  (floodplain, via FEMA NFHL). Each remaining one is a single public layer
  plus the `PolygonIndex` / `SegmentIndex` we already have. Cheapest four
  first: slope (USGS 3DEP), protected lands (USGS PAD-US), wetlands (FWS NWI —
  liveness already probed in `data-source-research.md`), population density
  (Census). Adopt their framing too: parameters are *flags to inform*, not
  rules to rule a site in or out — the same posture as `coord_flags`.
- **[high] Ingest EPA RE-Powering's 190,000-site screening dataset.** We
  consume only the 1,905-record `RedevelopmentAppSitePoints` layer; EPA also
  publishes a screened dataset of 190k+ sites (XLSX ~78 MB + geodatabase) with
  acreage, renewable-energy capacity and **distance to nearest substation**.
  A ~100x coverage increase from a source we already trust, and its substation
  distances are an independent cross-check on `substation_mi` — precisely the
  external validation the 2026-08-09 audit found we lack.
- **[high] Population density.** OR-SAGE's most discriminating parameter and we
  carry none. Does triple duty: nuclear exclusion screening, NREL's
  "proximity to end users" latency proxy, and a community-opposition risk
  signal alongside `STATE_DC_REGULATION`.

### Tier 2

- **[med] Cite the labs inside the scoring UI.** The `grid_reuse` /
  `grid_inheritance` credit rests on INL's finding that reusing coal
  infrastructure cuts nuclear overnight capital cost **15–35%** (reusable:
  switchyard and transmission, office buildings, heat sink, steam cycle,
  roads, water rights). The flood penalty matches an OR-SAGE exclusion. Extend
  `FIELD_PROVENANCE` so scoring *components* cite a methodological basis, not
  just data fields — turns the rubric from assertion into argument.
- **[med] Site-level cooling-water demand estimate.** LBNL models WUE per
  cooling-system type against TMY climate data; we already carry
  `climate_zone` and an NRI drought rating per site. Water is also the gap
  INL's Oct 2025 workshop named explicitly.
- **[med] Join LBNL's county-level water-consumption and GHG intensity by
  balancing authority.** Published, county-level, joins to what we have.
- **[med] A flexibility lens.** LBNL: **76 GW of new load could interconnect
  today if it can curtail 0.25% of maximum uptime.** Our model scores every
  megawatt as if it must be firm. At minimum say so in the Rankings explainer.

### Tier 3 — blocked or expensive

- **[low] Interconnection queue position** (LBNL *Queued Up*). Highest buyer
  value — speed to power is *the* criterion — but per-ISO and messy.
- **[low] Noise constraints.** Named by INL as an open gap, now appearing in
  state law (VA HB153/SB94). No national dataset; likely a per-state
  regulatory field like `STATE_DC_REGULATION`, not a GIS layer.
- **[low] Latency proxy.** Still no public national fiber backbone dataset.
  But NREL derives latency from network infrastructure *and* proximity to end
  users — the second half is computable from Census population centers. A
  partial proxy beats the current nothing.

## Session checkpoint — 2026-08-18 (scheduled data-maintenance run)

**No data gap to close; landed the CI fault-isolation fix instead.** Coverage
re-asserted and identical to 2026-08-11 in every dataset — flood 42,576/46,759
(**91.1%**, 4,422 SFHA), `parcel-owner` 11,463 (12 uncovered, the known
permanent FL HTTP-400s), `epa-superfund-docs` 1,888/1,908 (**99.0%**),
`epa-echo` 1,906, `ai-summary` 1,908. `scripts/validate_data.py`: **23 pass ·
12 warn · 0 fail**, every warn in the documented upstream set, nothing new.

### The one thing that changed: a 13th CI failure, and a third trigger

The scheduled refresh failed again on **2026-08-17** — now **13/13 since
2026-05-25**. The new log carries a trigger distinct from both previously
recorded ones: `ConnectionError: Connection reset by peer` from ArcGIS at
`infra_proximity.py:660` `_build_index`. Three different hosts, three different
exceptions, one identical outcome — which is what finally settles that this is
the orchestration and not a flaky endpoint.

**The recorded diagnosis was slightly wrong, and the real defect is smaller.**
The 2026-08-11 entry said "`_run_one()` already returns a per-connector rc;
honour it and continue" — but the `--all` loop *was* already honouring it
(`rc = sub_rc or rc`, then carry on). The actual defect: `_run_one` **raises**
rather than returning nonzero, so the exception sailed straight past the loop
and out of `main()`, taking every connector still queued behind it. With
`--no-cache` in CI that discards a 30–50 minute run at whichever connector drew
the short straw.

Because the fix turned out to be ~8 lines in one function, it cleared this
routine's "explicitly small and self-contained" bar and was done here rather
than deferred: `refresh.py` now wraps the `_run_one` call in `--all`, logging
the full traceback via `log.exception` and keeping the run's exit code nonzero.
Fail-loud is preserved on purpose — isolation buys the remaining connectors
their turn, it does not turn a broken run green. Scoped to `--all`; `--source X`
still propagates, which is what the by-hand maintenance runs rely on. 8
regression tests, **verified red without the fix** (5 fail, 3 controls stay
green). Full suite 566 pass.

### Necessary but not sufficient — read this before assuming CI is fixed

The refresh step still exits nonzero, so GitHub Actions skips the downstream
commit step and **the cron still publishes nothing**. What the fix buys today is
diagnostic: one run now surfaces *every* failing connector instead of one per
week of whack-a-mole. Restoring auto-commit needs a `continue-on-error`
restructure of `refresh.yml`, and that was deliberately left supervised —

- **[high] Guard the empty-payload write before re-enabling auto-commit.**
  `_run_one` aborts on an empty record set only for `CANONICAL_SLUG`; every
  other producer gets `log.warning` and an **empty payload written over the live
  file**. Harmless today only because the commit step never runs. Re-enable
  committing without fixing this and a source outage that returns HTTP 200 with
  zero features blanks the dataset: **46,756 records exposed** — `epa-acres`
  36,003, `dod-fuds` 8,821, `epa-redev` 1,905, `dod-brac` 27. A producer
  returning zero rows is an outage, not a legitimate state; it should refuse the
  write the way the canonical file already does.
- **[high] Then restructure `refresh.yml`** so a partially-successful run still
  commits what it refreshed: `id` + `continue-on-error: true` on the Refresh
  step, commit, then a final step that fails the job if refresh failed. Order
  matters — the guard above lands first.
- **[med] Chunk + back off the Overpass substation queries** (carried forward).
  A 504 on a 12°×25° bbox is the expected response from a free endpoint under
  load, not an anomaly worth aborting on.

### Carried forward unchanged

- **[low] 38 static summaries omit acreage for sub-1-acre sites** (0.1–0.9 ac).
  Formatter behaviour in `build_static_summary()`, not staleness — a regen
  reproduces it byte-for-byte. Still code+tests, still supervised.
- Producer files remain **2026-05-12** (three months old). Unchanged guardrail:
  do not run producer refreshes unattended.

## Session checkpoint — 2026-08-11 (scheduled data-maintenance run)

**Verified, found nothing to backfill, stopped.** The 2026-08-04/05 entry's
closing instruction ("no data-only gap of any size remains — verify coverage,
then stop rather than manufacture work") held on re-test. **No data commit
this run; that is the correct outcome, not a failed one.**

Coverage re-asserted, all matching the recorded state exactly:

| dataset | state |
|---|---|
| flood (`infra-proximity`) | 42,576/46,759 = **91.1%**, 4,422 SFHA — complete |
| `parcel-owner` | 11,463 records; **12 uncovered, all FL** — the known permanent HTTP-400 cadastral failures |
| `epa-superfund-docs` | 1,888/1,908 = **99.0%**; residual 20 are the documented source-side dead ends |
| `epa-echo` | 1,906/1,908 (last 2 return no ECHO match) |
| `ai-summary` | 1,908 |

**Corpus health — [`scripts/validate_data.py`](scripts/validate_data.py): 23 pass · 12 warn · 0 fail.**
Every warn is in the known upstream-quality set; nothing new appeared since
2026-08-09.

**`ai-summary` is not stale — proven, not assumed.** Because its four input
files were repaired in place on 2026-08-09 without a `generated_at` bump,
staleness can't be read off the envelope. Ran the full static regen (1,908
records, <1 s, offline) and diffed the `summary` **text** field: **0 changed,
0 added, 0 removed.** Pure timestamp-only rewrite, so it was reverted per the
2026-07-28 rule. Worth keeping: the regen-and-diff is the only reliable
staleness test for this file, and it costs a second.

### The real finding — CI has been dead for 11 weeks

**The scheduled "Refresh site data" workflow has failed 12/12 runs since
2026-05-25.** Logged in [`issues.md`](issues.md). It was invisible to this routine because
every prior run checked *data coverage* and never *CI health* — and coverage
looked fine precisely because these agent sessions were doing the refresh work
by hand.

- **[high] Give `refresh.py --all` per-connector fault isolation.** One
  unhandled transient network error kills the whole chain. Two distinct
  triggers confirmed, so this is structural, not a flaky host: Overpass **504**
  at `infra_proximity.py:792` (`raise_for_status()` with no transient
  tolerance — while `FLOOD_TRANSIENT_HTTP_CODES` sits unused at line 251 of the
  same file), and an `echodata.epa.gov` **ReadTimeout** at `epa_echo.py:360`.
  `_run_one()` already returns a per-connector rc; honour it and continue.
- **[high] Add CI health to this routine's §0 orientation.** `gh run list`
  is one call and would have caught this 11 weeks ago. Checking that the data
  *files* look right is not the same as checking that the pipeline *runs*.
- **[med] Chunk + back off the Overpass substation queries.** A 504 on a
  12°×25° bbox is the expected response from a free endpoint under load, not
  an anomaly worth aborting on.

### One new data finding

- **[low] 38 static summaries omit acreage for sub-1-acre sites.** Surfaced by
  the validator's `ai-summary-consistency` check. All 38 have real acreage in
  the 0.1–0.9 range (e.g. Amco Chemical 0.9 ac, Curcio Scrap Metal 0.9 ac),
  but the lead sentence renders as "… is an EPA Superfund (NPL) in Oakland,
  CA" with the acreage clause dropped entirely. This is a **formatter
  behaviour in `build_static_summary()`, not staleness** — a regen reproduces
  it byte-for-byte. Fix is code + tests in `connectors/ai_summary.py`
  (render "a 0.9-acre" rather than suppressing), so it is left for a
  supervised session per this routine's scope guardrails.

### Blocking decision, now overdue — force-push or abandon

The 2026-08-09 `[decision pending]` on the `Co-Authored-By` history rewrite is
**still unmade, and it now blocks publishing.** Re-verified this run:

- `git merge-base main origin/main` is **empty** — the rewrite went to the
  root, so the two histories share no ancestor. This is why `main` reads
  "ahead 213, behind 203"; it is rewrite noise, not divergent work.
- `git diff origin/main e7c2638` is **empty** — `origin/main`'s tree is
  byte-identical to a local commit. Local `main` therefore **strictly
  contains** everything published, plus 10 commits of real unmerged work
  (the validation, provenance, coord-quality and DOE-research session).
- `backup-pre-coauthor-strip` is intact at `56d4570` (= `origin/main`), so the
  abandon path is still fully open.

**A scheduled run will not force-push**: rewriting 203 commits of published
history is outward-facing and irreversible, and it is an explicitly parked
decision. Consequence: **the last two sessions' work is committed locally but
unpublished**, so GitHub Pages is serving the 2026-08-05 state.

- Publish: `git push --force-with-lease origin main` (content-safe — purely
  additive; nothing on origin is lost).
- Abandon: `git reset --hard backup-pre-coauthor-strip`, then cherry-pick the
  10 commits `e7c2638..main` (`23c84d0 e5cfc8e c2f0634 f0910ee cd1f46b
  8945587 a0a8b87 d486efb 5a92288 827c0d3`, plus this checkpoint).

## Session checkpoint — 2026-08-09 (comprehensive data validation + branch cleanup)

Built two runnable validators and pointed them at the whole corpus. **The
infrastructure distances and the spatial index came out clean; the
coordinates did not.**

**New tooling (both re-runnable, both token-cheap to read):**
- [`scripts/validate_data.py`](scripts/validate_data.py) — 33 offline checks over all 24 data files
  in ~5 s. Families: `struct` (envelope, Pydantic schema, id uniqueness and
  namespace, enrichment→universe join, value domains, numeric ranges, dates,
  URLs), `geo` (coordinate range/region/placeholder, point-in-state,
  point-in-county, duplicate and low-precision coordinates, sentinel strings),
  `infra` (Lipschitz, co-located agreement, substation-vs-line, tombstones,
  exact recompute of the three joins whose source geometry we hold locally),
  `derived` (DC-candidate re-derivation, cross-layer coordinate/acreage
  agreement, AI-summary consistency, OZ/IRA rollups, freshness). One line per
  check; `--json` for the offending ids. `--only <family|check>` to scope.
- [`scripts/validate_against_sources.py`](scripts/validate_against_sources.py) — sampled ground truth against the
  live services. Re-queries each site's owning FeatureServer and, crucially,
  **independently re-measures the infra distances** by pulling the source
  layer's features inside a box around the site and computing the minimum
  locally — never touching our own index. IPv4-pinned (see the 2026-08-04/05
  IPv6 entry below), disk-cached, 1.5 s rate limit.
- [`tests/test_spatial_fuzz.py`](tests/test_spatial_fuzz.py) — 11 tests fuzzing `SegmentIndex` /
  `PointIndex` / `PolygonIndex` against brute force across four latitude
  bands. This is the guard the project never had on its most load-bearing
  correctness dependency.

**What is verified healthy — worth knowing so nobody re-audits it:**
- The spatial index is *correct*. Nearest-segment and nearest-point search
  match an exhaustive scan exactly at 25°N through 64°N; the Chebyshev
  ring-expansion early exit is a sound bound.
- `infra-lipschitz` passes across **511,927 near-pairs**: for every pair of
  sites within 2 mi, `|d(A) − d(B)| ≤ dist(A,B)` holds for all six distance
  fields. Nearest-feature distance is 1-Lipschitz in position, so this is a
  proof (not a heuristic) that no distance is internally inconsistent.
- Live re-measurement reproduced the stored distances on the sample
  (transmission / highway / rail / gas), and the `planned-retirements`,
  `nuclear-brownfield-proximity` and `retired-industrial` joins recompute
  **exactly** from their local source geometry.
- Schema conformance is 100% across 351,803 records; `sites.json` is a
  byte-exact mirror of `superfund-npl.json`; no file is stale or future-dated.
- **Ground truth against the live services (117-site sample, 30 per program):
  90/90 attribute round-trips clean** — every sampled Superfund / ACRES / FUDS
  record's name, state, coordinates and acreage still match what the owning
  FeatureServer returns today. **455/455 independently re-measured infra
  distances matched**, zero mismatches; median deviation 0.020 mi, max
  0.050 mi — i.e. every one agreed to within the 0.1 mi rounding granularity
  the connector emits at. 13 were skipped because the stored distance was
  large enough to need an impractically big query box (mostly `highway_mi`
  in remote AL/MS/CO). A follow-up run added the BRAC branch and covered all
  27 BRAC records: **108/108 attribute round-trips clean across all four
  programs.** (Writing that branch surfaced a doc drift — CLAUDE.md documents
  the BRAC namespace as `BRAC-<slugified SITE_NAME>`, but
  `dod_brac.normalize()` actually keys on `OBJECTID`, e.g. `BRAC-619`.)

**What is broken** — seven entries logged in [`issues.md`](issues.md) dated 2026-08-09.
Headline: a duplicate FUDS record, 50 Superfund `acreage: 0.0` where null is
meant, and **118 sites whose coordinates fall more than a mile outside their
own claimed state** (13 of them >25 mi, two outside the US entirely).

### Follow-ups

- ~~**Chain of evidence for every claim.**~~ **DONE 2026-08-09** —
  [`docs/provenance.js`](docs/provenance.js) is a field-level registry: publisher, dataset, layer,
  how the value was derived, the as-of date of ITS source file, and a
  verification URL that resolves to *this site* wherever the upstream service
  allows it. Rendered as a "Sources & evidence" section in the detail panel,
  built lazily on first expand (a full table is ~150 nodes against a
  5,000-node first-paint budget). `validate_against_sources.py --only
  evidence` exercises every link: 160/160 resolve, and each bbox link is
  sized from the site's own stored distance so it always contains the feature
  it evidences — **488/488 links verified across a 48-site sample**. Guards:
  [`tests/e2e/test_evidence_panel.py`](tests/e2e/test_evidence_panel.py) (10) + [`tests/test_provenance_registry.py`](tests/test_provenance_registry.py) (6),
  the latter failing CI if a field is rendered without a citation or a
  registry key stops matching the schema.

- **[decision pending] Local history rewrite is staged but NOT published.**
  All 203 commits were rewritten to strip `Co-Authored-By:` trailers (99
  Claude, 8 self). Verified before parking it: the tip tree is byte-identical
  to the pre-rewrite tree (`git diff 56d4570 main` is empty), the commit count
  is unchanged at 203, and `git log main --grep=co-authored -i` returns
  nothing. Local `main` therefore reads as "ahead 204, behind 203" against
  `origin/main` — that is rewrite noise, not divergent work, the same shape
  as the 2026-07-09 rewrite already described in CLAUDE.md.
  - To publish: `git push --force-with-lease origin main`.
  - To abandon: `git reset --hard backup-pre-coauthor-strip` (that tag points
    at the original tip `56d4570`), then cherry-pick the validation commit.
  - Whichever way it goes, **decide before the next data refresh** — a new
    commit on top of the rewritten history makes the revert path messier.
  - Also worth doing either way: drop the `Co-Authored-By` line from the
    commit-message convention so the trailers stop accumulating.
- ~~**[high] Assert id uniqueness in `refresh.py` before write.**~~ **DONE
  2026-08-09** — `assert_unique_ids()` runs before every per-connector write
  and the combined write; `dod_fuds` also dedupes at source.
- ~~**[high] Coerce non-positive computed acreage to `None`.**~~ **DONE
  2026-08-09** — in `superfund_npl.normalize()`; shipped data repaired too.
- ~~**[high] Add a geometry-vs-state guard to the connectors.**~~ **DONE
  2026-08-09** — `connectors/coord_quality.py` (slug `coord-quality`,
  `run_order = 150`) runs offline against the shipped `us-states.json` and
  emits `coord_flags` for the 3,991 affected records. Its counts match the
  validator's independent implementation exactly (118 / 17 / 2 / 190 /
  3,728), which is a useful cross-check of both. Surfaced in the detail
  panel as a location-confidence note.
- ~~**[med] Wire `scripts/validate_data.py` into CI.**~~ **DONE 2026-08-09** —
  new `data-integrity` job, `--fail-on FAIL`. Checks split into invariants we
  own (gate the build) and upstream data quality (report as WARN); the split
  lives in `UPSTREAM_QUALITY_CHECKS`. Corpus is currently 22 pass / 13 warn /
  0 fail.
- ~~**[med] Promote the IPv4 pin into `connectors/base.py`.**~~ **DONE
  2026-08-09** — `connectors.base.prefer_ipv4()`, called from `refresh.main()`
  before any socket opens, opt-out via `--allow-ipv6`. Idempotent. Every
  connector now gets the fix for free.
- **[med] 20 Superfund sites exist in EPA RE-Powering but not in the
  boundaries layer** — verified against the live service, so this is an
  upstream coverage gap, not a connector bug. Several are Final NPL
  (Norfolk Naval Shipyard, Puget Sound Naval Shipyard, Wright-Patterson AFB,
  Gelman Sciences, Upper Columbia River). `epa-redev` ships name / state /
  coords / status for all 20 — it could *emit* them as records rather than
  being enrichment-only, growing the Superfund set ~1%.
- ~~**[med] Collapse source sentinels connector-side.**~~ **DONE 2026-08-09**
  — `connectors/text.py:collapse_sentinel()`, wired into the three
  place-bearing connectors; 1,162 values repaired on disk. Turned out to be
  user-visible, not just tidiness: `NO CITY` and `Unknown` were missing from
  the frontend's `PLACE_SENTINELS`, so the detail panel showed "No City".
- **[med] Relax the scoring gate when a substation is in reach but no line
  is.** All three lenses return `null` when `transmission_mi == null`, on the
  reasoning that a site with no grid in the 100-mi window can't be assessed.
  But 180 sites have `transmission_mi == null` AND a substation within
  reach — one at 1.1 mi — which disproves the premise for exactly those
  records. `_effectiveGridAccess()` already handles the case correctly; only
  the gate needs to move. Small blast radius (0.4% of the corpus) but it
  makes previously-unscored sites appear in rankings, so it is a product
  decision, not a pure bug fix.
- ~~**[med] `transmission_mi` over-states grid distance for ~13% of sites.**~~
  **DONE 2026-08-09** — `dc-score.js:_effectiveGridAccess()` substitutes the
  substation as the interconnect point (distance AND voltage) when the line
  is more than `GRID_COVERAGE_GAP_MI` (2 mi) further away, i.e. only where
  there is positive evidence the line layer is incomplete. Measured impact:
  **5,922 of 46,211 scored sites (12.8%) gain a mean +9.2 points, max +27**,
  on all three lenses. 8 new e2e tests. Original finding kept below for
  context.
  <details><summary>original</summary> 6,222 records have a substation closer than the nearest HIFLD
  transmission line by more than 2 mi (median gap 4.2 mi; 1,210 over 10 mi;
  368 over 25 mi), spread across states — MI 941, CA 524, FL 406, AZ 285,
  ME 280 — so it isn't just the known HI/PR/AK coverage holes. A substation
  is by definition connected to the network, so these are lines HIFLD's
  public layer doesn't carry (mostly sub-transmission: 69/46/34.5 kV).
  Transmission distance is worth 16 points on the DC lens and 18 on
  generation, so this quietly deflates the score of one site in eight.
  Options: treat `min(transmission_mi, substation_mi)` as the effective
  interconnect distance, or credit the substation path directly when the gap
  is large. Detected by `infra-substation-vs-line`.</details>
- **[low] 3,728 sites share a coordinate with at least two others**, the
  largest cluster being 97 ACRES sites on one point. Almost certainly
  geocoder centroid fallback. Not wrong exactly, but a "precision unknown"
  flag would stop the detail panel implying survey accuracy.
- **[low] Re-measure infra distances at larger sample sizes periodically.**
  The sampler is cached and resumable; a few hundred sites per run would
  build a coverage record over time.

## Session checkpoint — 2026-08-04/05 (scheduled data-maintenance run)

**Headline: the "EPA is slow" finding from 2026-07-28 was a misdiagnosis — it's broken IPv6 on this machine, and it has been taxing every connector for months.** Fixing it at runtime took the docs backfill from a projected **6.6 hours to 21 minutes** and closed the gap that had been carried for two sessions. Two commits (`1e9b576`, `21bcab4`), both schema-validated; 449 unit tests green.

- **`epa-superfund-docs`: 1,781 → 1,888 (+107 sites, +603 documents), 99.0% coverage** (`1e9b576`). This was the only remaining record-level gap in the whole dataset.
- **`ai-summary`: full static regen, 94 summaries changed** (`21bcab4`). All 94 gained the federal-documents clause they previously had no data for (85 plural + 9 singular); zero lost one. Sites citing documents 1,464 → 1,549. Ran last, without `--missing-only`, per the playbook.

### Root cause: IPv6 blackhole + urllib3's serial address walk

Every EPA host (`www.epa.gov`, `cumulis.epa.gov`, `semspub.epa.gov`) resolves **AAAA-first**. This machine's IPv6 path is blackholed — a SYN to any IPv6 address times out silently (verified: 10 s hard timeout, no RST; the IPv4 address for the same host connects in 0.01 s). `requests`/urllib3 walks `getaddrinfo()` results **serially, spending the full 60 s socket timeout on the IPv6 address** before falling back to IPv4. `curl` is unaffected because it implements Happy Eyeballs (RFC 8305).

Measured on the identical URL, same User-Agent, no proxy: **`curl` 0.59 s vs `requests` 60.3 s**, both HTTP 200.

**This is not EPA-specific.** Of the hosts this project uses, these are all AAAA-first and therefore paying ~60 s per uncached request: `www.epa.gov`, `cumulis.epa.gov`, `semspub.epa.gov`, `data.epa.gov`, `echodata.epa.gov`, `services{,1,2}.arcgis.com`, `tigerweb.geo.census.gov`, `overpass-api.de`. Only `hazards.fema.gov` and `gis.fdot.gov` are A-first — **which is exactly why the FEMA flood backfill always ran at normal speed while the EPA connectors crawled.** That asymmetry is the tell, and it was hiding in plain sight across every prior checkpoint.

Workaround used this run (scratch-only, not committed): `scratch_logs/run_ipv4.py`, which sets `urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET` before invoking `refresh.py`.

- **[high] Land the IPv4/Happy-Eyeballs fix in `connectors/base.py`.** Deliberately left as code work for a supervised session because it touches the shared HTTP layer for *every* connector and a blanket `AF_INET` force would break anyone on an IPv6-only network. Preferred shape: try IPv4 first with a short connect timeout and fall back to IPv6, or make the family preference an env-var/CLI knob defaulting to "prefer IPv4". Needs a unit test that asserts the resolver preference. **Payoff is large and repo-wide** — a 40–120× speedup on every uncached fetch, which retroactively un-blocks several items previously written off as "too slow to run unattended."
- **[med] Re-fetch documents for the 1,781 already-covered sites.** `--missing-only` never revisits them, so their document lists are as old as the run that first covered them (some date to the original F/D pass). A full re-fetch is ~1,781 sites × ~3 requests × 1.5 s ≈ **2.2 h now that IPv6 isn't taxing it** — previously ~4.5 days, which is why it was never proposed. Worth doing supervised once the base.py fix lands.

### Residual 20 docs sites — source-side defects, stable across two consecutive runs

Not closable by re-running; every one reproduced identically on an immediate retry:
- **9 have bespoke EPA microsites** instead of the standard profile template — New Bedford (`/superfund/newbedford` → `/new-bedford-harbor`), Bonita Peak, San Jacinto River, Silver Bow/Butte, Wyckoff-Eagle Harbor, Colorado Smelter, USS Lead, Lower Neponset, GE. These pages carry **no `csitinfo.cfm?id=` link at all**, so the EPA_ID → SF_SITE_ID hop has no bridge.
- **5 return HTTP 404** on their `profile_url`. One is **malformed in the source data**: `IAN000706042` → `https://www.epa.gov/superfund/www.epa.gov/superfund/highway3pce` (doubled path).
- **4 carry a cumulis URL as `profile_url`, and it is truncated** — `csitinfo.cfm?id=COD00706353` is missing the final character of `COD007063530`. Separately verified that **cumulis does not accept an EPA_ID as `id`** anyway: it returns HTTP 200 with an empty profile shell (blank `<title>`, no docdata links), so this is a dead end even with the untruncated ID.
- **1 SSLError** (`NYD980763841`, Hudson River PCBs) and **1 HTTP 500** (`CA2570024453`, George AFB) — both genuine server-side, not the IPv6 timeout (they now fail in ~1.7 s).

Closing these needs a corrected `profile_url` from a producer refresh, or a second SF_SITE_ID resolution path — **[low]**, 20 sites out of 1,908.

### Verified unchanged this run (cheap assertions only, per playbook §1)

flood **91.1%** (42,576/46,760 — COMPLETE, residual unmapped in NFHL); parcel **11,463 records / 7,270 owners / 4,621 acreages** (all 11 states exhausted); `epa-echo` **1,906/1,908** (the 2 aren't in ECHO). No producer work — files still 2026-05-12 (~12 wk), still the top supervised freshness item.

---

## Session checkpoint — 2026-07-28 (scheduled data-maintenance run)

**Both standing backfills were already done** — flood COMPLETE (91.1%, verified this run: `flood_zone` 42,576/46,760, `in_sfha` true 4,422) and parcel exhausted across all 11 registered states. So this run pivoted to the **next real gap: the Superfund enrichments were silently capped at NPL status F/D**, leaving the 121 non-Final/Deleted records (70 Not-on-NPL, 36 Proposed, 10 Removed, 3 A, 2 S) unattempted since those connectors shipped. Three commits (`8e222e9`, `ab3807b`, `796c355`), all schema-validated:

- **`ai-summary`: 1,787 → 1,908 (+121), 19 reconciled** (`796c355`). Ran `--ai-static --ai-status all --ai-limit 0`, instant. Beyond coverage this surfaced a **staleness class of bug**: ai-summary derives its narrative from four OTHER enrichment files, but was last built 2026-06-05 — before the 2026-06-19 `epa-echo` refresh. 19 summaries described superseded enforcement (8 dropped a now-absent clause — ECHO counters are rolling 5-yr windows so actions age out; 4 gained one). `epa-echo.json` verified byte-identical to HEAD, so the deltas are purely re-reading current data. **Deliberately did NOT use `--missing-only` here** — it would have preserved exactly the stale rows the pass needed to fix.
- **`epa-superfund-docs`: 1,772 → 1,781 (+9)** (`ab3807b`). Only 9 of 136 landed: EPA cumulis/semspub were at **~60 s per request** (documented off-hours spike) → **~3.8 min/site**, so a full pass would be ~10 h. Stopped the unbounded run at 12 sites and replayed `--docs-limit 12`, which writes from cache in <1 s. **127 still uncovered**, cache-cold.
- **`parcel-owner`: +26 records / +19 owners / +19 parcel acreages** (`8e222e9`). Closed 26 of the 38 FL sites left unqueried after the 2026-07-26 round-2 run.

**Dead-ends confirmed this run (don't re-attempt):**
- **`epa-echo` is complete.** The 2 uncovered Superfund records return "no ECHO match" — those facilities aren't in ECHO. Ran to exhaustion; output was byte-identical, so the write was **reverted rather than committed** (a timestamp-only bump would falsely advance the UI's "Refreshed" date, which reads `max(generated_at)` across files — same principle as `diff.py` not committing on timestamp alone).
- **`iso-rto`'s 1,708-record gap is structurally correct** — it is 100% AK/HI/PR/GU/MP/AS/VI/FM/PW, none of which sit in an organized market. Not a backfill candidate.
- **12 FL parcel sites are permanently unresolvable by re-running** — every one fails `Florida_Statewide_Cadastral` with HTTP 400 "Invalid query parameters" on point-intersect (all FUDS, pathological geometry; root cause logged issues.md 2026-07-26). Needs a connector-side query fix, not more budget.

**New items found this run:**

- **[med] `climate-zone` has a 764-site CONUS gap that IS closable (nearest-polygon fallback).** Total gap is 1,216, but only 452 are the expected AK/GU/HI/MP structural misses — the other **764 are in CONUS states** (FL 139, TX 86, WA 60, CA 59, MA 58, NY 58, ME 53, NJ 46 …) and every sampled one is a coastal/riverine point that falls just *outside* the climate-zone polygons: Fox River, Saginaw River, Tyndall AFB, New Bedford harbor, Parris Island, Whidbey Island, NASA Wallops. All have valid lat/lon. Same coastal-edge failure mode as FEMA-NRI. Fix is a bounded nearest-polygon snap (e.g. ≤5 mi) in the `PolygonIndex` containment path, mirroring how the parcel connector tolerates near-misses — code + tests, so supervised.
- **[med] Enrichment freshness is not tracked anywhere, and derived layers go stale silently.** `ai-summary` sat 6 weeks behind `epa-echo` with no signal; nothing in the repo asserts "derived file must be newer than its inputs." A cheap guard: a test (or a `refresh.py --check-staleness` mode) that compares each derived file's `generated_at` against the `generated_at` of every file it reads and fails/warns when a dependency is newer. Would have caught this class immediately. Dependency edges: `ai-summary` ← {superfund-npl, epa-redev, infra-proximity, epa-superfund-docs, epa-echo}; `planned-retirements-proximity` ← planned-retirements; `retired-industrial` join ← the four producer files.
- **[low] `epa-superfund-docs` should default to a small `--docs-limit` in unattended runs.** At ~3.8 min/site an unbounded run can never write (the connector only writes on successful completion), so an interrupted pass loses the merge even though the cache survives. Either bound it at the call site or make the connector checkpoint-write every N sites.

**Producer files still 2026-05-12** (~11 wk old) — supervised producer refresh remains the top freshness item; still deliberately out of scope for unattended runs.

---

## Session checkpoint — 2026-07-25/26 (reactor + DC siting comprehensive review; supervised, crossed two usage-window resets)

Full session review in [siting-review-2026-07-26.md](siting-review-2026-07-26.md); UX spec in [jtbd-ux-plan.md](jtbd-ux-plan.md). Commits `e8878e2`→`02c3bc9`+docs; 4 Sonnet research agents + 1 Opus coding agent.

- **FEMA flood backfill COMPLETE — 52.6% → 91.1%, 0 deferred** (`e8878e2` +3,140; `2e04e7e` +6,133; final `1513941` +8,689). All 46,760 sites attempted; the residual 8.9% are genuinely unmapped in FEMA's NFHL (source-side completeness, not backlog). `in_sfha` true: 4,422. Closes the backfill that ran across ~8 sessions since June — **no further flood runs needed** until a producer refresh adds new sites.
- **Parcel registry round 2 + backfill DONE** (`f4094d2` code, `0b1bf00` data): +FL/CO/IA/MN (11 states), `acreage_multiplier` mechanism, API-error skip + 15-consecutive-failure state guard (first run crashed on one pathological FL parcel — issues.md 2026-07-26), probe log §19-30, 19 unit tests. Full run: 5,230 queries, zero crashes, owners 3,573 → 7,251, parcel_acreage 1,886 → 4,602 (FL 1,798 / MN 790 / IA 634 / CO 587). All 11 registered states now exhausted — next parcel lift is a new verified state (none remain on the priority list; see the §19-30 dead-end log).
- **Civilian nuclear pipeline: refreshed + finally rendered** (`596e033`, `02c3bc9`): 68 sites (V.C. Summer FID by 2028-03-31; TMI/Crane + Palisades restarting; Clinch River first-ever advanced-reactor CP recommendation, hearing 2026-08-13; NEW Belews Creek Duke ESP), ⚛ map overlay (29 promising-tier markers + legend row + popups with top-3 nearby-brownfield ?site= links), Nuclear Siting tab civilian table with map→ fly-to. Closes the [high] "Frontend Nuclear Sites tab" item below.
- **JTBD quick-start strip** (`02c3bc9`): "What are you siting?" → Data center / Power generation / Nuclear reactor / Factory, one-click routing to the right view+lens; dismissible. DOM first-paint 4,938/5,000 (headroom ~62).
- **Jul-2026 regulation/incentive audit applied** (`02c3bc9`): STATE_DC_REGULATION now restrictive {NY — EO 62 permit pause}, cautionary {VA (downgraded), VT, FL}; OK removed (cost-causation tariff = excluded category). STATE_DC_INCENTIVES: AZ + IL → tier 3 `paused` (new-application freezes eff. 2026-07-01). **Next quarterly audit due ~2026-10** — also re-check the OH AEP tariff legal challenge, OK/MI re-attempts, and NY's unsigned Responsible Data Center Development Act.
- **Copy/framing from market research**: Grid Inherit = queue-skip (LBNL 55-month median), DOE coal-to-nuclear numbers in Retired Sites, AFCEC-26-R-0002 "selection pending" + Alaska expansion + ANPI vendor pairings + DOE/Amentum SRS note.

**New items from the 2026-07-26 research pass:**

- **[high] WRI Aqueduct water-stress penalty for the DC + Generation lenses.** Water is now the #2 siting constraint (JLL/DCF 2026; ~2/3 of planned DCs sit in drought-affected areas) and these lenses carry no water-availability signal (only the FEMA-NRI drought *rating* penalty). HydroBASINS polygons + `PolygonIndex`, subtractive term like flood/climate. Supersedes/absorbs the older Tier-2 WRI item.
- **[med] Recalibrate `DC_TIERS` for the gigawatt-campus era.** 2026 norm: 250+ MW single-parcel, 500 MW–1 GW+ hyperscale (CBRE/JLL). The mega tier's thresholds date to the 100–300 MW mental model.
- **[med] OZ + IRA combined "deal economics" filter.** Research JTBD #5 ("make the IRR work") is the least-surfaced job the data already supports — combinable headline filter for `in_opportunity_zone` + `in_energy_community` (+ state incentive tier), not just scoring bonuses.
- **[med] DOE federal AI-DC sites + ANPI bases as first-class rows.** SRS (Amentum, 1 GW DC + ~2 GW gen), INL/ORNL/Paducah (pending) + ANPI's Buckley/Malmstrom/JBSA (vendors paired Apr 2026) deserve scored Nuclear-Siting rows or a small curated overlay; currently a copy note only. Needs infra joins + analyst water/workforce fields per site.
- **[med] PJM/ERCOT queue-reform context chip.** PJM's new Cycle process (spring 2026, 1–2 yr target) and ERCOT Batch Zero (Jun 2026) make the flat "4.5-yr median queue" framing pessimistic in the two biggest DC markets — add an ISO-aware note chip in Rankings rows.
- **[low] Event tracking:** AFCEC-26-R-0002 award (was due Jan 2026, still unannounced); Army Janus vendor awards ("this summer" 2026); Clinch River CP hearing outcome (2026-08-13); Palisades grid reconnection; V.C. Summer operator selection (by Feb 2027).

---

## Session checkpoint — 2026-07-21 (scheduled data-maintenance run)

Flood-only run (parcel confirmed exhausted, no producer work), committed to `main` (`52d385f`):

- **FEMA flood-zone backfill: 50.4% → 52.6%** (`52d385f`) — `--infra-flood-budget 3000` full connector (all six infra layers recomputed, all 46,760 records preserved). `flood_zone` 23,564 → 24,614 (+1,050); `in_sfha` 2,033 → 2,170. **22,146 sites still deferred.** Ran short of the 3,000 budget: **FEMA's NFHL endpoint wobbled mid-run** — a burst of `ConnectionError`s tripped the connector's `25 consecutive FEMA errors — aborting` guard at **1,018 fetches** (~08:47). Designed resumable behavior: the 1,018 are cached/durable, the run still completed the CPU-bound spatial-index pass and wrote all records, and the unused budget rolls to the next run. Schema-validated post-write. Expect FEMA reliability — not budget — to be the limiter on future runs; if it aborts early, commit the partial gain and resume next run.
- **Parcel-owner: skipped (exhausted).** Verified 0 of 6,207 sites remaining across all 7 registered states (CT/MA/MT/NC/NJ/VT/WI). Re-running yields ~0 new owners; next parcel lift is **adding a new state** to `STATE_PARCEL_SOURCES` (code work — deferred to a supervised session).
- **Watcher/polling hardening (user ask, this session).** For long backfills, don't fire-and-wait on one self-terminating watcher — poll `kill -0 <PID>` + `ps -o stat,%cpu,etime` + `grep -c 'INFO fetching' <log>` between turns so a dropped/hung job is caught early. **Key gotcha:** after the flood abort the process kept running the CPU-bound spatial-index pass (rail 2.77M segs) with **no per-site logging** for ~8 min — a quiet log is NOT a dead job; verify liveness via `ps STAT=RN`/`%cpu>0`, not log tail alone. Recorded in the scheduled-task SKILL Learnings log + a `feedback-watcher-hardening-polling` memory.

**Branch hygiene:** only `main` exists (local + remote); PRs #15–#19 all MERGED; no stray branches, worktrees, or open PRs — `main` is the single source of truth, nothing to consolidate.

**Producer files still 2026-05-12** (~10 wk old) — supervised producer refresh remains the next big freshness item (deferred out of unattended runs per the ECHO-style truncation/merge gotchas).

---

## Session checkpoint — 2026-07-14 (scheduled data-maintenance run)

Two resumable missing-data backfills, run in parallel (separate output files + hosts, no conflict), committed separately and pushed to `origin/main` (`3ea5e99`, `33e35d4`):

- **FEMA flood-zone backfill: 43.9% → 50.4%** (`3ea5e99`) — `--infra-flood-budget 3000` full connector (all six infra layers recomputed, all 46,760 records preserved). `flood_zone` 20,508 → 23,564; `in_sfha` 1,771 → 2,033. **23,196 sites still deferred** — ~8 more runs at budget 3000 to finish. Halfway mark passed. See CLAUDE.md "Resumable flood backfill" / [[project-flood-backfill-resumable]].
- **Parcel-owner backfill: +710 owners, +980 parcel acreages** (`33e35d4`) — `--parcel-limit 1700` (1,648 new queries, 710 owner hits). Covered the remaining NJ/MA/VT/CT gaps. Owner 2,863 → 3,573; `parcel_acreage` 906 → 1,886. VT 14 → 329, CT 265 → 304, MA 526 → 881 owner-resolved; NJ lands acreage-only (blank MOD-IV owner, as documented). NC/MT/WI already complete. Both files re-validated against the Pydantic `Payload` schema post-write.

**Remaining parcel gap after this run:** all 7 registered states (CT/MA/MT/NC/NJ/VT/WI) are now essentially exhausted for owner-resolvable sites — the next parcel lift is **adding new states** to `STATE_PARCEL_SOURCES` (the [med] retired-industrial parcel-verification item + extending coverage), not re-running the current set. **Producer files still 2026-05-12** (~9 wk old) — a supervised producer refresh (sites/acres/fuds/brac + downstream re-enrichment) is the next big freshness item; deferred out of unattended runs per the ECHO-style truncation/merge gotchas.

---

## Session checkpoint — 2026-07-10 (branch consolidation + flood backfill)

**Branch/main hygiene (origin/main was force-rewritten `5a7dbac`→`595dda4`, identical trees).** Reset local main to origin, then made sure ALL unmerged work from this + prior sessions landed on main and cleaned up every stray branch:
- Deleted `claude/sleepy-rhodes-f1bd4b` (identical to main) and `claude/frosty-kowalevski-7e3ecf` (superseded PR #17) + worktree.
- Cherry-picked the 4 unique commits off `claude/intelligent-cannon-540b3d` (superset of `codex/pr18-review-fixes`) onto main — **zero conflicts** (branches sat on the pre-rewrite base but tree content matched current main). These were genuinely missing from main: `fix: harden siting evidence and scoring provenance` (PR #18 review fixes) + the NJ/VT/CT/MA statewide parcel expansion + `parcel_acreage`/`parcel_id` schema + scoring land fallback. Deleted both branches (local + remote) after confirming main is a strict superset.
- Full suite green before landing: **429 unit + 282 e2e**.
- Added a Git Discipline note to CLAUDE.md + AGENTS.md: `git fetch --prune` and check the newest of {`origin/main`, open PRs, newest feature branches} before starting; documented the force-rewrite recovery (identical-tree check → `git reset --hard`; rebase specific commits, not raw merge).

**FEMA flood-zone backfill: 36.8% → 43.9%** (`757dd0e`) — `--infra-flood-budget 3000`, `flood_zone` 17,197 → 20,508 (`in_sfha` 1,632 → 1,771). Full connector (all six infra layers recomputed, all 46,760 records preserved). **26,252 sites still deferred** — ~9 more runs at budget 3000 to finish. See [[project-flood-backfill-resumable]] / CLAUDE.md "Resumable flood backfill."

**Missing-data survey (all datasets):** flood is the only large non-structural gap remaining. Confirmed dead-ends (source-side, not backfillable): ACRES acreage (100% missing — no source column), FUDS acreage (66% — undigitized USACE polygons), FEMA-NRI (24% — AK/HI/territories). Owner data is expandable via parcel-owner (NJ/VT/CT/MA now added; the [med] retired-industrial owner backfill item below is the next parcel target). Producer files still 2026-05-12 (~8 wk) — best refreshed supervised.

---

## Session checkpoint — 2026-07-05 (parcel developable-acreage + scoring fallback)

**Completed this session:**
- **Brought in the stray provenance-fix commit.** Cherry-picked `fe48dc2` (`codex/pr18-review-fixes`, the post-merge trust/provenance audit from the PR #18 comment) onto this branch. `sleepy-rhodes` was already fully squash-merged as PR #18 (empty diff); `frosty` is behind main (an old pre-merge AP1000 branch — skipped).
- **Parcel developable-acreage (answers "how many acres are actually available for development").** `connectors/parcel_owner.py` already fetched `gisacres`/parcel-id in `outFields` but discarded them — now emits `parcel_acreage` + `parcel_id` (two new `SiteRecord` fields). This is the ONLY land-size signal for the ~36k ACRES brownfields (their source has no acreage column — gap #1). A parcel with acreage but a blank owner is now a real record (not a tombstone); 0/neg acreage dropped as bad geometry. Detail-panel "Parcel area" row + 2 CSV columns.
- **Scoring uses parcel acreage as a fallback.** `_effectiveAcreage(site)` in `dc-score.js` (`acreage ?? parcel_acreage`) feeds the acreage component of all three lenses, so ACRES / parcel-matched sites stop scoring 0 on land — biggest lift to the **Manufacturing** lens (mid-size parcels are its sweet spot). Conservative floor: reported `acreage` always wins.
- **Tests:** +4 unit (`test_parcel_owner.py`, now 10) + 2 e2e (`test_dc_score.py`, now 157). AGENTS.md mirror regenerated.

**State registry expanded this session — NJ, VT, CT added (6 states now).** Verified via ArcGIS-Online search + live field/point probes (`data-source-research.md` §18): NJ = NJOGIS Parcels/MOD-IV composite (`OWNER_NAME`/`CALC_ACRE`/`PAMS_PIN` — owner often blank → acreage-only, exactly the new path), VT = VCGI standardized parcels (`OWNER1`/`ACRESGL`/`MAPID`), CT = CT GIS Office CAMA layer (`Owner`/`Land_Acres`/`Parcel_ID`). ~1,830 new candidate sites (NJ 808 / CT 562 / VT 460); first bounded batch run this session, resumable for the rest.

**Follow-ons opened this session:**
- **[med] Continue the NJ/VT/CT backfill** (resumable `--parcel-limit N` runs) and add the free acreage-upgrade for the ~2,058 NC/MT/WI owner records once run where the cache lives.
- **[med] MA MassGIS parcels — needs `LOT_UNITS` handling.** Owner (`OWNER1`) is there but lot size is `LOT_SIZE` + a per-record `LOT_UNITS` (A=acres/S=sq ft). Add a per-record unit-aware acreage path to the connector, then register MA. PA has no statewide layer (county-by-county); NY public parcels carry no owner.
- **[low] Table "Parcel acres" column + sort.** Surface `parcel_acreage` as an optional table column so users can rank by actually-available land, distinct from program-reported `acreage`. **Attempted + reverted 2026-07-05** — a full column costs ~250–500 DOM nodes at the 250-row page size and pushed `test_dom_size_under_5k_nodes` to 5,377 (> 5,000 cap). `parcel_acreage` is already exposed via the detail-panel "Parcel area" row + CSV + all three scoring lenses, so it's not worth relaxing the perf guardrail. Revisit only alongside the DOM-budget item below (e.g. a user-toggled optional-columns mechanism that doesn't render inactive columns).
- **~~[med] DOM-budget drift — first-paint is ~4,876 nodes, cap is 5,000.~~** **Docs corrected + diagnosis fixed 2026-07-11.** Measured the real first-paint breakdown (added a throwaway e2e probe): total **4,876** — `view-table` **2,617** (the 250-row main Table, `TABLE_PAGE_SIZE`), `view-map` **1,576** (Leaflet panes/markers), `view-about` **171**; the hidden tab views are **already lazy** — `view-candidates` **49** and `view-ap1000` **39** are skeleton-only (their tables build on first activation). So the item's original premise was wrong: the "biggest win" of lazy-building the hidden Rankings/Nuclear-Siting tables would reclaim **<90 nodes**, not the bulk. The real cost is the main Table + map. Updated the stale claims: `test_dom_size_under_5k_nodes` docstring and the CLAUDE.md "Paginated table" entry now carry the accurate 4,876 breakdown + corrected lever. **Remaining headroom is ~124 nodes** — treat the 5k cap as effectively full. The only *large* win left is deferring the main Table's first-page build until the Table tab is activated (~2,617 nodes), but that breaks the "table rows always exist at load" invariant that many e2e tests and the marker→row highlight (`ensureRowRendered`) rely on — **[low]** now, its own PR, not worth it for the current headroom pressure.

---

## Session checkpoint — 2026-07-02 (generation opportunities + manufacturing reuse)

**Completed this session:**
- **Planned-retirements overlay (NEW).** `scripts/build_planned_retirements.py` → `docs/data/planned-retirements.json` (27 KB): 90 operating plants ≥100 MW / 75,573 MW with ANNOUNCED retirement dates (EIA-860M "Operating" sheet, `Planned Retirement Year` — the forward-looking counterpart to `eia-retired-plants`). Teal ⬢ markers via `ensurePlannedRetirementsLoaded()`, "Retiring plant" legend row, popup with MW/fuel/retirement window/BA/operator. Re-run alongside EIA-860M refreshes.
- **Manufacturing-reuse sector analysis** — `manufacturing-reuse-opportunities.md`: taxonomy of 7 manufacturing sectors that plausibly site on brownfields (battery/gigafactory, BESS, EAF green steel, hydrogen/e-fuels/ammonia, semiconductor fab, defense industrial, cleantech components) with per-sector power/water/acreage/rail/workforce requirements, mapped to existing dashboard signals. Key gap identified: workforce data.

**Evaluation doc (2026-07-02, same session):** `unified-rankings-and-pwr-siting-plan.md` — (1) Table + DC Candidates merge evaluation → recommend renaming to "Rankings" + third Manufacturing lens now, full config-driven table merge later; manufacturing v0 weights proposed (rail 22 / acreage-peaked 18 / transmission 16 / substation 12 / gas 12 / highway 10 / readiness 10). (2) AP1000 → PWR generalization: `REACTOR_CLASSES` parameterization (AP1000 / 2-unit / AP300 SMR / microreactor — water demand + acreage threshold + voltage anchor per class), water margin computed from **7Q10 low flow ÷ class consumptive demand** (replacing annual-mean anchoring), NEW **water-rights** dimension (`water_rights_regime` riparian/prior-appropriation/hybrid + site-level gatekeeper notes: TVA §26a, ACF compact, Tucson AMA, CA SWRCB; multiplier 1.0/0.6/0.2 on the water component), `dry_cooling_viable` flag, NRC 10 CFR 100.21 population flag. Sequenced: rankings-lens PR → water rights + 7Q10 pass → reactor-class PR → full table merge.

**Addendum 2026-07-02 (citations + parcel availability):** Envirofacts per-facility citation in every retired ◆ popup; `_join_tracked_corpus()` + `--join-only` in `build_retired_industrial.py` (214/658 sites linked to a tracked record carrying owner/SWRAU/cleanup evidence); `REACTOR_CLASSES` spec/water citations + provenance line; Parcel-availability block on every Nuclear Siting row (AF RFLP parcels / Janus program vehicle / SAM.gov + GSA disposal links).

- **[med] Retired-industrial parcel verification via parcel polygons.** All 658 overlay points remain availability-unverified; the 214 nearby tracked-program links are proximity context only. Extend verified `STATE_PARCEL_SOURCES` coverage and use point-in-polygon to attach owner + parcel id without inferring parcel identity from distance.
- **[low] GSA disposal / SAM.gov lease-offering connector.** Scrape disposal.gsa.gov listings + SAM.gov RLP/EUL notices into a small overlay so "actually offered" federal parcels become a first-class data layer instead of per-row links.

**New backlog items from this session:**

- ~~**[high] Rankings tab rename + Manufacturing lens v0**~~ **Done 2026-07-02.** Tab renamed, `computeManufacturingScore` lens shipped (`?lens=mfg`).
- ~~**[high] AP1000 water-rights + 7Q10 curation pass**~~ **Done 2026-07-02** (rights: all 14 sites curated + multiplier; low-flow margin machinery shipped, populated for Robins). **Remaining [med]: script the USGS 7Q10 backfill** for the other river-supplied sites (daily-values RDB fetch → 7-day rolling annual minima → 10-yr recurrence) and fill `water_low_flow_cfs`.
- ~~**[med] Reactor-class parameterization**~~ **Done 2026-07-02.** `REACTOR_CLASSES` (AP1000/APR1400 large PWRs distinct from AP300 SMR and Janus micro), tab renamed "Nuclear Siting", per-class water/acreage/voltage. Remaining [low]: `dry_cooling_viable` UI flag chip + NRC 10 CFR 100.21 population-proximity flag.
- **[med] Full Table/Rankings merge (config-driven column presets)** — Part 1A; last, own PR.

- **[high] Workforce enrichment via Census LEHD/LODES.** Manufacturing-sector employment (WAC files, free bulk CSV, no key) within a ~30-mi commute radius of each site, pre-indexed with the pure-Python `PointIndex` pattern. The single missing layer for a manufacturing lens; also strengthens the AP1000 workforce factor with quantitative data.
- ~~**[med] Third scoring lens: "Manufacturing fit" in dc-score.js.**~~ **Done 2026-07-02 (v0).** Workforce remains the next quantitative upgrade; do not treat the current cross-sector screen as a sector-specific feasibility model.
- **~~[med] Join planned-retirements into scoring.~~** ✓ **Done 2026-07-11.** New `connectors/planned_retirements.py` (slug `planned-retirements-proximity` — distinct from the overlay slug so it doesn't clobber the file it reads) distance-joins the 90 overlay plants onto all 46,760 sites via a pure-Python `PointIndex` → `docs/data/planned-retirements-proximity.json` (614 within 5 mi). Schema gained `planned_retirement_{mi,mw,fuel,year,name}`. [dc-score.js](docs/dc-score.js) `_scoreGridReuse()` now credits `MAX(_retiredPlantFrac, _plannedRetirementFrac)`; the planned path uses a forward-looking `_plannedRetirementProximity(year)` multiplier (≤2029 → 1.0 deal-window / ≤2033 → 0.6 / later → 0.3, absolute-year buckets, re-baseline annually). **Generation lens only** (per scope — no DC `grid_inheritance` credit); `grid_reuse` weight unchanged at 8, weights still sum to 100. Frontend: `ensurePlannedRetireProxLoaded()` join + detail-panel "Retiring plant" row (`#d-planned-retire-mi`). Verified in-browser (155 joined, row renders "0.3 mi · Sherman Avenue · 113 MW · gas · ret. 2027", no console errors). Tests: 11 unit + 8 e2e. CLAUDE.md + llms.txt + AGENTS.md updated. Code review (PR #19) caught + fixed a `--missing-only` truncation bug (empty index returned `[]` instead of the on-disk records) — guarded by `test_missing_only_empty_index_does_not_truncate`.
- **[high] Systemic enrichment load-order race — small all-programs enrichments silently drop ACRES/FUDS/BRAC joins.** Discovered via Codex review of PR #19. Every enrichment loader (`ensureInfraLoaded`, `ensureRetiredPlantsLoaded`, `ensureParcelOwnerLoaded`, `ensureOppZoneLoaded`, `ensureIraEnergyCommunityLoaded`, `ensureFemaNriLoaded`, `ensureClimateZoneLoaded`, …) applies its join with `const existing = sitesById.get(rec.id); if (!existing) continue;` — but they all run in the same `Promise.allSettled(lazyLoads)` fan-out as `ensureAcresLoaded`/`ensureFudsLoaded`/`ensureBracLoaded` with NO ordering guarantee. Any all-programs enrichment whose file is **smaller than `epa-acres.json` (~10.9 MB) / `dod-fuds.json` (~4.4 MB)** resolves first and drops those programs' records permanently. By on-disk size the at-risk layers are: `parcel-owner` (542 KB), `eia-retired-plants` (1.4 MB), `climate-zone` (2.8 MB), `opportunity-zone` (4.0 MB), `ira-energy-community` (4.8 MB), `fema-nri` (7.9 MB) — all < ACRES. Only `infra-proximity` (12 MB, > ACRES) is accidentally safe. **PR #19 fixed just its own new loader** (`ensurePlannedRetireProxLoaded` now `await`s the program promises before applying, mirroring `applyUrlSelection`; guarded by `test_planned_retirement_join_covers_all_programs`, which forces the race via `page.route` delay). **Altitude fix**: extract a shared `applyEnrichmentWhenProgramsReady(payload, applyRecordFn)` helper that awaits `[acresLoadingPromise, fudsLoadingPromise, bracLoadingPromise].filter(Boolean)` once, and route every all-programs enrichment loader through it (Superfund-only enrichments — echo/docs/redev/ai-summary — don't need it since Superfund is eager). Add a race-forcing e2e per affected layer (or one parametrized test over the data files). This measurably affects ACRES DC scores today whenever an at-risk layer wins the race.
- **[low] `eia-retired-plants` has the same `--missing-only` empty-index truncation as the one fixed in `planned-retirements-proximity` (PR #19).** `connectors/eia_retired_plants.py` `fetch_records()` does `if idx.point_count == 0: return []` *before* the missing_only merge — so a `--missing-only` run that hits an empty index (EIA-860M download failure / cache miss) would overwrite `eia-retired-plants.json` empty. Apply the same guard: `return self.existing_records() if missing_only else []`, and add a regression test mirroring `test_missing_only_empty_index_does_not_truncate`. Deferred out of PR #19 to keep its scope to the new connector.
- **[low] Port proximity layer.** Ammonia/e-fuels exports anchor on ports; no current signal. Census TIGER or USACE port shapefiles → `port_mi` via existing `SegmentIndex`/`PointIndex` machinery.

---

## Session checkpoint — 2026-06-30 (nuclear civilian sites + INL study)

**Completed this session:**
- **USGS ASCE 7-22 seismic hazard for AP1000 military tab (PR #16, merged).** `USGS_SEISMIC` dict with all 14 sites, pre-fetched from USGS ASCE 7-22 API (Risk Cat. IV, Site Class C). Emits `usgs_pgam`, `usgs_ss`, `usgs_sdc`, `usgs_exceeds_sse`, `usgs_api_source`. 4 sites exceed AP1000 SSE threshold (0.30g): JBLM 0.59g, Wainwright 0.46g, Edwards 0.45g, Campbell 0.37g.
- **INL AP1000 report saved** — `docs/data/references/INL-AP1000-Opportunities-Sort128167.pdf` (Aug 2024 INL/MIS-24-80216, 65 sites evaluated).
- **Idaho ANSF saved** — `docs/data/references/Idaho-Advanced-Nuclear-Strategic-Framework.pdf` (Sep 2025, Idaho Strategic Energy Alliance strategy document — no specific siting coordinates, focuses on policy/workforce/supply chain).
- **`docs/data/nuclear-civilian-sites.json`** (NEW) — all 67 civilian nuclear sites (65 from INL Table 1 + Project Matador + Kewaunee), with INL category, COL status, owner, market, lat/lon for 67 sites, and per-site notes. Generated by `scripts/build_nuclear_civilian_sites.py`.
- **`docs/data/nuclear-brownfield-proximity.json`** (NEW) — 452 Superfund proximity matches across 67 nuclear sites within 50 mi, generated alongside the nuclear sites JSON.

**Idaho ANSF key takeaways (logged for backlog, not yet implemented):**
- Idaho's "Advanced Nuclear Strategic Framework" (Sep 2025) is a **policy/workforce document**, not a siting study. No specific new AP1000 coordinates — existing Idaho nuclear activity centers on the INL / former CFPP site (already in `nuclear-civilian-sites.json` as `inl-cfpp-id`).
- Key orgs: INEC (Intermountain-West Nuclear Energy Corridor), LINE Commission, SPEED Council, Idaho Power NuScale CFPP (NuScale, not AP1000).
- Rocky Mountain Power's IRP calls for 500 MW nuclear baseload within 10 years.
- Idaho EO 2025-06 created a nuclear energy task force — potential for new site designations in the next 12–18 months. **Check Idaho Governor's office for EO 2025-06 implementation updates quarterly.**
- **Don't** treat Idaho's ANSF as an AP1000 siting guide — it's a workforce/supply-chain investment strategy.

---

## Session checkpoint — 2026-06-30 (scheduled data-maintenance run)

- **FEMA flood-zone backfill: 31.7% → 36.8%** (`e09453d`) — `--infra-flood-budget 2500`, `flood_zone` 14,814 → 17,197 (`in_sfha` 1,632). Overlaid only the new flood values onto main (no OSM substation re-fetch drift); all 46,760 records preserved. ~27,895 sites still deferred — ~12 more runs at this budget to finish. See [[project-flood-backfill-resumable]] / CLAUDE.md "Resumable flood backfill."
- The three AP1000 backlog items below were landed in parallel via PR #15 / #16 during this same run. Next obvious data work: keep running the flood backfill; the producer datasets (`sites.json`, `epa-acres`, `dod-fuds`, `dod-brac`) are from 2026-05-12 (~7 wk old) and are the next freshness item — but a producer refresh re-fetches whole datasets + triggers downstream re-enrichment, so it's best run supervised (watch the ECHO-style truncation/merge gotchas).

---

## AP1000 tab — next steps (2026-06-25)

- ~~**[high] Add `power_plant_*` / `retired_plant_*` to AP1000 CSV export.**~~ **Done 2026-06-30 (PR #15).** Added `iso_rto`, `iso_rto_note`, `power_plant_mi/mw/fuel`, `retired_plant_mi/mw/fuel/year/name` to `AP1000_CSV_COLUMNS`.

- ~~**[high] ISO/RTO field per AP1000 site.**~~ **Done 2026-06-30 (PR #15).** `GRID_OPERATOR` dict in `build_ap1000_sites.py`; emits `iso_rto` / `iso_rto_note` / `iso_rto_source_url`; Grid context block leads with the ISO/RTO row. Correct assignments: TVA ×5 (Arnold, Campbell, Holston, Redstone, Fort Campbell), PJM ×1 (JBMDL), ERCOT ×1 (Fort Hood), NYISO ×1 (Fort Drum), CAISO ×1 (Edwards), Non-RTO/SERC ×3 (Robins, Benning, Bragg), Non-RTO/WECC ×2 (Davis-Monthan, JBLM), ASEA ×1 (Fort Wainwright).

- ~~**[med] USGS quantitative seismic hazard**~~ **Done 2026-06-30.** `USGS_SEISMIC` lookup dict embedded in `build_ap1000_sites.py` (ASCE 7-22, Risk Cat. IV, Site Class C). Emits `usgs_pgam` / `usgs_ss` / `usgs_sdc` / `usgs_exceeds_sse` / `usgs_api_source` on every site. Flags cell now shows "⚡ Seismic PGA 0.59g · SDC D" with source link; color-coded by exceedance of AP1000 SSE threshold (0.30g): `bad` ≥0.30g (JBLM 0.59, Wainwright 0.46, Edwards 0.45, Campbell 0.37), `warn` ≥0.15g, `ok` otherwise. 4 CSV columns added. 1 new e2e test (`test_ap1000_seismic_flag_shows_usgs_pga`).

---

## Nuclear civilian sites — next steps (2026-06-30)

Curated data is in `docs/data/nuclear-civilian-sites.json` (67 sites, INL Table 1 + Matador + Kewaunee). The brownfield proximity is in `docs/data/nuclear-brownfield-proximity.json`. Items below are frontend + analysis work not yet implemented.

- ~~**[high] Frontend "Nuclear Sites" tab (or overlay layer).**~~ **Done 2026-07-26** (`02c3bc9`) — ⚛ overlay for 29 promising-tier sites (incl. blue restarts + post-study entrants), legend row, popups with nearby-brownfield links, civilian table in the Nuclear Siting tab. Original scope follows: Display the 18 "promising" civilian AP1000 sites (dark_green + light_green INL categories) on the map — a new `L.divIcon` layer (blue ◉ for dark_green, light_blue ◉ for light_green, teal ◉ for blue restart). Click → popup with name, category, COL status, owner, units planned, and a "View nearby brownfields" button that loads the proximity list. `ensureNuclearSitesLoaded()` lazy-loads the JSON. **Don't** use the same marker shape as reference-campuses (★) or retired-industrial (◆) — pick a distinctive nuclear symbol (⚛ or ◉).
  - **Legend row** per category when the layer is populated (dark_green = "AP1000 ready", light_green = "AP1000 feasible", blue = "Restart / SMR").
  - **Tab implementation** could be a fourth overlay toggle button next to the legend rows, OR a separate tab (lower priority — the overlay is lighter-weight).

- **[med] Brownfield proximity table in the detail panel.** For any nuclear site selected from the overlay, the popup/panel shows the top-5 Superfund brownfields within 50 mi from `nuclear-brownfield-proximity.json`. Each row shows: site name, distance, EPA_ID, acreage, NPL status — and clicking navigates to `?site=<id>` in the main map. Enables the "AP1000 site → co-located brownfield cleanup opportunity" discovery path.

- **[med] Add all-programs brownfield proximity.** The current `nuclear-brownfield-proximity.json` only cross-references Superfund NPL sites (`docs/data/sites.json`). Extend `scripts/build_nuclear_civilian_sites.py` to also load `docs/data/epa-acres.json` (36k brownfields) and emit a broader proximity result. Will surface ACRES brownfields (which have no acreage but have city/state) within 50 mi of each nuclear candidate. Gate on lazy-loading `epa-acres.json` at script time (already on disk).

- **[low] V.C. Summer progress tracker badge.** Brookfield/Nuclear Company's FID is expected 2027–2028; this is the highest-probability near-term AP1000 deployment. Add a "FID Expected 2027" badge or date chip to the detail popup for `vc-summer-sc`. Source: `nuclear_civilian_sites.json` `fid_expected` field already set. Refresh when FID decision is announced.

- **[low] Project Matador COLA tracker.** Fermi America's COLA was accepted by NRC June 2025; NRC review is ~3 years (decision expected ~2028). Add a "NRC review in progress" status chip for `project-matador-tx`. Source: NRC docket. Refresh quarterly.

- **[low] Regenerate proximity after `epa-acres.json` lazy-load expands.** The current proximity only searches Superfund (~1.9k sites). The 36k ACRES brownfields within 50 mi of V.C. Summer (Fairfield County SC) would be a more complete picture for a co-located cleanup thesis. Separate script pass: `python3 scripts/build_nuclear_civilian_sites.py --all-programs`.

---

## Nuclear-relevant manufacturing brownfields — expansion (2026-06-30)

The current `docs/data/retired-industrial.json` (658 sites: 533 manufacturing + 125 mining) captures GHGRP stopped-reporting (≥2010). It misses a generation of pre-GHGRP closures that are the most *nuclear-relevant* industrial brownfields — those with the largest stranded grid interconnects (steel mills, aluminum smelters, heavy chemical plants) that closed 1980–2009.

**Why these sites matter for nuclear:** An AP1000 needs a 1,117 MWe interconnect. The closest analogy in the brownfield corpus is a large retired steel mill or aluminum smelter: these were typically served by 345–500 kV FERC-jurisdictional tie lines (not distribution loops), and the grid infrastructure persists as stranded assets.

**Known pre-GHGRP closures not in current overlay (add to `retired-industrial.json` or a new `nuclear-grid-brownfields.json`):**

| Site | Location | Closure | Type | Est. MW load | Grid notes |
|---|---|---|---|---|---|
| Bethlehem Steel Lackawanna | Lackawanna NY | 1983 | Integrated steel mill | ~400 MW | NYPA tie, 345 kV |
| Geneva Steel | Vineyard UT | 2001 | Integrated steel mill | ~350 MW | PacifiCorp 345 kV |
| Wheeling-Pittsburgh Steel (Steubenville) | Steubenville OH | 1985 | Steel | ~200 MW | AEP 345 kV |
| Homestead Works (US Steel) | Homestead PA | 1986 | Steel | ~300 MW | Duquesne Light 138+ kV |
| Kaiser Aluminum (Mead) | Spokane WA | 2001 | Aluminum smelter | ~350 MW | Bonneville Power |
| Kaiser Aluminum (Ravenswood) | Ravenswood WV | 2000 | Aluminum smelter | ~500 MW | AEP 345 kV |
| Anaconda Copper Smelter | Anaconda MT | 1980 | Copper smelter | ~100 MW | NorthWestern |
| Columbia Falls Aluminum | Columbia Falls MT | 2009 | Aluminum smelter | ~250 MW | Flathead Electric |
| Norsk Hydro (Philadelphia) | Philadelphia PA | 2002 | Aluminum | ~80 MW | PECO |
| Globe Metallurgical (Beverly) | Beverly OH | closed | Ferroalloy | ~60 MW | AEP |

**Implementation path:**
1. **[med] Build `scripts/build_nuclear_grid_brownfields.py`** — a separate curated script (NOT a connector) that hand-curates the ~30 most grid-significant pre-GHGRP industrial closures. Same pattern as `build_retired_industrial.py` but focused on sites with documented ≥100 MW interconnects. Source: EIA-860 historical plant data (goes back to 1990 for most units, earlier for large industrial) + DOE/FOIA for pre-EIA loads.
2. **[low] Merge into `retired-industrial.json` overlay** OR keep as a separate `nuclear-grid-brownfields.json` layer with a distinct ◈ marker color. The distinction matters: GHGRP-stopped sites have *confirmed* recent reporting; pre-GHGRP sites have *estimated* historical load — show the provenance difference in the popup.
3. **[low] EIA Form 860 historical industrial loads.** EIA's bulk download includes industrial power plant (sector 99) data going back to 1990. Filter to ≥100 MW capacity, status "RE" (retired), NAICS in steel/aluminum/chemicals. This would give systematic coverage rather than the manual list above. Adds ~300 additional sites. Merge with the GHGRP overlay by plant lat/lon proximity.

---

## Session checkpoint — 2026-06-24

**Completed this session:**
- **Consolidated flood backfill from `feat/rau-status-land-readiness` onto `main`.** Data-aware merge kept current `main`'s newer parcel-owner / retired-site schema and copied the final FEMA NFHL fields from the flood branch record-by-record. `docs/data/infra-proximity.json` remains 46,760 records; `flood_zone` coverage is now 14,814 records (~31.7%). This supersedes the branch-local 2026-06-23 checkpoint while preserving later `main` work.

## Session checkpoint — 2026-06-19

**Completed this session:**
- **Ranking-view Signals badges (v1.22.x).** Surfaced four scoring signals that already moved a site's DC score but were invisible in the DC Candidates table: **Land Ready** (SWRAU, solid-green), **Climate** (FEMA NRI Very-High wildfire/drought, red), **Nuclear** (operating nuclear ≥500 MW ≤5 mi grid-inheritance, purple), **Zoning** (state regulatory friction, red). Each has an e2e regression test (`test_candidates_view.py`).
- **v1.23 — `STATE_DC_REGULATION` regulatory-climate penalty.** From 2026 market research (Regulation is now a Tier-3 siting filter). Per-state lookup → `s.dc_regulatory_climate` stamped at ingest → `_regulatoryPenalty()` subtracts 8/4 from the **DC lens only** (generation untouched — a DC moratorium doesn't block a power plant). 4 states flagged (VA/OK restrictive, VT/FL cautionary), conservative + dated, quarterly re-audit. UI: Zoning badge, suitability chip + note, score meters. `test_regulatory_penalty_dc_lens_only`; weight tables still sum to 100. CLAUDE.md entry added.
- **"How this ranking works" explainer.** Collapsible `.cand-help` in the candidates view decoding the 0–100 score, both lenses, tier buckets, and badge color semantics — the clarity surface for the ranking. Verified visually (VA: DC 76 vs Gen 78 divergence from the penalty).
- **Data:** flood_zone backfill checkpoint 9,900 → 13,407 (28.7%).
- **ECHO NPDES re-enrichment — DONE.** Populated `has_npdes_permit` (was 0 across the file). ECHO HTTP-429'd hard, so the full F/D run took **6 cache-resumed passes** (1,094 → 1,740 reachable; 429s 188→0; ~47 sites unreachable = no ECHO registry match). To avoid dropping the 166 records outside this run's reachable set (all carry prior enforcement data), **merged over the previously-committed file: 1,906 preserved, 1,740 refreshed, 166 flagged `has_npdes_permit=true`.** Water badge + detail-panel NPDES row verified rendering end-to-end (Playwright). The NPDES item (backlog #1 + the "In progress / blocked" note below) is now closed.

**Parcel-owner verification — proven for NC, ready to go broad (v1.25):**
- `connectors/parcel_owner.py` verifies each site's owner against public state cadastral (parcel) records by point-in-polygon. **NC proven 95% hit rate** (NC OneMap `NC1Map_Parcels` layer 1) — fills `current_owner` + `current_owner_source` for the ~38k sites that had none (Superfund/ACRES/BRAC were 0%). Frontend join (`ensureParcelOwnerLoaded`, fill-if-empty so FUDS's USACE owner isn't clobbered) + detail-panel owner row already render it. 6 unit tests. A 40-site NC proof batch is committed in `docs/data/parcel-owner.json`.
- **To go broad** (run when greenlit; rate-limited ~1.5s/site + cache makes it resumable): `python3 refresh.py --source parcel-owner --parcel-state NC --parcel-limit 0` for all NC (~1,139 sites, ~30 min), then add states. The only extension point is the `STATE_PARCEL_SOURCES` registry — one verified entry per state.
- **Next states:** [high] confirm the TX StratMap/TxGIO host (`feature.tnris.org` didn't resolve from the dev sandbox — see data-source-research.md §14) and enable the stubbed TX entry; then probe other states' GIS portals for a parcels FeatureServer with an owner field (use the §13 point-query pattern with `outFields=*` to find the owner field, then add a registry row).
- **Follow-on [med]:** emit `parcel_acreage` (the parcel polygon's `gisacres`) too — needs a schema field, but the parcel area could partially fill the ACRES 100%-missing-acreage gap and cross-validate Superfund acreage. Deferred to keep the first cut schema-clean.
- **Structural miss classes (don't chase):** federal megasites (military reservations aren't in county parcels) and ACRES address-geocodes that land off-parcel.

**Deferred — terrain slope (from 2026-06-19 research, #2 idea):**
- **[med] Terrain slope penalty.** Standard siting filters at <7% slope; we score no terrain. USGS 3DEP / National Elevation Dataset is public. For the ~5k polygon-bearing sites (Superfund/FUDS/BRAC) sample mean slope and penalize steep/unbuildable parcels. **Why deferred, not done:** heavier than point-in-polygon (DEM raster sampling — USGS EPQS is one elevation/point, so slope needs ~4-5 calls/site = ~25k calls, or a raster pull that needs rasterio/GDAL and breaks the pure-Python spatial architecture); and coverage is partial (the 36k ACRES points have no polygon). Best scoped as its own session, ideally folded into the backlogged `developable-land` connector (both need polygon sampling). Fiber/IXP proximity and substation hosting-capacity were also evaluated and confirmed **data-blocked** (no public nationwide source) — don't re-research without a new source.

---

## Session checkpoint — 2026-06-16 (scheduled data-maintenance run)

**Completed (v1.22):**
- **RAU_Status (SWRAU land-readiness) wired through the stack.** Was fetched in epa-redev `OUTFIELDS` but dropped in `normalize()`. Now in `schema.py` + `EpaRedev.normalize()` (`_clean_rau_status()`), regenerated from cache (zero new HTTP). Live: 940 "Meets the Measure" / 832 "Does Not Meet" / 87 retracted / 13 formerly-retracted / 33 null on 1,905 records. Frontend: green "Land Ready" program-cell pill (`_meetsRau()`), detail-panel "Land readiness" row (`setRauStatusCell()`), CSV column, DC-score readiness +3 / generation +2 (cap-absorbed, weights still sum to 100). 3 unit + 2 e2e tests. Verified in preview.
- **Resumable flood backfill (`--infra-flood-budget` + seed).** `infra_proximity.py` now seeds prior `flood_zone`/`in_sfha` from the on-disk file (so a partial run never re-nulls) and caps NEW FEMA fetches via `--infra-flood-budget N` (cache hits/seeds are free), writing the full record set every run. `_flood_cache_key()` centralizes the cache key. 1 unit test. CLAUDE.md documents the pattern + the ~15-min rail-index fixed cost.

**In progress (this session):**
- **flood_zone backfill run** — `--infra-flood-budget 1100` launched 2026-06-16; takes prior 9,900 → ~11,000 (21.2% → ~23.5%). Per-site loop iterates all 46,760 (~45 min) + 1,100 FEMA fetches (~28 min). Commits the data file when it writes. Remaining ~35,760 sites for future scheduled runs (see CLAUDE.md "Resumable flood backfill").

**Still open (deferred — need supervised/long runs):**
- **ECHO NPDES re-enrichment** — `has_npdes_permit` still 0/1,906. Needs a full replace run (NOT `--missing-only` — that skips all covered ids, leaving the stale field). Truncation gotcha: verify `len==1906` before commit. ~50 min–10 hr, killed twice historically. Best done in a supervised session.

## Session checkpoint — 2026-06-08

**Completed this session (v1.16 → v1.17):**

- **v1.16 (merged PR #12):** EIA-860M retired plant enrichment connector (`connectors/eia_retired_plants.py`). Fetches the public EIA-860M monthly Excel "Retired" sheet; 466 plants indexed; 7,620 records emitted (573 within 1 mi). Schema: `retired_plant_{mi,mw,fuel,year,name}`. `_scoreGridInheritance()` checks retired plants first (≥100 MW dispatchable, ≤1 mi = full 8 pts); falls back to HIFLD active plant (≥500 MW coal/gas ≤1 mi). CLAUDE.md updated. 105 e2e tests passed.

- **v1.17 (just committed `f441590`):**
  - **Reference campuses overlay:** `docs/data/reference-campuses.json` (10 confirmed hyperscale brownfield deals: Google/Widows Creek, Aligned/Conesville, Homer City Energy Campus, AWS/Susquehanna, NorthPoint/Fairless Works, Project Marvel AL, Meta/Forest City, QTS/Qimonda Richmond, Cheswick PA, Microsoft/Foxconn WI). Gold ★ star markers on a `referenceCampusLayer` in Leaflet; click → popup with company, previous use, status, acreage/MW, source link; legend row added when populated; lazy-loaded alongside other enrichments.
  - **Nuclear adjacency DC scoring:** `_scoreGridInheritance()` gains a 3rd pathway — operating nuclear ≥500 MW within 5 mi → 45% of cap (4 pts). AWS/Talen Susquehanna $650M deal pattern (PPA + grid-neighborhood). 4 new e2e parametrize cases; 109 e2e + 388 unit tests pass.

- **v1.18:** IRA Energy Community enrichment connector (`connectors/ira_energy_community.py`). Point-in-polygon against DOE NETL coal-closure (4,325 tracts) + fossil-fuel-employment (901 counties) layers. **14,790 / 46,760 sites qualify (31.6%).** Schema: `in_energy_community`, `energy_community_type`, `energy_community_detail`. Frontend: detail-panel row, green "IRA · Coal"/"IRA" pill, `sig-ira` badge, CSV columns. DC-score: +3 readiness both lenses. 12 unit + 2 e2e tests.

- **v1.19 (just committed):** FEMA National Risk Index enrichment (`connectors/fema_nri.py`). County-level point-in-polygon against the FEMA NRI county FeatureServer (3,232 polygons). **35,783 / 46,760 matched (76.5%).** Schema: `nri_risk_score`, `nri_risk_rating`, `nri_wildfire_rating`, `nri_drought_rating`, `nri_heatwave_rating`. Scoring: `_climatePenalty()` — MAX(wildfire,drought) → −10/−5, both lenses, weight tables still sum to 100. Frontend: detail-panel "Natural-hazard risk" row, red climate note + "Climate −N" suit chip, 4 CSV columns. 8 unit + 3 e2e tests; **408 unit + 114 e2e (dc-score) pass.** Verified in preview.

- **v1.20 (2026-06-10):** Suitability scoring v3 — algorithm-accuracy pass on both lenses in `docs/dc-score.js`. (a) `_interp()` piecewise-linear curves replace step functions (substation / gas / acreage / gen-transmission) — no more 5-pt cliffs at 25/100/500 ac; anchors unchanged so all anchor-point test expectations held. (b) Grid inheritance scales by `_mwFrac` (100→0.5 … ≥1000→1.0) and `_retirementRecency` (≥2018 ×1.0 / 2008–2017 ×0.75 / older ×0.5); retired band extends to 3 mi at half credit (3,299 sites previously cliffed); active coal/gas 1–5 mi → ×0.3 PPA band. (c) `substation_kv` (on disk since v1.13.3, never used) discounts provably distribution-class substations (<69 kV ×0.5; 69–114 ×0.75; null unpunished — 7,087 sites affected). (d) Generation lens gains `grid_reuse` (8 pts, retired-plant repowering; weights rebalanced 24/18/14/12/10/8/8/6, still 100) and a 10-mi gen-tie transmission taper (was the DC 2-mi cliff). 148 e2e dc-score tests (+34 new) + 101 other e2e + 408 unit all pass.

**In progress / blocked:**
- **ECHO NPDES re-enrichment (still pending — DO NOT commit a partial file):** Connector supports `has_npdes_permit` (v1.15 column 99), but the full re-run has NOT completed — it's slow (ECHO HTTP-500s + rate limits, ~3 sites/min → ~10 hr) and the background process died mid-run twice this session. **Gotcha discovered 2026-06-08:** an interrupted `refresh.py --source epa-echo` run left `docs/data/epa-echo.json` **truncated to 18 sites** (from 1,906) — caught at the merge gate and restored from git HEAD. Before committing epa-echo.json after any future run, ALWAYS verify `len(sites) == 1906` (or whatever the full count is) AND spot-check `has_npdes_permit` coverage. Prefer running to completion in one uninterrupted session (or use `--missing-only` so a partial run merges with the on-disk file instead of replacing it). Re-run: `python3 refresh.py --source epa-echo --echo-limit 0 --echo-status F,D --missing-only`. After it completes: add `Water` badge in DC Candidates Signals (the `sig-water` CSS class already exists) + detail-panel enforcement row when `s.enforcement?.has_npdes_permit === true`.

**Available-land findings (2026-06-10 research pass):**
- ~~**[high] Wire `RAU_Status` (Sitewide Ready for Anticipated Use) through epa-redev.**~~ **Done 2026-06-16 (v1.22).** `rau_status` added to `schema.py` + `EpaRedev.normalize()` (`_clean_rau_status()` collapses blanks→None); re-run from cache (zero new HTTP). Live distribution on the 1,905 redev records: 940 "Meets the Measure" / 832 "Does Not Meet the Measure" / 87 "(Retracted)" / 13 "(Formerly Retracted)" / 33 null. Frontend: `ensureRedevLoaded()` copies `rau_status` onto the Superfund record; green "Land Ready" program-cell pill via `_meetsRau()` (only the two affirmative values count); detail-panel "Land readiness" row (`setRauStatusCell()`); CSV `rau_status` column; DC-score readiness +3 and generation readiness +2 (both absorbed by the readiness cap on fully-ready sites, weight tables still sum to 100). 3 unit tests (`test_redev.py`) + 2 e2e (`test_dc_score.py`). Verified in browser preview across all four states.
- **[med] `developable-land` enrichment connector — Monte-Carlo land-cover subtraction.** For the ~5k polygon-bearing sites (≈2.1k Superfund boundaries, ~3k FUDS layer-4, 27 BRAC): sample ~500 points inside the site polygon (reuse `PolygonIndex` ray-casting; no polygon-clipping code needed), classify each against (a) FWS NWI wetlands (`fwsprimary.wim.usgs.gov/server/rest/services/Wetlands/MapServer` — live-verified 2026-06-10, per-site bbox query, cacheable), (b) optionally OSM buildings via Overpass (already a dependency), (c) optionally FEMA NFHL SFHA polygons (already integrated per-site). Emit `developable_acreage_est` + `wetland_pct` / `built_pct` / `sfha_pct`. ~1–2 HTTP/site × 5k sites ≈ 2–4 h once, cached. Feed `_scoreAcreage*` with developable acres when present.
- **Dead ends confirmed (don't revisit without new sources):** EPA IC boundaries (`FAC_Superfund_Institutional_Control_Boundaries_EPA_Public`) = 165 polygons, OU boundaries = 239 — too sparse to generalize; `Superfund_Sites_In_Reuse` layer = points only, no acres-in-reuse field; `RedevelopmentAppSitePoints` has no reuse-acres field (full field list checked); ACRES sites are point-only with no acreage at all (existing structural gap #1), so no available-land estimate is possible for the 36k brownfields.

**Tab-UX simplification findings (2026-06-10):**
- ~~**[high] Unify the DC Candidates view with the global filter system.**~~ **Done 2026-06-10 (v1.21).** `buildCandidatesView()` now sources from `tableState.filtered`; the duplicated "Min tier" / "Readiness" button groups are deleted (their predicates live in the persona buttons / OZ checkbox / DC-candidate KPI toggle); only the DC/Gen lens toggle remains, URL-persisted as `?lens=gen`; `applyFilter()` rebuilds the view live; stats line flags "global filters applied". 5 e2e tests in `tests/e2e/test_candidates_view.py`; full suite 254 e2e pass.
- **[med] Merge DC Candidates into the Table as a "Power signals" column preset.** The deeper simplification (option 1 from the 2026-06-10 findings): one table, one filter system, one pagination/infinite-scroll implementation. Add a column-preset toggle to the Table view — "Overview" (current 8 columns) and "Power signals" (rank, site, ST, acres, score, tier, kV, substation mi, plant, gas, signals) — defaulting the Power-signals preset to score-desc sort with the rank column. The DC/Gen lens toggle moves into the preset bar. Then delete `#view-candidates`, `candidatesState`, `makeCandidateRow`, `_appendCandidatesPage`, `_setupCandidatesScroll` (~300 lines incl. the duplicated IntersectionObserver scroll guard), and the `tab-candidates` button; tab strip becomes Map | Table | About. Keep `?lens=` URL state. Prereq: v1.21 already unified the filter model, so this is purely a view merge — port the 5 `test_candidates_view.py` tests to the preset UI rather than deleting them.
1. **~~[high] NPDES badge frontend~~** ✓ **Done (ECHO re-enrichment closed 2026-06-19; frontend + tests 2026-07-11).** `Water` badge (`sig-water`) renders in the DC Candidates Signals column when `s.enforcement?.has_npdes_permit === true` (app.js:3776), and the detail panel's "Water permit (NPDES)" row (`#d-echo-npdes`) shows the ready-tinted affirmative. Now guarded by `test_water_badge_renders_for_npdes_permit` + `test_detail_panel_npdes_row_renders` in `test_candidates_view.py`.
2. **[high] USGS seismic (ASCE 7-22 SDC)** — per-site live REST (`earthquake.usgs.gov/ws/designmaps/asce7-22.json`), overnight job. SDC ≥ D = structural cost premium, ≥ E often disqualifying. Would add a second structural-hazard scoring input alongside FEMA NRI. `run_order=365`.
3. **[med] Military DC solicitations** — curated `docs/data/mil-dc-solicitations.json` (~5–10 rows: Arnold AFB TN, Davis-Monthan AZ, Edwards CA, McGuire-Dix-Lakehurst NJ, Robins GA). Same curated-JSON + overlay pattern as reference-campuses.json (v1.17).
4. **[med] WRI Aqueduct water stress** — complements FEMA NRI drought with a withdrawal/supply ratio; HydroBASINS polygon point-in-polygon (reuse `PolygonIndex`). Water is the #2 DC constraint after grid.

---

## New ideas — DC-brownfield market research (2026-06-05)

*Sourced from web research on the 2025–2026 DC-brownfield deal landscape: Homer City Energy Campus, Google/Widows Creek, Aligned/Conesville, AWS/Susquehanna, Microsoft/TMI/Mount Pleasant, Bessemer "Project Marvel," Keystone NAP/Fairless Works, EO 14318, EPA's January 2026 guidance, JLL/CBRE 2025–26 data center reports, IRA energy community rules, and the PNNL coal-plant-to-data-center white paper.*

### Stranded grid capacity — the biggest missing signal (2026-06-05)

The dominant pattern in 2025–2026 is retired coal/gas plant sites: they carry existing FERC-jurisdictional interconnection agreements that can potentially be inherited or re-contracted, bypassing PJM's 5–7-year queue. Google built on Widows Creek (TVA coal, 2,000 ac), Aligned on Conesville (AEP coal, 197 ac), Homer City is a 4.5 GW BTM gas plant on a 3,200 ac former coal site. In PJM, a 1 GW interconnection queue bypass is worth hundreds of millions in NPV at $10.7–11.3M/MW all-in construction cost.

- ~~**[high] Score bonus for large-plant co-location ("Grid Inherit" signal).**~~ **Done 2026-06-07.** Replaced generic `power_plant` (distance-only, 8 pts) with `grid_inheritance` (8 pts, strict: coal/gas ≥500 MW ≤1 mi). Weight table still sums to 100. `_DC_SUIT_GROUPS` updated. 95 e2e tests pass.

- ~~**[med] Nuclear adjacency scoring (v1.17, 2026-06-08).**~~ Added 3rd pathway to `_scoreGridInheritance()`: operating nuclear ≥500 MW within 5 mi → `Math.round(cap * 0.45)` = 4 pts (PPA/grid-neighborhood signal; the AWS/Talen Susquehanna $650M deal pattern). Wider radius than coal/gas (5 mi vs 1 mi) because nuclear plants connect high in the transmission hierarchy and DCs access via PPA, not direct co-location. Cap at 45% because interconnect is not stranded. 4 new e2e test cases in `test_dc_grid_inheritance_component` (`nuclear` fuel, mi=0.5/5.0/5.1, MW=600/400). All 11 parametrize cases pass.

- **[high] EIA-860 plant retirement feed → retired-plant layer.** The current `power_plant_mi` nearest match is agnostic to whether the plant is operational or retired. Add a `power_plant_retired: bool` field: fetch the EIA Form 860 "Generators" and "Plants" tables (free bulk download at `https://www.eia.gov/electricity/data/eia860/`) and flag plants whose generator status is "RE" (retired) or "DC" (decommissioned). A retired plant nearby is MORE valuable than an operating one — it suggests stranded interconnection capacity. Also useful for filtering the DC Candidates tab to "Grid Inherit + Retired." Run order 310, emits to `docs/data/plant-retirement.json`; `ensurePlantRetirementLoaded()` joins by `power_plant_mi` approximate lat/lon match (nearest EIA plant within 0.5 mi). ~130k EIA generators nationwide; 90-day refresh cadence since retirements are steady. **Test**: `test_retired_plant_flag_matches_eia_status`.

- **[med] FERC generator interconnection agreement lookup.** Decommissioned plants may have publicly filed FERC GIAs that can be searched on FERC eLibrary. Not automatable at scale, but: add a UI tooltip / "search FERC eLibrary" deep-link on any "Grid Inherit" flagged site in the DC Candidates table. A future enrichment pass could batch-scrape FERC eLibrary GIA filings by plant name for the top ~200 "Grid Inherit" candidates. Tier 4 complexity.

### Water as the second constraint — no public nationwide layer (2026-06-05)

Water is now the #2 site-selection constraint after grid (JLL 2026). Arizona, Nevada, and parts of TX have effectively closed new large-withdrawal permits. Former industrial/power plant sites with river access and legacy NPDES permits are worth a material premium. AZ and CA Aqueduct scores (WRI Aqueduct, Tier 2 backlog) are the right answer, but a quick proxy is available now:

- **~~[high] EPA ECHO NPDES permit flag as water-access proxy.~~** ✓ **Done (re-enrichment 2026-06-19, frontend guarded 2026-07-11).** Connector code (v1.15 — column 99 `NPDESFlag`; `has_npdes_permit`), the full F/D re-enrichment (6 cache-resumed passes; 166 records flagged true; merged over the prior file to preserve all 1,906), the `Water` Signals badge, and the detail-panel NPDES row all landed. e2e regression tests added 2026-07-11 (see the "NPDES badge frontend" item above).

- **[med] WRI Aqueduct baseline water stress → `water_stress_score`.** Already in Tier 2 backlog. Re-prioritize to **high** given 2026 market evidence that water is now a deal-killer in AZ, CA, parts of TX, and the Mountain West. Add to DC score as a penalty component (similar to flood: −12 pts for `bws_score ≥ 3`). The current Tier 2 entry has full implementation notes.

### EO 14318 "federal fast lane" — new policy tailwind (2026-06-05)

Executive Order 14318 (July 23, 2025) directed EPA to identify Superfund/brownfield sites for data center development, created NEPA categorical exclusions for qualifying projects, and fast-tracked Army Corps Section 404 permits. EPA published its brownfield data center guidance in January 2026. This is a significant regulatory tailwind that should be surfaced per-site.

- ~~**[high] EO 14318 eligibility badge.**~~ **Done 2026-06-07.** `_hasEO14318()` helper in app.js; `+3` readiness bonus in `_scoreReadinessDc`; "Fed Fast Lane" `sig-badge` in DC Candidates Signals column; `eo14318-pill` in detail-panel program pill row. `test_eo14318_readiness_bonus` covers all four ineligibility branches.

- **[med] Military installation data center solicitations.** Under EO 14318, the Pentagon is actively leasing land on **operating** military bases — not just closed BRAC sites. Five Air Force bases (Arnold AFB TN, Davis-Monthan AZ, Edwards CA, McGuire-Dix-Lakehurst NJ, Robins GA) have issued lease solicitations as of 2026. Add a curated layer `docs/data/mil-dc-solicitations.json` — a hand-maintained ~20-row JSON with site name, installation, state, solicitation status, estimated acreage, and source URL. Frontend shows these as distinctive markers on the map and a section in the DC Candidates tab. Unlike BRAC (closed sites already in our DB), these are active bases seeking tenants — a different use-case category.

### IRA energy community bonus — stacking opportunity (2026-06-05)

Brownfield sites qualify as "energy communities" under the IRA, entitling clean energy projects on them to +10pp PTC/ITC. Rural Qualified Opportunity Zone sites qualify for a 30% basis step-up (vs. 15% for standard OZ). These financial bonuses stack and significantly affect project IRR.

- ~~**[high] Rural OZ score bonus in `dc-score.js`.**~~ **Done 2026-06-07.** `_scoreReadinessDc` now gives +7 for `oz_rural === true` and +5 for standard OZ. `test_oz_rural_bonus_higher_than_standard_oz` guards it.

- ~~**[med] IRA energy community layer.**~~ **Done 2026-06-08 (v1.18).** `connectors/ira_energy_community.py`, slug `ira-energy-community`, `run_order=355`. Point-in-polygon (`PolygonIndex`) against TWO DOE NETL 2024 layers on `arcgis.netl.doe.gov/server/rest/services/Hosted/`: `2024_Coal_Closure_Energy_Communities` (4,325 tracts) + `2024_MSAs_NonMSAs_that_are_Energy_Communities` (901 counties, filtered `ec_qual_status='Yes'`). Schema: `in_energy_community: bool`, `energy_community_type` (`coal_closure` | `fossil_fuel_employment`, coal precedence), `energy_community_detail` (mine/generator/adjacent reason or MSA name). **14,790 / 46,760 sites qualify (31.6%): 3,236 coal-closure + 11,554 fossil-fuel-employment.** Deliberately does NOT auto-assert the third (brownfield) IRA category — CERCLA §101(39) excludes NPL sites and has BFPP nuances our program flag can't resolve. Frontend: detail-panel "IRA energy community" row (green link to energycommunities.gov), green "IRA · Coal" / "IRA" program-cell pill, `sig-ira` DC-Candidates badge, CSV columns. DC-score: `+3` readiness (both lenses; generation gets +3 > OZ's +2 since the +10pp ITC/PTC applies directly to a ground-up build). 12 unit tests + 2 e2e tests. **Don't** add a filter facet or rebalance weight tables — readiness cap absorbs the bonus, weights still sum to 100.

### Market-driven scoring gaps (2026-06-05)

- **[high] Interconnection queue MW within 50 mi → `queued_mw_50mi`.** Already in Tier 2 backlog under "LBNL Queued Up." Re-prioritize to **high** based on JLL 2026 evidence that grid queue wait times (4–7 years in PJM) are the #1 site-selection constraint. Sites near large queued projects know grid is being built; sites in MISO backlog areas face less constraint than PJM. Use LBNL Queued Up 2025 Edition (free annual Excel) for non-ISO regions. Full implementation notes already in the Tier 2 backlog entry.

- **[med] Union labor density by county → `ibew_density`.** States with prevailing wage requirements tied to data center tax incentives: PA (Shapiro mandate), NJ (signed law), CA (SB pending). Former steel/coal/industrial communities (Bessemer AL, Coshocton OH, Indiana PA) often have high IBEW concentrations — and this can be a prerequisite for incentive eligibility. BLS OEWS API (`api.bls.gov/publicAPI/v2/timeseries/data/`) — occupational employment for electricians (SOC 49-2111), HVAC (49-9021), construction supervisors (11-9021) by MSA → county crosswalk. New `connectors/bls_oews.py`, `run_order=380`. Surfaces as a `Labor` tier badge (High/Moderate/Low) in DC Candidates.

- ~~**[med] Reference layer: known hyperscale brownfield campuses.**~~ **Done 2026-06-08.** `docs/data/reference-campuses.json` (10 sites: Google/Widows Creek, Aligned/Conesville, Homer City, AWS/Susquehanna, Keystone/Fairless Works, Project Marvel AL, Meta/Forest City, QTS/Qimonda Richmond, Cheswick PA, Microsoft/Foxconn WI). Gold ★ star markers via L.divIcon on a `referenceCampusLayer` above the program marker layer; click → popup with company, previous use, status, acreage/MW, source link. Legend row added under programs when layer is populated. `ensureReferenceCampusesLoaded()` lazy-loaded alongside other enrichments. CSS: `.ref-campus-icon`, `.ref-campus-popup`, `.ref-status-{operational,active,planned}`. `llms.txt` updated.

- **[low] Permitting speed index by state.** Some states have formal expedited brownfield review programs (Connecticut SB 1404, Virginia DEQ fast-track, EPA CERCLA Bona Fide Prospective Purchaser protections). Map average time-to-close for brownfield redevelopment projects by state using ASTSWMO data. Surfaces as a "Permitting Speed" tier (Fast/Moderate/Slow) per state in the detail panel DC incentive section.

---

## Data-center suitability scoring (tiered plan, researched 2026-05-07)

**Goal.** Move the dashboard from "is this site a brownfield?" to "is this site a viable data-center site?" — a scored, persona-filterable view across all ~47k records. Today we have a single Boolean `data_center_reuse_candidate` flag (EPA RE-Powering, ≥50 ac + power + water, ~776 Superfund sites) plus universal `transmission_mi` / `rail_mi` / `highway_mi` distances. The thesis is that post-remediation industrial land with grid + water + fiber + favorable state tax is gold for AI buildouts; this section turns it into an actionable rubric.

**Supersedes** the older "Data Center Opportunity Dashboard (pivot)" section further down. Items marked with **[exists]** are already in this backlog elsewhere — recording them here too so the tier ordering is complete.

### Industry-standard thresholds (anchor for every filter / score)

Sourced from Datacenters.com, LightBox, EPA Brownfields, USPE Global, Equinix, Introl, ASHRAE 169, FEMA P-2192, S&P Global, Ramboll (cited inline in research notes). Encode these as `DC_TIERS` constants:

| Tier | Acreage | Power (HV transmission within) | Voltage class | Water | Climate / risk excludes |
|---|---|---|---|---|---|
| **Edge / inference** | ≥5 ac | ≤1 mi | ≥69 kV | optional (closed-loop OK) | FEMA Zone V; SDC E/F |
| **Colocation / general** | ≥25 ac | ≤1 mi | ≥138 kV | desirable; ≤2 mi to municipal | FEMA Zone A/AE/V; WHP Very High |
| **Hyperscale (100 MW+)** | ≥100 ac (matches EPA threshold) | ≤1 mi | ≥230 kV | required for evap; ≤1 mi or in PWS service area | + WRI Aqueduct BWS ≥3 (high-stress) |
| **AI mega-campus (500 MW+)** | ≥500 ac | ≤1 mi | ≥500 kV OR gas pipeline ≤2 mi (BTM viability) | flexible (closed-loop trend, e.g. Microsoft 2025+) | + non-attainment counties (NAAQS) for backup-gen permitting |

Reference figures: WUE industry avg = 1.8 L/kWh ≈ 276,000 gal/day per MW evap-cooled; rack power 100kW (NVIDIA GB200) → 600 kW (Vera Rubin 2026); typical interconnection-queue wait 5 yr (CAISO 9 yr); buildable share of acreage is 30–40% after buffers.

### ~~Tier 0 — Quick wins (zero new fetches, hours not days)~~ Done 2026-05-07 (PR #3)

All five Tier 0 items shipped together as the v1.12 data-center suitability scoring v0. Audit confirmed 2026-05-08 — 280 unit tests + 5 dedicated e2e tests passing; 250 hyperscale-ready sites surfaced in the live KPI; persona filter narrows the visible set with `?dc_tier=` URL round-trip; DC tier pill + kV chip + tax incentive chip render in the detail panel.

- ~~**[high] Voltage class on the existing transmission proximity result.**~~ Done — `connectors/infra_proximity.py` extracts `VOLTAGE` (Double, kV) with `VOLT_CLASS` fallback via `VOLT_CLASS_TO_KV` map; HIFLD null sentinel `-999999` collapses to None. `transmission_kv` populated on 46,211 / 46,211 records that have `transmission_mi` (100% coverage of in-range sites). Cache key includes `out_fields` so the v1.10 cache (no attributes) doesn't shadow the v1.12 fetch.
- ~~**[high] DC suitability score v0 from existing fields.**~~ Done — `computeDcScore(s)` in [app.js](docs/app.js:327) reads `acreage` + `transmission_mi` + `transmission_kv`, iterates `DC_TIERS` highest-down, returns `null | edge | colo | hyperscale | mega`. Sites without `transmission_kv` cap at edge (≥138 kV unverified). Renders as a `.dc-tier-pill` next to the existing `Cleanup Complete` / `Active Reuse` / `DC candidate` pills; hyperscale+ gets the green `.ready` variant.
- ~~**[high] Static state DC tax incentive lookup table.**~~ Done — `STATE_DC_INCENTIVES` in [app.js](docs/app.js:361) covers all 50 states + DC. **Two-pass audit complete 2026-05-08** — every row now carries `verified_at: "2026-05-08"` with citation-grade URLs (statute / DOR / EDC / NCSL-specific snapshot row). Pass 1 (16 rows): NC threshold $150M→$75M, OH payroll floor, CT thresholds, FL HB 7031, IA 2025 rollback, MN→Tier 3 / `partially_repealed`, UT→Tier 2, OK `under_reform`, AR Act 548, CO `pending_legislation`. Pass 2 (35 rows): TN $250M→$100M, IL sunset 2029→2056, WI/IN/PA/MD/MS/KY/WV/WA/WY thresholds + dates filled, NY/ME promoted to Tier 2 (real statutory programs), AK status `none`→`no_state_sales_tax`. Three statuses wired through (`partially_repealed`, `pending_legislation`, `restrictive`); Tier 3 metaText branch prefers row-specific `program` strings. The "Tier 1 incentive states only" *filter facet* was scoped out — per-state filter already lets users hit it directly; revisit if a user requests bulk-tier filtering.

- **[med] Annual Q2 re-audit of `STATE_DC_INCENTIVES`.** DC tax legislation moved through 30+ states in early 2026; the cadence is faster than this dashboard's release cycle. Schedule the next audit for ~2027-Q2 (after most state legislative sessions close) to catch threshold changes, sunsets, and tier moves. Process: walk every row, re-confirm against its `url` + cross-check against the [NCSL snapshot](https://www.ncsl.org/fiscal/policy-snapshot-data-center-incentives) + [Stateline tracker](https://stateline.org/2026/02/24/data-center-tax-breaks-are-on-the-chopping-block-in-some-states/), bump `verified_at` everywhere or correct the row. Should take ~2 hours since URLs are now primary-grade. Watch list (rows likely to drift first): VA (`under_reform`), FL (`under_reform`), OK (`under_reform`), ME (`under_reform`), CO (`pending_legislation`), PA (`under_reform`), WV (recently expanded — could re-tier).
- ~~**[high] Persona filter presets in the filter UI.**~~ Done — four buttons (Edge/Colo/Hyperscale/AI mega) in `#f-personas`, generated from `PERSONA_PRESETS = [...DC_TIERS].reverse()` so future tiers drop in via the same drift-safe legend-iteration pattern as `PROGRAM_LEGEND` (UAT-007 lesson). Click toggles `filterState.dcTier`; debounced `syncUrl()` writes `?dc_tier=` (200ms after click). Reset clears it. The acreage slider stays independent — persona filter narrows by *computed score*, not by mutating `minAcreage`.
- ~~**[high] KPI cell: hyperscale-ready count.**~~ Done — `#kpi-hyperscale` in [index.html](docs/index.html:72), computed from in-memory `sites` post-lazy-load; 250 sites at audit time. Subtext: "≥100 ac · ≥230 kV · ≤1 mi" (drops the "water service area" wording since the score doesn't currently gate on water — that was a v0 simplification, revisit when Tier 1 layers land).

### Tier 1 — High-signal new layers (1–2 days each)

Each adds one connector or extends `infra-proximity`. All free, no auth (or instant free-tier signup).

- ~~**[high] HIFLD natural-gas pipelines → `gas_pipeline_mi`.**~~ Done 2026-05-08 (v1.13) — extended `connectors/infra_proximity.py` with a fourth layer (`Natural_Gas_Interstate_and_Intrastate_Pipelines_1` on `services2.arcgis.com/FiaPA4ga0iQKduv3`, ~33k polylines, page_size 2000). Same `SegmentIndex` machinery as transmission/rail/highway; one new schema field `gas_pipeline_mi: Optional[float]`; one new detail-panel row (Gas pipeline). NGL (natural-gas-liquids) layer intentionally excluded — DCs want methane for BTM turbines, not propane. Per-layer skip via `--infra-skip-gas-pipeline`. **Doesn't yet feed the DC scoring tiers** — Tier 0 `computeDcScore()` still gates on transmission only; future work could add `<2 mi` gas-pipeline threshold for hyperscale tier (Stargate Texas pattern). 2 new unit tests + 1 e2e test cover the new layer.

- ~~**[high] EIA Atlas → `iso_rto` region attribution.**~~ Done 2026-05-23 — new `connectors/iso_rto.py` enrichment connector assigns lower-48/DC sites to PJM / MISO / ERCOT / CAISO / SPP / NYISO / ISO-NE or `non-RTO` via point-in-polygon against EIA/HIFLD RTO polygons (official EIA Atlas item is anonymous-permission-blocked; connector uses a public ArcGIS mirror with the same EIA fields and cites EIA/HIFLD as source). Output: `docs/data/iso-rto.json` with 45,051 records; 1,709 AK/HI/territory records intentionally outside source scope. Frontend lazy-loads it, shows ISO/RTO in the detail panel, adds an ISO/RTO filter facet with `?iso_rto=...` URL state, and includes `iso_rto` in CSV export. Regression tests cover connector normalization/merge behavior plus detail-row render and filter-facet behavior.

- ~~**[high] FEMA National Risk Index (NRI) → composite climate-risk fields.**~~ **Done 2026-06-08 (v1.19).** Built `connectors/fema_nri.py` (`run_order=360`) at **county** resolution (not tract — county is sufficient for the DC-siting penalty and avoids the tract-TIGER-polygon dependency the original note worried about). Source pivot: the bulk CSV + `hazards.fema.gov/nri` portal 301-redirect post-2025, so the connector point-in-polygons against the **FEMA NRI county FeatureServer on ArcGIS Online** (`services.arcgis.com/XG15cJAlne2vxtgt/.../National_Risk_Index_Counties`, 3,232 polygons) — fetches geometry + risk attrs together (reuses `PolygonIndex`, no FIPS join). Schema: `nri_risk_score` (0-100 composite), `nri_risk_rating`, `nri_wildfire_rating`, `nri_drought_rating`, `nri_heatwave_rating` (official FEMA buckets, carried verbatim). 35,783 / 46,760 matched. Scoring: `_climatePenalty()` — MAX(wildfire, drought) severity → −10 (Very High) / −5 (Relatively High), separate subtractive term so weight tables stay at 100; heat wave displayed not penalized. UX: detail-panel row + red climate note + "Climate −N" suit chip + 4 CSV columns. 8 unit + 3 e2e tests. **Decision vs the original spec**: kept composite + 3 DC-relevant hazard *ratings* instead of all-hazard *EALT dollars* — ratings are display-ready and the re-weighting flexibility the EALT approach promised isn't needed for a binary penalty. Revisit EALT/tract-level only if a user wants fine-grained hazard re-weighting.

- **[high] USGS seismic API → `sdc` (A–F).** Source: `https://earthquake.usgs.gov/ws/designmaps/asce7-22.json?latitude=...&longitude=...&riskCategory=III&siteClass=D`. Returns SDS, SD1, and the derived SDC. Per-site live REST, ~1 s/call, no key. 47 k sites × 1.5 s = ~20 hr — overnight enrichment connector. Use Risk Category III (DCs are "substantial hazard to life on failure"), Site Class D default. Threshold: SDC ≥ D = significant structural cost premium; SDC ≥ E = often disqualifying. New `connectors/usgs_seismic.py`, `run_order=320`.

- ~~**[high] ASHRAE climate zone → `climate_zone`.**~~ Done 2026-05-23 — new `connectors/climate_zone.py` enrichment connector assigns IECC / ASHRAE-style county climate zones (`5B`, `3A`, etc.) from the DOE / PNNL Building America county FeatureServer. Output: `docs/data/climate-zone.json` with 45,543 records; 1,217 sites outside the county polygon layer are skipped. Frontend lazy-loads it, shows Climate zone in the detail panel, and includes `climate_zone` in CSV export. Implementation note: the source advertises 2,000-record pages but intermittently 504s on geometry-heavy pages, so the connector uses 500-record pages and keys cache by page size.

### Tier 2 — Medium-signal new layers (3–5 days each)

- **[high] Audubon OSM substations → `substation_mi`.** HIFLD substations have been auth-walled since 2022 (DHS/CEII) and the HIFLD Open portal shut down 2025-08-26. Free alternative: Audubon ArcGIS Hub publishes an OSM-derived substations FeatureServer at `https://data-library-audubon.hub.arcgis.com/content/7ddd8bf991eb483d8f172fda75903b1b`. Filter to `voltage ≥ 69000` (HV-only). Coverage ~70–80% of US HV substations (vs. legacy HIFLD's ~99%) — document as a known gap. Backup: OSM Overpass API direct query, rate-limited, tile by state. Add to `infra-proximity.json` as a fourth `SegmentIndex` (point-to-point, not polyline).

- **[high] LBNL Queued Up + `gridstatus` → queued MW within 50 mi.** Source (a) LBNL Queued Up 2025 Edition annual Excel at `https://emp.lbl.gov/queues` — project-level rows from 7 ISO/RTOs + 49 non-ISO BAs (~97% US capacity), county/state-level. Source (b) `gridstatus` Python lib (Apache 2.0, `pip install gridstatus`) — live `iso.get_interconnection_queue()` for CAISO / MISO / ERCOT / NYISO / PJM / ISO-NE / SPP. NYISO/PJM/MISO ship lat-lon; CAISO/ERCOT/SPP are county-only. Aggregate to `queued_mw_50mi` per site. Use LBNL for non-ISO regions, gridstatus for ISO regions. New `connectors/queue_capacity.py`, `run_order=310`. **MW available is the actual gating factor for DC siting** — stronger signal than "is there a wire nearby."

- **[high] EIA Form 861 + HIFLD service territory → `electricity_rate_cents_kwh`.** Two-step: (a) HIFLD `Electric_Retail_Service_Territories` (NASA mirror at `https://maps.nccs.nasa.gov/mapping/rest/services/hifld_open/energy/FeatureServer/26` — the most reliable post-HIFLD-shutdown endpoint). Polygons keyed by `ID` (matches EIA `Utility_Number`). (b) EIA Open Data API `electricity/retail-sales` — `https://api.eia.gov/v2/electricity/retail-sales/data?api_key=<KEY>` with free key (instant signup). Cross-walk: site lat/lon → service-territory polygon → `Utility_Number` → EIA industrial-sector rate. Fall back to state-average industrial rate when polygon coverage misses. New `connectors/utility_rates.py`, `run_order=330`. Industrial rates are the right sector — not residential.

- **[med] NOAA NCEI 1991-2020 climate normals → `cdd65` / `hdd65`.** Bulk CSV download at `https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020/` — ~7,300 stations with `ANN-CLDD-BASE65` field. IDW point-sample to site lat/lon using 5 nearest stations. Tiers: CDD<2,000 = excellent (Pacific NW, Upper Midwest); 2,000–3,500 = moderate; >3,500 = poor (Sun Belt). New `connectors/noaa_normals.py`, `run_order=340`. ~10 MB compressed cache. HDD comes free in the same product.

- **[med] FEMA NFHL flood zones → `flood_zone`.** Source: `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer` layer 28 (Flood Hazard Zones). Per-site `intersects` query returns `FLD_ZONE` (`A`/`AE`/`AH`/`AO`/`A99`/`V`/`VE`/`X`/`D`). Excludes A/AE/AH/AO/V/VE for hyperscale (1% annual chance — Special Flood Hazard Area). ~25% of CONUS isn't NFHL-mapped → null is informative ("unmapped"), not a clear pass. Per-site live REST, overnight enrichment job for 47 k records. Apply the **TIGERweb page-size quirk** rule: `page_size=1000` with geometry. New `connectors/fema_flood.py`, `run_order=350`.

- **[med] USFS Wildfire Hazard Potential 2023 raster → `wildfire_class`.** Source: `https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential` — 270 m raster, 5 classes (Very Low → Very High). Bulk GeoTIFF (~1 GB) + `rasterio.sample()` is faster than per-site REST `identify` (which would be 47 k × 1.5 s = 20 hr). Use the GeoTIFF path. Threshold: exclude class 5 (Very High); flag class 4 (High) for hardened design. ~8% of CONUS land in classes 4–5. Will need to add `rasterio` to `requirements.txt` — first non-pure-Python dep; flag for review. CONUS-only (skip AK/HI).

- **[med] WRI Aqueduct 4.0 baseline water stress → `water_stress_score`.** Source: `https://www.wri.org/data/aqueduct-water-risk-atlas` — HydroBASINS sub-basin polygon shapefile, ~80 MB. Field `bws_score` (0–5 categorical). Threshold: `≥3` (>40% withdrawal/supply ratio) = high-stress flag, exclude or require closed-loop cooling. Carry 2030/2040 projections too — they're free with the baseline pull. Reuse `connectors/spatial.py` polygon point-in-polygon pattern. **Crucial for the AI mega-campus tier** since they're ~1–5 M gal/day each. New `connectors/wri_aqueduct.py`, `run_order=325`.

- **[med] EPA AQS PM2.5 county aggregate → `pm25_ugm3`.** Source: `https://aqs.epa.gov/aqsweb/airdata/download_files.html` — pre-aggregated `annual_conc_by_monitor` CSV per year, ~20 MB. Aggregate by county, average over last 3–5 years. Threshold: EPA NAAQS annual standard 9 µg/m³ (lowered 2024). Flag counties >12 µg/m³ as "outside-air economizer needs significant filtration." For unmonitored counties, use nearest-monitor IDW or flag as "unmonitored." New `connectors/epa_aqs.py`, `run_order=345`. Same county-FIPS join pattern as ASHRAE zone.

- **[med] EPA Green Book NAAQS attainment → `attainment_status`.** Source: `https://www.epa.gov/green-book/green-book-gis-download` — per-pollutant zipped Shapefiles + PHISTORY CSV. Per-county nonattainment status by pollutant. **Crucial for backup-generator permitting** (non-attainment counties trigger NSR for new generator stacks → multi-month permit drag). New `connectors/epa_greenbook.py`, `run_order=345`. Tiny dataset; trivial county join.

### Tier 3 — Composite scoring + UI rebuild (after Tier 1+2 lands)

- **[high] `compute_dc_score(s)` v1 — weighted multi-criteria score.** ~~Replace the v0 frontend score with a weighted rubric.~~ **Substantially done 2026-05-31 (v1.14)** — [dc-score.js](docs/dc-score.js) rewritten into two pure/deterministic weighted lenses, `computeDcCompositeScore` (data-center load) + `computeGenerationScore` (new generation), both 0–100 with a `*Breakdown()` companion so the detail panel shows *why*. The DC score now consumes substation + power-plant + a SFHA flood penalty (the v1.13.3 signals that were on disk but unused). Each weight table sums to exactly 100; flood is a separate −18 subtractive term. **Still open**: the *intra-DC* persona presets the original item listed (`hyperscale_default` / `ai_mega_campus` / `edge_inference` / `crypto_hpc` weight dicts) — see the "Persona filter UI" item below; the component scorers already take a `cap` arg, so a persona becomes just a weight dict passed into a `(site, weights)` shape. Inputs the original rubric wanted but which still aren't on disk (water stress, FEMA NRI climate risk, SDC) are gated on the Tier 1/2 layers landing.

- ~~**[high] Detail panel "Data Center Suitability" section.**~~ Done 2026-05-31 (v1.14) — `#d-suitability-block` ("Siting suitability", between the tax-incentive and infra blocks, `open` by default) rendered by `renderSuitability(s)`. Shows both lenses as tier-colored 0–100 score meters with grouped breakdown chips (Power access / Land / Gas / Logistics / Readiness for DC; Land / Grid export / Gas / Market / Readiness for generation) and a red SFHA deal-blocker note when `in_sfha === true`. Synthesizes rather than field-dumps. Didn't use the tab-strip pattern — the two-meter block is compact enough to sit inline above the raw infra rows it summarizes. Future: add ISO/RTO queue MW + FEMA NRI climate-risk rows as those layers land.

- **[high] Persona filter UI.** Above the persona-tier buttons from Tier 0, add a "Profile" dropdown: `Hyperscale (default)` · `AI mega-campus` · `Edge / inference` · `Crypto / HPC`. Switching the profile recomputes scores for all sites and re-renders the table sort. URL state: `?profile=ai_mega`. Default profile from `localStorage` so a returning user keeps their persona.

- **[med] Map: filled markers for top-quartile DC scores.** Tier 1 hyperscale-ready sites get a filled circle with a halo; sub-tier sites stay as the existing dot. Don't add a new color — use the existing program color but add a 2px outer stroke. Drives "where in the US is the dense set of viable sites" at a glance. Implement only after Tier 1+2 layers land.

- **[med] KPI deck: 4-cell DC view.** Replace one of the existing KPI cells (probably `#kpi-states`) with `#kpi-power-ready` (count of sites within 1 mi of ≥230 kV transmission), `#kpi-water-ready` (count near a water source for evap or in PWS service area), `#kpi-tax-tier1` (count in Tier 1 incentive states). Hyperscale-ready remains as `#kpi-hyperscale` (Tier 0).

### Tier 4 — Nice-to-have / advanced (defer until users request)

- **[low] USGS NHD water bodies → `water_body_mi`.** For evap-cooling proximity (vs. PWS service area). NHD HighRes is enormous; the right cut is `NHDWaterbody` filtered to `FType=390` (LakePond) AND `AreaSqKm > 1.0`, plus `NHDFlowline` filtered to perennial streams (`FCode IN (46006, 55800)`). Bulk download by HUC-4. NHD itself was retired 2023-10-01 — data still available, future updates flow through 3DHP. Useful for the AI mega-campus tier but also genuine source-of-truth complexity (millions of features). Defer until evap-cooling proximity becomes a binding filter.

- **[low] EPA Community Water System Service Area Boundaries → `pws_service_id`.** Source: `https://www.epa.gov/ground-water-and-drinking-water/community-water-system-service-area-boundaries` — EPA released a national modeled dataset in 2024 covering ~44 k CWS systems (~99% of CWS-served population). Polygon shapefile keyed by federal `PWSID`. Stronger signal than "near a water main" because PWSID also lets us cross-walk SDWIS for capacity / violation data. The existing `near_water_supply` Redev field is a Superfund-only buckets ("Yes — 1 mile") proxy; this would be a precise replacement for all programs.

- **[low] FAA airports → `airport_dist_mi`.** Source: `https://adds-faa.opendata.arcgis.com/` — Airports + Runways layers, free, no auth. Filter `Runways.LENGTH > 3200` ft; flag sites <3 mi from a qualifying runway endpoint (FAA Part 77 imaginary-surface conflict — cooling tower / gen-set exhaust triggers Form 7460-1 review). Low priority because most contaminated industrial sites are already away from active airports; mostly a flag-not-exclude field.

- **[low] NREL NSRDB → `solar_ghi_kwh_m2_day`.** Source: `https://developer.nrel.gov/docs/solar/nsrdb/nsrdb_data_query/` — free API key, ~1000 calls/hr. Threshold `>5 kWh/m²/day` annual GHI = solar-attractive. Only matters if the dashboard claims behind-the-meter PPA viability. Defer.

- **[low] NREL Wind Toolkit → `wind_cf_pct`.** Source: `https://developer.nrel.gov/docs/wind/wind-toolkit/` — same key. Threshold `>35%` 100 m hub-height capacity factor = wind-attractive (Great Plains corridor IA→TX). Defer with NSRDB.

- **[low] PeeringDB IXP locations → `ixp_dist_mi` (fiber proxy).** Source: `https://www.peeringdb.com/api/ix` — free anonymous read, ~120 US IXPs with `latitude`/`longitude` on linked `fac` endpoint. Proxy for "fiber-rich metro" since IXPs sit at major carrier hotels. Not a real long-haul fiber map but the best free proxy — the cleanest public layer doesn't exist (GeoTel / FiberLocator are paid-only, ~$5–25 k/yr). Pair with FCC BDC fiber-served address density per H3 cell for a second proxy.

### Tier 5 — Defer / no clean public source

- **Long-haul fiber routes.** No clean public layer. GeoTel / FiberLocator / NA Fiber Map are paid. Best free proxies are PeeringDB IXP + FCC BDC last-mile (above). Don't promise fiber proximity until at least one paid source is funded.
- **Real-time available transmission capacity (FERC OASIS).** Fragmented across per-provider portals with no central bulk API. FERC Form 715 is CEII-restricted. Both are dead ends. Use queued-MW proxy via LBNL + gridstatus (Tier 2) instead.
- **Water rights (Western US).** State-by-state, no machine-readable national source. Defer until a single-state customer pilot funds the per-state work.
- **Local zoning / land use.** Most counties don't publish machine-readable zoning. The "manual-check-needed" item already in the older "Data Center Opportunity Dashboard (pivot)" section stays accurate.
- **Anticipated Future Land Use (AFL) codes.** Already confirmed dead end 2026-05-05 — SEMS-internal field, FOIA-only.

### Suggested implementation order

A two-week MVP path that turns this into a usable scoring view:

1. **Week 1 — Tier 0 + start Tier 1.** Voltage-class extension, frontend score v0, state-incentive lookup table, persona filter buttons, hyperscale KPI cell. Then `gas_pipeline_mi` (HIFLD reuse), `iso_rto` (EIA Atlas point-in-polygon), ASHRAE zone (county-FIPS lookup). All zero-paid-deps; the FEMA NRI bulk pull starts overnight.
2. **Week 2 — Finish Tier 1.** USGS seismic API enrichment (overnight job), FEMA NRI tract-level fields, detail panel `#d-dc-block` v1 surfacing everything that landed. Stop here for a release; ship the scoring as v1.12.
3. **Following sprint — Tier 2.** Audubon substations, LBNL queue capacity, EIA utility rates, climate normals. Add `compute_dc_score` v1 with weighted rubric and persona presets.
4. **Defer Tier 3 UI rebuild** until Tier 2 lands — designing the detail-panel section before the full data is on disk would force rework.

### Schema additions

Add to `SiteRecord` in `schema.py` (all optional / nullable — `extra="forbid"` keeps drift loud):

```python
# Tier 0 — voltage class on existing transmission proximity
transmission_kv: float | None  # nominal kV of nearest HIFLD line; null when source is null

# Tier 1 — high-signal layers
gas_pipeline_mi: float | None        # miles to nearest HIFLD natural-gas pipeline
iso_rto: str | None                  # PJM | MISO | ERCOT | CAISO | SPP | NYISO | ISO-NE | non-RTO
sdc: Literal["A", "B", "C", "D", "E", "F"] | None  # USGS ASCE 7-22 Seismic Design Category
climate_zone: str | None             # ASHRAE 169 zone, e.g. "5B" / "3A"

# FEMA NRI — composite climate-risk per hazard (annualized expected loss in USD)
nri: dict | None                     # {hurricane_ealt, tornado_ealt, wildfire_ealt, drought_ealt,
                                     #  earthquake_ealt, hail_ealt, ...} — frontend re-weights for DC

# Tier 2 — medium-signal layers
substation_mi: float | None          # miles to nearest HV (≥69 kV) substation (OSM/Audubon)
queued_mw_50mi: float | None         # MW queued for interconnection within 50 mi (LBNL + gridstatus)
electricity_rate_cents_kwh: float | None  # EIA Form 861 industrial-sector rate
cdd65: int | None                    # annual cooling-degree-days base 65°F (NOAA normals)
hdd65: int | None                    # annual heating-degree-days base 65°F
flood_zone: str | None               # FEMA NFHL FLD_ZONE; null = unmapped (informative)
wildfire_class: int | None           # USFS WHP 2023 class 1–5
water_stress_score: int | None       # WRI Aqueduct BWS 0–5
pm25_ugm3: float | None              # 5-yr average PM2.5 from EPA AQS
attainment_status: dict | None       # per-pollutant: {ozone: "attainment", pm25: "nonattainment", ...}

# Tier 3 — derived / score
dc_score: int | None                 # 0–100, computed at runtime from the above
dc_tier: Literal["edge", "colo", "hyperscale", "mega"] | None  # derived bucket
```

### Frontend constants to add (single source of truth)

In `app.js`:
- `DC_TIERS` — the threshold table from the top of this section.
- `STATE_DC_INCENTIVES` — full 50-state + DC lookup.
- `PERSONA_WEIGHTS` — per-persona weight dict for `compute_dc_score`.
- `ISO_RTO_LABELS` — display labels for `iso_rto` values.

All are static; no fetches. `READINESS_LEGEND` pattern (Reset handler iterates the legend, UAT-007) applies — when a new persona ships, `Reset` and `populateProfileFilter` pick it up for free.

### Cost summary

Everything in Tier 0–2 is **free, no auth or one-time free signup**. Two paid fallbacks flagged for later:
- Regrid / Landgrid Parcel API (~$0.001–0.01 / parcel) for owner data — already in backlog.
- GeoTel / FiberLocator (~$5–25 k/yr) for true long-haul fiber routes — only if a paying customer cites fiber as a binding filter.

The single new dep introduced: **`rasterio`** (for USFS WHP raster sampling, Tier 2). First non-pure-Python connector dep — flag for review when the PR lands. WRI Aqueduct, FEMA NRI, NHD all stay in the existing `connectors/spatial.py` polygon pattern with no new C extensions.

---

## ~~Static summary quality pass (audited 2026-05-05)~~ Fixed 2026-05-05

Systematic review of all 1,787 generated static summaries found 9 recurring issues. Grouped by impact — fix the HIGH items before re-running at scale.

> **All five HIGH items below fixed in v1.11.3 AND now regression-guarded (2026-07-11).** Verified the fixes are live in `connectors/ai_summary.py` (`_title_word()` regex, `_STOP_WORDS`, `_pretty_token()` `.endswith(".")` acronym disambiguation, the `fa or penalties` enforcement gate, the vowel-aware `"an"` article) and added five dedicated regression tests to `tests/test_ai_summary.py` (`test_pretty_text_apostrophe_possessive_not_uppercased`, `test_pretty_text_prepositions_lowercased`, `test_pretty_text_company_abbrev_not_state_code`, `test_static_summary_lead_uses_an_for_vowel_program_label`, `test_static_summary_suppresses_clean_compliance_noise`). 31/31 pass. The bullets below are retained for the audit trail.

**~~[high] Apostrophe title-case bug — 20 sites.~~** ✓ Done (v1.11.3, guarded 2026-07-11). `str.title()` treats `'` as a word boundary, producing `Beck'S Lake`, `Sigmon'S Septic Tank Service`. Replace `w.title()` in `_pretty_text()` with a regex-based variant: split on word-start boundaries only (e.g. `re.sub(r"(?<!['\w])(\w)", lambda m: m.group().upper(), text.lower())`), or use `string.capwords(w)` per word which handles apostrophes correctly.

**~~[high] Prepositions kept uppercase — 87 sites.~~** ✓ Done (v1.11.3, guarded 2026-07-11). The `len(core) <= 2 and core.isupper()` rule in `_pretty_text()` is too broad: it preserves `OF`, `IN`, `AT`, `AN`, `BY`, `TO` (prepositions) the same way it preserves state codes and acronyms, producing `University OF Minnesota`, `Kokomo, IN (Currently on the Final NPL)` mid-sentence, `Town OF Bedford`. Fix: add an explicit `STOP_WORDS = {"of", "in", "at", "an", "by", "to", "for", "the", "and", "or"}` set and lowercase those unconditionally _before_ the acronym/length check. State codes (2-char) should go in `_NAME_KEEP_UPPER` explicitly so the ≤2-char catch-all can be removed.

**~~[high] "CO." kept uppercase — 179 sites.~~** ✓ Done (v1.11.3, guarded 2026-07-11). "Company" abbreviation `CO.` strips to core `CO` which hits the ≤2-char rule and stays as `CO.` rather than becoming `Co.` — looks like the state abbreviation for Colorado. Fix is the same as above: kill the ≤2-char catch-all and whitelist state postal codes explicitly. `CO.` would then fall through to `w.title()` → `Co.` correctly.

**~~[high] "No Violation Identified" noise in enforcement block — 80 sites.~~** ✓ Done (v1.11.3, guarded 2026-07-11). When the only ECHO signal is `current_compliance: "No Violation Identified"` with zero formal actions, zero penalties, and no violation date, the enforcement sentence reads `ECHO enforcement: compliance: No Violation Identified.` — a clean record surfaced as if it were a risk. Fix in `build_static_summary()`: suppress the enforcement block entirely when `formal_actions_5yr == 0` and `penalties_5yr_usd == 0` and `last_violation_date` is null. A clean compliance status is better shown as a brief inline positive note only if ECHO data exists at all (e.g. "No enforcement actions on record (ECHO).").

**~~[high] Grammar: "is a EPA" — 11 sites.~~** ✓ Done (v1.11.3, guarded 2026-07-11). The lead sentence uses `"a"` before `program_label`, but labels starting with a vowel sound ("EPA Superfund", "ARNG", "USCG") need `"an"`. Fix: check `program_label[0].lower() in "aeiou"` in `build_static_summary()` and swap to `"an"` accordingly.

**[med] 0-acre anomaly — 70 sites.** Sites where the source acreage field is literally `0` or rounds to zero produce `a 0-acre EPA Superfund` which looks like a data error. Fix: treat `acreage == 0` the same as `acreage is None` — omit the acreage token entirely and let the sentence read `Genzale Plating Co. is an EPA Superfund (NPL) in Franklin Square, NY (Final NPL).`

~~**[med] "0.0 mi" for adjacent infrastructure — 213 sites.**~~ Done 2026-05-06 (v1.11.4) — `_fmt_distance()` now returns `"adjacent"` when `v < 0.05` and `f"{v:.1f} miles away"` otherwise, with all three infra clauses sharing the same shape. Frontend `fmt.miles()` mirrors the rule (renders `"Adjacent"` so it reads as a value, not placeholder text). 206 of 1,787 static summaries now read `transmission lines adjacent` / `rail adjacent` / `highway adjacent`; zero `on-site` strings remain.

~~**[med] DC reuse parenthetical repeated verbatim on 776 sites.**~~ Done 2026-05-06 (v1.11.4) — trimmed to `"Flagged as a data-center reuse candidate."` in `build_static_summary()`. The criteria still surface in three lower-noise places: the KPI-deck subtext, the legend pill tooltip, and the new detail-panel `.dd-criteria` sub-line (see entry below).

**[low] Status phrasing is verbose — all 1,787 sites.** `"(Currently on the Final NPL)"` is 26 chars; `"(Deleted from the Final NPL)"` is 28 chars. Shorter: `"(Final NPL)"` / `"(Deleted from NPL)"`. Reduces avg summary length ~10 chars with no information loss. Low priority since the text is still correct and readable.

---

## ~~Static summary prose rewrite (2026-05-05)~~ Done

After the 9-issue quality pass, `build_static_summary()` was rewritten from a colon-separated field dump to natural flowing sentences:

- ~~**Lead sentence**~~ Done — "X is a Y-acre Program in City, ST, currently on the Final NPL." (acreage omitted when null or 0; article "a"/"an" correct; NPL status shortened to "Final NPL" / "Deleted from NPL").
- ~~**Infrastructure**~~ Done — "Infrastructure proximity: transmission lines 0.8 miles from the boundary, rail 7.0 miles, and highway 31.9 miles." Oxford-comma-joined via `_join_list()`; "on-site" when `< 0.05 mi` via `_fmt_distance()` (avoids "0.0 miles" display bug). Only infra types with data are listed.
- ~~**DC reuse**~~ Done — "The site meets EPA RE-Powering criteria as a data-center reuse candidate." (parenthetical "(≥50 ac + power + water)" trimmed — criteria visible in legend/panel).
- ~~**Owner**~~ Done — "Current owner: X (per USACE FUDS)." when source provides it.
- ~~**Documents**~~ Done — "N federal documents on file (Category A, Category B, and Category C)." Correct singular/plural; Oxford-comma list.
- ~~**Enforcement**~~ Done — "EPA ECHO records show N formal enforcement actions in the past 5 years and $X in penalties." Block suppressed entirely for clean records (zero formal actions + zero penalties).
- ~~**Disclaimer**~~ Done — All summaries end with "AI-generated summary from federal records." so the generated nature is always attributed.
- ~~**Sparse fallback**~~ Done — When no infra/docs/enforcement data is available, a natural sentence "No infrastructure proximity, document, or enforcement data is available…" replaces an empty block.
All 1,787 F+D summaries regenerated (964 KB). Helpers extracted: `_fmt_distance(v)`, `_join_list(items)`.

---

## Continue ECHO + docs coverage (2026-05-05+)

The v1.11.2 commit fixed the ECHO connector and shipped 380 of 1,787 Final/Deleted Superfund sites with enforcement data. Batches 2–5 (2026-05-05/06) added 796 more sites, bringing ECHO coverage to **1,176/1,787 (65.8%)**; subsequent runs completed ECHO at **1,787/1,787 (100%)**. A parallel docs backfill is now at **1,594/1,787 (89.2%)** as of 2026-05-31 (the docs data file reflects this even though the prior backlog prose lagged at 1,410 — corrected here during the 2026-05-31 branch reconciliation). Continued docs coverage is gated by upstream API throttling, so this is staged work, not a single sprint:

- ~~**[high] Continue ECHO backfill.**~~ Done — ECHO coverage is now 1,787/1,787 F/D Superfund sites. (The 2 missing Superfund sites confirmed 2026-06-04 — `SCN000407376` Henry's Knob and `UT0008921894` Bountiful 5 Points PCE Plume — have no ECHO match because they're not in EPA's ECHO facility database; not backfillable.)
- ~~**[high] Continue docs backfill (193 eligible sites remaining).**~~ Effectively done 2026-06-04 — F/D coverage is now 1,772/1,787 (99.2%). The 15 remaining sites are structural dead-ends: their EPA pretty pages either return HTTP 404/500 or have no `csitinfo.cfm?id=` link to follow, so the SF_SITE_ID hop can't resolve. These won't move without an upstream EPA fix (or a different identifier discovery path). Re-running `--missing-only` does no harm but adds nothing new.
- **[med] Regenerate ai-summary after each docs batch.** Static summaries are cache-aware (`_fingerprint()` hashes the enrichment fields). Run `python3 refresh.py --source ai-summary --ai-static --ai-status F,D --ai-limit 0` after each batch; only sites whose ECHO/docs data changed will be regenerated (~3–5 s total in static mode). Already done: 1,787 sites include enforcement context; 1,594 sites now have document-aware summary context.
- **[low] ECHO non-Superfund coverage.** The connector currently only enriches Superfund records (`run_order = 250` reads `superfund-npl.json`). FUDS / ACRES / BRAC sites don't have an EPA_ID equivalent for ECHO's `p_pid` filter — would need a name + state fuzzy match (`p_fn` + `p_st`) which is unreliable. Defer until an actual user asks for non-Superfund enforcement data.

---

## Coverage audit findings (2026-06-04)

A pass over every enrichment file's coverage vs. its target scope. Each remaining gap is either a structural source-side dead-end or a connector-improvement opportunity. Captured here so a future audit doesn't re-discover from scratch.

- **[med] Climate-zone coastal-site gap (766 lower-48 sites).** `climate-zone.json` covers 45,543 / 46,759 (97.4%). The 1,217 skipped sites split as: 451 in genuinely-out-of-scope territories (AK 209, HI 53, GU 61, PR/VI/MP/AS, etc. — no Building America county polygon coverage) **plus 766 in lower-48 states** (top: FL 139, TX 86, WA 60, CA 59, MA 58, NY 58, ME 53, NJ 46, RI 40, MD 29). These are coastal / island / harbor sites whose coordinates fall just outside the nearest county polygon (point-in-polygon test fails by tens of meters). Fix: extend `connectors/climate_zone.py` to fall back to "nearest county polygon within ~1 km" when point-in-polygon misses, matching the spatial-tolerance pattern `connectors/county_lookup.py` could be extended with. Same connector improvement would lift the ~99.5% ACRES county-fill rate too.
- **[low] iso-rto + climate-zone tombstones for out-of-scope sites.** Today these connectors emit records ONLY for sites that fall inside their source polygons; out-of-scope sites (e.g. AK for iso-rto) leave no record on disk. Means every `--missing-only` re-run does the full source-index build for sites that have zero chance of ever resolving. Same pattern infra-proximity adopted in v1.11.5: emit `{id, program}` tombstones so the ID set is the source of truth for "we tried." Per-connector ~10-line change in `fetch_records()`. No frontend changes required — both surfaces already render `null` as a graceful absence.
- **Confirmed dead-ends (do not re-attempt without upstream source change):**
  - **15 F/D Superfund sites missing docs** — all 15 have either HTTP 404/500 on the EPA pretty page or no `csitinfo.cfm?id=` link to extract SF_SITE_ID from. Examples: NEWBEDFORD, WYCKOFF-EAGLE-HARBOR, COLORADO-SMELTER, BONITA-PEAK, LOWER-NEPONSET. EPA needs to fix the upstream pages.
  - **2 Superfund sites missing ECHO** (`SCN000407376` Henry's Knob, `UT0008921894` Bountiful 5 Points PCE Plume TCRA) — no ECHO facility match by EPA_ID.
  - **1,709 sites outside lower-48/DC iso-rto scope** — AK 821, HI 457, PR 249, GU 62, MP 53, AS 33, VI 31, PW 2, FM 1. Two PW (Palau) records are the only "lower-48-state-coded" ones, and Palau is genuinely outside the lower-48; the state field is just sentinel-like. No RTO coverage exists for these regions, period.

---

## ~~Frontend / UX — reducing clickthroughs to good sites (2026-05-11 UAT)~~ Done 2026-05-11

All seven items shipped together. Verified in the preview against the worktree's `docs/`.

- ~~**[high] KPI cells as one-click filter shortcuts.**~~ Done — `wireKpiClicks()` in [app.js](docs/app.js) makes the two actionable KPI cells (`data-kpi="hyperscale"` and `data-kpi="dc"`) into `role="button"` toggles with keyboard activation. Clicking Hyperscale sets `filterState.dcTier = "hyperscale"` + syncs the persona button + applies the filter (verified: 250 sites in `search-count`). Clicking DC candidates flips the new `filterState.dcCandidate` boolean (verified: 821 sites). The three overview cells (total / acreage / states) stay non-actionable. `.kpi-actionable` + `.kpi-active` CSS show the engaged state. `Reset` clears both via `refreshKpiActiveStates()`.

- ~~**[high] Search typeahead dropdown.**~~ Done — `#search` is now a `combobox` paired with `#search-typeahead` (`role="listbox"`). Typing ≥2 chars renders up to 8 ranked matches (name-prefix > name-contains > city/state-contains) via the existing `_searchKey` index. Arrow keys navigate, Enter / mousedown / click picks → `window.__selectSite(id)` directly. Escape clears. Verified end-to-end: typing "fox river" → 2 results → click first → Fox River detail panel opens.

- ~~**[med] "Nearby sites" panel in detail view.**~~ Done — new `#d-nearby-block` `<details>` element renders up to 5 sites within `NEARBY_RADIUS_MI = 25` of the selected site, sorted by Haversine distance ascending. Uses `lat_real` / `lon_real` so inset-remapped coords don't pollute. Each result is a styled button → `selectSite(id)`. Pre-filtered by cheap lat/lon-box check (~99% of sites skipped before Haversine). Empty state hidden. Verified: Fox River selection shows "5 of 22 within 25 mi" Wisconsin neighbours.

- ~~**[med] Detail panel remembers active tab within session.**~~ Done — module-level `_lastDetailTab` defaults to `"overview"` and is updated by every tab-button click. `resetDetailTabs()` now reads it instead of hardcoding Overview. Page reload resets. Verified: clicking Summary on site A, then opening site B keeps Summary active.

- ~~**[med] Persona filter active label in filter chip.**~~ Done — `updateFilterChip()` now collects a human-readable string for every active filter (`"search \"fox\""`, `"state California"`, `"Hyperscale (100 MW+)"`, `"DC candidates"`, etc.) and sets the chip's `title` attribute to `"Active: <list>"`. The numeric badge stays for at-a-glance count; the tooltip reveals which filters are engaged. Also updates the `aria-label` on the gear button so screen readers hear the same context.

- ~~**[low] KPI subtext full text on hover.**~~ Done — static-string subtexts (DC criteria, hyperscale criteria, states subtext) got `title` attributes in `index.html`; dynamic-string subtexts (total / acreage) get their `title` updated by `updateKpiDeck()` via a new `setSub()` helper that mirrors `textContent` into `title`.

- ~~**[low] "Copy shareable link" button.**~~ Done — new `#share-link` icon button (⎘) in the topbar between Export and Theme. `wireShareLink()` calls `navigator.clipboard.writeText(window.location.href)` (or the legacy `execCommand("copy")` fallback for non-secure contexts), then fires a toast confirming the copy ("Link copied to clipboard") or a fallback hint ("Couldn't copy link — long-press the address bar instead") if both paths fail.

---

## ~~v1.11.1 — Bug-fix pass + UX polish (2026-05-05)~~ Done

Three defects closed:

- ~~**[high] `?site=FUDS-/BRAC-` showed a premature "not found" toast.**~~ Done 2026-05-05 — `applyUrlSelection()` now `Promise.allSettled`s every in-flight program-data fetch (ACRES / FUDS / BRAC) before declaring an ID unknown; boot order rearranged so the lazy-load promises are populated *before* `applyUrlSelection()` runs. Same drift-risk pattern as the Reset handler (UAT-007).
- ~~**[high] CSV export silently dropped every enrichment field.**~~ Done 2026-05-05 — extracted `CSV_COLUMNS` to a curated 40-field schema mirroring the detail panel (FUDS / BRAC / owner / universal infra distances / EPA RE-Powering qualitative buckets / ECHO enforcement / document count). `pickCsvField()` walks dotted paths (`enforcement.formal_actions_5yr`) and supports a `.length` shortcut for array sizes.
- ~~**[high] Site names rendered ALL CAPS in table, marker tooltip, and detail title.**~~ Done 2026-05-05 — new `prettyName()` helper runs in `ingestSites()` with an EPA/DOD acronym whitelist (NIKE, AFB, NRDA, PCB, USDOE, USACE, USDA, USFS, BLM, NPS, …) seeded from a frequency scan of the dataset. Raw preserved on `s.name_raw`.

Demoted from this pass — call out for future work:

- ~~**[med] Out-of-CONUS infra placeholder.**~~ Done 2026-05-07 (path a) — `setMileCell()` renders `"Remote — outside continental US"` when `s._inset` is truthy. Path b (AK-specific enrichment) still open if a user requests AK-specific infra distances.
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
- ~~**[low] Per-record reasoning for the data-center candidate flag.**~~ Done 2026-05-06 (v1.11.4) — detail panel's "Data center candidate" `<dd>` carries an italicized `.dd-criteria` sub-line (`≥50 acres · electric transmission · water service area`) that shows when the boolean is `true` and stays hidden otherwise. The rule today is the qualitative EPA RE-Powering buckets (`near_electric_transmission` + `near_water_supply` start with "Yes", `acreage ≥ 50`); a future swap to mileage thresholds against the universal `transmission_mi` / water-body data would change only the criteria string.

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
  - **Federal civilian real property** ([GSA FRPP Public Dataset](https://catalog.data.gov/dataset/fy-2024-federal-real-property-profile-frpp-public-dataset)) — annual XLSX (no REST API) of all federal civilian real estate by agency: ownership status (`Owned` / `Leased` / `Other`), use code, square footage. **DOD assets excluded for security** — the DOD file is installation-level summaries only, not parcel-level. So this *won't* help BRAC/FUDS at parcel resolution but *will* help when we add federal civilian contaminated sites (DOE legacy, NRC, GSA-controlled). Contact: `publicfrppdata@gsa.gov`. Active listings (for-sale federal properties): `realestatesales.gov` — HTML-only, no API. Confirmed limitations 2026-05-05.
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

- **"Construction Complete" (CC) milestone** — SEMS milestone date: cleanup work is physically done, deletion paperwork underway. Typically 1–5 years before formal NPL Deletion. Source: **cumulis.epa.gov schedule page** (`fuseaction=second.schedule&id=<SF_SITE_ID>`) — confirmed as the only public surface for CC date, SWRAU date, and all FYR dates. `sems.epa.gov/rest/` is dead (connection refused); Envirofacts `sems.*` tables HTTP 500 in practice. One additional HTTP request per site after the SF_SITE_ID hop that `epa_superfund_docs.py` already does. New `epa_sems_milestones.py` enrichment connector; set `run_order = 210` (after `epa-acres`, before `epa-echo`).
- **"Ready for Anticipated Use" (RAU)** — EPA's per-Operable-Unit formal determination that the site can support its planned future use. A site can be RAU while still on the NPL (e.g., if cleanup continues in one corner but the main parcel is cleared). RAU date published in SEMS and in the EPA site-profile Redevelopment tab. More granular than NPL Deletion — distinguishes partial vs. whole-site readiness.
- **BRAC LIFOC (Lease in Furtherance of Conveyance)** — federal government leases land to a developer while cleanup finishes; deed transfer on completion. Developer can start site planning and sometimes vertical construction. Lease start date = actionable now for sophisticated acquirers. Source: same per-Service PDF scrape as the full BRAC item.
- **ACRES assessment complete, cleanup not started** — brownfields where environmental assessment is done (contamination scope known, cost estimate in hand) but cleanup hasn't started. These are "developer-fundable cleanups" — the acquirer funds remediation as part of the deal. `ACRES_assessments_*` layer `Assessment_Completion_Date` populated + no `Cleanup_Completion_Date` = this tier.

**Tier 3 — "Long pipeline": cleanup ongoing or not yet scoped**

- **FUDS "Eligible" + `has_projects = true`** — USACE is actively investigating or cleaning. Timeline unclear but progressing. At 8,822 FUDS records with 2,874 having active projects, this is a large pipeline pool.
- **NPL status "F" (Final, active)** — on the NPL, cleanup underway. Wide range from years-to-completion to decades.
- **NPL status "P" (Proposed)** — newly proposed, cleanup not yet started.

### Anticipated future land use — what the site will be used for when ready

- **EPA SEMS AFL (Anticipated Future Land Use) code** — per-site code set by EPA project manager: `Industrial/Commercial`, `Recreational/Open Space`, `Residential`, `Unknown`. **AFL codes are not in any public API or FeatureServer** (confirmed 2026-05-05 — not in `RedevelopmentAppSitePoints`, not in `envirofacts_site`, not in cumulis HTML). SEMS-internal field, FOIA-only. Drop from `epa_sems_milestones.py` scope; remove from `anticipated_land_use` schema field. The cumulis schedule page does not carry AFL. If AFL data is ever needed, file a FOIA request for a SEMS bulk export.
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

- **[high] cumulis schedule page scrape for Superfund milestones.** `sems.epa.gov/rest/` is dead; Envirofacts `sems.*` HTTP 500 in practice — confirmed 2026-05-05. The only public structured surface for CC date, SWRAU date, and FYR dates is the cumulis schedule page: `https://cumulis.epa.gov/supercpad/SiteProfiles/index.cfm?fuseaction=second.schedule&id=<SF_SITE_ID>`. New `epa_sems_milestones.py` enrichment connector (`run_order = 210`): reuse the SF_SITE_ID extraction hop that `epa_superfund_docs.py` already does (or share the mapping if that connector has cached it), then one `http_get_text` call per site and regex-extract the milestone table rows. Emits `docs/data/sems-milestones.json` with `[{epa_id, construction_complete_date, swrau_date, fyr_dates: [...]}]`. Join client-side in `ensureSemsLoaded()`. Drop AFL code from scope — it's not publicly available. Resumable via `--milestones-limit N --milestones-status F,D`.

- **[high] cumulis redevelopment tab scrape for reuse data.** Confirmed URL: `https://cumulis.epa.gov/supercpad/SiteProfiles/index.cfm?fuseaction=second.redevelop&id=<SF_SITE_ID>` (not at `epa.gov/superfund/[slug]` — the EPA pretty page just links through to cumulis). Carries: businesses on site, economic summary, reuse description (sparse, often just a paragraph). A separate `epa_superfund_redev.py` connector (`run_order = 215`); cache by `(epa_id, "redevelop_tab")`. Drop AFL description from scope — it's only in the SEMS-internal AFL code field, not on any public page. Output: `docs/data/epa-redev-tab.json` with `[{epa_id, in_reuse: bool, reuse_description: str, reuse_businesses: int, reuse_revenue_usd: int}]`. The `In_Reuse` boolean is already in `RedevelopmentAppSitePoints` (field `In_Reuse = "Yes"/"No"`) — surface that zero-fetch quick win first before building the scrape.

- **[med] FUDS current_owner normalization to readiness proxy.** The `current_owner` raw-code normalization already in backlog ("`PRIV:*` → `"Private"`") is a prerequisite. Once normalized, a FUDS record with a non-federal owner + `fuds_status = "Eligible"` (meaning remediation obligations met) maps cleanly to Tier 1. No new fetches — just use existing `current_owner` once the normalization ships.

- **[low] BRAC LRA reuse plan manual curation.** 27 BRAC sites is small enough to hand-curate: for each site, look up the LRA name, reuse plan headline (e.g., "Great Park Irvine — mixed-use / recreation"), and percent acreage transferred (from `bracpmo.navy.mil`). Store as a static lookup in `connectors/dod_brac.py` (similar to how `NPL_STATUS_LABELS` works for Superfund). Zero ongoing maintenance needed — BRAC is a closed list.

### New sources researched 2026-05-05

- **[high] Federal Register API — NPL deletion + BRAC conveyance signals.** Confirmed public JSON API; no auth. `https://www.federalregister.gov/api/v1/documents.json?conditions[term]=national+priorities+list+deletion&conditions[type][]=RULE` returns NPL deletion final rules with `publication_date`, `title`, and `abstract`. Every NPL site that exits the program gets a final rule published here — this is a stronger and earlier signal than polling `npl_status_code` via the ArcGIS FeatureServer (which can lag by months). BRAC surplus conveyance notices appear under `conditions[agencies][]=department-of-defense&conditions[term]=surplus+property+conveyance`. Pattern: weekly incremental fetch → extract EPA_ID from document title/abstract via regex → set `fr_deletion_date` on matching `sitesById` records → join client-side. New `fed_register.py` enrichment connector; `run_order = 300`. Emits `docs/data/fed-register.json` with `[{epa_id, deletion_date, fr_document_number, fr_url}]`.

- ~~**[high] `In_Reuse` flag quick win (zero new fetches).**~~ Done 2026-05-05 — `epa_redev.py` already populated `in_reuse` on the schema (string "Yes"/"No" rather than bool — kept as-is, the source ships occasional non-`Yes`/`No` values like blank strings). `selectSite()` now renders an `Active Reuse` pill (green outline, `--readiness-ready` token) next to the program pill when `s.in_reuse` matches `/^yes/i`. Regression test: `test_active_reuse_pill_for_in_reuse_site` + `test_no_reuse_pill_when_in_reuse_no`.

- **[med] NY State BCP Certificates of Completion connector.** The NY Brownfield Cleanup Program publishes a machine-readable Socrata dataset of all sites that completed remediation and received a Certificate of Completion — the strongest possible "cleanup complete + reuse ready" signal for NY state brownfields. These are a completely separate universe from EPA ACRES (state VCP, not federal). Dataset: `https://data.ny.gov/resource/ir93-7qzi.json` (SODA API, no auth, CSV/JSON/GeoJSON downloads). Fields: site ID, site name, locality, acreage, year certificate issued. ~500+ records. New `ny_bcp.py` connector; `program: "ny-bcp"`, `run_order = 100`. Cross-reference by lat/lon against existing ACRES records (`ACRES-*` IDs) to detect overlapping sites. First state-level connector; proves out the pattern for CA EnviroStor, NJ HDSRF, TX TCEQ when those publish machine-readable endpoints.

- **[low] Chicago City-Owned Land Inventory crosswalk.** Socrata dataset: `https://data.cityofchicago.org/resource/aksk-kvfp.json` (~10k city-owned parcels on the South/West sides). No environmental-status field, but spatial crosswalk against existing ACRES/FUDS markers (±0.001° lat/lon) would flag which brownfields are still on city rolls vs. transferred. The city's ChiBlockBuilder portal makes these available for acquisition. Worth a `chicago_land.py` enrichment connector only if we expand to city-surplus tracking generally; lower priority than the FR API or NY BCP.

- **[dead end confirmed] AFL (Anticipated Future Land Use) codes.** Searched all public EPA APIs and FeatureServers 2026-05-05. Not in `RedevelopmentAppSitePoints`, not in `envirofacts_site`, not in the cumulis schedule or redevelopment HTML pages. SEMS-internal field that EPA project managers enter via the SEMS UI but never expose externally. Remove `anticipated_land_use` from the `SiteRecord` schema additions planned above — there is no public data source to populate it. If AFL is ever needed, file a FOIA request for a SEMS bulk export.

- **[dead end confirmed] SEMS REST API (`sems.epa.gov/rest/`).** Connection refused on all attempts. Envirofacts `data.epa.gov/efservice/sems.*` tables are documented but HTTP 500 in practice. The authoritative programmatic path for milestone dates is the cumulis schedule page scrape (see `epa_sems_milestones.py` item above). Update any backlog items that reference `sems.epa.gov/rest/` to use the cumulis path instead.

- **[dead end confirmed] DERA/DERP and USACE FUDS deed records.** Defense Environmental Restoration Account (DERA) only publishes program-level funding summaries as PDFs — no site-level transfer records. USACE Real Estate division publishes Finding of Suitability to Transfer (FOST) documents as PDFs on individual district websites (e.g. Sacramento District, Wilmington District), but there is no central index or feed and scraping 38+ district sites is fragile. The existing FUDS FeatureServer `FUDS_STATUS` field remains the best available public proxy for remediation progress. Defer USACE deed records to a future FOIA request if a specific district partnership develops.

### Schema additions (all optional / nullable)

Add to `SiteRecord` in `schema.py`:
```
readiness_tier: Literal["available", "construction_complete", "lifoc", "assessment_complete", "cleanup_in_progress", "no_data"] | None
construction_complete_date: str | None   # YYYY-MM-DD; Superfund CC milestone (cumulis schedule scrape)
swrau_date: str | None                   # YYYY-MM-DD; Sitewide Ready for Anticipated Use (cumulis schedule)
fyr_dates: list[str] | None             # YYYY-MM-DD list; Five-Year Review dates (cumulis schedule)
cleanup_complete_date: str | None        # YYYY-MM-DD; ACRES CA_Status=Completed date
in_reuse: bool | None                   # True = site currently in active reuse (from RedevelopmentAppSitePoints.In_Reuse)
reuse_description: str | None           # plain-text reuse description (cumulis redevelop scrape)
fr_deletion_date: str | None            # YYYY-MM-DD; date of Federal Register NPL deletion rule
transfer_complete: bool | None           # FUDS/BRAC: title passed to non-federal entity
# NOTE: anticipated_land_use removed — AFL codes are not in any public API (SEMS-internal, FOIA-only; confirmed 2026-05-05)
```
`readiness_tier` is derived, not source-supplied — set by a `compute_readiness_tier()` function in `refresh.py` after all enrichments run.

### UI changes

- ~~**[high] "Cleanup Complete" badge in detail panel.**~~ Done 2026-05-05 — `selectSite()` checks `s.program === "superfund" && s.npl_status_code === "D"` and renders a green outline pill (`--readiness-ready` token, same shape as `.dc-pill` / `.reuse-pill`). Regression tests: `test_cleanup_complete_pill_for_npl_deleted` + `test_no_cleanup_pill_for_active_npl_site`.

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
- ~~**[med] Mobile filter UX.**~~ Done 2026-05-11 (v1.12) — `#filters` is the same DOM on both layouts; mobile CSS re-styles it into a slide-up bottom sheet with a `#filters-backdrop` overlay dimming the map, drag handle, close ×, and a pinned Reset + Done action row. Desktop strip behavior unchanged. Sheet header/footer/backdrop are `display: none` above 640px. Same v1.12 pass also added: hero KPI deck wrapped in a `<details>` disclosure with a 2-number summary chip (`Sites tracked · DC candidates`); footer source list collapsed behind a "Sources" chip; four detail-panel sections (Owner & encumbrances · Federal documents · Infrastructure proximity · Enforcement & compliance) converted to `<details class="d-section">` accordions with session-memory in `DETAIL_SECTION_PREFS`, defaulting closed on mobile and open on desktop; table hides City + County columns + drops Program pill background on `<640px`. Net result: chrome at iPhone-SE viewport drops from ~340px to ~580px of map real estate.

## Performance / hosting

### Frontend JS — code-level hot paths (audited 2026-05-05)

- ~~**[high] Pre-build search index at ingest time.**~~ Done 2026-05-05 — `ingestSites()` writes `s._searchKey = [name, city, county, state].filter(Boolean).join(" ").toLowerCase()` once per record. `siteMatchesQuery()` now reads `s._searchKey.includes(q)`. Eliminates the 47k×N per-keystroke string concatenations the audit flagged. Regression test: `test_search_index_built_at_ingest` + `test_search_filter_uses_prebuilt_index`.

- ~~**[high] Cache `refitMapToFilters()` bbox — eliminate O(n) min/max scan.**~~ Done 2026-05-05 — `refreshTableForFilter()` now computes `tableState.visibleBBox = {minLat, maxLat, minLon, maxLon, count}` while it walks the filtered set; `refitMapToFilters()` reads from it instead of re-scanning all 47k records. Every event handler that calls `refitMapToFilters()` already calls `applyFilter()` first, so the bbox is always fresh. Regression test: `test_visible_bbox_cached_on_filter`.

- ~~**[med] Replace `sites.some(s => s.program === X)` with a `loadedPrograms` Set.**~~ Done 2026-05-07 — module-level `const loadedPrograms = new Set()` populated in `ingestSites()`; `ensureAcresLoaded` / `ensureFudsLoaded` / `ensureBracLoaded` now do an O(1) `loadedPrograms.has(...)` check instead of an O(n) `sites.some(...)` scan over up to 47k records.

- ~~**[med] Move `decimateKeep(zoom)` outside the marker-visibility loop.**~~ Verified 2026-05-07 — already hoisted in `applyMarkerVisibility()` ([app.js:1112](docs/app.js:1112)) via `const keepEvery = decimateKeep(zoom)`. Backlog item was stale; only `shouldDecimateOut(id, keepEvery)` runs in the per-marker hot loop.

- ~~**[med] Batch enrichment property assignment.**~~ Done 2026-05-07 — `ensureRedevLoaded` and `ensureInfraLoaded` build a `patch = {}` per record then `Object.assign(existing, patch)`. The single-field `ensureSuperfundDocsLoaded` / `ensureEchoLoaded` / `ensureSummariesLoaded` loaders are intentionally left alone — `Object.assign` adds churn without saving lookups when there's only one or two keys.

- ~~**[med] Cache `updateCountText()` inputs from `refreshTableForFilter()`.**~~ Done 2026-05-07 — `refreshTableForFilter()` now writes `tableState.filteredAcreSum` + `tableState.filteredAcreSites` in the same pass that builds `tableState.filtered` and `tableState.visibleBBox`. `updateCountText()` reads those instead of re-scanning all 47k records — every caller already runs `refreshTableForFilter()` first via `applyFilter()`, so the cache is always fresh.

- ~~**[low] Event delegation for table header sort clicks.**~~ Done 2026-05-07 — single delegated `click` listener on `#sites-table thead` that checks `event.target.closest("th[data-sort]")`. Survives future column additions without rebinding. N column listeners → 1.

- ~~**[low] Cache `querySelectorAll` in `updateSortIndicators()`.**~~ Done 2026-05-07 — `_sortHeaders` cached on first call via `getSortHeaders()` and reused. The header set never changes for the document's lifetime.

- **[low] Pre-compile `prettyPlace`/`prettyName` regexes as module constants.** Both functions define their split regexes inline (re-parsed each call at startup). Move them to `const PLACE_SPLIT_RE = /(\s+|[-/])/g` at module scope. V8 likely caches them already, but explicit constants make the intent clearer.

- **[low] Single-pass KPI deck computation.** `updateKpiDeck()` loops `sites` once per metric (total, acres, DC candidates, state set). Merge into one `sites.reduce()` call that accumulates all four in parallel. Reduces 4 passes to 1.

### UAT 2026-04-29 #2 (high priority)

- **[med] LOD swap for the basemap above zoom 10.** State strokes still look blocky at zoom 12+. Pagination + chunked hydration moved this off the critical path; revisit when we can swap to a higher-detail GeoJSON or fade strokes at zoom > 10. *(Demoted — counties carry visible borders past zoom 7, so the simplification artifact is mostly cosmetic on infrequent deep-zoom views.)*
- ~~**[high] Re-evaluate `ensureCountiesLoaded()` on every `moveend`.**~~ Done 2026-04-29 (v1.6) — `map.on("moveend", updateCountyVisibility)` now fires for any view change, including `setView`-driven auto-zoom from `?site=` or the detail panel.
- ~~**[high] Toast / inline feedback when `?site=<id>` doesn't match.**~~ Done 2026-04-29 (v1.6) — `applyUrlSelection()` waits for `acresLoadingPromise` (so the toast doesn't fire prematurely), then `showToast(...)` with the bad ID. URL is preserved.
- ~~**[high] Fix URL-state unwind on filter clear.**~~ Verified 2026-04-29 (v1.6) — `syncUrl()` already drops keys at default; new regression test `test_url_unwinds_on_filter_clear` guards against future drift.

### UAT 2026-04-29 (high priority)

- **[high] Audit first-paint payload now that ACRES auto-loads.** Cold load = ~12 MB decoded / ~1.8 MB on the wire (sites.json 184 KB gz + epa-acres.json 1.58 MB gz + states 30 KB + leaflet/topojson/app/css). Partial mitigation 2026-05-07: every post-paint enrichment fetch (`epa-redev`, `infra-proximity`, `epa-echo`, `ai-summary`, `epa-superfund-docs`) now passes `priority: "low"` so browsers (Chrome 102+, Firefox 132+, Safari 17+) deprioritize them behind the first-paint resources. Doesn't reduce bytes — bytes problem is still real. Real fix is one of: (a) make ACRES opt-in (already in Frontend/UX backlog as `[low]` since the cold-freeze was killed by chunked hydration); (b) state-shard ACRES and lazy-fetch only the visible state(s); (c) drop unused fields from the ACRES output (audit `epa-acres.json` for null-heavy columns). Defer until a user cites the bandwidth cost.
- ~~**[high] Cap or virtualize markers on the canvas at low zoom.**~~ Partial 2026-05-07 — tightened decimation to 1/16 at zoom ≤4 (was 1/8) and 1/8 at zoom ≤5 (was 1/4). Visible-marker count at zoom 4 drops from ~5,900 to ~3,000 across all four programs. Viewport-clipped renderer (only add markers within `getBounds()` and re-evaluate on `moveend`) deferred until a user reports residual pan-lag at zoom 4.

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

- ~~**[med] Out-of-CONUS sites have no infra-proximity data — undocumented.**~~ Done 2026-05-07 (option a) — `setMileCell()` now accepts an `offConus` flag (set when `s._inset` is truthy in `selectSite()`) and renders `"Remote — outside continental US"` instead of `"Not available"` for AK / HI / PR / VI / GU / MP / AS / FM records. The 395 FUDS + 142 ACRES out-of-CONUS records now read as a known source-side limitation rather than missing data. Option (b) — running AK-specific enrichment with AK DOT&PF + HIFLD AK railroad layers — still open if a user requests AK-specific infra distances.

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
