"""Fuzz the pure-Python spatial indexes against brute force.

`connectors/spatial.py` is the load-bearing correctness dependency for every
distance in `infra-proximity.json` — a nearest-neighbour miss there silently
inflates a site's `transmission_mi` and mis-scores it in both siting lenses.
The index uses grid bucketing plus a Chebyshev ring-expansion early exit, and
that early exit is exactly the kind of bound that is easy to get subtly wrong
(degrees vs metres, latitude vs longitude scale).

These tests answer the question no amount of reading answers: over many
randomised layouts, does the index return the same nearest feature as an
exhaustive scan? The comparison is against brute force using the index's own
distance primitive, so the tests isolate the *search*, not the projection.

Added 2026-08-09 after the corpus-wide `infra-lipschitz` validation
(`scripts/validate_data.py`) reported 2,146 pairs where two sites within
2 miles of each other disagreed by more than their separation — which is
impossible unless a distance is wrong. These tests establish whether the
index or the data pipeline is responsible.
"""
from __future__ import annotations

import math
import random

import pytest

from connectors.spatial import (
    PointIndex,
    PolygonIndex,
    SegmentIndex,
    _segment_distance_m,
)

# Latitudes chosen to span the cos(lat) range the real corpus covers:
# southern Florida through northern Alaska. Longitude scaling shrinks by
# ~3x across this band, which is precisely where a bound that confuses the
# latitude and longitude metres-per-degree factors would break.
LAT_BANDS = [25.0, 40.0, 48.0, 64.0]


def _brute_segment_mi(lat, lon, segments):
    """Exhaustive nearest-segment distance using the index's own projection."""
    cos_lat = math.cos(math.radians(lat))
    m_lon = 111_320.0 * cos_lat
    m_lat = 110_540.0
    px, py = lon * m_lon, lat * m_lat
    best = None
    for (a_lat, a_lon, b_lat, b_lon) in segments:
        d = _segment_distance_m(
            px, py, a_lon * m_lon, a_lat * m_lat, b_lon * m_lon, b_lat * m_lat
        )
        if best is None or d < best:
            best = d
    return None if best is None else best / 1609.344


def _brute_point_mi(lat, lon, points):
    cos_lat = math.cos(math.radians(lat))
    m_lon = 111_320.0 * cos_lat
    m_lat = 110_540.0
    px, py = lon * m_lon, lat * m_lat
    best = None
    for (p_lat, p_lon) in points:
        d = math.hypot(px - p_lon * m_lon, py - p_lat * m_lat)
        if best is None or d < best:
            best = d
    return None if best is None else best / 1609.344


@pytest.mark.parametrize("base_lat", LAT_BANDS)
def test_segment_index_matches_brute_force(base_lat):
    """Nearest-segment search must equal an exhaustive scan at every latitude."""
    rng = random.Random(1234 + int(base_lat))
    segments = []
    idx = SegmentIndex()
    # Mix of short local lines and long cross-cell runs — long polylines are
    # what stress the bbox bucketing.
    for _ in range(300):
        lat0 = base_lat + rng.uniform(-1.5, 1.5)
        lon0 = -100.0 + rng.uniform(-1.5, 1.5)
        span = rng.choice([0.01, 0.05, 0.4, 1.2])
        pts = [[lon0, lat0]]
        for _ in range(rng.randint(1, 5)):
            pts.append([
                pts[-1][0] + rng.uniform(-span, span),
                pts[-1][1] + rng.uniform(-span, span),
            ])
        idx.add_polyline(pts)
        for a, b in zip(pts, pts[1:]):
            segments.append((a[1], a[0], b[1], b[0]))

    worst = 0.0
    for _ in range(400):
        qlat = base_lat + rng.uniform(-2.0, 2.0)
        qlon = -100.0 + rng.uniform(-2.0, 2.0)
        got = idx.nearest_distance_mi(qlat, qlon)
        want = _brute_segment_mi(qlat, qlon, segments)
        assert got is not None and want is not None
        worst = max(worst, abs(got - want))
        assert got == pytest.approx(want, abs=1e-6), (
            f"lat={qlat} lon={qlon}: index={got} brute={want}"
        )
    assert worst < 1e-6


