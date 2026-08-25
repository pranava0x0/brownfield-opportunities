# Spec 11: DOE Sites — Multi-Site Dossier Explorer & the Federal-Site Dossier Pattern

**Status:** v2 shipped 2026-08-24 — "DOE Sites" tab (Hanford + SRS + Portsmouth + Paducah + WIPP), answers-first restructure, cited facility-fit matrix, unit drawer, seven-category infrastructure. v1 (Hanford-only) shipped earlier the same day.
**Priority:** High (Impact: 5/5, Size: 3/5, Completeness: 4/5)
**Target Version:** v1.15.x
**Lead Component:** `scripts/build_hanford_e2e.py`, `scripts/build_doe_sites_e2e.py`, `docs/data/{hanford,srs,portsmouth,paducah,wipp}-e2e.json`, `docs/app.js` (DOE-sites module), `schema.py::HanfordParcel`

---

## 0. v2 (2026-08-24): the practitioner evaluation that drove the restructure

A NEPA-practitioner / project-developer walkthrough of v1 found the tab
answered the right questions but buried them:

**Measured v1 problems (headless + browser, 554px viewport):**
- 3.8 screens of scroll with everything COLLAPSED; the first 719px was an
  OPEN "Sources & methodology" accordion — a full screen of methods before
  any fact about the site. Zero facts visible on screen one.
- One parcel card open = 1,597px (~3 screens); fit summary + one parcel =
  8 screens. All facts lived in nine stacked accordions.
- The facility-fit matrix hid each cell's 300+-char rationale in a `title`
  attribute — invisible on touch, invisible to assistive tech, uncited.
- **Best-fit bug:** the tie-ranking listed every type at the top rank, so
  an all-precluded parcel (100/200 Area) read "Data center / Large
  reactor / SMR / Microreactor" — fit-for-everything, the exact opposite
  of the data.
- Citation audit: parcels carried row-level citations, but multi-claim
  prose hung off a single link; the Atlas Agro claims (~$500M DC, July
  2027 deadline) had NO citation; nothing disclosed that the prose is
  AI-drafted.

**The v2 answers (all shipped):**
- Answers-first order: site pills → at-a-glance (size, units, N viable /
  N off the table, landlord, AI-disclosure, jump links) → open fit matrix
  → unit card grid + ONE drawer → cited infrastructure → collapsed
  permitting/managers/methodology. Whole dossier ≈ 3.8 screens with the
  matrix OPEN; the first screen now answers "who runs it, what fits, what's
  off the table."
- Fit cells are real `<button>`s; click expands a full-width reasoning row:
  rationale + `constraint` chip (mission/land/licensing/power/water/gas/
  workforce/security — "mission occupies land" vs "land status/designation"
  deliberately distinct per the 2026-08-24 permanence lesson) + per-cell
  `sources` + the unit's primary source. Schema enforces `constraint`.
- Best fit: rank counts only conditional-or-better; all-precluded renders
  "None — off the table" (regression-pinned).
- `narrative_note` on every payload: "AI-drafted from the cited primary
  sources and human-verified on <date>" — rendered as a visible note.
- Seven-category `infrastructure` (power_td + natural_gas added by user
  direction; water/rail/road/fiber/workforce): one cited claim per row,
  `schema.DoeInfrastructureRow`; a category with no verifiable public
  source is omitted (SRS/WIPP fiber), aggregator-only figures are hedged
  in-text ("per a siting-data aggregator").
- Prior-federal-decision-documents block in the drawer (the backlog quick
  win): NPL-sub-area units reuse the epa-superfund-docs join client-side.

## 0.1 The four sibling sites (v2)

`scripts/build_doe_sites_e2e.py` — one builder, four curated rosters, the
same payload shape, an EIGHT-source screen (NOAA West Coast CH + salmon
EFH are Pacific-scoped per the capability census; the frontend renders
screen rows only for sources a payload declares, so running them East
would have manufactured misleading zeros):

| Site | Units | The story |
|---|---|---|
| Savannah River (SC) | 5 | Amentum selected Jul 2026 to negotiate 1 GWe DC + ~2 GWe gas→advanced-nuclear on 10 tracts/3,103 ac (strong, not anchored — selection ≠ award); D-Area as DOE's own reuse-ready 210-ac powerhouse parcel; F/H tank farms + Crackerneck honestly precluded |
| Portsmouth (OH) | 5 | PORTS Technology Campus anchored (executed 189-ac lease, groundbreaking 2026-03-20, OpenAI ~8 GW); Centrus HALEU (security-precluded); X-326/OSWDF cleanup core; SODI parcels with **Oklo microreactor anchored**; X-530 grid asset + AEP $4.2B 765 kV |
| Paducah (KY) | 5 | Brookfield/NextEra 1.8 GW award anchored (~$100B); General Matter 100-ac enrichment lease; DUF6 operating; WKWMA conservation with the 545-ac carve-out precedent |
| WIPP (NM) | 2 | Operating repository precluded; the ~8,786-ac LWA balance where **water is the ranked constraint** (6.6M gal/YEAR total site allocation — large reactor water-precluded, microreactor strong, NextEra solar in realty negotiation) |

