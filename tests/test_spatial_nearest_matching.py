"""SegmentIndex.nearest_matching agrees with a brute-force scan over the
segments that satisfy the predicate."""
import random

from connectors.infra_proximity import line_threshold_fields
from connectors.spatial import SegmentIndex


def _index(seed: int):
    rng = random.Random(seed)
    idx = SegmentIndex()
    lines = []
    for _ in range(300):
        lat, lon = rng.uniform(30, 45), rng.uniform(-100, -80)
        path = [[lon, lat], [lon + rng.uniform(-0.3, 0.3), lat + rng.uniform(-0.3, 0.3)]]
        kv = rng.choice([None, 34.5, 69, 115, 138, 230, 345, 500])
        idx.add_polyline(path, attr={"kv": kv})
        lines.append((path, kv))
    return idx, lines


def _brute(lines, lat, lon, test):
    best = None
    for path, kv in lines:
        if not test(kv):
            continue
        one = SegmentIndex()
        one.add_polyline(path)
        d = one.nearest_distance_mi(lat, lon, max_rings=10_000)
        if d is not None and (best is None or d < best):
            best = d
    return best


def test_nearest_matching_matches_brute_force():
    idx, lines = _index(7)
    rng = random.Random(1)
    for _ in range(40):
        lat, lon = rng.uniform(31, 44), rng.uniform(-99, -81)
        hit = idx.nearest_matching(lat, lon, lambda a: a["kv"] is not None and a["kv"] >= 230)
        want = _brute(lines, lat, lon, lambda kv: kv is not None and kv >= 230)
        assert hit is not None and abs(hit[0] - want) < 1e-6 * max(1.0, want)
        assert hit[1]["kv"] >= 230


def test_threshold_distance_is_never_nearer_than_the_nearest_line():
    idx, _ = _index(3)
    lat, lon = 37.5, -90.0
    nearest = idx.nearest_with_attr(lat, lon)[0]
    fields = line_threshold_fields(idx, lat, lon)
    assert fields["transmission_69kv_mi"] <= fields["transmission_115kv_mi"] <= fields["transmission_230kv_mi"]
    assert all(v >= round(nearest, 1) for v in fields.values())


def test_low_voltage_nearest_line_does_not_hide_a_qualifying_one():
    idx = SegmentIndex()
    idx.add_polyline([[-90.0, 40.01], [-89.9, 40.01]], attr={"kv": 69})   # ~0.7 mi
    idx.add_polyline([[-90.0, 40.04], [-89.9, 40.04]], attr={"kv": 345})  # ~2.8 mi
    fields = line_threshold_fields(idx, 40.0, -89.95)
    assert fields["transmission_69kv_mi"] < 1 and 2 < fields["transmission_230kv_mi"] < 3
    assert "transmission_unknown_kv_mi" not in fields
