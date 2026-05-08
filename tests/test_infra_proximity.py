"""Unit tests for the universal infrastructure-proximity enrichment.

Covers:
- _load_sites iterates per-program JSON files
- _build_index ingests ESRI polyline features (via mocked http_get_json)
- fetch_records emits one enriched record per site, omits sites with no
  layer hit and out-of-range distances, drops sites with bad coords
- run_order ordering puts the connector last in --all
- schema accepts the new distance fields without `extra=forbid` complaint
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import connectors as connectors_pkg
from connectors.infra_proximity import (
    DISTANCE_FIELD,
    LAYERS,
    MAX_DISTANCE_MI,
    InfraProximity,
)
from schema import Payload, SiteRecord


# --- helpers ---

def _write_program_file(dir_path: Path, fname: str, sites: list[dict]) -> None:
    """Mimic refresh.py's per-source JSON output."""
    payload = {
        "generated_at": "2026-05-04T00:00:00Z",
        "source": "test",
        "source_url": "test://",
        "count": len(sites),
        "sites": sites,
    }
    (dir_path / fname).write_text(json.dumps(payload))


def _polyline_feature(coords: list[list[float]]) -> dict:
    """ESRI polyline feature shape."""
    return {"attributes": {}, "geometry": {"paths": [coords]}}


def _make_args(**overrides):
    """argparse.Namespace with the per-layer skip flags defaulted off."""
    base = {"limit": None}
    for layer in LAYERS:
        base[f"infra_skip_{layer}"] = False
    base.update(overrides)
    return argparse.Namespace(**base)


# --- run_order / wiring ---

def test_run_order_after_all_producers():
    """Connector runs after every producer connector in --all mode.

    Producers stay at the default run_order=100; enrichment connectors
    bump higher so they see the per-program JSON files. infra-proximity
    must sort strictly after every default-100 producer.
    """
    infra_order = connectors_pkg.get("infra-proximity").run_order
    for slug in connectors_pkg.names():
        cls = connectors_pkg.get(slug)
        if cls.run_order == 100:  # producer tier
            assert infra_order > cls.run_order, f"infra-proximity must run after producer {slug}"


def test_run_order_after_superfund_npl():
    """Specifically must run after superfund-npl (we read its JSON)."""
    npl_order = connectors_pkg.get("superfund-npl").run_order
    infra_order = connectors_pkg.get("infra-proximity").run_order
    assert infra_order > npl_order


def test_registered_in_registry():
    assert "infra-proximity" in connectors_pkg.names()
    assert connectors_pkg.get("infra-proximity") is InfraProximity


def test_distance_field_per_layer():
    # Sanity: every LAYERS key has a corresponding DISTANCE_FIELD entry.
    assert set(DISTANCE_FIELD) == set(LAYERS)


# --- _load_sites ---

def test_load_sites_iterates_program_files(tmp_path, monkeypatch):
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    _write_program_file(tmp_path, "epa-acres.json", [
        {"id": "ACRES-1", "program": "brownfield", "lat": 40.5, "lon": -74.5},
        {"id": "ACRES-2", "program": "brownfield", "lat": 41.0, "lon": -75.0},
    ])
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    sites = list(inst._load_sites())
    assert len(sites) == 3
    assert {s["id"] for s in sites} == {"S1", "ACRES-1", "ACRES-2"}
    assert inst._loaded_program_count == 2


def test_load_sites_skips_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    # Only one file present.
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    sites = list(inst._load_sites())
    assert len(sites) == 1
    assert inst._loaded_program_count == 1


