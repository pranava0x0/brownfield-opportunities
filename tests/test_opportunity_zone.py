"""Unit tests for the Opportunity Zone enrichment connector.

Covers:
- Layer fetcher + index build with mocked http_get_json
- Per-site point-in-polygon containment producing in_opportunity_zone +
  oz_tract_geoid + oz_rural fields
- Rural-flag parsing tolerates HUD's "Y"/"Yes"/"1"/1 variants
- --missing-only mode skips covered sites and merges with existing output
- Schema accepts the new fields
- Registry wires the connector
- run_order puts it after producers in --all
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import connectors as connectors_pkg
from connectors.base import Connector
from connectors.opportunity_zone import OpportunityZone
from schema import Payload, SiteRecord


# --- helpers ---

def _write_program_file(dir_path: Path, fname: str, sites: list[dict]) -> None:
    payload = {
        "generated_at": "2026-05-17T00:00:00Z",
        "source": "test",
        "source_url": "test://",
        "count": len(sites),
        "sites": sites,
    }
    (dir_path / fname).write_text(json.dumps(payload))


def _oz_feature(rings, geoid: str, state: str = "Alabama", county: str = "01",
                tract: str = "010100", rural: str | None = "N") -> dict:
    return {
        "attributes": {
            "GEOID10": geoid,
            "STATE_NAME": state,
            "COUNTY": county,
            "TRACT": tract,
            "Rural": rural,
        },
        "geometry": {"rings": rings},
    }


def _make_args(**overrides):
    base = {"limit": None, "missing_only": False}
    base.update(overrides)
    return argparse.Namespace(**base)


# Unit square at lat/lon (40-41, -75 to -74).
_SQUARE_RINGS = [[
    [-75.0, 40.0],
    [-74.0, 40.0],
    [-74.0, 41.0],
    [-75.0, 41.0],
    [-75.0, 40.0],
]]


# --- registry / wiring ---

def test_registered_in_registry():
    assert "opportunity-zone" in connectors_pkg.names()
    assert connectors_pkg.get("opportunity-zone") is OpportunityZone


def test_run_order_after_all_producers():
    oz_order = connectors_pkg.get("opportunity-zone").run_order
    for slug in connectors_pkg.names():
        cls = connectors_pkg.get(slug)
        if cls.run_order == 100:  # producer tier
            assert oz_order > cls.run_order


# --- _load_sites ---

def test_load_sites_iterates_program_files(tmp_path, monkeypatch):
    monkeypatch.setattr(OpportunityZone, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.5, "lon": -74.5},
    ])
    _write_program_file(tmp_path, "epa-acres.json", [
        {"id": "ACRES-1", "program": "brownfield", "lat": 41.5, "lon": -75.5},
    ])
    inst = OpportunityZone(cache_dir=tmp_path / "cache")
    sites = list(inst._load_sites())
    assert {s["id"] for s in sites} == {"S1", "ACRES-1"}
    assert inst._loaded_program_count == 2


# --- _build_oz_index + Rural flag parsing ---

def test_build_oz_index_parses_rural_yes_string():
    inst = OpportunityZone(cache_dir=Path("/tmp/oz_test"))
    pages = [
        {"features": [_oz_feature(_SQUARE_RINGS, geoid="01000010100", rural="Y")]},
        {"features": []},
    ]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        idx = inst._build_oz_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    assert hit is not None
    assert hit["rural"] is True
    assert hit["geoid"] == "01000010100"


def test_build_oz_index_parses_rural_no_string():
    inst = OpportunityZone(cache_dir=Path("/tmp/oz_test"))
    pages = [{"features": [_oz_feature(_SQUARE_RINGS, geoid="01", rural="N")]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        idx = inst._build_oz_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    assert hit["rural"] is False


def test_build_oz_index_parses_rural_integer():
    inst = OpportunityZone(cache_dir=Path("/tmp/oz_test"))
    pages = [{"features": [_oz_feature(_SQUARE_RINGS, geoid="01", rural=1)]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        idx = inst._build_oz_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    assert hit["rural"] is True


def test_build_oz_index_handles_rural_missing():
    inst = OpportunityZone(cache_dir=Path("/tmp/oz_test"))
    pages = [{"features": [_oz_feature(_SQUARE_RINGS, geoid="01", rural=None)]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        idx = inst._build_oz_index(use_cache=True)
    hit = idx.containing(40.5, -74.5)
    assert hit["rural"] is None


# --- fetch_records end-to-end ---

def test_fetch_records_marks_site_inside_oz(tmp_path, monkeypatch):
    """Site at (40.5, -74.5) is inside our test OZ square; site at (35, -90)
    is outside. Both must appear in the output with the correct flag."""
    monkeypatch.setattr(OpportunityZone, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "INSIDE", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "OUTSIDE", "program": "superfund", "lat": 35.0, "lon": -90.0},
    ])

    inst = OpportunityZone(cache_dir=tmp_path / "cache")
    pages = [
        {"features": [_oz_feature(_SQUARE_RINGS, geoid="34001020100", rural="N")]},
        {"features": []},
    ]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(_make_args(), use_cache=True)

    by_id = {r["id"]: r for r in records}
    assert by_id["INSIDE"]["in_opportunity_zone"] is True
    assert by_id["INSIDE"]["oz_tract_geoid"] == "34001020100"
    assert by_id["INSIDE"]["oz_rural"] is False
    assert by_id["OUTSIDE"]["in_opportunity_zone"] is False
    assert "oz_tract_geoid" not in by_id["OUTSIDE"]


def test_fetch_records_skips_sites_with_bad_coords(tmp_path, monkeypatch):
    monkeypatch.setattr(OpportunityZone, "_data_dir", staticmethod(lambda: tmp_path))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "GOOD", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "BAD-NONE", "program": "superfund", "lat": None, "lon": None},
        {"id": "BAD-STR", "program": "superfund", "lat": "x", "lon": "y"},
    ])
    inst = OpportunityZone(cache_dir=tmp_path / "cache")
    pages = [{"features": [_oz_feature(_SQUARE_RINGS, geoid="01")]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        records = inst.fetch_records(_make_args(), use_cache=True)
    assert {r["id"] for r in records} == {"GOOD"}


def test_fetch_records_missing_only_skips_covered(tmp_path, monkeypatch):
    """--missing-only must drop sites already in the existing output and
    merge new records back with what's on disk."""
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(OpportunityZone, "_data_dir", staticmethod(lambda: tmp_path))
    # Existing output already has S1 covered.
    (tmp_path / "opportunity-zone.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x", "count": 1,
        "sites": [{"id": "S1", "program": "superfund",
                   "in_opportunity_zone": True,
                   "oz_tract_geoid": "OLD-TRACT"}],
    }))
    _write_program_file(tmp_path, "superfund-npl.json", [
        {"id": "S1", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "S2", "program": "superfund", "lat": 40.5, "lon": -74.5},
    ])

    inst = OpportunityZone(cache_dir=tmp_path / "cache")
    fetched_pages: list[int] = []
    pages = [{"features": [_oz_feature(_SQUARE_RINGS, geoid="NEW-TRACT")]}, {"features": []}]
    call_count = {"n": 0}
    def fake_get(url, params, use_cache, cache_key=None):
        fetched_pages.append(cache_key.get("offset", -1))
        result = pages[call_count["n"]]
        call_count["n"] += 1
        return result
    with patch.object(inst, "http_get_json", side_effect=fake_get):
        out = inst.fetch_records(_make_args(missing_only=True), use_cache=True)

    by_id = {r["id"]: r for r in out}
    # S1 retains its existing record (not overwritten).
    assert by_id["S1"]["oz_tract_geoid"] == "OLD-TRACT"
    # S2 is newly enriched.
    assert by_id["S2"]["oz_tract_geoid"] == "NEW-TRACT"


