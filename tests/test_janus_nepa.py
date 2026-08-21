"""Contract tests for the generated Army Janus NEPA screening artifact."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_janus_nepa.py"
OUTPUT = ROOT / "docs" / "data" / "janus-nepa.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_janus_nepa", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_janus_source_roster_is_nine_installations():
    rows = _load_module().load_janus_sites()
    assert len(rows) == 9
    assert len({row["id"] for row in rows}) == 9
    assert all(row["lat"] is not None and row["lon"] is not None for row in rows)


def test_normalized_usace_data_cannot_claim_a_jurisdictional_determination():
    mod = _load_module()
    result = mod.normalize_usace(
        {
            "regulatory_districts": {"districts": [{"district_name": "Test"}]},
            "wetland_regions": {"regions": [{"region_name": "Test region"}]},
            "wetland_subregions": {"subregions": []},
        }
    )
    assert "does not show wetland presence" in result["limitation"]
    assert "jurisdictional determination" in result["limitation"]


def test_padus_uses_a_distinct_point_context_cache():
    mod = _load_module()
    assert mod.PADUS_POINT_BUFFER_MILES == 0.1
    assert mod.cache_path("demo", "padus").name == "demo--padus-0p1mi.json"
    assert "0.1-mile" in mod.SOURCE_META["padus"]["covers"]


def test_source_errors_are_cached_as_unavailable(tmp_path):
    mod = _load_module()
    site = {"id": "demo"}
    with patch.object(mod, "CACHE_DIR", tmp_path):
        result = mod.cache_error(site, "padus", TimeoutError("slow upstream"))
        cached = json.loads(mod.cache_path("demo", "padus").read_text())
    assert result["status"] == "unavailable"
    assert cached["error"] == "slow upstream"


def test_single_site_rebuild_preserves_complete_inventory(tmp_path):
    mod = _load_module()
    output = tmp_path / "janus-nepa.json"
    geojson_dir = tmp_path / "geojson"
    output.write_text(json.dumps({"sites": [
        {"id": "keep", "name": "Keep", "screening": {}},
        {"id": "replace", "name": "Old", "screening": {}},
    ]}))
    selected = [{
        "id": "replace", "name": "New", "commitment_id": "x",
        "state": "AL", "location": "Alabama", "lat": 1, "lon": 2,
    }]
    with patch.object(mod, "OUTPUT_PATH", output), patch.object(mod, "GEOJSON_DIR", geojson_dir):
        mod.write_outputs(selected, {"replace": {}}, {}, merge_existing=True)
    written = json.loads(output.read_text())
    assert written["site_count"] == 2
    assert {site["id"] for site in written["sites"]} == {"keep", "replace"}
    assert next(site for site in written["sites"] if site["id"] == "replace")["name"] == "New"


def test_generated_payload_has_source_status_and_clickthrough_data():
    payload = json.loads(OUTPUT.read_text())
    assert payload["site_count"] == 9
    assert payload["nepa_mcp_version"] == "0.1.1"
    assert payload["screening_buffer_miles"] == 10.0
    assert payload["deployment_pathway"]["reactor_regulator"] == "United States Army"
    assert "not been published" in payload["deployment_pathway"]["nepa_status"]
    assert "permit conclusion" in " ".join(payload["limitations"])
    for site in payload["sites"]:
        assert set(site["screening"]) == {
            "ipac", "tribal", "nrhp", "padus", "usace", "nepa_assist"
        }
        assert all(section["status"] in {"ok", "unavailable"} for section in site["screening"].values())
        assert site["geojson_url"].startswith("data/janus-nepa/")
        geojson = ROOT / "docs" / site["geojson_url"]
        assert geojson.exists()
        mapped = json.loads(geojson.read_text())
        assert mapped["type"] == "FeatureCollection"
        assert mapped["metadata"]["site_id"] == site["id"]
