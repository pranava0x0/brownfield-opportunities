"""Drift guards between the provenance registry and the schema it describes.

`docs/provenance.js` is the chain of evidence: it claims to say where every
value on a record came from. Two ways that claim quietly becomes false:

  1. A registry key is misspelled or renamed out from under it. `buildEvidence`
     emits a row only when the site carries that key, so a typo produces no
     row and no error — the field simply stops being cited, invisibly.
  2. A new user-visible field ships with no registry entry, so the panel shows
     a number nobody can trace.

Both are caught here rather than in review. The registry is JavaScript because
the browser renders it, so these tests `require()` the real module instead of
reimplementing it — a Python copy of the registry would be the single thing
most likely to drift away from what users actually see.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROVENANCE_JS = ROOT / "docs" / "provenance.js"

HARNESS = r"""
const prov = require(process.argv[2]);
process.stdout.write(JSON.stringify({
  keys: Object.keys(prov.FIELD_PROVENANCE),
  specs: Object.fromEntries(Object.entries(prov.FIELD_PROVENANCE).map(
    ([k, v]) => [k, {
      group: v.group || null,
      label: v.label || null,
      hasDerivation: !!(v.derivation || v.derivationByProgram),
      byProgram: !!v.byProgram,
      publisher: v.publisher || null,
      code: v.code || null,
    }])),
}));
"""


@pytest.fixture(scope="module")
def registry():
    if shutil.which("node") is None:
        pytest.skip("node not available")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(HARNESS)
        harness = fh.name
    proc = subprocess.run(["node", harness, str(PROVENANCE_JS)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def schema_fields():
    from schema import SiteRecord
    return set(SiteRecord.model_fields)


def test_every_registry_key_is_a_real_schema_field(registry, schema_fields):
    """A typo'd key silently stops citing its field — no row, no error."""
    unknown = [k for k in registry["keys"] if k not in schema_fields]
    assert not unknown, (
        f"provenance.js cites fields that do not exist on SiteRecord: {unknown}. "
        "These produce no evidence row and fail silently."
    )


# Fields a reader would reasonably ask "says who?" about. Anything here that
# loses its registry entry stops being traceable, which is the whole point of
# the panel. Extend this when a new user-visible claim ships.
MUST_BE_CITED = {
    "name", "state", "city", "lat", "acreage",
    "transmission_mi", "substation_mi", "power_plant_mi", "gas_pipeline_mi",
    "rail_mi", "highway_mi", "flood_zone",
    "retired_plant_mi", "planned_retirement_mi",
    "in_opportunity_zone", "in_energy_community", "in_aiannha_area",
    "county_construction_employment", "nri_risk_rating",
    "iso_rto", "climate_zone",
    "current_owner", "enforcement", "documents", "cleanup_status",
    "data_center_reuse_candidate", "summary", "coord_flags",
}


def test_all_user_visible_claims_are_cited(registry):
    missing = sorted(MUST_BE_CITED - set(registry["keys"]))
    assert not missing, (
        f"these fields are shown to users but have no provenance entry: {missing}"
    )


def test_every_entry_states_a_publisher_and_a_derivation(registry):
    """A source without a derivation is a citation the reader can't judge."""
    bad = []
    for key, spec in registry["specs"].items():
        # byProgram entries inherit their publisher from PROGRAM_SOURCE.
        if not spec["byProgram"] and not spec["publisher"]:
            bad.append(f"{key}: no publisher")
        if not spec["hasDerivation"]:
            bad.append(f"{key}: no derivation")
        if not spec["label"] or not spec["group"]:
            bad.append(f"{key}: no label/group")
    assert not bad, bad


def test_derived_values_cite_the_code_that_produced_them(registry):
    """A computed field must not read as agency data."""
    for key in ("coord_flags", "summary"):
        spec = registry["specs"][key]
        assert spec["code"], f"{key} is derived but cites no source code"
        assert "project" in (spec["publisher"] or "").lower(), (
            f"{key} must be attributed to this project, not to an agency"
        )


