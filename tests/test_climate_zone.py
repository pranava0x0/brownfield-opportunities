"""Unit tests for the DOE / PNNL climate-zone enrichment connector."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import connectors as connectors_pkg
from connectors.base import Connector
from connectors.climate_zone import ClimateZone, _format_climate_zone
from schema import SiteRecord


def _write_program_file(dir_path: Path, fname: str, sites: list[dict]) -> None:
    payload = {
        "generated_at": "2026-05-23T00:00:00Z",
        "source": "test",
        "source_url": "test://",
        "count": len(sites),
        "sites": sites,
    }
    (dir_path / fname).write_text(json.dumps(payload))


def _feature(rings, zone=5, moisture="B") -> dict:
    return {
        "attributes": {
            "FIPS": "08031",
            "County_Name": "Denver",
            "STATE_NAME": "Colorado",
            "IECC_Climate_Zone": zone,
            "IECC_Moisture_Regime": moisture,
            "BA_Climate_Zone": "Cold",
        },
        "geometry": {"rings": rings},
    }


def _make_args(**overrides):
    base = {"limit": None, "missing_only": False}
    base.update(overrides)
    return argparse.Namespace(**base)


_SQUARE_RINGS = [[
    [-105.0, 39.0],
    [-104.0, 39.0],
    [-104.0, 40.0],
    [-105.0, 40.0],
    [-105.0, 39.0],
]]


def test_registered_in_registry():
    assert "climate-zone" in connectors_pkg.names()
    assert connectors_pkg.get("climate-zone") is ClimateZone


def test_run_order_after_producers():
    order = connectors_pkg.get("climate-zone").run_order
    for slug in connectors_pkg.names():
        cls = connectors_pkg.get(slug)
        if cls.run_order == 100:
            assert order > cls.run_order


def test_format_climate_zone_combines_zone_and_moisture():
    assert _format_climate_zone({
        "IECC_Climate_Zone": 5,
        "IECC_Moisture_Regime": "b",
    }) == "5B"


def test_format_climate_zone_tolerates_missing_moisture():
    assert _format_climate_zone({
        "IECC_Climate_Zone": "4",
        "IECC_Moisture_Regime": None,
    }) == "4"


def test_fetch_records_assigns_climate_zone(tmp_path, monkeypatch):
    monkeypatch.setattr(ClimateZone, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "INSIDE", "program": "superfund", "lat": 39.5, "lon": -104.5},
        {"id": "OUTSIDE", "program": "superfund", "lat": 35.0, "lon": -90.0},
    ])

    inst = ClimateZone(cache_dir=tmp_path / "cache")
    pages = [{"features": [_feature(_SQUARE_RINGS)]}, {"features": []}]
    call_count = {"n": 0}

    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(_make_args(), use_cache=True)

    assert records == [
        {"id": "INSIDE", "program": "superfund", "climate_zone": "5B"}
    ]


def test_fetch_records_missing_only_merges_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(ClimateZone, "_data_dir", staticmethod(lambda: tmp_path))
    (tmp_path / "climate-zone.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x", "count": 1,
        "sites": [{"id": "S1", "program": "superfund", "climate_zone": "4A"}],
    }))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 39.5, "lon": -104.5},
        {"id": "S2", "program": "superfund", "lat": 39.5, "lon": -104.5},
    ])

    inst = ClimateZone(cache_dir=tmp_path / "cache")
    pages = [{"features": [_feature(_SQUARE_RINGS)]}, {"features": []}]
    call_count = {"n": 0}

    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(_make_args(missing_only=True), use_cache=True)

    by_id = {r["id"]: r for r in records}
    assert by_id["S1"]["climate_zone"] == "4A"
    assert by_id["S2"]["climate_zone"] == "5B"


def test_schema_accepts_climate_zone():
    SiteRecord(id="S1", program="superfund", climate_zone="5B")
