"""Unit tests for the DOD FUDS connector.

Covers normalize() — converting ArcGIS features from USACE FUDS FeatureServer
into the dashboard's record schema. No network calls.
"""
from __future__ import annotations

from connectors.dod_fuds import DodFuds


def _feature(attrs=None, geom=None):
    base = {
        "OBJECTID": 1,
        "DODFUDSPROPERTYIDPK": "A04MS0001",
        "FEATURENAME": "SOUTHEAST AIR DEPOT",
        "CLOSESTCITY": "Hattiesburg",
        "COUNTY": "Forrest",
        "STATE": "ms",
        "EPAREGION": "04",
        "LATITUDE": 31.264,
        "LONGITUDE": -89.252,
        "STATUS": "Properties without projects",
        "STATUSCODE": "Not on the NPL",
        "ELIGIBILITY": "Eligible",
        "CURRENTOWNER": "LOCAL: City of Hattiesburg",
        "HAS_PROJECTS": "no",
        "CONGRESSIONALDISTRICT": "04",
        "EMSMGMTACTIONPLANLINK": "https://fuds.example.com/A04MS0001",
        "FISCALYEAR": "2024",
    }
    base.update(attrs or {})
    return {
        "attributes": base,
        "geometry": geom if geom is not None else {"x": -89.252, "y": 31.264},
    }


def test_normalize_happy_path():
    rec = DodFuds.normalize(_feature())
    assert rec is not None
    assert rec["id"] == "FUDS-A04MS0001"
    assert rec["program"] == "fuds"
    assert rec["name"] == "SOUTHEAST AIR DEPOT"
    assert rec["city"] == "Hattiesburg"
    assert rec["county"] == "Forrest"
    assert rec["state"] == "MS"
    assert rec["region"] == 4
    assert rec["lat"] == 31.264
    assert rec["lon"] == -89.252
    assert rec["eligibility"] == "Eligible"
    assert rec["fuds_status"] == "Properties without projects"
    assert rec["has_projects"] == "no"
    assert rec["current_owner"] == "LOCAL: City of Hattiesburg"
    assert rec["congressional_district"] == "04"
    assert rec["profile_url"] == "https://fuds.example.com/A04MS0001"
    assert rec["npl_status"] == "Not on the NPL"


def test_state_uppercased():
    """FUDS source returns lowercase state codes; connector must uppercase."""
    rec = DodFuds.normalize(_feature({"STATE": "ca"}))
    assert rec["state"] == "CA"


def test_state_null_handled():
    rec = DodFuds.normalize(_feature({"STATE": None}))
    assert rec["state"] is None


def test_region_parsed_from_string():
    rec = DodFuds.normalize(_feature({"EPAREGION": "10"}))
    assert rec["region"] == 10


def test_region_non_numeric_handled():
    rec = DodFuds.normalize(_feature({"EPAREGION": "N/A"}))
    assert rec["region"] is None


def test_region_null_handled():
    rec = DodFuds.normalize(_feature({"EPAREGION": None}))
    assert rec["region"] is None


def test_drops_record_with_no_property_id():
    rec = DodFuds.normalize(_feature({"DODFUDSPROPERTYIDPK": None}))
    assert rec is None


def test_drops_null_island():
    f = _feature(
        attrs={"LATITUDE": 0.0, "LONGITUDE": 0.0},
        geom={"x": 0.0, "y": 0.0},
    )
    assert DodFuds.normalize(f) is None


def test_drops_out_of_range_coords():
    f = _feature(
        geom={"x": 999.0, "y": 999.0},
        attrs={"LATITUDE": 999.0, "LONGITUDE": 999.0},
    )
    assert DodFuds.normalize(f) is None


def test_falls_back_to_attribute_lat_lon():
    """If geometry is missing, use attribute lat/lon."""
    rec = DodFuds.normalize(_feature(geom={}))
    assert rec is not None
    assert rec["lat"] == 31.264
    assert rec["lon"] == -89.252


def test_drops_record_with_no_coords():
    f = _feature(
        attrs={"LATITUDE": None, "LONGITUDE": None},
        geom={},
    )
    assert DodFuds.normalize(f) is None


def test_eligible_only_filter():
    rec_eligible = DodFuds.normalize(
        _feature({"ELIGIBILITY": "Eligible"}), eligible_only=True
    )
    assert rec_eligible is not None

    rec_ineligible = DodFuds.normalize(
        _feature({"ELIGIBILITY": "Ineligible"}), eligible_only=True
    )
    assert rec_ineligible is None

    rec_null = DodFuds.normalize(
        _feature({"ELIGIBILITY": None}), eligible_only=True
    )
    assert rec_null is None


def test_eligible_filter_off_by_default():
    rec = DodFuds.normalize(_feature({"ELIGIBILITY": "Ineligible"}))
    assert rec is not None
    assert rec["eligibility"] == "Ineligible"


def test_id_namespace_unique():
    """FUDS IDs must not collide with EPA_IDs or ACRES IDs."""
    rec = DodFuds.normalize(_feature())
    assert rec["id"].startswith("FUDS-")


def test_handles_string_coords():
    f = _feature(geom={"x": "-89.5", "y": "31.5"})
    rec = DodFuds.normalize(f)
    assert rec is not None
    assert rec["lat"] == 31.5
    assert rec["lon"] == -89.5


def test_profile_url_null_when_missing():
    rec = DodFuds.normalize(_feature({"EMSMGMTACTIONPLANLINK": None}))
    assert rec["profile_url"] is None


def test_record_shape_complete():
    """Every key the connector emits must be schema-known."""
    rec = DodFuds.normalize(_feature())
    expected = {
        "id", "program", "name", "city", "county", "state", "region",
        "lat", "lon", "profile_url", "current_owner", "eligibility",
        "fuds_status", "has_projects", "congressional_district", "npl_status",
    }
    assert set(rec.keys()) == expected
    assert rec["program"] == "fuds"