def test_load_sites_handles_corrupt_json(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    (tmp_path / "epa-acres.json").write_text("{not json")
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    sites = list(inst._load_sites())
    # Corrupt file logged + skipped, valid file's sites still come through.
    assert len(sites) == 1


def test_load_sites_empty_when_no_files(tmp_path, monkeypatch):
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    sites = list(inst._load_sites())
    assert sites == []
    assert inst._loaded_program_count == 0


# --- _build_index (with mocked HTTP) ---

def test_build_index_mocked_pagination(tmp_path):
    """Mock http_get_json to return one page of features then an empty page."""
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    pages = [
        {"features": [
            _polyline_feature([[-74.0, 40.0], [-74.0, 41.0]]),
            _polyline_feature([[-75.0, 40.5], [-76.0, 40.5]]),
        ]},
        {"features": []},
    ]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        cfg = LAYERS["transmission"]
        idx = inst._build_index("transmission", cfg, use_cache=True)
    # 2 polylines × 1 segment each = 2 segments.
    assert idx.segment_count == 2


def test_build_index_handles_polyline_with_multiple_paths(tmp_path):
    """ESRI polyline features can have multiple paths; index every one."""
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    feat = {
        "attributes": {},
        "geometry": {"paths": [
            [[-74.0, 40.0], [-74.0, 41.0]],
            [[-75.0, 40.0], [-75.0, 41.0]],
        ]},
    }
    pages = [{"features": [feat]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        idx = inst._build_index("rail", LAYERS["rail"], use_cache=True)
    assert idx.segment_count == 2  # one segment per path


# --- fetch_records integration ---

def test_fetch_records_emits_distance_per_layer(tmp_path, monkeypatch):
    """End-to-end: mock layers, write program files, verify enrichment shape."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    _write_program_file(tmp_path, "epa-acres.json", [
        {"id": "ACRES-1", "program": "brownfield", "lat": 40.5, "lon": -74.5},
    ])
    # Fake transmission line ~0.01° east of S1 → very close.
    pages_by_layer = {
        "transmission": [{"features": [_polyline_feature([[-74.0, 40.0], [-74.01, 40.01]])]}, {"features": []}],
        "highway":      [{"features": [_polyline_feature([[-74.0, 40.5], [-74.01, 40.51]])]}, {"features": []}],
        "rail":         [{"features": [_polyline_feature([[-74.5, 40.5], [-74.51, 40.51]])]}, {"features": []}],
    }
    call_count = {"transmission": 0, "highway": 0, "rail": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        layer = (cache_key or {}).get("layer")
        result = pages_by_layer[layer][call_count[layer]]
        call_count[layer] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args()
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    by_id = {r["id"]: r for r in records}
    assert "S1" in by_id
    assert by_id["S1"]["program"] == "superfund"
    # All three distance fields present (close to all three test layers).
    assert "transmission_mi" in by_id["S1"]
    assert "highway_mi" in by_id["S1"]
    assert "rail_mi" in by_id["S1"]


def test_fetch_records_skips_sites_with_bad_coords(tmp_path, monkeypatch):
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "GOOD", "program": "superfund", "lat": 40.0, "lon": -74.0},
        {"id": "BAD-NULL", "program": "superfund", "lat": None, "lon": None},
        {"id": "BAD-STR", "program": "superfund", "lat": "not a number", "lon": "?"},
    ])
    pages = [{"features": [_polyline_feature([[-74.0, 40.0], [-74.01, 40.01]])]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        if (cache_key or {}).get("layer") != "transmission":
            return {"features": []}
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True)
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    ids = {r["id"] for r in records}
    assert ids == {"GOOD"}


def test_fetch_records_emits_tombstone_when_no_layer_hit(tmp_path, monkeypatch):
    """When every layer is >MAX_DISTANCE_MI away (or returns None), still
    emit a `{id, program}` tombstone record so the cross-program join file
    reflects every site we tried to enrich. Pre-2026-05 the record was
    silently dropped, hiding ~540 off-grid AK / Pacific sites — the gap
    looked like "enrichment never ran" rather than "no infra in reach."
    """
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "REMOTE", "program": "superfund", "lat": 65.0, "lon": -160.0},
    ])
    # Layer features are in CONUS — query in Alaska, no segment within 100 mi.
    pages = [{"features": [_polyline_feature([[-100.0, 40.0], [-99.0, 40.0]])]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        if (cache_key or {}).get("layer") != "transmission":
            return {"features": []}
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True)
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    assert len(records) == 1
    rec = records[0]
    assert rec["id"] == "REMOTE"
    assert rec["program"] == "superfund"
    # No distance fields — tombstone record only.
    assert "transmission_mi" not in rec
    assert "highway_mi" not in rec
    assert "rail_mi" not in rec


def test_fetch_records_aborts_when_no_files_loaded(tmp_path, monkeypatch, caplog):
    """If no per-program JSON files exist, return empty + log error."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    with caplog.at_level("ERROR"):
        records = inst.fetch_records(_make_args(), use_cache=True)
    assert records == []
    assert any("no per-program JSON files found" in r.message for r in caplog.records)


def test_fetch_records_skip_layer_flags_honored(tmp_path, monkeypatch):
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    # Mock transmission only — highway and rail skipped.
    pages = [{"features": [_polyline_feature([[-74.0, 40.0], [-74.01, 40.01]])]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        if (cache_key or {}).get("layer") != "transmission":
            pytest.fail("skipped layer was queried")
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True)
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    assert len(records) == 1
    rec = records[0]
    assert "transmission_mi" in rec
    assert "highway_mi" not in rec
    assert "rail_mi" not in rec


def test_fetch_records_drops_distance_over_max(tmp_path, monkeypatch):
    """A segment beyond MAX_DISTANCE_MI is dropped from the field set, but
    the record itself is still emitted as a tombstone (id + program only)."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    # 2° of latitude ≈ 138 mi (>100 mi). Tx feature far north of the site.
    pages = [{"features": [_polyline_feature([[-74.0, 42.0], [-74.0, 42.1]])]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        if (cache_key or {}).get("layer") != "transmission":
            return {"features": []}
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True)
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    # Distance > MAX_DISTANCE_MI → field absent, but tombstone record present.
    assert len(records) == 1
    assert records[0]["id"] == "S1"
    assert "transmission_mi" not in records[0]


def test_fetch_records_emits_partial_when_some_layers_in_range(tmp_path, monkeypatch):
    """Site within range of one layer + out-of-range for the others: emit
    the record with that one field, no field for the rest. (No tombstone-vs-
    real-data ambiguity — partial records were already emitted pre-2026-05;
    this just locks in the contract alongside the tombstone change.)"""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    # Transmission close, highway + rail far away.
    pages_by_layer = {
        "transmission": [{"features": [_polyline_feature([[-74.0, 40.0], [-74.01, 40.01]])]}, {"features": []}],
        "highway":      [{"features": [_polyline_feature([[-74.0, 42.0], [-74.0, 42.1]])]}, {"features": []}],
        "rail":         [{"features": [_polyline_feature([[-74.0, 42.0], [-74.0, 42.1]])]}, {"features": []}],
    }
    call_count = {"transmission": 0, "highway": 0, "rail": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        layer = (cache_key or {}).get("layer")
        result = pages_by_layer[layer][call_count[layer]]
        call_count[layer] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(_make_args(), use_cache=True)
    assert len(records) == 1
    rec = records[0]
    assert "transmission_mi" in rec
    assert "highway_mi" not in rec
    assert "rail_mi" not in rec


# --- schema integration ---

def test_schema_accepts_distance_fields():
    rec = SiteRecord(
        id="S1",
        program="superfund",
        transmission_mi=2.3,
        rail_mi=1.1,
        highway_mi=0.5,
    )
    assert rec.transmission_mi == 2.3
    assert rec.rail_mi == 1.1
    assert rec.highway_mi == 0.5


def test_schema_accepts_transmission_kv():
    """`transmission_kv` joined alongside the distance — drives the DC
    scoring tiers (≥230 kV for hyperscale)."""
    rec = SiteRecord(
        id="S1",
        program="superfund",
        transmission_mi=0.4,
        transmission_kv=230.0,
    )
    assert rec.transmission_kv == 230.0


def test_extract_attr_voltage_field_takes_precedence():
    """When VOLTAGE is populated, return it directly."""
    from connectors.infra_proximity import InfraProximity
    kv = InfraProximity._extract_attr("transmission", {"VOLTAGE": 230.0, "VOLT_CLASS": "100-161"})
    assert kv == 230.0


def test_extract_attr_falls_back_to_volt_class():
    """When VOLTAGE is HIFLD's null sentinel, map VOLT_CLASS to a kV
    floor so the ≥230 kV filter is conservatively strict."""
    from connectors.infra_proximity import InfraProximity
    kv = InfraProximity._extract_attr("transmission", {"VOLTAGE": -999999, "VOLT_CLASS": "345"})
    assert kv == 345.0


def test_extract_attr_returns_none_when_both_missing():
    from connectors.infra_proximity import InfraProximity
    assert InfraProximity._extract_attr("transmission", {}) is None
    # Unknown VOLT_CLASS string also returns None — don't make up a kV.
    assert InfraProximity._extract_attr("transmission", {"VOLT_CLASS": "MYSTERY"}) is None


def test_extract_attr_returns_none_for_non_transmission_layers():
    """Rail and highway layers don't carry kV — return None unconditionally
    so we don't accidentally write a `transmission_kv` for them."""
    from connectors.infra_proximity import InfraProximity
    assert InfraProximity._extract_attr("rail", {"VOLTAGE": 230}) is None
    assert InfraProximity._extract_attr("highway", {"VOLTAGE": 230}) is None


def test_fetch_records_emits_transmission_kv(tmp_path, monkeypatch):
    """End-to-end: a transmission feature with VOLTAGE=230 attaches that
    voltage to its segments; the nearest-segment query returns it as
    `transmission_kv` on the enriched record."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    feat = {
        "attributes": {"VOLTAGE": 230.0, "VOLT_CLASS": "220-287"},
        "geometry": {"paths": [[[-74.0, 40.0], [-74.01, 40.01]]]},
    }
    pages = [{"features": [feat]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        if (cache_key or {}).get("layer") != "transmission":
            return {"features": []}
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True)
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    assert len(records) == 1
    rec = records[0]
    assert rec["id"] == "S1"
    assert "transmission_kv" in rec
    assert rec["transmission_kv"] == 230.0


def test_fetch_records_omits_transmission_kv_when_voltage_null(tmp_path, monkeypatch):
    """A line with no VOLTAGE / no VOLT_CLASS still produces a distance
    field but `transmission_kv` is absent — the frontend treats it as
    "voltage unknown, scoring caps at edge tier."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    feat = {
        "attributes": {"VOLTAGE": -999999, "VOLT_CLASS": ""},
        "geometry": {"paths": [[[-74.0, 40.0], [-74.01, 40.01]]]},
    }
    pages = [{"features": [feat]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        if (cache_key or {}).get("layer") != "transmission":
            return {"features": []}
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True)
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    assert len(records) == 1
    rec = records[0]
    assert "transmission_mi" in rec
    assert "transmission_kv" not in rec


def test_cache_key_includes_out_fields():
    """Bumping `out_fields` invalidates the v1.10 transmission cache so
    we re-fetch with VOLTAGE / VOLT_CLASS instead of silently shadowing
    with a geometry-only response."""
    from connectors.infra_proximity import LAYERS
    assert LAYERS["transmission"]["out_fields"] == "VOLTAGE,VOLT_CLASS"
    # Rail and highway intentionally stay attribute-free.
    assert LAYERS["rail"]["out_fields"] == ""
    assert LAYERS["highway"]["out_fields"] == ""


def test_schema_distance_fields_excluded_when_none():
    rec = SiteRecord(id="S1", program="superfund")
    dumped = rec.model_dump(exclude_none=True)
    for f in ("transmission_mi", "rail_mi", "highway_mi"):
        assert f not in dumped


def test_payload_with_infra_records_validates():
    payload = Payload(
        generated_at="2026-05-04T00:00:00Z",
        source="test",
        source_url="test://",
        count=2,
        sites=[
            {"id": "S1", "program": "superfund", "transmission_mi": 1.0, "highway_mi": 5.5},
            {"id": "ACRES-1", "program": "brownfield", "rail_mi": 0.7},
        ],
    )
    assert payload.count == 2
    # Confirm fields round-tripped.
    assert payload.sites[0].transmission_mi == 1.0
    assert payload.sites[1].rail_mi == 0.7
