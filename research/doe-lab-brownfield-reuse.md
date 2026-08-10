# DOE national-lab research on brownfield reuse — findings and what to build next

Retrieved **2026-08-09**. Primary sources are listed with checksums in
[`sources/MANIFEST.md`](sources/MANIFEST.md); the PDFs themselves are gitignored (they are
re-fetchable federal documents, and the repo rule is no large binaries).

The purpose of this pass was not a literature review for its own sake. It was
to answer one question: **what do the national labs know about siting on
contaminated and former-industrial land that this dashboard does not yet
encode?** Section 3 is the answer, ranked.

---

## 1. The headline: NREL names this dashboard's exact gap

NREL's *Data Centers Gap Analysis* (February 2026) tabulates what is missing
for near-term large-load integration. One row reads:

| Lever | Why it matters | Data needed | Gap? |
|---|---|---|---|
| Brownfield conversion projects | "Utilize existing land to speed up otherwise lengthy permitting processes" | "Database of eligible brownfield conversion sites" | **Yes** |

That is a national lab, six months ago, listing "a database of eligible
brownfield conversion sites" as an open data gap. This project is that
database — 46,759 sites with grid, gas, rail, flood, and climate signals
already joined. The gap is not the corpus. **The gap is that our screening
criteria are homegrown, while the labs have published, defensible ones.**
Closing that is the single highest-value thing on this list.

The same deck also lays out the geospatial factor taxonomy NREL uses for its
own siting tool, which is a useful checklist against our coverage:

| NREL factor category | Examples | Our coverage |
|---|---|---|
| Land use development | wetlands, forests, urban areas, **slope** | ✗ none |
| Environmental / climate | **water resources**, ambient humidity, projected climate risk | partial — FEMA NRI drought/wildfire/heat, IECC climate zone; no water resources |
| Land use exclusions | **military land/airspace**, topography, **conservation areas**, private property | partial — parcel owner in 11 states; no PAD-US, no airspace |
| Access needs | **latency**, proximity to end users, **fiber**, grid infrastructure/congestion | partial — grid yes; no latency, no fiber, no congestion |

NREL also publishes a public **Speed to Power** map
(`maps.nrel.gov/speed-to-power`), which is worth reading for terminology
alignment — "speed to power" is the industry's framing and ours should match it.

---

## 2. What each source establishes

### 2.1 INL/ANL/ORNL — *Investigating Benefits and Challenges of Converting Retiring Coal Plants into Nuclear Plants* (INL/RPT-22-67964, Sept 2022)

The C2N study. Screened **157 retired** and **237 operating** coal plant sites;
found **80%** viable for advanced reactors. The number this project already
leans on, now properly sourced:

> Reusing coal infrastructure cuts nuclear **overnight capital cost by 15–35%**
> versus greenfield.

Reusable components are enumerated: **electric switchyard and transmission
infrastructure**, office buildings, heat-sink components, steam-cycle
components, roads, and water rights. This is the citation that justifies the
`grid_reuse` / `grid_inheritance` components in [`dc-score.js`](../docs/dc-score.js) — we
should cite it in the UI explainer rather than asserting the logic unsourced.

**The most transferable asset here is ORNL's OR-SAGE criteria set** (Appendix A).
Ten thresholded, GIS-computable rules, every one of them a public dataset:

| OR-SAGE criterion | Threshold | Our status |
|---|---|---|
| Population density | exclude >500 people/sq mi, 4-mi buffer (advanced reactor); 20-mi per RG 4.7 for large LWR | ✗ no population data at all |
| Seismic | exclude SSE peak ground acceleration >0.5 g (2% in 50 yr) | partial — ASCE 7-22 values exist for the 14 curated nuclear sites only |
| Fault standoff | exclude land too close to fault; distance scales with fault length (10 CFR 100 App. A) | ✗ |
| Landslide | exclude moderate/high USGS susceptibility | ✗ |
| Slope | exclude >18% (~10°) — a site-prep economics rule | ✗ |
| Wetlands / open water | exclude | ✗ |
| 100-year floodplain | exclude | ✓ **already have** (FEMA NFHL, 91.1% coverage) |
| Cooling water | exclude >20 mi from a source of ≥135,000 gpm (LWR); relaxed for air-cooled ARs | ✗ nationally (hand-researched for 14 nuclear sites) |
| Protected lands | exclude parks, historic areas, wildlife refuges | ✗ |
| Hazard proximity | avoid airports, military, missile, toxic-gas facilities | ✗ |
| Footprint | ~50 acres suffices for an advanced reactor; microreactors need a few | ✓ acreage |

Note their framing, which we should copy: *"All the parameters should be
considered flags to inform siting decisions and should not be used to rule in
or rule out any site."* That is exactly the posture of our `coord_flags` work.

