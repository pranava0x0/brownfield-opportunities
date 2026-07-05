from __future__ import annotations

from collections import defaultdict

from scripts.build_retired_industrial import _nearest_tracked_record, _tracked_bucket


def test_nearest_tracked_record_uses_neighboring_spatial_cells() -> None:
    """The indexed lookup must find a near record across a cell boundary and
    reject unrelated records beyond the one-mile screening radius."""
    site = {"lat": 40.0199, "lon": -75.0}
    records = [
        (40.0201, -75.0, "NEAR", "Nearby record", "brownfield"),
        (40.05, -75.0, "FAR", "Unrelated record", "brownfield"),
    ]
    buckets = defaultdict(list)
    for record in records:
        buckets[_tracked_bucket(record[0], record[1])].append(record)

    hit = _nearest_tracked_record(site, buckets)

    assert hit is not None
    assert hit[1:] == ("NEAR", "Nearby record", "brownfield")
    assert hit[0] < 0.1


def test_nearest_tracked_record_returns_none_outside_radius() -> None:
    site = {"lat": 40.0, "lon": -75.0}
    record = (40.03, -75.0, "FAR", "Unrelated record", "fuds")
    buckets = {_tracked_bucket(record[0], record[1]): [record]}

    assert _nearest_tracked_record(site, buckets) is None
