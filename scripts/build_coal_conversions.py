#!/usr/bin/env python3
"""Build docs/data/coal-conversions.json and docs/data/coal-conversions-proximity.json.

Spec 04: Coal-to-Nuclear & Coal-to-Data-Center Conversion Engine
(docs/specs/spec-coal-reindustrialization-engine.md).

Curates prominent active, retiring, retired, and gas-converted coal-fired
generation assets (>=100 MW), evaluates switchyard voltage, rail loops, and
water intake assets, computes a MODELED stranded-asset valuation, derives
ISO/RTO queue-transfer eligibility, and builds the spatial proximity join
onto the brownfields corpus.

Provenance contract (house rule): every row carries `source_url` (verified
resolving) + `verified_at` (YYYY-MM-DD). Fields no public document supports
(intake GPM, NPDES permit IDs) stay None — absent means unverified, never
zero. Facts re-verified 2026-08-23 against the industry sweep in
research/industry-topical-2026-08.md; re-audit quarterly (retirement dates
move under DOE 202(c) orders and data-center-driven life extensions, in
BOTH directions).

The durable path (spec §3.3) is deriving MW / retirement dates / coordinates
from the cached EIA-860M workbook instead of hand-curating; until then,
`scripts/validate_data.py --only coal-catalog-coherence` guards internal
consistency on every run.
"""
import datetime as dt
import importlib.util
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema import CoalConversionAsset, CoalConversionProximityRecord  # noqa: E402

# Load PointIndex directly from spatial.py so the script also runs in
# sandboxes without `requests` (connectors/__init__ imports every connector).
_spatial_spec = importlib.util.spec_from_file_location("spatial", str(ROOT / "connectors" / "spatial.py"))
_spatial_mod = importlib.util.module_from_spec(_spatial_spec)
_spatial_spec.loader.exec_module(_spatial_mod)
PointIndex = _spatial_mod.PointIndex

log = logging.getLogger("build_coal_conversions")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

COAL_CONVERSIONS_OUT = ROOT / "docs" / "data" / "coal-conversions.json"
COAL_PROXIMITY_OUT = ROOT / "docs" / "data" / "coal-conversions-proximity.json"

VERIFIED = "2026-08-23"

