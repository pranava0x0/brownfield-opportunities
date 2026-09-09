"""End-to-end tests for the two Nickel Refining scoring lenses.

The score functions live in `docs/nickel-score.js` and expose on `window`:
  computeNickelImportScore / computeNickelImportBreakdown
  computeNickelDomesticScore / computeNickelDomesticBreakdown
  nickelScorable / nickelAcreageStatus / nickelTier
  NICKEL_WEIGHTS_IMPORT / NICKEL_WEIGHTS_DOMESTIC / NICKEL_MIN_ACRES

Synthetic records via page.evaluate — a logic test of the formula, not a
data-quality test of real records.

Also guards the name-collision regression that broke the DC lens when
maritime-score.js shipped (2026-08-27): every internal helper in
nickel-score.js is `_nickel`/`NICKEL_`-prefixed, and this file asserts the
OTHER score modules still compute correctly after nickel-score.js has loaded.
The collision is invisible in the offending file's own diff, so the guard has
to live here.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function(
        "typeof window.computeNickelImportScore === 'function'"
        " && typeof window.computeNickelDomesticScore === 'function'"
        " && typeof window.computeDcCompositeScore === 'function'",
        timeout=10_000,
    )


def _imp(page: Page, r: dict):
    return page.evaluate("(r) => window.computeNickelImportScore(r)", r)


def _dom(page: Page, r: dict):
    return page.evaluate("(r) => window.computeNickelDomesticScore(r)", r)


def _imp_bd(page: Page, r: dict):
    return page.evaluate("(r) => window.computeNickelImportBreakdown(r)", r)


def _dom_bd(page: Page, r: dict):
    return page.evaluate("(r) => window.computeNickelDomesticBreakdown(r)", r)


# Strong across every component of both lenses.
_STRONG = {
    "transmission_mi": 0.4, "transmission_kv": 345,
    "substation_mi": 0.4, "substation_kv": 230,
    "rail_mi": 0.2, "port_mi": 4,
    "water_gage_mi": 1.5, "water_flow_cfs": 6000,
    "nickel_feedstock_mi": 20, "nickel_demand_mi": 60,
    "acreage": 800,
    "_waterChecked": True,
}


def _rec(**over) -> dict:
    r = dict(_STRONG)
    r.update(over)
    return r


# --- weights ---------------------------------------------------------------

def test_nickel_weight_tables_each_sum_to_100(page: Page, base_url: str) -> None:
    """A new component takes points from an existing one; it never appends.

    Both penalties (flood, drought) are subtractive precisely so this holds.
    """
    _ready(page, base_url)
    for name in ("NICKEL_WEIGHTS_IMPORT", "NICKEL_WEIGHTS_DOMESTIC"):
        total = page.evaluate(
            f"Object.values(window.{name}).reduce((a, b) => a + b, 0)")
        assert total == 100, f"{name} sums to {total}, not 100"


def test_land_is_not_a_scored_component(page: Page, base_url: str) -> None:
    """Acreage is a threshold, not a ranked factor — 5,000 acres is worth no
    more to a refinery than 500. Neither weight table may carry it."""
    _ready(page, base_url)
    for name in ("NICKEL_WEIGHTS_IMPORT", "NICKEL_WEIGHTS_DOMESTIC"):
        keys = page.evaluate(f"Object.keys(window.{name})")
        assert "acreage" not in keys and "land" not in keys, keys


# --- gate ------------------------------------------------------------------

def test_no_scored_component_reads_a_field_that_is_never_populated(
        page: Page, base_url: str) -> None:
    """A component computed from a universally-null field is a CONSTANT: it
    adds the same points to every site, moves no ranking, and makes the score
    table look as though the factor had been assessed.

    A first cut of this lens scored workforce off `county_labor_force`, which
    is present on ZERO of the 46,759 records because the connector that would
    fill it needs a Census key nobody has registered. The term was removed and
    the factor is disclosed as unassessed instead. This guard keeps the next
    component from repeating it: for every input the weight tables read, at
    least some real site must carry a value.
    """
    _ready(page, base_url)
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    inputs = ["port_mi", "water_flow_cfs", "transmission_mi", "transmission_kv",
              "substation_mi", "rail_mi", "nickel_demand_mi", "nickel_feedstock_mi"]
    populated = page.evaluate(
        """(fields) => Object.fromEntries(fields.map(f =>
             [f, window.__sites.filter(s => s[f] != null).length]))""",
        inputs)
    dead = [f for f, n in populated.items() if n == 0]
    assert not dead, f"scored inputs that no site carries: {dead} ({populated})"


def test_workforce_is_disclosed_as_unassessed_not_scored(
        page: Page, base_url: str) -> None:
    """Electra names workforce as a criterion, so its absence has to be a
    stated choice rather than an omission."""
    _ready(page, base_url)
    for name in ("NICKEL_WEIGHTS_IMPORT", "NICKEL_WEIGHTS_DOMESTIC"):
        assert "workforce" not in page.evaluate(f"Object.keys(window.{name})")


def test_score_is_null_without_transmission(page: Page, base_url: str) -> None:
    """"Cannot assess" is not "bad" — the gate returns null, never 0."""
    _ready(page, base_url)
    assert _imp(page, _rec(transmission_mi=None)) is None
    assert _dom(page, _rec(transmission_mi=None)) is None


def test_score_is_null_before_the_water_join_has_run(page: Page, base_url: str) -> None:
    """Water is 20 of 100 on both lenses. Before the lazy join resolves every
    site would look water-less and score zero on it, so the gate waits for
    `_waterChecked` — the same guard the microreactor lens applies with
    `_infraChecked`."""
    _ready(page, base_url)
    r = _rec()
    del r["_waterChecked"]
    assert _imp(page, r) is None
    assert _dom(page, r) is None


# --- the lens split --------------------------------------------------------

def test_import_lens_scores_port_and_domestic_lens_ignores_it(
        page: Page, base_url: str) -> None:
    """The two live US projects published opposite logic. Westwin built 400
    miles from salt water, so a port must contribute nothing to the domestic
    lens; Electra named deep-water port first, so it must matter most on the
    import one."""
    _ready(page, base_url)
    with_port = _rec(port_mi=4)
    no_port = _rec(port_mi=None)
    assert _imp(page, with_port) > _imp(page, no_port)
    assert _dom(page, with_port) == _dom(page, no_port)
    assert "port" not in page.evaluate("Object.keys(window.NICKEL_WEIGHTS_DOMESTIC)")


def test_domestic_lens_scores_feedstock_and_import_lens_ignores_it(
        page: Page, base_url: str) -> None:
    """The import lens's feed arrives by ship, so distance to a domestic mine
    is irrelevant to it."""
    _ready(page, base_url)
    near = _rec(nickel_feedstock_mi=20)
    far = _rec(nickel_feedstock_mi=900)
    assert _dom(page, near) > _dom(page, far)
    assert _imp(page, near) == _imp(page, far)


def test_rail_is_weighted_higher_on_the_domestic_lens(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    imp_w = page.evaluate("window.NICKEL_WEIGHTS_IMPORT.rail")
    dom_w = page.evaluate("window.NICKEL_WEIGHTS_DOMESTIC.rail")
    assert dom_w > imp_w


# --- water -----------------------------------------------------------------

def test_water_needs_both_a_nearby_gage_and_real_flow(page: Page, base_url: str) -> None:
    """A gage next door on a 12 cfs creek is not industrial water, and a
    5,000 cfs river two basins away is not this site's water."""
    _ready(page, base_url)
    good = _imp_bd(page, _rec(water_gage_mi=1.5, water_flow_cfs=6000))["water"]
    creek = _imp_bd(page, _rec(water_gage_mi=1.5, water_flow_cfs=12))["water"]
    distant = _imp_bd(page, _rec(water_gage_mi=45, water_flow_cfs=6000))["water"]
    assert good > creek
    assert good > distant


