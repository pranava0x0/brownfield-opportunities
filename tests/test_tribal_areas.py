"""Contract tests for national TIGERweb AIANNHA containment."""
from __future__ import annotations

import argparse
import json
from unittest.mock import patch

import connectors
from connectors.tribal_areas import LAYERS, TribalAreas
from schema import SiteRecord

SQUARE = [[[-75, 40], [-74, 40], [-74, 41], [-75, 41], [-75, 40]]]


def _args():
    return argparse.Namespace(limit=None, missing_only=False)


def test_registered_and_schema_accepts_fields():
    assert connectors.get("tribal-areas") is TribalAreas
    record = SiteRecord(
        id="X", program="fuds", in_aiannha_area=True, aiannha_area_count=1,
        aiannha_areas=[{"name": "Example", "geoid": "1", "category": "Reservation"}],
    )
    assert record.aiannha_area_count == 1


def test_bulk_layers_join_inside_and_outside(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "superfund-npl.json").write_text(json.dumps({"sites": [
        {"id": "IN", "program": "superfund", "lat": 40.5, "lon": -74.5},
        {"id": "OUT", "program": "superfund", "lat": 20, "lon": -100},
    ]}))
    monkeypatch.setattr(TribalAreas, "_data_dir", staticmethod(lambda: data_dir))
    instance = TribalAreas(tmp_path / "cache")

    calls = {layer: 0 for layer in LAYERS}

    def fake_get(url, params, use_cache, cache_key=None):
        layer = cache_key["layer"]
        calls[layer] += 1
        if layer == 2 and calls[layer] == 1:
            return {"features": [{
                "attributes": {"NAME": "Example Reservation", "GEOID": "999"},
                "geometry": {"rings": SQUARE},
            }]}
        return {"features": []}

    with patch.object(instance, "http_get_json", side_effect=fake_get):
        records = instance.fetch_records(_args(), use_cache=True)
    by_id = {record["id"]: record for record in records}
    assert by_id["IN"]["in_aiannha_area"] is True
    assert by_id["IN"]["aiannha_areas"][0]["name"] == "Example Reservation"
    assert by_id["OUT"] == {
        "id": "OUT", "program": "superfund", "in_aiannha_area": False,
        "aiannha_area_count": 0,
    }