# Curated benchmark of prominent US coal-fired power plants (>=100 MW)
# covering operating, announced-retirement, retired, and gas-converted assets.
# MW figures are nameplate COAL capacity; per-row citation is a resolving
# Global Energy Monitor wiki page (checked 200 on 2026-08-23), with deal
# context in `note`. eia_plant_id is only set when verified against EIA-860M
# (none yet — the validator's EIA-agreement check matches by name+state).
COAL_PLANTS_CATALOG: list[dict[str, Any]] = [
    {
        "plant_name": "Homer City Generating Station",
        "utility_operator": "Homer City Redevelopment / Kiewit",
        "state": "PA", "county": "Indiana",
        "latitude": 40.5133, "longitude": -79.1975,
        "status": "retired", "retired_year": 2023,
        "nameplate_coal_mw": 1884.0, "switchyard_kv": 345.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 3200.0, "iso_rto": "PJM",
        "conversion_suitability": "datacenter_preferred",
        "note": "Homer City Energy Campus: 4.5 GW gas (7 GE Vernova 7HA.02), $10B+, EQT supply agreement-in-principle, ops target 2027 — the marquee coal-to-DC conversion.",
        "source_url": "https://www.gem.wiki/Homer_City_Generating_Station",
    },
    {
        "plant_name": "Widows Creek Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "AL", "county": "Jackson",
        "latitude": 34.8933, "longitude": -85.7533,
        "status": "retired", "retired_year": 2015,
        "nameplate_coal_mw": 1969.0, "switchyard_kv": 500.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 1400.0, "iso_rto": "TVA",
        "conversion_suitability": "datacenter_preferred",
        "note": "Google data center announced 2015 (construction from 2016) — the original coal-to-DC precedent (see reference-campuses).",
        "source_url": "https://www.gem.wiki/Widows_Creek_Fossil_Plant",
    },
    {
        "plant_name": "Conesville Power Plant",
        "utility_operator": "AEP / Frontier Industrial",
        "state": "OH", "county": "Coshocton",
        "latitude": 40.1869, "longitude": -81.8953,
        "status": "retired", "retired_year": 2020,
        "nameplate_coal_mw": 2174.8, "switchyard_kv": 345.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 2500.0, "iso_rto": "PJM",
        "conversion_suitability": "dual_feasible",
        "note": "Aligned Data Centers campus announced on the demolished plant site (see reference-campuses).",
        "source_url": "https://www.gem.wiki/Conesville_Power_Plant",
    },
    {
        "plant_name": "Naughton Power Plant (Kemmerer)",
        "utility_operator": "PacifiCorp",
        "state": "WY", "county": "Lincoln",
        "latitude": 41.7583, "longitude": -110.5956,
        "status": "planned_retirement", "planned_retirement_year": 2026,
        "nameplate_coal_mw": 700.0, "switchyard_kv": 230.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 1200.0, "iso_rto": "Non-RTO/WECC",
        "conversion_suitability": "nuclear_preferred",
        "note": "TerraPower Natrium Kemmerer Unit 1 adjacent — NRC construction permit 2026-03-04 (first commercial non-LWR in 40+ yrs), construction started 2026-04-23; the world's only active coal-to-nuclear conversion.",
        "source_url": "https://www.gem.wiki/Naughton_Power_Plant",
    },
    {
        "plant_name": "Belews Creek Steam Station",
        "utility_operator": "Duke Energy Carolinas",
        "state": "NC", "county": "Stokes",
        "latitude": 36.2994, "longitude": -80.0617,
        "status": "planned_retirement", "planned_retirement_year": 2036,
        "nameplate_coal_mw": 2240.0, "switchyard_kv": 500.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 2100.0, "iso_rto": "Non-RTO/SERC",
        "conversion_suitability": "nuclear_preferred",
        "note": "Duke SMR early-site-permit application submitted for this site (late 2025); Duke has proposed delaying coal retirement to 2040 — dates policy-contingent.",
        "source_url": "https://www.gem.wiki/Belews_Creek_Steam_Station",
    },
    {
        "plant_name": "Colstrip Steam Plant",
        "utility_operator": "NorthWestern Energy (55% owner) / Talen Montana (operator)",
        "state": "MT", "county": "Rosebud",
        "latitude": 45.8825, "longitude": -106.6128,
        "status": "operating",
        "nameplate_coal_mw": 1480.0, "switchyard_kv": 500.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 3500.0, "iso_rto": "Non-RTO/WECC",
        "conversion_suitability": "datacenter_preferred",
        "note": "LIFE-EXTENSION, not retirement: NorthWestern became 55% majority owner of Units 3&4 on 2026-01-01 (Avista/Puget exits) and signed DC development agreements (Sabey, Atlas Power, Quantica) — ~150 MW late-2027 growing to ~1,500 MW by 2030.",
        "source_url": "https://www.gem.wiki/Colstrip_Steam_Plant",
    },
    {
        "plant_name": "Craig Generating Station",
        "utility_operator": "Tri-State Generation & Transmission",
        "state": "CO", "county": "Moffat",
        "latitude": 40.4636, "longitude": -107.5911,
        "status": "planned_retirement", "planned_retirement_year": 2028,
        "nameplate_coal_mw": 1303.0, "switchyard_kv": 345.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 1800.0, "iso_rto": "Non-RTO/WECC",
        "conversion_suitability": "dual_feasible",
        "note": "Unit 2 retirement announced for 2028-09-30; Unit 1's end-2025 retirement is ALREADY overridden by an active DOE 202(c) emergency order (Dec 2025, renewed). Tri-State's announced replacement is solar + gas + storage, so nuclear is advocacy, not an owner program.",
        "source_url": "https://www.gem.wiki/Craig_Station",
    },
    {
        "plant_name": "Gibson Generating Station",
        "utility_operator": "Duke Energy Indiana",
        "state": "IN", "county": "Gibson",
        "latitude": 38.3711, "longitude": -87.7578,
        "status": "planned_retirement", "planned_retirement_year": 2038,
        "nameplate_coal_mw": 3145.0, "switchyard_kv": 345.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 3200.0, "iso_rto": "MISO",
        "conversion_suitability": "dual_feasible",
        "note": "Latest Duke Indiana IRP pushed retirement from 2035 to 2038 with a gas co-fire retrofit — an example of the retirement-slippage current.",
        "source_url": "https://www.gem.wiki/Gibson_Generating_Station",
    },
    {
        "plant_name": "Montour Steam Electric Station",
        "utility_operator": "Talen Energy",
        "state": "PA", "county": "Montour",
        "latitude": 41.0717, "longitude": -76.6667,
        "status": "converted_gas", "retired_year": 2025,
        "nameplate_coal_mw": 1500.0, "switchyard_kv": 500.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 2100.0, "iso_rto": "PJM",
        "conversion_suitability": "datacenter_preferred",
        "note": "Gas conversion COMPLETED Aug 2023 (dual-fuel); coal exit required by end-2025. An operating gas plant with a 500 kV POI, not a stranded site.",
        "source_url": "https://www.gem.wiki/Montour_Steam_Station",
    },
    {
        "plant_name": "Rockport Generating Station",
        "utility_operator": "Indiana Michigan Power (AEP)",
        "state": "IN", "county": "Spencer",
        "latitude": 37.9258, "longitude": -87.0372,
        "status": "planned_retirement", "planned_retirement_year": 2028,
        "nameplate_coal_mw": 2600.0, "switchyard_kv": 765.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 2800.0, "iso_rto": "PJM",
        "conversion_suitability": "dual_feasible",
        "note": "Both units retire by end-2028 under a court consent decree; Indiana officials moved in Aug 2026 to keep it burning, and I&M has filed plans for a gas 'energy center' at the site (~2030). 765 kV switchyard — the highest-capacity POI in the catalog.",
        "source_url": "https://www.gem.wiki/Rockport_Plant",
    },
    {
        "plant_name": "Cumberland Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "TN", "county": "Stewart",
        "latitude": 36.3908, "longitude": -87.6533,
        "status": "operating",
        "nameplate_coal_mw": 2470.0, "switchyard_kv": 500.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 2300.0, "iso_rto": "TVA",
        "conversion_suitability": "dual_feasible",
        "note": "LIFE-EXTENSION: TVA's board voted unanimously 2026-02-11 to continue operating Cumberland (and Kingston) beyond the previously scheduled retirement dates, reversing the 2024 decision; the 1,450-MW gas CC remains under construction adjacent. The Colstrip pattern, not a conversion window.",
        "source_url": "https://www.gem.wiki/Cumberland_Fossil_Plant",
    },
    {
        "plant_name": "Martin Lake Steam Electric Station",
        "utility_operator": "Luminant (Vistra)",
        "state": "TX", "county": "Rusk",
        "latitude": 32.2619, "longitude": -94.5683,
        "status": "operating",
        "nameplate_coal_mw": 2250.0, "switchyard_kv": 345.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 3000.0, "iso_rto": "ERCOT",
        "conversion_suitability": "datacenter_preferred",
        "source_url": "https://www.gem.wiki/Martin_Lake_Steam_Station",
    },
    {
        "plant_name": "Bull Run Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "TN", "county": "Anderson",
        "latitude": 36.0219, "longitude": -84.1575,
        "status": "retired", "retired_year": 2023,
        "nameplate_coal_mw": 881.0, "switchyard_kv": 500.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 950.0, "iso_rto": "TVA",
        "conversion_suitability": "dual_feasible",
        "note": "Stacks imploded Jun 2025; TVA redevelopment underway — Type One Energy fusion LOI, synchronous-condenser RFP, economic-development targeting study. 500 kV POI adjacent to the Oak Ridge corridor.",
        "source_url": "https://www.gem.wiki/Bull_Run_Fossil_Plant",
    },
    {
        "plant_name": "John Sevier Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "TN", "county": "Hawkins",
        "latitude": 36.3867, "longitude": -82.9817,
        "status": "retired", "retired_year": 2012,
        "nameplate_coal_mw": 800.0, "switchyard_kv": 161.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 820.0, "iso_rto": "TVA",
        "conversion_suitability": "datacenter_preferred",
        "note": "TVA gas combined-cycle operating on-site since 2012 — the coal-to-gas-on-site pattern. The POI is in use by the CC, so reuse means surplus-interconnection headroom, not a full transfer.",
        "source_url": "https://www.gem.wiki/John_Sevier_Fossil_Plant",
    },
    {
        "plant_name": "Cheswick Generating Station",
        "utility_operator": "GenOn / Charah Solutions",
        "state": "PA", "county": "Allegheny",
        "latitude": 40.5392, "longitude": -79.7917,
        "status": "retired", "retired_year": 2022,
        "nameplate_coal_mw": 565.0, "switchyard_kv": 138.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 56.0, "iso_rto": "PJM",
        "conversion_suitability": "datacenter_preferred",
        "note": "Plant demolished 2023-24; site marketed for redevelopment (see reference-campuses row).",
        "source_url": "https://www.gem.wiki/Cheswick_Power_Station",
    },
    {
        "plant_name": "Paradise Fossil Plant",
        "utility_operator": "Tennessee Valley Authority",
        "state": "KY", "county": "Muhlenberg",
        "latitude": 37.2611, "longitude": -86.9806,
        "status": "retired", "retired_year": 2020,
        "nameplate_coal_mw": 2630.0, "switchyard_kv": 500.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 3000.0, "iso_rto": "TVA",
        "conversion_suitability": "dual_feasible",
        "note": "TVA Paradise gas combined-cycle operating on-site; retired coal units demolished 2021. The POI is in use by the CC, so reuse means surplus-interconnection headroom, not a full transfer.",
        "source_url": "https://www.gem.wiki/Paradise_Fossil_Plant",
    },
    {
        "plant_name": "Merom Generating Station",
        "utility_operator": "Hallador Energy",
        "state": "IN", "county": "Sullivan",
        "latitude": 39.0567, "longitude": -87.5142,
        "status": "operating",
        "nameplate_coal_mw": 1080.0, "switchyard_kv": 345.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 1900.0, "iso_rto": "MISO",
        "conversion_suitability": "datacenter_preferred",
        "note": "Hallador (acquired from Hoosier Energy) signed a 12-year contract with NIPSCO GenCo (2026) to serve Google and Amazon data-center load from Merom — the operating-coal-to-DC-supply pattern.",
        "source_url": "https://www.gem.wiki/Merom_Generating_Station",
    },
    {
        "plant_name": "W.A. Parish Electric Generating Station",
        "utility_operator": "NRG Texas Power",
        "state": "TX", "county": "Fort Bend",
        "latitude": 29.4789, "longitude": -95.6319,
        "status": "operating",
        "nameplate_coal_mw": 2497.0, "switchyard_kv": 345.0,
        "has_rail": True, "has_water_intake": True,
        "site_acreage": 4800.0, "iso_rto": "ERCOT",
        "conversion_suitability": "datacenter_preferred",
        "note": "Petra Nova carbon-capture facility on-site; co-located gas units.",
        "source_url": "https://www.gem.wiki/W_A_Parish_Generating_Station",
    },
]


