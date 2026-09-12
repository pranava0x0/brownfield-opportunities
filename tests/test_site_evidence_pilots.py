from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_site_evidence_pilots.py"
DATA = ROOT / "docs" / "data" / "site-evidence-pilots.json"


def _load():
    spec = importlib.util.spec_from_file_location("build_site_evidence_pilots", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_checked_in_pilot_matches_builder():
    assert json.loads(DATA.read_text()) == _load().build_payload()


def test_pilot_keeps_context_separate_from_service_and_supply():
    rec = _load().RECORDS[0]
    assert rec["water_network"]["status"] == "network_context"
    assert rec["water_network"]["feature_id"]
    assert "rights" in rec["water_network"]["unresolved"]
    assert rec["fiber_regional"]["evidence_scope"] == "regional"
    for unsupported in ("serviceable", "available_capacity", "route_diversity"):
        assert unsupported not in rec["fiber_regional"]