# Sub-fields deliberately covered by a parent row rather than their own.
COVERED_BY_PARENT = {
    "transmission_kv": "transmission_mi", "substation_kv": "substation_mi",
    "power_plant_mw": "power_plant_mi", "power_plant_fuel": "power_plant_mi",
    "power_plant_retired": "power_plant_mi",
    "retired_plant_mw": "retired_plant_mi", "retired_plant_fuel": "retired_plant_mi",
    "retired_plant_year": "retired_plant_mi", "retired_plant_name": "retired_plant_mi",
    "planned_retirement_mw": "planned_retirement_mi",
    "planned_retirement_fuel": "planned_retirement_mi",
    "planned_retirement_year": "planned_retirement_mi",
    "planned_retirement_name": "planned_retirement_mi",
    "coal_conversion_plant_mi": "coal_conversion_plant_name",
    "coal_conversion_mw": "coal_conversion_plant_name",
    "coal_conversion_switchyard_kv": "coal_conversion_plant_name",
    "coal_conversion_stranded_val_usd": "coal_conversion_plant_name",
    "coal_conversion_queue_fasttrack": "coal_conversion_plant_name",
    "in_sfha": "flood_zone",
    "oz_tract_geoid": "in_opportunity_zone", "oz_rural": "in_opportunity_zone",
    "energy_community_type": "in_energy_community",
    "energy_community_detail": "in_energy_community",
    "aiannha_area_count": "in_aiannha_area", "aiannha_areas": "in_aiannha_area",
    "county_labor_force": "county_construction_employment",
    "county_median_household_income": "county_construction_employment",
    "workforce_county": "county_construction_employment",
    "workforce_data_year": "county_construction_employment",
    "nri_risk_score": "nri_risk_rating", "nri_wildfire_rating": "nri_risk_rating",
    "nri_drought_rating": "nri_risk_rating", "nri_heatwave_rating": "nri_risk_rating",
    "county": "city", "address": "city", "zip": "city",
    "current_owner_source": "current_owner",
    "parcel_acreage": "acreage", "parcel_id": "acreage",
    "lon": "lat",
    "grant_total_usd": "cleanup_status", "grant_count": "cleanup_status",
    "grant_types": "cleanup_status", "cleanup_complete_date": "cleanup_status",
    "summary_meta": "summary",
    "coord_actual_state": "coord_flags", "coord_state_gap_mi": "coord_flags",
    "coord_shared_count": "coord_flags",
    "port_name": "port_mi", "port_type": "port_mi", "port_hurricane_freq": "port_mi",
    "shipyard_name": "shipyard_mi", "shipyard_capability": "shipyard_mi",
}

# Internal plumbing — identifiers, program-specific labels already shown with
# their own source context, and EPA RE-Powering's qualitative flags, which are
# cited as a group by `data_center_reuse_candidate`.
INTERNAL = {
    "id", "program", "epa_id", "parent_epa_id", "children",
    "npl_status", "npl_status_code", "federal_facility",
    "federal_facility_code", "region", "profile_url", "last_updated",
    "eligibility", "fuds_status", "has_projects", "congressional_district",
    "component", "in_reuse", "in_opp_zone", "rau_status", "pop_density",
    "near_electric_transmission", "near_highway", "near_railroad",
    "near_water_supply", "near_wastewater", "near_water_body",
    "historical_owners", "encumbrances", "remediation_detail",
}


def test_parent_rows_for_covered_subfields_exist(registry):
    cited = set(registry["keys"])
    for key, parent in COVERED_BY_PARENT.items():
        assert parent in cited, (
            f"{key} is documented as covered by {parent}, but {parent} is not cited"
        )


def test_no_rendered_schema_field_is_left_uncited(registry, schema_fields):
    """Reverse drift: a field the panel renders but nothing explains.

    Scoped to fields app.js actually reads off a site, so internal plumbing
    doesn't force a citation — but anything new and user-facing does.
    """
    app_js = (ROOT / "docs" / "app.js").read_text()
    referenced = set(re.findall(r"\bs\.([a-z_][a-z0-9_]*)\b", app_js))
    rendered = referenced & schema_fields
    uncited = sorted(
        rendered - set(registry["keys"]) - set(COVERED_BY_PARENT) - INTERNAL
    )
    assert not uncited, (
        f"app.js renders these schema fields but provenance.js does not cite "
        f"them: {uncited}. Add a registry entry, or list the field in INTERNAL "
        f"with a reason if it is genuinely not a user-facing claim."
    )
