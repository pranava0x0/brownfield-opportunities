"""Unit tests for the EPA ACRES (brownfield) connector.

Covers normalize() — the pure function that converts an ArcGIS feature dict
into the dashboard's record schema. No network calls.
"""
from __future__ import annotations

from connectors.epa_acres import EpaAcres


def _feature(attrs=None, geom=None):
    base = {
        "PROPERTY_ID": 122062,
        "PROPERTY_NAME": "Bates Mill #5",
        "RS_REGION_ID_1000": 1,
        "LABEL_STATE": "ME",
        "ADDRESS1": "15 Canal Street",
        "CITY": "Lewiston",
        "COUNTY": "Androscoggin",
        "ZIP_CODE": "04240",
        "LATITUDE_MEASURE": 44.098393,
        "LONGITUDE_MEASURE": -70.218544,
    }
    base.update(attrs or {})
    return {
        "attributes": base,
        "geometry": geom if geom is not None else {"x": -70.218544, "y": 44.098393},
    }


def test_normalize_happy_path():
    rec = EpaAcres.normalize(_feature())
    assert rec is not None
    assert rec["id"] == "ACRES-122062"
    assert rec["program"] == "brownfield"
    assert rec["name"] == "Bates Mill #5"
    assert rec["state"] == "ME"
    assert rec["region"] == 1
    assert rec["lat"] == 44.098393
    assert rec["lon"] == -70.218544
    assert rec["profile_url"].endswith("122062.html")
    # ACRES has no acreage / NPL fields.
    assert "acreage" not in rec
    assert "npl_status_code" not in rec
    assert "federal_facility" not in rec


def test_normalize_falls_back_to_attribute_lat_lon():
    """If geometry is missing, use the attribute lat/lon."""
    rec = EpaAcres.normalize(_feature(geom={}))
    assert rec is not None
    assert rec["lat"] == 44.098393
    assert rec["lon"] == -70.218544


def test_normalize_drops_record_with_no_property_id():
    rec = EpaAcres.normalize(_feature(attrs={"PROPERTY_ID": None}))
    assert rec is None


def test_normalize_drops_null_island():
    """Lat=0, lon=0 is almost always a geocoder failure — discard."""
    f = _feature(attrs={"LATITUDE_MEASURE": 0.0, "LONGITUDE_MEASURE": 0.0},
                 geom={"x": 0.0, "y": 0.0})
    assert EpaAcres.normalize(f) is None


def test_normalize_drops_out_of_range_coords():
    f = _feature(geom={"x": 999.0, "y": 999.0},
                 attrs={"LATITUDE_MEASURE": 999.0, "LONGITUDE_MEASURE": 999.0})
    assert EpaAcres.normalize(f) is None


def test_normalize_handles_string_coords():
    """Source occasionally returns numeric values as strings."""
    f = _feature(geom={"x": "-70.5", "y": "44.5"})
    rec = EpaAcres.normalize(f)
    assert rec is not None
    assert rec["lat"] == 44.5
    assert rec["lon"] == -70.5


def test_id_namespace_unique():
    """ACRES IDs must not collide with EPA_IDs (which look like 'XYZ12345678')."""
    rec = EpaAcres.normalize(_feature())
    assert rec["id"].startswith("ACRES-")
