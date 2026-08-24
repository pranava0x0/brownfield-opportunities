#!/usr/bin/env python3
"""Build docs/data/federal-clean-energy.json — the DOE "Cleanup to Clean
Energy" / AI-data-centers-on-federal-land / CEML mine-lands overlay (Spec 08,
docs/specs/spec-cleanup-to-clean-energy-and-mine-lands.md).

Provenance contract: every row carries a `solicitation_url` verified to
resolve (never a guessed slug — the v1 draft shipped two 404s) and a
`verified_at` audit stamp. Facts re-verified 2026-08-23 against the industry
sweep (research/industry-topical-2026-08.md §T6): Paducah's Brookfield /
NextEra award (Jul 2026), SRS's Amentum selection, Portsmouth's Mar-2026
announcement, and Lewis Ridge being Rye Development's 266 MW PUMPED-STORAGE
project (not solar). Coordinates are reservation reference points, not parcel
centroids. Re-audit quarterly — these programs move on political timelines.
"""
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema import FederalCleanEnergySite  # noqa: E402

log = logging.getLogger("build_federal_clean_energy_sites")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_PATH = ROOT / "docs" / "data" / "federal-clean-energy.json"

VERIFIED = "2026-08-23"
DOE_SITE_SELECTION_URL = "https://www.energy.gov/articles/doe-announces-site-selection-ai-data-center-and-energy-infrastructure-development-federal"
EM_LAND_REUSE_URL = "https://www.energy.gov/em/em-clean-energy-land-reuse"
CEML_URL = "https://www.energy.gov/oced/clean-energy-demonstration-program-current-and-former-mine-land"

