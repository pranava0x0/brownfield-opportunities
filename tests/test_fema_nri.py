"""Unit tests for the FEMA National Risk Index enrichment connector.

Covers:
- County-polygon index build (mocked http_get_json) carrying composite +
  per-hazard ratings as the polygon attr
- Per-site point-in-polygon producing the nri_* fields
- Sites outside any county polygon get a tombstone {id, program} (no nri_*)
- Numeric / rating coercion (blank → None, rounding)
- Bad-coordinate sites skipped
- --missing-only mode skips covered sites and merges with existing output
- Schema accepts the new fields
- Registry wires the connector; run_order after producers
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import connectors as connectors_pkg
from connectors.base import Connector
from connectors.fema_nri import FemaNri
from schema import SiteRecord


def _write_program_file(dir_path: Path, fname: str, sites: list[dict]) -> None:
    payload = {
        "generated_at": "2026-06-08T00:00:00Z",
        "source": "test", "source_url": "test://",
        "count": len(sites), "sites": sites,
    }
    (dir_path / fname).write_text(json.dumps(payload))


_SQUARE_A = [[
    [-75.0, 40.0], [-74.0, 40.0], [-74.0, 41.0], [-75.0, 41.0], [-75.0, 40.0],
]]


def _nri_feature(rings, fips="34001", score=87.5, rating="Relatively High",
                 wfir="Very High", drgt="Relatively Low", hwav="Relatively Moderate") -> dict:
    return {
        "attributes": {
            "STCOFIPS": fips,
            "RISK_SCORE": score,
            "RISK_RATNG": rating,
            "WFIR_RISKR": wfir,
            "DRGT_RISKR": drgt,
            "HWAV_RISKR": hwav,
        },
        "geometry": {"rings": rings},
    }


def _make_args(**overrides):
    base = {"limit": None, "missing_only": False}
    base.update(overrides)
    return argparse.Namespace(**base)


def _pages(*page_features):
    """Return a fake http_get_json yielding the given pages then an empty one."""
    pages = [{"features": list(f)} for f in page_features] + [{"features": []}]
    state = {"n": 0}

    def fake_get(url, params, use_cache, cache_key=None):
        page = pages[state["n"]]
        state["n"] += 1
        return page

    return fake_get


# --- registry / wiring ---

def test_registered_in_registry():
    assert "fema-nri" in connectors_pkg.names()
    assert connectors_pkg.get("fema-nri") is FemaNri


def test_run_order_after_all_producers():
    order = connectors_pkg.get("fema-nri").run_order
    for slug in connectors_pkg.names():
        cls = connectors_pkg.get(slug)
        if cls.run_order == 100:
            assert order > cls.run_order


# --- index build ---

def test_index_carries_ratings_as_attr():
    inst = FemaNri(cache_dir=Path("/tmp/nri_test"))
    with patch.object(inst, "http_get_json", side_effect=_pages([_nri_feature(_SQUARE_A)])):
        idx = inst._build_nri_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    assert hit is not None
    assert hit["nri_risk_score"] == 87.5
    assert hit["nri_risk_rating"] == "Relatively High"
    assert hit["nri_wildfire_rating"] == "Very High"
    assert hit["nri_drought_rating"] == "Relatively Low"


def test_index_coerces_blank_rating_to_none():
    inst = FemaNri(cache_dir=Path("/tmp/nri_test"))
    feat = _nri_feature(_SQUARE_A, score="", drgt="")
    with patch.object(inst, "http_get_json", side_effect=_pages([feat])):
        idx = inst._build_nri_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    assert hit["nri_risk_score"] is None
    assert hit["nri_drought_rating"] is None


# --- fetch_records end-to-end ---

def test_fetch_records_matches_and_tombstones(tmp_path, monkeypatch):
    monkeypatch.setattr(FemaNri, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "INSIDE", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "OUTSIDE", "program": "superfund", "lat": 10.0, "lon": -10.0},
    ])
    inst = FemaNri(cache_dir=tmp_path / "cache")
    with patch.object(inst, "http_get_json", side_effect=_pages([_nri_feature(_SQUARE_A)])):
        records = inst.fetch_records(_make_args(), use_cache=True)
    by_id = {r["id"]: r for r in records}
    assert by_id["INSIDE"]["nri_risk_rating"] == "Relatively High"
    assert by_id["INSIDE"]["nri_wildfire_rating"] == "Very High"
    # OUTSIDE gets a tombstone — present but no nri_* fields.
    assert by_id["OUTSIDE"] == {"id": "OUTSIDE", "program": "superfund"}


def test_fetch_records_skips_bad_coords(tmp_path, monkeypatch):
    monkeypatch.setattr(FemaNri, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "GOOD", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "BAD", "program": "superfund", "lat": None, "lon": None},
    ])
    inst = FemaNri(cache_dir=tmp_path / "cache")
    with patch.object(inst, "http_get_json", side_effect=_pages([_nri_feature(_SQUARE_A)])):
        records = inst.fetch_records(_make_args(), use_cache=True)
    assert {r["id"] for r in records} == {"GOOD"}


def test_fetch_records_missing_only_merges(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(FemaNri, "_data_dir", staticmethod(lambda: tmp_path))
    (tmp_path / "fema-nri.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x", "count": 1,
        "sites": [{"id": "S1", "program": "superfund",
                   "nri_risk_rating": "Very High"}],
    }))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "S2", "program": "superfund", "lat": 40.5, "lon": -74.5},
    ])
    inst = FemaNri(cache_dir=tmp_path / "cache")
    with patch.object(inst, "http_get_json",
                      side_effect=_pages([_nri_feature(_SQUARE_A, rating="Very Low")])):
        records = inst.fetch_records(_make_args(missing_only=True), use_cache=True)
    by_id = {r["id"]: r for r in records}
    assert by_id["S1"]["nri_risk_rating"] == "Very High"  # preserved
    assert by_id["S2"]["nri_risk_rating"] == "Very Low"    # fresh


# --- schema ---

def test_schema_accepts_nri_fields():
    rec = SiteRecord(
        id="X", program="superfund",
        nri_risk_score=99.8, nri_risk_rating="Very High",
        nri_wildfire_rating="Very High", nri_drought_rating="Relatively Low",
        nri_heatwave_rating="Relatively High",
    )
    assert rec.nri_risk_score == 99.8
    dumped = rec.model_dump(exclude_none=True)
    assert dumped["nri_wildfire_rating"] == "Very High"
