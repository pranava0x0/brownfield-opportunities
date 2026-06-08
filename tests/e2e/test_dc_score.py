"""End-to-end tests for the two site-suitability scoring lenses.

The score functions live in `docs/dc-score.js` and expose, on `window`:
  computeDcCompositeScore / computeDcScoreBreakdown          (data-center load)
  computeGenerationScore / computeGenerationScoreBreakdown   (new generation)
  DC_SCORE_WEIGHTS / DC_SCORE_TOOLTIP
  GENERATION_SCORE_WEIGHTS / GENERATION_SCORE_TOOLTIP
  FLOOD_SFHA_PENALTY

These tests load the page (which sources the script) and call the
functions with synthetic record payloads via `page.evaluate`, then assert
on the returned values. This is a logic test of the formula, not a
data-quality test of specific real-world records (those drift on refresh).

v2 (this file): the DC score now folds in substation proximity,
power-plant co-location, and a Special-Flood-Hazard-Area penalty — the
v1.13.3 signals that were on disk but unused. A second lens scores siting
for new power *generation* with a land/interconnection/market weighting.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


# -- Helpers ----------------------------------------------------------------

def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function(
        "typeof window.computeDcCompositeScore === 'function'"
        " && typeof window.computeGenerationScore === 'function'",
        timeout=10_000,
    )


def _dc(page: Page, record: dict) -> int | None:
    return page.evaluate("(r) => window.computeDcCompositeScore(r)", record)


def _dc_bd(page: Page, record: dict) -> dict | None:
    return page.evaluate("(r) => window.computeDcScoreBreakdown(r)", record)


def _gen(page: Page, record: dict) -> int | None:
    return page.evaluate("(r) => window.computeGenerationScore(r)", record)


def _gen_bd(page: Page, record: dict) -> dict | None:
    return page.evaluate("(r) => window.computeGenerationScoreBreakdown(r)", record)


# -- Module surface --------------------------------------------------------

def test_module_exposes_both_lenses(page, base_url):
    _ready(page, base_url)
    has = page.evaluate(
        "() => ({"
        "  dc: typeof window.computeDcCompositeScore,"
        "  dcBrk: typeof window.computeDcScoreBreakdown,"
        "  gen: typeof window.computeGenerationScore,"
        "  genBrk: typeof window.computeGenerationScoreBreakdown,"
        "  dcW: typeof window.DC_SCORE_WEIGHTS,"
        "  genW: typeof window.GENERATION_SCORE_WEIGHTS,"
        "  dcTip: typeof window.DC_SCORE_TOOLTIP,"
        "  genTip: typeof window.GENERATION_SCORE_TOOLTIP,"
        "  penalty: window.FLOOD_SFHA_PENALTY"
        "})"
    )
    assert has["dc"] == "function"
    assert has["dcBrk"] == "function"
    assert has["gen"] == "function"
    assert has["genBrk"] == "function"
    assert has["dcW"] == "object"
    assert has["genW"] == "object"
    assert has["dcTip"] == "string"
    assert has["genTip"] == "string"
    assert has["penalty"] == 18


def test_weight_tables_each_sum_to_100(page, base_url):
    """Both lenses are designed so the positive component caps sum to
    exactly 100; the flood penalty (a separate negative) pushes below."""
    _ready(page, base_url)
    sums = page.evaluate(
        "() => ({"
        "  dc: Object.values(window.DC_SCORE_WEIGHTS).reduce((a,b)=>a+b,0),"
        "  gen: Object.values(window.GENERATION_SCORE_WEIGHTS).reduce((a,b)=>a+b,0)"
        "})"
    )
    assert sums["dc"] == 100, f"DC weights sum {sums['dc']} != 100"
    assert sums["gen"] == 100, f"generation weights sum {sums['gen']} != 100"


# -- Gate (null transmission) ----------------------------------------------

def test_null_transmission_yields_null_for_both(page, base_url):
    """Transmission is the load-bearing signal for both lenses — no grid
    means a DC can't be powered and new generation can't export. Score is
    null (not assessable), not 0 (assessed as bad)."""
    _ready(page, base_url)
    rec = {"acreage": 1000, "transmission_mi": None, "transmission_kv": 500}
    assert _dc(page, rec) is None
    assert _gen(page, rec) is None


def test_null_site_yields_null(page, base_url):
    _ready(page, base_url)
    assert _dc(page, None) is None
    assert _gen(page, None) is None


# -- All-max records -------------------------------------------------------

def test_dc_all_max_record_scores_100(page, base_url):
    """A record that maxes every DC component (including grid inheritance,
    substation, and rural OZ readiness) lands at exactly 100."""
    _ready(page, base_url)
    rec = {
        "transmission_mi": 0.0, "transmission_kv": 500,
        "substation_mi": 0.0,
        "power_plant_mi": 0.5, "power_plant_mw": 600, "power_plant_fuel": "Natural Gas",
        "acreage": 1000, "gas_pipeline_mi": 0.0,
        "highway_mi": 0.5, "rail_mi": 0.5,
        "data_center_reuse_candidate": True,
        "npl_status_code": "D", "in_reuse": "Yes",
        "in_opportunity_zone": True,
    }
    assert _dc(page, rec) == 100


def test_generation_all_max_record_scores_100(page, base_url):
    _ready(page, base_url)
    rec = {
        "transmission_mi": 0.0, "transmission_kv": 500,
        "substation_mi": 0.0, "acreage": 2000,
        "gas_pipeline_mi": 0.0, "iso_rto": "PJM",
        "npl_status_code": "D", "in_opportunity_zone": True,
    }
    assert _gen(page, rec) == 100


def test_scores_clamp_to_0_100(page, base_url):
    _ready(page, base_url)
    weak = {"transmission_mi": 5.0, "transmission_kv": None, "acreage": None}
    dc = _dc(page, weak)
    gen = _gen(page, weak)
    assert dc is not None and 0 <= dc <= 100
    assert gen is not None and 0 <= gen <= 100


# -- DC per-component coverage ---------------------------------------------

@pytest.mark.parametrize("mi,expected", [
    (0.0, 16), (0.05, 16), (1.0, 8), (2.0, 0), (5.0, 0),
])
def test_dc_transmission_distance_component(page, base_url, mi, expected):
    _ready(page, base_url)
    assert _dc_bd(page, {"transmission_mi": mi})["transmission_distance"] == expected


@pytest.mark.parametrize("kv,expected", [
    (None, 0), (50, 3), (69, 6), (138, 8), (230, 11), (500, 14), (765, 14),
])
def test_dc_voltage_component(page, base_url, kv, expected):
    _ready(page, base_url)
    bd = _dc_bd(page, {"transmission_mi": 0.5, "transmission_kv": kv})
    assert bd["voltage"] == expected


@pytest.mark.parametrize("mi,expected", [
    (None, 0), (0.3, 12), (0.5, 12), (2.0, 9), (5.0, 6), (10.0, 3), (20.0, 0),
])
def test_dc_substation_component(page, base_url, mi, expected):
    """NEW in v2 — interconnection feasibility. 99% coverage on disk."""
    _ready(page, base_url)
    bd = _dc_bd(page, {"transmission_mi": 0.5, "substation_mi": mi})
    assert bd["substation"] == expected


@pytest.mark.parametrize("fuel,mw,mi,expected", [
    ("Natural Gas", 600, 0.5, 8),  # qualifies: gas ≥500 MW ≤1 mi
    ("Natural Gas", 600, 1.0, 8),  # exactly at 1 mi boundary
    ("Natural Gas", 600, 1.1, 0),  # just over 1 mi → no points
    ("Natural Gas", 400, 0.5, 0),  # MW too small (status unknown)
    ("Hydro",       600, 0.5, 0),  # wrong fuel type (hydro not scored)
    ("Coal",        500, 0.5, 8),  # coal qualifies
    (None,          600, 0.5, 0),  # no fuel → no points
    # v1.17: operating nuclear pathway (AWS/Susquehanna pattern)
    # Active nuclear ≥500 MW within 5 mi → 45% of cap (PPA/grid-neighborhood signal)
    ("nuclear",     600, 0.5, 4),  # nuclear at 0.5 mi → round(8*0.45)=4
    ("nuclear",     600, 5.0, 4),  # nuclear at boundary 5 mi → still qualifies
    ("nuclear",     600, 5.1, 0),  # just over 5 mi → no points
    ("nuclear",     400, 0.5, 0),  # nuclear below 500 MW floor → no points
])
def test_dc_grid_inheritance_component(page, base_url, fuel, mw, mi, expected):
    """Grid inheritance: large coal/gas ≥500 MW within 1 mi = full 8 pts;
    operating nuclear ≥500 MW within 5 mi = 45% of cap (4 pts) — the
    AWS/Talen Susquehanna PPA pattern; other fuels/distances = 0."""
    _ready(page, base_url)
    rec = {"transmission_mi": 0.5, "power_plant_mi": mi, "power_plant_mw": mw}
    if fuel is not None:
        rec["power_plant_fuel"] = fuel
    bd = _dc_bd(page, rec)
    assert bd["grid_inheritance"] == expected


@pytest.mark.parametrize("fuel,mw,use_retired_src,expected", [
    # EIA-860M retired plant (retired_plant_* fields): lower MW floor ≥100,
    # any dispatchable fuel qualifies.
    ("BIT",         300, True,  8),   # retired coal 300 MW — qualifies
    ("NG",          100, True,  8),   # retired gas at minimum MW floor
    ("NUC",         200, True,  8),   # retired nuclear — qualifies (San Onofre pattern)
    ("NG",           99, True,  0),   # retired but below 100 MW floor
    ("NG",          600, True,  8),   # retired large gas — also qualifies
    ("SUN",         500, True,  0),   # retired solar — non-dispatchable, no points
    ("WND",         400, True,  0),   # retired wind — non-dispatchable
    # HIFLD active plant fallback (power_plant_* fields, no retired_plant_*):
    # original strict ≥500 MW coal/natural gas rule.
    ("coal",        300, False, 0),   # active small coal → doesn't qualify
    ("natural gas", 500, False, 8),   # active large gas → qualifies (old rule)
])
def test_dc_grid_inheritance_retired_vs_operating(page, base_url, fuel, mw, use_retired_src, expected):
    """v1.15: EIA-860M retired plants (`retired_plant_*` fields) qualify at
    ≥100 MW for any dispatchable fuel; HIFLD active-plant fallback keeps the
    original ≥500 MW coal/gas rule."""
    _ready(page, base_url)
    rec = {"transmission_mi": 0.5}
    if use_retired_src:
        # Use EIA-860M retired-plant fields — no power_plant_* set
        rec["retired_plant_mi"] = 0.5
        rec["retired_plant_mw"] = mw
        rec["retired_plant_fuel"] = fuel
    else:
        # Use HIFLD active-plant fallback
        rec["power_plant_mi"] = 0.5
        rec["power_plant_mw"] = mw
        rec["power_plant_fuel"] = fuel
    bd = _dc_bd(page, rec)
    assert bd["grid_inheritance"] == expected


@pytest.mark.parametrize("acres,expected", [
    (None, 0), (1, 1), (5, 5), (25, 11), (100, 16), (500, 20), (50_000, 20),
])
def test_dc_acreage_component(page, base_url, acres, expected):
    _ready(page, base_url)
    bd = _dc_bd(page, {"transmission_mi": 0.5, "acreage": acres})
    assert bd["acreage"] == expected


@pytest.mark.parametrize("mi,expected", [
    (None, 0), (0.0, 10), (1.0, 8), (5.0, 6), (15.0, 3), (30.0, 0),
])
def test_dc_gas_pipeline_component(page, base_url, mi, expected):
    _ready(page, base_url)
    bd = _dc_bd(page, {"transmission_mi": 0.5, "gas_pipeline_mi": mi})
    assert bd["gas_pipeline"] == expected


@pytest.mark.parametrize("hwy,rail,expected", [
    (None, None, 0), (1.0, None, 3), (None, 1.0, 3), (1.0, 1.0, 6),
    (5.0, 5.0, 4), (15.0, 15.0, 1), (50.0, 50.0, 0), (0.5, 0.5, 6),
])
def test_dc_logistics_component(page, base_url, hwy, rail, expected):
    _ready(page, base_url)
    bd = _dc_bd(page, {"transmission_mi": 0.5, "highway_mi": hwy, "rail_mi": rail})
    assert bd["logistics"] == expected


def test_dc_readiness_caps_at_14(page, base_url):
    """All readiness sub-signals together (DC flag 5 + cleanup 3 + reuse 2 +
    rural OZ 7 = 17) are capped at the component max of 14."""
    _ready(page, base_url)
    rec = {
        "transmission_mi": 0.5,
        "data_center_reuse_candidate": True,
        "npl_status_code": "D",
        "in_reuse": "Yes",
        "in_opportunity_zone": True,
        "oz_rural": True,
    }
    assert _dc_bd(page, rec)["readiness"] == 14


def test_oz_rural_bonus_higher_than_standard_oz(page, base_url):
    """Rural OZ scores +7; non-rural OZ scores +5 — the extra 2 pts reflect
    the 30% vs 15% QOF basis step-up premium for designated rural tracts."""
    _ready(page, base_url)
    base = {"transmission_mi": 0.5, "in_opportunity_zone": True}
    rural = _dc_bd(page, dict(base, oz_rural=True))["readiness"]
    non_rural = _dc_bd(page, base)["readiness"]
    assert rural == 7
    assert non_rural == 5
    assert rural > non_rural


def test_eo14318_readiness_bonus(page, base_url):
    """EO 14318 eligible sites (superfund/brownfield, ≥100 ac, grid ≤2 mi,
    outside SFHA) earn +3 readiness pts; ineligible combos earn 0."""
    _ready(page, base_url)
    eligible = {
        "transmission_mi": 1.0, "program": "superfund",
        "acreage": 200, "in_sfha": False,
    }
    assert _dc_bd(page, eligible)["readiness"] == 3

    # FUDS is not covered by EO 14318
    ineligible_prog = dict(eligible, program="fuds")
    assert _dc_bd(page, ineligible_prog)["readiness"] == 0

    # Under 100 acres
    ineligible_small = dict(eligible, acreage=50)
    assert _dc_bd(page, ineligible_small)["readiness"] == 0

    # Grid too far
    ineligible_far = dict(eligible, transmission_mi=3.0)
    assert _dc_bd(page, ineligible_far)["readiness"] == 0

    # In SFHA
    ineligible_flood = dict(eligible, in_sfha=True)
    assert _dc_bd(page, ineligible_flood)["readiness"] == 0


def test_dc_energy_community_readiness_bonus(page, base_url):
    """An IRA energy community earns +3 DC-readiness pts (a financing
    sweetener that stacks with OZ). Both coal_closure and
    fossil_fuel_employment qualify; absent/false earns nothing."""
    _ready(page, base_url)
    base = {"transmission_mi": 0.5}
    coal = dict(base, in_energy_community=True, energy_community_type="coal_closure")
    ffe = dict(base, in_energy_community=True, energy_community_type="fossil_fuel_employment")
    none = dict(base, in_energy_community=False)
    assert _dc_bd(page, coal)["readiness"] == 3
    assert _dc_bd(page, ffe)["readiness"] == 3
    assert _dc_bd(page, none)["readiness"] == 0
    # Stacks with OZ: standard OZ (5) + energy community (3) = 8
    stacked = dict(base, in_opportunity_zone=True, in_energy_community=True)
    assert _dc_bd(page, stacked)["readiness"] == 8


def test_gen_energy_community_readiness_bonus(page, base_url):
    """For a NEW-GENERATION build the IRA +10pp ITC/PTC bonus applies directly,
    so energy community earns +3 — more than OZ's +2. Cap is 6."""
    _ready(page, base_url)
    base = {"transmission_mi": 0.5}
    ec = dict(base, in_energy_community=True, energy_community_type="coal_closure")
    assert _gen_bd(page, ec)["readiness"] == 3
    # clean (4) + energy community (3) = 7, capped at 6
    clean_ec = dict(ec, npl_status_code="D")
    assert _gen_bd(page, clean_ec)["readiness"] == 6
    # energy community (3) > OZ (2)
    oz = dict(base, in_opportunity_zone=True)
    assert _gen_bd(page, ec)["readiness"] > _gen_bd(page, oz)["readiness"]