Curation provenance: four independent primary-source research passes
(numbered-claims tables with verbatim quotes, 2026-08-24); unverifiable
items excluded or hedged in-text. Two shipped-citation bugs found and
fixed along the way: `federal-clean-energy.json`'s Portsmouth row cited
the four-site Jul-2025 announcement that never names Portsmouth, and its
"345 kV" switchyard figure was uncited (museum-sourced figure is 330 kV).

---

## 1. Executive Summary & Value Proposition

The dashboard's lenses rank 46,759 sites; the Hanford tab demonstrates what
the platform can say about ONE site when everything is brought to bear —
curated ground truth, a ten-source nepa-mcp environmental screen, permitting
and licensing pathway mapping, the dashboard's own infrastructure
enrichments joined back in, and an honest per-parcel opportunity call.

Hanford is the ideal subject because a single federal boundary contains
every reuse outcome at once: a National Monument ring (foreclosed,
permanently), a National Historical Park unit (Section 106 anchor), an
operating commercial reactor corridor with an SMR project in NRC
pre-application (Cascade / Xe-100), a gigawatt-scale solar lease negotiation
under the Cleanup-to-Clean-Energy program (Cereza, now Savion), a completed
NPL-deletion-to-industrial-park hand-off (1100 Area / Horn Rapids), a
research-campus edge (300 Area / PNNL), and a Central Plateau with **no**
near-term reuse story — which the dossier says out loud. Every curated row
carries `source_url` + `verified_at` (fact-checked 2026-08-24 against an
18-claim primary-source verification pass), enforced by
`schema.HanfordParcel` + `validate_data.py`.

## 2. What shipped (v1)

- **Data**: `hanford-e2e.json` — site overview (managers, CLUP, tribal
  context), 8 permitting/licensing pathway rows (NEPA, CERCLA/TPA, NRC,
  WA EFSEC, ESA §7 dual-agency, MSA EFH, NHPA §106, CWA 404), 9 parcels ×
  {curated fields, 10-source screen, corpus join, nearby tracked records,
  opportunities with `anchored/strong/conditional/precluded` fits}.
- **Screens**: the Janus six PLUS NOAA West Coast critical habitat, salmon
  EFH, FEMA NFHL zones, GBIF occurrences — the Columbia corridor is where
  the NMFS lens earns its keep (live result: Upper Columbia spring-run
  Chinook, Endangered, Final CH at the Energy Northwest point).
- **Map packages**: 14 layers per parcel including `eis_boundaries` (the
  NEPA-precedent layer) and `wetland_regions`; ROI-feature fitBounds.
- **UI**: lazy `<template>` mount (~2 first-paint nodes), 9 ▣ markers +
  legend row eager (the artifact drives the refresh date), `<details>`
  parcel cards, delegated bindings only.
- **Tests**: 9 unit (`test_hanford_e2e.py`) + 8 e2e (`test_hanford.py`).

## 3. Roadmap (v2+)

| Phase | Deliverable | Notes |
|---|---|---|
| **H1** | **Parcel polygons.** Replace representative points with real boundaries where public: monument boundary (USFWS), MAPR park unit (NPS), NPL operable-unit polygons (EPA GeoPlatform site-boundary layer — full-coverage per `data-source-research.md`), the EA-1915 conveyance parcels | The single biggest honesty upgrade; the `coord_note` disclaimers exist because v1 is points. |
| **H2** | **DOE realty/NEPA action tracker per parcel.** CX-034321 was found by hand; DOE's NEPA reading room lists CX/EA/EIS actions by site — poll for new Hanford actions and stamp `nepa_review_document_url` per parcel | Makes `availability` self-updating evidence instead of a quarterly re-audit row. |
| **H3** | **Repeat the pattern for the other federal flagships**: INL, Oak Ridge/ETTP, Paducah, SRS (the four Jul-2025 AI-DC selections, already curated in `federal-clean-energy.json`) | `build_hanford_e2e.py` is deliberately structured as PARCELS + PATHWAYS + sources so a sibling site is a curation exercise. Do NOT genericize prematurely — two sites first, then extract what actually repeats. |
| **H4** | Tie parcels into the JTBD strip ("Solar on federal land" job → Hanford tab) and cross-link the 🏛 federal marker popup to the tab | Discovery path parity with the coal tab. |
| **H5** | Water framing: Columbia intake context (Spec 05's 7Q10 framework applied to the two river-adjacent parcels) | Wet-cooling nuclear expansion at Energy Northwest is water-gated; the AP1000 water-validation method (USGS RDB) applies directly. |

## 4. Honesty rails (carry into every v2 change)

- Coordinates are representative points; counts are buffer-intersections;
  no result is an agency determination; unavailable ≠ no-hit; opportunity
  fits are cited editorial judgements, never computed scores.
- The Central Plateau parcel exists so "remaining land" is never oversold;
  the Monument parcel exists so "off the table" renders with the same
  confidence as any opportunity. Removing either breaks the tab's point.
- NFHL-unmapped ≠ flood-free (most of Hanford is unmapped).
- Tribal geography is consultation context — treaty rights extend beyond
  mapped boundaries; Rattlesnake Mountain (Laliik) framing stays.
