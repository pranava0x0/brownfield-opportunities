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
