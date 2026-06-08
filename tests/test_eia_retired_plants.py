"""Tests for connectors/eia_retired_plants.py.

Verifies that the EIA-860M connector:
  - Correctly groups multi-unit plants by Plant ID (sum MW)
  - Filters out non-dispatchable fuels (SUN, WND)
  - Filters out plants below MIN_PLANT_MW (100 MW)
  - Emits the correct per-site fields within MAX_DISTANCE_MI (5 mi)
  - Respects --missing-only merging
  - Handles missing geometry gracefully

All tests use synthetic workbook bytes — no network calls, no real EIA data.
"""
from __future__ import annotations

import io
import json
import pathlib

import pytest
import openpyxl

from connectors.eia_retired_plants import (
    EiaRetiredPlants,
    MAX_DISTANCE_MI,
    MIN_PLANT_MW,
    DISPATCHABLE_FUELS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workbook(data_rows: list[tuple]) -> bytes:
    """Build a minimal EIA-860M-shaped Excel workbook in memory.

    Row layout mirrors the real sheet:
      row 0 = banner
      row 1 = blank
      row 2 = header
      row 3+ = data
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Retired"
    # Banner
    ws.append(["Inventory of Retired Generators as of April 2026"])
    ws.append(["", ""])
    header = [
        "Entity ID", "Entity Name", "Plant ID", "Plant Name", "Google Map", "Bing Map",
        "Plant State", "County", "Balancing Authority Code", "Sector", "Generator ID",
        "Unit Code", "Nameplate Capacity (MW)", "Net Summer Capacity (MW)",
        "Net Winter Capacity (MW)", "Technology", "Energy Source Code",
        "Prime Mover Code", "Operating Month", "Operating Year",
        "Retirement Month", "Retirement Year",
        "Nameplate Energy Capacity (MWh)", "DC Net Capacity (MW)",
        "Latitude", "Longitude",
    ]
    ws.append(header)
    for row in data_rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(plant_id: int, plant_name: str, state: str,
         mw: float, fuel: str,
         ret_year: int, lat: float, lon: float,
         gen_id: str = "1") -> tuple:
    """Build one data row matching _COL_* indices in the Retired sheet."""
    return (
        None,        # col 0: Entity ID
        None,        # col 1: Entity Name
        plant_id,    # col 2: Plant ID  ← _COL_PLANT_ID
        plant_name,  # col 3: Plant Name
        None,        # col 4: Google Map
        None,        # col 5: Bing Map
        state,       # col 6: Plant State
        None,        # col 7: County
        None,        # col 8: BA Code
        None,        # col 9: Sector
        gen_id,      # col 10: Generator ID
        None,        # col 11: Unit Code
        mw,          # col 12: Nameplate MW (ignored — we use Net Summer)
        mw,          # col 13: Net Summer Capacity (MW)  ← _COL_MW
        mw,          # col 14: Net Winter MW (ignored)
        None,        # col 15: Technology
        fuel,        # col 16: Energy Source Code  ← _COL_FUEL
        None,        # col 17: Prime Mover
        1,           # col 18: Operating Month
        2000,        # col 19: Operating Year
        1,           # col 20: Retirement Month
        ret_year,    # col 21: Retirement Year  ← _COL_RET_YEAR
        None,        # col 22: Nameplate Energy Capacity
        None,        # col 23: DC Net Capacity
        lat,         # col 24: Latitude  ← _COL_LAT
        lon,         # col 25: Longitude  ← _COL_LON
    )


def _make_connector(tmp_path: pathlib.Path) -> EiaRetiredPlants:
    return EiaRetiredPlants(cache_dir=tmp_path / "cache")


def _patch_http_get_bytes(connector, wb_bytes: bytes):
    """Monkeypatch http_get_bytes to return synthetic workbook bytes."""
    def _fake(url, params, use_cache, cache_key):
        return wb_bytes
    connector.http_get_bytes = _fake


def _stub_load_sites(connector, sites):
    def _loader():
        connector._loaded_program_count = 1
        return iter(sites)
    connector._load_sites = _loader


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_single_plant_emits_fields(tmp_path):
    """A qualifying retired plant within 5 mi emits all expected fields."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(1001, "Old Coal Plant", "OH", 800.0, "BIT", 2019, 39.95, -82.0),
    ])
    _patch_http_get_bytes(conn, wb)

    # Site at same lat/lon — distance effectively 0
    sites = [{"id": "SF-001", "program": "superfund", "lat": 39.95, "lon": -82.0}]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert len(records) == 1
    r = records[0]
    assert r["id"] == "SF-001"
    assert r["program"] == "superfund"
    assert "retired_plant_mi" in r
    assert r["retired_plant_mi"] < 0.5   # adjacent
    assert r["retired_plant_mw"] == pytest.approx(800.0)
    assert r["retired_plant_fuel"] == "BIT"
    assert r["retired_plant_year"] == 2019
    assert r["retired_plant_name"] == "Old Coal Plant"


