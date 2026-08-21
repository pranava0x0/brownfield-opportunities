# NEPA MCP integration spec

**Status:** research + proposal. Nothing here is built.
**Researched:** 2026-08-21, against `nepa-mcp` **0.1.1** (the current release; `0.1.0` is the only prior one).
**Decision this asks for:** approve Tier A (zero cost, do it now), approve or defer Tiers B1–B3 (three narrow connectors), and accept the Tier C refusals.

---

## 1. What `nepa-mcp` actually is

`nepa-mcp` is the MCP server layer of **PermitAI**, PNNL's DOE-funded permitting-acceleration
toolkit. It is a *client-side research tool*: it wraps public federal GIS and regulatory
endpoints behind MCP tools so an agent can query them by region of interest.

| | |
|---|---|
| Publisher | Pacific Northwest National Laboratory — Chaturvedi, Chintalapati, Nally, Parker, Munikoti, Horawalavithana |
| PyPI | [`nepa-mcp`](https://pypi.org/project/nepa-mcp/) 0.1.1 |
| Repo / docs | [github.com/pnnl/nepa-mcp](https://github.com/pnnl/nepa-mcp) · [pnnl.github.io/nepa-mcp](https://pnnl.github.io/nepa-mcp/) |
| License | BSD 3-Clause (code). Upstream data keeps each source's terms. |
| Inventory | **19 servers, 46 tools, 32 GIS layers** — 78 capabilities across 12 federal agencies |
| Runtime | **Python ≥ 3.12**, `fastmcp==3.4.4`, plus `shapely`, `pyproj`, `folium`, `httpx` |
| Credentials | None for 17 servers. `census` needs `CENSUS_API_KEY`; `epa_aqs` needs `EPA_AQS_EMAIL` + `EPA_AQS_API_KEY`. Both free. |

PNNL states plainly that it is a **screening aid** — it makes no agency determination and
does not guarantee an upstream dataset is complete or current. That framing matches this
project's own posture exactly, and the spec below preserves it.

### 1.1 The hard constraint, first

**`nepa-mcp` cannot become a dependency of this project.** It requires Python ≥ 3.12; this
repo's floor is **Python 3.9+** (CLAUDE.md, Python Standards) and the machine's default
`python3` is **3.9.6**. It also pins `fastmcp==3.4.4` and pulls `shapely` + `pyproj` — C
extensions this project has *twice* refused on purpose (`connectors/spatial.py` and
`connectors/county_lookup.py` are pure-Python specifically to avoid ~10 MB of wheels in a
static-data project).

That is not a blocker, it is a shape constraint: **`nepa-mcp` runs out-of-process, on its own
interpreter, as an MCP server the agent talks to — never as an import inside `refresh.py`.**
`python3.12` is already present at `/Users/pranava/.local/bin/python3.12`; `pipx` is not
installed and would need to be.

---

## 2. Capability map against what we already have

The 19 servers split cleanly into three buckets against this repo's 25 data files.

### 2.1 Already covered — validation value only

| `nepa-mcp` | Ours today | Verdict |
|---|---|---|
| `fema_nfhl` flood zones | `infra-proximity` `flood_zone` / `in_sfha`, **91.1% coverage** after a ~15-hour per-site backfill | **Don't rebuild.** Use it to spot-check, the way `validate_against_sources.py` re-measures infra distances. |
| `tigerweb_counties` | `connectors/county_lookup.py` — offline TopoJSON point-in-polygon, ~99.5% hit | **Don't rebuild.** Ours is free and offline; theirs is an HTTP call per ROI. |
| `gis` ROI buffers / area | `connectors/spatial.py` `SegmentIndex` / `PointIndex` / `PolygonIndex`, fuzz-tested against brute force | **Don't rebuild.** |

### 2.2 Genuine gaps this closes

Each row below is a gap **this project has already written down** as unfilled.

| Gap (where it's recorded) | `nepa-mcp` tool | Why it matters here |
|---|---|---|
| **Workforce** — the AP1000/Nuclear Siting lens weights construction workforce **15/100** and CLAUDE.md admits it is "analyst-researched (no federal GIS layer exists for water/fiber/workforce)" | `census.get_acs_socioeconomic_indicators_in_roi` | ACS 5-Year by intersecting county turns a hand-curated `strong`/`good`/`moderate`/`limited` judgement into a measured layer. **Biggest single win.** Also unblocks the backlog's "workforce is the next quantitative upgrade" note on the Manufacturing lens. |
| **Tribal consultation** — nothing, anywhere | `tribal.get_tribal_lands_in_roi` | Section 106 / Tribal consultation is a schedule risk on federal land, and 8,848 of our sites *are* federal land. Currently invisible in every lens. |
| **Historic properties** — nothing | `nrhp.get_nrhp_properties_in_roi` | Same Section 106 exposure. FUDS and BRAC properties are disproportionately likely to contain listed structures. |
| **ESA species / critical habitat** — nothing | `ipac.get_ipac_resources_in_roi`, `gbif.*`, `esa_ranges.*`, `noaa.*` | A listed species on site is a genuine schedule-killer that no current lens can see. |
| **Wetlands / Section 404** — `data-source-research.md` logs an FWS NWI liveness probe that never became a connector | `usace.analyze_usace_jurisdiction`, `usace.get_usace_wetland_regions_in_roi`, `usace.get_usace_regulatory_district` | 404 jurisdiction determines whether a site needs a permit at all, and which district issues it. |
| **Protected areas** — nothing | `padus.get_padus_protected_areas_in_roi` | PAD-US 4.1 owner/manager attributes. Directly relevant to the "is this land actually available" question the parcel-owner connector only half-answers. |
| **Air quality / NAAQS** — nothing | `epa_aqs.*`, `nepa_assist.analyze_nepa_assist_screening` | Nonattainment status gates behind-the-meter gas turbines and diesel backup — i.e. it constrains the DC lens's `gas_pipeline_mi` component and the whole generation lens. |
| **Regulatory currency** — `STATE_DC_INCENTIVES` (51 rows, annual re-audit), `STATE_DC_REGULATION` (quarterly re-audit), EO 14318, all hand-maintained | `cfr.cfr_resolve_executive_order`, `cfr.cfr_rulemaking`, `cfr.cfr_compare_versions`, `cfr.cfr_history` | These re-audits are the most tedious recurring work in the repo. `cfr_compare_versions` diffs a citation between two dates — that is precisely the "has this changed since `verified_at`?" question. |
| **BLM land-use plans** — nothing | `blm.*` | Relevant to the western FUDS/BRAC sites that dominate the microreactor ranking's non-Alaska tail. |

### 2.3 Overlaps worth knowing but not acting on

`map_composer` composes 32 layers into an interactive Folium HTML map. We already ship a
tuned Leaflet map with a vector basemap and 47k decimated markers. **Do not replace it.** It
is useful as an *analyst scratchpad* for one site, not as a product surface.

---

## 3. Integration tiers

### Tier A — agent-time tool. Do this now. Zero architectural cost.

Install `nepa-mcp` as an MCP server for the *analyst working in Claude Code*, not as anything
the dashboard or `refresh.py` touches.

```bash
python3.12 -m pip install --user pipx && python3.12 -m pipx ensurepath
pipx install --python python3.12 nepa-mcp
nepa-mcp doctor          # expect: Installed servers: 19
nepa-mcp configure claude
```

**What it buys:** ad-hoc, per-site NEPA screening on the handful of sites that actually
matter — the top of a ranking, a site a user asked about, a candidate for the reference-campus
overlay. No new data file, no schema change, no refresh cost, nothing to keep fresh.

**Cost:** one `pipx` install and a `.mcp.json` entry. Reversible in one command.

**Risk to manage:** 19 servers × 46 tools is a large tool surface to load into context. Prefer
`nepa-mcp configure claude` scoped to the servers a session needs rather than the Codex plugin
that registers all 19 — the tool catalog exists precisely so you can "choose the smallest set
of servers needed for a workflow."

### Tier B — narrow connectors, only where the geography is coarse

The rule this project already learned the hard way: **bulk-fetch into a local spatial index;
never per-site HTTP over the corpus.** The flood backfill is the scar — ~15 hours, resumable,
budgeted, and *still* only 91.1%. Any Tier B item must fetch a bounded national layer once and
then answer 46,759 questions offline.

| | Layer | Feature count | Fits the pattern? |
|---|---|---|---|
| **B1** | ACS county socioeconomics (`census`) | ~3,232 counties | **Yes.** One fetch per county, joined by the county we *already* resolve offline. Reuses `CountyIndex`. |
| **B2** | Tribal lands, TIGERweb AIANNHA (`tribal`) | ~700 polygons | **Yes.** Straight `PolygonIndex` containment — identical in shape to `opportunity-zone` and `ira-energy-community`. |
| **B3** | PAD-US protected areas (`padus`) | large but bulk-downloadable | **Probably.** Needs a size probe before committing. |

**B1 is the one to build first**, and it should be built as a normal connector against the
Census API directly — *not* through `nepa-mcp`. `nepa-mcp` is how you discover that ACS answers
the workforce question and validate the shape on ten sites; the connector is how you ship it to
46,759. Using an MCP server as a batch ETL layer would inherit the per-ROI HTTP cost this
project exists to avoid.

Suggested: `connectors/census_workforce.py`, slug `census-workforce`, `run_order = 365`
(after `fema-nri` at 360). New `SiteRecord` fields — `county_labor_force`,
`county_construction_employment`, `county_median_income`, `workforce_source`. Then
`ap1000-score.js` `_ap1000ScoreWorkforce()` reads a measured value with the analyst rating as
fallback, and the Nuclear Siting tab's provenance line stops saying "analyst-researched" for
workforce.

### Tier C — refuse, and write down why

- **Per-site ESA / wetlands / NRHP / air-quality over the full corpus.** These are ROI queries
  with no bulk endpoint exposed through `nepa-mcp`. At 1.5 s/site that is ~19 hours *per layer*,
  and we have direct experience of what that costs. Use them per-site in Tier A instead.
- **Replacing our FEMA flood data.** 91.1% coverage already exists and cost 15 hours. Re-deriving
  it through a second path buys nothing.
- **`map_composer` as a product surface.** Folium HTML is not a substitute for the tuned Leaflet
  map; adding it would be a second, worse map.
- **Adding `nepa-mcp` to `requirements.txt`.** Python floor and C-extension policy both forbid it.

---

## 4. Key scenarios

Grounded in what this repo's 217 commits actually consist of — **56 `feat`, 53 `data`
(refresh/backfill), 32 `docs`, 17 `fix`**, with 32 connector/enrichment commits and 10
audit/re-verify commits.

### S1 — "Screen the top of a ranking before I show it to anyone" *(question type: siting)*

> *The microreactor lens ranks Haines Pol Dump (FUDS, AK) #1. Is it actually permittable?*

Today the four lenses see grid, land, hazard, and finance. They cannot see species, wetlands,
tribal land, or historic properties — so a #1 site could be undevelopable for a reason the
dashboard structurally cannot show.

**Flow (Tier A):** `gis.summarize_roi_buffer` → `ipac.get_ipac_resources_in_roi` →
`usace.analyze_usace_jurisdiction` → `tribal.get_tribal_lands_in_roi` →
`nrhp.get_nrhp_properties_in_roi`.

**Output:** a short screening note appended to `issues.md` or the site's row in a review doc.
**Explicitly not** a new score component — one-off screening of 10 sites must never be
presented as a corpus-wide field, because 46,749 sites would silently lack it.

### S2 — "Has the regulatory ground moved since we last checked?" *(question type: re-audit)*

> *`STATE_DC_REGULATION` says quarterly. `STATE_DC_INCENTIVES` rows carry `verified_at: 2026-05-08`. Both are overdue.*

This is the single most repetitive recurring task in the repo and the one most likely to be
skipped. `cfr_compare_versions` diffs a CFR citation between two dates paragraph by paragraph;
`cfr_rulemaking` lists Federal Register documents that touched a citation; `cfr_history` gives
every amendment event in a window.

**Flow (Tier A):** for each row with a `verified_at`, `cfr_history` / `cfr_rulemaking` from
`verified_at` → today. Non-empty result = re-read that row by hand. Empty = bump `verified_at`
with evidence.

**Value:** turns a 51-row manual sweep into a filtered list of the handful that actually moved.
**Caveat:** state tax law is *not* in the CFR. This works for federal instruments — EO 14318,
IRA 48E/45X, NEPA implementing regs — not for `STATE_DC_INCENTIVES`. Be honest about that split
or the audit will produce false confidence.

### S3 — "Replace an analyst judgement with a measured layer" *(question type: connector/enrichment — 32 commits)*

> *Workforce is 15/100 of the Nuclear Siting score and it is a hand-typed adjective.*

**Flow:** Tier A to validate shape on the 14 curated installations (does ACS construction
employment actually separate Redstone from Fort Wainwright the way the analyst rating does?) →
if yes, Tier B1 builds `census-workforce` as a normal bulk connector → `ap1000-score.js` reads
the measured value, analyst rating becomes fallback → `provenance.js` gains a real citation row.

**This is the highest-value item in the spec** because it converts a documented soft spot into
a hard one and follows the exact path every good connector here has followed.

### S4 — "Validate a field we already ship" *(question type: data validation)*

> *`validate_against_sources.py` re-measures infra distances against live services. Flood zones have no independent check.*

**Flow:** sample N sites → `fema_nfhl.get_fema_nfhl_flood_zones_in_roi` → compare to stored
`flood_zone` / `in_sfha` → report as `WARN` (upstream) or `FAIL` (ours) per the existing
`UPSTREAM_QUALITY_CHECKS` split.

**Note the trap** documented in CLAUDE.md: a checker that does not model the real join measures
nothing. Any such check must go through `Corpus.merged`'s fill-if-empty semantics, and pinned
100-mile-cap values are censored, not measured.

### S5 — "A new site-availability signal" *(question type: feature — 56 commits)*

> *`parcel-owner` covers 11 states. PAD-US covers protected-area owner/manager nationally.*

PAD-US answers a question the parcel connector cannot: is this land in a conservation
designation that forecloses development regardless of who holds title? Tier B3 pending a size
probe; Tier A immediately for spot checks.

### S6 — "Why did the scheduled refresh fail again?" *(question type: fix — 17 commits; CI has failed 12/12 runs since 2026-05-25)*

**`nepa-mcp` does not help here.** Listed so the spec is honest about its boundary: the CI
failures are IPv6-blackhole and fault-isolation problems in our own pipeline. Adding a new data
source to a pipeline that cannot complete a run would make things worse, not better. **Fix the
refresh chain before adding Tier B.**

---

## 5. Recommended sequence

1. **Now — Tier A.** `pipx install nepa-mcp`, `nepa-mcp configure claude`. Run **S1** against the
   top 10 microreactor sites and the 14 Nuclear Siting installations. Log findings in
   `data-source-research.md` in the existing probe format, so the discovery is never re-paid.
2. **Then — S2** on the federal instruments only, and record in CLAUDE.md that state tax rows
   still need the manual sweep.
3. **Then — S3 validation half.** If ACS separates the 14 installations sensibly, open Tier B1.
   If it doesn't, stop and say so — that is a real finding, and cheaper than a connector.
4. **Blocked on the refresh chain — Tier B1/B2/B3.** Do not add a 26th data file to a pipeline
   with 12 consecutive CI failures.

## 6. Open questions

- Does `nepa-mcp` respect a rate limit per upstream service, or does the caller? Our connectors
  hold a hard 1.5 s/host floor as an ethics rule; an MCP server fanning out 46 tools could
  violate it invisibly. **Verify before any batch use.**
- `pipx` is not installed on this machine. Confirm the install path before promising Tier A.
- 0.1.1 is an early release with two versions on PyPI. Pin the version in any documented
  workflow, and re-read the tool catalog on upgrade — it is generated from the live
  `tools/list` contract and will drift.
