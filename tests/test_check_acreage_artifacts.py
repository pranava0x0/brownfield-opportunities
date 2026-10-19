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
])
def test_water_and_plume_names_flagged(name):
    assert names_water_or_plume(name)


@pytest.mark.parametrize("name", [
    "SAVANNAH RIVER SITE (USDOE)", "PEARL HARBOR NAVAL COMPLEX", "KERR-MCGEE CHEMICAL CORP. (SODA SPRINGS PLANT)",
    "WPSC TWO RIVERS MGP", "JAMES RIVER SHIPBUILDING", "35TH AVENUE",
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
