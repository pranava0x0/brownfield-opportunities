"""End-to-end tests for the composite DC suitability score.

The score function itself lives in `docs/dc-score.js` and exposes
`window.computeDcCompositeScore` / `window.computeDcScoreBreakdown` /
`window.DC_SCORE_WEIGHTS` / `window.DC_SCORE_TOOLTIP`. These tests load
the page (which sources the script) and call the function with synthetic
record payloads via `page.evaluate`, then assert on the returned values.

This is a logic test, not a data-quality test — we test the formula, not
specific real-world records (those drift on every refresh).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


# -- Helpers ----------------------------------------------------------------

def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("typeof window.computeDcCompositeScore === 'function'", timeout=10_000)


def _score(page: Page, record: dict) -> int | None:
    return page.evaluate("(r) => window.computeDcCompositeScore(r)", record)


def _breakdown(page: Page, record: dict) -> dict | None:
    return page.evaluate("(r) => window.computeDcScoreBreakdown(r)", record)


# -- Module surface --------------------------------------------------------

def test_module_exposes_score_function(page, base_url):
    _ready(page, base_url)
    has = page.evaluate(
        "() => ({"
        "  fn: typeof window.computeDcCompositeScore,"
        "  brk: typeof window.computeDcScoreBreakdown,"
        "  weights: typeof window.DC_SCORE_WEIGHTS,"
        "  tooltip: typeof window.DC_SCORE_TOOLTIP"
        "})"
    )
    assert has["fn"] == "function"
    assert has["brk"] == "function"
    assert has["weights"] == "object"
    assert has["tooltip"] == "string"


def test_weights_sum_to_100(page, base_url):
    _ready(page, base_url)
    total = page.evaluate(
        "() => Object.values(window.DC_SCORE_WEIGHTS).reduce((a, b) => a + b, 0)"
    )
    assert total == 100


def test_tooltip_is_attached_to_column_header(page, base_url):
    _ready(page, base_url)
    title = page.evaluate(
        "document.getElementById('th-dc-score').getAttribute('title')"
    )
    assert title and "0–100" in title and "transmission" in title


# -- Gate (null transmission) ----------------------------------------------

def test_null_transmission_yields_null_score(page, base_url):
    """Transmission distance is the load-bearing signal — no power means
    no DC. Score must be null, not 0."""
    _ready(page, base_url)
    record = {"acreage": 1000, "transmission_mi": None, "transmission_kv": 500}
    assert _score(page, record) is None


def test_null_site_yields_null(page, base_url):
    _ready(page, base_url)
    assert _score(page, None) is None


# -- All-max record --------------------------------------------------------

def test_all_max_record_scores_100(page, base_url):
    """A perfect record across every component should land at exactly 100."""
    _ready(page, base_url)
    record = {
        "acreage": 1000,
        "transmission_mi": 0.0,
        "transmission_kv": 500,
        "gas_pipeline_mi": 0.0,
        "highway_mi": 0.5,
        "rail_mi": 0.5,
        "data_center_reuse_candidate": True,
        "npl_status_code": "D",
        "in_reuse": "Yes",
    }
    assert _score(page, record) == 100


# -- Per-component coverage ------------------------------------------------

@pytest.mark.parametrize("mi,expected", [
    (0.0, 20),   # adjacent
    (0.05, 20),  # adjacent boundary
    (1.0, 10),   # midpoint of the linear falloff
    (2.0, 0),    # cutoff
    (5.0, 0),    # beyond cutoff
])
def test_transmission_distance_component(page, base_url, mi, expected):
    _ready(page, base_url)
    record = {"transmission_mi": mi}
    bd = _breakdown(page, record)
    assert bd["transmission_distance"] == expected


@pytest.mark.parametrize("kv,expected", [
    (None, 0),
    (50,   4),
    (69,   8),
    (138, 12),
    (230, 16),
    (500, 20),
    (765, 20),  # >500 still capped at 20
])
def test_voltage_component(page, base_url, kv, expected):
    _ready(page, base_url)
    record = {"transmission_mi": 0.5, "transmission_kv": kv}
    bd = _breakdown(page, record)
    assert bd["voltage"] == expected


@pytest.mark.parametrize("acres,expected", [
    (None,  0),
    (1,     2),
    (5,     7),
    (25,   14),
    (100,  20),
    (500,  25),
    (50_000, 25),  # huge acreage stays capped
])
def test_acreage_component(page, base_url, acres, expected):
    _ready(page, base_url)
    record = {"transmission_mi": 0.5, "acreage": acres}
    bd = _breakdown(page, record)
    assert bd["acreage"] == expected


@pytest.mark.parametrize("mi,expected", [
    (None, 0),
    (0.0, 15),
    (1.0, 12),
    (5.0, 8),
    (15.0, 4),
    (30.0, 0),
])
def test_gas_pipeline_component(page, base_url, mi, expected):
    _ready(page, base_url)
    record = {"transmission_mi": 0.5, "gas_pipeline_mi": mi}
    bd = _breakdown(page, record)
    assert bd["gas_pipeline"] == expected


@pytest.mark.parametrize("hwy,rail,expected", [
    (None, None, 0),
    (1.0, None, 5),
    (None, 1.0, 5),
    (1.0, 1.0, 10),     # both within 1 mi → 10 (cap)
    (5.0, 5.0, 6),      # both ≤ 5 → 3 + 3
    (15.0, 15.0, 2),    # both ≤ 15 → 1 + 1
    (50.0, 50.0, 0),    # both beyond → 0
    (0.5, 0.5, 10),     # cap holds
])
def test_logistics_component(page, base_url, hwy, rail, expected):
    _ready(page, base_url)
    record = {"transmission_mi": 0.5, "highway_mi": hwy, "rail_mi": rail}
    bd = _breakdown(page, record)
    assert bd["logistics"] == expected


def test_readiness_caps_at_10(page, base_url):
    """All readiness sub-signals on a single record should not exceed the
    component cap of 10."""
    _ready(page, base_url)
    record = {
        "transmission_mi": 0.5,
        "data_center_reuse_candidate": True,  # 5
        "npl_status_code": "D",                # 3
        "in_reuse": "Yes",                     # 2
    }
    bd = _breakdown(page, record)
    assert bd["readiness"] == 10


def test_readiness_npl_final_gives_partial(page, base_url):
    _ready(page, base_url)
    record = {"transmission_mi": 0.5, "npl_status_code": "F"}
    bd = _breakdown(page, record)
    assert bd["readiness"] == 1


def test_readiness_in_reuse_case_insensitive(page, base_url):
    _ready(page, base_url)
    record_yes = {"transmission_mi": 0.5, "in_reuse": "Yes"}
    record_no  = {"transmission_mi": 0.5, "in_reuse": "No"}
    record_yo  = {"transmission_mi": 0.5, "in_reuse": "YES - 2018"}
    assert _breakdown(page, record_yes)["readiness"] == 2
    assert _breakdown(page, record_no)["readiness"]  == 0
    assert _breakdown(page, record_yo)["readiness"]  == 2


# -- Clamp -----------------------------------------------------------------

def test_score_is_clamped_to_0_100(page, base_url):
    """Defensive — the formula's max is 100 by construction, but the
    clamp on the return value should hold even if a future change adds
    a bonus component without updating the caps."""
    _ready(page, base_url)
    # Score this should produce 0
    record = {"transmission_mi": 5.0, "transmission_kv": None, "acreage": None}
    score = _score(page, record)
    assert score is not None and 0 <= score <= 100


# -- Table integration -----------------------------------------------------

def test_dc_score_column_rendered_in_table(page, base_url):
    """v1.13: the table's 8th column is "DC score" and renders numeric
    scores for records with transmission data, em-dash otherwise."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    page.locator("#tab-table").click()
    page.wait_for_selector("#sites-table tbody tr")
    header = page.evaluate(
        "document.querySelector(\"#sites-table thead th[data-sort='dc_score']\").textContent.trim()"
    )
    assert header == "DC score"
    # Click the DC score header to sort desc — first row should have a
    # numeric score (not an em-dash).
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
    """After a desc sort, scores in the first page should be non-increasing
    and all numeric (the null group falls to the tail)."""
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
