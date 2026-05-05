"""Unit tests for the offline TIGER county point-in-polygon lookup.

Covers TopoJSON arc decoding, ring stitching, and the spatial-grid lookup
that fills missing `county` on ACRES records. Uses a small synthetic
TopoJSON fixture so tests don't depend on the production us-counties file.
A separate "real fixture" test loads `docs/data/us-counties-topo.json` to
guard against regressions in the actual decoder against the actual data.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from connectors.county_lookup import (
    CountyIndex,
    _accumulate_arc,
    _point_in_ring,
    _stitch_ring,
)

REAL_TOPOJSON = (
    Path(__file__).resolve().parent.parent / "docs" / "data" / "us-counties-topo.json"
)


def _square_topology(name: str = "Square", state_id: str = "01") -> dict:
    """Smallest possible valid TopoJSON: one square county.

    Square goes from (0, 0) to (10, 10) in lon/lat, so any point inside
    that box should land inside the polygon.
    """
    return {
        "type": "Topology",
        "transform": {"scale": [1.0, 1.0], "translate": [0.0, 0.0]},
        "arcs": [
            # Delta-encoded square: start (0,0) → (10,0) → (10,10) → (0,10) → (0,0)
            [[0, 0], [10, 0], [0, 10], [-10, 0], [0, -10]],
        ],
        "objects": {
            "counties": {
                "type": "GeometryCollection",
                "geometries": [
                    {
                        "type": "Polygon",
                        "arcs": [[0]],
                        "id": f"{state_id}001",
                        "properties": {"name": name},
                    },
                ],
            },
        },
    }


def test_accumulate_arc_decodes_deltas():
    """Delta-encoded arc should accumulate into absolute coordinates after
    applying the transform."""
    arc = [[0, 0], [10, 0], [0, 5]]
    transform = {"scale": [1.0, 1.0], "translate": [0.0, 0.0]}
    coords = _accumulate_arc(arc, transform)
    assert coords == [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]


def test_accumulate_arc_applies_transform_scale_and_translate():
    arc = [[0, 0], [100, 200]]
    transform = {"scale": [0.01, 0.005], "translate": [-179.0, -14.0]}
    coords = _accumulate_arc(arc, transform)
    assert coords[0] == pytest.approx((-179.0, -14.0))
    assert coords[1] == pytest.approx((-178.0, -13.0))


def test_stitch_ring_handles_negative_arc_indices():
    """TopoJSON encodes shared boundaries by reusing arcs with reversed
    orientation (`~i`). Verify the stitcher reverses correctly."""
    decoded = [
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        [(10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
    ]
    forward = _stitch_ring([0, 1], decoded)
    assert forward == [
        (0.0, 0.0), (10.0, 0.0), (10.0, 10.0),
        (0.0, 10.0), (0.0, 0.0),
    ]
    # Reversed second arc: ~1 == -2 → reverse decoded[1] → ((0,0), (0,10), (10,10))
    reversed_second = _stitch_ring([0, ~1], decoded)
    assert reversed_second[-1] == (10.0, 10.0)


def test_point_in_ring_inside():
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    assert _point_in_ring(5.0, 5.0, ring) is True


def test_point_in_ring_outside():
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    assert _point_in_ring(15.0, 5.0, ring) is False
    assert _point_in_ring(5.0, 15.0, ring) is False


def test_lookup_returns_county_for_point_inside():
    idx = CountyIndex.from_topojson(_square_topology(name="Test County"))
    assert idx.lookup(5.0, 5.0) == "Test County"


def test_lookup_returns_none_for_point_outside():
    idx = CountyIndex.from_topojson(_square_topology())
    assert idx.lookup(20.0, 20.0) is None


def test_lookup_respects_expected_state():
    """Two counties with the same name in different states — expected_state
    should disambiguate by FIPS prefix."""
    topo = _square_topology(name="Lincoln", state_id="01")
    # Add a second county with the same name in a different state.
    second = {
        "type": "Polygon",
        "arcs": [[1]],
        "id": "02001",
        "properties": {"name": "Lincoln"},
    }
    topo["objects"]["counties"]["geometries"].append(second)
    topo["arcs"].append(
        [[100, 100], [10, 0], [0, 10], [-10, 0], [0, -10]],
    )
    # The added arc starts at (100, 100) and traces a 10×10 square there.
    # The state FIPS "02" is Alaska in the lookup table.
    idx = CountyIndex.from_topojson(topo)
    # Point inside the AK square; expected_state filter to AK should hit it.
    assert idx.lookup(105.0, 105.0, expected_state="AK") == "Lincoln"
    # Same point with the wrong expected_state should miss.
    assert idx.lookup(105.0, 105.0, expected_state="AL") is None


def test_real_topojson_loads_and_locates_known_cities():
    """Smoke test against the real TIGER counties file we ship.

    Guards against drift in the file format (TopoJSON spec) or our decoder.
    """
    if not REAL_TOPOJSON.exists():
        pytest.skip("real TIGER topojson not present")
    idx = CountyIndex.from_path(REAL_TOPOJSON)
    # ~3,231 counties in the source; multipolygon expansion pushes count higher.
    assert idx.polygon_count > 3000

    # Spot-check a handful of well-known cities.
    cases = [
        # (lat, lon, expected_state, expected_county_substring)
        (40.7128, -74.0060, "NY", "New York"),     # Manhattan
        (29.7604, -95.3698, "TX", "Harris"),        # Houston
        (44.0982, -70.2186, "ME", "Androscoggin"),  # Lewiston
        (61.2210, -149.8204, "AK", "Anchorage"),    # Anchorage
    ]
    for lat, lon, state, expected in cases:
        actual = idx.lookup(lat, lon, expected_state=state)
        assert actual is not None, f"no county hit at {lat},{lon} ({state})"
        assert expected.lower() in actual.lower(), (
            f"expected {expected!r} for {lat},{lon} but got {actual!r}"
        )

    # Ocean point (well off the East Coast) should miss.
    assert idx.lookup(40.0, -65.0, expected_state="MA") is None
