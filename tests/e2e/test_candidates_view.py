"""End-to-end tests for the DC Candidates view's unified filter model.

v1.21 (2026-06-10): the candidates tab previously ignored the global
filter strip entirely and carried its own unsynced "Min tier" and
"Readiness" button groups (duplicating the persona filter / OZ checkbox /
DC-candidate KPI toggle). It now sources from `tableState.filtered` —
the same globally-filtered set as the map and table — and keeps exactly
one piece of view-local state: the DC/Generation scoring lens,
round-tripped through the URL as `?lens=gen`.
"""
from __future__ import annotations

from playwright.sync_api import Page


def _ready(page: Page, base_url: str, query: str = "") -> None:
    page.goto(f"{base_url}/index.html{query}")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)


def _open_candidates(page: Page) -> None:
    page.locator("#tab-candidates").click()
    page.wait_for_selector("#candidates-table tbody tr")


def _pick_scored_state(page: Page) -> str:
    """A state that has at least 25 scored (transmission-bearing) sites, so
    the filtered candidates view is guaranteed non-empty."""
    state = page.evaluate(
        "() => {"
        "  const byState = {};"
        "  for (const s of window.__sites) {"
        "    if (s.transmission_mi != null && s.state) {"
        "      byState[s.state] = (byState[s.state] || 0) + 1;"
        "    }"
        "  }"
        "  return Object.entries(byState).find(([, n]) => n >= 25)?.[0] || null;"
        "}"
    )
    assert state, "expected at least one state with >=25 scored sites"
    return state


def _set_state_filter(page: Page, state: str) -> None:
    page.evaluate(
        "(st) => { const sel = document.getElementById('f-state');"
        " sel.value = st; sel.dispatchEvent(new Event('change')); }",
        state,
    )


def test_duplicate_filter_groups_removed(page, base_url):
    """The unsynced Min-tier / Readiness button groups are gone — those
    predicates live in the global filter strip (persona buttons, OZ
    checkbox, DC-candidate KPI toggle). Only the lens toggle remains,
    plus a note pointing at the global filters."""
    _ready(page, base_url)
    counts = page.evaluate(
        "() => ({"
        "  tier: document.querySelectorAll('[data-cand-tier]').length,"
        "  ready: document.querySelectorAll('[data-cand-ready]').length,"
        "  lens: document.querySelectorAll('[data-cand-lens]').length,"
        "  note: !!document.querySelector('.cand-filter-note')"
        "})"
    )
    assert counts["tier"] == 0
    assert counts["ready"] == 0
    assert counts["lens"] == 2
    assert counts["note"] is True


def test_candidates_respect_global_state_filter(page, base_url):
    """Filter to one state on the filter strip, then open DC Candidates:
    every rendered row must belong to that state and the stats line must
    say the global filters are applied. (Pre-v1.21 the tab silently showed
    nationwide results.)"""
    _ready(page, base_url)
    state = _pick_scored_state(page)
    _set_state_filter(page, state)
    _open_candidates(page)
    page.wait_for_function(
        "document.getElementById('candidates-stats').textContent"
        ".includes('global filters applied')"
    )
    st_cells = page.evaluate(
        "() => Array.from(document.querySelectorAll('#candidates-table tbody tr'))"
        ".slice(0, 50).map(r => r.children[2].textContent.trim())"
    )
    assert st_cells, "expected rendered candidate rows"
    assert all(c == state for c in st_cells), (
        f"expected all rows in {state}, got {sorted(set(st_cells))}"
    )


def test_candidates_rebuild_live_on_filter_change(page, base_url):
    """Changing a global filter WHILE the candidates tab is active rebuilds
    the view (applyFilter -> maybeRefreshCandidates)."""
    _ready(page, base_url)
    _open_candidates(page)
    before = page.evaluate("document.getElementById('candidates-stats').textContent")
    assert "global filters applied" not in before
    state = _pick_scored_state(page)
    _set_state_filter(page, state)
    page.wait_for_function(
        "document.getElementById('candidates-stats').textContent"
        ".includes('global filters applied')"
    )
    first_st = page.evaluate(
        "document.querySelector('#candidates-table tbody tr td:nth-child(3)').textContent.trim()"
    )
    assert first_st == state


def test_lens_toggle_roundtrips_url(page, base_url):
    """Switching to the Generation lens writes ?lens=gen (debounced);
    the default DC lens is NOT encoded."""
    _ready(page, base_url)
    assert "lens=" not in page.evaluate("location.search")
    _open_candidates(page)
    page.locator("[data-cand-lens='gen']").click()
    page.wait_for_function("location.search.includes('lens=gen')")
    page.wait_for_function(
        "document.getElementById('candidates-stats').textContent"
        ".includes('generation score')"
    )
    # Back to the default lens — the param must drop out of the URL.
    page.locator("[data-cand-lens='dc']").click()
    page.wait_for_function("!location.search.includes('lens=')")


def test_lens_restored_from_url(page, base_url):
    """Deep-linking with ?lens=gen lands with the Generation button active
    and the view sorted by generation score."""
    _ready(page, base_url, query="?lens=gen")
    active = page.evaluate(
        "document.querySelector('[data-cand-lens].active')?.dataset.candLens"
    )
    assert active == "gen"
    _open_candidates(page)
    stats = page.evaluate("document.getElementById('candidates-stats').textContent")
    assert "generation score" in stats


