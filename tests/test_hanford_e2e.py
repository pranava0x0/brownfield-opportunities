"""Contract tests for the Hanford E2E dossier builder and artifact.

Split mirrors test_janus_nepa.py: module-level tests exercise the curated
roster and pure helpers on Python 3.9 (no nepa-mcp, no network); artifact
tests pin the shape of the generated docs/data/hanford-e2e.json every
frontend surface and validate_data.py check depends on.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_hanford_e2e.py"
OUTPUT = ROOT / "docs" / "data" / "hanford-e2e.json"

EXPECTED_SOURCES = {
    "ipac", "noaa", "efh_salmon", "tribal", "nrhp",
    "padus", "usace", "fema_nfhl", "gbif", "nepa_assist",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("build_hanford_e2e", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parcel_roster_is_unique_cited_and_schema_valid():
    """validate_parcels() is the builder's pre-network gate; it must pass on
    the checked-in roster (and it validates against schema.HanfordParcel, so
    a curated-field typo fails here before any network spend)."""
    mod = _load_module()
    mod.validate_parcels()
    ids = [p["id"] for p in mod.PARCELS]
    assert len(ids) == len(set(ids)) == 9


def test_every_opportunity_fit_vocabulary_value_is_used():
    """The dossier's honesty depends on all four fits existing in the data —
    especially 'precluded': a siting tool that only ever says yes is an ad."""
    mod = _load_module()
    fits = {o["fit"] for p in mod.PARCELS for o in p["opportunities"]}
    assert fits == {"anchored", "strong", "conditional", "precluded"}


def test_corpus_join_targets_the_four_hanford_npl_records():
    mod = _load_module()
    joined = {p["corpus_site_id"] for p in mod.PARCELS if p["corpus_site_id"]}
    assert joined == {"WA3890090076", "WA1890090078", "WA2890090077", "WA4890090075"}


def test_nearby_search_prefilters_and_excludes_self_join():
    mod = _load_module()
    parcel = {"id": "x", "lat": 46.55, "lon": -119.50, "corpus_site_id": "SELF"}
    records = [
        {"id": "SELF", "name": "same record", "program": "superfund", "lat": 46.55, "lon": -119.50},
        {"id": "NEAR", "name": "near", "program": "fuds", "lat": 46.56, "lon": -119.51},
        {"id": "FAR", "name": "far", "program": "fuds", "lat": 40.0, "lon": -100.0},
        {"id": "NOLL", "name": "no coords", "program": "fuds", "lat": None, "lon": None},
    ]
    out = mod.nearby_tracked_records(parcel, records)
    assert [r["id"] for r in out] == ["NEAR"]
    assert out[0]["distance_mi"] < 1.5


def test_corpus_index_merge_is_fill_if_empty():
    """The join must mirror the frontend's ensure*Loaded() semantics — an
    enrichment value never overwrites a program-record value (the 2026-08-09
    merged-view lesson: a checker that models the merge differently
    manufactures findings)."""
    mod = _load_module()
    by_id = {"A": {"id": "A", "acreage": 10, "transmission_mi": None}}
    # simulate the enrichment loop body
    enrichment = {"id": "A", "acreage": 999, "transmission_mi": 1.2}
    existing = by_id["A"]
    for key, value in enrichment.items():
        if key == "id" or value is None:
            continue
        if existing.get(key) is None:
            existing[key] = value
    assert existing["acreage"] == 10          # program value kept
    assert existing["transmission_mi"] == 1.2  # absence filled


def test_generated_payload_contract():
    payload = json.loads(OUTPUT.read_text())
    assert payload["parcel_count"] == 9
    assert payload["nepa_mcp_version"] == "0.1.1"
    assert payload["screening_buffer_miles"] == 5.0
    assert len(payload["permitting_pathways"]) == 8
    assert "agency determination" in " ".join(payload["limitations"])
    for parcel in payload["parcels"]:
        assert set(parcel["screening"]) == EXPECTED_SOURCES, parcel["id"]
        for source, section in parcel["screening"].items():
            assert section["status"] in {"ok", "unavailable"}, (parcel["id"], source)
        assert parcel["source_url"].startswith("https://")
        assert len(parcel["verified_at"]) == 10


def test_generated_geojson_packages_exist_and_carry_metadata():
    payload = json.loads(OUTPUT.read_text())
    for parcel in payload["parcels"]:
        assert parcel["geojson_url"], parcel["id"]
        geo_path = ROOT / "docs" / parcel["geojson_url"]
        assert geo_path.exists(), parcel["id"]
        geo = json.loads(geo_path.read_text())
        assert geo["type"] == "FeatureCollection"
        assert geo["metadata"]["site_id"] == parcel["id"]
        assert "eis_boundaries" in geo["metadata"]["layers"], (
            "the EPA EIS-boundaries layer is the NEPA-precedent layer this "
            "dossier exists to demonstrate — it must be part of every package"
        )


def test_npl_parcels_carry_corpus_grid_joins():
    payload = json.loads(OUTPUT.read_text())
    for parcel in payload["parcels"]:
        if parcel.get("corpus_site_id"):
            corpus = parcel.get("corpus_record") or {}
            assert corpus.get("transmission_mi") is not None, parcel["id"]
            assert corpus.get("npl_status"), parcel["id"]


def test_artifact_rows_validate_against_the_live_schema():
    """Same live-contract discipline as the coal overlays: the schema class
    must actually validate the shipped rows, not just exist."""
    sys.path.insert(0, str(ROOT))
    try:
        import schema as schema_mod
    finally:
        sys.path.pop(0)
    payload = json.loads(OUTPUT.read_text())
    for parcel in payload["parcels"]:
        schema_mod.HanfordParcel.model_validate(parcel)


def test_single_parcel_rebuild_preserves_complete_inventory(tmp_path, monkeypatch):
    """--parcel must merge into the existing dossier, never truncate it to
    the selected rows (Codex PR #22 P1 — the Janus --site contract)."""
    mod = _load_module()
    output = tmp_path / "hanford-e2e.json"
    geojson_dir = tmp_path / "geojson"
    output.write_text(json.dumps({"parcels": [
        {"id": "hanford-100-area", "name": "Keep", "screening": {}},
        {"id": "hanford-200-area", "name": "Old", "screening": {}},
    ]}))
    monkeypatch.setattr(mod, "OUTPUT_PATH", output)
    monkeypatch.setattr(mod, "GEOJSON_DIR", geojson_dir)
    selected = [dict(p) for p in mod.PARCELS if p["id"] == "hanford-200-area"]
    mod.write_output(selected, {"hanford-200-area": {}}, {}, {}, [], merge_existing=True)
    written = json.loads(output.read_text())
    assert written["parcel_count"] == 2
    assert {p["id"] for p in written["parcels"]} == {"hanford-100-area", "hanford-200-area"}
    rebuilt = next(p for p in written["parcels"] if p["id"] == "hanford-200-area")
    assert rebuilt["name"] != "Old"
    # Curated PARCELS order is preserved (100 before 200).
    assert [p["id"] for p in written["parcels"]][:2] == ["hanford-100-area", "hanford-200-area"]


def test_single_parcel_rebuild_requires_existing_dossier(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "OUTPUT_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(mod, "GEOJSON_DIR", tmp_path / "geojson")
    try:
        mod.write_output([dict(mod.PARCELS[0])], {}, {}, {}, [], merge_existing=True)
    except RuntimeError as exc:
        assert "existing complete" in str(exc)
    else:
        raise AssertionError("merge without an existing dossier must fail loud")


def test_unavailable_map_package_is_not_published(tmp_path, monkeypatch):
    """A wholesale-failed package (empty features + metadata.status
    'unavailable') must publish NO geojson_url — 'Show 0 features' with a
    success toast would turn an upstream failure into an apparent no-hit
    (Codex PR #22 P2)."""
    mod = _load_module()
    monkeypatch.setattr(mod, "OUTPUT_PATH", tmp_path / "hanford-e2e.json")
    monkeypatch.setattr(mod, "GEOJSON_DIR", tmp_path / "geojson")
    parcel = dict(mod.PARCELS[0])
    failed = {"type": "FeatureCollection", "features": [],
              "metadata": {"status": "unavailable", "error": "boom"}}
    mod.write_output([parcel], {parcel["id"]: {}}, {parcel["id"]: failed}, {}, [])
    written = json.loads((tmp_path / "hanford-e2e.json").read_text())
    row = written["parcels"][0]
    assert row["geojson_url"] is None
    assert row["map_summary"] is None
    # A legitimately EMPTY package (no unavailable marker) still publishes.
    empty_ok = {"type": "FeatureCollection", "features": [],
                "metadata": {"site_id": parcel["id"], "layers": {"roi": {"status": "empty"}}}}
    mod.write_output([parcel], {parcel["id"]: {}}, {parcel["id"]: empty_ok}, {}, [])
    written = json.loads((tmp_path / "hanford-e2e.json").read_text())
    assert written["parcels"][0]["geojson_url"] is not None


def test_skip_screening_parcel_refresh_carries_evidence_forward(tmp_path, monkeypatch):
    """--parcel + --skip-screening (a curated-text-only refresh) must not
    blank the rebuilt parcel's screen or map package — prior evidence
    survives until replaced (PR #22 review finding 2, flood-seed pattern)."""
    mod = _load_module()
    output = tmp_path / "hanford-e2e.json"
    prev_screening = {"ipac": {"status": "ok", "counts": {"listed_species": 4}}}
    output.write_text(json.dumps({"parcels": [
        {"id": "hanford-100-area", "name": "Keep", "screening": {"x": 1},
         "geojson_url": "data/hanford-nepa/hanford-100-area.geojson"},
        {"id": "hanford-200-area", "name": "Old", "screening": prev_screening,
         "geojson_url": "data/hanford-nepa/hanford-200-area.geojson",
         "map_summary": {"feature_count": 34}},
    ]}))
    monkeypatch.setattr(mod, "OUTPUT_PATH", output)
    monkeypatch.setattr(mod, "GEOJSON_DIR", tmp_path / "geojson")
    selected = [dict(p) for p in mod.PARCELS if p["id"] == "hanford-200-area"]
    # Empty tabular + geojson maps == what --skip-screening passes through.
    mod.write_output(selected, {}, {}, {}, [], merge_existing=True)
    written = json.loads(output.read_text())
    rebuilt = next(p for p in written["parcels"] if p["id"] == "hanford-200-area")
    assert rebuilt["name"] != "Old"                       # curation refreshed
    assert rebuilt["screening"] == prev_screening         # evidence preserved
    assert rebuilt["geojson_url"] == "data/hanford-nepa/hanford-200-area.geojson"
    assert rebuilt["map_summary"] == {"feature_count": 34}


def test_validate_parcels_rejects_a_row_missing_opportunities(monkeypatch):
    """The pre-network gate must let Pydantic's required-field check fire —
    no silent defaulting (PR #22 review finding 3)."""
    mod = _load_module()
    broken = [dict(p) for p in mod.PARCELS]
    del broken[0]["opportunities"]
    monkeypatch.setattr(mod, "PARCELS", broken)
    try:
        mod.validate_parcels()
    except Exception as exc:
        assert "opportunities" in str(exc)
    else:
        raise AssertionError("a parcel without opportunities must fail validation")
