#!/usr/bin/env python3
"""Build the Hanford end-to-end NEPA screening dossier (the "Hanford" tab).

The product: one DOE cleanup site — Hanford, WA — taken all the way through
what this dashboard plus PNNL's nepa-mcp can say about it. For each remaining
land unit ("parcel" here means a named sub-area of the 580-square-mile site,
never a cadastral parcel) the dossier assembles:

* curated ground truth: what the area is, who controls it, cleanup status,
  land-use designation, availability — every row cited (source_url +
  verified_at, enforced by schema.py + scripts/validate_data.py);
* a ten-source nepa-mcp environmental screen (the six Janus sources plus
  NOAA West Coast critical habitat, NOAA salmon EFH, FEMA NFHL flood zones,
  and GBIF threatened-species occurrences — the Columbia River corridor is
  exactly where the NMFS-consulted layers earn their keep);
* a Map Composer GeoJSON package (the Janus 12 layers plus EPA EIS
  boundaries and USACE wetland regions) for the map overlay;
* joins from the dashboard's OWN enrichments (the four Hanford NPL records'
  grid / rail / flood fields, and nearby tracked corpus records) — the
  "byproduct reuse" the corpus exists for;
* an opportunity assessment per parcel — solar, advanced nuclear, AI data
  center, manufacturing — each with an explicit fit judgement, rationale,
  and the NEPA / licensing / Washington-state pathway it would ride.

Run with the isolated Python 3.12 interpreter (nepa-mcp is never a project
dependency — see nepa-mcp-integration-spec.md)::

    uv run --python 3.12 --with nepa-mcp==0.1.1 \
      python scripts/build_hanford_e2e.py [--no-geojson] [--skip-screening]

``--skip-screening`` emits the curated dossier without any network calls so
the frontend can iterate offline; the shipped artifact must always come from
a full run. All queries cache under data/cache/hanford-nepa/, so re-runs
after a curation edit are nearly free.

Honesty rails (same posture as the Janus screen): coordinates are
representative points inside each named area, not parcel boundaries; counts
mean features intersect the screening buffer, not a project footprint; no
result is an agency determination; an unavailable source is never a no-hit.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import nepa_screening as screening

ROOT = SCRIPTS_DIR.parent
DATA_DIR = ROOT / "docs" / "data"
OUTPUT_PATH = DATA_DIR / "hanford-e2e.json"
GEOJSON_DIR = DATA_DIR / "hanford-nepa"
CACHE_DIR = ROOT / "data" / "cache" / "hanford-nepa"

USER_AGENT = "BrownfieldOpportunities/0.2 (Hanford E2E NEPA screening; research)"

# Parcels are internal sub-areas of one 580 sq mi site, so a Janus-style
# 10-mile buffer would blur them into near-identical screens. Five miles
# keeps each parcel's context distinct while still reaching the Columbia
# River from every developable area.
BUFFER_MILES = 5.0
# PAD-US ROI calls proved unreliable beyond point context (Janus probe);
# flood zones use a tight radius because NFHL polygons are dense where
# mapped and the question is "what zones exist near this point".
PADUS_POINT_BUFFER_MILES = 0.1
FLOOD_RADIUS_MILES = 2.0
GBIF_MIN_YEAR = 2000  # drop century-old museum records; keep modern evidence
NEARBY_RADIUS_MI = 10.0
NEARBY_LIMIT = 5

# Janus's 12 map layers plus two additions that earn their place here:
# eis_boundaries (EPA-registered EIS project boundaries — this IS the NEPA
# precedent layer) and wetland_regions (delineation-method context for the
# Columbia riparian corridor).
MAP_LAYERS = (
    "roi",
    "tribal_lands",
    "critical_habitat",
    "wildlife_refuges",
    "usace_districts",
    "wetland_regions",
    "nhd_lakes",
    "nhd_reservoirs",
    "nhd_perennial_streams",
    "nhd_stream_areas",
    "federal_lands",
    "nps_boundaries",
    "fire_perimeters",
    "eis_boundaries",
)
MAP_LAYER_BUFFER_MILES = {"federal_lands": PADUS_POINT_BUFFER_MILES}

log = logging.getLogger("hanford-e2e")

VERIFIED_AT = "2026-08-24"

# ---------------------------------------------------------------------------
# Curated ground truth. Every factual row carries its own citation; facts were
# verified against primary sources on VERIFIED_AT (see research/ notes). The
# builder validates each parcel against schema.HanfordParcel before writing —
# same live-contract discipline as the coal catalog (spec 04/08 lesson:
# curated rows can be stale the day they are written, so the contract and the
# citation are enforced, not aspirational).
# ---------------------------------------------------------------------------

SITE_OVERVIEW = {
    "name": "Hanford Site",
    "state": "WA",
    "county": "Benton",
    "size_sq_mi": 580,
    "summary": (
        "Hanford produced plutonium from 1943 to 1989 and is now the largest "
        "environmental cleanup in the United States, run by DOE's Office of "
        "Environmental Management under the 1989 Tri-Party Agreement with EPA "
        "and Washington Ecology. Cleanup progress is releasing land at the "
        "edges — a National Monument ring, an operating commercial reactor "
        "corridor, a transferred industrial park, and a gigawatt-scale solar "
        "lease negotiation — while the Central Plateau remains a dedicated "
        "waste-treatment zone for decades. That spread makes it the ideal "
        "end-to-end example: one federal site, every reuse outcome."
    ),
    "managers": [
        {
            "role": "Cleanup (site landlord)",
            "who": "DOE Office of Environmental Management — Richland Operations Office + Office of River Protection",
            "url": "https://www.hanford.gov/",
        },
        {
            "role": "Regulators",
            "who": "EPA Region 10 and Washington Dept. of Ecology under the 1989 Tri-Party Agreement",
            "url": "https://ecology.wa.gov/waste-toxics/nuclear-waste/hanford-cleanup",
        },
        {
            "role": "National Monument",
            "who": (
                "U.S. Fish & Wildlife Service (Hanford Reach National Monument, "
                "194,451 acres, proclaimed June 2000; DOE manages inner portions "
                "under interagency agreement pending cleanup)"
            ),
            "url": "https://www.fws.gov/national-monument/hanford-reach",
        },
        {
            "role": "Historical park",
            "who": "National Park Service + DOE (Manhattan Project National Historical Park, Nov 2015 MOA)",
            "url": "https://www.nps.gov/mapr/index.htm",
        },
        {
            "role": "Tribal nations",
            "who": (
                "Yakama Nation, Confederated Tribes of the Umatilla Indian "
                "Reservation, and Nez Perce Tribe hold 1855 treaty-reserved "
                "rights; the Wanapum Band (not federally recognized) is a "
                "longstanding consultation partner. Mapped geography is "
                "consultation context, never a conclusion."
            ),
            "url": "https://www.energy.gov/em/articles/hanford-hosts-roundtable-focused-tribal-government-policy",
        },
    ],
    "land_use_plan": {
        "label": "Hanford Comprehensive Land-Use Plan EIS (DOE/EIS-0222-F, Sept 1999; ROD amended 2008; SA-01 2008, SA-02 2015)",
        "url": "https://www.energy.gov/nepa/eis-0222-hanford-comprehensive-land-use-plan",
        "note": (
            "The CLUP Record of Decision set nine land-use designations — "
            "including Industrial-Exclusive (Central Plateau), Industrial, "
            "Research & Development, Conservation (Mining and Grazing), "
            "Preservation, and Recreation. Parcel rows below carry their "
            "designation where it is unambiguous."
        ),
    },
}

# The permitting / licensing pathway reference the tab renders site-wide.
# Each row: which regime, who runs it, when it binds, and the citation. This
# is deliberately a REFERENCE (what applies and who decides), never a
# schedule estimate — timelines are project-specific and asserting one from
# a screening tool would be exactly the false confidence the limitations
# text warns against.
PERMITTING_PATHWAYS = [
    {
        "regime": "NEPA (DOE lead agency)",
        "applies": (
            "Any DOE realty action — leases under the Atomic Energy Act, "
            "land-offering parcels, land transfers. DOE chooses EA "
            "vs. EIS per 10 CFR 1021; the 2023 FRA amendments set 1-year EA "
            "/ 2-year EIS targets."
        ),
        "authority": "U.S. Department of Energy (NEPA office)",
        "url": "https://www.energy.gov/nepa/",
    },
    {
        "regime": "CERCLA / Tri-Party Agreement overlay",
        "applies": (
            "All four Hanford NPL areas. Any transfer of federal property "
            "requires CERCLA 120(h) covenants or deferral; reuse inside an "
            "operable unit must not interfere with the remedy."
        ),
        "authority": "EPA Region 10 + Washington Ecology + DOE",
        "url": "https://ecology.wa.gov/waste-toxics/nuclear-waste/hanford-cleanup",
    },
    {
        "regime": "NRC licensing (commercial reactors)",
        "applies": (
            "Commercial power reactors on leased DOE land license through "
            "the NRC. Energy Northwest's Cascade Advanced Energy Facility "
            "(X-energy Xe-100) is in NRC pre-application engagement — a "
            "construction permit application has not yet been filed. "
            "DoD/DOE-authorized reactors follow their own authorization "
            "basis instead."
        ),
        "authority": "U.S. Nuclear Regulatory Commission",
        "url": "https://www.nrc.gov/reactors/new-reactors/advanced.html",
    },
    {
        "regime": "Washington EFSEC certification",
        "applies": (
            "Any nuclear power facility in Washington (no size floor), "
            "non-nuclear thermal plants at or above 350 MW, and — since the "
            "2022 E2SHB 1812 expansion — clean-energy generation, storage, "
            "manufacturing, and hydrogen projects that opt in. EFSEC site "
            "certification substitutes for local land-use approvals; the "
            "governor signs the certification."
        ),
        "authority": "WA Energy Facility Site Evaluation Council (RCW 80.50)",
        "url": "https://www.efsec.wa.gov/",
    },
    {
        "regime": "ESA Section 7 — two consulting agencies",
        "applies": (
            "USFWS consults on terrestrial/freshwater species: Umtanum "
            "desert buckwheat and White Bluffs bladderpod (both listed 2013, "
            "critical habitat of 344 and 2,861 acres on the Hanford Reach) "
            "plus bull trout. NOAA Fisheries consults on Upper Columbia "
            "spring Chinook (endangered) and steelhead (threatened). A clean "
            "IPaC pull does not clear the NMFS side — the screen below "
            "queries both. The Reach's famous fall Chinook run is NOT "
            "ESA-listed; it binds through EFH, not Section 7."
        ),
        "authority": "USFWS + NOAA Fisheries",
        "url": "https://www.federalregister.gov/documents/2013/04/23/2013-09404/endangered-and-threatened-wildlife-and-plants-designation-of-critical-habitat-for-eriogonum-codium",
    },
    {
        "regime": "Magnuson-Stevens EFH consultation",
        "applies": (
            "The Hanford Reach is Essential Fish Habitat for Chinook and "
            "coho. EFH consultation triggers on federal actions affecting "
            "EFH even for healthy, unlisted runs — the Reach's fall Chinook "
            "are the textbook case."
        ),
        "authority": "NOAA Fisheries",
        "url": "https://www.fisheries.noaa.gov/national/habitat-conservation/consultations-essential-fish-habitat",
    },
    {
        "regime": "NHPA Section 106 + tribal consultation",
        "applies": (
            "B Reactor is a National Historic Landmark inside the Manhattan "
            "Project National Historical Park; the site holds extensive "
            "pre-contact cultural resources and places of tribal "
            "significance (Rattlesnake Mountain / Laliik). Section 106 and "
            "government-to-government consultation apply to federal "
            "undertakings across the site."
        ),
        "authority": "DOE + WA SHPO + consulting Tribes + ACHP",
        "url": "https://www.nps.gov/mapr/index.htm",
    },
    {
        "regime": "Clean Water Act 404 / Rivers & Harbors 10",
        "applies": (
            "Work touching the Columbia River shoreline or jurisdictional "
            "waters. The screen below returns the USACE regulatory district "
            "and delineation region — it cannot and does not determine "
            "jurisdiction or wetland presence."
        ),
        "authority": "U.S. Army Corps of Engineers",
        "url": "https://regulatory.ops.usace.army.mil/",
    },
]

OPPORTUNITY_KINDS = {
    "solar_storage": "Utility solar + storage",
    "advanced_nuclear": "Advanced nuclear (SMR)",
    "ai_datacenter": "AI data center",
    "advanced_manufacturing": "Advanced manufacturing",
    "battery_storage": "Grid battery storage",
    "research_campus": "Research / lab campus",
    "conservation": "Conservation (status quo)",
    "heritage_tourism": "Heritage interpretation",
}

# Facility-fit summary — a dedicated data-center-vs-reactor-class comparison
# distinct from the general `opportunities` list above (which already has a
# single combined "advanced_nuclear" kind). Splitting the reactor class into
# three tiers matters because each has a different licensing pathway, water
# draw, footprint, and infrastructure precedent — the same technical axes
# this dashboard's own dc-score.js / ap1000-score.js / microreactor-score.js
# lenses already score the 46,759-site corpus on, applied qualitatively here
# since Hanford's 9 curated land units aren't part of that corpus join.
FACILITY_TYPES = {
    "data_center": {
        "label": "Data center",
        "considerations": (
            "Land + firm power + fiber. No NRC or DOE reactor authorization "
            "needed, so it is the fastest of the four to build once power is "
            "secured — but it competes for the same scarce federal-land "
            "interconnection queue as everything else on this page."
        ),
    },
    "lwr_pwr": {
        "label": "Large reactor (LWR/PWR)",
        "considerations": (
            "A ≥1,000 MWe-class unit (e.g. AP1000). Needs an NRC construction "
            "permit and operating license — or DOE authorization on federal "
            "land — roughly 27 MGD of cooling water per unit, a multi-mile "
            "emergency planning zone, and is best sited where a high-voltage "
            "switchyard and EPZ infrastructure already exist."
        ),
    },
    "smr": {
        "label": "Small modular reactor (SMR)",
        "considerations": (
            "A ~50-300 MWe modular unit (e.g. X-energy Xe-100). Same NRC/DOE "
            "licensing track as a large reactor, but a smaller footprint, "
            "lower water draw, and a tighter exclusion zone — the class "
            "Energy Northwest is already building at Hanford today."
        ),
    },
    "microreactor": {
        "label": "Microreactor",
        "considerations": (
            "A 1-20 MWe factory-built unit. DOE authorization (not NRC) is "
            "the fast path on federal land, land is a 5-acre threshold "
            "rather than a ranked factor, and the best fit is a defined "
            "anchor load or a site without existing grid access — not simply "
            "the largest available parcel."
        ),
    },
}

# Fit vocabulary rendered by the UI:
#   anchored    — the opportunity is already committed/operating on the parcel
#   strong      — evidence supports pursuing now
#   conditional — real path exists but a named gate must clear first
#   precluded   — designation or mission forecloses it (worth saying out loud)
PARCELS = [
    {
        "id": "hanford-100-area",
        "name": "100 Area — reactor row on the Columbia",
        "kind": "cleanup_area",
        "lat": 46.5492,
        "lon": -119.5054,
        "coord_note": "EPA envelope center of the 100 Area NPL polygon; the nine reactor blocks line the river to the north.",
        "approx_acres": 16000,
        "corpus_site_id": "WA3890090076",
        "clup_designation": None,
        "clup_note": (
            "River Corridor designations mix Preservation and Conservation "
            "in DOE/EIS-0222-F; confirm on the CLUP map before any parcel "
            "planning."
        ),
        "status": (
            "Nine production reactors (B through N). River Corridor surface "
            "cleanup is largely complete; reactor cores sit in interim safe "
            "storage ('cocooned') for ~75 years pending final disposition. "
            "Groundwater remedies continue along the shoreline."
        ),
        "availability": (
            "Long-term federal control. Interim-closed land with monument "
            "boundary to the north and west; not offered for reuse."
        ),
        "source_url": "https://www.epa.gov/superfund/hanford-100",
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "conservation",
                "fit": "anchored",
                "rationale": (
                    "Shoreline and bluffs adjoin the Hanford Reach National "
                    "Monument; salmon spawning habitat in the Reach is the "
                    "binding constraint on any riverfront reuse."
                ),
            },
            {
                "kind": "solar_storage",
                "fit": "precluded",
                "rationale": (
                    "Interim safe storage of reactor cores plus active "
                    "groundwater remedies leave no offerable footprint; DOE "
                    "chose its land-lease acreage elsewhere on the site."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": t,
                "fit": "precluded",
                "rationale": (
                    "Interim-closed land under long-term federal control, "
                    "with cocooned reactor cores and an active groundwater "
                    "remedy — not offered for reuse of any kind, including "
                    "this one."
                ),
            }
            for t in FACILITY_TYPES
        ],
    },
    {
        "id": "hanford-200-area",
        "name": "200 Area — Central Plateau waste core",
        "kind": "cleanup_core",
        "lat": 46.5403,
        "lon": -119.5542,
        "coord_note": "EPA envelope center spanning 200 East and 200 West.",
        "approx_acres": 47000,
        "corpus_site_id": "WA1890090078",
        "clup_designation": "Industrial-Exclusive",
        "clup_note": "The CLUP's Industrial-Exclusive core — reserved for waste management and related industrial use.",
        "status": (
            "177 underground tanks holding ~56M gallons of radioactive "
            "waste; the Waste Treatment Plant began vitrifying actual tank "
            "waste in mid-October 2025 (Direct-Feed Low-Activity Waste hot "
            "commissioning, meeting a court-ordered deadline). This is "
            "Hanford's working waste-treatment zone for decades to come."
        ),
        "availability": (
            "None. The Inner Area is the one part of Hanford with no "
            "near-term reuse story — including it keeps this dossier "
            "honest about what 'remaining land' means."
        ),
        "source_url": "https://www.epa.gov/superfund/hanford-200",
        "extra_sources": [
            {
                "label": "WA Ecology — vitrification begins (Oct 2025)",
                "url": "https://ecology.wa.gov/about-us/who-we-are/news/2025/hanford-site-waste-vitrification-begins",
            },
        ],
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "advanced_manufacturing",
                "fit": "precluded",
                "rationale": (
                    "Industrial-Exclusive designation exists to protect the "
                    "waste mission, not to host tenants; tank retrieval and "
                    "vitrification will occupy the plateau past mid-century."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": t,
                "fit": "precluded",
                "rationale": (
                    "Industrial-Exclusive zoning protects the tank-waste "
                    "mission; vitrification runs past mid-century, leaving "
                    "no offerable footprint for any of these four facility "
                    "types."
                ),
            }
            for t in FACILITY_TYPES
        ],
    },
    {
        "id": "hanford-300-area",
        "name": "300 Area — fuel-fabrication legacy, research edge",
        "kind": "cleanup_area",
        "lat": 46.4182,
        "lon": -119.34,
        "coord_note": "EPA envelope center; the area fronts the Columbia just north of Richland.",
        "approx_acres": 1500,
        "corpus_site_id": "WA2890090077",
        "clup_designation": "Industrial / Research & Development",
        "clup_note": "CLUP designates the 300 Area corridor for industrial and R&D use adjoining north Richland.",
        "status": (
            "Former uranium fuel-fabrication complex. Surface remediation "
            "and demolition are substantially complete; a persistent "
            "uranium groundwater plume is managed with enhanced-attenuation "
            "remedies along the river."
        ),
        "availability": (
            "Medium-term. Adjacent to PNNL's growing north-Richland campus; "
            "reuse must coexist with the groundwater remedy and river-side "
            "cultural resources."
        ),
        "source_url": "https://www.epa.gov/superfund/hanford-300",
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "research_campus",
                "fit": "strong",
                "rationale": (
                    "Contiguous with PNNL and Washington State University "
                    "Tri-Cities; the CLUP already points this corridor at "
                    "R&D. The groundwater remedy constrains foundations and "
                    "water use, not office/lab siting."
                ),
            },
            {
                "kind": "advanced_manufacturing",
                "fit": "conditional",
                "rationale": (
                    "Gate: CERCLA 120(h) covenants for any transfer plus "
                    "remedy-compatibility review of the uranium plume. Horn "
                    "Rapids next door shows the demand exists."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": "data_center",
                "fit": "conditional",
                "rationale": (
                    "Land and grid access support it, but groundwater-remedy "
                    "compatibility review gates any new foundation, and the "
                    "CLUP points this corridor at R&D rather than industrial "
                    "load."
                ),
            },
            {
                "type": "lwr_pwr",
                "fit": "precluded",
                "rationale": (
                    "Too small at 1,500 acres and no existing nuclear "
                    "infrastructure or emergency-planning zone — a large "
                    "reactor here starts from zero, next to an active "
                    "groundwater remedy."
                ),
            },
            {
                "type": "smr",
                "fit": "conditional",
                "rationale": (
                    "Same remedy-compatibility gate as advanced manufacturing; "
                    "a single small module could plausibly coexist with R&D "
                    "use, but no SMR offering exists on this parcel today."
                ),
            },
            {
                "type": "microreactor",
                "fit": "strong",
                "rationale": (
                    "Contiguous with PNNL — the DOE-mission R&D campus that "
                    "builds nepa-mcp itself — a small footprint easily clears "
                    "the 5-acre threshold, and federal ownership keeps the "
                    "fast DOE-authorization licensing path open. The "
                    "best-matched facility type for this parcel."
                ),
            },
        ],
    },
    {
        "id": "hanford-1100-area",
        "name": "1100 Area / Horn Rapids — the completed hand-off",
        "kind": "transferred",
        "lat": 46.3539,
        "lon": -119.2964,
        "coord_note": "Deleted-NPL 1100 Area point; the surrounding Horn Rapids industrial area is the reuse footprint.",
        "approx_acres": 768,
        "corpus_site_id": "WA4890090075",
        "clup_designation": "Industrial (transferred out of federal ownership)",
        "clup_note": "Transferred land is governed by Richland zoning, not the CLUP.",
        "status": (
            "Cleaned up, deleted from the NPL on September 30, 1996, and "
            "transferred — the first Hanford land returned to productive "
            "use. DOE's 2015 conveyance of ~1,641 more acres (NEPA review "
            "EA-1915) extended the corridor: 760 acres to the Port of "
            "Benton, 581 to the City of Richland, ~300 reserved for an "
            "Energy Northwest solar project. Framatome fabricates "
            "commercial reactor fuel here today (NRC-approved to 10% "
            "enrichment in July 2026; TerraPower HALEU metallization line "
            "completed Nov 2025)."
        ),
        "availability": (
            "Available now under Port of Benton / City of Richland "
            "ownership — the proof that the full cycle (list, clean, "
            "delete, transfer, redevelop) completes."
        ),
        "source_url": "https://www.epa.gov/superfund/hanford-1100",
        "extra_sources": [
            {
                "label": "DOE EA-1915 — 1,641-acre conveyance (2015)",
                "url": "https://www.energy.gov/nepa/ea-1915-proposed-conveyance-land-hanford-site-richland-washington",
            },
            {
                "label": "Framatome — TerraPower HALEU metallization line",
                "url": "https://www.framatome.com/medias/framatome-and-terrapower-achieve-breakthrough-in-uranium-metallization-for-advanced-reactor-fuel-commercialization/",
            },
        ],
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "advanced_manufacturing",
                "fit": "anchored",
                "rationale": (
                    "Framatome's operating fuel plant anchors the corridor, "
                    "and Atlas Agro chose it for a ~$1.5B green "
                    "nitrogen-fertilizer plant — though that project remains "
                    "gated on a ~300 MW BPA interconnection (purchase "
                    "deadline extended to July 2027). Demand is proven; "
                    "speed-to-power is the binding constraint."
                ),
            },
            {
                "kind": "ai_datacenter",
                "fit": "conditional",
                "rationale": (
                    "Gate: firm power. Atlas Agro has bundled a ~$500M data "
                    "center with its power request, but the same BPA "
                    "large-load queue paces it — and no federal AI-DC award "
                    "landed at Hanford in DOE's July 2025 selections."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": "data_center",
                "fit": "conditional",
                "rationale": (
                    "Atlas Agro has bundled a ~$500M data center with its "
                    "power request, gated on the same BPA large-load queue "
                    "as the fertilizer plant."
                ),
            },
            {
                "type": "lwr_pwr",
                "fit": "precluded",
                "rationale": (
                    "Non-federal (transferred to Port of Benton / City of "
                    "Richland), with no existing nuclear infrastructure or "
                    "emergency-planning zone — a large reactor would need an "
                    "NRC license built from scratch on land DOE no longer "
                    "controls."
                ),
            },
            {
                "type": "smr",
                "fit": "precluded",
                "rationale": (
                    "Same missing-infrastructure problem as a large reactor; "
                    "the smaller footprint doesn't change the non-federal "
                    "ownership or the absent licensing precedent."
                ),
            },
            {
                "type": "microreactor",
                "fit": "conditional",
                "rationale": (
                    "Transferred land loses the fast DOE-authorization path "
                    "(would need NRC instead), but Framatome's operating "
                    "fuel-fabrication plant is exactly the kind of anchor "
                    "industrial load a microreactor could serve if the "
                    "economics clear NRC licensing."
                ),
            },
        ],
    },
    {
        "id": "hanford-energy-northwest",
        "name": "Energy Northwest corridor — Columbia Generating Station + Xe-100",
        "kind": "leased_energy",
        "lat": 46.4716,
        "lon": -119.3339,
        "coord_note": "Columbia Generating Station reference point on Energy Northwest's leased tract.",
        "approx_acres": 1089,
        "corpus_site_id": None,
        "clup_designation": "Industrial",
        "clup_note": "Energy Northwest operates on land leased from DOE inside the site boundary.",
        "status": (
            "Columbia Generating Station (EFSEC lists 1,236 MW maximum; a "
            "BPA-approved uprate adds ~186 MW by 2031) has run on leased "
            "Hanford land since the 1980s. Adjacent, Energy Northwest's "
            "Cascade Advanced Energy Facility — X-energy Xe-100 modules "
            "backed by Amazon's TRi Energy Partnership — targets four "
            "modules (~320 MWe) initially, expandable toward twelve (~960 "
            "MWe). Design-builder selected October 2025; NRC engagement is "
            "pre-application (no construction permit application filed yet)."
        ),
        "availability": (
            "Committed to nuclear generation; the live question is how much "
            "additional co-located load and generation the corridor takes."
        ),
        "source_url": "https://www.energy-northwest.com/news-releases/energy-northwest-selects-design-builder-for-cascade-advanced-energy-facility-in-washington-state/",
        "extra_sources": [
            {
                "label": "WA EFSEC — Columbia Generating Station",
                "url": "https://efsec.wa.gov/facilities/columbia-generating-station",
            },
        ],
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "advanced_nuclear",
                "fit": "anchored",
                "rationale": (
                    "Cascade is the Pacific Northwest's flagship SMR "
                    "deployment, on a site that already hosts an operating "
                    "reactor, its emergency-planning infrastructure, and a "
                    "500 kV interconnection — with the construction-permit "
                    "filing as the next public milestone."
                ),
            },
            {
                "kind": "ai_datacenter",
                "fit": "conditional",
                "rationale": (
                    "Gate: the Xe-100 fleet reaching operation. Amazon's "
                    "participation exists precisely to pair new nuclear "
                    "output with regional data-center load."
                ),
            },
            {
                "kind": "battery_storage",
                "fit": "strong",
                "rationale": (
                    "Interconnection headroom and BPA's 500 kV backbone make "
                    "storage the cheapest complement while nuclear "
                    "construction proceeds."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": "data_center",
                "fit": "conditional",
                "rationale": (
                    "Amazon's TRi Energy Partnership exists precisely to pair "
                    "new nuclear output with data-center load, but it's gated "
                    "on the Xe-100 fleet reaching operation."
                ),
            },
            {
                "type": "lwr_pwr",
                "fit": "anchored",
                "rationale": (
                    "Columbia Generating Station (1,236 MW) has operated here "
                    "since the 1980s with its own 500 kV interconnection and "
                    "emergency-planning zone already in place — the strongest "
                    "possible precedent for a large reactor."
                ),
            },
            {
                "type": "smr",
                "fit": "anchored",
                "rationale": (
                    "Energy Northwest's Cascade Advanced Energy Facility "
                    "(Xe-100 modules, design-builder selected Oct 2025) is "
                    "already under NRC pre-application review on this "
                    "corridor."
                ),
            },
            {
                "type": "microreactor",
                "fit": "conditional",
                "rationale": (
                    "Grid-connected and licensing-mature for large and "
                    "modular reactors, but that's the opposite case a "
                    "microreactor optimizes for — a demonstration unit is "
                    "plausible here, but not the priority use."
                ),
            },
        ],
    },
    {
        "id": "hanford-clean-energy-reservation",
        "name": "Cereza solar parcel — DOE lease negotiation (Savion)",
        "kind": "leased_energy",
        "lat": 46.55,
        "lon": -119.5,
        "coord_note": (
            "Representative point from the federal land-program overlay; DOE "
            "has not published a final parcel boundary."
        ),
        "approx_acres": 8000,
        "corpus_site_id": None,
        "clup_designation": None,
        "clup_note": "Offered acreage sits within CLUP industrial/conservation designations; the lease will fix the footprint.",
        "status": (
            "Hanford is one of the original 2023 sites in DOE's land-offering "
            "initiative ('Cleanup to Clean Energy'). DOE selected Hecate Energy to negotiate a realty "
            "agreement for up to 1 GW of solar plus storage on up to 8,000 "
            "offered acres (project 'Cereza'); DOE issued categorical "
            "exclusion CX-034321 (Aug 2025) covering a license agreement "
            "and Phase I site assessment; and in February 2026 Hecate sold "
            "the up-to-2-GW Cereza project to Savion, now lead developer."
        ),
        "availability": (
            "In active development under Savion. The lease NEPA action "
            "started as a categorical exclusion for site investigations; "
            "the construction-stage review is the next public milestone."
        ),
        "source_url": "https://www.energy.gov/articles/doe-announces-cleanup-clean-energy-project-hanford-site",
        "extra_sources": [
            {
                "label": "DOE CX-034321 — Cereza license agreement categorical exclusion",
                "url": "https://www.energy.gov/nepa/articles/cx-034321-hecate-energy-cereza-llc-license-agreement-and-categorical-exclusion",
            },
            {
                "label": "Hecate Energy — sale of Cereza to Savion (Feb 2026)",
                "url": "https://www.globenewswire.com/news-release/2026/02/18/3240680/0/en/Hecate-Energy-Advances-Growth-Strategy-with-Sale-of-up-to-2-Gigawatt-Cereza-Solar-and-Storage-Project.html",
            },
        ],
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "solar_storage",
                "fit": "anchored",
                "rationale": (
                    "DOE selected the acreage and a developer, the first "
                    "NEPA action (CX-034321) is complete, and the project "
                    "traded to Savion at up-to-2-GW scale — the screening "
                    "question is which footprint clears cultural and "
                    "habitat review fastest."
                ),
            },
            {
                "kind": "advanced_nuclear",
                "fit": "conditional",
                "rationale": (
                    "Gate: DOE choosing to offer additional acreage. The "
                    "same attributes (federal control, grid, water, "
                    "workforce) that drew the solar RFQ apply to reactors — "
                    "but no nuclear offering exists on this parcel today."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": "data_center",
                "fit": "conditional",
                "rationale": (
                    "The offered acreage is earmarked for solar plus storage "
                    "under an active DOE lease negotiation; a data center "
                    "would need its own separate federal land offering."
                ),
            },
            {
                "type": "lwr_pwr",
                "fit": "conditional",
                "rationale": (
                    "The same attributes that drew the solar RFQ (federal "
                    "control, grid, water, workforce) apply to a large "
                    "reactor, but no nuclear offering exists on this parcel "
                    "today."
                ),
            },
            {
                "type": "smr",
                "fit": "conditional",
                "rationale": "Same reasoning as the large-reactor case, at smaller scale — no offering exists today.",
            },
            {
                "type": "microreactor",
                "fit": "conditional",
                "rationale": (
                    "8,000 acres is far more than any microreactor needs, "
                    "and DOE's authorization pathway is available on this "
                    "federal land, but the acreage is already committed to "
                    "the solar lease negotiation."
                ),
            },
        ],
    },
    {
        "id": "hanford-reach-monument",
        "name": "Hanford Reach National Monument / ALE — the foreclosed ring",
        "kind": "conservation",
        "lat": 46.4436,
        "lon": -119.6011,
        "coord_note": "Rattlesnake Mountain summit reference point on the Arid Lands Ecology Reserve.",
        "approx_acres": 194451,
        "corpus_site_id": None,
        "clup_designation": "Preservation",
        "clup_note": "Monument proclamation 7319 (June 2000) plus CLUP Preservation designation.",
        "status": (
            "The security buffer that accidentally became one of the best "
            "shrub-steppe reserves in the Columbia Basin — proclaimed a "
            "194,451-acre National Monument in June 2000, primarily "
            "USFWS-managed, holding the last free-flowing non-tidal stretch "
            "of the Columbia and Rattlesnake Mountain (Laliik), sacred as "
            "the birthplace of the Washani faith."
        ),
        "availability": (
            "None, permanently. Shown because an honest siting tool must "
            "render 'this land is off the table' with the same confidence "
            "as any opportunity."
        ),
        "source_url": "https://www.fws.gov/national-monument/hanford-reach",
        "extra_sources": [
            {
                "label": "Proclamation — Hanford Reach National Monument (June 2000)",
                "url": "https://clintonwhitehouse3.archives.gov/CEQ/hanford_reach.html",
            },
        ],
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "conservation",
                "fit": "anchored",
                "rationale": (
                    "Monument status, two listed endemic plants with 344 and "
                    "2,861 acres of designated critical habitat, "
                    "fall-Chinook spawning grounds, and treaty-era cultural "
                    "landscapes all point one direction."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": t,
                "fit": "precluded",
                "rationale": (
                    "National Monument proclamation, listed-species critical "
                    "habitat, and treaty-era cultural landscapes foreclose "
                    "any industrial or energy development, including this "
                    "one."
                ),
            }
            for t in FACILITY_TYPES
        ],
    },
    {
        "id": "hanford-b-reactor",
        "name": "B Reactor — Manhattan Project National Historical Park",
        "kind": "cultural",
        "lat": 46.6303,
        "lon": -119.6467,
        "coord_note": "B Reactor building reference point.",
        "approx_acres": 20,
        "corpus_site_id": None,
        "clup_designation": "Preservation (public access)",
        "clup_note": "Operated for public tours under the DOE–NPS park agreement.",
        "status": (
            "The world's first full-scale plutonium production reactor "
            "(1944), a National Historic Landmark since August 2008, and "
            "the Hanford unit of the Manhattan Project National Historical "
            "Park since November 2015."
        ),
        "availability": (
            "Preserved. Its role in a siting dossier is as the Section 106 "
            "anchor: undertakings nearby inherit a historic-preservation "
            "consultation burden."
        ),
        "source_url": "https://www.nps.gov/mapr/index.htm",
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "heritage_tourism",
                "fit": "anchored",
                "rationale": (
                    "Public tours run today; interpretation is the highest "
                    "and best use, and the park boundary is a hard "
                    "constraint on neighboring development."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": t,
                "fit": "precluded",
                "rationale": (
                    "Manhattan Project National Historical Park boundary and "
                    "the Section 106 historic-preservation consultation it "
                    "triggers rule out any new industrial or energy facility "
                    "here, including this one."
                ),
            }
            for t in FACILITY_TYPES
        ],
    },
    {
        "id": "pnnl-campus",
        "name": "PNNL campus — the lab next door (context)",
        "kind": "context_campus",
        "lat": 46.3454,
        "lon": -119.2788,
        "coord_note": "PNNL main campus, north Richland — adjacent to, not inside, the cleanup footprint.",
        "approx_acres": 350,
        "corpus_site_id": None,
        "clup_designation": None,
        "clup_note": "City of Richland jurisdiction; included as workforce and R&D context, not DOE-EM land.",
        "status": (
            "Pacific Northwest National Laboratory — the DOE Office of "
            "Science lab operated by Battelle — anchors the region's "
            "technical workforce. It is also, fittingly, the lab that "
            "builds nepa-mcp: the screening tool generating this dossier."
        ),
        "availability": (
            "Not applicable (operating federal lab campus); listed as the "
            "workforce-anchor context every opportunity above leans on."
        ),
        "source_url": "https://www.pnnl.gov/",
        "verified_at": VERIFIED_AT,
        "opportunities": [
            {
                "kind": "research_campus",
                "fit": "anchored",
                "rationale": (
                    "Thousands of scientists and engineers within commuting "
                    "distance of every parcel in this dossier — the "
                    "workforce signal the AP1000 lens weights 15/100."
                ),
            },
        ],
        "facility_fit": [
            {
                "type": t,
                "fit": "precluded",
                "rationale": (
                    "An operating DOE Office of Science lab campus, not "
                    "offerable industrial land — its value to this comparison "
                    "is as the workforce anchor the nearby 300 Area's "
                    "microreactor fit leans on."
                ),
            }
            for t in FACILITY_TYPES
        ],
    },
]

SOURCE_META = {
    "ipac": {
        "label": "USFWS IPaC",
        "url": "https://ipac.ecosphere.fws.gov/",
        "covers": "ESA species, critical habitat, migratory birds, wetlands, refuges (USFWS lens)",
    },
    "noaa": {
        "label": "NOAA West Coast critical habitat",
        "url": "https://www.fisheries.noaa.gov/national/endangered-species-conservation/critical-habitat",
        "covers": "NMFS-designated critical habitat (salmon, steelhead); the consulting agency IPaC does not cover",
    },
    "efh_salmon": {
        "label": "NOAA salmon Essential Fish Habitat",
        "url": "https://www.fisheries.noaa.gov/national/habitat-conservation/consultations-essential-fish-habitat",
        "covers": "Magnuson-Stevens EFH by HUC-8 watershed; triggers consultation even for unlisted runs",
    },
    "tribal": {
        "label": "Census TIGERweb AIANNHA",
        "url": "https://tigerweb.geo.census.gov/tigerwebmain/TIGERweb_apps.html",
        "covers": "mapped tribal geographies; treaty rights extend beyond mapped boundaries",
    },
    "nrhp": {
        "label": "National Park Service NRHP",
        "url": "https://www.nps.gov/subjects/nationalregister/database-research.htm",
        "covers": "listed historic properties; not eligible-but-unlisted resources",
    },
    "padus": {
        "label": "USGS PAD-US 4.1",
        "url": "https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-overview",
        "covers": "protected-area context at the parcel reference point (0.1-mile query)",
    },
    "usace": {
        "label": "USACE regulatory boundaries and wetland regions",
        "url": "https://regulatory.ops.usace.army.mil/",
        "covers": "district and delineation method; not wetland presence or jurisdiction",
    },
    "fema_nfhl": {
        "label": "FEMA National Flood Hazard Layer",
        "url": "https://www.fema.gov/flood-maps/national-flood-hazard-layer",
        "covers": "mapped flood zones within 2 miles; much of Hanford is unmapped in NFHL — unmapped is not flood-free",
    },
    "gbif": {
        "label": "GBIF threatened-species occurrences",
        "url": "https://www.gbif.org/",
        "covers": "presence-only observation records since 2000; absence of records is absence of observers",
    },
    "nepa_assist": {
        "label": "EPA NEPAssist",
        "url": "https://nepassisttool.epa.gov/nepassist/nepamap.aspx",
        "covers": "environmental proximity flags from EPA screening services",
    },
    "map_composer": {
        "label": "PNNL NEPA MCP Map Composer",
        "url": "https://pnnl.github.io/nepa-mcp/",
        "covers": "provenance-rich federal GIS features clipped to the screening buffer, incl. EPA EIS boundaries",
    },
}

LIMITATIONS = [
    "Coordinates are representative points inside named areas, not parcel boundaries.",
    "Counts mean features intersect the screening buffer, not a project footprint.",
    "No result is an agency determination, permit conclusion, or suitability score.",
    "An unavailable source is never treated as a no-hit.",
    "Opportunity fits are curated editorial judgements with citations — screening evidence informs them, it does not compute them.",
    "Much of Hanford is unmapped in FEMA's NFHL; zero mapped flood zones does not mean flood-free.",
]


def cache_path(parcel_id: str, source: str) -> Path:
    """Cache naming for this builder: <parcel>--<source>.json (no legacy quirks)."""
    return CACHE_DIR / f"{parcel_id}--{source}.json"


def _source_defs() -> "tuple[screening.SourceDef, ...]":
    """The ten tabular sources. Order matters only for log readability."""
    normalize_padus = screening.make_normalize_padus(PADUS_POINT_BUFFER_MILES)
    return (
        screening.SourceDef(
            "ipac", "ipac", "get_ipac_resources_in_roi", screening.normalize_ipac,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "noaa", "noaa", "get_noaa_critical_habitat_in_roi", screening.normalize_noaa_habitat,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "efh_salmon", "efh", "get_salmon_efh_in_roi", screening.normalize_efh_salmon,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "tribal", "tribal", "get_tribal_lands_in_roi", screening.normalize_tribal,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "nrhp", "nrhp", "get_nrhp_properties_in_roi", screening.normalize_nrhp,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "padus", "padus", "get_padus_in_roi", normalize_padus,
            lambda fn, s: fn(s["lat"], s["lon"], PADUS_POINT_BUFFER_MILES),
        ),
        screening.SourceDef(
            "usace", "usace", "analyze_usace_jurisdiction", screening.normalize_usace,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "fema_nfhl", "fema_nfhl", "get_flood_zones", screening.normalize_flood_zones,
            lambda fn, s: fn(s["lat"], s["lon"], FLOOD_RADIUS_MILES),
        ),
        screening.SourceDef(
            "gbif", "gbif", "get_gbif_occurrences_in_roi", screening.normalize_gbif,
            lambda fn, s: fn(
                s["lat"], s["lon"], BUFFER_MILES,
                threatened_only=True, min_year=GBIF_MIN_YEAR,
            ),
        ),
        screening.SourceDef(
            "nepa_assist", "nepa_assist", "query_nepa_assist", screening.normalize_nepa_assist,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES, f"Hanford E2E — {s['name']}"),
        ),
    )


# ---------------------------------------------------------------------------
# Corpus joins — reuse what the dashboard already computed instead of
# re-deriving it. Fill-if-present, clearly labeled; the four NPL parcels get
# their program record's grid/rail/flood fields, and every parcel gets its
# nearest tracked corpus records as a discovery path into the detail panel.
# ---------------------------------------------------------------------------

CORPUS_JOIN_FIELDS = (
    "acreage", "npl_status", "npl_status_code", "profile_url",
    "transmission_mi", "transmission_kv", "substation_mi", "substation_kv",
    "rail_mi", "highway_mi", "gas_pipeline_mi", "flood_zone", "in_sfha",
    "power_plant_mi", "power_plant_mw", "power_plant_fuel", "iso_rto",
)

PROGRAM_FILES = ("sites.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json")
ENRICHMENT_FILES = ("infra-proximity.json", "iso-rto.json")


def _records(payload: Any) -> "list[dict[str, Any]]":
    """Every repo data file wraps rows as either {'sites': []} or a bare list."""
    if isinstance(payload, dict):
        return payload.get("sites") or payload.get("records") or []
    return payload or []


def load_corpus_index() -> "tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]":
    """Merged corpus view (program record + fill-if-empty enrichments).

    Mirrors the frontend's ensure*Loaded() join semantics: the program
    record owns core fields; enrichment files only fill absences. A checker
    or join that models the merge differently manufactures findings — the
    2026-08-09 Lipschitz lesson.
    """
    by_id: "dict[str, dict[str, Any]]" = {}
    all_records: "list[dict[str, Any]]" = []
    for fname in PROGRAM_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            continue
        for rec in _records(json.loads(path.read_text())):
            if rec.get("id") and rec["id"] not in by_id:
                by_id[rec["id"]] = dict(rec)
                all_records.append(by_id[rec["id"]])
    for fname in ENRICHMENT_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            continue
        for rec in _records(json.loads(path.read_text())):
            existing = by_id.get(rec.get("id"))
            if not existing:
                continue
            for key, value in rec.items():
                if key == "id" or value is None:
                    continue
                if existing.get(key) is None:
                    existing[key] = value
    return by_id, all_records


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles (exact enough at CONUS scale)."""
    rad = math.pi / 180.0
    dlat = (lat2 - lat1) * rad
    dlon = (lon2 - lon1) * rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    )
    return 3958.7613 * 2 * math.asin(math.sqrt(a))


