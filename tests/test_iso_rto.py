"""Unit tests for the ISO/RTO region enrichment connector."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import connectors as connectors_pkg
from connectors.base import Connector
from connectors.iso_rto import IsoRto, _normalize_rto, _pick_rto
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


def _feature(rings, rto="PJM", loc_type="ZON", loc_name="PJM zone") -> dict:
    return {
        "attributes": {
            "RTO_ISO": rto,
            "LOC_TYPE": loc_type,
            "LOC_NAME_T": loc_name,
            "LOC_NAME": loc_name,
            "NAME": loc_name,
        },
        "geometry": {"rings": rings},
    }


def _make_args(**overrides):
    base = {"limit": None, "missing_only": False}
    base.update(overrides)
    return argparse.Namespace(**base)


_SQUARE_RINGS = [[
    [-76.0, 39.0],
    [-75.0, 39.0],
    [-75.0, 40.0],
    [-76.0, 40.0],
    [-76.0, 39.0],
]]


def test_registered_in_registry():
    assert "iso-rto" in connectors_pkg.names()
    assert connectors_pkg.get("iso-rto") is IsoRto


def test_run_order_after_producers():
    order = connectors_pkg.get("iso-rto").run_order
    for slug in connectors_pkg.names():
        cls = connectors_pkg.get(slug)
        if cls.run_order == 100:
            assert order > cls.run_order


def test_normalize_rto_uses_iso_ne_label():
    assert _normalize_rto("ISONE") == "ISO-NE"
    assert _normalize_rto("pjm") == "PJM"


def test_pick_rto_prefers_regions_over_hubs():
    picked = _pick_rto([
        {"iso_rto": "MISO", "loc_type": "HUB", "loc_name": "Hub"},
        {"iso_rto": "MISO", "loc_type": "REG", "loc_name": "Region"},
    ])
    assert picked["loc_name"] == "Region"


def test_fetch_records_assigns_rto_and_non_rto(tmp_path, monkeypatch):
    monkeypatch.setattr(IsoRto, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "INSIDE", "program": "superfund", "state": "PA", "lat": 39.5, "lon": -75.5},
        {"id": "OUTSIDE", "program": "superfund", "state": "NV", "lat": 35.0, "lon": -115.0},
        {"id": "AK-SKIP", "program": "superfund", "state": "AK", "lat": 61.0, "lon": -150.0},
    ])

    inst = IsoRto(cache_dir=tmp_path / "cache")
    pages = [{"features": [_feature(_SQUARE_RINGS, rto="PJM", loc_type="ZON")]}, {"features": []}]
    call_count = {"n": 0}

    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(_make_args(), use_cache=True)

    by_id = {r["id"]: r for r in records}
    assert by_id["INSIDE"]["iso_rto"] == "PJM"
    assert by_id["OUTSIDE"]["iso_rto"] == "non-RTO"
    assert "AK-SKIP" not in by_id


def test_fetch_records_missing_only_merges_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(IsoRto, "_data_dir", staticmethod(lambda: tmp_path))
    (tmp_path / "iso-rto.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x", "count": 1,
        "sites": [{"id": "S1", "program": "superfund", "iso_rto": "PJM"}],
    }))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "state": "PA", "lat": 39.5, "lon": -75.5},
        {"id": "S2", "program": "superfund", "state": "PA", "lat": 39.5, "lon": -75.5},
    ])

    inst = IsoRto(cache_dir=tmp_path / "cache")
    pages = [{"features": [_feature(_SQUARE_RINGS, rto="ISONE", loc_type="REG")]}, {"features": []}]
    call_count = {"n": 0}

    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result

    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(_make_args(missing_only=True), use_cache=True)

    by_id = {r["id"]: r for r in records}
    assert by_id["S1"]["iso_rto"] == "PJM"
    assert by_id["S2"]["iso_rto"] == "ISO-NE"


def test_schema_accepts_iso_rto():
    SiteRecord(id="S1", program="superfund", iso_rto="PJM")