def calculate_stranded_asset_valuation(
    mw: float,
    has_water: bool,
    has_rail: bool,
    distance_mi: float = 0.0,
) -> float:
    """MODELED stranded-asset replacement value in USD.

    Heuristic anchored to the DOE/INL coal-to-nuclear literature's 15-35%
    overnight-capex-savings range: $180k/MW grid interconnect + $25M water
    intake + $12M rail loop + $8M civil works, decayed exp(-0.25 * miles).
    Always present as an estimate in UI — never as an appraisal.
    """
    grid_val = mw * 180_000.0
    water_val = 25_000_000.0 if has_water else 0.0
    rail_val = 12_000_000.0 if has_rail else 0.0
    civil_val = 8_000_000.0

    total_base = grid_val + water_val + rail_val + civil_val
    decay = math.exp(-0.25 * distance_mi)
    return round(total_base * decay, 2)


def build_assets() -> list[dict[str, Any]]:
    """Materialize the catalog: derive valuation + queue eligibility, stamp
    the audit date, and validate every row against the Pydantic schema so a
    malformed row fails the build instead of shipping."""
    assets: list[dict[str, Any]] = []
    for raw in COAL_PLANTS_CATALOG:
        asset = dict(raw)
        asset.setdefault("verified_at", VERIFIED)
        # POI-reuse eligibility is DERIVED, never hand-set: an operating
        # plant's interconnection is not transferable, and a gas-converted
        # plant's POI is occupied by its successor units (surplus headroom at
        # best — say so in the row note, don't claim a transfer).
        asset["queue_transfer_eligible"] = asset["status"] in ("retired", "planned_retirement")
        asset["est_stranded_asset_value_usd"] = calculate_stranded_asset_valuation(
            asset["nameplate_coal_mw"],
            asset["has_water_intake"],
            asset["has_rail"],
            distance_mi=0.0,
        )
        validated = CoalConversionAsset(**asset)
        assets.append(json.loads(validated.model_dump_json(exclude_none=True)))
    return assets


