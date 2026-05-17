"""Spatial grid index used by the infra-proximity connector.

Covers:
- haversine sanity (point-to-point distance)
- segment distance: endpoints, midpoint, off-segment perpendicular fall
- grid index: nearest hit across cells, ring expansion early-exit
- edge cases: empty index, null-island sentinel, out-of-range coords,
  degenerate single-vertex polylines
"""
from __future__ import annotations

import math

import pytest

from connectors.spatial import (
    PointIndex,
    SegmentIndex,
    _segment_distance_m,
    haversine_mi,
)


def test_haversine_zero_distance():
    assert haversine_mi(40.0, -74.0, 40.0, -74.0) == pytest.approx(0.0, abs=0.01)


def test_haversine_known_pair_nyc_to_la():
    # NYC (40.7128, -74.0060) → LA (34.0522, -118.2437) ≈ 2,451 mi
    d = haversine_mi(40.7128, -74.0060, 34.0522, -118.2437)
    assert 2440 < d < 2470


def test_haversine_one_degree_latitude():
    # Pure-latitude move of 1° ≈ 69.05 mi (110.54 km / 1.609)
    d = haversine_mi(40.0, -74.0, 41.0, -74.0)
    assert 68.5 < d < 69.5


def test_segment_distance_at_endpoint():
    # (0,0) to (10,0): query at (0,0) → 0 distance.
    assert _segment_distance_m(0, 0, 0, 0, 10, 0) == 0.0


def test_segment_distance_perpendicular_fall():
    # Segment along y=0; query at (5, 3) → 3 (perpendicular foot at (5,0)).
    assert _segment_distance_m(5, 3, 0, 0, 10, 0) == pytest.approx(3.0)


def test_segment_distance_clamps_past_endpoint():
    # Query at (15, 4) — past the segment end (10, 0) → distance to (10,0) = √(25+16)=√41
    assert _segment_distance_m(15, 4, 0, 0, 10, 0) == pytest.approx(math.sqrt(41))


def test_segment_distance_zero_length_segment():
    # Degenerate (a == b) should fall back to point-to-point distance.
    assert _segment_distance_m(3, 4, 0, 0, 0, 0) == pytest.approx(5.0)


def test_index_empty_returns_none():
    idx = SegmentIndex()
    assert idx.nearest_distance_mi(40.0, -74.0) is None


def test_index_invalid_cell_size_raises():
    with pytest.raises(ValueError):
        SegmentIndex(cell_deg=0)
    with pytest.raises(ValueError):
        SegmentIndex(cell_deg=-1)


def test_index_drops_null_island_and_out_of_range():
    """Null-island (≈0,0) and lat>90 are sentinels for missing geometry."""
    idx = SegmentIndex()
    added = idx.add_polyline([[0.0, 0.0], [0.1, 0.1], [200.0, 95.0]])
    # All vertices invalid → 0 segments.
    assert added == 0
    assert idx.segment_count == 0


def test_index_skips_polylines_with_one_point():
    idx = SegmentIndex()
    assert idx.add_polyline([[-74.0, 40.0]]) == 0
    assert idx.add_polyline([]) == 0


def test_index_single_segment_distance():
    """Polyline NYC → Boston. Query 1° south of NYC should be ~69 mi."""
    idx = SegmentIndex()
    idx.add_polyline([[-74.0, 40.7], [-71.0, 42.4]])
    d = idx.nearest_distance_mi(39.7, -74.0)
    assert d is not None
    # Off-segment fall to NYC endpoint, ~1° lat ≈ 69 mi.
    assert 65 < d < 73


def test_index_query_on_segment_returns_zero():
    idx = SegmentIndex()
    idx.add_polyline([[-100.0, 40.0], [-99.0, 40.0]])
    d = idx.nearest_distance_mi(40.0, -99.5)  # midpoint
    assert d is not None
    assert d < 0.1


def test_index_finds_nearest_among_many():
    """Three parallel north-south lines at different longitudes; query closer to
    the middle one."""
    idx = SegmentIndex()
    idx.add_polyline([[-100.0, 39.0], [-100.0, 41.0]])
    idx.add_polyline([[-95.0, 39.0], [-95.0, 41.0]])  # closest to query
    idx.add_polyline([[-90.0, 39.0], [-90.0, 41.0]])
    d = idx.nearest_distance_mi(40.0, -94.5)  # 0.5° east of middle
    assert d is not None
    # 0.5° lon at 40°N ≈ 26.5 mi
    assert 25 < d < 28


def test_index_segment_spans_cell_boundary():
    """A segment crossing several grid cells must be retrievable from a query
    in any cell along its bbox."""
    idx = SegmentIndex(cell_deg=0.25)
    # Long east-west segment from -100 to -98 at lat=40 (spans 8 cells of 0.25°)
    idx.add_polyline([[-100.0, 40.0], [-98.0, 40.0]])
    # Query near each end + middle — all should find it.
    for lon in (-99.95, -99.0, -98.05):
        d = idx.nearest_distance_mi(40.0, lon)
        assert d is not None
        assert d < 0.5  # query is essentially on the line


