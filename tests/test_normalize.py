"""Unit tests for SuperfundNPL.normalize() — locks in unit-conversion + filter behavior."""
from __future__ import annotations

import pytest

from connectors.superfund_npl import NPL_STATUS_LABELS, SuperfundNPL


@pytest.fixture
def conn(tmp_path):
    return SuperfundNPL(cache_dir=tmp_path / "cache")


def _feature(attrs: dict, rings=None) -> dict:
    """Build a minimal ArcGIS feature dict with sensible defaults."""
    base = {
        "EPA_ID": "TEST00000001",
        "SITE_NAME": "Test Site",
        "NPL_STATUS_CODE": "F",
        "FEDERAL_FACILITY_DETER_CODE": "N",
        "REGION_CODE": 5,
        "STREET_ADDR_TXT": "1 Main St",
        "CITY_NAME": "Springfield",
        "COUNTY": "Sangamon",
        "STATE_CODE": "IL",
        "ZIP_CODE": "62701",
        "GIS_AREA": 100.0,
        "GIS_AREA_UNITS": "Acres",
        "URL_ALIAS_TXT": None,
        "FEATURE_INFO_URL": None,
        "LAST_CHANGE_DATE": 1700000000000,
        "ORIGINAL_CREATION_DATE": 1500000000000,
    }
    base.update(attrs)
    return {
        "attributes": base,
        "geometry": {"rings": rings or [[[-89.65, 39.78], [-89.64, 39.78], [-89.64, 39.79], [-89.65, 39.79], [-89.65, 39.78]]]},
    }


# --- Unit conversion ---

def test_acres_pass_through(conn):
    rec = conn.normalize(_feature({"GIS_AREA": 250.5, "GIS_AREA_UNITS": "Acres"}))
    assert rec is not None
    assert rec["acreage"] == 250.5


def test_square_miles_converted(conn):
    rec = conn.normalize(_feature({"GIS_AREA": 2.0, "GIS_AREA_UNITS": "Square Miles"}))
    assert rec is not None
    assert rec["acreage"] == 1280.0  # 2 sq mi × 640 ac/sq mi


def test_miles_unit_falls_back_to_polygon_area(conn):
    """Linear features (Miles): GIS_AREA is a length, not an area, so we
    compute acreage from the polygon rings instead. The default fixture rings
    cover ~0.01° × 0.01° at lat 39.78 → ~234 acres."""
    rec = conn.normalize(
        _feature({"GIS_AREA": 5.0, "GIS_AREA_UNITS": "Miles"}),
        include_no_acreage=True,
    )
    assert rec is not None
    assert rec["acreage"] is not None
    assert 200 < rec["acreage"] < 270


