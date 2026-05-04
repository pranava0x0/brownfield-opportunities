"""Polygon math used by FUDS + BRAC connectors."""
from __future__ import annotations

import math

from connectors.geom import (
    ACRES_PER_SQ_METER,
    envelope_center,
    polygon_acreage,
    polygon_area_sq_meters,
)


def test_envelope_center_single_ring():
    rings = [[[-100.0, 40.0], [-99.0, 40.0], [-99.0, 41.0], [-100.0, 41.0], [-100.0, 40.0]]]
    lon, lat = envelope_center(rings)
    assert lon == -99.5
    assert lat == 40.5


def test_envelope_center_multi_ring():
    rings = [
        [[-100.0, 40.0], [-99.0, 40.0], [-100.0, 40.0]],
        [[-110.0, 30.0], [-109.0, 30.0], [-110.0, 30.0]],
    ]
    lon, lat = envelope_center(rings)
    assert lon == -104.5
    assert lat == 35.0


def test_envelope_center_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        envelope_center([])


def test_polygon_area_unit_square_at_equator():
    """A 1°×1° square at the equator should be ~111km × 111km ≈ 1.23e10 m²."""
    rings = [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]
    area = polygon_area_sq_meters(rings)
    expected = 111_320 * 110_540  # cos(0) = 1
    assert math.isclose(area, expected, rel_tol=0.01)


def test_polygon_area_at_high_latitude_smaller():
    """Same 1°×1° square in degrees shrinks at higher latitudes via cos(lat)."""
    equator = polygon_area_sq_meters(
        [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]
    )
    high = polygon_area_sq_meters(
        [[[0.0, 60.0], [1.0, 60.0], [1.0, 61.0], [0.0, 61.0], [0.0, 60.0]]]
    )
    # cos(60°) = 0.5 → high should be ~half of equator
    assert 0.45 < high / equator < 0.55


def test_polygon_area_skips_degenerate_rings():
    """Ring with <3 vertices is silently skipped; must not crash."""
    rings = [
        [[0.0, 0.0], [1.0, 1.0]],  # only 2 points — skipped
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]],  # valid
    ]
    area = polygon_area_sq_meters(rings)
    assert area > 0


def test_polygon_acreage_round_trip():
    """1°×1° at the equator ≈ 1.23e10 m² ≈ 3.04 million acres."""
    rings = [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]
    acres = polygon_acreage(rings)
    sq_m = polygon_area_sq_meters(rings)
    assert acres == round(sq_m * ACRES_PER_SQ_METER, 1)


def test_polygon_acreage_zero_returns_none():
    assert polygon_acreage([]) is None
    # Degenerate-only input → polygon_area_sq_meters returns 0 → None
    assert polygon_acreage([[[0.0, 0.0], [1.0, 1.0]]]) is None