def test_multi_unit_plant_sums_mw(tmp_path):
    """Three generators at the same Plant ID → MW summed, latest ret year."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(2000, "Conesville", "OH", 500.0, "BIT", 2018, 40.184, -81.881, "1"),
        _row(2000, "Conesville", "OH", 700.0, "BIT", 2020, 40.184, -81.881, "2"),
        _row(2000, "Conesville", "OH", 725.0, "BIT", 2019, 40.184, -81.881, "3"),
    ])
    _patch_http_get_bytes(conn, wb)

    # Site 1 mi away
    sites = [{"id": "SF-CON", "program": "superfund", "lat": 40.184, "lon": -81.867}]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert len(records) == 1
    r = records[0]
    assert r["retired_plant_mw"] == pytest.approx(1925.0)
    assert r["retired_plant_year"] == 2020   # latest of 2018/2019/2020
    assert r["retired_plant_fuel"] == "BIT"  # largest unit (725 MW) sets fuel


def test_non_dispatchable_fuel_excluded(tmp_path):
    """Solar and wind plants are excluded from the index."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(3001, "Big Solar Farm", "NV", 500.0, "SUN", 2022, 36.0, -115.0),
        _row(3002, "Wind Farm",      "TX", 400.0, "WND", 2021, 36.05, -115.0),
    ])
    _patch_http_get_bytes(conn, wb)

    sites = [{"id": "SF-001", "program": "superfund", "lat": 36.0, "lon": -115.0}]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert records == []


def test_below_min_mw_excluded(tmp_path):
    """Plants below MIN_PLANT_MW (100 MW) are excluded."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(4001, "Small Diesel",  "FL", 50.0, "DFO", 2020, 25.0, -80.5),
        _row(4002, "Tiny Gas Unit", "FL", 99.0, "NG",  2021, 25.0, -80.5),
    ])
    _patch_http_get_bytes(conn, wb)

    sites = [{"id": "SF-001", "program": "superfund", "lat": 25.0, "lon": -80.5}]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert records == []


def test_plant_too_far_excluded(tmp_path):
    """Plants beyond MAX_DISTANCE_MI (5 mi) are not emitted."""
    conn = _make_connector(tmp_path)
    # Place plant ~10 mi north of site
    wb = _make_workbook([
        _row(5001, "Distant Coal", "IN", 500.0, "BIT", 2018, 39.3, -86.0),
    ])
    _patch_http_get_bytes(conn, wb)

    sites = [{"id": "SF-001", "program": "superfund", "lat": 39.15, "lon": -86.0}]  # ~9 mi south
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert records == []


def test_multiple_sites_nearest_chosen(tmp_path):
    """When two plants are in range, the nearest one is returned."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(6001, "Close Plant",  "PA", 500.0, "BIT", 2019, 40.500, -79.200),
        _row(6002, "Far Plant",    "PA", 800.0, "BIT", 2020, 40.530, -79.200),
    ])
    _patch_http_get_bytes(conn, wb)

    # Site at 40.500 — should match plant 6001 (distance ~0)
    sites = [{"id": "SF-001", "program": "superfund", "lat": 40.500, "lon": -79.200}]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert len(records) == 1
    assert records[0]["retired_plant_name"] == "Close Plant"


def test_nuclear_plant_qualifies(tmp_path):
    """Nuclear is a dispatchable fuel and should qualify."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(7001, "San Onofre", "CA", 2200.0, "NUC", 2013, 33.369, -117.555),
    ])
    _patch_http_get_bytes(conn, wb)

    sites = [{"id": "SF-001", "program": "superfund", "lat": 33.369, "lon": -117.555}]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert len(records) == 1
    assert records[0]["retired_plant_fuel"] == "NUC"


def test_natural_gas_qualifies(tmp_path):
    """Natural gas at exactly 100 MW (min floor) should qualify."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(8001, "Gas Peaker", "IL", 100.0, "NG", 2021, 41.0, -88.0),
    ])
    _patch_http_get_bytes(conn, wb)

    sites = [{"id": "SF-001", "program": "superfund", "lat": 41.0, "lon": -88.0}]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert len(records) == 1
    assert records[0]["retired_plant_mw"] == pytest.approx(100.0)


