"""Build the SRS / Portsmouth / Paducah / WIPP end-to-end dossiers.

Sibling of scripts/build_hanford_e2e.py — one curated file for the four
non-Hanford DOE sites of the DOE Sites tab, sharing that builder's generic
machinery (corpus join, nearby-tracked, Map Composer layers) and the
scripts/nepa_screening.py engine. Each site emits docs/data/<site>-e2e.json
plus docs/data/<site>-nepa/*.geojson with the SAME payload shape as
hanford-e2e.json, so the frontend renders all five sites through one code
path.

Two deliberate differences from Hanford:

* **Eight-source screen, not ten.** The NOAA West Coast critical-habitat and
  salmon-EFH tools are Pacific-scoped (capability census 2026-08); running
  them at an East/interior site would return misleading zeros. The frontend
  renders screen rows only for sources a payload declares.
* **These files are lazy-loaded** (on site-pill selection), so their loaders
  never call recordRefreshDate (the reference-campuses rule) and the files
  stay out of test_refresh_date_reflects_freshest_data_file's list.

Curation provenance: every row carries source_url + verified_at and was
assembled 2026-08-24 from four primary-source research passes (numbered
claims tables with verbatim quotes; unverifiable items were excluded or
hedged in the text itself — e.g. "per a siting-data aggregator"). The
builder validates every parcel against schema.HanfordParcel and every
infrastructure row against schema.DoeInfrastructureRow before any network
spend.

Run (screening requires the isolated nepa-mcp interpreter)::

    uv run --python 3.12 --with nepa-mcp==0.1.1 \
        python scripts/build_doe_sites_e2e.py --site srs

    # curated-text iteration without network:
    python3 scripts/build_doe_sites_e2e.py --site srs --skip-screening \
        --parcel srs-ai-lease-area ... (every parcel being touched)

NEVER run this concurrently with build_hanford_e2e.py / build_janus_nepa.py /
build_coal_nepa.py — the 1.5 s/host throttle is per-process.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import nepa_screening as screening
import build_hanford_e2e as hanford  # generic machinery only; no CLI side effects

ROOT = SCRIPTS_DIR.parent
DATA_DIR = ROOT / "docs" / "data"
CACHE_ROOT = ROOT / "data" / "cache"

USER_AGENT = "BrownfieldOpportunities/0.2 (DOE sites E2E NEPA screening; research)"

VERIFIED_AT = "2026-08-24"
BUFFER_MILES = hanford.BUFFER_MILES
PADUS_POINT_BUFFER_MILES = hanford.PADUS_POINT_BUFFER_MILES
FLOOD_RADIUS_MILES = hanford.FLOOD_RADIUS_MILES
GBIF_MIN_YEAR = hanford.GBIF_MIN_YEAR
MAP_LAYERS = hanford.MAP_LAYERS
MAP_LAYER_BUFFER_MILES = hanford.MAP_LAYER_BUFFER_MILES

log = logging.getLogger("doe-sites-e2e")

FIT_VALUES = {"anchored", "strong", "conditional", "precluded"}

# One shared vocabulary across all four sites (labels render from the
# payload, so the frontend never hardcodes them).
OPPORTUNITY_KINDS = {
    "solar_storage": "Utility solar + storage",
    "advanced_nuclear": "Advanced nuclear",
    "ai_datacenter": "AI data center",
    "advanced_manufacturing": "Advanced manufacturing",
    "battery_storage": "Grid battery storage",
    "research_campus": "Research / lab campus",
    "conservation": "Conservation (status quo)",
    "heritage_tourism": "Heritage interpretation",
    "gas_generation": "Gas generation",
    "hydrogen_ammonia": "Hydrogen / ammonia",
    "nuclear_fuel_cycle": "Nuclear fuel cycle",
    "waste_disposal": "Waste mission (operating)",
}

# Site-agnostic facility-type criteria (the Hanford file keeps its own,
# Hanford-flavored copy; these four sites share this generic set).
FACILITY_TYPES = {
    "data_center": {
        "label": "Data center",
        "considerations": (
            "Land + firm power + fiber. No NRC or DOE reactor authorization "
            "needed, so it is the fastest of the four to build once power is "
            "secured — but it competes for the same scarce federal-land "
            "interconnection queue as everything else on this page."
        ),
        "source_url": "https://www.epa.gov/re-powering",
        "verified_at": VERIFIED_AT,
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
        "source_url": "https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf",
        "verified_at": VERIFIED_AT,
    },
    "smr": {
        "label": "Small modular reactor (SMR)",
        "considerations": (
            "A ~50-300 MWe modular unit. Same NRC/DOE licensing track as a "
            "large reactor, but a smaller footprint, lower water draw, and a "
            "tighter exclusion zone. Executive Order 14299 (May 23, 2025) "
            "directs DOE to use its authorization authority for privately "
            "funded advanced reactors on DOE sites — the pathway every "
            "'advanced nuclear' plan on this page leans on."
        ),
        "source_url": "https://www.energy.gov/ne/articles/5-fast-facts-about-doe-reactor-authorization",
        "verified_at": VERIFIED_AT,
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
        "source_url": "https://www.datacenterfrontier.com/energy/article/55232808/westinghouse-evinci-microreactor-could-yield-5-mw-of-nuclear-power-every-8-years-for-ai-data-centers",
        "verified_at": VERIFIED_AT,
    },
}

# The 8-source screen (Hanford's ten minus the two Pacific-marine tools).
SOURCE_META = {
    key: dict(meta) for key, meta in hanford.SOURCE_META.items()
    if key not in ("noaa", "efh_salmon")
}

NARRATIVE_NOTE_TEMPLATE = (
    "Narrative text in this dossier (site history, unit status, availability, "
    "and fit rationales) is AI-drafted from the primary sources cited on each "
    "row and human-verified against them on {date}. Numbers and dated facts "
    "each carry their citation; screening rows are live tool output, never "
    "prose. No text on this page is an agency determination."
)

SHARED_LIMITATIONS = [
    "Coordinates are representative points inside named areas, not parcel boundaries.",
    "Counts mean features intersect the screening buffer, not a project footprint.",
    "No result is an agency determination, permit conclusion, or suitability score.",
    "An unavailable source is never treated as a no-hit.",
    "Opportunity and facility fits are curated editorial judgements with citations — screening evidence informs them, it does not compute them.",
    "NFHL map coverage varies by county; zero mapped flood zones does not mean flood-free.",
]

FLOOD_UNMAPPED_NOTE = "NFHL coverage varies here — unmapped is not flood-free"


# ---------------------------------------------------------------------------
# Savannah River Site (SC)
# ---------------------------------------------------------------------------

SRS_SITE = {
    "site_id": "srs",
    "site_label": "Savannah River",
    "site_overview": {
        "name": "Savannah River Site",
        "state": "SC",
        "county": "Aiken / Barnwell / Allendale",
        "size_sq_mi": 310,
        "summary": (
            "SRS produced plutonium and tritium for the weapons program from "
            "1951 (five heavy-water reactors, all shut down by end of 1988) "
            "and now pairs the DOE-EM cleanup with expanding NNSA missions — "
            "sole-source tritium, and plutonium pit production in the former "
            "MOX building. NNSA became the site landlord on October 1, 2024, "
            "with EM continuing as the cleanup tenant. In July 2026 NNSA "
            "selected Amentum to negotiate a phased lease for a 1 GWe AI "
            "data center backed by ~2 GWe of co-located generation — gas "
            "first, transitioning to advanced nuclear — on 10 identified "
            "tracts totaling 3,103 acres."
        ),
        "managers": [
            {
                "role": "Landlord (since Oct 2024)",
                "who": "NNSA Savannah River Field Office — site authority and stewardship; DOE-EM continues the cleanup mission as a tenant",
                "url": "https://www.energy.gov/srs/articles/em-nnsa-landlord-transition-complete-savannah-river-site",
            },
            {
                "role": "Regulators",
                "who": (
                    "EPA Region 4 and the SC Dept. of Environmental Services "
                    "(successor to DHEC's environmental programs, July 2024) "
                    "under the Federal Facility Agreement effective Aug 16, 1993"
                ),
                "url": "https://www.srs.gov/general/programs/soil/ffa/",
            },
            {
                "role": "M&O contractor",
                "who": "Savannah River Nuclear Solutions (through Sept 2026 + one option year); liquid waste: Savannah River Mission Completion; SRNL: Battelle Savannah River Alliance",
                "url": "https://www.energy.gov/srs/savannah-river-site",
            },
            {
                "role": "Research park",
                "who": "The AEC designated 192,323 acres as the nation's first National Environmental Research Park (June 20, 1972); UGA's Savannah River Ecology Laboratory co-manages ecological research",
                "url": "https://srel.uga.edu/",
            },
        ],
        "land_use_plan": {
            "label": "SRS Land Use Baseline Report (WSRC, 1995) + SRS Land Use Plan (updated May 2013)",
            "url": "https://digital.library.unt.edu/ark:/67531/metadc626351/",
            "note": (
                "All SRS land is DOE-owned; use is governed by NEPA, RCRA, "
                "and CERCLA with the 1995 baseline report and later land-use "
                "plans as the framework documents."
            ),
        },
    },
    "permitting_pathways": [
        {
            "regime": "CERCLA Federal Facility Agreement",
            "applies": (
                "Governs all environmental remediation across SRS's ~515 "
                "operable units (408 complete / 10 in remediation per the "
                "EPA profile). DOE leads remedial action with EPA Region 4 "
                "and SC DES concurrence; effective Aug 16, 1993."
            ),
            "authority": "EPA Region 4 + SC Dept. of Environmental Services + DOE",
            "url": "https://www.srs.gov/general/programs/soil/ffa/",
        },
        {
            "regime": "DOE reactor authorization (Atomic Energy Act)",
            "applies": (
                "Executive Order 14299 (May 23, 2025) directs DOE to use its "
                "authorization authority for privately funded advanced "
                "reactors on DOE sites — the pathway the Amentum project's "
                "gas-to-nuclear generation plan would lean on for any "
                "DOE-authorized unit; NRC licensing remains the alternative."
            ),
            "authority": "U.S. Department of Energy",
            "url": "https://www.energy.gov/ne/articles/5-fast-facts-about-doe-reactor-authorization",
        },
        {
            "regime": "SC PSC siting certificate (S.C. Code Title 58, Ch. 33)",
            "applies": (
                "A state certificate applies to SC-jurisdictional utilities "
                "building >75 MW generation or ≥125 kV lines. Whether it "
                "reaches a behind-the-fence, non-utility project on the "
                "federal enclave is UNCONFIRMED — an open question, not a "
                "settled answer."
            ),
            "authority": "South Carolina Public Service Commission",
            "url": "https://law.justia.com/codes/south-carolina/title-58/chapter-33/section-58-33-20/",
        },
        {
            "regime": "DOE NEPA review",
            "applies": (
                "Any DOE realty action (the AI-DC lease tracts included) "
                "takes an EA/EIS or categorical exclusion under 10 CFR 1021; "
                "DOE has proposed a new categorical exclusion for advanced "
                "reactors on federal sites (Mar 2026 notice)."
            ),
            "authority": "U.S. Department of Energy",
            "url": "https://www.energy.gov/nepa/doe-categorical-exclusion-cx-determinations",
        },
        {
            "regime": "Clean Water Act 404 / wetlands",
            "applies": (
                "SRS holds extensive Carolina-bay wetlands; construction "
                "touching jurisdictional waters needs USACE permitting. The "
                "screen below returns district and delineation-region "
                "context only — never a jurisdictional determination."
            ),
            "authority": "U.S. Army Corps of Engineers",
            "url": "https://regulatory.ops.usace.army.mil/",
        },
    ],
    "infrastructure": [
        {
            "category": "power_td",
            "summary": (
                "Dominion Energy South Carolina (formerly SCE&G) operates 115 "
                "and 230 kV transmission on the site, including the 151-1L "
                "switchyard; since the Oct 2024 landlord transition NNSA "
                "directly holds the site's utility contracts with Dominion, "
                "Ameresco, and CSX. Plant Vogtle's four-unit nuclear campus "
                "sits directly across the Savannah River in Burke County, GA."
            ),
            "source_label": "DOE — EM/NNSA landlord transition",
            "source_url": "https://www.energy.gov/srs/articles/em-nnsa-landlord-transition-complete-savannah-river-site",
            "extra_sources": [
                {
                    "label": "DOE NEPA CX-022129 — SCE&G 115/230 kV lines on SRS",
                    "url": "https://www.energy.gov/nepa/articles/cx-022129-herbicide-application-sce-and-g-115-and-230-kv-electricity-transmission",
                },
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "natural_gas",
            "summary": (
                "Carolina Gas Transmission (Berkshire Hathaway Energy) "
                "operates interstate gas infrastructure across Aiken and "
                "Barnwell counties, including an Aiken County compressor "
                "station — the most plausible supply for the Amentum "
                "project's gas-bridge generation. No public source specifies "
                "the lateral or interconnect that would serve the lease "
                "tracts."
            ),
            "source_label": "Rextag pipeline atlas — Carolina Gas Transmission",
            "source_url": "https://rextag.com/pages/carolina-gas-transmission",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "water",
            "summary": (
                "The Savannah River at Augusta (USGS gauge 02197000, ~25 mi "
                "upstream) averages ~7,477 cfs over the last decade. The "
                "site cooled five production reactors from the river via Par "
                "Pond (built 1958-59, ~2,640 acres) and L-Lake (1985, ~988 "
                "acres); large-scale cooling withdrawal ended with reactor "
                "shutdown by 1988."
            ),
            "source_label": "USGS NWIS — gauge 02197000 statistics",
            "source_url": "https://waterdata.usgs.gov/monitoring-location/USGS-02197000/statistics/",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "rail",
            "summary": (
                "The internal rail network originally exceeded 60 miles; "
                "less than half remains operational. The site interchanges "
                "with CSX at Dunbarton, and NNSA holds the CSX rail-service "
                "contract directly since the 2024 landlord transition."
            ),
            "source_label": "Savannah River Plant history (rail network)",
            "source_url": "https://en.wikipedia.org/wiki/Savannah_River_Plant",
            "extra_sources": [
                {
                    "label": "DOE — NNSA holds the CSX contract",
                    "url": "https://www.energy.gov/srs/articles/em-nnsa-landlord-transition-complete-savannah-river-site",
                },
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "road",
            "summary": (
                "SC-125 runs 17.3 miles through the site connecting Augusta, "
                "GA and Allendale, SC (a no-stopping zone inside the "
                "boundary); SC-19 links Aiken to the site and meets I-20 at "
                "Exit 18."
            ),
            "source_label": "SC Highway 125 (WSDOT-style route data)",
            "source_url": "https://en.wikipedia.org/wiki/South_Carolina_Highway_125",
            "verified_at": VERIFIED_AT,
        },
        # fiber: omitted — no public source documenting fiber assets at or
        # serving SRS was found (honest gap, not an absence claim).
        {
            "category": "workforce",
            "summary": (
                "13,510 employed at the site as of March 2026 (SRNS 6,969; "
                "SRMC 3,735; SRNL/BSRA 1,390), projected toward ~18,000 as "
                "plutonium pit production ramps. The Augusta-Richmond "
                "County GA-SC metro's civilian labor force was 270,500 "
                "(Dec 2025)."
            ),
            "source_label": "Aiken Standard — SRS workforce growth",
            "source_url": "https://www.postandcourier.com/aikenstandard/aikenstandard/news/savannah-river-site/savannah-river-site-workforce-growth/article_bf9f65d9-16bb-4bc4-9010-c12ad18a5f3d.html",
            "extra_sources": [
                {"label": "FRED — Augusta MSA labor force", "url": "https://fred.stlouisfed.org/series/AUGU213LFN"},
            ],
            "verified_at": VERIFIED_AT,
        },
    ],
    "parcels": [
        {
            "id": "srs-ai-lease-area",
            "name": "AI data-center / energy lease tracts (10 tracts)",
            "kind": "leased_energy",
            "lat": 33.2500,
            "lon": -81.6500,
            "coord_note": (
                "NNSA has not published tract boundaries; this is the "
                "site-level reference point, low-precision by design."
            ),
            "approx_acres": 3103,
            "corpus_site_id": "SC1890008989",
            "clup_designation": None,
            "clup_note": (
                "Ten tracts (81-570 acres each) designated for AI/energy "
                "leasing; one named tract, L-Area, currently stores used "
                "nuclear fuel — a constraint on that specific tract."
            ),
            "status": (
                "NNSA identified 10 tracts totaling 3,103 acres and, on "
                "July 20, 2026, selected Amentum to enter phased lease "
                "negotiations for a 1 GWe AI data center backed by ~2 GWe "
                "of co-located generation — natural gas first, transitioning "
                "to advanced nuclear. Founding coalition members include "
                "DC BLOX, Milliken & Company, Google, and Nucor."
            ),
            "availability": (
                "Not yet leased — the selection is explicitly not a final "
                "award; lease negotiation plus permitting, safety, and "
                "security reviews are the remaining gates."
            ),
            "source_url": "https://www.energy.gov/nnsa/articles/nnsa-selects-amentum-ai-data-center-and-energy-project-savannah-river-site",
            "extra_sources": [
                {
                    "label": "NEI Magazine — Amentum SRS AI campus (1 GWe + 2 GWe)",
                    "url": "https://www.neimagazine.com/news/amentum-to-develop-srs-ai-campus/",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "ai_datacenter",
                    "fit": "strong",
                    "rationale": (
                        "Amentum was selected July 20, 2026 to negotiate the "
                        "lease — a committed direction, but selection is not "
                        "a final award, so the executed lease is the gate."
                    ),
                },
                {
                    "kind": "gas_generation",
                    "fit": "strong",
                    "rationale": (
                        "The announced ~2 GWe generation plan starts on "
                        "natural gas as the bridge fuel; no supply lateral "
                        "for the tracts has been publicly specified."
                    ),
                },
                {
                    "kind": "advanced_nuclear",
                    "fit": "conditional",
                    "rationale": (
                        "The plan transitions to advanced nuclear, but no "
                        "reactor vendor or design has been announced — "
                        "technology selection and DOE/NRC authorization are "
                        "the gates."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "strong",
                    "constraint": "land",
                    "rationale": (
                        "This is the tracts' committed purpose — but NNSA's "
                        "selection of Amentum is explicitly not a final "
                        "award, so the executed lease (plus permitting, "
                        "safety, and security review) is what separates "
                        "strong from anchored."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "conditional",
                    "constraint": "licensing",
                    "rationale": (
                        "The ~2 GWe co-located generation plan targets "
                        "'advanced nuclear' after a gas bridge, but no "
                        "reactor class or vendor is announced; any "
                        "GW-class unit still needs DOE authorization or an "
                        "NRC license."
                    ),
                    "sources": [
                        {
                            "label": "NEI Magazine — gas bridge to advanced nuclear",
                            "url": "https://www.neimagazine.com/news/amentum-to-develop-srs-ai-campus/",
                        },
                    ],
                },
                {
                    "type": "smr",
                    "fit": "strong",
                    "constraint": "licensing",
                    "rationale": (
                        "SMR-class units fit the announced gas-to-nuclear "
                        "plan and the EO 14299 DOE-authorization pathway; "
                        "the gap is a finalized vendor/technology decision."
                    ),
                    "sources": [
                        {
                            "label": "DOE — reactor authorization fast facts",
                            "url": "https://www.energy.gov/ne/articles/5-fast-facts-about-doe-reactor-authorization",
                        },
                    ],
                },
                {
                    "type": "microreactor",
                    "fit": "strong",
                    "constraint": "licensing",
                    "rationale": (
                        "A microreactor could serve as an early, lower-risk "
                        "demonstration ahead of the larger nuclear build-out "
                        "under DOE's streamlined authorization — none is "
                        "announced for SRS today."
                    ),
                },
            ],
        },
        {
            "id": "srs-a-m-area",
            "name": "A/M Area — SRNL campus and the industrial-park question",
            "kind": "context_campus",
            "lat": 33.3428,
            "lon": -81.7381,
            "coord_note": "SRNL's published campus coordinate, northwest corner of the site near Jackson, SC.",
            "approx_acres": 5000,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": (
                "SRNL campus is an active R&D mission; the adjacent "
                "~5,000-acre industrial-park concept has no confirmed DOE "
                "land-use redesignation."
            ),
            "status": (
                "Savannah River National Laboratory (~820,000 sq ft, "
                "operated by Battelle Savannah River Alliance) anchors the "
                "site's northwest corner; M-Area completed CERCLA closure in "
                "2010. A community proposal (reported 2021) to convert "
                "~5,000 acres near the boundary into an industrial park "
                "still requires a DOE land transfer that has not occurred."
            ),
            "availability": (
                "SRNL campus is an operating DOE lab — not available. The "
                "industrial-park footprint is proposal-stage only, gated on "
                "a DOE land transfer plus ~$25M in water/sewer buildout."
            ),
            "source_url": "https://www.srnl.gov/fact-sheets/srnl-overview/",
            "extra_sources": [
                {
                    "label": "Post & Courier — SRS industrial-park proposal",
                    "url": "https://www.postandcourier.com/columbia/proposal-would-turn-chunk-of-srs-into-industrial-park-if-the-feds-will-give-back/article_125d73b6-2215-11ec-8758-23083e939004.html",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "research_campus",
                    "fit": "anchored",
                    "rationale": (
                        "SRNL is operating and growing — the workforce and "
                        "R&D anchor every reuse plan on this page leans on."
                    ),
                },
                {
                    "kind": "advanced_manufacturing",
                    "fit": "conditional",
                    "rationale": (
                        "The industrial-park concept has real regional "
                        "backing but needs the unexecuted DOE land transfer "
                        "and state-funded utilities first."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "Real infrastructure and a long-standing push for an "
                        "adjacent industrial park, but no data center is "
                        "proposed here and the land transfer hasn't happened."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "precluded",
                    "constraint": "mission",
                    "rationale": (
                        "SRNL is an active, mission-critical national-lab "
                        "campus; no part of A/M Area is under consideration "
                        "for utility-scale reactor siting."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "The broader site has SMR-partnership history "
                        "(Holtec SMR-160 agreements, 2012-2020s — current "
                        "status unconfirmed), but an SMR here needs both the "
                        "unexecuted land transfer and a siting decision."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "strong",
                    "constraint": "licensing",
                    "rationale": (
                        "A lab-adjacent microreactor demonstration is "
                        "plausible without the full land transfer, on the "
                        "DOE-authorization path; none is announced."
                    ),
                },
            ],
        },
        {
            "id": "srs-d-area",
            "name": "D-Area — retired coal powerhouse on the river",
            "kind": "cleanup_area",
            "lat": 33.3385,
            "lon": -81.7346,
            "coord_note": "Global Energy Monitor facility entry for the D-Area Power House.",
            "approx_acres": 210,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "DOE-EM frames post-cleanup D-Area as 'prepared for industrial use if needed.'",
            "status": (
                "The 78.2 MW coal powerhouse (seven units, commissioned "
                "1952) closed in 2012; ash basins and landfill were "
                "remediated from 2014. Roughly 60% of D-Area structures "
                "have been demolished, with the powerhouse building and "
                "water treatment plant among those remaining; solar "
                "installation is planned."
            ),
            "availability": (
                "DOE-EM's stated goal is returning all 210 acres to a "
                "condition 'prepared for industrial use if needed' — the "
                "site's own reuse-ready brownfield."
            ),
            "source_url": "https://www.energy.gov/em/articles/reducing-footprints-increasing-opportunities-savannah-river-site",
            "extra_sources": [
                {
                    "label": "Global Energy Monitor — D-Area Power House",
                    "url": "https://www.gem.wiki/Savannah_River_D-Area_Power_House",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "solar_storage",
                    "fit": "strong",
                    "rationale": (
                        "DOE's own reporting says solar-panel installation "
                        "is planned for the remediated footprint."
                    ),
                },
                {
                    "kind": "advanced_manufacturing",
                    "fit": "conditional",
                    "rationale": (
                        "DOE-EM's 'prepared for industrial use' framing is "
                        "the invitation; completing the remaining demolition "
                        "is the gate."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "strong",
                    "constraint": "land",
                    "rationale": (
                        "A 210-acre parcel with grid and river-water "
                        "history that DOE-EM itself frames as reuse-ready; "
                        "the nearest gate is finishing demolition, not a "
                        "fundamental barrier."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "210 acres is generally undersized for a "
                        "conventional large-LWR campus with its exclusion "
                        "area."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "strong",
                    "constraint": "licensing",
                    "rationale": (
                        "The acreage plausibly fits SMR units, and the "
                        "parcel's former-powerhouse river-water and grid "
                        "interconnection history is exactly the repowering "
                        "pattern — no SMR is proposed here yet."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "strong",
                    "constraint": "licensing",
                    "rationale": (
                        "Fits easily within the remediated footprint, "
                        "consistent with DOE's own industrial-reuse framing."
                    ),
                },
            ],
        },
        {
            "id": "srs-fh-tank-farms",
            "name": "F/H Area — tank farms and the liquid-waste core",
            "kind": "cleanup_core",
            "lat": 33.2800,
            "lon": -81.6400,
            "coord_note": (
                "Rough interpolation only — DOE describes the General "
                "Separations Area as 'north-central'; no public sub-area "
                "geocode exists."
            ),
            "approx_acres": 67,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "Active FFA-directed remediation area; long-term waste-management designation expected post-closure.",
            "status": (
                "51 underground waste tanks (22 in F, 29 in H); 8 "
                "operationally closed. Of the >165 million gallons of "
                "liquid waste historically generated, ~33 million gallons "
                "remain in storage (Feb 2026). The Salt Waste Processing "
                "Facility reached full operations in January 2021; the "
                "liquid-waste system plan targets all tanks operationally "
                "closed between 2037 and 2041."
            ),
            "availability": (
                "None — the active cleanup core under the FFA, precluded "
                "until tank closure substantially completes (2037+), with "
                "land-use controls persisting after."
            ),
            "source_url": "https://www.energy.gov/em/articles/latest-srs-liquid-waste-system-plan-outlines-path-tank-closure",
            "extra_sources": [
                {
                    "label": "NRC — F-Area Tank Farm (WIR reviews)",
                    "url": "https://www.nrc.gov/waste/incidental-waste/wir-process/wir-locations/f-area-tank-farm",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "waste_disposal",
                    "fit": "anchored",
                    "rationale": (
                        "The liquid-waste mission IS this land's use for the "
                        "next decade-plus; saying so keeps 'remaining land' "
                        "honest."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": t,
                    "fit": "precluded",
                    "constraint": "mission",
                    "rationale": (
                        "Active high-level liquid-waste cleanup core (43 "
                        "tanks pending closure through 2037-2041) plus "
                        "H-Canyon processing — no reuse consideration before "
                        "the mission completes. A mission timeline, not a "
                        "permanent legal bar."
                    ),
                }
                for t in FACILITY_TYPES
            ],
        },
        {
            "id": "srs-crackerneck",
            "name": "Crackerneck WMA / Par Pond — the conservation set-aside",
            "kind": "conservation",
            "lat": 33.2354,
            "lon": -81.5165,
            "coord_note": "USGS gauge point below the Par Pond dam — the nearest confirmed public coordinate.",
            "approx_acres": 10470,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "Wildlife Management Area & Ecological Reserve within the National Environmental Research Park set-aside.",
            "status": (
                "Crackerneck Wildlife Management Area & Ecological Reserve "
                "(10,470 acres, DOE-owned, SCDNR-managed under a 1987 "
                "agreement formalized by a 1999 DOE proclamation) holds "
                "old-growth river swamp and Carolina bays. Par Pond (built "
                "1958-59, ~2,640 acres) and L-Lake (1985) are the former "
                "reactor-cooling reservoirs."
            ),
            "availability": (
                "Not available for industrial or energy reuse — a "
                "conservation designation by DOE administrative action, "
                "which is a standing commitment rather than a statutory bar."
            ),
            "source_url": "https://public-lands-scdnr.hub.arcgis.com/pages/crackerneck-wma-ecological-reserve",
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "conservation",
                    "fit": "anchored",
                    "rationale": (
                        "Decades of SCDNR management and research set-aside "
                        "status point one direction."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": t,
                    "fit": "precluded",
                    "constraint": "land",
                    "rationale": (
                        "Formally designated WMA & Ecological Reserve inside "
                        "the research-park set-aside — an administrative "
                        "conservation designation DOE could in principle "
                        "revisit, unlike a statutory monument, but a real "
                        "bar as it stands."
                    ),
                }
                for t in FACILITY_TYPES
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Portsmouth Gaseous Diffusion Plant (OH)
# ---------------------------------------------------------------------------

PORTSMOUTH_SITE = {
    "site_id": "portsmouth",
    "site_label": "Portsmouth",
    "site_overview": {
        "name": "Portsmouth Gaseous Diffusion Plant (Piketon)",
        "state": "OH",
        "county": "Pike",
        "size_sq_mi": 6,
        "summary": (
            "PORTS enriched uranium from 1954 to 2001 on a ~3,700-3,777-acre "
            "reservation (~1,000 acres industrialized); USEC returned the "
            "plant to DOE for decontamination and decommissioning in 2011. "
            "It is now the furthest-along federal reuse story in the "
            "country: SB Energy's PORTS Technology Campus broke ground "
            "March 20, 2026 (10 GW of IT capacity planned, OpenAI as a "
            "~8 GW anchor tenant), Centrus operates the only NRC-licensed "
            "HALEU enrichment cascade in the US, Oklo holds land rights for "
            "two Aurora powerhouses, and 354 acres have already transferred "
            "to the community reuse organization SODI."
        ),
        "managers": [
            {
                "role": "Cleanup (site owner)",
                "who": "DOE Portsmouth/Paducah Project Office (PPPO); D&D contractor Southern Ohio Cleanup Company (Amentum-led, 2,000+ workers)",
                "url": "https://www.energy.gov/pppo/portsmouth-site-description",
            },
            {
                "role": "Regulators",
                "who": (
                    "Ohio EPA under the 1989 Consent Decree and "
                    "Administrative Consent Order, implemented through five "
                    "Director's Final Findings & Orders (RCRA corrective "
                    "action — the site is NOT on the NPL; EPA lists it as "
                    "Federal Facility-Lead Cleanup, ID OH7890008983)"
                ),
                "url": "https://www.energy.gov/pppo/portsmouth-regulatory-approach",
            },
            {
                "role": "Community reuse",
                "who": "Southern Ohio Diversification Initiative (SODI) — DOE's designated Community Reuse Organization since 1995; targets 500+ transferred acres",
                "url": "https://www.sodidevelopment.org/about-us/",
            },
            {
                "role": "NRC licensee on site",
                "who": "American Centrifuge Operating (Centrus) under NRC materials license SNM-2011 — the only licensed HALEU production facility in the US",
                "url": "https://www.nrc.gov/materials/fuel-cycle-fac/usecfacility",
            },
        ],
        "land_use_plan": {
            "label": "PORTSFuture Vision Project + DOE parcel-by-parcel transfer program",
            "url": "https://www.energy.gov/pppo/portsmouth-future-site-reuse",
            "note": (
                "DOE's holistic cleanup approach enables parcel-by-parcel "
                "transfer for reindustrialization; Parcels 1-3 (354 acres) "
                "have transferred to SODI, with Parcel 4 pending."
            ),
        },
    },
    "permitting_pathways": [
        {
            "regime": "Ohio EPA consent decree / RCRA corrective action",
            "applies": (
                "Governs all D&D, remediation, and waste disposal site-wide "
                "under the 1989 Consent Decree, Administrative Consent "
                "Order, and five Director's Final Findings & Orders."
            ),
            "authority": "Ohio EPA",
            "url": "https://www.energy.gov/pppo/portsmouth-regulatory-approach",
        },
        {
            "regime": "Ohio Power Siting Board certificate",
            "applies": (
                "Required for ≥50 MW generation under ORC Ch. 4906 — the "
                "PORTS Energy Center gas build proceeds through OPSB per "
                "AEP's public statements, with a public information meeting "
                "scheduled Aug 27, 2026."
            ),
            "authority": "Ohio Power Siting Board",
            "url": "https://opsb.ohio.gov/",
        },
        {
            "regime": "NRC licensing",
            "applies": (
                "Centrus' American Centrifuge Plant operates under NRC "
                "license SNM-2011. Oklo's Portsmouth Aurora units trail its "
                "lead INL unit, which proceeds under DOE's Reactor Pilot "
                "Program authorization; Oklo states it will pursue NRC "
                "licensing later for commercial operation."
            ),
            "authority": "U.S. Nuclear Regulatory Commission / DOE",
            "url": "https://www.nrc.gov/materials/fuel-cycle-fac/usecfacility",
        },
        {
            "regime": "DOE NEPA categorical exclusions (realty)",
            "applies": (
                "The 189-acre Batch 1 lease to Pike County Portsmouth DC "
                "LLC used CX-270875 (Nov 17, 2025) under CERCLA §120(h) / "
                "the Hall Amendment + 10 CFR Part 770; a follow-on "
                "environmental site assessment used CX-270956 (Apr 29, "
                "2026)."
            ),
            "authority": "U.S. Department of Energy (PPPO)",
            "url": "https://www.energy.gov/node/4855269",
        },
        {
            "regime": "FAST-41 covered-project review",
            "applies": (
                "The PORTS-Pike Energy Center is reported as the first "
                "HPC-sector FAST-41 covered project, with USACE as lead "
                "agency; Ohio EPA's CWA §401 certification is pending "
                "(additional wetlands and endangered-species documentation "
                "requested), with a review deadline reported for late "
                "December 2026."
            ),
            "authority": "Federal Permitting Council / USACE / Ohio EPA",
            "url": "https://www.datacenterfrontier.com/hyperscale/article/55398883/ports-pike-takes-shape-as-an-8-gw-ai-infrastructure-model",
        },
    ],
    "infrastructure": [
        {
            "category": "power_td",
            "summary": (
                "Two 330 kV switchyards (X-533 + X-530) historically "
                "delivered up to 2,200 MW to the enrichment cascade; X-533 "
                "was demolished by 2011, X-530 remains active as the site's "
                "high-voltage interconnection. OVEC was created in 1952 "
                "specifically to power this plant. SB Energy is funding a "
                "$4.2B AEP Ohio transmission buildout — a new ~50-mile "
                "765 kV line from the Baku substation (Pike County) to the "
                "Gavin substation — with power expected to flow in 2029; "
                "the first ~800 MW phase (2028) rides existing AEP "
                "infrastructure."
            ),
            "source_label": "AEP — $4.2B transmission investment",
            "source_url": "https://www.aep.com/news/stories/view/10823/",
            "extra_sources": [
                {
                    "label": "PORTS Virtual Museum — X-533 switchyard",
                    "url": "https://www.portsvirtualmuseum.org/virtual-tour/x533/index.html",
                },
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "natural_gas",
            "summary": (
                "No named pipeline lateral or supplier for the ~9.2 GW "
                "PORTS Energy Center gas plant has been made public — a "
                "notable gap at that scale. Regional interstate context: "
                "Columbia Gas Transmission's system crosses Ohio; the gas "
                "plant itself sits on ~1,300-2,700 acres of PRIVATE land "
                "adjacent to the DOE reservation per the FAST-41 filing."
            ),
            "source_label": "Data Center Frontier — PORTS-Pike FAST-41 profile",
            "source_url": "https://www.datacenterfrontier.com/hyperscale/article/55398883/ports-pike-takes-shape-as-an-8-gw-ai-infrastructure-model",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "water",
            "summary": (
                "The Scioto River is the site's water source: the X-611 "
                "water treatment plant was designed for 40 MGD (36 MGD "
                "recirculating cooling makeup + 4 MGD sanitary) and "
                "historically processed >10 MGD during enrichment "
                "operations. Reporting on the new campus says the gas plant "
                "draws Scioto water while the data-center buildings are "
                "closed-loop/air-cooled."
            ),
            "source_label": "Ohio EPA — NPDES fact sheet (Portsmouth)",
            "source_url": "https://dam.assets.ohio.gov/image/upload/epa.ohio.gov/Portals/35/permits/doc/0IS00023.fs.pdf",
            "extra_sources": [
                {
                    "label": "The Post (Athens) — campus water use",
                    "url": "https://www.thepostathens.com/article/2026/08/data-center-piketon-ohio-environmental-impacts",
                },
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "rail",
            "summary": (
                "22 miles of on-site rail were built during 1950s "
                "construction, including a delivery spur along X-333. "
                "Whether any trackage remains in service today, and which "
                "mainline carrier connects, is UNCONFIRMED in public "
                "sources — an open question, not an asset claim."
            ),
            "source_label": "PORTS Virtual Museum — construction history",
            "source_url": "https://www.portsvirtualmuseum.org/history/construction.html",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "road",
            "summary": (
                "The site fronts US-23 (3930 US Route 23 South, Piketon); "
                "OH-32, the Appalachian Highway, provides the regional "
                "east-west connection through Pike County."
            ),
            "source_label": "EPA site profile (address)",
            "source_url": "https://cumulis.epa.gov/supercpad/cursites/csitinfo.cfm?id=0504940",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "fiber",
            "summary": (
                "No public source confirms a fiber asset serving the "
                "reservation itself. Regionally, the Horizon Telcom-led "
                "'Connecting Appalachian Ohio' middle-mile project adds "
                "1,960 fiber miles across 34 counties with OARnet holding "
                "rights of use."
            ),
            "source_label": "NTIA — Appalachian Ohio middle-mile award",
            "source_url": "https://broadbandusa.ntia.gov/funding-programs/enabling-middle-mile-broadband-infrastructure-program/awardee/appalachian-ohio-middle-mile-expansion",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "workforce",
            "summary": (
                "Over 2,400 workers are employed at the site today (D&D "
                "contractor SOCCo alone employs 2,000+). Campus job "
                "projections diverge by source and scope: DOE materials "
                "cite 10,000 construction / 2,000+ permanent at full "
                "buildout, while FAST-41-scope coverage (including the gas "
                "plant) cites ~35,000 construction over six years / 2,500 "
                "permanent — unreconciled, both attributed here."
            ),
            "source_label": "DOE PPPO — Portsmouth site description",
            "source_url": "https://www.energy.gov/pppo/portsmouth-site-description",
            "extra_sources": [
                {
                    "label": "Data Center Frontier — FAST-41-scope job figures",
                    "url": "https://www.datacenterfrontier.com/hyperscale/article/55398883/ports-pike-takes-shape-as-an-8-gw-ai-infrastructure-model",
                },
            ],
            "verified_at": VERIFIED_AT,
        },
    ],
    "parcels": [
        {
            "id": "ports-technology-campus",
            "name": "PORTS Technology Campus — SB Energy / OpenAI",
            "kind": "leased_energy",
            "lat": 39.0100,
            "lon": -83.0050,
            "coord_note": "Approximate, derived from the site address on US-23; DOE has not published the leased-parcel boundary.",
            "approx_acres": 189,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": (
                "189-acre 'Batch 1' executed DOE lease; the broader campus "
                "plan references the ~3,700-acre reservation plus "
                "~1,300-2,700 acres of adjacent private land for the gas "
                "buildout."
            ),
            "status": (
                "SB Energy (SoftBank) broke ground March 20, 2026 on a "
                "campus targeting 10 GW of IT capacity paired with up to 10 "
                "GW of new generation. OpenAI signed a 20-year lease for "
                "~8 GW of IT capacity; NVIDIA committed $1.5B to SB Energy "
                "backing an initial 4.25 GW tranche. The first ~800 MW "
                "phase targets 2028 on existing AEP infrastructure; the "
                "PORTS Energy Center gas plant (initial ~2 GW) targets "
                "construction Q1 2027 and operation Q3 2028."
            ),
            "availability": (
                "The 189-acre Batch 1 parcel is under an executed DOE lease "
                "(CX-270875, Nov 2025); remaining campus acreage requires "
                "further leasing, NEPA review, and OPSB approval for the "
                "generation."
            ),
            "source_url": "https://www.energy.gov/node/4855269",
            "extra_sources": [
                {
                    "label": "DOE-EM — partnership powers AI future at Portsmouth",
                    "url": "https://www.energy.gov/em/articles/partnership-ensures-affordable-energy-powers-ai-future-portsmouth-site",
                },
                {
                    "label": "Data Center Frontier — PORTS-Pike profile",
                    "url": "https://www.datacenterfrontier.com/hyperscale/article/55398883/ports-pike-takes-shape-as-an-8-gw-ai-infrastructure-model",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "ai_datacenter",
                    "fit": "anchored",
                    "rationale": (
                        "Executed 189-acre lease, OpenAI 20-year commitment, "
                        "NVIDIA backing, and a groundbreaking already held — "
                        "an operating commitment, not a prospect."
                    ),
                },
                {
                    "kind": "gas_generation",
                    "fit": "strong",
                    "rationale": (
                        "The ~9.2 GW PORTS Energy Center plan is funded and "
                        "scheduled (construction Q1 2027) but still needs "
                        "its OPSB certificate and CWA §401 sign-off — and "
                        "sits largely on adjacent private land."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "anchored",
                    "constraint": "land",
                    "rationale": (
                        "Executed DOE lease (CX-270875), OpenAI anchor "
                        "tenancy, NVIDIA investment, groundbreaking held "
                        "March 20, 2026 — the largest announced US AI-DC "
                        "project on federal land."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "precluded",
                    "constraint": "land",
                    "rationale": (
                        "The land is committed to the data-center/gas "
                        "buildout under an executed lease and FAST-41 "
                        "track; a GW-class reactor would displace the "
                        "committed plan."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "Beside the site's active HV interconnection and a "
                        "committed GW-scale load — structurally attractive — "
                        "but no SMR is named and the acreage is earmarked; "
                        "the gate is a new lease outside SB Energy's "
                        "footprint."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "Same logic at smaller scale; Oklo's committed "
                        "units are on separate SODI land, not here."
                    ),
                },
            ],
        },
        {
            "id": "ports-centrus-acp",
            "name": "Centrus American Centrifuge Plant",
            "kind": "operating_mission",
            "lat": 38.9980,
            "lon": -83.0250,
            "coord_note": "Approximate — 'southwest quadrant of the DOE reservation' per NRC/Centrus sourcing.",
            "approx_acres": None,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "Occupies GCEP-era buildings X-3001 and X-7725; no standalone parcel acreage is published.",
            "status": (
                "American Centrifuge Operating (Centrus) holds NRC license "
                "SNM-2011 — the only NRC-licensed HALEU production facility "
                "in the US. The demonstration cascade passed 1,900+ "
                "cumulative kilograms by mid-June 2026, and Centrus "
                "finalized a $900M DOE contract (July 1, 2026) to "
                "transition to commercial-scale operation and expand "
                "LEU/HALEU capacity."
            ),
            "availability": (
                "Not available — an active, security-controlled NRC-licensed "
                "nuclear materials facility, expanding under its own DOE "
                "contract."
            ),
            "source_url": "https://www.nrc.gov/materials/fuel-cycle-fac/usecfacility",
            "extra_sources": [
                {
                    "label": "Centrus — $900M DOE contract (July 2026)",
                    "url": "https://www.centrusenergy.com/news/centrus-signs-contract-with-department-of-energy-for-900-million-award-intends-to-transition-haleu-production-cascade-to-commercial-operation/",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "nuclear_fuel_cycle",
                    "fit": "anchored",
                    "rationale": (
                        "The operating HALEU cascade plus the July 2026 "
                        "commercial-operation contract make this the "
                        "front-end fuel anchor for every advanced-reactor "
                        "plan in the region."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": t,
                    "fit": "precluded",
                    "constraint": "security",
                    "rationale": (
                        "An active, security-controlled special-nuclear-"
                        "material production facility under NRC license "
                        "SNM-2011 — safeguards and criticality-safety "
                        "requirements foreclose co-locating any of these "
                        "facility types on its footprint."
                    ),
                }
                for t in FACILITY_TYPES
            ],
        },
        {
            "id": "ports-process-buildings",
            "name": "Former process buildings + On-Site Waste Disposal Facility",
            "kind": "cleanup_core",
            "lat": 39.0050,
            "lon": -83.0100,
            "coord_note": "Approximate — central industrialized area inside Perimeter Road.",
            "approx_acres": None,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": (
                "X-333 alone had 66 acres of floor space under roof; the "
                "OSWDF occupies a 300-acre footprint. No combined parcel "
                "acreage is published."
            ),
            "status": (
                "X-326 (the largest process building) was demolished with "
                "final waste disposal completed August 24, 2023. X-333 "
                "deactivation completed December 2024 and demolition began "
                "November 2025 (waste placement through ~FY2031); X-330 is "
                "mid-deactivation with demolition expected 2030-2032. The "
                "OSWDF continues accepting debris with disposal-cell "
                "construction through FY2033."
            ),
            "availability": (
                "Not available near-term — the active cleanup core, with "
                "disposal operations continuing into the early-to-mid "
                "2030s. The cleared X-326 pad is furthest along but has no "
                "announced reuse action."
            ),
            "source_url": "https://www.energy.gov/pppo/portsmouth-deactivation-demolition",
            "extra_sources": [
                {
                    "label": "DOE-EM — X-333 demolition kickoff",
                    "url": "https://www.energy.gov/em/articles/em-crews-kick-x-333-facility-demolition-activities-portsmouth-site",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "waste_disposal",
                    "fit": "anchored",
                    "rationale": (
                        "The operating OSWDF and the remaining demolition "
                        "sequence are this footprint's mission into the "
                        "2030s."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "conditional",
                    "constraint": "mission",
                    "rationale": (
                        "The cleared X-326 pad is the most-advanced "
                        "footprint but sits inside the active D&D zone "
                        "beside the operating OSWDF; the gate is a DOE "
                        "land-use determination plus an adequate buffer "
                        "from waste operations."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "precluded",
                    "constraint": "mission",
                    "rationale": (
                        "An operating waste landfill and two process "
                        "buildings mid-demolition (through ~2032) occupy "
                        "the footprint — a GW-class reactor here isn't "
                        "credible on DOE's published D&D timeline."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "conditional",
                    "constraint": "mission",
                    "rationale": (
                        "Feasible only after D&D substantially completes "
                        "(~2032) with a safety buffer from the "
                        "still-operating OSWDF."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "conditional",
                    "constraint": "mission",
                    "rationale": (
                        "The smallest footprint of the four types could use "
                        "the cleared X-326 pad soonest — still gated on DOE "
                        "land-use authorization and an OSWDF buffer."
                    ),
                },
            ],
        },
        {
            "id": "ports-sodi-parcels",
            "name": "SODI transferred parcels — Trillium and Oklo",
            "kind": "transferred",
            "lat": 39.0000,
            "lon": -82.9950,
            "coord_note": "Approximate — 'southeast portion, adjacent Perimeter Road' per DOE sourcing for the first transfer.",
            "approx_acres": 354,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "Parcels 1-2 (306 ac) and Parcel 3 (48 ac) transferred; Parcel 4 pending; SODI targets 500+ acres.",
            "status": (
                "SODI's transferred land already hosts two named projects: "
                "Trillium H2 Power bought ~80 acres for a $1.5B "
                "hydrogen/ammonia/silicon complex (announced January 2024), "
                "and Oklo signed an executed land-rights agreement "
                "(February 2024) for two 15-MWe Aurora powerhouses plus "
                "50+ MW of process heat — trailing Oklo's lead INL unit, "
                "which proceeds under DOE's Reactor Pilot Program "
                "authorization."
            ),
            "availability": (
                "354 acres are out of DOE ownership; within that, ~80 acres "
                "are Trillium's and a further tranche is under Oklo's "
                "option — the remainder is SODI's active marketing "
                "inventory."
            ),
            "source_url": "https://www.energy.gov/pppo/portsmouth-future-site-reuse",
            "extra_sources": [
                {
                    "label": "SODI — DOE 80-acre transfer",
                    "url": "https://www.sodidevelopment.org/notices/doe-to-transfer-80-acres-at-portsmouth-site-to-sodi/",
                },
                {
                    "label": "POWER Magazine — Oklo's two Aurora plants for southern Ohio",
                    "url": "https://www.powermag.com/oklos-next-two-nuclear-power-plants-planned-for-southern-ohio/",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "hydrogen_ammonia",
                    "fit": "strong",
                    "rationale": (
                        "Trillium's $1.5B h2TEAM complex owns its 80 acres "
                        "and is announced at scale; construction status "
                        "remains the open question."
                    ),
                },
                {
                    "kind": "advanced_nuclear",
                    "fit": "anchored",
                    "rationale": (
                        "Oklo's executed land-rights agreement for two "
                        "Aurora powerhouses is the flagship example of the "
                        "transfer-to-reactor pathway."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "SODI actively markets transferred land with "
                        "large-tenant precedent, but no DC tenant is "
                        "announced on SODI land — the gate is acreage "
                        "beyond what Trillium and Oklo hold."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "precluded",
                    "constraint": "land",
                    "rationale": (
                        "Parcels of tens to a few hundred acres are sized "
                        "for diversified industrial reuse, not a GW-class "
                        "exclusion-zone campus."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "A mid-size parcel could plausibly host an SMR and "
                        "SODI's mandate includes energy projects (the Oklo "
                        "precedent), but none is announced."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "anchored",
                    "constraint": "licensing",
                    "rationale": (
                        "Oklo holds an executed option and right of first "
                        "refusal (February 2024) for two 15-MWe Aurora "
                        "powerhouses plus 50+ MW of process heat — a "
                        "committed, named project."
                    ),
                    "sources": [
                        {
                            "label": "POWER Magazine — Oklo Portsmouth plants",
                            "url": "https://www.powermag.com/oklos-next-two-nuclear-power-plants-planned-for-southern-ohio/",
                        },
                    ],
                },
            ],
        },
        {
            "id": "ports-x530-switchyard",
            "name": "X-530 switchyard corridor — the grid asset",
            "kind": "cleanup_area",
            "lat": 39.0080,
            "lon": -83.0150,
            "coord_note": "Approximate — industrialized core near the former process buildings.",
            "approx_acres": None,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "No standalone tract acreage is published for the switchyard corridor.",
            "status": (
                "The plant's two 330 kV switchyards delivered up to 2,200 MW "
                "combined; X-533 (built 1956) was de-energized in 2008 and "
                "demolished by March 2011, while X-530 remains active as "
                "the site's high-voltage interconnection — now the anchor "
                "for AEP Ohio's SB-Energy-funded $4.2B, 765 kV Baku-to-"
                "Gavin transmission buildout."
            ),
            "availability": (
                "An infrastructure asset rather than a building site: the "
                "corridor's value is the live interconnection and the "
                "proven GW-scale delivery history."
            ),
            "source_url": "https://www.portsvirtualmuseum.org/virtual-tour/x533/index.html",
            "extra_sources": [
                {
                    "label": "AEP — $4.2B transmission buildout",
                    "url": "https://www.aep.com/news/stories/view/10823/",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "ai_datacenter",
                    "fit": "strong",
                    "rationale": (
                        "The live X-530 interconnection and the 765 kV "
                        "buildout it anchors are what make the adjacent "
                        "campus's power story credible."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "strong",
                    "constraint": "power",
                    "rationale": (
                        "Anchors the site's one active HV interconnection "
                        "and the new $4.2B buildout — enabling "
                        "infrastructure, though the announced DC buildings "
                        "sit on the separate Batch 1 lease."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "Historic 2,200 MW delivery proves the corridor "
                        "can move GW-scale power, but the switchyard tract "
                        "itself is too small for a reactor campus and no "
                        "LWR is proposed at Portsmouth."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "Interconnection-adjacent siting lowers grid risk; "
                        "the gate is identifying adjacent land for reactor "
                        "buildings and an exclusion area."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "conditional",
                    "constraint": "land",
                    "rationale": (
                        "Smallest footprint need beside live HV "
                        "infrastructure, but no project names this parcel "
                        "(Oklo's units are on SODI land)."
                    ),
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Paducah Gaseous Diffusion Plant (KY)
# ---------------------------------------------------------------------------

PADUCAH_SITE = {
    "site_id": "paducah",
    "site_label": "Paducah",
    "site_overview": {
        "name": "Paducah Gaseous Diffusion Plant",
        "state": "KY",
        "county": "McCracken",
        "size_sq_mi": 6,
        "summary": (
            "Paducah enriched uranium from 1952 until 2013 — the last "
            "operating gaseous diffusion plant in the US — on a 3,556-acre "
            "DOE reservation (~750 fenced acres). It is now the "
            "furthest-along federal AI-energy award: DOE announced in July "
            "2026 that Brookfield will develop a 1.8 GW AI/HPC campus with "
            "NextEra building ~2 GW of new gas generation and up to 2.6 GW "
            "of battery storage (~$100B total investment), while General "
            "Matter leased 100 acres for a $1.5B enrichment plant and the "
            "DUF6 conversion mission keeps operating."
        ),
        "managers": [
            {
                "role": "Cleanup (site owner)",
                "who": "DOE Portsmouth/Paducah Project Office; D&D contractor Four Rivers Nuclear Partnership (CH2M-led with Fluor and BWXT)",
                "url": "https://www.energy.gov/pppo/paducah-site-description",
            },
            {
                "role": "Regulators",
                "who": (
                    "EPA Region 4 and the Kentucky Energy and Environment "
                    "Cabinet under the 1998 Federal Facility Agreement "
                    "(NPL-listed 1994, EPA ID KY8890008982)"
                ),
                "url": "https://eec.ky.gov/Environmental-Protection/Waste/hazardous-waste/Pages/paducah-gaseous-diffusion-plant.aspx",
            },
            {
                "role": "Community reuse",
                "who": "Paducah Area Community Reuse Organization (PACRO) — one of seven active DOE Community Reuse Organizations",
                "url": "https://pacroky.com/about/",
            },
            {
                "role": "Conservation buffer",
                "who": "KY Dept. of Fish & Wildlife Resources manages the ~4,495-acre West Kentucky Wildlife Management Area around the reservation (portions DOE- and TVA-licensed)",
                "url": "https://app.fw.ky.gov/public_lands_search/detail.aspx?Kdfwr_id=137",
            },
        ],
        "land_use_plan": {
            "label": "DOE Paducah future-use vision (EA + FONSI enabling property transfers)",
            "url": "https://www.energy.gov/pppo/paducah-site-future-use",
            "note": (
                "DOE's stated most-likely end state is 'a combination of "
                "industrial and recreational use'; an Environmental "
                "Assessment and FONSI cleared the way for transfers."
            ),
        },
    },
    "permitting_pathways": [
        {
            "regime": "CERCLA Federal Facility Agreement",
            "applies": (
                "Governs all site remediation under the 1998 tri-party FFA "
                "(DOE lead; EPA Region 4 + Kentucky EEC co-regulators); a "
                "'Decision 2029' initiative aims to consolidate 50+ "
                "regulatory documents into five."
            ),
            "authority": "EPA Region 4 + Kentucky Energy and Environment Cabinet",
            "url": "https://eec.ky.gov/Environmental-Protection/Waste/hazardous-waste/Pages/paducah-gaseous-diffusion-plant.aspx",
        },
        {
            "regime": "Kentucky electric generation siting",
            "applies": (
                "The KY State Board on Electric Generation and Transmission "
                "Siting reviews merchant plants ≥10 MW — whether it asserts "
                "jurisdiction over NextEra's ~2 GW gas build on federal "
                "land is UNCONFIRMED either way."
            ),
            "authority": "KY Electric Generation and Transmission Siting Board",
            "url": "https://psc.ky.gov/Home/EGTSB",
        },
        {
            "regime": "Utility service approval",
            "applies": (
                "Big Rivers Electric (wholesale), Jackson Purchase Energy, "
                "and Paducah Power System are the announced utility "
                "partners; Kentucky PSC approval of the power-service "
                "agreement was still needed as of the July 2026 "
                "announcement."
            ),
            "authority": "Kentucky Public Service Commission",
            "url": "https://www.lpm.org/news/2026-07-30/100b-data-center-gas-fired-power-plant-to-be-developed-around-paducah-doe-site",
        },
        {
            "regime": "NRC licensing",
            "applies": (
                "NRC oversight of the enrichment plant ended when USEC's "
                "Certificate of Compliance terminated (2014). A NEW NRC "
                "license is required for General Matter's enrichment plant "
                "or any future private reactor; the DUF6 mission runs under "
                "DOE nuclear-safety orders."
            ),
            "authority": "U.S. Nuclear Regulatory Commission",
            "url": "https://www.govinfo.gov/content/pkg/FR-2013-10-31/html/2013-25966.htm",
        },
        {
            "regime": "DOE NEPA process for the AI/energy campus",
            "applies": (
                "DOE ran an RFI (April 7, 2025, 16 sites) and a competitive "
                "RFO (due January 30, 2026); the Paducah Citizens Advisory "
                "Board endorsed the use (Recommendation 25-01). No "
                "campus-level NEPA determination had been published as of "
                "late August 2026 — pre-award infrastructure CXs exist."
            ),
            "authority": "U.S. Department of Energy",
            "url": "https://www.energy.gov/sites/default/files/2025-06/Recommendation%20No25-01%20Artificial%20Intelligence%20on%20DOE%20Paducah%20Gaseous%20Diffusion%20Site_0.pdf",
        },
    ],
    "infrastructure": [
        {
            "category": "power_td",
            "summary": (
                "Four switchyards historically supported up to 3,000 MW "
                "(peak demand 3,040 MW); the last came offline in 2021, "
                "replaced by a TVA-built system sized for the ~12 MW "
                "cleanup load (up to 40 MW capacity). NextEra's award "
                "pairs ~2 GW of new gas with transmission upgrades and up "
                "to 2.6 GW of storage. TVA's Shawnee Fossil Plant (nine "
                "coal units, 1,206 MW summer net) operates nearby — TVA "
                "land, not DOE."
            ),
            "source_label": "DOE-EM — Paducah electrical realignment",
            "source_url": "https://www.energy.gov/em/articles/downsizing-atomic-city-paducah-realigns-electrical-system-cleanup-mission",
            "extra_sources": [
                {
                    "label": "NextEra — Paducah American Energy Hub",
                    "url": "https://www.project.nexteraenergyresources.com/paducah-american-energy-hub",
                },
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "natural_gas",
            "summary": (
                "Texas Gas Transmission's >6,000-mile interstate system "
                "runs through western Kentucky (HQ in Owensboro). Per a "
                "siting-data aggregator (not independently confirmed): the "
                "nearest gas line is ~4.3 miles out and a Texas Gas "
                "receipt point ~14 miles away lists >100,000 dekatherms/"
                "day of capacity — indicative figures for the 2 GW gas "
                "build, not verified engineering."
            ),
            "source_label": "LandGate — Paducah siting profile (aggregator)",
            "source_url": "https://www.landgate.com/news/doe-s-100-billion-paducah-bet",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "water",
            "summary": (
                "The site's Ohio River water plant was designed for ~30 "
                "MGD (current cleanup-era use is ~1 MGD). The announced "
                "campus commits to closed-loop cooling at under 5 MGD — "
                "less than the plant's original design draw."
            ),
            "source_label": "DOE-EM — Paducah water system",
            "source_url": "https://www.energy.gov/em/articles/water-pump-project-improves-efficiency-sustainability-paducah-site-0",
            "extra_sources": [
                {
                    "label": "Louisville Public Media — campus water commitment",
                    "url": "https://www.lpm.org/news/2026-07-30/100b-data-center-gas-fired-power-plant-to-be-developed-around-paducah-doe-site",
                },
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "rail",
            "summary": (
                "On-site heavy rail survives from the enrichment era; the "
                "historic Kevil branch is now part of the Paducah & "
                "Louisville Railway, a 270-route-mile Class II railroad "
                "connecting Paducah to Louisville with branches to "
                "Mayfield, Kevil, and Elizabethtown."
            ),
            "source_label": "Paducah & Louisville Railway",
            "source_url": "https://en.wikipedia.org/wiki/Paducah_%26_Louisville_Railway",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "road",
            "summary": (
                "US-60 is the primary access; the adjacent WKWMA entrance "
                "is about 7 miles from I-24 Exit 4, and the reservation "
                "carries 19 miles of internal roadway."
            ),
            "source_label": "KDFWR — West Kentucky WMA",
            "source_url": "https://app.fw.ky.gov/public_lands_search/detail.aspx?Kdfwr_id=137",
            "extra_sources": [
                {"label": "DOE PPPO — site description", "url": "https://www.energy.gov/pppo/paducah-site-description"},
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "fiber",
            "summary": (
                "NextEra's project materials state the site already has "
                "fiber connectivity. Per a siting-data aggregator (not "
                "independently confirmed): a Quad State Internet exchange "
                "point sits ~0.1 mile away with Uniti/Windstream routes "
                "nearby. Paducah Power System separately operates a "
                "61-mile city fiber backbone, not confirmed to reach the "
                "DOE site."
            ),
            "source_label": "NextEra — Paducah American Energy Hub",
            "source_url": "https://www.project.nexteraenergyresources.com/paducah-american-energy-hub",
            "extra_sources": [
                {"label": "LandGate — siting profile (aggregator)", "url": "https://www.landgate.com/news/doe-s-100-billion-paducah-bet"},
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "workforce",
            "summary": (
                "About 1,400 contractor workers run D&D and waste "
                "disposition today (the DUF6 plant alone employs ~225). "
                "Kentucky's Nuclear Energy Development Authority (SB198, "
                "2024) is funding the pipeline: $1.5M to West Kentucky "
                "Community & Technical College and $1.9M to the West "
                "Kentucky Educational Cooperative for nuclear-workforce "
                "programs."
            ),
            "source_label": "DOE-EM — Paducah workforce",
            "source_url": "https://www.energy.gov/em/articles/paducah-bridges-generational-knowledge-legacy-building-deactivation",
            "extra_sources": [
                {
                    "label": "WKCTC — $1.9M WKEC nuclear-STEM grant",
                    "url": "https://westkentucky.kctcs.edu/newsroom/news/2026/03-31-wkec-grant.aspx",
                },
            ],
            "verified_at": VERIFIED_AT,
        },
    ],
    "parcels": [
        {
            "id": "paducah-ai-campus",
            "name": "AI/HPC innovation campus — Brookfield / NextEra",
            "kind": "leased_energy",
            "lat": 37.1110,
            "lon": -88.8100,
            "coord_note": "Approximate site-center reference; DOE has not published the campus parcel boundary.",
            "approx_acres": 600,
            "corpus_site_id": "KY8890008982",
            "clup_designation": None,
            "clup_note": "~600 acres reported leased for the data-center campus within the 3,556-acre reservation.",
            "status": (
                "Announced July 29, 2026: Brookfield develops and operates "
                "a 1.8 GW AI/HPC campus; NextEra builds ~2 GW of new gas "
                "generation plus up to 2.6 GW of battery storage (~4.6 GW "
                "of dedicated generation), with Big Rivers Electric, "
                "Jackson Purchase Energy, and Paducah Power as utility "
                "partners. Total investment is cited at ~$100B with ~8,000 "
                "construction and ~600 permanent jobs; completion is "
                "reported as 2031 or 2032 depending on source."
            ),
            "availability": (
                "Committed under the July 2026 award (following DOE's "
                "April 2025 RFI and January 2026 RFO); Kentucky PSC "
                "approval of the power-service agreement remains pending."
            ),
            "source_url": "https://www.energy.gov/em/articles/us-energy-department-seeks-proposals-ai-data-centers-energy-projects-paducah-site",
            "extra_sources": [
                {
                    "label": "NextEra — Paducah American Energy Hub",
                    "url": "https://www.project.nexteraenergyresources.com/paducah-american-energy-hub",
                },
                {
                    "label": "Louisville Public Media — $100B award coverage",
                    "url": "https://www.lpm.org/news/2026-07-30/100b-data-center-gas-fired-power-plant-to-be-developed-around-paducah-doe-site",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "ai_datacenter",
                    "fit": "anchored",
                    "rationale": (
                        "A formal DOE RFO produced the award, ~600 acres "
                        "are reported leased, and the utility partners are "
                        "named — the furthest-along federal AI-DC site."
                    ),
                },
                {
                    "kind": "gas_generation",
                    "fit": "strong",
                    "rationale": (
                        "NextEra's ~2 GW gas plan is central to the award "
                        "but still needs its permits and the pending KY PSC "
                        "power-service approval."
                    ),
                },
                {
                    "kind": "battery_storage",
                    "fit": "strong",
                    "rationale": "Up to 2.6 GW of BESS is in the announced generation package.",
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "anchored",
                    "constraint": "power",
                    "rationale": (
                        "Committed, awarded project with ~600 acres "
                        "reported leased and dedicated generation planned; "
                        "the pending KY PSC service approval is the "
                        "remaining formal step."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "conditional",
                    "constraint": "licensing",
                    "rationale": (
                        "The committed generation for this load is gas plus "
                        "storage, not nuclear; a GW-class reactor would "
                        "need a future developer and an NRC license from "
                        "scratch."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "conditional",
                    "constraint": "licensing",
                    "rationale": (
                        "DOE's RFI named nuclear as an option across its 16 "
                        "sites, but no SMR developer or filing is tied to "
                        "Paducah and the awarded plan is gas + BESS."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "conditional",
                    "constraint": "power",
                    "rationale": (
                        "Scale mismatch — a 1-20 MWe unit cannot "
                        "meaningfully serve a 1.8 GW committed load; it "
                        "fits only as an ancillary application nobody has "
                        "proposed."
                    ),
                },
            ],
        },
        {
            "id": "paducah-process-buildings",
            "name": "GDP process-building footprint (C-333 / C-337 …)",
            "kind": "cleanup_core",
            "lat": 37.1140,
            "lon": -88.8140,
            "coord_note": "Approximate — within the ~750-acre fenced area; no building-specific public coordinate.",
            "approx_acres": 74,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "~74 acres under roof across the cascade buildings, inside the ~750-acre fenced area.",
            "status": (
                "The legacy D&D core. C-333 became the first process "
                "building fully deactivated (all 497 converters removed by "
                "2026); C-337 is next, with worker training underway as of "
                "June 2026. Sitewide cleanup is projected through 2065, "
                "with buildings sequentially cleared."
            ),
            "availability": (
                "Not available while active D&D continues — individual "
                "footprints clear sequentially over the coming decades."
            ),
            "source_url": "https://www.energy.gov/em/articles/paducah-achieves-goal-remove-497-converters-first-process-building",
            "extra_sources": [
                {
                    "label": "DOE-EM — C-337 deactivation training",
                    "url": "https://www.energy.gov/em/articles/paducah-bridges-generational-knowledge-legacy-building-deactivation",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "waste_disposal",
                    "fit": "anchored",
                    "rationale": (
                        "Deactivation, demolition, and waste disposition "
                        "are this footprint's mission on a published "
                        "timeline through 2065."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "conditional",
                    "constraint": "mission",
                    "rationale": (
                        "Gated on completing deactivation/demolition "
                        "(C-333 done, C-337 underway) and a DOE "
                        "transfer/lease decision for the cleared footprint."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "conditional",
                    "constraint": "licensing",
                    "rationale": (
                        "The D&D-completion gate is compounded by NRC site "
                        "characterization on a legacy contaminated "
                        "footprint — years beyond simple demolition."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "conditional",
                    "constraint": "mission",
                    "rationale": (
                        "Same D&D-completion gate; a smaller footprint "
                        "could fit sooner post-clearance, but nothing is "
                        "proposed."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "conditional",
                    "constraint": "mission",
                    "rationale": (
                        "Smallest footprint requirement of the four, so "
                        "plausibly earliest once a sub-parcel clears — "
                        "still unproposed."
                    ),
                },
            ],
        },
        {
            "id": "paducah-duf6",
            "name": "DUF6 Conversion Facility",
            "kind": "operating_mission",
            "lat": 37.1080,
            "lon": -88.8060,
            "coord_note": "Approximate site-center reference; no facility-specific public coordinate.",
            "approx_acres": 100,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "~100 acres of the 3,556-acre site.",
            "status": (
                "The operating DOE conversion mission: Mid-America "
                "Conversion Services (Atkins/Fluor/Westinghouse) converts "
                "depleted uranium hexafluoride to uranium oxide, with "
                "1,000+ cylinders converted in 2025 as an EM priority. "
                "About 225 people work here; no firm mission-end date is "
                "published."
            ),
            "availability": "Not available while the conversion mission operates.",
            "source_url": "https://www.energy.gov/pppo/depleted-uranium-hexafluoride-duf6-conversion",
            "extra_sources": [
                {
                    "label": "DOE-EM — 1,000 cylinders converted (2025)",
                    "url": "https://www.energy.gov/em/articles/em-priority-crews-convert-1000-cylinders-duf6-2025",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "waste_disposal",
                    "fit": "anchored",
                    "rationale": "DUF6 conversion IS this parcel's operating use.",
                },
            ],
            "facility_fit": [
                {
                    "type": t,
                    "fit": "precluded",
                    "constraint": "mission",
                    "rationale": (
                        "The ~100-acre footprint is occupied by an active "
                        "DOE conversion mission with no announced end "
                        "date — a mission constraint, not a permanent "
                        "legal bar."
                    ),
                }
                for t in FACILITY_TYPES
            ],
        },
        {
            "id": "paducah-general-matter",
            "name": "General Matter enrichment site (100-acre lease)",
            "kind": "leased_industrial",
            "lat": 37.1150,
            "lon": -88.8050,
            "coord_note": "Approximate — the leased parcel's location within the reservation is not published.",
            "approx_acres": 100,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "Leased under Hall Amendment authority, August 2025.",
            "status": (
                "DOE leased ~100 acres to General Matter (August 2025) for "
                "a $1.5B LEU/HALEU enrichment plant, including access to "
                "at least 7,600 cylinders of existing DOE UF6 feedstock; "
                "the company won a ~$900M federal HALEU contract in "
                "January 2026. Construction was reported to target 2026, "
                "with enrichment operations planned for 2034."
            ),
            "availability": "Committed — the parcel is under an executed enrichment lease.",
            "source_url": "https://fissilematerials.org/blog/2025/08/general_matter_leases_a_s.html",
            "extra_sources": [
                {
                    "label": "World Nuclear News — General Matter Paducah plant",
                    "url": "https://www.world-nuclear-news.org/articles/general-matter-plans-new-enrichment-plant-in-paducah",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "nuclear_fuel_cycle",
                    "fit": "anchored",
                    "rationale": (
                        "An executed DOE lease, feedstock rights, and a "
                        "federal HALEU contract make this a committed "
                        "fuel-cycle project (NRC licensing still ahead)."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": t,
                    "fit": "precluded",
                    "constraint": "land",
                    "rationale": (
                        "The full 100-acre parcel is committed under an "
                        "executed DOE lease to the enrichment build — "
                        "nothing else sites here while that holds."
                    ),
                }
                for t in FACILITY_TYPES
            ],
        },
        {
            "id": "paducah-wkwma",
            "name": "West Kentucky WMA — conservation buffer with a carve-out precedent",
            "kind": "conservation",
            "lat": 37.1332,
            "lon": -88.8139,
            "coord_note": "WKWMA public entrance coordinate, published by KDFWR.",
            "approx_acres": 4495,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": (
                "~1,208 acres remain DOE-licensed and ~1,481 TVA-licensed "
                "within the WMA as of the 2025 land actions."
            ),
            "status": (
                "The state-managed conservation and recreation buffer "
                "around the reservation. It is also the proof that the "
                "designation is revisable: effective June 30, 2025, 545.66 "
                "DOE-licensed acres were removed from the KDFWR license "
                "for economic development, and a 665-acre tract swap "
                "enabled Global Laser Enrichment's adjacent $1.76B "
                "project."
            ),
            "availability": (
                "Not available while under the WMA license — but the 2025 "
                "carve-outs show the removal mechanism when a project "
                "clears the bar."
            ),
            "source_url": "https://app.fw.ky.gov/public_lands_search/detail.aspx?Kdfwr_id=137",
            "extra_sources": [
                {
                    "label": "KDFWR — land swap closes portion of WKWMA",
                    "url": "https://fw.ky.gov/News/Pages/PSA-Land-swap-for-major-economic-development-project-closes-portion-of-West-Kentucky-WMA-to-public-access.aspx",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "conservation",
                    "fit": "anchored",
                    "rationale": "KDFWR management is the standing use of the buffer.",
                },
            ],
            "facility_fit": [
                {
                    "type": t,
                    "fit": "precluded",
                    "constraint": "land",
                    "rationale": (
                        "The wildlife-management designation forecloses "
                        "industrial siting as it stands — though the 2025 "
                        "carve-outs (545.66 acres removed; the GLE swap) "
                        "prove the license is revisable through a formal "
                        "removal process, unlike a statutory bar."
                    ),
                }
                for t in FACILITY_TYPES
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Waste Isolation Pilot Plant (NM)
# ---------------------------------------------------------------------------

WIPP_SITE = {
    "site_id": "wipp",
    "site_label": "WIPP",
    "site_overview": {
        "name": "Waste Isolation Pilot Plant",
        "state": "NM",
        "county": "Eddy",
        "size_sq_mi": 16,
        "summary": (
            "WIPP is the nation's only operating deep geologic repository, "
            "emplacing defense transuranic waste 2,150 feet down in the "
            "Salado salt since 1999 on a 16-section (10,240-acre) federal "
            "land withdrawal, with DOE anticipating operations beyond "
            "2050. The reuse story is the withdrawal's balance: DOE's "
            "Cleanup-to-Clean-Energy program identified ~9,000 acres for "
            "carbon-free energy (naming solar, wind, AND nuclear), and "
            "selected NextEra in September 2024 to negotiate a solar + "
            "storage lease. Water — not land — is the binding constraint: "
            "WIPP's own supply is capped at 6.6 million gallons per YEAR, "
            "piped 31 miles from Carlsbad."
        ),
        "managers": [
            {
                "role": "Operator (site owner)",
                "who": "DOE-EM Carlsbad Field Office; M&O contractor Salado Isolation Mining Contractors (Bechtel-led, contract extended Dec 2025)",
                "url": "https://www.energy.gov/em/waste-isolation-pilot-plant-wipp",
            },
            {
                "role": "State regulator",
                "who": (
                    "NM Environment Department — RCRA hazardous waste "
                    "permit (effective Nov 3, 2023; a 2026 revision "
                    "dedicates 55% of disposal volume to LANL legacy waste "
                    "through 2031, rising to 75%)"
                ),
                "url": "https://www.env.nm.gov/hazardous-waste/wipp/",
            },
            {
                "role": "Federal certifier",
                "who": "EPA certifies long-term disposal safety under 40 CFR 191/194 every five years (last recertified May 3, 2022; next application due by Nov 26, 2026)",
                "url": "https://www.epa.gov/radiation/certification-and-recertification-wipp",
            },
            {
                "role": "Surface administration",
                "who": "BLM administers grazing and secondary surface uses on the withdrawal balance, subject to DOE's statutory jurisdiction and WIPP-purpose priority",
                "url": "https://www.emnrd.nm.gov/wipp-transportation-safety-program/frequently-asked-questions-about-wipp/",
            },
        ],
        "land_use_plan": {
            "label": "WIPP Land Withdrawal Act (P.L. 102-579, 1992) + WIPP Land Management Plan",
            "url": "https://www.congress.gov/102/statute/STATUTE-106/STATUTE-106-Pg4777.pdf",
            "note": (
                "The Act withdrew the 16 sections from mining and mineral "
                "leasing, gave WIPP purposes priority, and lets the "
                "Secretary permit non-WIPP uses — the authority DOE "
                "exercised for the 2024 clean-energy solicitation."
            ),
        },
    },
    "permitting_pathways": [
        {
            "regime": "WIPP Land Withdrawal Act",
            "applies": (
                "Governs all use of the 10,240-acre withdrawal: land is "
                "withdrawn from mining and mineral leasing, WIPP purposes "
                "have priority, and the Secretary of Energy may permit "
                "non-WIPP uses — the basis for the clean-energy leasing."
            ),
            "authority": "U.S. DOE (Secretary of Energy) under P.L. 102-579",
            "url": "https://www.congress.gov/102/statute/STATUTE-106/STATUTE-106-Pg4777.pdf",
        },
        {
            "regime": "NMED RCRA hazardous waste permit",
            "applies": (
                "Regulates the hazardous component of TRU mixed waste "
                "(co-permittees DOE + SIMCO); the current permit took "
                "effect Nov 3, 2023 and a 2026 revision mandates higher "
                "LANL legacy-waste shares."
            ),
            "authority": "New Mexico Environment Department",
            "url": "https://www.env.nm.gov/hazardous-waste/wipp/",
        },
        {
            "regime": "EPA 40 CFR 191/194 certification",
            "applies": (
                "Certifies 10,000-year disposal safety on a five-year "
                "recertification cycle; the next compliance application is "
                "due on or before November 26, 2026. Physical repository "
                "changes route through EPA Planned Change Requests — most "
                "recently the July 31, 2025 approval of replacement Panels "
                "11 and 12."
            ),
            "authority": "U.S. EPA",
            "url": "https://www.epa.gov/radiation/certification-and-recertification-wipp",
        },
        {
            "regime": "NM PRC siting review",
            "applies": (
                "New Mexico's certificate requirement attaches to 'public "
                "utilities' serving the public; a merchant clean-energy "
                "project on federal land likely falls outside it — a legal "
                "INFERENCE flagged as such, not a confirmed determination."
            ),
            "authority": "NM Public Regulation Commission (jurisdiction uncertain)",
            "url": "https://codes.findlaw.com/nm/chapter-62-electric-gas-and-water-utilities/nm-st-sect-62-9-3/",
        },
        {
            "regime": "DOE NEPA review",
            "applies": (
                "Any DOE realty action on the withdrawal (a clean-energy "
                "lease included) requires NEPA review; no WIPP-solar EA or "
                "CX had been published as of August 2026, consistent with "
                "the NextEra project still being in realty negotiation."
            ),
            "authority": "U.S. Department of Energy",
            "url": "https://www.energy.gov/nepa/doe-categorical-exclusion-cx-determinations",
        },
    ],
    "infrastructure": [
        {
            "category": "power_td",
            "summary": (
                "Xcel Energy's Southwestern Public Service serves the "
                "area, with a 345 kV regional backbone through Eddy "
                "County. SPS told the NM Legislature it is building 200+ "
                "miles of new distribution feeders across Eddy and Lea "
                "counties for oil-and-gas electrification — an actively "
                "expanding, strained grid rather than idle headroom."
            ),
            "source_label": "NM Legislature — SPS Eddy/Lea buildout testimony",
            "source_url": "https://www.nmlegis.gov/handouts/WNR%20102824%20Item%2011%20Xcel%20Energy%20ETA.pdf",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "natural_gas",
            "summary": (
                "Gas is regionally abundant: El Paso Natural Gas "
                "(~10,140-mile Kinder Morgan system) and Energy Transfer's "
                "Transwestern Pipeline both cross the Permian Basin around "
                "the site."
            ),
            "source_label": "El Paso Natural Gas system overview",
            "source_url": "https://en.wikipedia.org/wiki/El_Paso_Natural_Gas",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "water",
            "summary": (
                "THE binding constraint. WIPP's water arrives by a "
                "31-mile pipeline DOE built in 1984 from Carlsbad's "
                "Double Eagle wellfield; under the 2009 transfer "
                "agreement Carlsbad supplies WIPP up to 6.6 million "
                "gallons per YEAR. The Pecos River basin adjudication has "
                "been pending since 1956 and the interstate compact "
                "obligates deliveries to Texas — there is no evident "
                "surplus for a new large water-intensive use."
            ),
            "source_label": "DOE — WIPP water line transfer (2009)",
            "source_url": "https://www.wipp.energy.gov/pr/2009/WIPP_Water_Line_6-18-09.pdf",
            "extra_sources": [
                {"label": "NM OSE — Pecos basin", "url": "https://www.ose.nm.gov/Basins/Pecos/isc_Pecos.php"},
            ],
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "rail",
            "summary": (
                "BNSF's Carlsbad and Loving industrial spurs serve the "
                "regional potash corridor (BNSF resumed direct operation "
                "when Southwestern Railroad's contract ended in January "
                "2017). TRU waste itself moves to WIPP exclusively by "
                "truck in NRC-certified casks — the spur is a freight "
                "asset, not the waste pathway."
            ),
            "source_label": "Federal Register — Southwestern Railroad discontinuance",
            "source_url": "https://www.federalregister.gov/documents/2017/02/06/2017-02427/southwestern-railroad-inc-discontinuance-of-service-exemption-in-curry-roosevelt-chaves-and-eddy",
            "verified_at": VERIFIED_AT,
        },
        {
            "category": "road",
            "summary": (
                "US-62/180 is the designated WIPP transportation corridor. "
                "DOE's own pages disagree on the Carlsbad distance — 26 "
                "miles (wipp.energy.gov, NM EMNRD) vs 33 miles (the DOE-EM "
                "page); both are cited, unresolved."
            ),
            "source_label": "WIPP — about the site",
            "source_url": "https://wipp.energy.gov/about-us.asp",
            "extra_sources": [
                {"label": "DOE-EM — WIPP overview (33-mi figure)", "url": "https://www.energy.gov/em/waste-isolation-pilot-plant-wipp"},
            ],
            "verified_at": VERIFIED_AT,
        },
        # fiber: omitted — no public source documents fiber at or near WIPP.
        {
            "category": "workforce",
            "summary": (
                "The best citable headcount is ~1,100 employees as of June "
                "2017 (DOE's site-by-the-numbers sheet) — dated, and "
                "plausibly higher today given shaft and ventilation "
                "construction since, but no current figure is published. "
                "Regional nuclear workforce context: URENCO's Eunice "
                "enrichment plant (~40 mi class, Lea County) employs 230+ "
                "directly and supplies about a third of US enrichment "
                "demand."
            ),
            "source_label": "DOE — WIPP site by the numbers (2017)",
            "source_url": "https://www.energy.gov/sites/prod/files/2017/08/f36/WIPP%20Site%20by%20Numbers%20June%202017.pdf",
            "extra_sources": [
                {"label": "URENCO USA — capacity expansion", "url": "https://www.urenco.com/news/usa/2025/urenco-usa-expands-u.s-enrichment-capacity-with-second-new-cascade"},
            ],
            "verified_at": VERIFIED_AT,
        },
    ],
    "parcels": [
        {
            "id": "wipp-repository-core",
            "name": "WIPP surface facilities + repository core",
            "kind": "operating_mission",
            "lat": 32.3714,
            "lon": -103.7924,
            "coord_note": "Los Medanos area reference point; DOE's exclusive-use surface area is 1,453.90 acres.",
            "approx_acres": 1454,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": "The Land Withdrawal Act reserves this core to WIPP purposes while the repository operates.",
            "status": (
                "The active mission core: waste handling building, five "
                "shafts (the 2,275-ft utility shaft reached depth in "
                "October 2023), and the repository 2,150 feet down in the "
                "Salado salt. EPA approved replacement Panels 11 and 12 on "
                "July 31, 2025 after Panels 9 and 10 were abandoned for "
                "ground conditions; the new 540,000-cfm ventilation system "
                "targets full operation in 2026. DOE anticipates operating "
                "beyond 2050."
            ),
            "availability": "None — the nation's only operating deep geologic TRU repository.",
            "source_url": "https://www.energy.gov/em/waste-isolation-pilot-plant-wipp",
            "extra_sources": [
                {
                    "label": "Federal Register — EPA approval of Panels 11/12",
                    "url": "https://www.federalregister.gov/documents/2025/08/19/2025-15741/approval-of-replacement-waste-panels-11-and-12-at-the-waste-isolation-pilot-plant",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "waste_disposal",
                    "fit": "anchored",
                    "rationale": (
                        "TRU disposal is the statutory purpose of this "
                        "land under the Land Withdrawal Act, for decades "
                        "yet."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": t,
                    "fit": "precluded",
                    "constraint": "mission",
                    "rationale": (
                        "The operating repository core is reserved to WIPP "
                        "purposes under the Land Withdrawal Act while the "
                        "mission runs (anticipated beyond 2050) — and even "
                        "WIPP's own water allocation is only 6.6 million "
                        "gallons per year."
                    ),
                }
                for t in FACILITY_TYPES
            ],
        },
        {
            "id": "wipp-lwa-balance",
            "name": "Land Withdrawal Area balance — the clean-energy acreage",
            "kind": "leased_energy",
            "lat": 32.3700,
            "lon": -103.8000,
            "coord_note": "Withdrawal-area reference point; the ~8,786-acre balance surrounds the fenced core.",
            "approx_acres": 8786,
            "corpus_site_id": None,
            "clup_designation": None,
            "clup_note": (
                "BLM administers grazing/secondary surface uses on the "
                "balance; DOE retains statutory jurisdiction with "
                "WIPP-purpose priority."
            ),
            "status": (
                "DOE's Cleanup-to-Clean-Energy RFI (February 2024) "
                "identified ~9,000 contiguous acres here for carbon-free "
                "energy, explicitly naming solar, wind, and nuclear as "
                "eligible. DOE selected NextEra in September 2024 to "
                "negotiate a realty agreement for at least 150 MW of solar "
                "plus 100 MW of storage on up to 1,800 acres — still at "
                "the realty-negotiation stage as of August 2026, leaving "
                "roughly 7,200 acres uncommitted."
            ),
            "availability": (
                "In negotiation (solar) with most of the acreage "
                "uncommitted; every use competes with the water reality — "
                "WIPP's own allocation is 6.6 million gallons per year."
            ),
            "source_url": "https://www.energy.gov/em/em-clean-energy-land-reuse",
            "extra_sources": [
                {
                    "label": "DOE — WIPP clean-energy RFI (solar/wind/nuclear eligible)",
                    "url": "https://www.energy.gov/em/articles/us-department-energy-issues-request-information-potential-clean-energy-projects-wipp",
                },
                {
                    "label": "DOE — NextEra selected for WIPP solar",
                    "url": "https://www.energy.gov/em/articles/doe-selects-nextera-energy-large-scale-solar-project-waste-isolation-pilot-plant",
                },
            ],
            "verified_at": VERIFIED_AT,
            "opportunities": [
                {
                    "kind": "solar_storage",
                    "fit": "strong",
                    "rationale": (
                        "NextEra was selected September 2024, but no "
                        "signed lease or construction start is public — "
                        "the realty agreement is the gate."
                    ),
                },
                {
                    "kind": "battery_storage",
                    "fit": "strong",
                    "rationale": "The selected proposal pairs 100 MW of storage with the solar.",
                },
                {
                    "kind": "advanced_nuclear",
                    "fit": "conditional",
                    "rationale": (
                        "DOE's own RFI names nuclear as eligible on this "
                        "acreage; water supply (or dry cooling) and a "
                        "licensing pathway are the gates."
                    ),
                },
            ],
            "facility_fit": [
                {
                    "type": "data_center",
                    "fit": "conditional",
                    "constraint": "water",
                    "rationale": (
                        "The Land Withdrawal Act lets the Secretary approve "
                        "non-WIPP uses (the solar solicitation is the "
                        "precedent), but there is no proven water source "
                        "beyond WIPP's committed 6.6 million gallons/year "
                        "and no committed interconnection point on this "
                        "parcel."
                    ),
                },
                {
                    "type": "lwr_pwr",
                    "fit": "precluded",
                    "constraint": "water",
                    "rationale": (
                        "Land is sufficient but water is fatal: the basin "
                        "is fully committed among Carlsbad, potash, and "
                        "oil-and-gas users, the Pecos adjudication has been "
                        "open since 1956, and a Vogtle-class unit needs "
                        "roughly 20+ MGD — three orders of magnitude above "
                        "WIPP's own annual allocation."
                    ),
                },
                {
                    "type": "smr",
                    "fit": "conditional",
                    "constraint": "water",
                    "rationale": (
                        "DOE's RFI explicitly lists nuclear as eligible "
                        "here — a named primary-source signal — but a new "
                        "water right or a dry-cooled design, plus a "
                        "licensing pathway, must come first."
                    ),
                },
                {
                    "type": "microreactor",
                    "fit": "strong",
                    "constraint": "water",
                    "rationale": (
                        "Small footprint in ~7,200 uncommitted acres, "
                        "near-zero wet-cooling draw for most 1-20 MWe "
                        "designs, DOE has already named nuclear as "
                        "eligible, and DOE-EM is the site's own landlord — "
                        "not anchored only because no developer has been "
                        "selected."
                    ),
                },
            ],
        },
    ],
}


SITES = {
    "srs": SRS_SITE,
    "portsmouth": PORTSMOUTH_SITE,
    "paducah": PADUCAH_SITE,
    "wipp": WIPP_SITE,
}


def output_path(site_id: str) -> Path:
    return DATA_DIR / f"{site_id}-e2e.json"


def geojson_dir(site_id: str) -> Path:
    return DATA_DIR / f"{site_id}-nepa"


def cache_path_fn(site_id: str):
    cache_dir = CACHE_ROOT / f"{site_id}-nepa"
    def cache_path(parcel_id: str, source: str) -> Path:
        return cache_dir / f"{parcel_id}--{source}.json"
    return cache_path


def _source_defs() -> "tuple[screening.SourceDef, ...]":
    """The eight-source matrix — Hanford's ten minus the Pacific-marine pair."""
    normalize_padus = screening.make_normalize_padus(PADUS_POINT_BUFFER_MILES)
    return (
        screening.SourceDef(
            "ipac", "ipac", "get_ipac_resources_in_roi", screening.normalize_ipac,
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
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES, f"DOE site E2E — {s['name']}"),
        ),
    )


