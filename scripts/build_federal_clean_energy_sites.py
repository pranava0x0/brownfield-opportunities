import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

log = logging.getLogger("build_federal_clean_energy_sites")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_PATH = ROOT / "docs" / "data" / "federal-clean-energy.json"

FEDERAL_SITES_CATALOG: list[dict[str, Any]] = [
    {
        "site_id": "doe-em-srs",
        "site_name": "Savannah River Site (SRS)",
        "managing_office": "DOE-EM",
        "state": "SC",
        "county": "Aiken",
        "latitude": 33.2458,
        "longitude": -81.5642,
        "available_acreage": 310000.0,
        "target_technologies": ["datacenter_ai", "nuclear_smr", "solar_utility", "battery_storage"],
        "program_stage": "RFQ_Awarded",
        "commercial_partner": "Amentum / Battelle Savannah River Alliance",
        "solicitation_url": "https://www.energy.gov/em/articles/doe-announces-selection-clean-energy-project-savannah-river-site",
        "nepa_review_document_url": "https://www.energy.gov/nepa/ea-2244-commercial-clean-energy-projects-savannah-river-site",
        "key_advantages": [
            "1 GW Hyperscale AI Data Center Campus + ~2 GW Dedicated Clean Power",
            "Federal security perimeter (DoD/DOE Level-3 protected)",
            "High-capacity 230/500 kV transmission ties to Southern Company / Dominion",
            "Dedicated Savannah River cooling water allocations",
        ],
    },
    {
        "site_id": "doe-em-inl",
        "site_name": "Idaho National Laboratory (INL Site / CFPP)",
        "managing_office": "DOE-EM",
        "state": "ID",
        "county": "Butte",
        "latitude": 43.5333,
        "longitude": -112.9500,
        "available_acreage": 570000.0,
        "target_technologies": ["nuclear_smr", "nuclear_micro", "datacenter_ai", "geothermal"],
        "program_stage": "Pre_Application",
        "commercial_partner": "Battelle Energy Alliance / NuScale / TerraPower / Oklo",
        "solicitation_url": "https://www.energy.gov/em/articles/cleanup-clean-energy-initiative-idaho-national-laboratory",
        "nepa_review_document_url": "https://www.energy.gov/nepa/doe-eis-0545-versatile-test-reactor",
        "key_advantages": [
            "National nuclear innovation & test reservation",
            "NRC & DOE nuclear regulatory testing authorization pathways",
            "Extensive geotechnical, seismic, and meteorological baseline records",
            "High-voltage Western Interconnection (WECC) tie-lines",
        ],
    },
    {
        "site_id": "doe-em-hanford",
        "site_name": "Hanford Site Clean Energy Reservation",
        "managing_office": "DOE-EM",
        "state": "WA",
        "county": "Benton",
        "latitude": 46.5500,
        "longitude": -119.5000,
        "available_acreage": 8000.0,
        "target_technologies": ["solar_utility", "battery_storage", "nuclear_smr", "datacenter_ai"],
        "program_stage": "RFI_Issued",
        "commercial_partner": "DOE Office of Environmental Management / BPA",
        "solicitation_url": "https://www.energy.gov/em/cleanup-clean-energy-hanford-site",
        "nepa_review_document_url": "https://www.energy.gov/nepa/ea-2230-commercial-clean-energy-hanford",
        "key_advantages": [
            "Columbia River high-volume cooling water corridor",
            "BPA 500 kV heavy transmission backbone proximity",
            "8,000+ contiguous acres designated for commercial utility clean energy leasing",
            "Proximity to Energy Northwest / Columbia Generating Station nuclear infrastructure",
        ],
    },
    {
        "site_id": "doe-em-wipp",
        "site_name": "Waste Isolation Pilot Plant (WIPP Land Withdrawal)",
        "managing_office": "DOE-EM",
        "state": "NM",
        "county": "Eddy",
        "latitude": 32.3717,
        "longitude": -103.7917,
        "available_acreage": 10000.0,
        "target_technologies": ["solar_utility", "battery_storage", "nuclear_micro"],
        "program_stage": "RFI_Issued",
        "commercial_partner": "DOE Environmental Management",
        "solicitation_url": "https://www.energy.gov/em/cleanup-clean-energy-wipp",
        "nepa_review_document_url": None,
        "key_advantages": [
            "Exceptional direct normal solar irradiance (Permian Basin)",
            "Federal security perimeter and non-interfering surface rights",
            "High industrial power demand in surrounding Permian oil & gas electrification corridor",
        ],
    },
    {
        "site_id": "doe-em-nnss",
        "site_name": "Nevada National Security Site (NNSS)",
        "managing_office": "DOE-EM",
        "state": "NV",
        "county": "Nye",
        "latitude": 37.0000,
        "longitude": -116.0000,
        "available_acreage": 860000.0,
        "target_technologies": ["solar_utility", "battery_storage", "nuclear_micro", "datacenter_ai"],
        "program_stage": "RFI_Issued",
        "commercial_partner": "Mission Support and Test Services (MSTS)",
        "solicitation_url": "https://www.energy.gov/em/cleanup-clean-energy-nnss",
        "nepa_review_document_url": None,
        "key_advantages": [
            "Massive contiguous land buffer with zero civilian encroachment",
            "Direct proximity to NV Energy grid and southwest transmission corridors",
            "Ideal for isolated, zero-trust AI defense compute installations",
        ],
    },
    {
        "site_id": "doe-em-paducah",
        "site_name": "Paducah Gaseous Diffusion Plant",
        "managing_office": "DOE-EM",
        "state": "KY",
        "county": "McCracken",
        "latitude": 37.1167,
        "longitude": -88.8000,
        "available_acreage": 3500.0,
        "target_technologies": ["nuclear_smr", "datacenter_ai", "solar_utility"],
        "program_stage": "RFI_Issued",
        "commercial_partner": "DOE Environmental Management / TVA",
        "solicitation_url": "https://www.energy.gov/em/cleanup-clean-energy-paducah",
        "nepa_review_document_url": None,
        "key_advantages": [
            "Legacy GW-scale switchyards (former enrichment plant electrical load)",
            "Ohio River water intake infrastructure",
            "Heavy rail access directly on site",
            "TVA transmission interconnects",
        ],
    },
    {
        "site_id": "doe-em-portsmouth",
        "site_name": "Portsmouth Gaseous Diffusion Plant (Piketon)",
        "managing_office": "DOE-EM",
        "state": "OH",
        "county": "Pike",
        "latitude": 39.0167,
        "longitude": -83.0000,
        "available_acreage": 3700.0,
        "target_technologies": ["nuclear_smr", "nuclear_micro", "datacenter_ai", "solar_utility"],
        "program_stage": "RFI_Issued",
        "commercial_partner": "DOE EM / Southern Ohio Diversification Initiative (SODI)",
        "solicitation_url": "https://www.energy.gov/em/cleanup-clean-energy-portsmouth",
        "nepa_review_document_url": None,
        "key_advantages": [
            "Massive 345/765 kV switchyards (historically drew over 2 GW)",
            "Scioto River water access and licensed wastewater discharge",
            "Centrus commercial HALEU enrichment cascade adjacent",
        ],
    },
    {
        "site_id": "doe-em-oak-ridge",
        "site_name": "Oak Ridge Reservation (Heritage Center / ETTP)",
        "managing_office": "DOE-EM",
        "state": "TN",
        "county": "Roane",
        "latitude": 35.9333,
        "longitude": -84.3833,
        "available_acreage": 1200.0,
        "target_technologies": ["nuclear_smr", "datacenter_ai", "advanced_mfg"],
        "program_stage": "Lease_Executed",
        "commercial_partner": "Kairos Power / TVA / CROET",
        "solicitation_url": "https://www.energy.gov/em/oak-ridge-clean-energy",
        "nepa_review_document_url": "https://www.energy.gov/nepa/ea-2218-kairos-hermes-reactor",
        "key_advantages": [
            "Site of Kairos Hermes demonstration reactor construction",
            "TVA 161/500 kV electrical grid and Clinch River cooling water",
            "Proximity to ORNL research and supercomputing clusters",
        ],
    },
    {
        "site_id": "doe-oced-mineral-basin",
        "site_name": "Mineral Basin Solar Project (Clearfield Mine Land)",
        "managing_office": "DOE-OCED",
        "state": "PA",
        "county": "Clearfield",
        "latitude": 41.0833,
        "longitude": -78.4167,
        "available_acreage": 2700.0,
        "target_technologies": ["solar_utility", "battery_storage", "datacenter_ai"],
        "program_stage": "RFQ_Awarded",
        "commercial_partner": "Swift Current Energy / DOE OCED",
        "solicitation_url": "https://www.energy.gov/oced/clean-energy-demonstrations-current-and-former-mine-land",
        "nepa_review_document_url": None,
        "key_advantages": [
            "402 MW utility-scale solar on former surface coal mining land",
            "PJM transmission interconnection queue position",
            "IRA Energy Community 10% bonus tax credit qualification",
            "Provides clean power to regional PJM industrial and data center loads",
        ],
    },
    {
        "site_id": "doe-oced-lewis-ridge",
        "site_name": "Lewis Ridge Clean Energy Project (Bell County Mine Land)",
        "managing_office": "DOE-OCED",
        "state": "KY",
        "county": "Bell",
        "latitude": 36.7500,
        "longitude": -83.6667,
        "available_acreage": 1500.0,
        "target_technologies": ["solar_utility", "battery_storage", "datacenter_ai"],
        "program_stage": "RFQ_Awarded",
        "commercial_partner": "EDF Renewables / DOE OCED",
        "solicitation_url": "https://www.energy.gov/oced/lewis-ridge-project",
        "nepa_review_document_url": None,
        "key_advantages": [
            "287 MW solar on reclaimed coal mine land in Eastern Kentucky",
            "PJM interconnect via adjacent mining transmission substation",
            "Appalachian regional economic transition priority zone",
        ],
    },
]


def main() -> int:
    log.info("Building Federal Clean Energy Sites Catalog...")
    sites = [dict(raw) for raw in FEDERAL_SITES_CATALOG]

    payload = {
        "generated_at": "2026-08-23T14:00:00Z",
        "source": "DOE Office of Environmental Management (Cleanup to Clean Energy) & DOE OCED Clean Energy on Mine Lands",
        "count": len(sites),
        "sites": sites,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Wrote %d federal clean energy sites -> %s", len(sites), OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