def test_miles_unit_with_zero_area_polygon_dropped_when_excluded(conn):
    """When polygon collapses to a line (zero area) and units aren't areal,
    polygon_acreage returns None — same exclusion behavior as before."""
    degenerate_rings = [[[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]]  # collinear, 0 area
    rec = conn.normalize(
        _feature({"GIS_AREA": 5.0, "GIS_AREA_UNITS": "Miles"}, rings=degenerate_rings),
        include_no_acreage=False,
    )
    assert rec is None


def test_null_units_falls_back_to_polygon_area(conn):
    """When EPA didn't tag the units at all but the geometry is present,
    compute acreage from rings (don't lose the record's footprint)."""
    rec = conn.normalize(
        _feature({"GIS_AREA": 5.0, "GIS_AREA_UNITS": None}),
        include_no_acreage=True,
    )
    assert rec is not None
    assert rec["acreage"] is not None
    assert 200 < rec["acreage"] < 270


def test_null_gis_area_with_acres_units_falls_back_to_polygon_area(conn):
    """Source said 'Acres' but didn't provide a value — compute from rings
    rather than dropping. Same behavior as the units-None branch."""
    rec = conn.normalize(
        _feature({"GIS_AREA": None, "GIS_AREA_UNITS": "Acres"}),
        include_no_acreage=True,
    )
    assert rec is not None
    assert rec["acreage"] is not None
    assert 200 < rec["acreage"] < 270


def test_null_gis_area_dropped_when_excluded_and_polygon_zero(conn):
    """include_no_acreage=False still drops records where polygon_acreage
    returns None (degenerate / collapsed geometry)."""
    degenerate_rings = [[[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]]  # 0 area
    rec = conn.normalize(
        _feature({"GIS_AREA": None, "GIS_AREA_UNITS": "Acres"}, rings=degenerate_rings),
        include_no_acreage=False,
    )
    assert rec is None


# --- Geometry ---

def test_missing_geometry_dropped(conn):
    feat = _feature({})
    feat["geometry"] = None
    assert conn.normalize(feat) is None


def test_missing_rings_dropped(conn):
    feat = _feature({})
    feat["geometry"] = {}
    assert conn.normalize(feat) is None


def test_centroid_uses_envelope(conn):
    rings = [[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]]
    rec = conn.normalize(_feature({}, rings=rings))
    assert rec is not None
    assert rec["lon"] == 5.0
    assert rec["lat"] == 5.0


# --- Status code mapping ---

def test_all_status_codes_mapped(conn):
    for code, label in NPL_STATUS_LABELS.items():
        rec = conn.normalize(_feature({"NPL_STATUS_CODE": code}))
        assert rec is not None
        assert rec["npl_status_code"] == code
        assert rec["npl_status"] == label


def test_unknown_status_code(conn):
    rec = conn.normalize(_feature({"NPL_STATUS_CODE": "Z"}))
    assert rec is not None
    assert rec["npl_status"] == "Unknown"


def test_null_status_code(conn):
    rec = conn.normalize(_feature({"NPL_STATUS_CODE": None}))
    assert rec is not None
    assert rec["npl_status"] == "Unknown"


# --- Profile URL fallback chain ---

def test_url_alias_preferred(conn):
    rec = conn.normalize(_feature({
        "URL_ALIAS_TXT": "https://example.com/alias",
        "FEATURE_INFO_URL": "https://example.com/feature",
    }))
    assert rec["profile_url"] == "https://example.com/alias"


def test_feature_info_fallback(conn):
    rec = conn.normalize(_feature({
        "URL_ALIAS_TXT": None,
        "FEATURE_INFO_URL": "https://example.com/feature",
    }))
    assert rec["profile_url"] == "https://example.com/feature"


def test_epa_id_template_fallback(conn):
    """When both URL fields null, build URL from EPA_ID."""
    rec = conn.normalize(_feature({
        "URL_ALIAS_TXT": None,
        "FEATURE_INFO_URL": None,
        "EPA_ID": "ILD000123456",
    }))
    assert rec["profile_url"] == "https://cumulis.epa.gov/supercpad/CurSites/csitinfo.cfm?id=ILD000123456"


def test_no_profile_url_when_epa_id_missing(conn):
    rec = conn.normalize(_feature({
        "URL_ALIAS_TXT": None,
        "FEATURE_INFO_URL": None,
        "EPA_ID": None,
    }))
    assert rec["profile_url"] is None


# --- Federal facility decoding ---

def test_federal_facility_label_decoded(conn):
    rec = conn.normalize(
        _feature({"FEDERAL_FACILITY_DETER_CODE": "Y"}),
        federal_facility_labels={"Y": "Federal Facility", "N": "Non-Federal", "F": "Formerly Federal"},
    )
    assert rec["federal_facility"] == "Federal Facility"
    assert rec["federal_facility_code"] == "Y"


def test_federal_facility_falls_back_to_code_when_no_labels(conn):
    rec = conn.normalize(_feature({"FEDERAL_FACILITY_DETER_CODE": "Y"}))
    assert rec["federal_facility"] == "Y"
    assert rec["federal_facility_code"] == "Y"


# --- All-optional-fields-null ---

def test_all_optional_fields_null(conn):
    rec = conn.normalize(_feature({
        "STREET_ADDR_TXT": None,
        "CITY_NAME": None,
        "COUNTY": None,
        "STATE_CODE": None,
        "ZIP_CODE": None,
        "FEDERAL_FACILITY_DETER_CODE": None,
        "REGION_CODE": None,
        "LAST_CHANGE_DATE": None,
    }))
    assert rec is not None
    assert rec["address"] is None
    assert rec["city"] is None
    assert rec["state"] is None
    assert rec["federal_facility"] is None


def test_record_shape_complete(conn):
    """Every key the connector emits must be schema-known.

    Future enrichment slots (current_owner, proximity, etc.) live in the
    schema but are no longer emitted by the connector — they're added by
    downstream enrichment passes. Dropping them here keeps the JSON small.
    """
    rec = conn.normalize(_feature({}))
    expected = {
        "id", "program",
        "epa_id", "name", "acreage", "npl_status_code", "npl_status",
        "federal_facility", "federal_facility_code", "region", "address",
        "city", "county", "state", "zip", "lat", "lon", "profile_url",
        "last_updated",
    }
    assert set(rec.keys()) == expected
    assert rec["program"] == "superfund"
    assert rec["id"] == rec["epa_id"]
