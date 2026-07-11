"""Tests for connectors/planned_retirements.py.

Verifies that the planned-retirements-proximity connector:
  - Emits the correct per-site fields for a plant within MAX_DISTANCE_MI
  - Takes last_retirement_year as the plant's retirement year
  - Excludes plants below MIN_PLANT_MW and beyond MAX_DISTANCE_MI
  - Tolerates both the {"sites": [...]} envelope and a bare list overlay
  - Respects --missing-only merging
  - Skips sites with missing/invalid coordinates
  - Does NOT collide with the overlay filename (slug != overlay slug)

All tests use a synthetic in-memory overlay — no network, no real data.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import pytest

from connectors.planned_retirements import (
    PlannedRetirements,
    MAX_DISTANCE_MI,
    MIN_PLANT_MW,
    OVERLAY_FILE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plant(name, lat, lon, mw, fuel="coal",
           first_year=2027, last_year=2028) -> dict:
    return {
        "id": f"EIA-PLANNED-{name}",
        "name": name,
        "lat": lat,
        "lon": lon,
        "mw": mw,
        "fuel": fuel,
        "first_retirement_year": first_year,
        "last_retirement_year": last_year,
    }


def _make_connector(tmp_path: pathlib.Path, plants, *, envelope=True) -> PlannedRetirements:
    """Build a connector whose _data_dir points at tmp_path holding a
    synthetic overlay file."""
    data_dir = tmp_path / "docs" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    body = {"sites": plants} if envelope else plants
    (data_dir / OVERLAY_FILE).write_text(json.dumps(body))
    conn = PlannedRetirements(cache_dir=tmp_path / "cache")
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

def test_single_plant_emits_fields(tmp_path):
    """A qualifying planned-retirement plant within range emits all fields."""
    conn = _make_connector(tmp_path, [
        _plant("Cumberland", 36.39, -87.65, 2600.0, "coal", 2026, 2028),
    ])
    _stub_load_sites(conn, [
        {"id": "SF-1", "program": "superfund", "lat": 36.39, "lon": -87.65},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert len(records) == 1
    r = records[0]
    assert r["id"] == "SF-1"
    assert r["program"] == "superfund"
    assert r["planned_retirement_mi"] < 0.5
    assert r["planned_retirement_mw"] == pytest.approx(2600.0)
    assert r["planned_retirement_fuel"] == "coal"
    assert r["planned_retirement_year"] == 2028  # last unit's year
    assert r["planned_retirement_name"] == "Cumberland"


def test_year_falls_back_to_first_when_no_last(tmp_path):
    """When last_retirement_year is absent, first_retirement_year is used."""
    p = _plant("Solo", 40.0, -82.0, 500.0, "natural gas", 2030, None)
    p.pop("last_retirement_year")
    conn = _make_connector(tmp_path, [p])
    _stub_load_sites(conn, [
        {"id": "SF-2", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert records[0]["planned_retirement_year"] == 2030


def test_below_min_mw_excluded(tmp_path):
    """A plant below MIN_PLANT_MW is not indexed."""
    conn = _make_connector(tmp_path, [
        _plant("Tiny", 40.0, -82.0, MIN_PLANT_MW - 1.0),
    ])
    _stub_load_sites(conn, [
        {"id": "SF-3", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert records == []


def test_plant_too_far_excluded(tmp_path):
    """A plant beyond MAX_DISTANCE_MI is not emitted."""
    # ~10 mi north (≈0.145° lat)
    conn = _make_connector(tmp_path, [
        _plant("Distant", 40.145, -82.0, 800.0),
    ])
    _stub_load_sites(conn, [
        {"id": "SF-4", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert records == []


def test_bare_list_overlay_tolerated(tmp_path):
    """The connector reads a bare-list overlay as well as the {"sites"} one."""
    conn = _make_connector(tmp_path, [
        _plant("Cumberland", 36.39, -87.65, 2600.0),
    ], envelope=False)
    _stub_load_sites(conn, [
        {"id": "SF-5", "program": "superfund", "lat": 36.39, "lon": -87.65},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    assert len(records) == 1


def test_missing_coordinates_site_skipped(tmp_path):
    """A site with no lat/lon is skipped, not crashed on."""
    conn = _make_connector(tmp_path, [
        _plant("Cumberland", 36.39, -87.65, 2600.0),
    ])
    _stub_load_sites(conn, [
        {"id": "SF-6", "program": "superfund", "lat": None, "lon": None},
        {"id": "SF-7", "program": "superfund", "lat": 36.39, "lon": -87.65},
    ])
    records = conn.fetch_records(_args(), use_cache=False)
    ids = {r["id"] for r in records}
    assert ids == {"SF-7"}


def test_missing_only_merges_existing(tmp_path):
    """--missing-only merges new records with the existing output file."""
    conn = _make_connector(tmp_path, [
        _plant("Homer City", 40.513, -79.196, 1888.0),
    ])
    # Existing output covers SF-OLD.
    existing = {"sites": [
        {"id": "SF-OLD", "program": "superfund", "planned_retirement_mi": 0.5,
         "planned_retirement_mw": 700.0, "planned_retirement_fuel": "coal",
         "planned_retirement_year": 2027},
    ]}
    (conn.OUTPUT_DIR / f"{conn.slug}.json").write_text(json.dumps(existing))
    _stub_load_sites(conn, [
        {"id": "SF-OLD", "program": "superfund", "lat": 40.513, "lon": -79.196},
        {"id": "SF-NEW", "program": "superfund", "lat": 40.513, "lon": -79.196},
    ])
    records = conn.fetch_records(_args(missing_only=True), use_cache=False)
    ids = {r["id"] for r in records}
    assert "SF-OLD" in ids
    assert "SF-NEW" in ids


def test_missing_only_empty_index_does_not_truncate(tmp_path):
    """Under --missing-only, an empty/missing overlay must NOT wipe the
    existing join file — the connector returns the on-disk records instead of
    []. (The ECHO/epa-echo truncation-to-18 gotcha, generalized.)"""
    # Empty overlay → empty index.
    conn = _make_connector(tmp_path, [])
    # A previously-written join with real records.
    existing = {"sites": [
        {"id": "SF-KEEP", "program": "superfund", "planned_retirement_mi": 0.4,
         "planned_retirement_mw": 800.0, "planned_retirement_fuel": "coal",
         "planned_retirement_year": 2028},
    ]}
    (conn.OUTPUT_DIR / f"{conn.slug}.json").write_text(json.dumps(existing))
    _stub_load_sites(conn, [
        {"id": "SF-NEW", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    records = conn.fetch_records(_args(missing_only=True), use_cache=False)
    # The prior record survives; nothing is truncated.
    assert {r["id"] for r in records} == {"SF-KEEP"}


def test_full_run_empty_index_returns_empty(tmp_path):
    """A NON-missing-only run with an empty index legitimately returns [] —
    the truncation guard is scoped to --missing-only only."""
    conn = _make_connector(tmp_path, [])
    _stub_load_sites(conn, [
        {"id": "SF-NEW", "program": "superfund", "lat": 40.0, "lon": -82.0},
    ])
    assert conn.fetch_records(_args(missing_only=False), use_cache=False) == []


def test_slug_does_not_collide_with_overlay(tmp_path):
    """The connector's output slug must differ from the overlay filename it
    reads, or a run would clobber the 90-plant overlay."""
    assert PlannedRetirements.slug + ".json" != OVERLAY_FILE
    assert PlannedRetirements.slug == "planned-retirements-proximity"


def test_schema_accepts_planned_retirement_fields():
    """schema.SiteRecord must accept all five planned_retirement_* fields."""
    from schema import SiteRecord
    rec = SiteRecord(
        id="test", name="Test Site", program="superfund", state="TN",
        lat=36.0, lon=-87.0,
        planned_retirement_mi=0.3,
        planned_retirement_mw=2600.0,
        planned_retirement_fuel="coal",
        planned_retirement_year=2028,
        planned_retirement_name="Cumberland",
    )
    d = rec.model_dump(exclude_none=True)
    assert d["planned_retirement_mi"] == pytest.approx(0.3)
    assert d["planned_retirement_mw"] == pytest.approx(2600.0)
    assert d["planned_retirement_fuel"] == "coal"
    assert d["planned_retirement_year"] == 2028
    assert d["planned_retirement_name"] == "Cumberland"
