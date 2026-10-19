"""Acreage that cannot describe a parcel is flagged, and real sites are not."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_acreage_artifacts import names_water_or_plume  # noqa: E402


@pytest.mark.parametrize("name", [
    "HUDSON RIVER PCBS", "GRIGGS & WALNUT GROUND WATER PLUME", "OLEAN WELL FIELD",
    "FOX RIVER NRDA/PCB RELEASES", "ONONDAGA LAKE", "MILLTOWN RESERVOIR SEDIMENTS",
    "TAR CREEK (OTTAWA COUNTY)", "LOWER DARBY CREEK AREA", "COMMENCEMENT BAY, SOUTH TACOMA CHANNEL",
])
def test_water_and_plume_names_flagged(name):
    assert names_water_or_plume(name)


@pytest.mark.parametrize("name", [
    "SAVANNAH RIVER SITE (USDOE)", "PEARL HARBOR NAVAL COMPLEX", "KERR-MCGEE CHEMICAL CORP. (SODA SPRINGS PLANT)",
    "WPSC TWO RIVERS MGP", "JAMES RIVER SHIPBUILDING", "35TH AVENUE",
    "PACIFIC SOUND RESOURCES", "RIVER CITY METAL FINISHING", "BOG CREEK FARM",
])
def test_facility_and_federal_names_not_flagged(name):
    assert not names_water_or_plume(name)


def test_published_flags_cover_known_artifacts_and_spare_real_sites():
    flags = {r["id"]: r["acreage_flag"] for r in json.loads((ROOT / "docs/data/acreage-flags.json").read_text())["sites"]}
    assert flags.get("OKD980629844") in ("county_outline", "water_or_plume")  # Tar Creek: 310,173 ac vs ~25,600 per Oklahoma DEQ
    assert flags.get("FUDS-F10OR0208") == "county_outline"                    # Northwest Maneuver Area, 8M ac
    assert flags.get("NYD980763841") == "water_or_plume"                      # Hudson River PCBs
    assert flags.get("SC1890008989") == "region"                              # Savannah River Site: real land, spans counties
    assert "CA2570024453" not in flags                                        # George AFB, 5,269 ac
    assert "FUDS-F10AK0015" not in flags  # 6,632 ac in the Aleutians East Borough (~0.1%), not one island


def test_county_area_counts_every_component_of_a_multipolygon():
    from connectors.county_lookup import CountyIndex
    counties = CountyIndex.from_path(ROOT / "docs/data/us-counties-topo.json")
    hit = counties.lookup_polygon(55.2, -162.7, "AK")  # Cold Bay, Aleutians East
    assert hit and hit[0] == "Aleutians East"
    assert len(counties.county_polygons(hit[2])) > 1


def test_same_named_city_and_county_are_not_merged():
    """Baltimore city and Baltimore County share a name and a state."""
    from connectors.county_lookup import CountyIndex
    counties = CountyIndex.from_path(ROOT / "docs/data/us-counties-topo.json")
    city = counties.lookup_polygon(39.29, -76.61, "MD")    # downtown Baltimore
    county = counties.lookup_polygon(39.40, -76.60, "MD")  # Towson
    assert city[0] == county[0] == "Baltimore"
    assert not any(p is county[2] for p in counties.county_polygons(city[2]))