### 2.2 LBNL — *2024 United States Data Center Energy Usage Report* (Dec 2024)

The demand-side case for the whole project:

- **176 TWh in 2023 = 4.4%** of US electricity, up from 76 TWh (1.9%) in 2018.
- CAGR **~7% (2014–18) → 18% (2018–23)**, projected **13–27% (2023–28)**.
- 2028 range **325–580 TWh (6.7–12.0%)** — at 50% utilization, **74–132 GW** of
  new demand.
- Water: **66 billion liters** direct consumption in 2023, 84% from hyperscale
  and colocation.
- Virginia leads demand, then California and Texas.
- PUE/WUE are modelled **per cooling system type against TMY climate data by
  weather station** — i.e. cooling water demand is a function of climate zone,
  which we already carry per site.
- They publish **county-level water-consumption intensity and GHG intensity by
  balancing authority** — directly joinable to our records.

### 2.3 INL — *Bridging the Gap for Powering Data Centers* (INL/RPT-26-89901, Jan 2026)

Proceedings of INL's Oct 2025 workshop, 100+ industry participants. The
themes are the buyer's actual decision criteria:

- **Speed to power** is the organizing concern — planning, permitting and
  construction timelines, not levelized cost.
- Developers increasingly pursue **behind-the-meter and hybrid architectures**
  (on-site generation, microgrids, storage) specifically **to bypass
  transmission interconnection delays**.
- On BTM incentives, workshop attendees most favored options that
  "incentivized self-generation and rewarded proactive investment in new
  capacity."
- Named knowledge gaps: **environmental siting (water and noise)**, public
  perception, and licensing pathways for advanced nuclear.

Noise is a siting constraint we have never modelled and which is now appearing
in state legislation (cf. Virginia HB153/SB94 in `STATE_DC_REGULATION`).

### 2.4 LBNL — *Large Load Literature Review* (Nov 2025 update)

A curated index of large-load literature across 12 themes. The finding most
relevant to scoring:

> **76 GW of new load could be integrated** if that load can curtail
> **0.25% of its maximum uptime**; the integrable quantity rises with higher
> curtailment tolerance.

Flexibility is therefore a first-order siting lever, and one our model treats
as nonexistent — we score a site as if every megawatt must be firm.

### 2.5 NREL — *Solar Development on Contaminated and Disturbed Lands* (NREL/TP-6A20-58485)

The brownfields-to-brightfields foundation. Finds sufficient contaminated and
disturbed land exists to meet SunShot-scale deployment without touching
agricultural or otherwise productive land, and that contaminated sites can
carry **permitting and environmental-mitigation advantages** over greenfield.
EPA/NREL have **pre-screened over 190,000 sites** for renewable potential.

### 2.6 EPA RE-Powering screening dataset — a coverage discovery

EPA's RE-Powering Mapper publishes a **screening dataset of 190,000+ sites**
(XLSX ~78 MB, plus a geodatabase), searchable by "state, acreage, renewable
energy capacity, **distance to nearest substation**, and more," screened
against criteria developed with NREL.

We currently consume only the 1,905-record `RedevelopmentAppSitePoints` layer.
**This is a ~100× coverage difference on a dataset we already treat as
authoritative**, and it independently reports two quantities we compute
ourselves (acreage, substation distance) — so it is both an expansion and a
cross-check.

---

## 3. Opportunities, ranked by value over effort

### Tier 1 — high value, data already public and pure-Python computable

1. **Adopt the OR-SAGE criteria corpus-wide.** Implement the ten thresholds as
   a `siting-constraints` enrichment across all 46,759 sites, not just the 14
   curated nuclear ones. Each is one public layer plus the `PolygonIndex` /
   `SegmentIndex` we already have. This converts our homegrown screening into
   *the* published federal methodology and directly fills NREL's stated gap.
   Start with the four cheapest: **slope** (USGS 3DEP), **protected lands**
   (USGS PAD-US), **wetlands** (FWS NWI — liveness already probed in
   `data-source-research.md`), **population density** (Census).

2. **Ingest the EPA RE-Powering 190k screening dataset.** Biggest single
   coverage win available, from a source we already trust. Use its
   substation-distance column as an independent check on `substation_mi` — the
   kind of external validation the 2026-08-09 audit showed we otherwise lack.

3. **Population density.** OR-SAGE's single most discriminating parameter, and
   we have none. Serves three purposes at once: nuclear exclusion screening,
   NREL's "proximity to end users" latency proxy, and a community-opposition
   risk signal that pairs with `STATE_DC_REGULATION`.

### Tier 2 — high value, moderate effort

4. **Cite the labs in the UI.** The `grid_reuse` credit rests on INL's 15–35%
   OCC finding; the flood penalty matches an OR-SAGE exclusion. The evidence
   panel already exists — extend `FIELD_PROVENANCE` so scoring *components*
   cite their methodological basis, not just the data fields. Cheap, and it
   turns the rubric from assertion into argument.