# --- schema round-trip ---

def test_schema_accepts_oz_fields():
    rec = SiteRecord(
        id="S1", program="superfund",
        in_opportunity_zone=True,
        oz_tract_geoid="34001020100",
        oz_rural=False,
    )
    dumped = rec.model_dump(exclude_none=True)
    assert dumped["in_opportunity_zone"] is True
    assert dumped["oz_tract_geoid"] == "34001020100"
    assert dumped["oz_rural"] is False


def test_schema_oz_fields_excluded_when_none():
    rec = SiteRecord(id="S1", program="superfund")
    dumped = rec.model_dump(exclude_none=True)
    for f in ("in_opportunity_zone", "oz_tract_geoid", "oz_rural"):
        assert f not in dumped


def test_payload_with_oz_records_validates():
    payload = Payload(
        generated_at="2026-05-17T00:00:00Z",
        source="test",
        source_url="test://",
        count=2,
        sites=[
            {"id": "S1", "program": "superfund", "in_opportunity_zone": True,
             "oz_tract_geoid": "01001020100", "oz_rural": True},
            {"id": "ACRES-1", "program": "brownfield", "in_opportunity_zone": False},
        ],
    )
    assert payload.count == 2
    assert payload.sites[0].in_opportunity_zone is True
    assert payload.sites[1].in_opportunity_zone is False
