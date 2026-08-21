#!/usr/bin/env python3
"""Build docs/data/microreactor-fleet.json — the microreactor vendor fleet,
the named commitments, and the sector demand ladder.

This is a CURATED build script, not a connector (same class as
``build_ap1000_sites.py`` / ``build_nuclear_civilian_sites.py`` /
``build_retired_industrial.py``). Its output is an OVERLAY + reference layer,
NOT a ``SiteRecord`` set, so it stays out of ``schema.py`` and ``refresh.py``.

Provenance — every row is carried forward from one of two sibling projects,
both of which cite primary sources per row:

  1. Microreactor Opportunity Map  (~/Projects/microreactors)
     - ``data/vendors.json``        3 ANPI vendors, deep spec detail
     - ``data/opportunities.json``  14 opportunity rows across 3 tracks
     - ``data/sectors.json``        8 sectors of annual-average load bands
  2. Deployment Core               (~/Projects/Nuclear Deployment)
     - ``app/data.ts`` ``raceEntrants``  11 companies in the Microreactor lane
     - ``app/data.ts`` ``projects``      microreactor / test-reactor projects
     - ``app/data.ts`` ``capacityBands`` the six evidence bands used here
     - ``app/data.ts`` ``proofEvents``   the 2026 criticality record

Two rules inherited from those projects and enforced here:

  * **A megawatt sits in exactly one evidence band** — the strongest state its
    evidence supports. ``framework`` (MOU / announced) capacity is never summed
    with ``contracted`` or ``doe-authorized`` capacity.
  * **Gaps are honest absences.** A field with no located source is ``None``
    and shows as "not found" downstream. Nothing is inferred to fill a blank.

Coordinates for the nine Army Janus installations are JOINED from
``docs/data/ap1000-sites.json`` rather than re-typed, so the two nuclear
surfaces can never disagree about where Fort Wainwright is.

Run:  python3 scripts/build_microreactor_fleet.py
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "docs" / "data"
OUT_PATH = DATA / "microreactor-fleet.json"
AP1000_PATH = DATA / "ap1000-sites.json"

GENERATED_AT = "2026-08-21"

# The evidence ladder, carried verbatim from Deployment Core's `capacityBands`.
# Strongest first. The UI renders in this order and must not re-sort.
EVIDENCE_BANDS = [
    {
        "band": "operational",
        "label": "Operational",
        "rule": "Grid-connected and generating commercial power.",
        "authority": "Grid operator",
    },
    {
        "band": "construction",
        "label": "Nuclear construction",
        "rule": "NRC construction permit issued and physical nuclear work documented.",
        "authority": "NRC",
    },
    {
        "band": "doe-authorized",
        "label": "DOE-authorized build",
        "rule": "Built under a DOE authorization pathway with physical work "
                "documented. Not an NRC license to operate.",
        "authority": "DOE",
    },
    {
        "band": "review",
        "label": "Under review",
        "rule": "Construction-permit or combined-license application docketed "
                "and in active regulator review.",
        "authority": "NRC",
    },
    {
        "band": "contracted",
        "label": "Contracted",
        "rule": "An executed, funded agreement for a named project — offtake, "
                "order, delivery, or development funding — not yet in "
                "regulator review.",
        "authority": "Counterparty",
    },
    {
        "band": "framework",
        "label": "Announced, non-binding",
        "rule": "MOU, LOI, master agreement, or announced target. No executed "
                "project documents.",
        "authority": "None",
    },
]

BAND_IDS = {b["band"] for b in EVIDENCE_BANDS}

# ---------------------------------------------------------------------------
# VENDORS — 11 companies in Deployment Core's "Microreactor" lane, plus Oklo
# as an explicitly-labelled adjacency (its Aurora rating outgrew the ≤20 MWe
# microreactor band but it holds the Eielson award that sits in this pipeline).
#
# `footprint_acres` is the vendor's own published site-footprint claim where
# one exists. Only Westinghouse publishes one, so the rest are None — that
# sparsity is the finding, not a hole to fill (Microreactor Opportunity Map,
# data/gaps.json: land area is 1/14 covered across the whole opportunity set).
# ---------------------------------------------------------------------------
VENDORS = [
    {
        "id": "radiant",
        "name": "Radiant Nuclear",
        "design": "Kaleidos",
        "mwe_low": 1.0, "mwe_high": 1.2, "mwt": 3.0,
        "mwe_label": "1 MWe (3 MWt)",
        "coolant": "Helium (HTGR), prismatic graphite blocks",
        "fuel": "HALEU TRISO (Standard Nuclear, Oak Ridge TN)",
        "refuel_years": 5,
        "service_life_years": 20,
        "mass_tonnes": 70,
        "footprint_acres": None,
        "transport": "Fits a single shipping container",
        "grid_required": None,
        "band": "doe-authorized",
        "band_basis": "First new reactor design fuelled in DOE's DOME test bed at INL; "
                      "signed delivery agreement with the Defense Innovation Unit and "
                      "the Department of the Air Force.",
        "ticker": None,
        "funding_usd": 300000000,
        "funding_note": "$300M Series D on top of a $165M Series C; total raised >$500M. "
                        "Reactor factory foundation in Oak Ridge, TN in 2026.",
        "commercial": "Equinix agreement to purchase 20 reactors.",
        "anpi_site": "Buckley Space Force Base, CO",
        "sources": [
            {"label": "ANS — Radiant signs microreactor contract with the military",
             "url": "https://www.ans.org/news/2025-08-14/article-7277/radiant-signs-contract-on-microreactors-for-the-military/"},
            {"label": "Radiant — first TRISO fuel at INL DOME",
             "url": "https://www.radiantnuclear.com/blog/triso-fuel-inl/"},
            {"label": "Radiant — Series D announcement",
             "url": "https://www.radiantnuclear.com/blog/series-d-announcement/"},
        ],
        "gaps": ["Equinix 20-unit deal: no per-unit price or delivery schedule published",
                 "No published land-area or exclusion-zone footprint"],
    },
    {
        "id": "evinci",
        "name": "Westinghouse",
        "design": "eVinci",
        "mwe_low": 0.005, "mwe_high": 5.0, "mwt": 13.0,
        "mwe_label": "several kWe – 5 MWe",
        "coolant": "Heat pipe (passive)",
        "fuel": "TRISO",
        "refuel_years": 8,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": 2,
        "transport": "Transportable, factory-built",
        "grid_required": None,
        "band": "contracted",
        "band_basis": "DOE selected the eVinci for the first fuelled microreactor "
                      "experiments at the DOME test bed; first commercial customer "
                      "(Saskatchewan Research Council) funded.",
        "ticker": None,
        "funding_usd": None,
        "funding_note": None,
        "commercial": "Saskatchewan Research Council pilot by 2029 (SRC as licensed "
                      "operator, CA$80M government funding). Penn State filed a letter "
                      "of intent with the NRC to host and operate an eVinci (2026-02-28).",
        "anpi_site": "Malmstrom Air Force Base, MT",
        "sources": [
            {"label": "DOE — first microreactor experiments in DOME",
             "url": "https://www.energy.gov/ne/articles/energy-department-announces-first-microreactor-experiments-dome-test-bed"},
            {"label": "POWER — Westinghouse secures first eVinci customer",
             "url": "https://www.powermag.com/westinghouse-secures-first-customer-for-evinci-nuclear-microreactor/"},
            {"label": "Data Center Frontier — eVinci for AI data centers",
             "url": "https://www.datacenterfrontier.com/energy/article/55232808/westinghouse-evinci-microreactor-could-yield-5-mw-of-nuclear-power-every-8-years-for-ai-data-centers"},
        ],
        "gaps": ["No US commercial (non-government) offtake located",
                 "Malmstrom timeline not separately published beyond the ANPI 2030 goal"],
    },
    {
        "id": "antares",
        "name": "Antares Nuclear",
        "design": "R1",
        "mwe_low": 0.1, "mwe_high": 1.0, "mwt": None,
        "mwe_label": "100 kWe – 1 MWe class (200–300 kWe rating)",
        "coolant": "Sodium heat pipe",
        "fuel": "TRISO",
        "refuel_years": 6,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": "Truck-delivered, factory-produced",
        "grid_required": False,
        "band": "doe-authorized",
        "band_basis": "First DOE Reactor Pilot Program participant to reach criticality — "
                      "Mark-0 at INL with the U.S. Army, 2026-06-04.",
        "ticker": None,
        "funding_usd": None,
        "funding_note": None,
        "commercial": None,
        "anpi_site": "Joint Base San Antonio, TX",
        "sources": [
            {"label": "army.mil — Antares zero-power criticality test",
             "url": "https://www.army.mil/article/293057/antares_nuclears_successful_zero_power_criticality_test_marks_major_step_for_military_applications_of_advanced_microreactors"},
            {"label": "DOE — first advanced-reactor criticality",
             "url": "https://www.energy.gov/articles/department-energy-celebrates-first-advanced-reactor-criticality"},
            {"label": "Businesswire — ANPI selection (2026-04-22)",
             "url": "https://www.businesswire.com/news/home/20260422886007/en/Antares-Selected-for-Proposed-Deployment-of-Nuclear-Microreactor-at-Joint-Base-San-Antonio-Under-Department-of-the-Air-Force-ANPI-Initiative"},
        ],
        "gaps": ["No disclosed funding total",
                 "No published land-area or exclusion-zone footprint",
                 "No utility filing located for the JBSA interconnection"],
    },
    {
        "id": "bwxt",
        "name": "BWXT",
        "design": "Project Pele / BANR",
        "mwe_low": 1.0, "mwe_high": 5.0, "mwt": 75.0,
        "mwe_label": "1.5 MWe (Pele unit); 1–5 MWe program target",
        "coolant": "Gas-cooled (HTGR)",
        "fuel": "TRISO",
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": "Transportable — road/rail/air deployable by design",
        "grid_required": False,
        "band": "doe-authorized",
        "band_basis": "Prime contractor building the Project Pele transportable "
                      "microreactor for the Department of Defense at INL.",
        "ticker": "NYSE: BWXT",
        "funding_usd": None,
        "funding_note": None,
        "commercial": None,
        "anpi_site": None,
        "sources": [
            {"label": "DOE — DoD breaks ground on Project Pele",
             "url": "https://www.energy.gov/ne/articles/department-defense-breaks-ground-project-pele-microreactor"},
        ],
        "gaps": ["BANR (the commercial variant) has no named US site or customer on record"],
    },
    {
        "id": "aalo",
        "name": "Aalo Atomics",
        "design": "Aalo-X",
        "mwe_low": 10.0, "mwe_high": 10.0, "mwt": 30.0,
        "mwe_label": "10 MWe (30 MWt); Aalo Pod bundles to 50 MWe",
        "coolant": "Sodium-cooled",
        "fuel": None,
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": None,
        "grid_required": None,
        "band": "doe-authorized",
        "band_basis": "Critical Test Reactor reached DOE-authorized criticality at INL "
                      "on 2026-07-04 — the fourth of the pilot cohort and the first "
                      "new reactor built at INL in 50 years.",
        "ticker": None,
        "funding_usd": None,
        "funding_note": None,
        "commercial": None,
        "anpi_site": None,
        "sources": [
            {"label": "DOE — fourth criticality ahead of the July 4 goal",
             "url": "https://www.energy.gov/articles/department-energy-celebrates-fourth-criticality-ahead-july-4th-goal"},
        ],
        "gaps": ["Commercial Aalo Pod has no named site or offtaker on record"],
    },
    {
        "id": "deep-fission",
        "name": "Deep Fission",
        "design": "Gravity Reactor (borehole)",
        "mwe_low": 5.0, "mwe_high": 15.0, "mwt": 45.0,
        "mwe_label": "up to 15 MWe (45 MWt)",
        "coolant": "Pressurised water, sited ~1 mi underground in a borehole",
        "fuel": None,
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": "Lowered down a 30-inch borehole",
        "grid_required": None,
        "band": "doe-authorized",
        "band_basis": "DOE Reactor Pilot Program selection with a sited pilot at "
                      "Parsons, Kansas; first data-acquisition well drilled.",
        "ticker": "Nasdaq: FISN",
        "funding_usd": None,
        "funding_note": None,
        "commercial": None,
        "anpi_site": None,
        "sources": [
            {"label": "WNN — Deep Fission begins drilling first data-acquisition well",
             "url": "https://www.world-nuclear-news.org/articles/deep-fission-begins-drilling-first-data-acquisition-well"},
        ],
        "gaps": ["NRC pre-application material describes 45 MWt / up to 15 MWe; "
                 "2025 press describes 15 MWt / 5 MWe — the rating is unsettled"],
    },
    {
        "id": "last-energy",
        "name": "Last Energy",
        "design": "PWR-20 (PWR-5 pilot)",
        "mwe_low": 5.0, "mwe_high": 20.0, "mwt": None,
        "mwe_label": "20 MWe (PWR-5 is the 5 MWe pilot)",
        "coolant": "Pressurised water",
        "fuel": None,
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": "Modular, factory-fabricated",
        "grid_required": None,
        "band": "doe-authorized",
        "band_basis": "Selected for the DOE Reactor Pilot Program to build and test "
                      "the PWR-5 at the Texas A&M-RELLIS campus.",
        "ticker": None,
        "funding_usd": None,
        "funding_note": None,
        "commercial": "DP World Thames Freeport (UK) — PWR-20, target online 2030; "
                      "Preliminary Design Review completed with UK ONR July 2025.",
        "anpi_site": None,
        "sources": [
            {"label": "WNN — Last Energy microreactor planned at Texas university",
             "url": "https://www.world-nuclear-news.org/articles/last-energy-microreactor-planned-at-texas-university"},
        ],
        "gaps": ["No US commercial offtake located"],
    },
    {
        "id": "nano-nuclear",
        "name": "NANO Nuclear Energy",
        "design": "KRONOS MMR",
        "mwe_low": 15.0, "mwe_high": 15.0, "mwt": 45.0,
        "mwe_label": "15 MWe (up to 45 MWt)",
        "coolant": "Gas-cooled (HTGR)",
        "fuel": None,
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": None,
        "grid_required": None,
        "band": "review",
        "band_basis": "NRC accepted the KRONOS construction-permit application for "
                      "the University of Illinois site.",
        "ticker": "Nasdaq: NNE",
        "funding_usd": None,
        "funding_note": None,
        "commercial": "Strategic MOU with Super Micro Computer (May 2026) for a "
                      "standardised pre-integrated power-plus-compute product.",
        "anpi_site": None,
        "sources": [
            {"label": "UIUC NPRE — NRC accepts the KRONOS construction-permit application",
             "url": "https://npre.illinois.edu/news/stories/imdp-cpa"},
            {"label": "smrintel — nuclear data-center deals tracker",
             "url": "https://smrintel.com/nuclear-data-center-deals/"},
        ],
        "gaps": ["Supermicro relationship is an MOU — no binding capacity, site, or date"],
    },
    {
        "id": "valar",
        "name": "Valar Atomics",
        "design": "Ward 250",
        "mwe_low": 5.0, "mwe_high": 5.0, "mwt": None,
        "mwe_label": "5 MWe commercial target (Utah test unit ran at 100 kWt)",
        "coolant": None,
        "fuel": None,
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": None,
        "grid_required": None,
        "band": "doe-authorized",
        "band_basis": "Reached DOE-authorized criticality in Emery County, Utah on "
                      "2026-06-18 — the only pilot reactor built outside a national "
                      "laboratory.",
        "ticker": None,
        "funding_usd": None,
        "funding_note": None,
        "commercial": None,
        "anpi_site": None,
        "sources": [
            {"label": "DOE — second advanced reactor achieving criticality",
             "url": "https://www.energy.gov/articles/department-energy-celebrates-second-advanced-reactor-achieving-criticality"},
        ],
        "gaps": ["The 5 MWe figure is a commercial scale-up target, not a demonstrated rating"],
    },
    {
        "id": "deployable-energy",
        "name": "Deployable Energy",
        "design": "Unity",
        "mwe_low": 1.0, "mwe_high": 1.0, "mwt": None,
        "mwe_label": "1 MWe",
        "coolant": None,
        "fuel": None,
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": None,
        "grid_required": None,
        "band": "doe-authorized",
        "band_basis": "Unity reached DOE-authorized criticality at the National Reactor "
                      "Innovation Center, INL on 2026-07-01 — about 150 days from kickoff.",
        "ticker": None,
        "funding_usd": None,
        "funding_note": None,
        "commercial": None,
        "anpi_site": None,
        "sources": [
            {"label": "DOE — third advanced reactor delivered",
             "url": "https://www.energy.gov/articles/us-department-energy-meets-president-trumps-goal-delivers-third-advanced-reactor"},
        ],
        "gaps": ["No named commercial site or offtaker on record"],
    },
    {
        "id": "terrestrial",
        "name": "Terrestrial Energy",
        "design": "IMSR (TETRA-1 pilot)",
        "mwe_low": None, "mwe_high": None, "mwt": None,
        "mwe_label": "TETRA-1 pilot output not disclosed (commercial IMSR is 195 MWe/core)",
        "coolant": "Molten salt",
        "fuel": None,
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": None,
        "grid_required": None,
        "band": "contracted",
        "band_basis": "Secured ~77 acres at the Texas A&M-RELLIS campus for a pilot, "
                      "to generate the site data an NRC construction-permit application "
                      "requires. Selected for the DOE Reactor Pilot Program.",
        "ticker": "Nasdaq: IMSR",
        "funding_usd": None,
        "funding_note": None,
        "commercial": None,
        "anpi_site": None,
        "sources": [
            {"label": "ANS — Terrestrial Energy and Texas A&M reach siting agreement",
             "url": "https://www.ans.org/news/2026-06-23/article-8139/terrestrial-energy-and-texas-am-reach-agreement-on-reactor-siting/"},
        ],
        "gaps": ["Commercial IMSR is SMR-scale (195 MWe/core) — only the TETRA-1 pilot "
                 "sits in the microreactor band, and its output is undisclosed"],
    },
    {
        "id": "oklo",
        "name": "Oklo",
        "design": "Aurora",
        "mwe_low": 15.0, "mwe_high": 75.0, "mwt": None,
        "mwe_label": "up to 75 MWe — above the ≤20 MWe microreactor band",
        "coolant": "Liquid-metal fast reactor",
        "fuel": "HALEU",
        "refuel_years": None,
        "service_life_years": None,
        "mass_tonnes": None,
        "footprint_acres": None,
        "transport": None,
        "grid_required": None,
        "band": "doe-authorized",
        "band_basis": "Aurora-INL under construction under the DOE Reactor Pilot "
                      "Program with a combined-license application submitted to the NRC. "
                      "Groves reached first criticality on private land 2026-08-06.",
        "ticker": "NYSE: OKLO",
        "funding_usd": None,
        "funding_note": None,
        "commercial": "Eielson AFB (Fairbanks, AK) design/build/own/operate award.",
        "anpi_site": None,
        "adjacent": True,
        "adjacent_note": "Listed as an ADJACENCY, not a microreactor vendor. The Aurora "
                         "design scaled from 15 MWe through 50 MWe to a current 75 MWe "
                         "maximum, so it sits above the microreactor band — but Oklo holds "
                         "the Eielson award, which is the highest-value remote-base "
                         "opportunity in this pipeline.",
        "sources": [
            {"label": "Oklo — breaks ground on first Aurora powerhouse",
             "url": "https://oklo.com/newsroom/news-details/2025/Oklo-Breaks-Ground-on-First-Aurora-Powerhouse/default.aspx"},
            {"label": "Oklo — Groves reactor achieves first criticality",
             "url": "https://oklo.com/newsroom/news-details/2026/Oklos-Groves-Reactor-Achieves-First-Criticality-in-Under-a-Year/default.aspx"},
        ],
        "gaps": ["Primary Eielson award document not re-verified — carried forward from "
                 "the Microreactor Opportunity Map, not freshly sourced"],
    },
]

# ---------------------------------------------------------------------------
# COMMITMENTS — named pairings of a buyer, a programme, or a site to reactor
# capacity. `ap1000_site_id` joins coordinates from ap1000-sites.json so the
# Janus installations can never drift from the Nuclear Siting tab.
#
# `microreactor: False` marks SMR-scale rows kept as market comparators — they
# are excluded from every microreactor headline count.
# ---------------------------------------------------------------------------
COMMITMENTS = [
    # --- Air Force / Space Force ANPI: vendor paired to a named base ---------
    {
        "id": "anpi-jbsa", "track": "us-gov", "band": "contracted",
        "name": "Joint Base San Antonio (ANPI)",
        "owner": "U.S. Department of the Air Force",
        "sector": "Defense — installation power",
        "vendor_id": "antares", "vendor_name": "Antares Nuclear (R1)",
        "location": "San Antonio, TX", "state": "TX",
        "lat": 29.3842, "lon": -98.5811,
        "power_label": "0.1–1 MWe class", "mwe": 1.0,
        "timeline": "Deployment targeted 2028 or earlier; ANPI goal ≥1 reactor operating by 2030",
        "instrument": "ANPI selection (DAF + Defense Innovation Unit), contractor-owned/contractor-operated",
        "status": "Selected",
        "microreactor": True,
        "sources": [
            {"label": "Businesswire 2026-04-22",
             "url": "https://www.businesswire.com/news/home/20260422886007/en/Antares-Selected-for-Proposed-Deployment-of-Nuclear-Microreactor-at-Joint-Base-San-Antonio-Under-Department-of-the-Air-Force-ANPI-Initiative"},
            {"label": "Breaking Defense",
             "url": "https://breakingdefense.com/2026/04/department-of-air-force-picks-bidders-for-nuclear-microreactors-assigns-locations/"},
        ],
        "gaps": ["Land parcel not identified",
                 "No CPS Energy interconnection filing located — JBSA sits in CPS Energy "
                 "territory, a municipally owned utility, so any filing may be city-level "
                 "rather than PUC"],
    },
    {
        "id": "anpi-buckley", "track": "us-gov", "band": "contracted",
        "name": "Buckley Space Force Base (ANPI)",
        "owner": "U.S. Space Force / Dept of the Air Force",
        "sector": "Defense — installation power",
        "vendor_id": "radiant", "vendor_name": "Radiant Nuclear (Kaleidos)",
        "location": "Aurora, CO", "state": "CO",
        "lat": 39.7017, "lon": -104.7519,
        "power_label": "1 MWe (3 MWt)", "mwe": 1.0,
        "timeline": "ANPI goal ≥1 reactor operating by 2030; Radiant FOAK to a USAF base in 2028",
        "instrument": "ANPI selection (DAF + DIU)",
        "status": "Selected",
        "microreactor": True,
        "sources": [
            {"label": "ANS — Air Force selects three ANPI developers",
             "url": "https://www.ans.org/news/2026-04-23/article-7972/air-force-selects-three-microreactor-developers-for-anpi/"},
        ],
        "gaps": ["Land parcel not identified",
                 "No Xcel Energy Colorado interconnection filing located"],
    },
    {
        "id": "anpi-malmstrom", "track": "us-gov", "band": "contracted",
        "name": "Malmstrom Air Force Base (ANPI)",
        "owner": "U.S. Department of the Air Force",
        "sector": "Defense — installation power",
        "vendor_id": "evinci", "vendor_name": "Westinghouse (eVinci)",
        "location": "Great Falls, MT", "state": "MT",
        "lat": 47.5044, "lon": -111.1872,
        "power_label": "up to 5 MWe", "mwe": 5.0,
        "timeline": "ANPI goal ≥1 reactor operating by 2030",
        "instrument": "ANPI selection (DAF + DIU)",
        "status": "Selected",
        "microreactor": True,
        "sources": [
            {"label": "Exchange Monitor — Air Force picks three companies",
             "url": "https://www.exchangemonitor.com/air-force-picks-three-companies-to-deploy-microreactors-at-military-bases/?printmode=1"},
        ],
        "gaps": ["The vendor's 2-acre figure is a design claim, not a Malmstrom site allocation",
                 "No NorthWestern Energy filing located"],
    },
    # --- Army Janus: nine candidate installations, no vendor assigned --------
    # Coordinates joined from ap1000-sites.json via `ap1000_site_id`.
    *[
        {
            "id": f"janus-{sid}", "track": "us-gov", "band": "framework",
            "name": f"{label} (Army Janus)",
            "owner": "U.S. Department of the Army",
            "sector": "Defense — installation power",
            "vendor_id": None,
            "vendor_name": "Not yet assigned — vendor evaluation and design-to-site matching underway via DIU",
            "location": place, "state": st,
            "ap1000_site_id": sid,
            "lat": None, "lon": None,
            "power_label": "Not specified per site", "mwe": None,
            "timeline": "Army-regulated reactor operational at a domestic installation "
                        "by 2028-09-30; sites announced November 2025",
            "instrument": "Army program + DIU solicitation",
            "status": "Site identified, vendor not selected",
            "microreactor": True,
            "janus": True,
            "sources": [
                {"label": "army.mil — Janus next steps",
                 "url": "https://www.army.mil/article/289074/army_announces_next_steps_on_janus_program_for_next_generation_nuclear_energy"},
                {"label": "ANS — Army chooses nine sites",
                 "url": "https://www.ans.org/news/article-7567/us-army-chooses-nine-sites-for-possible-microreactor-by-2030/"},
            ],
            "gaps": gaps,
        }
        for sid, label, place, st, gaps in [
            ("fort-benning-ga", "Fort Benning (Fort Moore)", "Columbus, GA", "GA",
             ["Per-site load requirement not published"]),
            ("fort-bragg-nc", "Fort Bragg (Fort Liberty)", "Fayetteville, NC", "NC",
             ["Per-site load requirement not published"]),
            ("fort-campbell-ky", "Fort Campbell", "Fort Campbell, KY/TN", "KY",
             ["Per-site load requirement not published"]),
            ("fort-drum-ny", "Fort Drum", "Watertown, NY", "NY",
             ["Per-site load requirement not published"]),
            ("fort-hood-tx", "Fort Hood (Fort Cavazos)", "Killeen, TX", "TX",
             ["Per-site load requirement not published"]),
            ("fort-wainwright-ak", "Fort Wainwright", "Fairbanks, AK", "AK",
             ["No site-specific MW figure located — yet this is the highest-value row "
              "in the set: the one installation whose displaced alternative is coal/oil "
              "at Alaskan prices"]),
            ("holston-aap-tn", "Holston Army Ammunition Plant", "Kingsport, TN", "TN",
             ["Per-site load requirement not published"]),
            ("jblm-wa", "Joint Base Lewis-McChord", "Tacoma, WA", "WA",
             ["Per-site load requirement not published"]),
            ("redstone-arsenal-al", "Redstone Arsenal", "Huntsville, AL", "AL",
             ["Per-site load requirement not published"]),
        ]
    ],
    # --- DOE test infrastructure + Reactor Pilot Program ---------------------
    {
        "id": "dome-inl", "track": "us-gov", "band": "doe-authorized",
        "name": "DOE DOME test bed, Idaho National Laboratory",
        "owner": "U.S. Department of Energy / Battelle Energy Alliance",
        "sector": "Federal R&D — test infrastructure",
        "vendor_id": "radiant",
        "vendor_name": "Radiant (first), Westinghouse eVinci, Ultra Safe Nuclear (FEEED)",
        "location": "Idaho National Laboratory, ID", "state": "ID",
        "lat": 43.5210, "lon": -112.9490,
        "power_label": "Houses fuelled experiments up to 20 MWt", "mwe": None,
        "timeline": "First fuelled experiment from spring 2026; Radiant fuel received "
                    "2026-07-01; campaign targeted to complete Q3 2026",
        "instrument": "DOE National Reactor Innovation Center test-bed access",
        "status": "Operating",
        "microreactor": True,
        "sources": [
            {"label": "DOE — first microreactor experiments in DOME",
             "url": "https://www.energy.gov/ne/articles/energy-department-announces-first-microreactor-experiments-dome-test-bed"},
            {"label": "WNN — test bed open for business",
             "url": "https://www.world-nuclear-news.org/articles/first-of-a-kind-microreactor-test-bed-open-for-business"},
        ],
        "gaps": [],
    },
    {
        "id": "pele-inl", "track": "us-gov", "band": "doe-authorized",
        "name": "Project Pele — transportable microreactor",
        "owner": "U.S. Department of Defense (Strategic Capabilities Office)",
        "sector": "Defense — expeditionary power",
        "vendor_id": "bwxt", "vendor_name": "BWXT",
        "location": "Idaho National Laboratory, ID", "state": "ID",
        "lat": 43.5210, "lon": -112.9490,
        "power_label": "1–5 MWe", "mwe": 1.5,
        "timeline": "Under construction at INL",
        "instrument": "DoD prime contract",
        "status": "Physical deployment",
        "microreactor": True,
        "sources": [
            {"label": "DOE — DoD breaks ground on Project Pele",
             "url": "https://www.energy.gov/ne/articles/department-defense-breaks-ground-project-pele-microreactor"},
        ],
        "gaps": [],
    },
    {
        "id": "antares-mark0-inl", "track": "us-gov", "band": "doe-authorized",
        "name": "Antares Mark-0 — first pilot criticality",
        "owner": "U.S. Army / U.S. Department of Energy",
        "sector": "Federal R&D — pilot reactor",
        "vendor_id": "antares", "vendor_name": "Antares Nuclear",
        "location": "Idaho National Laboratory, ID", "state": "ID",
        "lat": 43.5210, "lon": -112.9490,
        "power_label": "Zero-power demonstrator — contributes 0 MWe", "mwe": None,
        "timeline": "Criticality 2026-06-04",
        "instrument": "DOE Reactor Pilot Program authorization",
        "status": "Critical",
        "microreactor": True,
        "sources": [
            {"label": "army.mil — Antares zero-power criticality test",
             "url": "https://www.army.mil/article/293057/antares_nuclears_successful_zero_power_criticality_test_marks_major_step_for_military_applications_of_advanced_microreactors"},
        ],
        "gaps": [],
    },
    {
        "id": "valar-ward250-ut", "track": "us-gov", "band": "doe-authorized",
        "name": "Valar Ward 250 — first pilot reactor off a national lab",
        "owner": "Valar Atomics / U.S. Department of Energy",
        "sector": "Federal R&D — pilot reactor",
        "vendor_id": "valar", "vendor_name": "Valar Atomics",
        "location": "Emery County, UT", "state": "UT",
        "lat": 39.0330, "lon": -111.0480,
        "power_label": "Ran at 100 kWt — contributes 0 MWe", "mwe": None,
        "timeline": "Criticality 2026-06-18",
        "instrument": "DOE Reactor Pilot Program authorization",
        "status": "Critical",
        "microreactor": True,
        "sources": [
            {"label": "DOE — second advanced reactor achieving criticality",
             "url": "https://www.energy.gov/articles/department-energy-celebrates-second-advanced-reactor-achieving-criticality"},
        ],
        "gaps": [],
    },
    {
        "id": "deployable-unity-inl", "track": "us-gov", "band": "doe-authorized",
        "name": "Deployable Energy Unity — third pilot criticality",
        "owner": "Deployable Energy / National Reactor Innovation Center",
        "sector": "Federal R&D — pilot reactor",
        "vendor_id": "deployable-energy", "vendor_name": "Deployable Energy",
        "location": "Idaho National Laboratory, ID", "state": "ID",
        "lat": 43.5210, "lon": -112.9490,
        "power_label": "Demonstration reactor — contributes 0 MWe", "mwe": None,
        "timeline": "Criticality 2026-07-01, ~150 days from kickoff",
        "instrument": "DOE Reactor Pilot Program authorization",
        "status": "Critical",
        "microreactor": True,
        "sources": [
            {"label": "DOE — third advanced reactor delivered",
             "url": "https://www.energy.gov/articles/us-department-energy-meets-president-trumps-goal-delivers-third-advanced-reactor"},
        ],
        "gaps": [],
    },
    {
        "id": "aalo-ctr-inl", "track": "us-gov", "band": "doe-authorized",
        "name": "Aalo Critical Test Reactor — fourth pilot criticality",
        "owner": "Aalo Atomics / U.S. Department of Energy",
        "sector": "Federal R&D — pilot reactor",
        "vendor_id": "aalo", "vendor_name": "Aalo Atomics",
        "location": "Idaho National Laboratory, ID", "state": "ID",
        "lat": 43.5210, "lon": -112.9490,
        "power_label": "Zero-power test reactor — contributes 0 MWe", "mwe": None,
        "timeline": "Criticality 2026-07-04 — first new reactor built at INL in 50 years",
        "instrument": "DOE Reactor Pilot Program authorization",
        "status": "Critical",
        "microreactor": True,
        "sources": [
            {"label": "DOE — fourth criticality ahead of the July 4 goal",
             "url": "https://www.energy.gov/articles/department-energy-celebrates-fourth-criticality-ahead-july-4th-goal"},
        ],
        "gaps": [],
    },
    {
        "id": "deep-fission-parsons-ks", "track": "us-gov", "band": "doe-authorized",
        "name": "Deep Fission borehole pilot — Parsons, Kansas",
        "owner": "Deep Fission / U.S. Department of Energy",
        "sector": "Federal R&D — pilot reactor",
        "vendor_id": "deep-fission", "vendor_name": "Deep Fission",
        "location": "Parsons, KS", "state": "KS",
        "lat": 37.3403, "lon": -95.2611,
        "power_label": "Not disclosed by DOE", "mwe": None,
        "timeline": "First data-acquisition well drilled",
        "instrument": "DOE Reactor Pilot Program selection",
        "status": "Development commitment",
        "microreactor": True,
        "sources": [
            {"label": "WNN — Deep Fission begins drilling first data-acquisition well",
             "url": "https://www.world-nuclear-news.org/articles/deep-fission-begins-drilling-first-data-acquisition-well"},
        ],
        "gaps": ["Output not disclosed by DOE"],
    },
    {
        "id": "last-energy-rellis-tx", "track": "us-gov", "band": "doe-authorized",
        "name": "Last Energy PWR-5 pilot — Texas A&M RELLIS",
        "owner": "Last Energy / Texas A&M University System",
        "sector": "Federal R&D — pilot reactor",
        "vendor_id": "last-energy", "vendor_name": "Last Energy",
        "location": "Texas A&M RELLIS Campus, Bryan, TX", "state": "TX",
        "lat": 30.6300, "lon": -96.4750,
        "power_label": "5 MWe pilot", "mwe": 5.0,
        "timeline": "Development commitment",
        "instrument": "DOE Reactor Pilot Program selection",
        "status": "Development commitment",
        "microreactor": True,
        "sources": [
            {"label": "WNN — Last Energy microreactor planned at Texas university",
             "url": "https://www.world-nuclear-news.org/articles/last-energy-microreactor-planned-at-texas-university"},
        ],
        "gaps": [],
    },
    {
        "id": "terrestrial-tetra1-rellis-tx", "track": "us-gov", "band": "contracted",
        "name": "Terrestrial TETRA-1 pilot — Texas A&M RELLIS",
        "owner": "Terrestrial Energy / Texas A&M University System",
        "sector": "Federal R&D — pilot reactor",
        "vendor_id": "terrestrial", "vendor_name": "Terrestrial Energy",
        "location": "Texas A&M RELLIS Campus, Bryan, TX", "state": "TX",
        "lat": 30.6300, "lon": -96.4750,
        "power_label": "Not disclosed by DOE", "mwe": None,
        "timeline": "~77 acres secured June 2026 to generate NRC construction-permit site data",
        "instrument": "Siting agreement + DOE Reactor Pilot Program selection",
        "status": "Development commitment",
        "microreactor": True,
        "sources": [
            {"label": "ANS — Terrestrial Energy and Texas A&M reach siting agreement",
             "url": "https://www.ans.org/news/2026-06-23/article-8139/terrestrial-energy-and-texas-am-reach-agreement-on-reactor-siting/"},
        ],
        "gaps": ["Output not disclosed by DOE"],
    },
    {
        "id": "uiuc-kronos-il", "track": "us-commercial", "band": "review",
        "name": "University of Illinois KRONOS MMR",
        "owner": "University of Illinois Urbana-Champaign",
        "sector": "Civic infrastructure — university campus",
        "vendor_id": "nano-nuclear", "vendor_name": "NANO Nuclear Energy",
        "location": "Champaign County, IL", "state": "IL",
        "lat": 40.1020, "lon": -88.2272,
        "power_label": "Non-power research reactor (KRONOS is rated 15 MWe / 45 MWt)",
        "mwe": None,
        "timeline": "Construction-permit application accepted by the NRC",
        "instrument": "NRC construction-permit application (research-reactor licensing)",
        "status": "Under NRC review",
        "microreactor": True,
        "sources": [
            {"label": "UIUC NPRE — NRC accepts the construction-permit application",
             "url": "https://npre.illinois.edu/news/stories/imdp-cpa"},
        ],
        "gaps": [],
    },
    {
        "id": "eielson-ak", "track": "us-gov", "band": "contracted",
        "name": "Eielson Air Force Base micro-reactor pilot",
        "owner": "U.S. Department of the Air Force",
        "sector": "Defense — remote installation power",
        "vendor_id": "oklo", "vendor_name": "Oklo (Aurora)",
        "location": "Fairbanks, AK", "state": "AK",
        "lat": 64.6656, "lon": -147.1017,
        "power_label": "Power and heat; the Aurora class sits above the microreactor band",
        "mwe": None,
        "timeline": "Oklo targets first commercial operation of Aurora-INL late 2027/2028",
        "instrument": "Design/build/own/operate award",
        "status": "Awarded",
        "microreactor": True,
        "sources": [
            {"label": "DOE — 3 microreactor experiments to watch from 2026",
             "url": "https://www.energy.gov/ne/articles/3-microreactor-experiments-watch-starting-2026"},
        ],
        "gaps": ["Primary Eielson award document not re-verified in this pass — "
                 "treat as carried-forward, not freshly sourced"],
    },
    # --- U.S. commercial ------------------------------------------------------
    {
        "id": "equinix-radiant", "track": "us-commercial", "band": "contracted",
        "name": "Equinix — 20-reactor purchase agreement",
        "owner": "Equinix, Inc. (NASDAQ: EQIX)",
        "sector": "Compute — colocation data centres",
        "vendor_id": "radiant", "vendor_name": "Radiant Nuclear (Kaleidos)",
        "location": "Not site-assigned", "state": None,
        "lat": None, "lon": None,
        "power_label": "20 × 1 MWe = 20 MWe committed", "mwe": 20.0,
        "timeline": "Not published",
        "instrument": "Purchase agreement / pre-order with deposits",
        "status": "Signed",
        "microreactor": True,
        "sources": [
            {"label": "Equinix investor release 2025-08-14",
             "url": "https://investor.equinix.com/news-events/press-releases/detail/1079/equinix-collaborates-with-leading-alternative-energy"},
        ],
        "gaps": ["No site list", "No delivery schedule", "No unit price"],
    },
    {
        "id": "nano-supermicro", "track": "us-commercial", "band": "framework",
        "name": "NANO Nuclear × Supermicro",
        "owner": "NANO Nuclear Energy; Super Micro Computer, Inc.",
        "sector": "Compute — integrated power+compute",
        "vendor_id": "nano-nuclear", "vendor_name": "NANO Nuclear Energy",
        "location": "Not site-assigned", "state": None,
        "lat": None, "lon": None,
        "power_label": "Not specified", "mwe": None,
        "timeline": "MOU signed May 2026",
        "instrument": "Strategic MOU — standardised microreactor power solution for "
                      "data centres, pre-integrated power-plus-compute",
        "status": "MOU",
        "microreactor": True,
        "sources": [
            {"label": "smrintel — nuclear data-center deals tracker",
             "url": "https://smrintel.com/nuclear-data-center-deals/"},
        ],
        "gaps": ["MOU only — no binding capacity, no site, no date"],
    },
    {
        "id": "ianc", "track": "us-commercial", "band": "framework",
        "name": "Industrial Advanced Nuclear Consortium (IANC)",
        "owner": "ExxonMobil, Shell, Chevron, ConocoPhillips, Rio Tinto, "
                 "Freeport-McMoRan, Nucor",
        "sector": "Heavy industry — oil & gas, mining, steel",
        "vendor_id": None,
        "vendor_name": "Technology-neutral; explicitly covers SMRs and MMRs",
        "location": "Multi-site, not assigned", "state": None,
        "lat": None, "lon": None,
        "power_label": "Use cases span remote well pads, offshore platforms, "
                       "refinery/LNG heat, mining",
        "mwe": None,
        "timeline": "ExxonMobil stated goal: make nuclear a viable option for "
                    "industrial projects by 2030",
        "instrument": "Demand-aggregation consortium, launched 2025-09-02 by The Open Group",
        "status": "Consortium formed; no procurement",
        "microreactor": True,
        "sources": [
            {"label": "The Open Group — Industrial Advanced Nuclear Consortium",
             "url": "https://www.opengroup.org/industrial-advanced-nuclear-consortium"},
        ],
        "gaps": ["No member has issued a microreactor RFP",
                 "Counter-signal: a MINING.COM analysis reports <10% of miners actively "
                 "considering SMRs vs >70% favouring wind/solar — press-reported only"],
    },
    {
        "id": "penn-state-evinci", "track": "us-commercial", "band": "framework",
        "name": "Penn State — eVinci letter of intent",
        "owner": "The Pennsylvania State University",
        "sector": "Civic infrastructure — university campus",
        "vendor_id": "evinci", "vendor_name": "Westinghouse (eVinci)",
        "location": "State College, PA", "state": "PA",
        "lat": 40.7982, "lon": -77.8599,
        "power_label": "up to 5 MWe", "mwe": 5.0,
        "timeline": "Letter of intent filed with the NRC 2026-02-28",
        "instrument": "Letter of intent to host and operate",
        "status": "Letter of intent",
        "microreactor": True,
        "sources": [
            {"label": "POWER — Westinghouse secures first eVinci customer",
             "url": "https://www.powermag.com/westinghouse-secures-first-customer-for-evinci-nuclear-microreactor/"},
        ],
        "gaps": ["LOI only — no construction-permit application docketed"],
    },
    {
        "id": "texas-backup", "track": "us-commercial", "band": "framework",
        "name": "Texas Backup Power Package Program",
        "owner": "State of Texas / Texas Energy Fund",
        "sector": "Civic infrastructure — resilience procurement",
        "vendor_id": None, "vendor_name": "None — currently solar, battery and gas",
        "location": "Texas", "state": "TX",
        "lat": None, "lon": None,
        "power_label": "Site-scale backup at hospitals, water treatment, nursing homes, "
                       "police/fire",
        "mwe": None,
        "timeline": "Announced 2025-06-11",
        "instrument": "$1.8B state funding programme",
        "status": "Live programme, nuclear not yet eligible",
        "microreactor": True,
        "sources": [
            {"label": "Carried from the Microreactor Opportunity Map §3 "
                      "(University of Houston Energy Innovation)",
             "url": "https://uh.edu/energy/"},
        ],
        "gaps": ["Nuclear is not named as an eligible technology — this is a "
                 "substitution opportunity into live procurement, not an existing "
                 "nuclear pipeline"],
    },
    # --- International ------------------------------------------------------
    {
        "id": "uk-lastenergy", "track": "intl", "band": "review",
        "name": "DP World Thames Freeport — Last Energy PWR-20",
        "owner": "DP World (freeport operator); Last Energy (developer)",
        "sector": "Ports & logistics",
        "vendor_id": "last-energy", "vendor_name": "Last Energy (PWR-20)",
        "location": "Thames Freeport, United Kingdom", "state": None,
        "lat": None, "lon": None,
        "power_label": "20 MWe", "mwe": 20.0,
        "timeline": "Preliminary Design Review completed with UK ONR July 2025; "
                    "target online 2030",
        "instrument": "Named commercial customer; UK regulatory review underway",
        "status": "In regulatory review",
        "microreactor": True,
        "sources": [
            {"label": "Carried from the Microreactor Opportunity Map §6 (UK ONR)",
             "url": "https://www.onr.org.uk/"},
        ],
        "gaps": ["Proof a commercial port operator will sign for microreactor power — "
                 "not itself an opening for the ANPI vendor slate"],
    },
    {
        "id": "canada-src", "track": "intl", "band": "contracted",
        "name": "Saskatchewan Research Council eVinci pilot",
        "owner": "Saskatchewan Research Council (Crown corporation)",
        "sector": "Government research council",
        "vendor_id": "evinci", "vendor_name": "Westinghouse (eVinci)",
        "location": "Saskatchewan, Canada", "state": None,
        "lat": None, "lon": None,
        "power_label": "up to 5 MWe", "mwe": 5.0,
        "timeline": "Pilot by 2029, subject to licensing",
        "instrument": "First eVinci customer; SRC is the licensed operator; "
                      "CA$80M government funding",
        "status": "Funded",
        "microreactor": True,
        "sources": [
            {"label": "POWER — Westinghouse secures first eVinci customer",
             "url": "https://www.powermag.com/westinghouse-secures-first-customer-for-evinci-nuclear-microreactor/"},
        ],
        "gaps": ["CNSC licensing milestones not tracked here"],
    },
    {
        "id": "jp-kr-moc", "track": "intl", "band": "framework",
        "name": "U.S.–Japan–Korea trilateral SMR Memorandum of Cooperation",
        "owner": "U.S. Dept of State; Japan MOFA; ROK MOFA",
        "sector": "Government-to-government export channel",
        "vendor_id": None, "vendor_name": "Channel, not vendor-specific",
        "location": "Third countries, Indo-Pacific first", "state": None,
        "lat": None, "lon": None,
        "power_label": "N/A", "mwe": None,
        "timeline": "Signed 2026-07-07",
        "instrument": "Trilateral MOC — U.S. reactor design, Japan heavy manufacturing, "
                      "Korea construction/supply chain",
        "status": "Signed",
        "microreactor": True,
        "sources": [
            {"label": "Carried from the Microreactor Opportunity Map §6 — state.gov "
                      "release, press-corroborated (UPI, Korea Times)",
             "url": "https://www.state.gov/"},
        ],
        "gaps": ["Primary state.gov page not independently read — press-corroborated only"],
    },
    {
        "id": "romania-nuscale", "track": "intl", "band": "contracted",
        "name": "Doicești NuScale VOYGR-6",
        "owner": "Nuclearelectrica / RoPower",
        "sector": "Electric utility — SMR (scale comparator)",
        "vendor_id": None, "vendor_name": "NuScale",
        "location": "Doicești, Romania", "state": None,
        "lat": None, "lon": None,
        "power_label": "6 modules — SMR scale, not microreactor", "mwe": None,
        "timeline": "Final Investment Decision approved February 2026",
        "instrument": "FID — the most construction-advanced U.S.-linked SMR export relationship",
        "status": "FID approved",
        "microreactor": False,
        "sources": [
            {"label": "Carried from the Microreactor Opportunity Map §6 (Neutron Bytes 2026-02-13)",
             "url": "https://neutronbytes.com/"},
        ],
        "gaps": ["SMR scale — included as proof the U.S. export machinery reaches funded "
                 "construction, not as a microreactor lead"],
    },
]

# ---------------------------------------------------------------------------
# SECTOR DEMAND LADDER — annual-average electrical demand planning bands,
# carried from the Microreactor Opportunity Map's data/sectors.json.
# `fit` marks whether a 1–20 MWe block covers the whole load ("full") or only
# a dedicated block inside a larger campus ("block").
#
# Caveat carried with the data: these are PLANNING bands, not guaranteed
# averages; final sizing needs at least one year of hourly site-load data.
# ---------------------------------------------------------------------------
MICRO_BAND_MWE = 20.0

SECTOR_LOADS = [
    ("Compute", [
        ("Regional data centers", 1, 10),
        ("Company-owned data centers", 1, 5),
        ("Shared data centers", 5, 50),
        ("Supercomputing centers", 10, 50),
        ("AI and very large cloud data centers", 50, 500),
        ("Dedicated baseload / outage-protection blocks in larger DC campuses", 1, 20),
    ]),
    ("Mining", [
        ("Large pozzolan mines with onsite crushing, grinding or drying", 1, 5),
        ("Remote lithium and rare-earth mines with onsite processing", 5, 20),
        ("Remote copper and other large mines", 12, 25),
    ]),
    ("Electric utilities", [
        ("Individual remote grids with sufficient year-round demand", 1, 10),
        ("Regional grids serving several communities", 5, 20),
        ("Replacements for older diesel and coal generation", 1, 20),
        ("Power for new mines, factories, DCs and communities before grid upgrades", 1, 20),
        ("Staged additions for future load growth", 1, 20),
    ]),
    ("Manufacturing", [
        ("Steel rolling and finishing plants (excl. full steelmaking mills)", 5, 20),
        ("Cement plants", 7, 25),
        ("Lime plants", 2, 8),
        ("Chemical plants", 5, 50),
        ("Fertilizer plants", 5, 30),
        ("Hydrogen and low-carbon fuel plants", 5, 20),
        ("Pulp and paper mills", 10, 40),
        ("Large integrated sawmills and wood-products plants", 1, 8),
        ("Semiconductor fabs", 30, 150),
        ("Battery-cell plants", 20, 100),
        ("Battery-material plants", 5, 30),
        ("Battery-recycling plants", 2, 15),
    ]),
    ("Oil & gas", [
        ("Remote oil fields and production hubs", 5, 20),
        ("Offshore platforms", 10, 50),
        ("Pipeline pumping and electric compression stations", 5, 20),
        ("Gas-processing plants", 5, 20),
        ("Smaller LNG plants and receiving terminals", 5, 20),
        ("Smaller refineries", 5, 20),
        ("Dedicated electrical blocks at larger refineries", 5, 20),
    ]),
    ("Transportation", [
        ("Large fulfillment and distribution centers", 1, 10),
        ("Refrigerated distribution centers", 1, 5),
        ("Cargo-port electrical systems incl. ship plug-in power", 5, 20),
        ("Major passenger airports", 10, 30),
        ("Major air-cargo campuses", 3, 15),
        ("Large rail, truck and fleet-charging hubs", 1, 10),
    ]),
    ("Civic infrastructure", [
        ("Large individual hospitals", 2, 8),
        ("Major medical campuses", 10, 40),
        ("Large prison complexes", 1, 3),
        ("Major universities", 5, 30),
        ("National laboratories", 10, 50),
        ("Large campus electrical systems", 5, 30),
        ("Regional drinking-water treatment and pumping systems", 1, 10),
        ("Major city wastewater plants", 1, 15),
        ("Large seawater desalination plants", 5, 20),
    ]),
    ("Agriculture & food", [
        ("Large lighted greenhouse campuses", 1, 8),
        ("Large indoor-growing facilities", 1, 10),
        ("Large land-based aquaculture operations", 1, 5),
        ("Remote seafood-processing plants on a year-round community grid", 1, 5),
        ("Very large meat, dairy and frozen-food plants", 2, 15),
        ("Large grain and oilseed mills", 5, 20),
        ("Integrated agricultural campuses", 2, 20),
    ]),
]


def _band_label(lo: float, hi: float) -> str:
    lo_s = f"{lo:g}"
    hi_s = f"{hi:g}"
    return f"{lo_s}–{hi_s} MW"


def build_sectors() -> list[dict]:
    """Expand SECTOR_LOADS into the emitted shape, computing `fit` per load."""
    out = []
    for sector, loads in SECTOR_LOADS:
        rows = []
        for label, lo, hi in loads:
            # "full" — a single ≤20 MWe unit covers the whole annual-average
            # load. "block" — the load exceeds the microreactor band, so a unit
            # serves a dedicated slice of a larger campus.
            rows.append({
                "label": label,
                "mw_low": lo,
                "mw_high": hi,
                "band": _band_label(lo, hi),
                "fit": "full" if hi <= MICRO_BAND_MWE else "block",
            })
        out.append({"sector": sector, "loads": rows})
    return out


def join_ap1000_coords(commitments: list[dict]) -> tuple[list[dict], int]:
    """Fill lat/lon on Janus rows from ap1000-sites.json.

    Fails loud on a missing installation: a silently-unmapped Janus site would
    just vanish from the overlay with no error, which is exactly the class of
    drift this join exists to prevent.
    """
    if not AP1000_PATH.exists():
        raise FileNotFoundError(
            f"{AP1000_PATH} not found — run scripts/build_ap1000_sites.py first; "
            "the Janus installations take their coordinates from it."
        )
    by_id = {s["id"]: s for s in json.loads(AP1000_PATH.read_text())["sites"]}
    joined = 0
    for c in commitments:
        sid = c.pop("ap1000_site_id", None)
        if not sid:
            continue
        src = by_id.get(sid)
        if src is None:
            raise KeyError(
                f"Janus commitment {c['id']!r} references ap1000 site {sid!r}, "
                "which is not in ap1000-sites.json."
            )
        c["lat"] = src["lat"]
        c["lon"] = src["lon"]
        c["ap1000_ref"] = sid
        joined += 1
    return commitments, joined


def validate(vendors: list[dict], commitments: list[dict]) -> None:
    """Structural asserts — the same drift-safe discipline as the AP1000 build."""
    vendor_ids = {v["id"] for v in vendors}
    assert len(vendor_ids) == len(vendors), "duplicate vendor id"

    commit_ids = {c["id"] for c in commitments}
    assert len(commit_ids) == len(commitments), "duplicate commitment id"

    for v in vendors:
        assert v["band"] in BAND_IDS, f"{v['id']}: unknown band {v['band']!r}"
        assert v["sources"], f"{v['id']}: a vendor with no source must not be written"

    for c in commitments:
        assert c["band"] in BAND_IDS, f"{c['id']}: unknown band {c['band']!r}"
        assert c["sources"], f"{c['id']}: a commitment with no source must not be written"
        vid = c.get("vendor_id")
        assert vid is None or vid in vendor_ids, f"{c['id']}: unknown vendor_id {vid!r}"
        # A mappable row needs BOTH coordinates or neither — one alone would
        # place a marker at the equator.
        assert (c["lat"] is None) == (c["lon"] is None), f"{c['id']}: half a coordinate"


def main() -> None:
    vendors = [dict(v) for v in VENDORS]
    commitments = [dict(c) for c in COMMITMENTS]
    commitments, janus_joined = join_ap1000_coords(commitments)
    validate(vendors, commitments)

    sectors = build_sectors()
    micro_commitments = [c for c in commitments if c.get("microreactor")]
    mapped = [c for c in commitments if c["lat"] is not None]

    # Committed MWe is summed ONLY within a band — never across bands. Summing
    # `framework` (MOU) capacity with `contracted` capacity is the exact error
    # Deployment Core's band rules exist to prevent.
    mwe_by_band = {}
    for c in micro_commitments:
        if c.get("mwe") is None:
            continue
        mwe_by_band[c["band"]] = round(mwe_by_band.get(c["band"], 0.0) + c["mwe"], 1)

    payload = {
        "generated_at": GENERATED_AT,
        "source": "Curated. Carried forward from two sibling research projects, each "
                  "of which cites primary sources per row.",
        "source_projects": [
            {
                "name": "Microreactor Opportunity Map",
                "contributes": "Vendor specs (coolant, fuel, refuel interval, transport, "
                               "footprint), the opportunity/commitment set, and the sector "
                               "demand ladder.",
                "method": "Web search only; every row carries at least one source URL.",
            },
            {
                "name": "Deployment Core",
                "contributes": "The six evidence bands, the Microreactor-lane company "
                               "roster with its roster basis, and the 2026 criticality "
                               "record.",
                "method": "Primary regulator and agency sources outrank company reporting; "
                          "a megawatt sits in exactly one band.",
            },
        ],
        "micro_band_mwe": MICRO_BAND_MWE,
        "evidence_bands": EVIDENCE_BANDS,
        "counts": {
            "vendors": len(vendors),
            "vendors_microreactor_band": sum(1 for v in vendors if not v.get("adjacent")),
            "commitments": len(commitments),
            "commitments_microreactor": len(micro_commitments),
            "commitments_mapped": len(mapped),
            "janus_sites": janus_joined,
            "sectors": len(sectors),
            "sector_loads": sum(len(s["loads"]) for s in sectors),
            "sector_loads_full_fit": sum(
                1 for s in sectors for l in s["loads"] if l["fit"] == "full"
            ),
        },
        "committed_mwe_by_band": mwe_by_band,
        "vendors": vendors,
        "commitments": commitments,
        "sectors": sectors,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"Wrote {OUT_PATH}")
    print(f"  vendors:      {len(vendors)} ({payload['counts']['vendors_microreactor_band']} in band, "
          f"{len(vendors) - payload['counts']['vendors_microreactor_band']} adjacent)")
    print(f"  commitments:  {len(commitments)} ({len(micro_commitments)} microreactor, "
          f"{len(mapped)} mappable, {janus_joined} Janus joined from ap1000-sites.json)")
    print(f"  sectors:      {len(sectors)} / {payload['counts']['sector_loads']} loads "
          f"({payload['counts']['sector_loads_full_fit']} fully served by a ≤{MICRO_BAND_MWE:g} MWe unit)")
    print("  committed MWe by band (never summed across bands):")
    for b in EVIDENCE_BANDS:
        if b["band"] in mwe_by_band:
            print(f"    {b['label']:24s} {mwe_by_band[b['band']]:>7.1f} MWe")


if __name__ == "__main__":
    main()
