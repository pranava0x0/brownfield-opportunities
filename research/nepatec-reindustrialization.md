# NEPATEC patterns for brownfield reindustrialization

**Researched:** 2026-08-21
**Product question:** how can this dashboard move from site discovery to a defensible
reuse decision for retired plants, brownfields, FUDS/BRAC land, and industrial districts?

## What others built from the same stack

PNNL's PermitAI stack separates three jobs that this product currently mixes:

1. **Corpus and links.** [NEPATEC 2.0](https://www.pnnl.gov/projects/permitai/data-lakehouse)
   contains more than 120,000 documents from 60,000 projects. Its metadata follows the
   CEQ NEPA data standard. PermitTEC adds court cases and links them to projects where
   possible. NEPATEC 3.0 is targeted for Q3 2026 with GIS elements.
2. **Find and interrogate precedent.** [SearchNEPA and ChatNEPA](https://www.pnnl.gov/projects/permitai/ai-applications)
   combine filters, semantic search, document questions, and verifiable answers. More
   than 500 federal beta users use the product.
3. **Apply current site evidence.** PermitAI's PermitCE combines comparable historical
   categorical exclusions with current, site-specific geospatial evidence. `nepa-mcp`
   exposes that evidence layer: species, protected areas, tribal geographies, historic
   properties, water context, agency boundaries, regulatory text, and map packages.

The transferable pattern is **precedent + current place + explicit gaps**. It is not an
LLM-written permit conclusion.

## What successful reuse programs emphasize

- NRC's [brownfield and retired-fossil guidance](https://www.nrc.gov/reactors/new-reactors/advanced/new-app/general-guidance/brownfield)
  says applicants can reuse prior site studies, NEPA documents, infrastructure, and
  potentially prior water/air/land-use permits. The useful inventory includes roads,
  rail, transmission, switchyards, pipelines, water intakes, meteorology, hydrology,
  geology, geotechnical work, and seismology. Contamination and coal ash remain review
  inputs; prior disturbance is not a waiver.
- DOE screened 157 retired and 237 operating coal sites and found 80% potentially
  compatible with sub-gigawatt advanced reactors. Its
  [coal-to-nuclear summary](https://www.energy.gov/ne/articles/doe-report-finds-hundreds-retiring-coal-plant-sites-could-convert-nuclear)
  estimates 15–35% construction-cost savings where electrical, cooling, road, and
  building infrastructure can be reused.
- EPA's [RE-Powering Mapper](https://www.epa.gov/re-powering/re-powering-mapper)
  pre-screens more than 190,000 contaminated lands, landfills, and mine sites and lets
  users filter acreage, capacity, substation distance, cleanup program, and incentives.
- EPA's [manufacturing-on-brownfields guide](https://www.epa.gov/land-revitalization/new-manufacturing-old-brownfields)
  treats remediation, industrial recruitment, workforce, and community redevelopment as
  one delivery problem—not sequential handoffs.
- DOE's [Cleanup to Clean Energy](https://www.energy.gov/em/em-clean-energy-land-reuse)
  uses leases and staged RFIs/RFQs to turn roughly 34,000 acres of cleanup-site land into
  an investable pipeline. Site pages bundle land-use plans, environmental reports,
  solicitation documents, comments, and awards.

## Product direction for this site

### 1. Reuse dossier — build next

Every selected site gets one click-through dossier with six neutral inventories:

| Inventory | Existing data | Missing next evidence |
|---|---|---|
| Land and control | acreage, parcel owner, FUDS/BRAC status, cleanup | exact project parcel, easements, conveyance/use instrument |
| Reusable infrastructure | transmission, substation, plant, rail, highway, pipelines | switchyard voltage/capacity, water intake/discharge, structural condition |
| Environmental baseline | flood, NRI, climate, tribal context; Janus NEPA MCP screen | wetlands delineation, parcel ESA survey, cultural survey, contamination/coal ash |
| Prior record | EPA documents and cleanup links | NEPATEC analogues, prior site NEPA documents, transferable permits |
| Workforce/community | county, incentives, energy community | ACS/LODES trades, displaced plant workers, tax-base dependence, community priorities |
| Delivery path | owner/source links, program status | lead/cooperating agencies, permit dependencies, preapplication contacts, schedule |

Show **known / no hit / unavailable / project-specific work required**. Never collapse
these into a red-green suitability score.

### 2. Analog project finder — build after dossier

Use NEPATEC metadata and semantic search to find projects by:

- reuse type: coal-to-nuclear, industrial brownfield, federal cleanup land, BRAC/FUDS;
- technology and load: reactor class, advanced manufacturing, data center, industrial heat;
- agency, review level, geography, resource issue, mitigation, and outcome;
- cited page and paragraph, so every extracted precedent is inspectable.

The result should answer: **what was studied, what was reused, what delayed the project,
what mitigation worked, and what evidence can be incorporated by reference?** A historical
analogue informs scope; it never determines the new site's review level.

### 3. Permit and evidence graph

Render a dependency graph rather than a permit checklist: project action → lead agency →
NEPA review → consultations → water/air/land approvals → cleanup/land-control instruments →
construction authorization. Each node carries owner, status, source, date, prerequisite,
and missing document. Link PermitTEC cases to the procedural node they challenged.

### 4. Industrial-district mode

Reindustrialization often spans adjacent parcels. Add a 1/5/10-mile cluster view that groups
retired generation, brownfields, FUDS/BRAC land, substations, rail, water, and workforce.
Model shared assets separately from parcels. This makes combinations visible: a cleaned
brownfield for manufacturing, adjacent retired switchyard for power, nearby rail, and a
shared water/utility corridor.

### 5. Conversion lanes

Do not force every site into nuclear. Screen transparent reuse lanes against physical assets:

- nuclear generation or nuclear-powered industrial heat;
- advanced manufacturing and nuclear supply chain;
- data center / high-reliability load;
- storage, hydrogen/e-fuels, or clean-firm hybrid;
- logistics or industrial park.

Display the evidence that supports a lane and the evidence still missing. Keep economics,
community preference, and legal feasibility as separate dimensions.

### 6. Agency-ready export and monitor

Export a source manifest, GeoJSON, retrieved dates, prior-document links, issue register,
and unanswered fieldwork list. Add change monitoring for source refreshes, Federal Register/
CFR changes, solicitations, cleanup milestones, and newly available NEPATEC records.

## Recommended order

1. Ship the dossier from fields already on disk; add the Janus interaction pattern to all sites.
2. Complete ACS/LODES workforce and ingest EPA's full RE-Powering screening dataset.
3. Add NEPATEC analogue search with page citations and explicit confidence.
4. Add permit/evidence graph and agency-ready export.
5. Add cluster mode and conversion lanes after parcel/control data improves.

The first release should optimize for a developer asking: **“What can I reuse, what must I
prove, who decides, and where is the source?”**
