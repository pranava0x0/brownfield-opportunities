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
    """argparse.Namespace with skip flags set up for fast unit tests.

    Polyline layers default to NOT-skipped (tests that want them mock
    `http_get_json`). Point + per-site layers (substation / power_plant /
    flood_zone) default to SKIPPED — they go through different code paths
    and would otherwise hit real Overpass / HIFLD / FEMA endpoints when the
    enclosing test doesn't explicitly mock them.
    """
    base = {"limit": None}
    for layer in LAYERS:
        base[f"infra_skip_{layer}"] = False
    # Default-skip the layers added in v1.13.3 (substation, power_plant,
    # flood_zone) so existing tests don't accidentally trigger network I/O.
    for layer in ("substation", "power_plant", "flood_zone"):
        base[f"infra_skip_{layer}"] = True
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
    # Point layers (substation, power_plant) live outside LAYERS but still
    # carry a `*_mi` field, so DISTANCE_FIELD is a superset of LAYERS.
    assert set(LAYERS).issubset(set(DISTANCE_FIELD))


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
    # Fake polyline ~0.01° east of S1 → very close (≤1 mi).
    pages_by_layer = {
        "transmission": [{"features": [_polyline_feature([[-74.0, 40.0], [-74.01, 40.01]])]}, {"features": []}],
        "highway":      [{"features": [_polyline_feature([[-74.0, 40.5], [-74.01, 40.51]])]}, {"features": []}],
        "rail":         [{"features": [_polyline_feature([[-74.5, 40.5], [-74.51, 40.51]])]}, {"features": []}],
        "gas_pipeline": [{"features": [_polyline_feature([[-74.0, 40.0], [-74.01, 40.01]])]}, {"features": []}],
    }
    call_count = {"transmission": 0, "highway": 0, "rail": 0, "gas_pipeline": 0}
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
    # All four distance fields present (close to all four test layers).
    assert "transmission_mi" in by_id["S1"]
    assert "highway_mi" in by_id["S1"]
    assert "rail_mi" in by_id["S1"]
    assert "gas_pipeline_mi" in by_id["S1"]


def _write_existing_output(dir_path: Path, sites: list[dict]) -> None:
    """Mimic a prior infra-proximity.json on disk (for flood seeding)."""
    payload = {
        "generated_at": "2026-06-01T00:00:00Z",
        "source": "test",
        "source_url": "test://",
        "count": len(sites),
        "sites": sites,
    }
    (dir_path / "infra-proximity.json").write_text(json.dumps(payload))


