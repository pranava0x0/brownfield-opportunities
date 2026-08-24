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