def test_dc_readiness_npl_final_gives_partial(page, base_url):
    _ready(page, base_url)
    assert _dc_bd(page, {"transmission_mi": 0.5, "npl_status_code": "F"})["readiness"] == 1


# -- Flood penalty ---------------------------------------------------------

def test_sfha_subtracts_from_both_scores(page, base_url):
    """A site in a Special Flood Hazard Area takes an 18-point penalty on
    both lenses. The all-max DC record (100) drops to 82."""
    _ready(page, base_url)
    rec = {
        "transmission_mi": 0.0, "transmission_kv": 500,
        "substation_mi": 0.0,
        "power_plant_mi": 0.5, "power_plant_mw": 600, "power_plant_fuel": "Natural Gas",
        "acreage": 1000, "gas_pipeline_mi": 0.0,
        "highway_mi": 0.5, "rail_mi": 0.5,
        "data_center_reuse_candidate": True,
        "npl_status_code": "D", "in_reuse": "Yes",
        "in_opportunity_zone": True,
        "in_sfha": True,
    }
    assert _dc(page, rec) == 82
    assert _dc_bd(page, rec)["flood_penalty"] == -18


def test_unmapped_flood_is_not_penalized(page, base_url):
    """in_sfha === null (unmapped / not yet backfilled) must NOT subtract —
    absence of evidence isn't evidence of risk."""
    _ready(page, base_url)
    base = {"transmission_mi": 0.5, "acreage": 100, "transmission_kv": 230}
    none_flood = dict(base)               # in_sfha absent
    false_flood = dict(base, in_sfha=False)
    assert _dc_bd(page, none_flood)["flood_penalty"] == 0
    assert _dc_bd(page, false_flood)["flood_penalty"] == 0