5. **Site-level water demand estimate.** LBNL models WUE by cooling type
   against TMY climate data; we already carry `climate_zone` and NRI drought
   rating per site. A "cooling water demand (est.)" figure crossed with drought
   risk is a genuinely differentiated signal, and water is the constraint INL's
   workshop named as an open gap.

6. **Join LBNL's county water/GHG intensity by balancing authority.** Published,
   county-level, joins to what we already have.

7. **A flexibility lens.** LBNL's 76 GW / 0.25% curtailment finding says a
   curtailable load faces a completely different interconnection reality. At
   minimum surface it in the Rankings explainer; ideally score it.

### Tier 3 — valuable but blocked or expensive

8. **Interconnection queue position** (LBNL *Queued Up*). Queue data is
   published but messy and per-ISO. High buyer value — speed to power is *the*
   criterion — but a real project.

9. **Noise constraints.** Named by INL as an open gap and now appearing in
   state law. No national dataset exists; likely a per-state regulatory field
   like `STATE_DC_REGULATION` rather than a GIS layer.

10. **Fiber / latency.** Still no public national backbone dataset (confirmed
    again here). NREL treats latency as derived from network infrastructure
    *and* proximity to end users — the second half is computable from Census
    population centers even though the first is not. A partial proxy beats the
    current nothing.

---

## 4. Data-source notes worth keeping

- **NREL's document host does not resolve from this sandbox** (`docs.nrel.gov`,
  `www.nrel.gov` → `ENOTFOUND`), while `docs.nlr.gov` serves the same documents
  and returned 200. NREL materials dated 2026 carry the footer **"National
  Laboratory of the Rockies"** and cite `maps.nlr.gov/speed-to-power` *or*
  `maps.nrel.gov/speed-to-power`. Treat `nlr.gov` as the working host and
  `nrel.gov` as possibly-renamed; verify before hardcoding either.
- `orsage.ornl.gov` serves a JS-rendered shell — useless to WebFetch. The
  OR-SAGE criteria are in Appendix A of the C2N PDF instead.
- `eta-publications.lbl.gov` 403s a bare `WebFetch` but serves fine to `curl`
  with a browser User-Agent.
- OSTI (`osti.gov/biblio/<id>`) is a reliable landing page for lab reports when
  the lab's own host is unreachable.

---

## Sources

- INL/ANL/ORNL, [*Investigating Benefits and Challenges of Converting Retiring Coal Plants into Nuclear Plants*](https://gain.inl.gov/content/uploads/4/2024/11/INL-RPT-22-67964-Investigating-Benefits-and-Challenges-C2N.pdf) (INL/RPT-22-67964, Sept 2022) · [OSTI 1886660](https://www.osti.gov/biblio/1886660) · [DOE summary](https://www.energy.gov/ne/articles/doe-report-finds-hundreds-retiring-coal-plant-sites-could-convert-nuclear)
- LBNL, [*2024 United States Data Center Energy Usage Report*](https://eta-publications.lbl.gov/sites/default/files/2024-12/lbnl-2024-united-states-data-center-energy-usage-report_1.pdf) (Dec 2024) · [landing page](https://eta.lbl.gov/publications/2024-lbnl-data-center-energy-usage-report)
- INL, [*Bridging the Gap for Powering Data Centers*](https://inl.gov/content/uploads/2026/01/Bridging-the-Gap-for-Powering-Data-Centers.pdf) (INL/RPT-26-89901, Jan 2026)
- LBNL, [*Large Load Literature Review, November 2025 Update*](https://eta-publications.lbl.gov/sites/default/files/2025-11/wip_lbnl_lllreview_oct_update_2025.pdf)
- NREL / NLR, [*Data Centers Gap Analysis*](https://docs.nlr.gov/docs/fy26osti/97168.pdf) (GDO Planning for Large Loads, Feb 2026)
- NREL / NLR, [*Smart Data Center Siting Backed by NREL Expertise*](https://docs.nlr.gov/docs/gen/fy25/96080.pdf)
- NREL, [*Solar Development on Contaminated and Disturbed Lands*](https://www.osti.gov/biblio/1260337) (NREL/TP-6A20-58485)
- EPA, [*RE-Powering: How to Identify Sites*](https://www.epa.gov/re-powering/how-identify-sites) — 190,000+ pre-screened sites, downloadable
- ORNL, [OR-SAGE](https://orsage.ornl.gov/) · [DOE: ORNL and Elementl Power partner to accelerate siting of nuclear-powered data centers](https://www.energy.gov/ne/articles/oak-ridge-national-laboratory-and-elementl-power-partner-accelerate-siting-nuclear)