def main() -> int:
    log.info("Building Coal Conversion Assets...")
    assets = build_assets()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "generated_at": now,
        "source": "Curated from Global Energy Monitor plant records + 2026-08 industry sweep (research/industry-topical-2026-08.md); valuation modeled per spec 04",
        "count": len(assets),
        "assets": assets,
    }
    COAL_CONVERSIONS_OUT.parent.mkdir(parents=True, exist_ok=True)
    COAL_CONVERSIONS_OUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %d coal conversion assets -> %s", len(assets), COAL_CONVERSIONS_OUT)

    # Build spatial index to join onto tracked brownfield sites
    log.info("Building spatial proximity index onto brownfield sites...")
    plant_index = PointIndex()
    for a in assets:
        plant_index.add_point(a["latitude"], a["longitude"], a)

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
            # Derive the flag from the SAME rounded value we store, so the
            # emitted record is self-consistent and any consumer (validator,
            # tests, UI) can re-derive it from the record's own fields.
            dist_r = round(dist_mi, 2)
            val = calculate_stranded_asset_valuation(
                plant_asset["nameplate_coal_mw"],
                plant_asset["has_water_intake"],
                plant_asset["has_rail"],
                distance_mi=dist_r,
            )
            rec = CoalConversionProximityRecord(
                id=s_id,
                coal_conversion_plant_name=plant_asset["plant_name"],
                coal_conversion_plant_mi=dist_r,
                coal_conversion_mw=plant_asset["nameplate_coal_mw"],
                coal_conversion_switchyard_kv=plant_asset["switchyard_kv"],
                coal_conversion_rail=plant_asset["has_rail"],
                coal_conversion_water=plant_asset["has_water_intake"],
                coal_conversion_stranded_val_usd=val,
                coal_conversion_queue_fasttrack=(
                    dist_r <= 1.5 and plant_asset["queue_transfer_eligible"]
                ),
            )
            proximity_matches.append(json.loads(rec.model_dump_json()))

    prox_payload = {
        "generated_at": now,
        "source": "Coal Conversion Proximity Index (PointIndex <= 10 mi)",
        "count": len(proximity_matches),
        "matches": proximity_matches,
    }
    COAL_PROXIMITY_OUT.write_text(json.dumps(prox_payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %d coal conversion proximity matches -> %s", len(proximity_matches), COAL_PROXIMITY_OUT)

    return 0


if __name__ == "__main__":
    sys.exit(main())
