"""Unit tests for the EPA Superfund Redevelopment enrichment connector.

Covers normalize() and is_dc_candidate() — converting ArcGIS features from
the RedevelopmentAppSitePoints FeatureServer and computing the data-center
reuse candidacy flag. No network calls.
"""
from __future__ import annotations

import pytest

from connectors.epa_redev import EpaRedev, is_dc_candidate


def _feature(attrs=None, geom=None):
    base = {
        "OBJECTID": 1,
        "EPA_ID": "NJD980528962",
        "Site_Name": "LIPARI LANDFILL",
        "Region": 2,
        "Address": "1 Landfill Rd",
        "City": "Mantua Township",
        "State": "NJ",
        "County": "Gloucester",
        "ZIP": "08051",
        "Latitude": 39.782,
        "Longitude": -75.174,
        "NPL_Status": "Currently on the Final NPL",
        "Acres": 200.5,
        "InOppZone": "No",
        "NearRR": "Yes - 1/2 mile",
        "NearHwy": "Yes - 1 mile",
        "NearElectL": "Yes - 1 mile",
        "PopDensity": "Completely Within Urban Area",
        "In_Reuse": "No",
        "InWaterServiceArea": "Yes - Within (Over 10,000 Population Served)",
        "NearWastewaterFacility": "Yes - 1 mile",
        "NearWater": "Yes - 1/2 mile",
        "RAU_Status": "Meets the Measure",
    }
    base.update(attrs or {})
    return {
        "attributes": base,
        "geometry": geom if geom is not None else {"x": -75.174, "y": 39.782},
    }


# --- normalize ---

def test_normalize_happy_path():
    rec = EpaRedev.normalize(_feature())
    assert rec is not None
    assert rec["id"] == "NJD980528962"
    assert rec["program"] == "superfund"
    assert rec["epa_id"] == "NJD980528962"
    assert rec["name"] == "LIPARI LANDFILL"
    assert rec["acreage"] == 200.5
    assert rec["state"] == "NJ"
    assert rec["region"] == 2
    assert rec["lat"] == 39.782
    assert rec["lon"] == -75.174
    assert rec["near_electric_transmission"] == "Yes - 1 mile"
    assert rec["near_highway"] == "Yes - 1 mile"
    assert rec["near_railroad"] == "Yes - 1/2 mile"
    assert rec["near_water_supply"] == "Yes - Within (Over 10,000 Population Served)"
    assert rec["near_wastewater"] == "Yes - 1 mile"
    assert rec["near_water_body"] == "Yes - 1/2 mile"
    assert rec["pop_density"] == "Completely Within Urban Area"
    assert rec["in_opp_zone"] == "No"
    assert rec["in_reuse"] == "No"
    assert rec["data_center_reuse_candidate"] is True


def test_drops_record_with_no_epa_id():
    assert EpaRedev.normalize(_feature({"EPA_ID": None})) is None
    assert EpaRedev.normalize(_feature({"EPA_ID": ""})) is None


def test_drops_null_island():
    f = _feature(
        attrs={"Latitude": 0.0, "Longitude": 0.0},
        geom={"x": 0.0, "y": 0.0},
    )
    assert EpaRedev.normalize(f) is None


def test_drops_out_of_range_coords():
    f = _feature(geom={"x": 999.0, "y": 999.0}, attrs={"Latitude": 999.0, "Longitude": 999.0})
    assert EpaRedev.normalize(f) is None


def test_falls_back_to_attribute_lat_lon():
    rec = EpaRedev.normalize(_feature(geom={}))
    assert rec is not None
    assert rec["lat"] == 39.782
    assert rec["lon"] == -75.174


def test_handles_null_acreage():
    rec = EpaRedev.normalize(_feature({"Acres": None}))
    assert rec is not None
    assert rec["acreage"] is None


def test_handles_string_acreage():
    rec = EpaRedev.normalize(_feature({"Acres": "150.3"}))
    assert rec is not None
    assert rec["acreage"] == 150.3


def test_region_parsed_from_numeric():
    rec = EpaRedev.normalize(_feature({"Region": 10}))
    assert rec["region"] == 10


def test_region_null_handled():
    rec = EpaRedev.normalize(_feature({"Region": None}))
    assert rec["region"] is None


# --- is_dc_candidate ---

def test_dc_candidate_all_criteria_met():
    rec = {
        "near_electric_transmission": "Yes - 1 mile",
        "acreage": 100.0,
        "near_water_supply": "Yes - Within (Over 10,000 Population Served)",
    }
    assert is_dc_candidate(rec) is True


def test_dc_candidate_no_power():
    rec = {
        "near_electric_transmission": "No",
        "acreage": 100.0,
        "near_water_supply": "Yes - Within",
    }
    assert is_dc_candidate(rec) is False


def test_dc_candidate_too_small():
    rec = {
        "near_electric_transmission": "Yes - 1 mile",
        "acreage": 10.0,
        "near_water_supply": "Yes - Within",
    }
    assert is_dc_candidate(rec) is False


def test_dc_candidate_no_water():
    rec = {
        "near_electric_transmission": "Yes - 1 mile",
        "acreage": 100.0,
        "near_water_supply": "No",
    }
    assert is_dc_candidate(rec) is False


def test_dc_candidate_null_acreage():
    rec = {
        "near_electric_transmission": "Yes - 1 mile",
        "acreage": None,
        "near_water_supply": "Yes - Within",
    }
    assert is_dc_candidate(rec) is False


def test_dc_candidate_null_fields():
    rec = {
        "near_electric_transmission": None,
        "acreage": 100.0,
        "near_water_supply": None,
    }
    assert is_dc_candidate(rec) is False


def test_dc_candidate_exactly_50_acres():
    """50 acres is the threshold — should qualify."""
    rec = {
        "near_electric_transmission": "Yes - 1/2 mile",
        "acreage": 50.0,
        "near_water_supply": "Yes - Within (Under 10,000 Population Served)",
    }
    assert is_dc_candidate(rec) is True


def test_dc_candidate_49_acres():
    """Just under threshold — should not qualify."""
    rec = {
        "near_electric_transmission": "Yes - 1/2 mile",
        "acreage": 49.9,
        "near_water_supply": "Yes - Within",
    }
    assert is_dc_candidate(rec) is False


def test_record_shape_complete():
    rec = EpaRedev.normalize(_feature())
    expected = {
        "id", "program", "epa_id", "name", "acreage", "npl_status",
        "region", "address", "city", "state", "county", "zip",
        "lat", "lon",
        "near_electric_transmission", "near_highway", "near_railroad",
        "near_water_supply", "near_wastewater", "near_water_body",
        "pop_density", "in_opp_zone", "in_reuse",
        "data_center_reuse_candidate",
    }
    assert set(rec.keys()) == expected
    assert rec["program"] == "superfund"
