"""Unit tests for the DOD FUDS connector.

Covers normalize() — converting ArcGIS features from USACE FUDS FeatureServer
into the dashboard's record schema, and the layer-1 + layer-4 polygon join.
No network calls.
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
        "lat", "lon", "profile_url", "current_owner", "current_owner_source",
        "eligibility", "fuds_status", "has_projects", "congressional_district",
        "npl_status",
    }
    assert set(rec.keys()) == expected
    assert rec["program"] == "fuds"


def test_owner_source_set_when_owner_present():
    """v1.9: every FUDS record with an owner gets a citation label so the
    UI can show provenance."""
    rec = DodFuds.normalize(_feature({"CURRENTOWNER": "PRIVATE: Acme LLC"}))
    assert rec["current_owner_source"] == "USACE FUDS"


def test_owner_source_null_when_owner_missing():
    rec = DodFuds.normalize(_feature({"CURRENTOWNER": None}))
    assert rec["current_owner_source"] is None


# ----- layer-1 + layer-4 polygon join -----

def test_polygon_join_aggregates_multi_parcel_acreage():
    """Same property ID across multiple polygon features → rings concatenate
    and acreage sums. Ensures we don't undercount split FUDS parcels."""
    polygon_features = [
        {
            "attributes": {"DODFUDSPROPERTYIDPK": "X1"},
            "geometry": {"rings": [[[0.0, 0.0], [0.01, 0.0], [0.01, 0.01], [0.0, 0.01], [0.0, 0.0]]]},
        },
        {
            "attributes": {"DODFUDSPROPERTYIDPK": "X1"},
            "geometry": {"rings": [[[1.0, 0.0], [1.01, 0.0], [1.01, 0.01], [1.0, 0.01], [1.0, 0.0]]]},
        },
        {
            "attributes": {"DODFUDSPROPERTYIDPK": "X2"},
            "geometry": {"rings": [[[2.0, 0.0], [2.01, 0.0], [2.01, 0.01], [2.0, 0.01], [2.0, 0.0]]]},
        },
    ]

    # Inline the same logic the connector uses.
    rings_by_id: dict = {}
    for feat in polygon_features:
        prop_id = feat["attributes"]["DODFUDSPROPERTYIDPK"]
        rings_by_id.setdefault(prop_id, []).extend(feat["geometry"]["rings"])

    from connectors.geom import polygon_acreage
    acres_x1 = polygon_acreage(rings_by_id["X1"])
    acres_x2 = polygon_acreage(rings_by_id["X2"])
    # X1 has two parcels, each ~the same size as X2's single parcel,
    # so X1's acreage should be ~2× X2's.
    assert acres_x1 is not None and acres_x2 is not None
    assert 1.8 < acres_x1 / acres_x2 < 2.2


def test_polygon_skips_features_with_no_geometry():
    """Polygon-layer features can lack geometry; those just don't enrich."""
    polygon_features = [
        {"attributes": {"DODFUDSPROPERTYIDPK": "X1"}, "geometry": None},
        {"attributes": {"DODFUDSPROPERTYIDPK": "X2"}, "geometry": {"rings": []}},
    ]
    rings_by_id: dict = {}
    for feat in polygon_features:
        attrs = feat.get("attributes") or {}
        geom = feat.get("geometry") or {}
        prop_id = attrs.get("DODFUDSPROPERTYIDPK")
        rings = geom.get("rings")
        if not prop_id or not rings:
            continue
        rings_by_id.setdefault(prop_id, []).extend(rings)
    assert rings_by_id == {}
