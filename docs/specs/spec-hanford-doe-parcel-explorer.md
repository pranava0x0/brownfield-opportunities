# Spec 11: Hanford E2E — DOE Parcel Explorer & the Federal-Site Dossier Pattern

**Status:** v1 shipped 2026-08-24 — "Hanford" tab (ninth tab), 9-parcel dossier, ten-source screen, 14-layer map packages, corpus joins, opportunity assessments
**Priority:** High (Impact: 5/5, Size: 3/5, Completeness: 4/5)
**Target Version:** v1.15.x
**Lead Component:** `scripts/build_hanford_e2e.py`, `docs/data/hanford-e2e.json`, `docs/data/hanford-nepa/*.geojson`, `docs/app.js` (Hanford module), `schema.py::HanfordParcel`

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