def test_sfha_floors_at_zero_not_negative(page, base_url):
    _ready(page, base_url)
    rec = {"transmission_mi": 5.0, "acreage": None, "in_sfha": True}
    assert _dc(page, rec) == 0
    assert _gen(page, rec) == 0


# -- FEMA NRI climate penalty ----------------------------------------------

def test_climate_penalty_wildfire_very_high(page, base_url):
    """Very-High wildfire (or drought) subtracts 10 from both lenses;
    Relatively-High subtracts 5; lower tiers and null subtract nothing."""
    _ready(page, base_url)
    base = {"transmission_mi": 0.5}
    vh = dict(base, nri_wildfire_rating="Very High")
    rh = dict(base, nri_wildfire_rating="Relatively High")
    mod = dict(base, nri_wildfire_rating="Relatively Moderate")
    none = dict(base)
    assert _dc_bd(page, vh)["climate_penalty"] == -10
    assert _dc_bd(page, rh)["climate_penalty"] == -5
    assert _dc_bd(page, mod)["climate_penalty"] == 0
    assert _dc_bd(page, none)["climate_penalty"] == 0
    # Same on the generation lens.
    assert _gen_bd(page, vh)["climate_penalty"] == -10


def test_climate_penalty_takes_max_of_wildfire_drought(page, base_url):
    """The penalty is the worst of wildfire / drought, not the sum."""
    _ready(page, base_url)
    both = {"transmission_mi": 0.5,
            "nri_wildfire_rating": "Very High",
            "nri_drought_rating": "Relatively High"}
    assert _dc_bd(page, both)["climate_penalty"] == -10  # max(10, 5), not 15
    # Drought alone drives it when wildfire is benign.
    drought_only = {"transmission_mi": 0.5,
                    "nri_wildfire_rating": "Very Low",
                    "nri_drought_rating": "Very High"}
    assert _dc_bd(page, drought_only)["climate_penalty"] == -10