def test_missing_coordinates_skipped(tmp_path):
    """Sites without lat/lon are skipped gracefully."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(9001, "Coal Plant", "AL", 500.0, "BIT", 2020, 34.9, -85.9),
    ])
    _patch_http_get_bytes(conn, wb)

    sites = [
        {"id": "SF-001", "program": "superfund", "lat": None, "lon": None},
        {"id": "SF-002", "program": "superfund"},  # missing altogether
        {"id": "SF-003", "program": "superfund", "lat": 34.9, "lon": -85.9},
    ]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    ids = {r["id"] for r in records}
    assert "SF-001" not in ids
    assert "SF-002" not in ids
    assert "SF-003" in ids


def test_missing_only_merges_existing(tmp_path):
    """--missing-only must merge new records with the existing output file."""
    # Pre-populate existing output with one record
    output_dir = tmp_path / "docs" / "data"
    output_dir.mkdir(parents=True)

    conn = _make_connector(tmp_path)
    conn.OUTPUT_DIR = output_dir

    existing_data = {
        "sites": [
            {"id": "SF-OLD", "program": "superfund", "retired_plant_mi": 0.5,
             "retired_plant_mw": 800.0, "retired_plant_fuel": "BIT", "retired_plant_year": 2019}
        ]
    }
    (output_dir / "eia-retired-plants.json").write_text(json.dumps(existing_data))

    wb = _make_workbook([
        _row(10001, "Homer City", "PA", 1888.0, "BIT", 2024, 40.513, -79.196),
    ])
    _patch_http_get_bytes(conn, wb)

    sites = [
        # SF-OLD is already covered — should be skipped
        {"id": "SF-NEW", "program": "superfund", "lat": 40.513, "lon": -79.196},
    ]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=True, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    ids = {r["id"] for r in records}
    # Both old AND new should be in the merged output
    assert "SF-OLD" in ids
    assert "SF-NEW" in ids


def test_dispatchable_fuels_set_completeness():
    """Sanity-check that key fuel codes are in DISPATCHABLE_FUELS."""
    for code in ("BIT", "SUB", "LIG", "NG", "DFO", "NUC"):
        assert code in DISPATCHABLE_FUELS, f"{code!r} missing from DISPATCHABLE_FUELS"
    for code in ("SUN", "WND", "GEO", "LFG"):
        assert code not in DISPATCHABLE_FUELS, f"{code!r} should NOT be in DISPATCHABLE_FUELS"


def test_schema_accepts_retired_plant_fields():
    """schema.SiteRecord must accept all five retired_plant_* fields."""
    from schema import SiteRecord
    rec = SiteRecord(
        id="test",
        name="Test Site",
        program="superfund",
        state="OH",
        lat=40.0,
        lon=-82.0,
        retired_plant_mi=0.3,
        retired_plant_mw=1925.0,
        retired_plant_fuel="BIT",
        retired_plant_year=2020,
        retired_plant_name="Conesville",
    )
    d = rec.model_dump(exclude_none=True)
    assert d["retired_plant_mi"] == pytest.approx(0.3)
    assert d["retired_plant_mw"] == pytest.approx(1925.0)
    assert d["retired_plant_fuel"] == "BIT"
    assert d["retired_plant_year"] == 2020
    assert d["retired_plant_name"] == "Conesville"


def test_plant_with_null_island_coords_skipped(tmp_path):
    """Plants at (0, 0) are invalid — PointIndex sentinel filter drops them."""
    conn = _make_connector(tmp_path)
    wb = _make_workbook([
        _row(11001, "Bad Coords", "TX", 500.0, "NG", 2020, 0.0, 0.0),
        _row(11002, "Good Coords", "TX", 500.0, "NG", 2019, 29.5, -95.0),
    ])
    _patch_http_get_bytes(conn, wb)

    sites = [{"id": "SF-001", "program": "superfund", "lat": 29.5, "lon": -95.0}]
    _stub_load_sites(conn, sites)

    import argparse
    args = argparse.Namespace(missing_only=False, limit=None)
    records = conn.fetch_records(args, use_cache=False)

    assert len(records) == 1
    assert records[0]["retired_plant_name"] == "Good Coords"


def test_max_distance_mi_constant():
    """The 5-mi cap should be the correct boundary for the scoring narrative."""
    assert MAX_DISTANCE_MI == 5.0


def test_min_plant_mw_constant():
    """The 100 MW floor should match the scoring and badge threshold."""
    assert MIN_PLANT_MW == 100.0
