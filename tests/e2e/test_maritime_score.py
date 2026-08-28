"""End-to-end tests for the two Maritime Siting scoring lenses.

The score functions live in `docs/maritime-score.js` and expose, on `window`:
  computeFloatingNuclearScore / computeFloatingNuclearBreakdown
  computeCoastalGenerationScore / computeCoastalGenerationBreakdown
  OFFSHORE_NUCLEAR_WEIGHTS / COASTAL_GENERATION_WEIGHTS
  maritimeScorable

These tests load the page and call the functions with synthetic record
payloads via `page.evaluate` — a logic test of the formula, not a
data-quality test of real records.

Also guards the 2026-08-27 name-collision regression: maritime-score.js's
internal helpers must NOT be plain top-level `function`/bare-`const`
declarations that shadow dc-score.js's own same-named globals (e.g. the
original `_scoreGasPipeline` / `_scoreSubstation` / `_floodPenalty` clashed
and silently broke the DC/Generation/Manufacturing lenses when loaded after
dc-score.js — caught in manual browser verification, not by any test at the
time). This file asserts BOTH score modules still compute correctly after
maritime-score.js has loaded.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function(
        "typeof window.computeFloatingNuclearScore === 'function'"
        " && typeof window.computeCoastalGenerationScore === 'function'"
        " && typeof window.computeDcCompositeScore === 'function'",
        timeout=10_000,
    )


def _offshore(page: Page, record: dict):
    return page.evaluate("(r) => window.computeFloatingNuclearScore(r)", record)


def _offshore_bd(page: Page, record: dict):
    return page.evaluate("(r) => window.computeFloatingNuclearBreakdown(r)", record)


def _coastal(page: Page, record: dict):
    return page.evaluate("(r) => window.computeCoastalGenerationScore(r)", record)


def _coastal_bd(page: Page, record: dict):
    return page.evaluate("(r) => window.computeCoastalGenerationBreakdown(r)", record)


# A record with strong values across every component of both lenses.
_STRONG_RECORD = {
    "id": "test-1", "program": "superfund", "acreage": 400,
    "in_sfha": False,
    "port_mi": 2.0, "port_type": "Coastal", "port_hurricane_freq": 0.05,
    "shipyard_mi": 4.0, "shipyard_capability": "heavy_module",
    "transmission_mi": 0.2, "substation_mi": 0.5, "substation_kv": 230,
    "gas_pipeline_mi": 0.5,
    "current_owner": "ACME Corp", "in_reuse": "Yes",
    "in_energy_community": True, "in_opportunity_zone": True,
    "npl_status_code": "D",
    "_portChecked": True,
}


def test_weight_tables_each_sum_to_100(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    offshore_total = page.evaluate(
        "Object.values(window.OFFSHORE_NUCLEAR_WEIGHTS).reduce((a,b)=>a+b,0)"
    )
    coastal_total = page.evaluate(
        "Object.values(window.COASTAL_GENERATION_WEIGHTS).reduce((a,b)=>a+b,0)"
    )
    assert offshore_total == 100
    assert coastal_total == 100


def test_ungated_site_returns_null_for_both_lenses(page: Page, base_url: str) -> None:
    """No port_mi and no _portChecked stamp = 'not yet checked', not zero."""
    _ready(page, base_url)
    record = {"id": "x", "program": "brownfield"}
    assert _offshore(page, record) is None
    assert _coastal(page, record) is None


def test_checked_but_landlocked_site_still_scores_not_null(page: Page, base_url: str) -> None:
    """_portChecked=True means the join has RUN — the site is scorable even
    with nothing within range, it just scores low on the port/shipyard
    components. Only the absence of the join (no stamp, no port_mi) gates
    to null; 'checked and nothing nearby' is a real, low, non-null score."""
    _ready(page, base_url)
    record = {"id": "x", "program": "brownfield", "_portChecked": True}
    offshore = _offshore(page, record)
    coastal = _coastal(page, record)
    assert offshore is not None and offshore < 25
    assert coastal is not None and coastal < 25


def test_strong_record_scores_highly_on_both_lenses(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    offshore = _offshore(page, _STRONG_RECORD)
    coastal = _coastal(page, _STRONG_RECORD)
    assert offshore is not None and offshore >= 75
    assert coastal is not None and coastal >= 75


def test_offshore_lens_weights_shipyard_above_port(page: Page, base_url: str) -> None:
    """The floating-nuclear lens's largest single weight is shipyard
    proximity — every real precedent builds AT a shipyard and tows to site."""
    _ready(page, base_url)
    weights = page.evaluate("window.OFFSHORE_NUCLEAR_WEIGHTS")
    assert weights["shipyard"] > weights["port_access"]
    assert weights["shipyard"] == max(weights.values())


def test_coastal_lens_weights_transmission_above_port(page: Page, base_url: str) -> None:
    """The coastal-generation lens weights grid access above port access —
    the inverse priority order of the offshore lens (port is a SECONDARY
    delivery-feasibility signal here, not the primary driver)."""
    _ready(page, base_url)
    weights = page.evaluate("window.COASTAL_GENERATION_WEIGHTS")
    assert weights["transmission"] > weights["port_access"]


def test_coastal_lens_has_no_shipyard_component(page: Page, base_url: str) -> None:
    """A data center / generation plant has no assembly-yard dependency."""
    _ready(page, base_url)
    bd = _coastal_bd(page, _STRONG_RECORD)
    assert "shipyard" not in bd


def test_great_lakes_port_scores_lower_than_coastal(page: Page, base_url: str) -> None:
    """Great Lakes ports connect to the ocean only via the draft-limited
    St. Lawrence Seaway — real but narrower access than an open coastal
    port, scored as a discount not a disqualifier."""
    _ready(page, base_url)
    coastal_rec = dict(_STRONG_RECORD, port_type="Coastal")
    lakes_rec = dict(_STRONG_RECORD, port_type="Great Lakes")
    assert _offshore(page, lakes_rec) < _offshore(page, coastal_rec)


def test_sfha_flood_penalty_applied_to_both_lenses(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    flooded = dict(_STRONG_RECORD, in_sfha=True)
    clean = dict(_STRONG_RECORD, in_sfha=False)
    penalty = page.evaluate("window.MARITIME_FLOOD_SFHA_PENALTY")
    assert penalty > 0
    assert _offshore(page, clean) - _offshore(page, flooded) == penalty
    assert _coastal(page, clean) - _coastal(page, flooded) == penalty


def test_hurricane_penalty_charged_harder_on_offshore_lens(page: Page, base_url: str) -> None:
    """A permanently moored offshore facility is charged more than an
    onshore plant/DC a port merely delivers equipment to."""
    _ready(page, base_url)
    calm = dict(_STRONG_RECORD, port_hurricane_freq=0.0)
    stormy = dict(_STRONG_RECORD, port_hurricane_freq=0.5)
    offshore_drop = _offshore(page, calm) - _offshore(page, stormy)
    coastal_drop = _coastal(page, calm) - _coastal(page, stormy)
    assert offshore_drop > 0
    assert coastal_drop > 0
    assert offshore_drop > coastal_drop


def test_heavy_module_shipyard_scores_above_naval_repair(page: Page, base_url: str) -> None:
    """heavy_module (offshore platform/topsides fabrication) is the
    capability most analogous to floating-reactor assembly; naval_repair
    (drydock/overhaul only) is the weakest fit."""
    _ready(page, base_url)
    heavy = dict(_STRONG_RECORD, shipyard_capability="heavy_module")
    repair = dict(_STRONG_RECORD, shipyard_capability="naval_repair")
    assert _offshore(page, heavy) > _offshore(page, repair)


def test_score_clamped_to_0_100(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    worst = dict(_STRONG_RECORD, in_sfha=True, port_hurricane_freq=1.0,
                  port_mi=75, shipyard_mi=150, transmission_mi=None,
                  substation_mi=None, gas_pipeline_mi=None, acreage=None,
                  current_owner=None, in_reuse=None, in_energy_community=False,
                  in_opportunity_zone=False, npl_status_code=None)
    offshore = _offshore(page, worst)
    coastal = _coastal(page, worst)
    assert offshore is not None and 0 <= offshore <= 100
    assert coastal is not None and 0 <= coastal <= 100


def test_dc_lens_still_computes_after_maritime_score_loads(page: Page, base_url: str) -> None:
    """Regression guard for the 2026-08-27 name-collision bug: loading
    maritime-score.js after dc-score.js must not corrupt dc-score.js's own
    internal helpers (the original bug clobbered `_scoreGasPipeline` /
    `_scoreSubstation` / `_floodPenalty`, breaking every DC/Generation/
    Manufacturing score computation)."""
    _ready(page, base_url)
    record = {
        "id": "dc-test", "program": "superfund", "acreage": 300,
        "transmission_mi": 0.5, "transmission_kv": 230, "substation_mi": 1.0,
        "gas_pipeline_mi": 2.0, "in_sfha": False,
    }
    dc_score = page.evaluate(
        "(r) => window.computeDcCompositeScore(r)", record
    )
    gen_score = page.evaluate(
        "(r) => window.computeGenerationScore(r)", record
    )
    assert dc_score is not None
    assert gen_score is not None