def test_climate_penalty_heatwave_not_charged(page, base_url):
    """Heat wave is displayed for context but does NOT drive the penalty."""
    _ready(page, base_url)
    rec = {"transmission_mi": 0.5, "nri_heatwave_rating": "Very High"}
    assert _dc_bd(page, rec)["climate_penalty"] == 0


# -- Generation per-component coverage -------------------------------------

@pytest.mark.parametrize("acres,expected", [
    (None, 0), (1, 0), (5, 2), (25, 6), (100, 13), (250, 18),
    (500, 24), (1000, 28), (5000, 28),
])
def test_gen_acreage_component(page, base_url, acres, expected):
    """Generation acreage curve keeps climbing past the DC flatten point —
    utility-scale solar/wind scales with land."""
    _ready(page, base_url)
    bd = _gen_bd(page, {"transmission_mi": 0.5, "acreage": acres})
    assert bd["acreage"] == expected


@pytest.mark.parametrize("mi,expected", [
    (0.0, 18), (1.0, 9), (2.0, 0),
])
def test_gen_transmission_distance_component(page, base_url, mi, expected):
    _ready(page, base_url)
    assert _gen_bd(page, {"transmission_mi": mi})["transmission_distance"] == expected


@pytest.mark.parametrize("mi,expected", [
    (None, 0), (0.3, 16), (2.0, 12), (5.0, 8), (10.0, 4), (20.0, 0),
])
def test_gen_substation_component(page, base_url, mi, expected):
    _ready(page, base_url)
    bd = _gen_bd(page, {"transmission_mi": 0.5, "substation_mi": mi})
    assert bd["substation"] == expected