def test_missing_flow_scores_zero_water_not_a_null_score(
        page: Page, base_url: str) -> None:
    """Once the join has run, no gage in range is a real negative result: the
    component is 0, but the site still gets a score."""
    _ready(page, base_url)
    bd = _imp_bd(page, _rec(water_gage_mi=None, water_flow_cfs=None))
    assert bd is not None
    assert bd["water"] == 0
    assert bd["total"] > 0


# --- land threshold --------------------------------------------------------

def test_acreage_status_is_tri_state(page: Page, base_url: str) -> None:
    """null means the source publishes no acreage — every ACRES brownfield and
    two-thirds of FUDS. Reading it as "too small" would delete most of the
    corpus from the lens; reading it as "big enough" would invent a fact."""
    _ready(page, base_url)
    ev = lambda r: page.evaluate("(r) => window.nickelAcreageStatus(r)", r)
    assert ev({"acreage": 900}) is True
    assert ev({"acreage": 12}) is False
    assert ev({"acreage": None, "parcel_acreage": None}) is None
    # A parcel figure is a conservative floor and counts when acreage is null.
    assert ev({"acreage": None, "parcel_acreage": 500}) is True


def test_min_acres_matches_the_documented_precedent(page: Page, base_url: str) -> None:
    """Long Harbour is ~370 acres including residue ponds; Westwin's tract is
    480. 300 is the conservative floor and is stated in the tab copy."""
    _ready(page, base_url)
    assert page.evaluate("window.NICKEL_MIN_ACRES") == 300