def nearby_tracked_records(
    parcel: "dict[str, Any]", all_records: "list[dict[str, Any]]"
) -> "list[dict[str, Any]]":
    """Nearest corpus records within NEARBY_RADIUS_MI (excluding self-joins).

    A cheap lat/lon box pre-filter skips ~99% of the 46k records before any
    trig — same pattern as the frontend's renderNearbySites().
    """
    lat, lon = parcel["lat"], parcel["lon"]
    lat_delta = NEARBY_RADIUS_MI / 69.0
    lon_delta = NEARBY_RADIUS_MI / (69.0 * max(0.2, math.cos(lat * math.pi / 180.0)))
    hits = []
    for rec in all_records:
        rlat, rlon = rec.get("lat"), rec.get("lon")
        if rlat is None or rlon is None:
            continue
        if abs(rlat - lat) > lat_delta or abs(rlon - lon) > lon_delta:
            continue
        if rec["id"] == parcel.get("corpus_site_id"):
            continue
        d = haversine_mi(lat, lon, rlat, rlon)
        if d <= NEARBY_RADIUS_MI:
            hits.append((d, rec))
    hits.sort(key=lambda pair: pair[0])
    return [
        {
            "id": rec["id"],
            "name": rec.get("name"),
            "program": rec.get("program"),
            "distance_mi": round(d, 1),
        }
        for d, rec in hits[:NEARBY_LIMIT]
    ]