def test_index_dedupes_segment_seen_in_multiple_cells():
    """A segment that touches multiple cells shouldn't be double-counted in
    the distance loop. We check by computing distance once vs. the same query
    after the same polyline is added 3 times — the min should still be the
    same (no negative distances or numerical drift)."""
    idx = SegmentIndex()
    poly = [[-100.0, 40.0], [-99.0, 40.0]]
    idx.add_polyline(poly)
    d1 = idx.nearest_distance_mi(40.5, -99.5)
    idx.add_polyline(poly)
    idx.add_polyline(poly)
    d2 = idx.nearest_distance_mi(40.5, -99.5)
    assert d1 == pytest.approx(d2, abs=1e-9)


def test_index_returns_none_for_remote_query():
    """A query too far from any segment (beyond MAX_RINGS) returns None."""
    idx = SegmentIndex(cell_deg=0.25)
    # One segment in NJ.
    idx.add_polyline([[-74.0, 40.0], [-74.5, 40.5]])
    # Query near Hawaii (~5,000 mi away) — should exceed MAX_RINGS.
    d = idx.nearest_distance_mi(21.3, -157.8, max_rings=4)
    assert d is None


def test_index_high_latitude_distance_correct():
    """At 60°N, 1° of longitude ≈ 34.5 mi (cos(60°)=0.5). Verify the local
    projection in nearest_distance_mi compensates correctly."""
    idx = SegmentIndex()
    idx.add_polyline([[-100.0, 60.0], [-100.0, 60.5]])
    # Query 1° east of the line, same latitude.
    d = idx.nearest_distance_mi(60.25, -99.0)
    assert d is not None
    assert 33 < d < 36


def test_index_handles_invalid_vertex_in_middle():
    """A bad coordinate splits the polyline; segments before and after still index."""
    idx = SegmentIndex()
    coords = [
        [-100.0, 40.0],
        [-99.0, 40.0],
        [None, None],   # invalid — segment break
        [-95.0, 40.0],
        [-94.0, 40.0],
    ]
    added = idx.add_polyline(coords)
    # Two valid segments survive: -100→-99 and -95→-94.
    assert added == 2
    # Both should be findable.
    d1 = idx.nearest_distance_mi(40.0, -99.5)
    d2 = idx.nearest_distance_mi(40.0, -94.5)
    assert d1 is not None and d1 < 0.5
    assert d2 is not None and d2 < 0.5


def test_index_early_exit_finds_correct_minimum():
    """The ring-expansion early-exit must not return a local minimum when a
    closer segment exists in a farther ring."""
    idx = SegmentIndex(cell_deg=0.25)
    # Segment 1: 50 mi away in cell ring 0.
    idx.add_polyline([[-99.5, 40.0], [-99.4, 40.0]])
    # Segment 2: 5 mi away in cell ring 1.
    idx.add_polyline([[-100.05, 40.0], [-100.04, 40.0]])
    # Query near segment 2 — the closer one. The grid index must visit
    # multiple rings and return the correct nearest.
    d = idx.nearest_distance_mi(40.0, -100.0)
    assert d is not None
    # 0.05° lon at 40°N ≈ 2.6 mi
    assert d < 5


# --- per-segment attribute carryover (transmission kV use case) ---

def test_nearest_with_attr_returns_polyline_attribute():
    idx = SegmentIndex(cell_deg=0.25)
    idx.add_polyline([[-100.0, 40.0], [-99.9, 40.0]], attr=230.0)
    hit = idx.nearest_with_attr(40.0, -99.95)
    assert hit is not None
    d, kv = hit
    assert d < 5  # close
    assert kv == 230.0


def test_nearest_with_attr_resolves_correct_segment_when_multiple_polylines():
    idx = SegmentIndex(cell_deg=0.25)
    idx.add_polyline([[-100.0, 40.0], [-99.9, 40.0]], attr=138.0)
    idx.add_polyline([[-100.0, 41.0], [-99.9, 41.0]], attr=500.0)
    # Query near the 500 kV line.
    hit = idx.nearest_with_attr(41.0, -99.95)
    assert hit is not None
    _, kv = hit
    assert kv == 500.0


def test_nearest_with_attr_returns_none_attr_when_polyline_has_none():
    """Polylines added without an attr return None for the attr slot
    (rail / highway never call add_polyline with attr)."""
    idx = SegmentIndex(cell_deg=0.25)
    idx.add_polyline([[-100.0, 40.0], [-99.9, 40.0]])
    hit = idx.nearest_with_attr(40.0, -99.95)
    assert hit is not None
    _, kv = hit
    assert kv is None


def test_nearest_with_attr_lazy_allocation_backfills_prior_segments():
    """Adding an attr-less polyline first then an attr-bearing one must
    not corrupt the parallel array — prior segments backfill to None."""
    idx = SegmentIndex(cell_deg=0.25)
    idx.add_polyline([[-100.0, 40.0], [-99.9, 40.0]])  # no attr
    idx.add_polyline([[-100.0, 41.0], [-99.9, 41.0]], attr=345.0)
    # First polyline still queryable, returns None for attr.
    h1 = idx.nearest_with_attr(40.0, -99.95)
    assert h1 is not None and h1[1] is None
    # Second polyline returns its kV.
    h2 = idx.nearest_with_attr(41.0, -99.95)
    assert h2 is not None and h2[1] == 345.0