def test_land_ready_badge_renders_for_swrau_site(page, base_url):
    """A site whose EPA SWRAU `rau_status` meets the measure shows the
    solid-green "Land Ready" signal badge in the candidates Signals column.
    Pick a state with <=200 scored sites (one candidates page) and inject the
    SWRAU value onto one of its scored sites so it is guaranteed to render."""
    _ready(page, base_url)
    state = page.evaluate(
        "() => {"
        "  const byState = {};"
        "  for (const s of window.__sites) {"
        "    if (s.transmission_mi != null && s.state) (byState[s.state] ||= []).push(s);"
        "  }"
        "  for (const [st, arr] of Object.entries(byState)) {"
        "    if (arr.length >= 1 && arr.length <= 200) {"
        "      arr[0].rau_status = 'Meets the Measure'; return st;"
        "    }"
        "  }"
        "  return null;"
        "}"
    )
    assert state, "expected a state with 1..200 scored sites"
    _set_state_filter(page, state)
    _open_candidates(page)
    labels = page.evaluate(
        "() => Array.from(document.querySelectorAll('#candidates-table .sig-land'))"
        ".map((b) => b.textContent.trim())"
    )
    assert "Land Ready" in labels, "expected a Land Ready badge for the SWRAU site"


def test_climate_badge_renders_for_very_high_hazard(page, base_url):
    """A site with a FEMA NRI Very-High wildfire or drought rating (the −10
    climate penalty) shows the red "Climate" risk badge in the Signals
    column, parallel to the Flood badge for SFHA sites."""
    _ready(page, base_url)
    state = page.evaluate(
        "() => {"
        "  const byState = {};"
        "  for (const s of window.__sites) {"
        "    if (s.transmission_mi != null && s.state) (byState[s.state] ||= []).push(s);"
        "  }"
        "  for (const [st, arr] of Object.entries(byState)) {"
        "    if (arr.length >= 1 && arr.length <= 200) {"
        "      arr[0].nri_wildfire_rating = 'Very High'; return st;"
        "    }"
        "  }"
        "  return null;"
        "}"
    )
    assert state, "expected a state with 1..200 scored sites"
    _set_state_filter(page, state)
    _open_candidates(page)
    labels = page.evaluate(
        "() => Array.from(document.querySelectorAll('#candidates-table .cand-signals .sig-badge'))"
        ".map((b) => b.textContent.trim())"
    )
    assert "Climate" in labels, "expected a Climate badge for the Very-High-hazard site"


def test_nuclear_badge_renders_for_nuclear_adjacency(page, base_url):
    """A site within 5 mi of an operating nuclear plant >=500 MW shows the
    "Nuclear" grid-inheritance badge (the AWS/Susquehanna pattern)."""
    _ready(page, base_url)
    state = page.evaluate(
        "() => {"
        "  const byState = {};"
        "  for (const s of window.__sites) {"
        "    if (s.transmission_mi != null && s.state) (byState[s.state] ||= []).push(s);"
        "  }"
        "  for (const [st, arr] of Object.entries(byState)) {"
        "    if (arr.length >= 1 && arr.length <= 200) {"
        "      Object.assign(arr[0], {power_plant_mi: 2.0, power_plant_mw: 800,"
        "        power_plant_fuel: 'nuclear', retired_plant_mi: null});"
        "      return st;"
        "    }"
        "  }"
        "  return null;"
        "}"
    )
    assert state, "expected a state with 1..200 scored sites"
    _set_state_filter(page, state)
    _open_candidates(page)
    labels = page.evaluate(
        "() => Array.from(document.querySelectorAll('#candidates-table .cand-signals .sig-badge'))"
        ".map((b) => b.textContent.trim())"
    )
    assert "Nuclear" in labels, "expected a Nuclear badge for the nuclear-adjacent site"


def test_zoning_badge_renders_for_restrictive_state(page, base_url):
    """A site in a restrictive DC regulatory-climate state (stamped
    s.dc_regulatory_climate at ingest) shows the red "Zoning" risk badge."""
    _ready(page, base_url)
    state = page.evaluate(
        "() => {"
        "  const byState = {};"
        "  for (const s of window.__sites) {"
        "    if (s.transmission_mi != null && s.state) (byState[s.state] ||= []).push(s);"
        "  }"
        "  for (const [st, arr] of Object.entries(byState)) {"
        "    if (arr.length >= 1 && arr.length <= 200) {"
        "      arr[0].dc_regulatory_climate = 'restrictive'; return st;"
        "    }"
        "  }"
        "  return null;"
        "}"
    )
    assert state, "expected a state with 1..200 scored sites"
    _set_state_filter(page, state)
    _open_candidates(page)
    labels = page.evaluate(
        "() => Array.from(document.querySelectorAll('#candidates-table .cand-signals .sig-badge'))"
        ".map((b) => b.textContent.trim())"
    )
    assert "Zoning" in labels, "expected a Zoning badge for the restrictive-state site"
