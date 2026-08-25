"""Contract tests for the four-site DOE dossier builder and artifacts.

Mirrors test_hanford_e2e.py: module-level tests exercise the curated
rosters and pure helpers on Python 3.9 (no nepa-mcp, no network); artifact
tests pin the shape of the generated docs/data/<site>-e2e.json files the
frontend's multi-site code path and validate_data.py depend on.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "build_doe_sites_e2e.py"
DATA = ROOT / "docs" / "data"

SITE_IDS = ("srs", "portsmouth", "paducah", "wipp")

# The eight-source matrix: Hanford's ten minus the Pacific-marine pair.
EXPECTED_SOURCES = {
    "ipac", "tribal", "nrhp", "padus", "usace", "fema_nfhl", "gbif", "nepa_assist",
}


def _load_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("build_doe_sites_e2e", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_all_site_rosters_validate():
    """validate_site() is the pre-network gate; it must pass on every
    checked-in roster (schema.HanfordParcel + DoeInfrastructureRow live
    validation included)."""
    mod = _load_module()
    total = 0
    for sid in SITE_IDS:
        mod.validate_site(mod.SITES[sid])
        total += len(mod.SITES[sid]["parcels"])
    assert total == 17


def test_facility_fit_cells_all_carry_constraints():
    """2026-08-24 rework contract: every cell names its binding constraint
    so the matrix can render WHY — enforced, not aspirational."""
    mod = _load_module()
    for sid in SITE_IDS:
        for p in mod.SITES[sid]["parcels"]:
            for ff in p["facility_fit"]:
                assert ff.get("constraint"), f"{p['id']}/{ff['type']} missing constraint"


def test_validate_site_rejects_missing_constraint():
    mod = _load_module()
    site = json.loads(json.dumps(mod.SITES["wipp"]))  # deep copy
    del site["parcels"][0]["facility_fit"][0]["constraint"]
    try:
        mod.validate_site(site)
    except SystemExit as exc:
        assert "constraint" in str(exc)
    else:
        raise AssertionError("validate_site accepted a cell without a constraint")


def test_source_matrix_excludes_pacific_marine_tools():
    """The NOAA West Coast critical-habitat and salmon-EFH tools are
    Pacific-scoped (capability census 2026-08); running them at an East or
    interior site would return misleading zeros. The frontend renders screen
    rows only for declared sources, so the declaration IS the contract."""
    mod = _load_module()
    keys = set(mod.SOURCE_META)
    assert "noaa" not in keys
    assert "efh_salmon" not in keys
    assert EXPECTED_SOURCES <= keys
    defs = {d.key for d in mod._source_defs()}
    assert defs == EXPECTED_SOURCES


def test_every_site_has_gas_and_td_infrastructure_rows():
    """The user-directed seven-category vocabulary: natural_gas and power_td
    must exist for every site (the other categories may be honestly omitted
    when no public source exists — e.g. SRS/WIPP fiber)."""
    mod = _load_module()
    for sid in SITE_IDS:
        cats = {r["category"] for r in mod.SITES[sid]["infrastructure"]}
        assert "natural_gas" in cats, f"{sid} missing natural_gas row"
        assert "power_td" in cats, f"{sid} missing power_td row"


def test_every_site_names_something_off_the_table():
    """The honesty rail: each dossier carries at least one parcel precluded
    across all four facility types — a siting tool that only says yes is
    an ad."""
    mod = _load_module()
    for sid in SITE_IDS:
        all_precluded = [
            p["id"] for p in mod.SITES[sid]["parcels"]
            if all(ff["fit"] == "precluded" for ff in p["facility_fit"])
        ]
        assert all_precluded, f"{sid} has no all-precluded parcel"


def test_wipp_large_reactor_is_water_precluded():
    """The signature honest cell: WIPP's LWA balance has land for a large
    reactor but water is fatal (the site's own allocation is 6.6M gal/YEAR
    vs ~20+ MGD for a Vogtle-class unit). Pin the fit AND the constraint."""
    mod = _load_module()
    balance = next(p for p in mod.SITES["wipp"]["parcels"] if p["id"] == "wipp-lwa-balance")
    lwr = next(ff for ff in balance["facility_fit"] if ff["type"] == "lwr_pwr")
    assert lwr["fit"] == "precluded"
    assert lwr["constraint"] == "water"


def test_artifact_payload_contract():
    """Pin the shape every frontend surface and validator depends on."""
    for sid in SITE_IDS:
        payload = json.loads((DATA / f"{sid}-e2e.json").read_text())
        assert payload["site_id"] == sid
        assert payload["site_label"]
        assert "AI-drafted" in payload["narrative_note"]
        assert payload["flood_unmapped_note"]
        assert payload["parcel_count"] == len(payload["parcels"])
        assert set(payload["sources"]) >= EXPECTED_SOURCES
        assert "noaa" not in payload["sources"]
        assert payload["infrastructure"], f"{sid} artifact missing infrastructure"
        for row in payload["infrastructure"]:
            assert row["source_url"].startswith("https://")
            assert len(row["verified_at"]) == 10
        for p in payload["parcels"]:
            assert p["source_url"].startswith("https://")
            for ff in p["facility_fit"]:
                assert ff.get("constraint")


def test_artifact_rows_validate_against_the_live_schema():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import schema as schema_mod

    for sid in SITE_IDS:
        payload = json.loads((DATA / f"{sid}-e2e.json").read_text())
        for parcel in payload["parcels"]:
            schema_mod.HanfordParcel.model_validate(parcel)
        for row in payload["infrastructure"]:
            schema_mod.DoeInfrastructureRow.model_validate(row)


def test_single_parcel_rebuild_preserves_inventory_and_evidence(tmp_path, monkeypatch):
    """The PR #22 empty/partial-write class, applied to the multi-site
    builder: a --parcel refresh must never truncate the dossier to the
    selected rows, and a --skip-screening refresh must never blank a
    parcel's screening evidence or map package."""
    mod = _load_module()
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    site = mod.SITES["wipp"]
    # Seed a complete two-parcel dossier with fake evidence on both rows.
    seeded = {
        "parcels": [
            {
                "id": p["id"],
                "screening": {"ipac": {"status": "ok", "marker": p["id"]}},
                "geojson_url": f"data/wipp-nepa/{p['id']}.geojson",
                "map_summary": {"feature_count": 1, "layers_ok": 14, "layers_partial": 0, "layers_failed": 0},
            }
            for p in site["parcels"]
        ],
    }
    (tmp_path / "wipp-e2e.json").write_text(json.dumps(seeded))
    # Rebuild ONE parcel with no screening/geojson (the curated-text path).
    mod.write_output(
        site, [site["parcels"][1]], {}, {}, {}, [], merge_existing=True,
    )
    out = json.loads((tmp_path / "wipp-e2e.json").read_text())
    assert [p["id"] for p in out["parcels"]] == [p["id"] for p in site["parcels"]]
    rebuilt = next(p for p in out["parcels"] if p["id"] == site["parcels"][1]["id"])
    untouched = next(p for p in out["parcels"] if p["id"] == site["parcels"][0]["id"])
    # Evidence carried forward on the rebuilt row, untouched row intact.
    assert rebuilt["screening"].get("ipac", {}).get("marker") == rebuilt["id"]
    assert rebuilt["geojson_url"] == f"data/wipp-nepa/{rebuilt['id']}.geojson"
    assert untouched["screening"].get("ipac", {}).get("marker") == untouched["id"]


def test_unavailable_map_package_is_not_published(tmp_path, monkeypatch):
    """A wholesale-failed package (empty features + status unavailable)
    must publish NO geojson_url — 'Show 0 features' with a success toast
    would turn an upstream failure into an apparent no-hit."""
    mod = _load_module()
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    site = mod.SITES["wipp"]
    bad = {
        "type": "FeatureCollection",
        "features": [],
        "metadata": {"status": "unavailable", "error": "boom"},
    }
    mod.write_output(
        site, site["parcels"], {},
        {p["id"]: bad for p in site["parcels"]}, {}, [], merge_existing=False,
    )
    out = json.loads((tmp_path / "wipp-e2e.json").read_text())
    for p in out["parcels"]:
        assert p["geojson_url"] is None
        assert p["map_summary"] is None
