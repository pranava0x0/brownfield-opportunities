"""Unit tests for the IRA Energy Community enrichment connector.

Covers:
- Coal-closure index build (mocked http_get_json) with detail derivation
- FFE (fossil-fuel-employment) index build, filtering ec_qual_status='Yes'
- Per-site point-in-polygon producing in_energy_community + type + detail
- coal_closure precedence over fossil_fuel_employment when a site is in both
- Sites outside both layers get in_energy_community=False
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
from connectors.ira_energy_community import IraEnergyCommunity
from schema import SiteRecord


# --- helpers ---

def _write_program_file(dir_path: Path, fname: str, sites: list[dict]) -> None:
    payload = {
        "generated_at": "2026-06-08T00:00:00Z",
        "source": "test",
        "source_url": "test://",
        "count": len(sites),
        "sites": sites,
    }
    (dir_path / fname).write_text(json.dumps(payload))


# Unit square at lat 40-41, lon -75 to -74.
_SQUARE_A = [[
    [-75.0, 40.0], [-74.0, 40.0], [-74.0, 41.0], [-75.0, 41.0], [-75.0, 40.0],
]]
# A different square at lat 30-31, lon -90 to -89.
_SQUARE_B = [[
    [-90.0, 30.0], [-89.0, 30.0], [-89.0, 31.0], [-90.0, 31.0], [-90.0, 30.0],
]]


def _coal_feature(rings, geoid="34001020100", mine="No", generator="No",
                  adjacent="No") -> dict:
    return {
        "attributes": {
            "geoid_tract_2020": geoid,
            "mine_closure": mine,
            "generator_closure": generator,
            "adjacent_to_closure": adjacent,
            "state_name": "New Jersey",
            "county_name": "Atlantic",
        },
        "geometry": {"rings": rings},
    }


def _ffe_feature(rings, geoid="22071", area="New Orleans, LA",
                 qual="Yes") -> dict:
    return {
        "attributes": {
            "geoid_cty_2020": geoid,
            "ec_qual_status": qual,
            "msa_area_name": area,
            "msa_nmsa_label": area + " MSA",
            "state_name": "Louisiana",
        },
        "geometry": {"rings": rings},
    }


def _make_args(**overrides):
    base = {"limit": None, "missing_only": False}
    base.update(overrides)
    return argparse.Namespace(**base)


def _dispatch(coal_pages, ffe_pages):
    """Return a fake http_get_json that routes by cache_key['src']."""
    state = {"coal": 0, "ffe": 0}

    def fake_get(url, params, use_cache, cache_key=None):
        src = (cache_key or {}).get("src", "")
        if src == "ira_coal_closure":
            page = coal_pages[state["coal"]]
            state["coal"] += 1
            return page
        if src == "ira_ffe":
            page = ffe_pages[state["ffe"]]
            state["ffe"] += 1
            return page
        raise AssertionError(f"unexpected src {src!r}")

    return fake_get


# --- registry / wiring ---

def test_registered_in_registry():
    assert "ira-energy-community" in connectors_pkg.names()
    assert connectors_pkg.get("ira-energy-community") is IraEnergyCommunity


def test_run_order_after_all_producers():
    order = connectors_pkg.get("ira-energy-community").run_order
    for slug in connectors_pkg.names():
        cls = connectors_pkg.get(slug)
        if cls.run_order == 100:  # producer tier
            assert order > cls.run_order


# --- coal-closure detail derivation ---

def test_coal_index_detail_mine_closure():
    inst = IraEnergyCommunity(cache_dir=Path("/tmp/ira_test"))
    coal_pages = [{"features": [_coal_feature(_SQUARE_A, mine="Yes", adjacent="Yes")]},
                  {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch(coal_pages, [{"features": []}])):
        idx = inst._build_coal_closure_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    # Mine closure beats adjacency for the human-readable detail.
    assert hit["detail"] == "Coal mine closure"


def test_coal_index_detail_generator_closure():
    inst = IraEnergyCommunity(cache_dir=Path("/tmp/ira_test"))
    coal_pages = [{"features": [_coal_feature(_SQUARE_A, generator="Yes", adjacent="Yes")]},
                  {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch(coal_pages, [{"features": []}])):
        idx = inst._build_coal_closure_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    assert hit["detail"] == "Coal generator retirement"


def test_coal_index_detail_adjacent_only():
    inst = IraEnergyCommunity(cache_dir=Path("/tmp/ira_test"))
    coal_pages = [{"features": [_coal_feature(_SQUARE_A, adjacent="Yes")]},
                  {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch(coal_pages, [{"features": []}])):
        idx = inst._build_coal_closure_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    assert hit["detail"] == "Adjacent to coal closure"


# --- FFE index filters ec_qual_status ---

def test_ffe_index_skips_non_qualifying():
    inst = IraEnergyCommunity(cache_dir=Path("/tmp/ira_test"))
    ffe_pages = [{"features": [_ffe_feature(_SQUARE_B, qual="No")]}, {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch([{"features": []}], ffe_pages)):
        idx = inst._build_ffe_index(use_cache=True)
    # A 'No' record must not be indexed.
    assert idx.containing(30.5, -89.5) is None


def test_ffe_index_indexes_qualifying():
    inst = IraEnergyCommunity(cache_dir=Path("/tmp/ira_test"))
    ffe_pages = [{"features": [_ffe_feature(_SQUARE_B, area="Houma, LA")]}, {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch([{"features": []}], ffe_pages)):
        idx = inst._build_ffe_index(use_cache=True)
    hit = idx.containing(30.5, -89.5)
    assert hit is not None
    assert hit["area"] == "Houma, LA"


# --- fetch_records end-to-end ---

def test_fetch_records_coal_and_ffe_and_none(tmp_path, monkeypatch):
    monkeypatch.setattr(IraEnergyCommunity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "COAL", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "FFE", "program": "superfund", "lat": 30.5, "lon": -89.5},
        {"id": "NONE", "program": "superfund", "lat": 10.0, "lon": -10.0},
    ])
    inst = IraEnergyCommunity(cache_dir=tmp_path / "cache")
    coal_pages = [{"features": [_coal_feature(_SQUARE_A, mine="Yes")]}, {"features": []}]
    ffe_pages = [{"features": [_ffe_feature(_SQUARE_B)]}, {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch(coal_pages, ffe_pages)):
        records = inst.fetch_records(_make_args(), use_cache=True)

    by_id = {r["id"]: r for r in records}
    assert by_id["COAL"]["in_energy_community"] is True
    assert by_id["COAL"]["energy_community_type"] == "coal_closure"
    assert by_id["COAL"]["energy_community_detail"] == "Coal mine closure"
    assert by_id["FFE"]["in_energy_community"] is True
    assert by_id["FFE"]["energy_community_type"] == "fossil_fuel_employment"
    assert by_id["FFE"]["energy_community_detail"] == "New Orleans, LA"
    assert by_id["NONE"]["in_energy_community"] is False
    assert "energy_community_type" not in by_id["NONE"]


def test_fetch_records_coal_takes_precedence_over_ffe(tmp_path, monkeypatch):
    """A site inside BOTH a coal-closure tract and an FFE county is tagged
    coal_closure — the more localized, higher-confidence signal."""
    monkeypatch.setattr(IraEnergyCommunity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "BOTH", "program": "superfund", "lat": 40.5, "lon": -74.5},
    ])
    inst = IraEnergyCommunity(cache_dir=tmp_path / "cache")
    # Both layers cover the SAME square A.
    coal_pages = [{"features": [_coal_feature(_SQUARE_A, generator="Yes")]}, {"features": []}]
    ffe_pages = [{"features": [_ffe_feature(_SQUARE_A, area="Overlap MSA")]}, {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch(coal_pages, ffe_pages)):
        records = inst.fetch_records(_make_args(), use_cache=True)
    assert records[0]["energy_community_type"] == "coal_closure"
    assert records[0]["energy_community_detail"] == "Coal generator retirement"


def test_fetch_records_skips_bad_coords(tmp_path, monkeypatch):
    monkeypatch.setattr(IraEnergyCommunity, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "GOOD", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "BAD-NONE", "program": "superfund", "lat": None, "lon": None},
        {"id": "BAD-STR", "program": "superfund", "lat": "x", "lon": "y"},
    ])
    inst = IraEnergyCommunity(cache_dir=tmp_path / "cache")
    coal_pages = [{"features": [_coal_feature(_SQUARE_A, mine="Yes")]}, {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch(coal_pages, [{"features": []}])):
        records = inst.fetch_records(_make_args(), use_cache=True)
    assert {r["id"] for r in records} == {"GOOD"}


def test_fetch_records_missing_only_skips_covered(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(IraEnergyCommunity, "_data_dir", staticmethod(lambda: tmp_path))
    (tmp_path / "ira-energy-community.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x", "count": 1,
        "sites": [{"id": "S1", "program": "superfund",
                   "in_energy_community": True,
                   "energy_community_type": "coal_closure"}],
    }))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "S2", "program": "superfund", "lat": 30.5, "lon": -89.5},
    ])
    inst = IraEnergyCommunity(cache_dir=tmp_path / "cache")
    coal_pages = [{"features": [_coal_feature(_SQUARE_A, mine="Yes")]}, {"features": []}]
    ffe_pages = [{"features": [_ffe_feature(_SQUARE_B)]}, {"features": []}]
    with patch.object(inst, "http_get_json", side_effect=_dispatch(coal_pages, ffe_pages)):
        records = inst.fetch_records(_make_args(missing_only=True), use_cache=True)
    by_id = {r["id"]: r for r in records}
    # S1 preserved from existing; S2 freshly computed.
    assert by_id["S1"]["energy_community_type"] == "coal_closure"
    assert by_id["S2"]["in_energy_community"] is True
    assert by_id["S2"]["energy_community_type"] == "fossil_fuel_employment"


# --- schema ---

def test_schema_accepts_energy_community_fields():
    rec = SiteRecord(
        id="X", program="superfund",
        in_energy_community=True,
        energy_community_type="coal_closure",
        energy_community_detail="Coal mine closure",
    )
    assert rec.in_energy_community is True
    assert rec.energy_community_type == "coal_closure"
    dumped = rec.model_dump(exclude_none=True)
    assert dumped["energy_community_detail"] == "Coal mine closure"
