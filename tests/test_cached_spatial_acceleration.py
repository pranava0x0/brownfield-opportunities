"""Accelerated rebuild must preserve spatial evidence, including Alaska."""
import random
import pytest
from connectors.spatial import SegmentIndex
from scripts.cached_spatial_acceleration import AcceleratedSegmentIndex


def test_acceleration_matches_core_for_sparse_and_dense_geometries():
    rng = random.Random(981)
    core, fast = SegmentIndex(), AcceleratedSegmentIndex()
    paths = []
    for i in range(1000):
        lon, lat = rng.uniform(-156,-145), rng.uniform(59,72)
        path = [[lon,lat],[lon+rng.uniform(-.5,.5),lat+rng.uniform(-.5,.5)]]
        paths.append(path)
        core.add_polyline(path, attr=i)
        fast.add_polyline(path, attr=i)
    for _ in range(100):
        lat, lon = rng.uniform(57,74), rng.uniform(-158,-143)
        a, b = core.nearest_with_attr(lat,lon), fast.nearest_with_attr(lat,lon)
        # Independently scan every source segment; no grid/ring early exit.
        import math
        candidates = []
        for asset_id, (left, right) in enumerate(paths):
            sx, sy = 111320 * math.cos(math.radians(lat)) / 1609.344, 110540 / 1609.344
            x1, y1 = (left[0]-lon)*sx, (left[1]-lat)*sy
            x2, y2 = (right[0]-lon)*sx, (right[1]-lat)*sy
            dx, dy = x2-x1, y2-y1
            denominator = dx*dx+dy*dy
            fraction = min(1, max(0, -(x1*dx+y1*dy)/denominator)) if denominator else 0
            candidates.append((math.hypot(x1+fraction*dx,y1+fraction*dy), asset_id))
        brute = min(candidates)
        if brute[0] <= 100:
            assert b is not None
            assert b[0] == pytest.approx(brute[0],abs=1e-8)
            assert b[1] == brute[1]
        else:
            assert b is None
        if a is None:
            assert b is None
        else:
            assert b[0] == pytest.approx(a[0], abs=1e-8)
            assert b[1] == a[1]


@pytest.mark.parametrize("latitude", [40,60,70])
def test_vectorized_long_segment_and_exact_radius_against_analytic_distance(latitude):
    import math
    idx = AcceleratedSegmentIndex()
    # Long horizontal segment: perpendicular projection is inside endpoints.
    delta_lat = 100 * 1609.344 / 110540
    idx.add_polyline([[-160, latitude + delta_lat],[-140, latitude + delta_lat]])
    hit = idx.nearest_with_attr(latitude,-150,max_rings=100)
    assert hit[0] == pytest.approx(100,abs=1e-8)
    assert idx.nearest_with_attr(latitude-.01,-150) is None


def test_vectorized_antimeridian_and_no_false_world_chord():
    idx = AcceleratedSegmentIndex()
    idx.add_polyline([[179.8,60],[-179.8,60]])
    assert idx.nearest_with_attr(60,180)[0] == pytest.approx(0,abs=1e-8)
    assert idx.nearest_with_attr(60,0) is None
