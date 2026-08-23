#!/usr/bin/env python3
"""Build docs/data/coal-conversions.json and docs/data/coal-conversions-proximity.json.

Spec 04: Coal-to-Nuclear & Coal-to-Data-Center Conversion Engine.
Ingests prominent active, retiring, and retired coal-fired generation assets (≥100 MW),
evaluates switchyard voltage, rail loops, and water intake assets, computes stranded
asset valuation ($M), ISO/RTO fast-track queue eligibility, and builds the spatial
proximity index joining onto the brownfields corpus.
"""
import importlib.util
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Load PointIndex directly from spatial.py to avoid connectors.__init__ dependencies
_spatial_spec = importlib.util.spec_from_file_location("spatial", str(ROOT / "connectors" / "spatial.py"))
_spatial_mod = importlib.util.module_from_spec(_spatial_spec)
_spatial_spec.loader.exec_module(_spatial_mod)
PointIndex = _spatial_mod.PointIndex

log = logging.getLogger("build_coal_conversions")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

COAL_CONVERSIONS_OUT = ROOT / "docs" / "data" / "coal-conversions.json"
COAL_PROXIMITY_OUT = ROOT / "docs" / "data" / "coal-conversions-proximity.json"

# Curated benchmark of prominent US coal-fired power plants (≥100 MW)
# covering active, announced retirement (2026–2035), and recent retirements (2015–2025).
# Combines EIA Form 860, EPA CAMD, and DOE Coal-to-Nuclear / Coal-to-DC studies.
COAL_PLANTS_CATALOG: list[dict[str, Any]] = [
    {
        "eia_plant_id": 3118,
        "plant_name": "Homer City Generating Station",
        "utility_operator": "Homer City Generation LP",
        "state": "PA",
        "county": "Indiana",
        "latitude": 40.5133,
        "longitude": -79.1975,
        "status": "retired",
        "retired_year": 2023,
        "nameplate_coal_mw": 2012.0,
        "switchyard_kv": 345.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 32000.0,
        "npdes_permit_id": "PA0005037",
        "site_acreage": 2400.0,
        "iso_rto": "PJM",
        "queue_transfer_eligible": True,
        "conversion_suitability": "dual_feasible",
    },
    {
        "eia_plant_id": 3877,
        "plant_name": "Widows Creek Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "AL",
        "county": "Jackson",
        "latitude": 34.8933,
        "longitude": -85.7533,
        "status": "retired",
        "retired_year": 2015,
        "nameplate_coal_mw": 1600.0,
        "switchyard_kv": 500.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 45000.0,
        "npdes_permit_id": "AL0003051",
        "site_acreage": 1400.0,
        "iso_rto": "TVA",
        "queue_transfer_eligible": True,
        "conversion_suitability": "datacenter_preferred",
    },
    {
        "eia_plant_id": 2840,
        "plant_name": "Conesville Power Plant",
        "utility_operator": "AEP / Frontier Industrial",
        "state": "OH",
        "county": "Coshocton",
        "latitude": 40.1869,
        "longitude": -81.8953,
        "status": "retired",
        "retired_year": 2020,
        "nameplate_coal_mw": 1780.0,
        "switchyard_kv": 345.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 38000.0,
        "npdes_permit_id": "OH0001082",
        "site_acreage": 2500.0,
        "iso_rto": "PJM",
        "queue_transfer_eligible": True,
        "conversion_suitability": "dual_feasible",
    },
    {
        "eia_plant_id": 6178,
        "plant_name": "Naughton Power Plant / Kemper Site",
        "utility_operator": "PacifiCorp / TerraPower",
        "state": "WY",
        "county": "Lincoln",
        "latitude": 41.7583,
        "longitude": -110.5956,
        "status": "planned_retirement",
        "planned_retirement_year": 2026,
        "nameplate_coal_mw": 700.0,
        "switchyard_kv": 230.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 18000.0,
        "npdes_permit_id": "WY0001392",
        "site_acreage": 1200.0,
        "iso_rto": "WECC",
        "queue_transfer_eligible": True,
        "conversion_suitability": "nuclear_preferred",
    },
    {
        "eia_plant_id": 2712,
        "plant_name": "Belews Creek Steam Station",
        "utility_operator": "Duke Energy Carolinas",
        "state": "NC",
        "county": "Stokes",
        "latitude": 36.2994,
        "longitude": -80.0617,
        "status": "planned_retirement",
        "planned_retirement_year": 2030,
        "nameplate_coal_mw": 2240.0,
        "switchyard_kv": 500.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 48000.0,
        "npdes_permit_id": "NC0024406",
        "site_acreage": 2100.0,
        "iso_rto": "Non-RTO/SERC",
        "queue_transfer_eligible": True,
        "conversion_suitability": "nuclear_preferred",
    },
    {
        "eia_plant_id": 6019,
        "plant_name": "Colstrip Steam Plant",
        "utility_operator": "Talen Montana / Puget Sound Energy",
        "state": "MT",
        "county": "Rosebud",
        "latitude": 45.8825,
        "longitude": -106.6128,
        "status": "planned_retirement",
        "planned_retirement_year": 2030,
        "nameplate_coal_mw": 1480.0,
        "switchyard_kv": 500.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 26000.0,
        "npdes_permit_id": "MT0023965",
        "site_acreage": 3500.0,
        "iso_rto": "WECC",
        "queue_transfer_eligible": True,
        "conversion_suitability": "dual_feasible",
    },
    {
        "eia_plant_id": 6035,
        "plant_name": "Craig Generating Station",
        "utility_operator": "Tri-State Generation & Transmission",
        "state": "CO",
        "county": "Moffat",
        "latitude": 40.4636,
        "longitude": -107.5911,
        "status": "planned_retirement",
        "planned_retirement_year": 2028,
        "nameplate_coal_mw": 1303.0,
        "switchyard_kv": 345.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 22000.0,
        "npdes_permit_id": "CO0001091",
        "site_acreage": 1800.0,
        "iso_rto": "WECC",
        "queue_transfer_eligible": True,
        "conversion_suitability": "nuclear_preferred",
    },
    {
        "eia_plant_id": 1364,
        "plant_name": "Gibson Generating Station",
        "utility_operator": "Duke Energy Indiana",
        "state": "IN",
        "county": "Gibson",
        "latitude": 38.3711,
        "longitude": -87.7578,
        "status": "planned_retirement",
        "planned_retirement_year": 2029,
        "nameplate_coal_mw": 3145.0,
        "switchyard_kv": 345.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 65000.0,
        "npdes_permit_id": "IN0000680",
        "site_acreage": 3200.0,
        "iso_rto": "MISO",
        "queue_transfer_eligible": True,
        "conversion_suitability": "dual_feasible",
    },
    {
        "eia_plant_id": 3149,
        "plant_name": "Montour Steam Electric Station",
        "utility_operator": "Talen Energy",
        "state": "PA",
        "county": "Montour",
        "latitude": 41.0717,
        "longitude": -76.6667,
        "status": "retired",
        "retired_year": 2025,
        "nameplate_coal_mw": 1500.0,
        "switchyard_kv": 500.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 30000.0,
        "npdes_permit_id": "PA0008443",
        "site_acreage": 2100.0,
        "iso_rto": "PJM",
        "queue_transfer_eligible": True,
        "conversion_suitability": "dual_feasible",
    },
    {
        "eia_plant_id": 8223,
        "plant_name": "Rockport Generating Station",
        "utility_operator": "Indiana Michigan Power (AEP)",
        "state": "IN",
        "county": "Spencer",
        "latitude": 37.9258,
        "longitude": -87.0372,
        "status": "planned_retirement",
        "planned_retirement_year": 2028,
        "nameplate_coal_mw": 2600.0,
        "switchyard_kv": 765.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 55000.0,
        "npdes_permit_id": "IN0001091",
        "site_acreage": 2800.0,
        "iso_rto": "PJM",
        "queue_transfer_eligible": True,
        "conversion_suitability": "dual_feasible",
    },
    {
        "eia_plant_id": 3935,
        "plant_name": "Cumberland Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "TN",
        "county": "Stewart",
        "latitude": 36.3908,
        "longitude": -87.6533,
        "status": "planned_retirement",
        "planned_retirement_year": 2028,
        "nameplate_coal_mw": 2470.0,
        "switchyard_kv": 500.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 52000.0,
        "npdes_permit_id": "TN0005789",
        "site_acreage": 2300.0,
        "iso_rto": "TVA",
        "queue_transfer_eligible": True,
        "conversion_suitability": "dual_feasible",
    },
    {
        "eia_plant_id": 6031,
        "plant_name": "Martin Lake Steam Electric Station",
        "utility_operator": "Luminant (Vistra)",
        "state": "TX",
        "county": "Rusk",
        "latitude": 32.2619,
        "longitude": -94.5683,
        "status": "operating",
        "nameplate_coal_mw": 2250.0,
        "switchyard_kv": 345.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 42000.0,
        "npdes_permit_id": "TX0047431",
        "site_acreage": 3000.0,
        "iso_rto": "ERCOT",
        "queue_transfer_eligible": True,
        "conversion_suitability": "datacenter_preferred",
    },
    {
        "eia_plant_id": 3943,
        "plant_name": "Bull Run Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "TN",
        "county": "Anderson",
        "latitude": 36.0219,
        "longitude": -84.1575,
        "status": "retired",
        "retired_year": 2023,
        "nameplate_coal_mw": 881.0,
        "switchyard_kv": 500.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 25000.0,
        "npdes_permit_id": "TN0005410",
        "site_acreage": 950.0,
        "iso_rto": "TVA",
        "queue_transfer_eligible": True,
        "conversion_suitability": "nuclear_preferred",
    },
    {
        "eia_plant_id": 3936,
        "plant_name": "John Sevier Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "TN",
        "county": "Hawkins",
        "latitude": 36.3867,
        "longitude": -82.9817,
        "status": "retired",
        "retired_year": 2012,
        "nameplate_coal_mw": 800.0,
        "switchyard_kv": 161.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 20000.0,
        "npdes_permit_id": "TN0005436",
        "site_acreage": 820.0,
        "iso_rto": "TVA",
        "queue_transfer_eligible": True,
        "conversion_suitability": "datacenter_preferred",
    },
    {
        "eia_plant_id": 880036,
        "plant_name": "Cheswick Generating Station",
        "utility_operator": "GenOn / Charah Solutions",
        "state": "PA",
        "county": "Allegheny",
        "latitude": 40.5392,
        "longitude": -79.7917,
        "status": "retired",
        "retired_year": 2022,
        "nameplate_coal_mw": 565.0,
        "switchyard_kv": 138.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 18000.0,
        "npdes_permit_id": "PA0001627",
        "site_acreage": 56.0,
        "iso_rto": "PJM",
        "queue_transfer_eligible": True,
        "conversion_suitability": "datacenter_preferred",
    },
    {
        "eia_plant_id": 3948,
        "plant_name": "Paradise Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "KY",
        "county": "Muhlenberg",
        "latitude": 37.2611,
        "longitude": -86.9806,
        "status": "retired",
        "retired_year": 2020,
        "nameplate_coal_mw": 2630.0,
        "switchyard_kv": 500.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 54000.0,
        "npdes_permit_id": "KY0001473",
        "site_acreage": 3000.0,
        "iso_rto": "TVA",
        "queue_transfer_eligible": True,
        "conversion_suitability": "dual_feasible",
    },
    {
        "eia_plant_id": 1374,
        "plant_name": "Merom Generating Station",
        "utility_operator": "Hoosier Energy / Hallador Energy",
        "state": "IN",
        "county": "Sullivan",
        "latitude": 39.0567,
        "longitude": -87.5142,
        "status": "operating",
        "nameplate_coal_mw": 1080.0,
        "switchyard_kv": 345.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 24000.0,
        "npdes_permit_id": "IN0038474",
        "site_acreage": 1900.0,
        "iso_rto": "MISO",
        "queue_transfer_eligible": True,
        "conversion_suitability": "datacenter_preferred",
    },
    {
        "eia_plant_id": 6040,
        "plant_name": "W.A. Parish Electric Generating Station",
        "utility_operator": "NRG Texas Power",
        "state": "TX",
        "county": "Fort Bend",
        "latitude": 29.4789,
        "longitude": -95.6319,
        "status": "operating",
        "nameplate_coal_mw": 2497.0,
        "switchyard_kv": 345.0,
        "has_rail": True,
        "has_water_intake": True,
        "intake_flow_gpm": 50000.0,
        "npdes_permit_id": "TX0047325",
        "site_acreage": 4800.0,
        "iso_rto": "ERCOT",
        "queue_transfer_eligible": True,
        "conversion_suitability": "datacenter_preferred",
    },
]