@pytest.mark.parametrize("iso,expected", [
    (None, 0), ("PJM", 8), ("MISO", 8), ("ERCOT", 8), ("CAISO", 8),
    ("SPP", 8), ("NYISO", 8), ("ISO-NE", 8), ("non-RTO", 4),
])
def test_gen_iso_rto_component(page, base_url, iso, expected):
    """Organized RTO = full marks; non-RTO bilateral region = half."""
    _ready(page, base_url)
    bd = _gen_bd(page, {"transmission_mi": 0.5, "iso_rto": iso})
    assert bd["iso_rto"] == expected


def test_gen_readiness_ignores_reuse(page, base_url):
    """A generation build wants vacant land — `in_reuse` (occupied) is NOT
    a plus, unlike the DC lens. Only cleanup-complete (4) + OZ (2) count."""
    _ready(page, base_url)
    reuse_only = {"transmission_mi": 0.5, "in_reuse": "Yes"}
    clean_oz = {"transmission_mi": 0.5, "npl_status_code": "D", "in_opportunity_zone": True}
    assert _gen_bd(page, reuse_only)["readiness"] == 0
    assert _gen_bd(page, clean_oz)["readiness"] == 6


def test_gen_excludes_grid_inheritance_component(page, base_url):
    """The generation breakdown must not carry a grid_inheritance key — you
    ARE the plant, co-location is irrelevant for new generation."""
    _ready(page, base_url)
    bd = _gen_bd(page, {
        "transmission_mi": 0.5, "power_plant_mi": 0.1,
        "power_plant_mw": 1000, "power_plant_fuel": "Natural Gas",
    })
    assert "grid_inheritance" not in bd
    assert "power_plant" not in bd