FEDERAL_SITES_CATALOG: list[dict[str, Any]] = [
    {
        "site_id": "doe-em-srs",
        "site_name": "Savannah River Site (SRS)",
        "managing_office": "DOE-EM",
        "state": "SC", "county": "Aiken",
        "latitude": 33.2458, "longitude": -81.5642,
        "available_acreage": 198000.0,
        "target_technologies": ["datacenter_ai", "nuclear_smr", "gas_generation", "solar_utility", "battery_storage"],
        "program_stage": "RFQ_Awarded",
        "commercial_partner": "Amentum (selected to negotiate AI data center + on-site power lease, 2026)",
        "solicitation_url": DOE_SITE_SELECTION_URL,
        "nepa_review_document_url": None,
        "key_advantages": [
            "One of the four Jul-2025 DOE AI-data-center flagship selections",
            "Federal security perimeter and controlled buffer",
            "High-capacity 230/500 kV transmission ties (Southern Company / Dominion)",
            "Savannah River cooling-water corridor",
        ],
    },
    {
        "site_id": "doe-em-inl",
        "site_name": "Idaho National Laboratory (INL Site)",
        "managing_office": "DOE-EM",
        "state": "ID", "county": "Butte",
        "latitude": 43.5333, "longitude": -112.9500,
        "available_acreage": 570000.0,
        "offered_acreage": 44000.0,
        "target_technologies": ["nuclear_smr", "nuclear_micro", "datacenter_ai", "geothermal"],
        "program_stage": "RFI_Issued",
        "commercial_partner": None,
        "solicitation_url": DOE_SITE_SELECTION_URL,
        "nepa_review_document_url": None,
        "key_advantages": [
            "One of the four Jul-2025 DOE AI-data-center flagship selections; first-tranche RFP issued Sept 2025 (responses due Nov 2025)",
            "~44,000 ac identified for AI infrastructure within the 570,000-ac reservation",
            "National nuclear innovation & test reservation (DOME, Aalo, Oklo pilots)",
            "Extensive geotechnical, seismic, and meteorological baseline records",
            "Western Interconnection tie-lines",
        ],
    },
    {
        "site_id": "doe-em-hanford",
        "site_name": "Hanford Site Clean Energy Reservation",
        "managing_office": "DOE-EM",
        "state": "WA", "county": "Benton",
        "latitude": 46.5500, "longitude": -119.5000,
        "available_acreage": 8000.0,
        "target_technologies": ["solar_utility", "battery_storage", "nuclear_smr", "datacenter_ai"],
        "program_stage": "RFQ_Awarded",
        # 2026-08-24 re-verify: Hecate (selected from 11 RFQ respondents)
        # sold the up-to-2-GW "Cereza" project to Savion in Feb 2026; DOE's
        # first NEPA action (CX-034321, Aug 2025) covered the license
        # agreement + Phase I ESA. Stage stays RFQ_Awarded — no lease
        # execution has been announced.
        "commercial_partner": "Savion (acquired the up-to-2-GW 'Cereza' solar+storage project from Hecate Energy, Feb 2026)",
        "solicitation_url": "https://www.energy.gov/articles/doe-announces-cleanup-clean-energy-project-hanford-site",
        "nepa_review_document_url": "https://www.energy.gov/nepa/articles/cx-034321-hecate-energy-cereza-llc-license-agreement-and-categorical-exclusion",
        "verified_at": "2026-08-24",
        "key_advantages": [
            "Original 2023 Cleanup-to-Clean-Energy site (with INL, SRS, WIPP, NNSS)",
            "Columbia River high-volume cooling-water corridor",
            "BPA 500 kV transmission backbone proximity",
            "Adjacent to Energy Northwest / Columbia Generating Station nuclear infrastructure",
        ],
    },
    {
        "site_id": "doe-em-wipp",
        "site_name": "Waste Isolation Pilot Plant (WIPP Land Withdrawal)",
        "managing_office": "DOE-EM",
        "state": "NM", "county": "Eddy",
        "latitude": 32.3717, "longitude": -103.7917,
        "available_acreage": 10240.0,
        "target_technologies": ["solar_utility", "battery_storage", "nuclear_micro"],
        "program_stage": "RFI_Issued",
        "commercial_partner": None,
        "solicitation_url": EM_LAND_REUSE_URL,
        "nepa_review_document_url": None,
        "key_advantages": [
            "Original 2023 Cleanup-to-Clean-Energy site; 16-section federal land withdrawal",
            "Exceptional direct normal solar irradiance (Permian Basin)",
            "High industrial power demand in the surrounding Permian electrification corridor",
        ],
    },
    {
        "site_id": "doe-nnsa-nnss",
        "site_name": "Nevada National Security Site (NNSS)",
        "managing_office": "DOE-NNSA",
        "state": "NV", "county": "Nye",
        "latitude": 37.0000, "longitude": -116.0000,
        "available_acreage": 860000.0,
        "target_technologies": ["solar_utility", "battery_storage", "nuclear_micro", "datacenter_ai"],
        "program_stage": "RFI_Issued",
        "commercial_partner": None,
        "solicitation_url": EM_LAND_REUSE_URL,
        "nepa_review_document_url": None,
        "key_advantages": [
            "Original 2023 Cleanup-to-Clean-Energy site; NNSA-managed",
            "Massive contiguous federal buffer with zero civilian encroachment",
            "NV Energy grid and southwest transmission corridor proximity",
        ],
    },
    {
        "site_id": "doe-em-paducah",
        "site_name": "Paducah Gaseous Diffusion Plant",
        "managing_office": "DOE-EM",
        "state": "KY", "county": "McCracken",
        "latitude": 37.1167, "longitude": -88.8000,
        "available_acreage": 3500.0,
        "target_technologies": ["datacenter_ai", "gas_generation", "battery_storage", "nuclear_smr"],
        "program_stage": "RFQ_Awarded",
        "commercial_partner": "Brookfield Asset Management (developer/operator); NextEra Energy (2 GW new gas + transmission upgrades + up to 2.6 GW BESS)",
        "solicitation_url": "https://www.energy.gov/em/articles/us-energy-department-seeks-proposals-ai-data-centers-energy-projects-paducah-site",
        "nepa_review_document_url": None,
        "key_advantages": [
            "Jul-2026 award: 1.8-GW AI/HPC innovation campus — the furthest-along federal AI-DC site",
            "Legacy GW-scale switchyards (former enrichment-plant load)",
            "Ohio River water intake infrastructure and on-site heavy rail",
            "TVA transmission interconnects",
        ],
    },
    {
        "site_id": "doe-em-portsmouth",
        "site_name": "Portsmouth Gaseous Diffusion Plant (Piketon)",
        "managing_office": "DOE-EM",
        "state": "OH", "county": "Pike",
        "latitude": 39.0167, "longitude": -83.0000,
        "available_acreage": 3700.0,
        "target_technologies": ["nuclear_smr", "nuclear_micro", "datacenter_ai", "gas_generation", "solar_utility"],
        "program_stage": "Construction",
        "commercial_partner": "SoftBank Group / SB Energy (PORTS Technology Campus — 10 GW DC + ~9.2 GW gas, $33.3B; initial 800 MW phase, ops target 2028)",
        "solicitation_url": DOE_SITE_SELECTION_URL,
        "nepa_review_document_url": None,
        "key_advantages": [
            "Groundbreaking held 2026-03-20 for the PORTS Technology Campus — the largest announced US AI-DC project on federal land",
            "Massive 345 kV switchyards (enrichment cascade historically drew ~2 GW)",
            "Scioto River water access and licensed discharge",
            "Centrus commercial HALEU enrichment cascade adjacent",
        ],
    },
    {
        "site_id": "doe-em-oak-ridge",
        "site_name": "Oak Ridge Reservation (Heritage Center / ETTP)",
        "managing_office": "DOE-EM",
        "state": "TN", "county": "Roane",
        "latitude": 35.9333, "longitude": -84.3833,
        "available_acreage": 1200.0,
        "target_technologies": ["nuclear_smr", "datacenter_ai", "advanced_mfg"],
        "program_stage": "Lease_Executed",
        "commercial_partner": "Kairos Power (Hermes demonstration reactors, via CROET land transfer); TVA PPA",
        "solicitation_url": DOE_SITE_SELECTION_URL,
        "nepa_review_document_url": None,
        "key_advantages": [
            "One of the four Jul-2025 DOE AI-data-center flagship selections",
            "Kairos Hermes demonstration reactor under construction at ETTP",
            "TVA 161/500 kV grid and Clinch River cooling water",
            "Proximity to ORNL research and supercomputing",
        ],
    },
    {
        "site_id": "doe-oced-mineral-basin",
        "site_name": "Mineral Basin Solar Project (Clearfield County Mine Land)",
        "managing_office": "DOE-OCED",
        "state": "PA", "county": "Clearfield",
        "latitude": 41.0833, "longitude": -78.4167,
        "available_acreage": 2700.0,
        "target_technologies": ["solar_utility", "battery_storage"],
        "program_stage": "RFQ_Awarded",
        "commercial_partner": "Mineral Basin Solar Power LLC (Swift Current Energy subsidiary)",
        "solicitation_url": CEML_URL,
        "nepa_review_document_url": None,
        "key_advantages": [
            "402 MW utility-scale solar on ~2,700 ac of former surface coal-mine land — largest solar project in Pennsylvania",
            "CEML demonstration award (part of the $475M mine-lands program)",
            "PJM interconnection; IRA energy-community bonus-credit territory",
        ],
    },
    {
        "site_id": "doe-oced-lewis-ridge",
        "site_name": "Lewis Ridge Pumped Storage (Bell County Mine Land)",
        "managing_office": "DOE-OCED",
        "state": "KY", "county": "Bell",
        "latitude": 36.7500, "longitude": -83.6667,
        "available_acreage": 1500.0,
        "target_technologies": ["pumped_storage"],
        "program_stage": "RFQ_Awarded",
        "commercial_partner": "Lewis Ridge Pumped Storage LLC (Rye Development)",
        "solicitation_url": CEML_URL,
        "nepa_review_document_url": "https://www.federalregister.gov/documents/2026/05/12/2026-09425/lewis-ridge-pumped-storage-llc-notice-of-intent-to-prepare-an-environmental-impact-statement-for-the",
        "key_advantages": [
            "266 MW closed-loop PUMPED-STORAGE HYDRO (FERC Final License Application; earlier filings said 287 MW) — the first US pumped storage on former coal-mine land",
            "FERC final license application filed 2025; EIS Notice of Intent published in the Federal Register 2026-05-12",
            "CEML demonstration award (up to $81M DOE cost share)",
        ],
    },
]


def build_sites() -> list[dict[str, Any]]:
    """Validate every row against the Pydantic schema so a malformed row fails
    the build instead of shipping."""
    sites: list[dict[str, Any]] = []
    for raw in FEDERAL_SITES_CATALOG:
        row = dict(raw)
        row.setdefault("verified_at", VERIFIED)
        validated = FederalCleanEnergySite(**row)
        sites.append(json.loads(validated.model_dump_json(exclude_none=True)))
    return sites


def main() -> int:
    log.info("Building Federal Clean Energy Sites Catalog...")
    sites = build_sites()

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "DOE Cleanup to Clean Energy (EM) + AI-data-centers-on-federal-land selections + OCED CEML mine-lands awards; facts per research/industry-topical-2026-08.md. Coordinates are reservation reference points; available_acreage is the full reservation/withdrawal unless a row's key_advantages say otherwise.",
        "count": len(sites),
        "sites": sites,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %d federal clean energy sites -> %s", len(sites), OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
