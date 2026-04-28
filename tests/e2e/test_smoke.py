"""Frontend smoke test — guards against regressions like the wireTabs() shadow bug.

Covers the golden path: page loads, tab switch works, marker click opens panel,
table row click opens panel, Esc closes panel.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.e2e


def test_page_loads_with_meta(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1", timeout=10000)
    assert "sites" in page.locator("#meta").text_content()


def test_tab_switch(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")

    # Default: map view
    assert page.locator("#view-map").is_visible()
    assert not page.locator("#view-table").is_visible()

    page.locator("#tab-table").click()
    page.wait_for_function("!document.getElementById('view-table').hidden")
    assert page.locator("#view-table").is_visible()

    page.locator("#tab-map").click()
    page.wait_for_function("!document.getElementById('view-map').hidden")
    assert page.locator("#view-map").is_visible()


def test_table_row_opens_detail(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")

    page.locator("#tab-table").click()
    first_row = page.locator("#sites-table tbody tr").first
    first_row.wait_for()
    first_row.click()

    page.wait_for_selector("#detail:not([hidden])")
    assert page.locator("#detail-title").text_content().strip() not in ("", "—")


def test_escape_closes_detail(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    page.locator("#sites-table tbody tr").first.click()
    page.wait_for_selector("#detail:not([hidden])")

    page.keyboard.press("Escape")
    page.wait_for_selector("#detail[hidden]")


def test_map_marker_click_opens_detail(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")

    # Markers are Canvas-rendered (no DOM nodes). Trigger via JS — hits the
    # same Leaflet event path as a real click.
    page.wait_for_function("window.__sitesLoaded === true || document.querySelectorAll('.leaflet-canvas-icon-layer, .leaflet-zoom-animated').length > 0")
    page.evaluate("""
        () => {
            const layer = window.__markerLayer;
            if (!layer) throw new Error('marker layer not exposed');
            const layers = layer.getLayers();
            if (!layers.length) throw new Error('no markers');
            layers[0].fire('click');
        }
    """)
    page.wait_for_selector("#detail:not([hidden])")


def test_search_filters_table(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()

    page.wait_for_selector("#sites-table tbody tr")
    total = page.evaluate("document.querySelectorAll('#sites-table tbody tr').length")
    assert total > 0

    # Type a query that won't match anything
    page.locator("#search").fill("zzzzzzznotreal")
    page.wait_for_function("document.getElementById('search-count').textContent.indexOf('0 of') === 0")
    visible = page.evaluate(
        "Array.from(document.querySelectorAll('#sites-table tbody tr')).filter(r => !r.hidden).length"
    )
    assert visible == 0

    # Clear → all visible again
    page.locator("#search").fill("")
    page.wait_for_function("document.getElementById('search-count').textContent === ''")
    visible = page.evaluate(
        "Array.from(document.querySelectorAll('#sites-table tbody tr')).filter(r => !r.hidden).length"
    )
    assert visible == total


def test_legend_renders(page, base_url):
    """Legend shows program rows that exist in loaded data — Superfund first paint
    only includes 'Superfund'; 'Brownfield' shows up after lazy-load completes."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    legend = page.locator(".legend")
    legend.wait_for()
    text = legend.text_content()
    assert "Superfund" in text
    assert "Program" in text  # legend title


def test_filters_panel_toggles(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#filters-toggle").click()
    page.wait_for_selector("#filters:not([hidden])")
    assert page.locator("#f-state").is_visible()
    assert page.locator("#f-status").is_visible()
    assert page.locator("#f-acreage").is_visible()


def test_state_filter_narrows_table(page, base_url):
    """Picking a state from the dropdown filters table + map markers."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    page.locator("#filters-toggle").click()
    page.wait_for_selector("#filters:not([hidden])")

    # Pick the first non-empty state option deterministically.
    page.evaluate(
        "() => { const sel = document.getElementById('f-state');"
        " const opt = Array.from(sel.options).find(o => o.value);"
        " sel.value = opt.value; sel.dispatchEvent(new Event('change')); }"
    )
    page.wait_for_function("document.getElementById('search-count').textContent.length > 0")
    visible = page.evaluate(
        "Array.from(document.querySelectorAll('#sites-table tbody tr')).filter(r => !r.hidden).length"
    )
    total = page.evaluate("document.querySelectorAll('#sites-table tbody tr').length")
    assert 0 < visible < total


def test_url_state_sharing(page, base_url):
    """Filters round-trip through ?state= in the URL."""
    page.goto(f"{base_url}/index.html?state=NY")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    page.wait_for_function("document.getElementById('search-count').textContent.length > 0")
    states = page.evaluate(
        "Array.from(document.querySelectorAll('#sites-table tbody tr'))"
        ".filter(r => !r.hidden).slice(0, 5).map(r => r.children[2].textContent.trim())"
    )
    assert all(s == "NY" for s in states), states


def test_brownfields_visible_by_default(page, base_url):
    """v1.3: both programs are on by default. Once ACRES finishes lazy-loading,
    the table contains brownfield rows and the legend shows the Brownfield row."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    # Wait for lazy-loaded brownfield records to land in the dataset.
    page.wait_for_function(
        "Array.from(document.querySelectorAll('#sites-table tbody tr'))"
        ".some(r => r.querySelector('[data-program=\"brownfield\"]'))",
        timeout=20000,
    )
    legend_text = page.locator(".legend").text_content()
    assert "Brownfield" in legend_text


def test_state_filter_shows_acreage_summary(page, base_url):
    """v1.3: search-count includes total acres + state name when a state filter is on."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#filters-toggle").click()
    page.wait_for_selector("#filters:not([hidden])")
    page.evaluate(
        "() => { const sel = document.getElementById('f-state');"
        " const opt = Array.from(sel.options).find(o => o.value);"
        " sel.value = opt.value; sel.dispatchEvent(new Event('change')); }"
    )
    page.wait_for_function("document.getElementById('search-count').textContent.indexOf(' in ') > -1")
    text = page.locator("#search-count").text_content()
    # "X of Y in ST · Z ac …" — assert the structure
    assert " in " in text
    assert " ac" in text


def test_theme_toggle_persists(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    initial = page.evaluate("document.documentElement.getAttribute('data-theme')")
    page.locator("#theme-toggle").click()
    after = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert after != initial
    stored = page.evaluate("localStorage.getItem('theme')")
    assert stored in ("light", "dark")
