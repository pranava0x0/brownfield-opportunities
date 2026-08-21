"""Tests for keyed, state-bulk ACS workforce enrichment."""
from __future__ import annotations

import argparse
import json
from unittest.mock import patch

import pytest

import connectors
from connectors.census_workforce import CensusWorkforce, normalize_county
from schema import SiteRecord


def test_county_normalizer_handles_census_suffixes():
    assert normalize_county("St. Louis County") == normalize_county("Saint Louis")
    assert normalize_county("Orleans Parish") == "orleans"


def test_key_is_required(tmp_path, monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CENSUS_API_KEY"):
        CensusWorkforce(tmp_path).fetch_records(argparse.Namespace(limit=None), True)


def test_state_bulk_response_joins_sites(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "superfund-npl.json").write_text(json.dumps({"sites": [{
        "id": "X", "program": "superfund", "state": "AL", "county": "Autauga",
    }]}))
    monkeypatch.setattr(CensusWorkforce, "_data_dir", staticmethod(lambda: data_dir))
    monkeypatch.setenv("CENSUS_API_KEY", "test-key")
    instance = CensusWorkforce(tmp_path / "cache")
    response = [
        ["NAME", "DP03_0003E", "DP03_0034E", "DP03_0062E", "state", "county"],
        ["Autauga County, Alabama", "25000", "2100", "72000", "01", "001"],
    ]
    with patch.object(instance, "http_get_json", return_value=response) as request:
        records = instance.fetch_records(argparse.Namespace(limit=None), True)
    assert request.call_count == 1
    assert records[0]["county_construction_employment"] == 2100
    assert SiteRecord(**records[0]).workforce_data_year == 2024
    assert connectors.get("census-workforce") is CensusWorkforce