def test_lenses_diverge_on_same_record(page, base_url):
    """A big remote parcel (lots of land, in an RTO, far from existing
    plants, modest grid) should score notably higher for generation than
    for a data-center load — the whole point of two lenses."""
    _ready(page, base_url)
    rec = {
        "transmission_mi": 0.3, "transmission_kv": 230,
        "substation_mi": 1.0, "acreage": 2000,
        "gas_pipeline_mi": 1.5, "iso_rto": "MISO",
        "power_plant_mi": 40,  # far — helps neither, hurts DC's co-location
        "npl_status_code": "D",
    }
    dc = _dc(page, rec)
    gen = _gen(page, rec)
    assert gen > dc, f"expected generation ({gen}) > data-center ({dc}) for a big remote parcel"


# -- Tooltip + column integration ------------------------------------------

def test_tooltip_is_attached_to_column_header(page, base_url):
    _ready(page, base_url)
    title = page.evaluate(
        "document.getElementById('th-dc-score').getAttribute('title')"
    )
    assert title and "0–100" in title and "transmission" in title


def test_dc_score_column_rendered_in_table(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    page.locator("#tab-table").click()
    page.wait_for_selector("#sites-table tbody tr")
    header = page.evaluate(
        "document.querySelector(\"#sites-table thead th[data-sort='dc_score']\").textContent.trim()"
    )
    assert header == "DC score"
    page.evaluate(
        "document.querySelector(\"#sites-table thead th[data-sort='dc_score']\")"
        ".dispatchEvent(new MouseEvent('click', { bubbles: true }))"
    )
    page.wait_for_function(
        "document.querySelector(\"#sites-table thead th[data-sort='dc_score']\")"
        ".getAttribute('data-sort-glyph') === '▼'"
    )
    top_cell = page.evaluate(
        "document.querySelector('#sites-table tbody tr td:nth-child(8)').textContent.trim()"
    )
    assert top_cell.isdigit(), f"top DC score row should be numeric, got {top_cell!r}"
    assert 0 <= int(top_cell) <= 100


def test_dc_score_sort_descending_is_monotonic(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    page.locator("#tab-table").click()
    page.wait_for_selector("#sites-table tbody tr")
    page.evaluate(
        "document.querySelector(\"#sites-table thead th[data-sort='dc_score']\")"
        ".dispatchEvent(new MouseEvent('click', { bubbles: true }))"
    )
    page.wait_for_function(
        "document.querySelector(\"#sites-table thead th[data-sort='dc_score']\")"
        ".getAttribute('data-sort-glyph') === '▼'"
    )
    cells = page.evaluate(
        "() => Array.from(document.querySelectorAll('#sites-table tbody tr'))"
        ".slice(0, 50).map(r => r.children[7].textContent.trim())"
    )
    numeric = [int(c) for c in cells if c.isdigit()]
    assert len(numeric) >= 5, f"expected ≥5 numeric scores in first 50 rows, got {cells[:10]}"
    for prev, curr in zip(numeric, numeric[1:]):
        assert prev >= curr, f"sort not monotonic: {prev} < {curr}"


# -- Detail-panel suitability block ----------------------------------------

def test_suitability_block_renders_both_lenses(page, base_url):
    """Opening a Superfund site (which carries infra-proximity data) should
    populate the detail-panel Siting-suitability block with two score
    meters."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    # Pick any site that has transmission data so the score is non-null.
    sid = page.evaluate(
        "() => (window.__sites || []).find(s => s.transmission_mi != null)?.id || null"
    )
    assert sid, "expected at least one site with transmission_mi"
    page.evaluate("(id) => window.__selectSite(id)", sid)
    page.wait_for_selector("#d-suit-dc .suit-score")
    dc_txt = page.evaluate("document.querySelector('#d-suit-dc .suit-score').textContent")
    gen_txt = page.evaluate("document.querySelector('#d-suit-gen .suit-score').textContent")
    # Either a number or "N/A" — but for a transmission-bearing site it
    # should be numeric.
    assert any(ch.isdigit() for ch in dc_txt), f"DC score not numeric: {dc_txt!r}"
    assert any(ch.isdigit() for ch in gen_txt), f"generation score not numeric: {gen_txt!r}"


def test_suitability_block_is_above_owner_in_panel(page, base_url):
    """UAT 2026-05-31: the suitability block — the headline DC/generation
    judgment the whole tool is built around — must sit near the TOP of the
    detail panel (right after the core KV grid), not buried below the
    Owner / Documents / Tax sections. Guards against accidental re-burial.
    `compareDocumentPosition` returns DOCUMENT_POSITION_FOLLOWING (4) when
    the owner block comes after the suitability block in document order."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    suit_before_owner = page.evaluate(
        "() => {"
        "  const suit = document.getElementById('d-suitability-block');"
        "  const owner = document.querySelector(\"#detail [data-section='owner']\");"
        "  if (!suit || !owner) return null;"
        "  return !!(suit.compareDocumentPosition(owner) & Node.DOCUMENT_POSITION_FOLLOWING);"
        "}"
    )
    assert suit_before_owner is True, (
        "suitability block must appear before the Owner section in the detail panel"
    )
