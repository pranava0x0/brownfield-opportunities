"""A core-coordinate refresh must regenerate the civilian nuclear join."""
import importlib.util
import json
from pathlib import Path


def test_rebuild_uses_current_coordinates_and_preserves_catalog(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/build_nuclear_civilian_sites.py"
    spec = importlib.util.spec_from_file_location("nuclear_builder", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    catalog = {"generated_at": "2026-07-26", "sites": [{"id": "n", "name": "Plant", "state": "NH", "lat": 40, "lon": -70, "inl_category": "blue"}]}
    catalog_path = tmp_path / "nuclear-civilian-sites.json"
    catalog_path.write_text(json.dumps(catalog))
    original = catalog_path.read_bytes()
    (tmp_path / "sites.json").write_text(json.dumps({"generated_at": "2026-09-12", "sites": [{"id": "b", "lat": 40.1, "lon": -70, "large_enrichment": "omit"}]}))
    (tmp_path / "nuclear-brownfield-proximity.json").write_text(json.dumps({"generated_at": "old", "radius_mi": 50, "records": []}))
    result = mod.rebuild_proximity_only(tmp_path)
    match = result["records"][0]["nearby_brownfields"][0]
    assert match["distance_mi"] == round(mod._haversine_mi(40, -70, 40.1, -70), 1)
    assert match["lat"] == 40.1 and "large_enrichment" not in match
    assert catalog_path.read_bytes() == original
    assert result["source_metadata"]["nuclear_catalog_generated_at"] == "2026-07-26"
    assert result["source_metadata"]["brownfield_generated_at"] == "2026-09-12"