def test_flood_seed_and_budget(tmp_path, monkeypatch):
    """Resumable flood backfill: prior flood values are seeded (carried
    forward without re-querying), and `--infra-flood-budget` caps NEW fetches
    so a run tops up the cache by N sites then writes the full record set.

    S1 is already populated on disk → seeded verbatim, no query.
    S2 is unpopulated, budget=1 → one fetch happens.
    S3 is unpopulated, budget exhausted → deferred, no flood field.
    All three records are still emitted (no truncation).
    """
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(InfraProximity, "OUTPUT_DIR", tmp_path)
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
        {"id": "S2", "program": "superfund", "lat": 41.0, "lon": -75.0},
        {"id": "S3", "program": "superfund", "lat": 42.0, "lon": -76.0},
    ])
    # Prior output: S1 already has a flood determination.
    _write_existing_output(tmp_path, [
        {"id": "S1", "program": "superfund", "flood_zone": "AE", "in_sfha": True},
        {"id": "S2", "program": "superfund"},  # unpopulated
    ])

    queried: list[tuple[float, float]] = []
    def fake_flood(lat, lon, use_cache):
        queried.append((round(lat, 1), round(lon, 1)))
        return ("X", False)

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    # Only the flood layer is active; budget allows exactly one new fetch.
    args = _make_args(
        infra_skip_transmission=True, infra_skip_highway=True,
        infra_skip_rail=True, infra_skip_gas_pipeline=True,
        infra_skip_flood_zone=False, infra_flood_budget=1,
    )
    with patch.object(inst, "_query_flood_zone", side_effect=fake_flood):
        records = inst.fetch_records(args, use_cache=True)

    by_id = {r["id"]: r for r in records}
    # All three records emitted — no truncation.
    assert set(by_id) == {"S1", "S2", "S3"}
    # S1 seeded verbatim, never queried.
    assert by_id["S1"]["flood_zone"] == "AE"
    assert by_id["S1"]["in_sfha"] is True
    assert (40.0, -74.0) not in queried
    # S2 consumed the one-fetch budget.
    assert by_id["S2"]["flood_zone"] == "X"
    assert (41.0, -75.0) in queried
    # S3 deferred over budget — no flood field, but record still present.
    assert "flood_zone" not in by_id["S3"]
    assert len(queried) == 1


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
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True, infra_skip_gas_pipeline=True)
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
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True, infra_skip_gas_pipeline=True)
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
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True, infra_skip_gas_pipeline=True)
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
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True, infra_skip_gas_pipeline=True)
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
    # Transmission close, highway + rail + gas all far away.
    pages_by_layer = {
        "transmission": [{"features": [_polyline_feature([[-74.0, 40.0], [-74.01, 40.01]])]}, {"features": []}],
        "highway":      [{"features": [_polyline_feature([[-74.0, 42.0], [-74.0, 42.1]])]}, {"features": []}],
        "rail":         [{"features": [_polyline_feature([[-74.0, 42.0], [-74.0, 42.1]])]}, {"features": []}],
        "gas_pipeline": [{"features": [_polyline_feature([[-74.0, 42.0], [-74.0, 42.1]])]}, {"features": []}],
    }
    call_count = {"transmission": 0, "highway": 0, "rail": 0, "gas_pipeline": 0}
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
    assert "gas_pipeline_mi" not in rec


# --- schema integration ---

def test_schema_accepts_distance_fields():
    rec = SiteRecord(
        id="S1",
        program="superfund",
        transmission_mi=2.3,
        rail_mi=1.1,
        highway_mi=0.5,
        gas_pipeline_mi=1.7,
    )
    assert rec.transmission_mi == 2.3
    assert rec.rail_mi == 1.1
    assert rec.highway_mi == 0.5
    assert rec.gas_pipeline_mi == 1.7


def test_gas_pipeline_layer_emits_distance(tmp_path, monkeypatch):
    """v1.13 Tier 1: gas pipeline layer emits gas_pipeline_mi when within
    range, alongside the existing three layers. Same SegmentIndex pattern
    as transmission/rail/highway — separate test guards against future
    refactors that might forget to wire a new layer through `LAYERS`."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    pages = [{"features": [_polyline_feature([[-74.0, 40.0], [-74.01, 40.01]])]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        if (cache_key or {}).get("layer") != "gas_pipeline":
            pytest.fail("non-gas-pipeline layer was queried")
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args(infra_skip_transmission=True, infra_skip_highway=True, infra_skip_rail=True)
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    assert len(records) == 1
    rec = records[0]
    assert "gas_pipeline_mi" in rec
    assert rec["gas_pipeline_mi"] >= 0


def test_gas_pipeline_skip_flag_honored(tmp_path, monkeypatch):
    """`--infra-skip-gas-pipeline` skips the layer cleanly."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    def fake_get(url, params, use_cache, cache_key=None):
        if (cache_key or {}).get("layer") == "gas_pipeline":
            pytest.fail("gas_pipeline was queried despite --infra-skip-gas-pipeline")
        return {"features": []}

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    args = _make_args(
        infra_skip_transmission=True,
        infra_skip_highway=True,
        infra_skip_rail=True,
        infra_skip_gas_pipeline=True,
    )
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    # All four layers skipped → no enrichment built → empty result.
    assert records == []


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
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True, infra_skip_gas_pipeline=True)
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
    args = _make_args(infra_skip_highway=True, infra_skip_rail=True, infra_skip_gas_pipeline=True)
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