# --- penalties -------------------------------------------------------------

def test_sfha_flood_is_penalised_and_unmapped_is_not(page: Page, base_url: str) -> None:
    """Absence of evidence is not evidence — the rule every penalty in this
    project follows."""
    _ready(page, base_url)
    base = _imp(page, _rec())
    assert _imp(page, _rec(in_sfha=True)) < base
    assert _imp(page, _rec(in_sfha=None)) == base
    assert _imp(page, _rec(in_sfha=False)) == base


def test_drought_is_penalised(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    base = _imp(page, _rec())
    assert _imp(page, _rec(nri_drought_rating="Very High")) < base
    assert _imp(page, _rec(nri_drought_rating="Relatively High")) < base
    assert (_imp(page, _rec(nri_drought_rating="Very High"))
            < _imp(page, _rec(nri_drought_rating="Relatively High")))


def test_nickel_wildfire_is_not_penalised(page: Page, base_url: str) -> None:
    """A deliberate divergence from dc-score.js's _climatePenalty, which
    charges max(wildfire, drought). A refinery's climate exposure is to water
    availability; wildfire risk to a fenced industrial plant with no interface
    fuel is a much weaker claim, so it is displayed and not charged."""
    _ready(page, base_url)
    assert _imp(page, _rec(nri_wildfire_rating="Very High")) == _imp(page, _rec())


# --- grid ------------------------------------------------------------------

def test_substation_stands_in_for_missing_line_coverage(
        page: Page, base_url: str) -> None:
    """HIFLD's public transmission layer is patchy on sub-transmission, so
    6,222 corpus sites report a substation closer than their "nearest" line —
    impossible, since a substation is by definition connected. Same correction
    dc-score.js:_effectiveGridAccess makes.

    The control sets substation_mi to null rather than moving it, so only the
    substitution changes — moving it would also perturb the substation
    component and the test would measure two things at once.
    """
    _ready(page, base_url)
    bd = _imp_bd(page, _rec(transmission_mi=40, substation_mi=0.5, substation_kv=230))
    assert bd["_viaSubstation"] is True
    control = _imp_bd(page, _rec(transmission_mi=40, substation_mi=None))
    assert bd["transmission"] > control["transmission"]


def test_null_voltage_is_neither_zero_nor_full_credit(
        page: Page, base_url: str) -> None:
    """~27% of substations carry no OSM voltage tag. Null is partial credit —
    the same handling the flood and climate terms give an unmapped value."""
    _ready(page, base_url)
    null_kv = _imp_bd(page, _rec(transmission_kv=None))["voltage"]
    high = _imp_bd(page, _rec(transmission_kv=345))["voltage"]
    low = _imp_bd(page, _rec(transmission_kv=25))["voltage"]
    assert 0 < null_kv < high
    assert null_kv > low


# --- no global collision ---------------------------------------------------

def test_other_lenses_still_compute_after_nickel_score_loads(
        page: Page, base_url: str) -> None:
    """A bare top-level declaration in a classic <script> becomes a window
    property, so a same-named helper in a later file silently overwrites an
    earlier one — the bug maritime-score.js shipped in 2026-08-27, thrown from
    inside dc-score.js by a defect that lived entirely in another file. Every
    new lens file needs this guard, because the collision is invisible in the
    offending file's own diff."""
    _ready(page, base_url)
    r = {
        "transmission_mi": 0.5, "transmission_kv": 345, "substation_mi": 0.5,
        "substation_kv": 230, "acreage": 900, "gas_pipeline_mi": 1,
        "highway_mi": 2, "rail_mi": 0.5, "_infraChecked": True,
        "_portChecked": True, "port_mi": 5, "shipyard_mi": 30,
    }
    for fn in ("computeDcCompositeScore", "computeGenerationScore",
               "computeManufacturingScore", "computeFloatingNuclearScore",
               "computeCoastalGenerationScore"):
        score = page.evaluate(f"(r) => window.{fn}(r)", r)
        assert isinstance(score, (int, float)), f"{fn} returned {score!r}"


# --- tiers -----------------------------------------------------------------

def test_tier_breaks_are_calibrated_to_this_lens(page: Page, base_url: str) -> None:
    """Not copied from the DC lens's 75/50/25 — the microreactor tab records
    why that produces a single-colour corpus. Measured over the full corpus:
    median 63, p90 ~80, max 96, so strong is about the top tenth."""
    _ready(page, base_url)
    assert page.evaluate("window.nickelTier(90).key") == "strong"
    assert page.evaluate("window.nickelTier(72).key") == "moderate"
    assert page.evaluate("window.nickelTier(60).key") == "marginal"
    assert page.evaluate("window.nickelTier(20).key") == "weak"
    assert page.evaluate("window.nickelTier(null)") is None