def validate_site(site: "dict[str, Any]") -> None:
    """Contract check before any network spend — mirrors the Hanford builder."""
    parcels = site["parcels"]
    ids = [p["id"] for p in parcels]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{site['site_id']}: duplicate parcel ids")
    for parcel in parcels:
        if not str(parcel.get("source_url", "")).startswith("https://"):
            raise SystemExit(f"{parcel['id']}: missing https source_url")
        if len(str(parcel.get("verified_at", ""))) != 10:
            raise SystemExit(f"{parcel['id']}: missing verified_at stamp")
        for opp in parcel.get("opportunities", []):
            if opp["kind"] not in OPPORTUNITY_KINDS:
                raise SystemExit(f"{parcel['id']}: unknown opportunity kind {opp['kind']}")
            if opp["fit"] not in FIT_VALUES:
                raise SystemExit(f"{parcel['id']}: unknown fit {opp['fit']}")
        facility_types = [ff["type"] for ff in parcel.get("facility_fit", [])]
        if sorted(facility_types) != sorted(FACILITY_TYPES):
            raise SystemExit(
                f"{parcel['id']}: facility_fit must cover exactly {sorted(FACILITY_TYPES)}, got {sorted(facility_types)}"
            )
        for ff in parcel.get("facility_fit", []):
            if ff["fit"] not in FIT_VALUES:
                raise SystemExit(f"{parcel['id']}: unknown facility_fit fit {ff['fit']}")
            if not ff.get("constraint"):
                raise SystemExit(f"{parcel['id']}/{ff['type']}: facility_fit cell missing constraint")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        import schema as schema_mod
    except Exception as exc:  # pydantic absent on this interpreter — CI still validates
        log.warning("schema.py unavailable on this interpreter (%s); CI validator still enforces it", exc)
        return
    for parcel in parcels:
        schema_mod.HanfordParcel.model_validate(parcel)
    for infra_row in site["infrastructure"]:
        schema_mod.DoeInfrastructureRow.model_validate(infra_row)