def validate_parcels() -> None:
    """Contract check before any network spend: unique ids, cited rows, and
    the live schema.HanfordParcel validation (imported from the project root
    so the CI validator and this builder can never disagree about shape)."""
    ids = [p["id"] for p in PARCELS]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate parcel ids in PARCELS")
    for parcel in PARCELS:
        if not str(parcel.get("source_url", "")).startswith("https://"):
            raise SystemExit(f"{parcel['id']}: missing https source_url")
        if len(str(parcel.get("verified_at", ""))) != 10:
            raise SystemExit(f"{parcel['id']}: missing verified_at stamp")
        for opp in parcel.get("opportunities", []):
            if opp["kind"] not in OPPORTUNITY_KINDS:
                raise SystemExit(f"{parcel['id']}: unknown opportunity kind {opp['kind']}")
            if opp["fit"] not in {"anchored", "strong", "conditional", "precluded"}:
                raise SystemExit(f"{parcel['id']}: unknown fit {opp['fit']}")
        facility_types = [ff["type"] for ff in parcel.get("facility_fit", [])]
        if sorted(facility_types) != sorted(FACILITY_TYPES):
            raise SystemExit(
                f"{parcel['id']}: facility_fit must cover exactly {sorted(FACILITY_TYPES)}, got {sorted(facility_types)}"
            )
        for ff in parcel.get("facility_fit", []):
            if ff["fit"] not in {"anchored", "strong", "conditional", "precluded"}:
                raise SystemExit(f"{parcel['id']}: unknown facility_fit fit {ff['fit']}")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        import schema as schema_mod
    except Exception as exc:  # pydantic absent on this interpreter — CI still validates
        log.warning("schema.py unavailable on this interpreter (%s); CI validator still enforces it", exc)
        return
    for parcel in PARCELS:
        # Validate the row exactly as curated — no defaulting: a parcel
        # missing `opportunities` must fail Pydantic's required-field check
        # here, before any network spend (PR #22 review finding 3).
        schema_mod.HanfordParcel.model_validate(parcel)


