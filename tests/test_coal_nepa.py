"""Contract tests for the coal permitting-screen builder and artifact."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_coal_nepa.py"
OUTPUT = ROOT / "docs" / "data" / "coal-nepa.json"

EXPECTED_SOURCES = {"ipac", "tribal", "nrhp", "padus", "usace", "fema_nfhl", "nepa_assist"}


def _load_module():
    spec = importlib.util.spec_from_file_location("build_coal_nepa", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_plant_roster_matches_the_coal_catalog():
    mod = _load_module()
    plants = mod.load_plants()
    catalog = json.loads((ROOT / "docs" / "data" / "coal-conversions.json").read_text())
    assert {p["plant_name"] for p in plants} == {a["plant_name"] for a in catalog["assets"]}
    # Slugs (cache keys) must be unique or two plants would share a cache file.
    assert len({p["id"] for p in plants}) == len(plants)


def test_plant_slug_is_filesystem_safe():
    mod = _load_module()
    assert mod.plant_slug("W. A. Parish (Unit 5–8)") == "w-a-parish-unit-5-8"


def test_single_plant_rebuild_preserves_other_screens(tmp_path, monkeypatch):
    """--plant must merge into the existing artifact, never truncate the
    other 17 screens (Codex PR #22 P2 — the drawer would report them as
    'not generated')."""
    mod = _load_module()
    output = tmp_path / "coal-nepa.json"
    output.write_text(json.dumps({"plants": [
        {"plant_name": "Alpha", "screening": {}},
        {"plant_name": "Beta", "screening": {"ipac": {"status": "ok"}}},
    ]}))
    monkeypatch.setattr(mod, "OUTPUT_PATH", output)
    selected = [{"id": "beta", "plant_name": "Beta", "eia_plant_id": 1,
                 "state": "PA", "status": "retired", "lat": 40.0, "lon": -79.0}]
    mod.write_output(selected, {"beta": {"ipac": {"status": "unavailable"}}}, merge_existing=True)
    written = json.loads(output.read_text())
    assert written["plant_count"] == 2
    assert {p["plant_name"] for p in written["plants"]} == {"Alpha", "Beta"}
    beta = next(p for p in written["plants"] if p["plant_name"] == "Beta")
    assert beta["screening"]["ipac"]["status"] == "unavailable"  # rebuilt row wins


def test_single_plant_rebuild_requires_existing_artifact(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "OUTPUT_PATH", tmp_path / "missing.json")
    try:
        mod.write_output([{"id": "x", "plant_name": "X", "eia_plant_id": None,
                           "state": "PA", "status": "retired", "lat": 1.0, "lon": 2.0}],
                         {}, merge_existing=True)
    except RuntimeError as exc:
        assert "existing complete" in str(exc)
    else:
        raise AssertionError("merge without an existing artifact must fail loud")


def test_generated_artifact_contract():
    payload = json.loads(OUTPUT.read_text())
    assert payload["plant_count"] == 18
    assert payload["nepa_mcp_version"] == "0.1.1"
    assert "agency determination" in " ".join(payload["limitations"])
    for plant in payload["plants"]:
        assert set(plant["screening"]) == EXPECTED_SOURCES, plant["plant_name"]
        for source, section in plant["screening"].items():
            assert section["status"] in {"ok", "unavailable"}, (plant["plant_name"], source)