def test_nearest_distance_mi_unaffected_by_attr_path():
    """Adding `attr=...` doesn't change the no-attr API result."""
    idx_a = SegmentIndex(cell_deg=0.25)
    idx_a.add_polyline([[-100.0, 40.0], [-99.9, 40.0]])
    idx_b = SegmentIndex(cell_deg=0.25)
    idx_b.add_polyline([[-100.0, 40.0], [-99.9, 40.0]], attr=230.0)
    da = idx_a.nearest_distance_mi(40.0, -99.95)
    db = idx_b.nearest_distance_mi(40.0, -99.95)
    assert da == pytest.approx(db, rel=1e-6)


# ----- PointIndex -----

def test_point_index_empty_returns_none():
    idx = PointIndex()
    assert idx.nearest_with_attr(40.0, -100.0) is None
    assert idx.nearest_distance_mi(40.0, -100.0) is None
    assert idx.point_count == 0


def test_point_index_zero_distance_at_point():
    idx = PointIndex(cell_deg=0.25)
    idx.add_point(40.0, -100.0, attr={"name": "Sub-A"})
    hit = idx.nearest_with_attr(40.0, -100.0)
    assert hit is not None
    d, attr = hit
    assert d == pytest.approx(0.0, abs=0.001)
    assert attr == {"name": "Sub-A"}


def test_point_index_picks_closer_of_two_points():
    idx = PointIndex(cell_deg=0.25)
    idx.add_point(40.0, -100.0, attr="A")     # far
    idx.add_point(40.05, -100.05, attr="B")   # close (~4.5 mi from query)
    hit = idx.nearest_with_attr(40.05, -100.05)
    assert hit is not None
    d, attr = hit
    assert attr == "B"
    assert d == pytest.approx(0.0, abs=0.001)


def test_point_index_filters_null_island():
    """(0,0) is the standard ESRI sentinel for missing geometry — must not
    pollute distance lookups."""
    idx = PointIndex()
    assert idx.add_point(0.0, 0.0, attr="bad") is False
    assert idx.add_point(40.0, -100.0, attr="good") is True
    hit = idx.nearest_with_attr(40.0, -100.0)
    assert hit is not None
    _, attr = hit
    assert attr == "good"


def test_point_index_filters_out_of_range_coords():
    idx = PointIndex()
    assert idx.add_point(95.0, 0.0, attr="bad") is False     # |lat| > 90
    assert idx.add_point(0.0, 200.0, attr="bad") is False    # |lon| > 180
    assert idx.add_point(45.0, -75.0, attr="good") is True
    assert idx.point_count == 1


def test_point_index_filters_non_numeric_coords():
    idx = PointIndex()
    assert idx.add_point("notanumber", -75.0) is False
    assert idx.add_point(45.0, None) is False
    assert idx.point_count == 0


def test_point_index_ring_expansion_finds_far_point():
    """A query in an empty central cell must walk outward to find the hit."""
    idx = PointIndex(cell_deg=0.25)
    # Single point ~0.6° away in both lat and lon — needs 3 rings of
    # expansion at 0.25° cells. Distance at 40°N: ~52 mi.
    idx.add_point(40.6, -100.6, attr="P")
    hit = idx.nearest_with_attr(40.0, -100.0)
    assert hit is not None
    d, attr = hit
    assert attr == "P"
    assert 45 < d < 60


def test_point_index_early_exit_skips_distant_cells():
    """Once we've found a hit, expansion must stop before scanning irrelevant
    far cells. We verify this indirectly: a near point plus 100 distant points
    should still resolve to the near point and not require visiting all 101.
    """
    idx = PointIndex(cell_deg=0.25)
    idx.add_point(40.001, -100.001, attr="near")
    # Distant ring of fillers — none should beat 'near' on distance.
    for i in range(100):
        idx.add_point(45.0 + 0.001 * i, -90.0, attr=f"far-{i}")
    hit = idx.nearest_with_attr(40.0, -100.0)
    assert hit is not None
    _, attr = hit
    assert attr == "near"


def test_point_index_attr_can_be_dict():
    """Substation / power-plant layers carry multi-field attrs."""
    idx = PointIndex(cell_deg=0.25)
    idx.add_point(40.0, -100.0, attr={"kv": 230.0, "name": "Test Sub"})
    hit = idx.nearest_with_attr(40.0, -100.0)
    assert hit is not None
    _, attr = hit
    assert attr["kv"] == 230.0
    assert attr["name"] == "Test Sub"


def test_point_index_invalid_cell_deg_raises():
    with pytest.raises(ValueError):
        PointIndex(cell_deg=0)
    with pytest.raises(ValueError):
        PointIndex(cell_deg=-0.5)
