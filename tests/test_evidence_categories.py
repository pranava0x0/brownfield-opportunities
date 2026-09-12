"""Evidence contracts: unknown data never becomes suitability or entitlement."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def assess(site, lens="dc"):
    script = "const e=require('./docs/evidence-categories.js'); console.log(JSON.stringify(e.assessSite(JSON.parse(process.argv[1]),process.argv[2], '2026-09-12')));"
    result = subprocess.run(["node", "-e", script, json.dumps(site), lens], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_empty_and_tombstone_do_not_establish_isolation_or_service():
    for site in [None, {}, {"_infraChecked": True, "program": "fuds"}]:
        a = assess(site, "micro")
        for key in ["grid", "grid_capacity", "fiber", "water_reliability", "water_rights", "demand", "regulatory"]:
            assert a[key]["status"] == "unknown"
            assert a[key]["confidence"] is None


def test_substation_only_keeps_evidence_without_borrowing_voltage():
    a = assess({"substation_mi": 0.2, "transmission_mi": 30, "transmission_kv": 500})
    assert "Substation" in a["grid"]["finding"]
    assert "500" not in a["grid"]["finding"]
    assert a["grid_capacity"]["status"] == "unknown"
    assert assess({"substation_mi": 1})["grid"]["status"] == "context"


def test_incompatible_asset_role_is_explicit_and_not_capacity():
    a = assess({"substation_mi": 0.1, "substation_role": "traction", "substation_kv": 0.6})
    assert "traction" in a["grid"]["finding"]
    assert a["grid_capacity"]["status"] == "unknown"


def test_unrelated_fiber_citation_and_analyst_rating_do_not_establish_service():
    a = assess({"fiber": "excellent", "acreage_source": "https://example.org/land"})
    assert a["fiber"]["status"] == "unknown"
    assert not a["fiber"]["sources"]


def test_gage_and_annual_mean_never_establish_supply_or_rights():
    a = assess({"water_gage_mi": 0, "water_flow_cfs": 20000,
                "water_low_flow_cfs": 854, "enforcement": {"has_npdes_permit": True}}, "nickel")
    assert a["water"]["status"] == "context"
    assert a["water"]["confidence"] == "Low"
    assert a["water_reliability"]["status"] == "unknown"
    assert a["water_rights"]["status"] == "unknown"


def test_unknown_land_is_not_a_constraint_and_known_flood_remains_visible():
    a = assess({"in_sfha": True})
    assert a["land"]["status"] == "unknown"
    assert a["hazards"]["status"] == "constraint"


def test_land_sources_skip_owner_labels_and_use_program_source_fallback():
    site = {"acreage": 80.4, "current_owner_source": "USACE FUDS", "profile_url": "https://example.org/site"}
    assert assess(site)["land"]["sources"] == ["https://example.org/site"]
    assert assess({"acreage": 100, "_coreSourceUrl": "https://example.org/program"})["land"]["sources"] == ["https://example.org/program"]
    assert assess({"acreage": 100})["land"]["confidence"] == "Low"
    parcel = {"parcel_acreage": 200, "profile_url": "https://example.org/cleanup", "current_owner_source": "https://example.org/parcel"}
    assert assess(parcel)["land"]["sources"] == ["https://example.org/parcel"]


def test_invalid_numeric_values_are_unknown():
    for value in [-1, "0.1", float("nan"), float("inf")]:
        # JSON cannot represent non-finite numbers; exercise those in node below.
        if isinstance(value, float):
            continue
        assert assess({"transmission_mi": value, "acreage": value})["grid"]["status"] == "unknown"
    script = "const e=require('./docs/evidence-categories.js'); for(const n of [NaN,Infinity]) if(e.assessSite({transmission_mi:n}).grid.status!=='unknown') process.exit(1);"
    subprocess.run(["node", "-e", script], cwd=ROOT, check=True)


def test_confidence_tracks_source_age_and_proxy_geometry():
    base = {"transmission_mi": 1, "infra_evidence": {"transmission": {
        "status": "matched_context", "source_url": "https://example.org/grid", "snapshot_at": "2026-08-01"}}}
    assert assess(base)["grid"]["confidence"] == "Medium"
    base["infra_evidence"]["transmission"]["snapshot_at"] = "2020-01-01"
    assert assess(base)["grid"]["confidence"] == "Low"
    base["infra_source_id"] = "proxy"
    assert "reference point" in assess(base)["grid"]["reason"]


def test_no_total_and_consistent_shared_categories_between_lenses():
    site = {"transmission_mi": 1, "water_gage_mi": 4, "water_flow_cfs": 40, "acreage": 100}
    baseline = assess(site)
    assert "total" not in baseline and "score" not in baseline
    for lens in ["gen", "mfg", "micro", "ap1000", "nickel", "maritime"]:
        other = assess(site, lens)
        for key in ["grid", "fiber", "water", "land", "logistics"]:
            assert baseline[key] == other[key]


def test_retained_or_failed_mapping_never_gets_recent_confidence():
    site = {"transmission_mi": 1, "infra_evidence": {"transmission": {
        "status": "retained_previous", "source_snapshot_at": "2026-09-01"}}}
    assert assess(site)["grid"]["confidence"] == "Low"


def test_coordinate_flags_reduce_confidence_and_are_explained():
    site = {"transmission_mi": 1, "coord_flags": ["state_mismatch"],
            "infra_evidence": {"transmission": {"source_snapshot_at": "2026-09-01"}}}
    assert assess(site)["grid"]["confidence"] == "Low"
    assert "coordinate" in assess(site)["grid"]["reason"].lower()


def test_water_statistic_and_period_not_mislabeled_as_low_flow():
    a = assess({"water_gage_mi": 2, "water_flow_cfs": 854.1,
                "water_statistic": "mean_of_annual_means", "water_gage_record_start_year": 1990,
                "water_gage_record_end_year": 2020, "water_gage_record_years": 28})
    assert "1990" in a["water"]["reason"] and "2020" in a["water"]["reason"]
    assert "mean of annual means" in a["water"]["reason"]
    assert a["water_reliability"]["status"] == "unknown"