@pytest.mark.parametrize("base_lat", LAT_BANDS)
def test_point_index_matches_brute_force(base_lat):
    """Nearest-point search must equal an exhaustive scan at every latitude."""
    rng = random.Random(99 + int(base_lat))
    pts = []
    idx = PointIndex()
    for _ in range(800):
        lat = base_lat + rng.uniform(-2.0, 2.0)
        lon = -95.0 + rng.uniform(-2.0, 2.0)
        pts.append((lat, lon))
        idx.add_point(lat, lon, attr=None)

    for _ in range(400):
        qlat = base_lat + rng.uniform(-2.5, 2.5)
        qlon = -95.0 + rng.uniform(-2.5, 2.5)
        got = idx.nearest_distance_mi(qlat, qlon)
        want = _brute_point_mi(qlat, qlon, pts)
        assert got == pytest.approx(want, abs=1e-6), (
            f"lat={qlat} lon={qlon}: index={got} brute={want}"
        )


def test_segment_index_sparse_layout_still_finds_far_feature():
    """A single distant line must still be found — this is the ring-budget path.

    Sparse regions (rural Nevada, the Dakotas) are where the early exit does
    the most ring expansion, and where an off-by-one in the budget silently
    turns a real 40-mile distance into a None.
    """
    idx = SegmentIndex()
    idx.add_polyline([[-100.0, 40.0], [-100.0, 40.5]])
    # Query ~53 miles due east.
    got = idx.nearest_distance_mi(40.25, -99.0)
    assert got is not None
    assert 50 < got < 56


def test_segment_index_is_lipschitz_over_random_queries():
    """|d(A) - d(B)| <= dist(A, B): the property the corpus validator asserts.

    Proving it holds for the index means any violation observed in
    `infra-proximity.json` originates upstream of the index — in the source
    snapshot or the join — not in the search.
    """
    rng = random.Random(7)
    idx = SegmentIndex()
    for _ in range(200):
        lat0 = 39.0 + rng.uniform(-1, 1)
        lon0 = -84.0 + rng.uniform(-1, 1)
        idx.add_polyline([
            [lon0, lat0],
            [lon0 + rng.uniform(-0.3, 0.3), lat0 + rng.uniform(-0.3, 0.3)],
        ])
    for _ in range(500):
        lat = 39.0 + rng.uniform(-1, 1)
        lon = -84.0 + rng.uniform(-1, 1)
        # Second query point a short, random hop away.
        dlat = rng.uniform(-0.02, 0.02)
        dlon = rng.uniform(-0.02, 0.02)
        d1 = idx.nearest_distance_mi(lat, lon)
        d2 = idx.nearest_distance_mi(lat + dlat, lon + dlon)
        if d1 is None or d2 is None:
            continue
        # Measure the hop with the index's OWN projection constants — using
        # a different earth model here would make the bound disagree by a
        # few 1e-4 mi and turn a passing property into a phantom failure.
        mi_per_deg_lat = 110_540.0 / 1609.344
        mi_per_deg_lon = 111_320.0 * math.cos(math.radians(lat)) / 1609.344
        sep = math.hypot(dlat * mi_per_deg_lat, dlon * mi_per_deg_lon)
        # d1 and d2 are each computed in a local equirectangular frame
        # anchored at their OWN latitude, so they live in slightly different
        # metrics. The property therefore holds only up to that projection
        # drift — ~0.01% here, well inside the module's documented <1% CONUS
        # accuracy. A real search bug overshoots by miles, not by 0.3 m.
        allowance = sep * 1e-3 + 1e-6
        assert abs(d1 - d2) <= sep + allowance, (
            f"Lipschitz broken: d1={d1} d2={d2} sep={sep}"
        )


def test_polygon_index_containment_matches_brute_force():
    """Point-in-polygon containment must agree with a direct ray cast."""
    rng = random.Random(31)
    idx = PolygonIndex()
    boxes = []
    for i in range(60):
        lat0 = 35.0 + rng.uniform(0, 3)
        lon0 = -90.0 + rng.uniform(0, 3)
        h, w = rng.uniform(0.05, 0.4), rng.uniform(0.05, 0.4)
        ring = [
            [lon0, lat0], [lon0 + w, lat0], [lon0 + w, lat0 + h],
            [lon0, lat0 + h], [lon0, lat0],
        ]
        idx.add_polygon([ring], attr=i)
        boxes.append((lat0, lon0, lat0 + h, lon0 + w, i))

    for _ in range(1500):
        qlat = 35.0 + rng.uniform(-0.2, 3.6)
        qlon = -90.0 + rng.uniform(-0.2, 3.6)
        expected = {
            i for (la, lo, ha, ho, i) in boxes
            if la < qlat < ha and lo < qlon < ho
        }
        got = idx.containing(qlat, qlon)
        if expected:
            assert got in expected, f"({qlat},{qlon}) expected one of {expected}, got {got}"
        else:
            assert got is None, f"({qlat},{qlon}) should be outside, got {got}"