# ----- v1.13.3: substation / power-plant / flood-zone layers -----

def test_parse_osm_voltage_handles_typical_inputs():
    from connectors.infra_proximity import _parse_osm_voltage
    assert _parse_osm_voltage("230000") == 230.0
    assert _parse_osm_voltage("115000") == 115.0
    # Multi-value tag: max wins.
    assert _parse_osm_voltage("230000;115000") == 230.0
    assert _parse_osm_voltage("46000;115000;230000") == 230.0


def test_parse_osm_voltage_returns_none_for_blanks():
    from connectors.infra_proximity import _parse_osm_voltage
    for v in (None, "", "  ", "abc", "0", "-100"):
        assert _parse_osm_voltage(v) is None


def test_parse_osm_voltage_skips_unparseable_parts():
    """A `;`-separated multi-value with some garbage parts still returns
    the max of the valid ones."""
    from connectors.infra_proximity import _parse_osm_voltage
    assert _parse_osm_voltage("230000;not_a_number;115000") == 230.0


def test_build_substation_index_attaches_kv_attr(tmp_path, monkeypatch):
    """The substation index must carry the parsed kV in the attr dict so
    `nearest_with_attr()` can surface it on enrichment."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    # Mock the per-bbox fetch to return a single substation with voltage tag.
    monkeypatch.setattr(
        inst, "_fetch_overpass_substations",
        lambda bbox, use_cache: [
            {"type": "way",
             "center": {"lat": 40.0, "lon": -74.0},
             "tags": {"power": "substation", "voltage": "230000"}},
        ],
    )
    idx = inst._build_substation_index(use_cache=True)
    # 7 bboxes × 1 substation each → 7 points all at (40, -74) with kv=230.
    assert idx.point_count == 7
    hit = idx.nearest_with_attr(40.0, -74.0)
    assert hit is not None
    d, attr = hit
    assert d == pytest.approx(0.0, abs=0.001)
    assert attr == {"kv": 230.0}


def test_build_substation_index_skips_missing_geometry(tmp_path, monkeypatch):
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    monkeypatch.setattr(
        inst, "_fetch_overpass_substations",
        lambda bbox, use_cache: [
            {"type": "node", "lat": None, "lon": None, "tags": {}},
            {"type": "way", "center": {}, "tags": {}},
            {"type": "node", "lat": 40.0, "lon": -74.0, "tags": {}},  # valid
        ],
    )
    idx = inst._build_substation_index(use_cache=True)
    # 7 bboxes × 1 valid substation = 7 indexed points.
    assert idx.point_count == 7


def test_build_power_plant_index_carries_mw_and_fuel(tmp_path):
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    pages = [
        {"features": [
            {"attributes": {"Plant_Name": "Test Gas", "Total_MW": 450.5,
                            "PrimSource": "natural gas"},
             "geometry": {"x": -74.0, "y": 40.0}},
            {"attributes": {"Plant_Name": "Test Solar", "Total_MW": 12.3,
                            "PrimSource": "solar"},
             "geometry": {"x": -75.0, "y": 41.0}},
        ]},
        {"features": []},
    ]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        idx = inst._build_power_plant_index(use_cache=True)
    assert idx.point_count == 2
    hit = idx.nearest_with_attr(40.0, -74.0)
    assert hit is not None
    _, attr = hit
    assert attr["mw"] == 450.5
    assert attr["fuel"] == "natural gas"
    assert attr["name"] == "Test Gas"
    # HIFLD Power_Plants_in_the_US only contains active generators — it has no
    # Status field. The attr dict carries `status: None` as a placeholder;
    # the eia-retired-plants enrichment connector will overwrite it via a
    # separate join against EIA-860 Form 3_3 retired generators.
    assert attr["status"] is None


def _mock_load_sites(inst, sites):
    """Return a callable that mimics _load_sites AND sets _loaded_program_count."""
    def _loader():
        inst._loaded_program_count = 1
        return iter(sites)
    return _loader


def test_power_plant_retired_absent_from_infra_proximity(tmp_path, monkeypatch):
    """HIFLD Power_Plants_in_the_US only includes ACTIVE generators and has
    no Status field. infra_proximity therefore never emits power_plant_retired
    — it is always absent from records, not False. The field will be populated
    by the future eia-retired-plants enrichment connector (EIA-860 Form 3_3)
    via a separate join."""
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    sites = [{"id": "S1", "program": "superfund", "lat": 40.0, "lon": -83.0}]
    monkeypatch.setattr(inst, "_load_sites", _mock_load_sites(inst, sites))

    def fake_get(url, params, use_cache, cache_key=None):
        key = cache_key or {}
        if key.get("src") == "power_plants":
            if key.get("offset", 0) == 0:
                return {"features": [
                    {"attributes": {"Plant_Name": "Gas Plant", "Total_MW": 600.0,
                                    "PrimSource": "natural gas"},
                     "geometry": {"x": -83.001, "y": 40.001}},
                ]}
            return {"features": []}
        return {"features": []}

    monkeypatch.setattr(inst, "_fetch_overpass_substations", lambda bbox, use_cache: [])
    args = _make_args(
        infra_skip_substation=True, infra_skip_power_plant=False,
        infra_skip_flood_zone=True,
        infra_skip_highway=True, infra_skip_rail=True,
        infra_skip_gas_pipeline=True, infra_skip_transmission=True,
    )
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    assert len(records) == 1
    r = records[0]
    assert "power_plant_mi" in r       # normal distance field still emitted
    assert "power_plant_mw" in r
    assert "power_plant_fuel" in r
    assert "power_plant_retired" not in r  # never populated from HIFLD


def test_build_power_plant_index_skips_missing_geometry(tmp_path):
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    pages = [
        {"features": [
            {"attributes": {}, "geometry": {}},  # no x/y
            {"attributes": {"Total_MW": 10, "PrimSource": "wind"},
             "geometry": {"x": -74.0, "y": 40.0}},
        ]},
        {"features": []},
    ]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        idx = inst._build_power_plant_index(use_cache=True)
    assert idx.point_count == 1


def test_query_flood_zone_parses_sfha_true(tmp_path):
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    fake_response = {"features": [
        {"attributes": {"FLD_ZONE": "AE", "SFHA_TF": "T", "ZONE_SUBTY": ""}},
    ]}
    with patch.object(inst, "http_get_json", return_value=fake_response):
        zone, sfha = inst._query_flood_zone(40.0, -74.0, use_cache=True)
    assert zone == "AE"
    assert sfha is True


def test_query_flood_zone_parses_sfha_false():
    inst = InfraProximity(cache_dir=Path("/tmp/test_cache_unused"))
    fake_response = {"features": [
        {"attributes": {"FLD_ZONE": "X", "SFHA_TF": "F"}},
    ]}
    with patch.object(inst, "http_get_json", return_value=fake_response):
        zone, sfha = inst._query_flood_zone(40.0, -74.0, use_cache=True)
    assert zone == "X"
    assert sfha is False


def test_query_flood_zone_returns_none_when_no_features():
    """Outside any mapped flood-study area, FEMA returns empty features."""
    inst = InfraProximity(cache_dir=Path("/tmp/test_cache_unused"))
    with patch.object(inst, "http_get_json", return_value={"features": []}):
        zone, sfha = inst._query_flood_zone(40.0, -74.0, use_cache=True)
    assert zone is None
    assert sfha is None


def test_query_flood_zone_handles_missing_sfha_tf():
    """SFHA_TF can be missing on some FEMA polygons — `in_sfha` must
    fall back to None rather than raising."""
    inst = InfraProximity(cache_dir=Path("/tmp/test_cache_unused"))
    fake_response = {"features": [
        {"attributes": {"FLD_ZONE": "D"}},  # no SFHA_TF
    ]}
    with patch.object(inst, "http_get_json", return_value=fake_response):
        zone, sfha = inst._query_flood_zone(40.0, -74.0, use_cache=True)
    assert zone == "D"
    assert sfha is None


def test_query_flood_zone_skips_empty_zone_features():
    """If FEMA returns a feature with FLD_ZONE blank, treat as no signal."""
    inst = InfraProximity(cache_dir=Path("/tmp/test_cache_unused"))
    fake_response = {"features": [
        {"attributes": {"FLD_ZONE": "", "SFHA_TF": "F"}},
    ]}
    with patch.object(inst, "http_get_json", return_value=fake_response):
        zone, sfha = inst._query_flood_zone(40.0, -74.0, use_cache=True)
    assert zone is None
    assert sfha is None


def test_fetch_records_emits_new_fields_when_enabled(tmp_path, monkeypatch):
    """End-to-end: with substation + power_plant + flood_zone enabled, the
    enriched record carries all the new fields."""
    monkeypatch.setattr(InfraProximity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.0, "lon": -74.0},
    ])
    inst = InfraProximity(cache_dir=tmp_path / "cache")
    # Mock the polyline pages (transmission only — keep the others skipped).
    pages = [
        {"features": [_polyline_feature([[-74.0, 40.0], [-74.001, 40.001]])]},
        {"features": []},
    ]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        # Power plant fetch and flood lookup both go through http_get_json.
        key = cache_key or {}
        if key.get("src") == "power_plants":
            return {"features": [
                {"attributes": {"Plant_Name": "Test Plant", "Total_MW": 100.0,
                                "PrimSource": "natural gas"},
                 "geometry": {"x": -74.0, "y": 40.001}},
                {"features": []},
            ]} if key.get("offset", 0) == 0 else {"features": []}
        if key.get("src") == "fema_flood":
            return {"features": [{"attributes": {"FLD_ZONE": "X", "SFHA_TF": "F"}}]}
        # Polyline transmission fetch.
        if key.get("layer") == "transmission":
            result = pages[call_count["n"]]
            call_count["n"] += 1
            return result
        return {"features": []}
    # Mock the Overpass substation fetcher directly.
    monkeypatch.setattr(
        inst, "_fetch_overpass_substations",
        lambda bbox, use_cache: [
            {"type": "node", "lat": 40.001, "lon": -74.001,
             "tags": {"voltage": "230000"}},
        ],
    )
    args = _make_args(
        infra_skip_substation=False, infra_skip_power_plant=False,
        infra_skip_flood_zone=False,
        infra_skip_highway=True, infra_skip_rail=True, infra_skip_gas_pipeline=True,
    )
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(args, use_cache=True)
    assert len(records) == 1
    r = records[0]
    assert "transmission_mi" in r
    assert "substation_mi" in r
    assert r["substation_kv"] == 230.0
    assert "power_plant_mi" in r
    assert r["power_plant_mw"] == 100.0
    assert r["power_plant_fuel"] == "natural gas"
    assert r["flood_zone"] == "X"
    assert r["in_sfha"] is False


def test_schema_accepts_new_v13_3_fields():
    """New v1.13.3+ fields must round-trip through SiteRecord + Payload."""
    rec = SiteRecord(
        id="S1", program="superfund",
        substation_mi=0.7, substation_kv=230.0,
        power_plant_mi=2.5, power_plant_mw=450.0, power_plant_fuel="natural gas",
        power_plant_retired=True,
        flood_zone="X", in_sfha=False,
    )
    dumped = rec.model_dump(exclude_none=True)
    assert dumped["substation_mi"] == 0.7
    assert dumped["substation_kv"] == 230.0
    assert dumped["power_plant_retired"] is True
    assert dumped["power_plant_fuel"] == "natural gas"
    assert dumped["flood_zone"] == "X"
    assert dumped["in_sfha"] is False


def test_schema_new_fields_excluded_when_none():
    rec = SiteRecord(id="S1", program="superfund")
    dumped = rec.model_dump(exclude_none=True)
    for f in ("substation_mi", "substation_kv", "power_plant_mi",
              "power_plant_mw", "power_plant_fuel", "flood_zone", "in_sfha"):
        assert f not in dumped
