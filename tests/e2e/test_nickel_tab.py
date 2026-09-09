"""The Nickel Refining tab: lazy mount, lens toggle, URL state, map overlay.

The DOM-size cap is deliberately NOT re-asserted here.
`test_dom_size_under_5k_nodes` is the single canonical guard for it; with the
headroom this budget runs at, a duplicated assertion just doubles the flake
surface without adding coverage (observed 2026-07-26).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _open_tab(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.click("#tab-nickel")
    page.wait_for_selector("#nickel-table tbody tr", timeout=30_000)


def test_tab_mounts_lazily_from_its_template(page: Page, base_url: str) -> None:
    """Template content is excluded from document.querySelectorAll('*'), which
    is how this view stays out of the first-paint node budget. Before the tab
    is clicked the interior must not exist in the live DOM."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    assert page.locator("#nickel-table").count() == 0
    page.click("#tab-nickel")
    expect(page.locator("#nickel-table")).to_be_visible()


def test_ranked_table_renders_and_is_sorted_descending(
        page: Page, base_url: str) -> None:
    _open_tab(page, base_url)
    scores = page.eval_on_selector_all(
        "#nickel-table tbody tr td.cand-score",
        "els => els.map(e => parseInt(e.textContent, 10)).filter(n => !isNaN(n))",
    )
    assert len(scores) > 10, f"only {len(scores)} scored rows"
    assert scores == sorted(scores, reverse=True)


def test_lens_toggle_switches_the_ranking_and_the_url(
        page: Page, base_url: str) -> None:
    """`?nlens=` is only encoded off-default, and the two lenses genuinely
    rank different sites — the import lens lists port-served sites, the
    domestic lens rail-served ones."""
    _open_tab(page, base_url)
    assert "nlens=" not in page.url
    first_import = page.locator("#nickel-table tbody tr").first.get_attribute("data-id")

    page.click("[data-nickel-lens='domestic']")
    # syncUrl() writes through a 200ms debounce, so the URL must be WAITED on,
    # never read immediately after the click. Asserting straight away passed
    # in isolation and failed under load — a timing accident, not a flake.
    page.wait_for_url("**nlens=domestic**", timeout=5_000)
    first_domestic = page.locator("#nickel-table tbody tr").first.get_attribute("data-id")
    assert first_import != first_domestic

    page.click("[data-nickel-lens='import']")
    page.wait_for_function("!location.search.includes('nlens=')", timeout=5_000)


def test_import_lens_lists_only_port_served_sites(page: Page, base_url: str) -> None:
    """The score gate only asks whether the water join has run, which every
    site passes. The ranked list asks the stricter question the tab's own copy
    implies — the Maritime tab had to learn this distinction twice."""
    _open_tab(page, base_url)
    ids = page.eval_on_selector_all(
        "#nickel-table tbody tr", "els => els.slice(0, 40).map(e => e.dataset.id)")
    portless = page.evaluate(
        "(ids) => ids.filter(id => window.__sites.find(s => s.id === id)?.port_mi == null)",
        ids)
    assert portless == [], f"portless sites in the import ranking: {portless}"


def test_land_column_says_unknown_rather_than_failing_the_threshold(
        page: Page, base_url: str) -> None:
    """EPA publishes no acreage at all for its ~36k brownfield properties, so
    most rows are genuinely unknown. Rendering that as a failed threshold
    would be a fabricated negative."""
    _open_tab(page, base_url)
    cells = page.eval_on_selector_all(
        "#nickel-table tbody tr td:last-child",
        "els => els.map(e => e.textContent.trim())")
    assert any(c == "Unknown" for c in cells), cells[:10]


def test_water_column_distinguishes_unchecked_from_nothing_in_range(
        page: Page, base_url: str) -> None:
    """Three states, and collapsing any two of them misleads."""
    _open_tab(page, base_url)
    texts = page.eval_on_selector_all(
        "#nickel-table tbody tr td:nth-child(5)",
        "els => els.map(e => e.textContent.trim())")
    assert texts, "no water cells rendered"
    assert all(t != "—" for t in texts), (
        "a listed row shows the unchecked dash, but the join has run")