def write_output(
    site: "dict[str, Any]",
    parcels: "list[dict[str, Any]]",
    tabular: dict,
    geojson_by_id: dict,
    corpus_by_id: "dict[str, dict[str, Any]]",
    all_records: "list[dict[str, Any]]",
    merge_existing: bool = False,
) -> None:
    site_id = site["site_id"]
    out_path = output_path(site_id)
    geo_dir = geojson_dir(site_id)
    geo_dir.mkdir(parents=True, exist_ok=True)
    out_parcels = []
    for parcel in parcels:
        row = dict(parcel)
        row["screening"] = tabular.get(parcel["id"], {})
        geojson = geojson_by_id.get(parcel["id"])
        # A wholesale-failed package must not publish a URL (Codex PR #22 P2).
        meta = (geojson or {}).get("metadata") or {}
        if (
            geojson
            and geojson.get("features") is not None
            and meta.get("status") != "unavailable"
        ):
            path = geo_dir / f"{parcel['id']}.geojson"
            path.write_text(json.dumps(geojson, separators=(",", ":")))
            row["geojson_url"] = f"data/{site_id}-nepa/{parcel['id']}.geojson"
            row["map_summary"] = screening.summarize_map_package(geojson)
        else:
            row["geojson_url"] = None
            row["map_summary"] = None
        corpus_rec = corpus_by_id.get(parcel.get("corpus_site_id") or "")
        row["corpus_record"] = (
            {k: corpus_rec.get(k) for k in hanford.CORPUS_JOIN_FIELDS if corpus_rec.get(k) is not None}
            if corpus_rec
            else None
        )
        row["nearby_tracked"] = hanford.nearby_tracked_records(parcel, all_records)
        out_parcels.append(row)

    if merge_existing:
        # A --parcel refresh must never truncate the published dossier, and a
        # curated-text refresh must never blank evidence (PR #22 findings 1-3).
        if not out_path.exists():
            raise RuntimeError(f"--parcel requires an existing complete {out_path.name}")
        existing = json.loads(out_path.read_text())
        existing_by_id = {p["id"]: p for p in existing.get("parcels", [])}
        for row in out_parcels:
            prev = existing_by_id.get(row["id"])
            if not prev:
                continue
            if not row.get("screening"):
                row["screening"] = prev.get("screening") or {}
            if row.get("geojson_url") is None and prev.get("geojson_url") is not None:
                row["geojson_url"] = prev["geojson_url"]
                row["map_summary"] = prev.get("map_summary")
        by_id = dict(existing_by_id)
        by_id.update({p["id"]: p for p in out_parcels})
        order = {p["id"]: i for i, p in enumerate(site["parcels"])}
        out_parcels = sorted(by_id.values(), key=lambda row: order.get(row["id"], len(order)))

    payload = {
        "generated_at": screening.utc_now(),
        "nepa_mcp_version": screening.NEPA_MCP_VERSION,
        "site_id": site_id,
        "site_label": site["site_label"],
        "screening_buffer_miles": BUFFER_MILES,
        "flood_radius_miles": FLOOD_RADIUS_MILES,
        "flood_unmapped_note": FLOOD_UNMAPPED_NOTE,
        "parcel_count": len(out_parcels),
        "method": (
            "PNNL nepa-mcp structured APIs and Map Composer layers, cached and "
            "rate-limited to at least 1.5 seconds between requests per host; "
            "curated parcel facts verified against primary sources; corpus "
            "fields joined from this project's own enrichment files."
        ),
        "narrative_note": NARRATIVE_NOTE_TEMPLATE.format(date=VERIFIED_AT),
        "site_overview": site["site_overview"],
        "permitting_pathways": site["permitting_pathways"],
        "opportunity_kinds": OPPORTUNITY_KINDS,
        "facility_types": FACILITY_TYPES,
        "infrastructure": site["infrastructure"],
        "limitations": SHARED_LIMITATIONS,
        "sources": SOURCE_META,
        "parcels": out_parcels,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    log.info("wrote %s (%d parcels)", out_path, len(out_parcels))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", action="append", default=[],
        choices=sorted(SITES), help="Only build this site (repeatable; default all)",
    )
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
    site_ids = args.site or sorted(SITES)
    for site_id in site_ids:
        validate_site(SITES[site_id])

    corpus_by_id, all_records = hanford.load_corpus_index()

    # Resolve the full --parcel selection across every site BEFORE any
    # network work or output write. A mixed request like
    # `--site srs --parcel <valid-id> --parcel typo` must reject `typo`
    # without first screening and publishing `<valid-id>` — a command that
    # reports failure must never leave a partially refreshed artifact behind
    # (Codex PR #24 finding: the unmatched check ran after write_output()).
    requested_parcels = set(args.parcel)
    site_parcels: "dict[str, list[dict[str, Any]]]" = {}
    matched_parcels: "set[str]" = set()
    for site_id in site_ids:
        parcels = [p for p in SITES[site_id]["parcels"] if not args.parcel or p["id"] in requested_parcels]
        site_parcels[site_id] = parcels
        matched_parcels.update(p["id"] for p in parcels)

    unmatched = requested_parcels - matched_parcels
    if unmatched:
        raise SystemExit(f"--parcel id(s) not found in any selected site: {sorted(unmatched)}")

    throttled = False
    for site_id in site_ids:
        site = SITES[site_id]
        parcels = site_parcels[site_id]
        if not parcels:
            if args.parcel:
                continue  # selected parcels belong to another site
            raise SystemExit(f"{site_id}: no parcels selected")
        # A --parcel refresh is always a merge onto the published dossier —
        # never fall back to a full rebuild silently if that dossier is
        # missing (Codex PR #24 finding: write_output()'s own guard for this
        # never ran because merge was False whenever out_path was absent).
        merge = bool(args.parcel)

        if args.skip_screening:
            write_output(site, parcels, {}, {}, corpus_by_id, all_records, merge_existing=merge)
            continue

        if not throttled:
            screening.verify_nepa_mcp_version()
            screening.prefer_ipv4()
            screening.install_request_throttle(USER_AGENT)
            throttled = True
        cache_fn = cache_path_fn(site_id)
        tabular = screening.run_source_matrix(
            parcels, _source_defs(), cache_path_fn=cache_fn, use_cache=not args.no_cache
        )
        geojson_by_id: "dict[str, dict[str, Any]]" = {}
        if not args.no_geojson:
            for parcel in parcels:
                try:
                    geojson_by_id[parcel["id"]] = screening.collect_map_geojson(
                        parcel,
                        MAP_LAYERS,
                        BUFFER_MILES,
                        cache_file=cache_fn(parcel["id"], "map-composer"),
                        layer_buffer_overrides=MAP_LAYER_BUFFER_MILES,
                        use_cache=not args.no_cache,
                        limitations=(
                            "Representative-point screening only; parcel boundary unknown. "
                            "Unavailable layers are not no-hit findings."
                        ),
                    )
                except Exception as exc:
                    log.exception("%s / map-composer failed", parcel["id"])
                    geojson_by_id[parcel["id"]] = {
                        "type": "FeatureCollection",
                        "features": [],
                        "metadata": {"status": "unavailable", "error": str(exc)},
                    }
        write_output(site, parcels, tabular, geojson_by_id, corpus_by_id, all_records, merge_existing=merge)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
