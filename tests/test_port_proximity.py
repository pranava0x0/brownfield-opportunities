"""Tests for connectors/port_proximity.py.

Verifies that the port-proximity connector:
  - Emits the correct per-site port fields for a port within MAX_DISTANCE_MI_PORT
  - Emits the correct per-site shipyard fields for a yard within MAX_DISTANCE_MI_SHIPYARD
  - Uses the TOMBSTONE convention — every site with coordinates gets a
    {id, program} record even when nothing is within range (unlike
    planned_retirements, which omits unmatched sites)
  - Tolerates both the {"sites": [...]} envelope and a bare list overlay
  - Respects --missing-only merging
  - Skips sites with missing/invalid coordinates
  - Continues (with a warning, not a crash) when the shipyard overlay is empty

All tests use synthetic in-memory overlays — no network, no real data.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import pytest

from connectors.port_proximity import (
    PortProximity,
    MAX_DISTANCE_MI_PORT,
    MAX_DISTANCE_MI_SHIPYARD,
    PORTS_FILE,
    SHIPYARDS_FILE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _port(name, lat, lon, port_type="Coastal", hurricane_freq=0.1) -> dict:
    return {
        "name": name, "port_type": port_type, "lat": lat, "lon": lon,
        "hurricane_freq": hurricane_freq,
        "source_url": "https://www.bts.gov/ntad", "verified_at": "2026-08-27",
    }


def _yard(name, lat, lon, capability="heavy_module") -> dict:
    return {
        "id": name.lower().replace(" ", "-"), "name": name,
        "operator": "Test Operator", "city": "Testville", "state": "TX",
        "lat": lat, "lon": lon, "coord_note": "test",
        "capability": capability,
        "source_url": "https://example.com", "verified_at": "2026-08-27",
    }


def _make_connector(tmp_path: pathlib.Path, ports, yards, *, envelope=True) -> PortProximity:
    """Build a connector whose _data_dir points at tmp_path holding
    synthetic ports.json / shipyards.json overlays."""
    data_dir = tmp_path / "docs" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    ports_body = {"sites": ports} if envelope else ports
    yards_body = {"sites": yards} if envelope else yards
    (data_dir / PORTS_FILE).write_text(json.dumps(ports_body))
    (data_dir / SHIPYARDS_FILE).write_text(json.dumps(yards_body))
    conn = PortProximity(cache_dir=tmp_path / "cache")
    conn._data_dir = lambda: data_dir  # shadow the staticmethod
    conn.OUTPUT_DIR = data_dir
    return conn


def _stub_load_sites(conn, sites):
    def _loader():
        conn._loaded_program_count = 1
        return iter(sites)
    conn._load_sites = _loader


def _args(missing_only=False, limit=None):
    return argparse.Namespace(missing_only=missing_only, limit=limit)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_port_and_shipyard_both_emit_fields(tmp_path):
    """A site near both a qualifying port and a qualifying shipyard gets
    every field from both joins in one record."""
    conn = _make_connector(
        tmp_path,
        [_port("Corpus Christi, TX", 27.85, -97.40, "Coastal", 0.2)],
        [_yard("Kiewit Offshore Services", 27.850, -97.208, "heavy_module")],
    )
    _stub_load_sites(conn, [
        {"id": "SF-1", "program": "superfund", "lat": 27.83, "lon": -97.40},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert len(records) == 1
    r = records[0]
    assert r["id"] == "SF-1"
    assert r["program"] == "superfund"
    assert r["port_mi"] < 5
    assert r["port_name"] == "Corpus Christi, TX"
    assert r["port_type"] == "Coastal"
    assert r["port_hurricane_freq"] == pytest.approx(0.2)
    assert r["shipyard_mi"] < 20
    assert r["shipyard_name"] == "Kiewit Offshore Services"
    assert r["shipyard_capability"] == "heavy_module"


def test_tombstone_emitted_when_nothing_in_range(tmp_path):
    """Unlike planned_retirements, EVERY site with coordinates gets a record
    — the tombstone convention (v1.11.5 infra-proximity lesson) so a null
    port_mi means 'checked, nothing nearby', not 'never checked'."""
    conn = _make_connector(
        tmp_path,
        [_port("Far Port", 45.0, -70.0)],  # nowhere near the site below
        [_yard("Far Yard", 45.0, -70.0)],
    )
    _stub_load_sites(conn, [
        {"id": "SF-LANDLOCKED", "program": "superfund", "lat": 39.0, "lon": -105.0},  # Denver, CO
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert len(records) == 1
    r = records[0]
    assert r["id"] == "SF-LANDLOCKED"
    assert r["program"] == "superfund"
    assert "port_mi" not in r
    assert "shipyard_mi" not in r


def test_port_beyond_max_distance_not_recorded(tmp_path):
    """A port farther than MAX_DISTANCE_MI_PORT does not populate port_mi,
    but the tombstone record still emits."""
    # ~1 degree lat ≈ 69 mi, well past MAX_DISTANCE_MI_PORT (75).
    far_lat = 40.0 + (MAX_DISTANCE_MI_PORT + 20) / 69.0
    conn = _make_connector(
        tmp_path, [_port("Too Far", far_lat, -82.0)], [],
    )
    _stub_load_sites(conn, [
        {"id": "SF-2", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert len(records) == 1
    assert "port_mi" not in records[0]


def test_shipyard_beyond_max_distance_not_recorded(tmp_path):
    # Isolate the control: a valid nearby port keeps the port index non-empty
    # (which would otherwise abort the run) without perturbing the shipyard
    # distance under test.
    far_lat = 40.0 + (MAX_DISTANCE_MI_SHIPYARD + 20) / 69.0
    conn = _make_connector(
        tmp_path, [_port("Nearby Port", 40.01, -82.0)],
        [_yard("Too Far Yard", far_lat, -82.0)],
    )
    _stub_load_sites(conn, [
        {"id": "SF-3", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert len(records) == 1
    assert "shipyard_mi" not in records[0]


def test_empty_shipyard_overlay_still_produces_port_join(tmp_path):
    """An empty shipyard overlay logs a warning and continues — the run
    isn't aborted just because scripts/build_shipyards.py hasn't been run."""
    conn = _make_connector(
        tmp_path, [_port("Nearby Port", 40.01, -82.0)], [],
    )
    _stub_load_sites(conn, [
        {"id": "SF-4", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert len(records) == 1
    assert records[0]["port_mi"] is not None
    assert "shipyard_mi" not in records[0]


def test_bare_list_overlay_tolerated(tmp_path):
    conn = _make_connector(
        tmp_path,
        [_port("P", 40.01, -82.0)], [_yard("Y", 40.01, -82.0)],
        envelope=False,
    )
    _stub_load_sites(conn, [
        {"id": "SF-5", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert len(records) == 1
    assert records[0]["port_mi"] is not None
    assert records[0]["shipyard_mi"] is not None


def test_missing_coordinates_site_skipped(tmp_path):
    conn = _make_connector(tmp_path, [_port("P", 40.01, -82.0)], [])
    _stub_load_sites(conn, [
        {"id": "SF-6", "program": "superfund", "lat": None, "lon": None},
        {"id": "SF-7", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    ids = {r["id"] for r in records}
    assert ids == {"SF-7"}


def test_missing_only_merges_existing(tmp_path):
    conn = _make_connector(tmp_path, [_port("P", 40.01, -82.0)], [])
    existing = {"sites": [
        {"id": "SF-OLD", "program": "superfund", "port_mi": 3.0, "port_name": "Old Port"},
    ]}
    (conn.OUTPUT_DIR / f"{conn.slug}.json").write_text(json.dumps(existing))
    _stub_load_sites(conn, [
        {"id": "SF-OLD", "program": "superfund", "lat": 40.0, "lon": -82.0},
        {"id": "SF-NEW", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(missing_only=True), use_cache=False)
    ids = {r["id"] for r in records}
    assert "SF-OLD" in ids
    assert "SF-NEW" in ids


def test_missing_only_empty_index_does_not_truncate(tmp_path):
    conn = _make_connector(tmp_path, [], [])
    existing = {"sites": [
        {"id": "SF-KEEP", "program": "superfund", "port_mi": 1.0, "port_name": "Keep Port"},
    ]}
    (conn.OUTPUT_DIR / f"{conn.slug}.json").write_text(json.dumps(existing))
    _stub_load_sites(conn, [
        {"id": "SF-NEW", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(missing_only=True), use_cache=False)
    assert {r["id"] for r in records} == {"SF-KEEP"}


def test_full_run_empty_port_index_returns_empty(tmp_path):
    """A NON-missing-only run with an empty PORT index aborts early (the
    port layer is the required signal); an empty shipyard-only overlay does
    not (see test_empty_shipyard_overlay_still_produces_port_join)."""
    conn = _make_connector(tmp_path, [], [])
    _stub_load_sites(conn, [
        {"id": "SF-NEW", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    assert conn.fetch_records(_args(missing_only=False), use_cache=False) == []


def test_slug_does_not_collide_with_overlays():
    assert PortProximity.slug + ".json" != PORTS_FILE
    assert PortProximity.slug + ".json" != SHIPYARDS_FILE
    assert PortProximity.slug == "port-proximity"


def test_schema_accepts_port_and_shipyard_fields():
    """schema.SiteRecord must accept all seven port_*/shipyard_* fields."""
    from schema import SiteRecord
    rec = SiteRecord(
        id="test", name="Test Site", program="superfund", state="TX",
        lat=27.8, lon=-97.4,
        port_mi=3.2, port_name="Corpus Christi, TX", port_type="Coastal",
        port_hurricane_freq=0.2,
        shipyard_mi=1.6, shipyard_name="Kiewit Offshore Services",
        shipyard_capability="heavy_module",
    )
    d = rec.model_dump(exclude_none=True)
    assert d["port_mi"] == pytest.approx(3.2)
    assert d["port_name"] == "Corpus Christi, TX"
    assert d["port_type"] == "Coastal"
    assert d["port_hurricane_freq"] == pytest.approx(0.2)
    assert d["shipyard_mi"] == pytest.approx(1.6)
    assert d["shipyard_name"] == "Kiewit Offshore Services"
    assert d["shipyard_capability"] == "heavy_module"


def test_port_schema_accepts_curated_row():
    from schema import Port
    p = Port.model_validate(_port("Test Port", 27.8, -97.4))
    assert p.port_type == "Coastal"


def test_shipyard_schema_accepts_curated_row():
    from schema import Shipyard
    y = Shipyard.model_validate(_yard("Test Yard", 27.8, -97.4))
    assert y.capability == "heavy_module"


def test_shipyard_schema_rejects_unknown_capability():
    from schema import Shipyard
    import pydantic
    bad = _yard("Bad Yard", 27.8, -97.4)
    bad["capability"] = "not_a_real_capability"
    with pytest.raises(pydantic.ValidationError):
        Shipyard.model_validate(bad)