def test_anchor_overlay_markers_and_legend_row_render(
        page: Page, base_url: str) -> None:
    """Overlay markers belong on the map from first paint, not behind a tab
    visit. The CSS rule targets the icon class itself — a `.icon span` rule
    silently orphans if the inner span is later removed, which shipped once
    with the coal markers and was caught only by asserting computed style."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.wait_for_selector(".nickel-anchor-icon", timeout=30_000)
    assert page.locator(".nickel-anchor-icon").count() >= 10
    size = page.eval_on_selector(
        ".nickel-anchor-icon", "e => getComputedStyle(e).fontSize")
    assert size == "15px", f"anchor glyph is unstyled ({size})"
    expect(page.locator(".legend")).to_contain_text("Nickel supply chain")


@pytest.mark.parametrize("width", [375, 640, 768, 900, 1024, 1280])
def test_eleventh_tab_does_not_overflow_the_page_at_any_width(
        page: Page, base_url: str, width: int) -> None:
    """Adding the seventh tab put 590px of tab strip against a 375px viewport
    and scrolled the whole document sideways on every tab. The fix then only
    applied under 640px — and with ELEVEN tabs the row stops fitting around
    1000px, so a band opened between the breakpoint and the desktop layout
    where the overflow escaped onto the document again: measured 5px at
    900px wide against 0 on the prior ten-tab build.

    Checking one narrow width missed it. `.tabs` now scrolls at every width,
    and this is parametrized across the band so the next tab cannot reopen it.
    """
    page.set_viewport_size({"width": width, "height": 720})
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow == 0, f"page scrolls horizontally by {overflow}px at {width}px"


def test_confirmed_land_breaks_ties_ahead_of_unknown_land(
        page: Page, base_url: str) -> None:
    """The score cannot use acreage — it is a threshold, and unknown for most
    of the corpus — so two sites can tie on infrastructure while one is a
    confirmed 200-acre mill and the other a one-acre former school beside a
    rail spur. Within a tied score, confirmed-adequate land must sort first.
    """
    _open_tab(page, base_url)
    rows = page.eval_on_selector_all(
        "#nickel-table tbody tr",
        """els => els.map(e => {
             const s = window.__sites.find(x => x.id === e.dataset.id);
             const st = window.nickelAcreageStatus(s);
             return {
               score: parseInt(e.querySelector('td.cand-score').textContent, 10),
               land: st === true ? 2 : st === null ? 1 : 0,
             };
           })""")
    for a, b in zip(rows, rows[1:]):
        if a["score"] == b["score"]:
            assert a["land"] >= b["land"], (
                f"tied at {a['score']} but land rank fell {a['land']}->{b['land']}")


def test_deep_link_shows_loading_not_a_false_empty_result(
        page: Page, base_url: str) -> None:
    """Landing straight on #nickel builds the view before the lazy water and
    port joins resolve, so the first pass has nothing to rank. Saying "no
    sites match the current filters" there blames the user's filters for a
    fetch that has not finished — the same conflation the water cell avoids
    between "not checked" and "nothing in range".

    Caught in the browser, not by a test: every existing test clicked the tab
    after __APP_READY__, which is after the joins land.
    """
    page.goto(f"{base_url}/index.html#nickel")
    stats = page.locator("#nickel-stats")
    stats.wait_for(timeout=30_000)
    # Whatever the state, it must never claim the filters excluded everything
    # while the data is still arriving.
    seen = []
    for _ in range(40):
        txt = stats.inner_text()
        seen.append(txt)
        if "sorted by" in txt:
            break
        page.wait_for_timeout(250)
    assert any("sorted by" in t for t in seen), f"never populated: {seen[-1]!r}"
    false_empty = [t for t in seen if "No sites match" in t]
    assert not false_empty, (
        f"showed a false empty-result message while loading: {false_empty[0]!r}")


def test_sites_known_to_be_under_the_land_threshold_are_excluded(
        page: Page, base_url: str) -> None:
    """Land is stated as a threshold, so a site KNOWN to be smaller than it is
    not a candidate. The tie-break alone only reordered equal scores, which
    left under-threshold sites outranking buildable ones whenever the scores
    differed (Codex review). Unknown acreage still qualifies — EPA publishes
    none for its ~36k brownfields, and excluding unknowns would delete most of
    the corpus on a fact we do not have.
    """
    _open_tab(page, base_url)
    bad = page.eval_on_selector_all(
        "#nickel-table tbody tr",
        """els => els.map(e => {
             const s = window.__sites.find(x => x.id === e.dataset.id);
             return {id: e.dataset.id, status: window.nickelAcreageStatus(s)};
           }).filter(r => r.status === false)""")
    assert bad == [], f"under-threshold sites in the ranking: {bad[:5]}"
    # And unknowns must still be there, or the filter went too far.
    unknown = page.eval_on_selector_all(
        "#nickel-table tbody tr",
        """els => els.filter(e => window.nickelAcreageStatus(
             window.__sites.find(x => x.id === e.dataset.id)) === null).length""")
    assert unknown > 0, "unknown-acreage sites were wrongly excluded"


def test_a_failed_data_load_reports_an_error_not_a_false_empty(
        page: Page, base_url: str) -> None:
    """The loaders swallow their own rejections and a 404 becomes an empty
    payload, so the boot fan-out settles either way. Without tracking the
    failure the tab told the user their filters matched nothing, when in fact
    the data it ranks on never arrived (Codex round 2).

    Forced by aborting the request, which is the only way to reach the branch.
    """
    page.route("**/data/water-proximity.json", lambda route: route.abort())
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.click("#tab-nickel")
    stats = page.locator("#nickel-stats")
    stats.wait_for(timeout=30_000)
    page.wait_for_function(
        "document.getElementById('nickel-stats')"
        "?.textContent.includes('Could not load')", timeout=30_000)
    txt = stats.inner_text()
    assert "water" in txt, txt
    assert "No sites match" not in txt


def test_the_nickel_tab_retries_a_failed_port_load(
        page: Page, base_url: str) -> None:
    """The import lens ranks on `port_mi`. A failed eager fetch clears its
    promise, so opening the tab has to retry it — otherwise the default
    ranking stays empty until a reload or a visit to Maritime (Codex round 2).
    """
    state = {"failed": False}

    def handler(route):
        if not state["failed"]:
            state["failed"] = True
            route.abort()
        else:
            route.continue_()

    page.route("**/data/port-proximity.json", handler)
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.click("#tab-nickel")
    # The retry fires on tab activation; the ranking must recover without a
    # reload.
    page.wait_for_selector("#nickel-table tbody tr", timeout=60_000)
    assert page.locator("#nickel-table tbody tr").count() > 0
