"""Pure helpers of scripts/audit_tabs.py. The network checks are exercised by running the script."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import audit_tabs as at  # noqa: E402

RDB = "\n".join(["# comment", "agency_cd\tsite_no\tyear_nu\tmean_va", "5s\t15s\t4s\t12n",
                 "USGS\t0001\t2001\t100", "USGS\t0001\t2002\t200", "USGS\t0001\t2003\t300"])


def test_rdb_mean_averages_the_annual_means():
    assert at._parse_rdb_mean(RDB) == 200


def test_rdb_without_discharge_is_none():
    assert at._parse_rdb_mean("# nothing\nagency_cd\tsite_no\n5s\t15s") is None


def test_segment_distance_to_a_parallel_line():
    lat, lon = 40.0, -100.0
    off = 1.0 / (110540 / 1609.344)       # one mile of latitude
    feats = [{"attributes": {}, "geometry": {"paths": [[[lon - 1, lat + off], [lon + 1, lat + off]]]}}]
    assert math.isclose(at._segments_min(lat, lon, feats), 1.0, rel_tol=1e-6)


def test_voltage_filter_ignores_lower_voltage_lines():
    lat, lon = 40.0, -100.0
    near = {"attributes": {"VOLTAGE": 69}, "geometry": {"paths": [[[lon - 1, lat + 0.01], [lon + 1, lat + 0.01]]]}}
    far = {"attributes": {"VOLTAGE": 345}, "geometry": {"paths": [[[lon - 1, lat + 0.05], [lon + 1, lat + 0.05]]]}}
    all_ = at._segments_min(lat, lon, [near, far])
    hv = at._segments_min(lat, lon, [near, far], lambda a: (a.get("VOLTAGE") or -1) >= 230)
    assert hv > all_ * 4


def test_compare_flags_a_difference_beyond_tolerance():
    assert at._compare("c", "x", "f", 0.8, 0.9, 6)["status"] == "OK"
    assert at._compare("c", "x", "f", 0.8, 1.4, 6)["status"] == "MISMATCH"


def test_compare_nothing_in_box_is_ok_only_when_stored_is_beyond_it():
    assert at._compare("c", "x", "f", 12.0, None, 6)["status"] == "OK"
    assert at._compare("c", "x", "f", 2.0, None, 6)["status"] == "MISMATCH"
    assert at._compare("c", "x", "f", None, 3.0, 6)["status"] == "MISMATCH"
