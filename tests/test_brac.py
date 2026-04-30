"""Unit tests for the DOD BRAC connector.

Covers normalize() and polygon_area_sq_meters() — converting ArcGIS features
from the milbases FeatureServer into the dashboard's record schema. No network calls.
"""
from __future__ import annotations

import math

import pytest

from connectors.dod_brac import ACRES_PER_SQ_METER, DodBrac

# A small square polygon near DC (~0.01° on a side ≈ ~1.1km × ~0.85km)
SAMPLE_RINGS = [
    [
        [-77.00, 38.90],
        [-76.99, 38.90],
        [-76.99, 38.91],
        [-77.00, 38.91],
        [-77.00, 38.90],
    ]
]


def _feature(attrs=None, rings=None):
    base = {
        "OBJECTID": 75,
        "COMPONENT": "Navy Active",
        "SITE_NAME": "NAS JRB Willow Grove",
        "JOINT_BASE": "N/A",
        "STATE_TERR": "Pennsylvania",
        "BRAC_SITE": "YES",
        "STPOSTAL": "PA",
    }
    base.update(attrs or {})
    return {
        "attributes": base,
        "geometry": {"rings": rings or SAMPLE_RINGS},
    }


def test_normalize_happy_path():
    rec = DodBrac.normalize(DodBrac, _feature())
    assert rec is not None
    assert rec["id"] == "BRAC-75"
    assert rec["program"] == "brac"
    assert rec["name"] == "NAS JRB Willow Grove"
    assert rec["state"] == "PA"
    assert rec["component"] == "Navy Active"
    assert rec["acreage"] is not None
    assert rec["acreage"] > 0
    assert rec["lat"] == pytest.approx(38.905, abs=0.001)
    assert rec["lon"] == pytest.approx(-76.995, abs=0.001)


def test_drops_missing_geometry():
    feat = _feature()
    feat["geometry"] = None
    assert DodBrac.normalize(DodBrac, feat) is None


def test_drops_empty_rings():
    feat = _feature()
    feat["geometry"] = {"rings": []}
    assert DodBrac.normalize(DodBrac, feat) is None


def test_drops_missing_site_name():
    assert DodBrac.normalize(DodBrac, _feature({"SITE_NAME": None})) is None
    assert DodBrac.normalize(DodBrac, _feature({"SITE_NAME": ""})) is None


def test_envelope_center():
    lon, lat = DodBrac.envelope_center(SAMPLE_RINGS)
    assert lon == pytest.approx(-76.995, abs=0.001)
    assert lat == pytest.approx(38.905, abs=0.001)


def test_envelope_center_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        DodBrac.envelope_center([])


def test_polygon_area_sq_meters():
    """A ~0.01° square at 38.9°N should be roughly 1km × 0.85km = ~0.93 km²."""
    area = DodBrac.polygon_area_sq_meters(SAMPLE_RINGS)
    area_km2 = area / 1e6
    assert 0.5 < area_km2 < 1.5


def test_polygon_area_acreage_conversion():
    """Sanity check: area in acres for a known polygon."""
    area = DodBrac.polygon_area_sq_meters(SAMPLE_RINGS)
    acres = area * ACRES_PER_SQ_METER
    assert 100 < acres < 400


def test_polygon_area_degenerate_ring():
    """A ring with fewer than 3 points should contribute zero area."""
    degenerate = [[[0.0, 0.0], [1.0, 1.0]]]
    assert DodBrac.polygon_area_sq_meters(degenerate) == 0.0


def test_id_namespace_unique():
    rec = DodBrac.normalize(DodBrac, _feature())
    assert rec["id"].startswith("BRAC-")


def test_state_from_postal():
    rec = DodBrac.normalize(DodBrac, _feature({"STPOSTAL": "TX"}))
    assert rec["state"] == "TX"


def test_state_null_handled():
    rec = DodBrac.normalize(DodBrac, _feature({"STPOSTAL": None}))
    assert rec["state"] is None


def test_record_shape_complete():
    rec = DodBrac.normalize(DodBrac, _feature())
    expected = {
        "id", "program", "name", "acreage", "state", "component",
        "lat", "lon",
    }
    assert set(rec.keys()) == expected
    assert rec["program"] == "brac"