def build_screening(parcels: "list[dict[str, Any]]", use_cache: bool) -> dict:
    return screening.run_source_matrix(
        parcels, _source_defs(), cache_path_fn=cache_path, use_cache=use_cache
    )


def build_geojson(parcel: "dict[str, Any]", use_cache: bool) -> dict:
    return screening.collect_map_geojson(
        parcel,
        MAP_LAYERS,
        BUFFER_MILES,
        cache_file=cache_path(parcel["id"], "map-composer"),
        layer_buffer_overrides=MAP_LAYER_BUFFER_MILES,
        use_cache=use_cache,
        limitations=(
            "Representative-point screening only; parcel boundary unknown. "
            "Unavailable layers are not no-hit findings."
        ),
    )


def write_output(
    parcels: "list[dict[str, Any]]",
    tabular: dict,
    geojson_by_id: dict,
    corpus_by_id: "dict[str, dict[str, Any]]",
    all_records: "list[dict[str, Any]]",
    merge_existing: bool = False,
) -> None:
    GEOJSON_DIR.mkdir(parents=True, exist_ok=True)
    out_parcels = []
    for parcel in parcels:
        row = dict(parcel)
        row["screening"] = tabular.get(parcel["id"], {})
        geojson = geojson_by_id.get(parcel["id"])
        # A package that failed wholesale (main() records an empty
        # FeatureCollection with metadata.status="unavailable") must NOT
        # publish a geojson_url — "Show 0 features" + a success toast would
        # turn an upstream failure into an apparent no-hit (Codex PR #22 P2).
        # A legitimately empty package still carries per-layer statuses and
        # no unavailable marker, so it stays publishable.
        meta = (geojson or {}).get("metadata") or {}
        if (
            geojson
            and geojson.get("features") is not None
            and meta.get("status") != "unavailable"
        ):
            path = GEOJSON_DIR / f"{parcel['id']}.geojson"
            path.write_text(json.dumps(geojson, separators=(",", ":")))
            row["geojson_url"] = f"data/hanford-nepa/{parcel['id']}.geojson"
            row["map_summary"] = screening.summarize_map_package(geojson)
        else:
            row["geojson_url"] = None
            row["map_summary"] = None
        corpus_rec = corpus_by_id.get(parcel.get("corpus_site_id") or "")
        row["corpus_record"] = (
            {k: corpus_rec.get(k) for k in CORPUS_JOIN_FIELDS if corpus_rec.get(k) is not None}
            if corpus_rec
            else None
        )
        row["nearby_tracked"] = nearby_tracked_records(parcel, all_records)
        out_parcels.append(row)

    if merge_existing:
        # A --parcel refresh must never truncate the published dossier to
        # the selected rows (Codex PR #22 P1 — the same empty/partial-write
        # class as the Janus --site path, which this mirrors): merge the
        # rebuilt rows over the existing inventory, keeping curated order.
        if not OUTPUT_PATH.exists():
            raise RuntimeError("--parcel requires an existing complete hanford-e2e.json")
        existing = json.loads(OUTPUT_PATH.read_text())
        existing_by_id = {p["id"]: p for p in existing.get("parcels", [])}
        for row in out_parcels:
            prev = existing_by_id.get(row["id"])
            if not prev:
                continue
            # Carry forward evidence this run did not (re)produce — a
            # curated-text refresh via --skip-screening / --no-geojson must
            # never blank a parcel's screen or map package, and a FAILED
            # fresh package must not delete a good prior one (the flood-seed
            # pattern: prior evidence survives until replaced; PR #22 review
            # finding 2).
            if not row.get("screening"):
                row["screening"] = prev.get("screening") or {}
            if row.get("geojson_url") is None and prev.get("geojson_url") is not None:
                row["geojson_url"] = prev["geojson_url"]
                row["map_summary"] = prev.get("map_summary")
        by_id = dict(existing_by_id)
        by_id.update({p["id"]: p for p in out_parcels})
        order = {p["id"]: i for i, p in enumerate(PARCELS)}
        out_parcels = sorted(by_id.values(), key=lambda row: order.get(row["id"], len(order)))

    payload = {
        "generated_at": screening.utc_now(),
        "nepa_mcp_version": screening.NEPA_MCP_VERSION,
        "screening_buffer_miles": BUFFER_MILES,
        "flood_radius_miles": FLOOD_RADIUS_MILES,
        "parcel_count": len(out_parcels),
        "method": (
            "PNNL nepa-mcp structured APIs and Map Composer layers, cached and "
            "rate-limited to at least 1.5 seconds between requests per host; "
            "curated parcel facts verified against primary sources; corpus "
            "fields joined from this project's own enrichment files."
        ),
        "site_overview": SITE_OVERVIEW,
        "permitting_pathways": PERMITTING_PATHWAYS,
        "opportunity_kinds": OPPORTUNITY_KINDS,
        "facility_types": FACILITY_TYPES,
        "limitations": LIMITATIONS,
        "sources": SOURCE_META,
        "parcels": out_parcels,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    log.info("wrote %s (%d parcels)", OUTPUT_PATH, len(out_parcels))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parcel", action="append", default=[], help="Only screen this parcel id")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached source responses")
    parser.add_argument("--no-geojson", action="store_true", help="Skip Map Composer GeoJSON")
    parser.add_argument(
        "--skip-screening", action="store_true",
        help="Emit curated dossier without network (frontend iteration only)",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    validate_parcels()
    parcels = [p for p in PARCELS if not args.parcel or p["id"] in set(args.parcel)]
    if not parcels:
        raise SystemExit("no parcels selected")

    corpus_by_id, all_records = load_corpus_index()

    if args.skip_screening:
        write_output(
            parcels, {}, {}, corpus_by_id, all_records,
            merge_existing=bool(args.parcel),
        )
        return 0

    screening.prefer_ipv4()
    screening.install_request_throttle(USER_AGENT)
    tabular = build_screening(parcels, use_cache=not args.no_cache)
    geojson_by_id: "dict[str, dict[str, Any]]" = {}
    if not args.no_geojson:
        for parcel in parcels:
            try:
                geojson_by_id[parcel["id"]] = build_geojson(parcel, use_cache=not args.no_cache)
            except Exception as exc:
                log.exception("%s / map-composer failed", parcel["id"])
                geojson_by_id[parcel["id"]] = {
                    "type": "FeatureCollection",
                    "features": [],
                    "metadata": {"status": "unavailable", "error": str(exc)},
                }
    write_output(
        parcels, tabular, geojson_by_id, corpus_by_id, all_records,
        merge_existing=bool(args.parcel),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