def calculate_stranded_asset_valuation(
    mw: float,
    has_water: bool,
    has_rail: bool,
    distance_mi: float = 0.0,
) -> float:
    """Calculate total estimated stranded asset replacement value in USD."""
    # Base grid interconnect value: $180,000 per MW
    grid_val = mw * 180_000.0
    water_val = 25_000_000.0 if has_water else 0.0
    rail_val = 12_000_000.0 if has_rail else 0.0
    civil_val = 8_000_000.0

    total_base = grid_val + water_val + rail_val + civil_val
    decay = math.exp(-0.25 * distance_mi)
    return round(total_base * decay, 2)


def main() -> int:
    log.info("Building Coal Conversion Assets...")
    assets: list[dict[str, Any]] = []

    for raw in COAL_PLANTS_CATALOG:
        val = calculate_stranded_asset_valuation(
            raw["nameplate_coal_mw"],
            raw["has_water_intake"],
            raw["has_rail"],
            distance_mi=0.0,
        )
        asset_dict = dict(raw)
        asset_dict["est_stranded_asset_value_usd"] = val
        assets.append(asset_dict)

    # Write coal-conversions.json
    payload = {
        "generated_at": "2026-08-23T14:00:00Z",
        "source": "EIA Form 860M / EPA CAMD / DOE Coal-to-Clean Reindustrialization Studies",
        "count": len(assets),
        "assets": assets,
    }
    COAL_CONVERSIONS_OUT.parent.mkdir(parents=True, exist_ok=True)
    COAL_CONVERSIONS_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Wrote %d coal conversion assets -> %s", len(assets), COAL_CONVERSIONS_OUT)

    # Build spatial index to join onto tracked brownfield sites
    log.info("Building spatial proximity index onto brownfield sites...")
    plant_index = PointIndex()
    for a in assets:
        plant_index.add_point(a["latitude"], a["longitude"], a)

    # Load all tracked site records from program files
    all_sites: list[dict[str, Any]] = []
    for prog_file in [
        ROOT / "docs" / "data" / "sites.json",
        ROOT / "docs" / "data" / "epa-acres.json",
        ROOT / "docs" / "data" / "dod-fuds.json",
        ROOT / "docs" / "data" / "dod-brac.json",
    ]:
        if prog_file.exists():
            data = json.loads(prog_file.read_text(encoding="utf-8"))
            all_sites.extend(data.get("sites", []))

    log.info("Total brownfield universe for coal proximity matching: %d sites", len(all_sites))

    proximity_matches: list[dict[str, Any]] = []
    MAX_RADIUS_MI = 10.0

    for site in all_sites:
        lat, lon, s_id = site.get("lat"), site.get("lon"), site.get("id")
        if lat is None or lon is None or not s_id:
            continue

        nearest = plant_index.nearest_with_attr(lat, lon)
        if nearest is not None and nearest[0] <= MAX_RADIUS_MI:
            dist_mi, plant_asset = nearest
            val = calculate_stranded_asset_valuation(
                plant_asset["nameplate_coal_mw"],
                plant_asset["has_water_intake"],
                plant_asset["has_rail"],
                distance_mi=dist_mi,
            )
            rec = {
                "id": s_id,
                "coal_conversion_plant_name": plant_asset["plant_name"],
                "coal_conversion_plant_mi": round(dist_mi, 2),
                "coal_conversion_mw": plant_asset["nameplate_coal_mw"],
                "coal_conversion_switchyard_kv": plant_asset["switchyard_kv"],
                "coal_conversion_rail": plant_asset["has_rail"],
                "coal_conversion_water": plant_asset["has_water_intake"],
                "coal_conversion_stranded_val_usd": val,
                "coal_conversion_queue_fasttrack": (dist_mi <= 1.5),
            }
            proximity_matches.append(rec)

    prox_payload = {
        "generated_at": "2026-08-23T14:00:00Z",
        "source": "Coal Conversion Proximity Index (PointIndex <= 10 mi)",
        "count": len(proximity_matches),
        "matches": proximity_matches,
    }
    COAL_PROXIMITY_OUT.write_text(json.dumps(prox_payload, indent=2), encoding="utf-8")
    log.info("Wrote %d coal conversion proximity matches -> %s", len(proximity_matches), COAL_PROXIMITY_OUT)

    return 0


if __name__ == "__main__":
    sys.exit(main())

