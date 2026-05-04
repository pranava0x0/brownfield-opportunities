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
    # NPL Status was a `<select multiple>` (UAT bug: hidden Cmd-click
    # interaction). It's now a checkbox group keyed by `data-status`.
    assert page.locator("#f-status-checks").is_visible()
    assert page.locator("#f-status-checks input[data-status='F']").is_visible()
    assert page.locator("#f-acreage").is_visible()


def test_state_filter_narrows_table(page, base_url):
    """Picking a state from the dropdown filters table + map markers.

    Table is now paginated, so DOM-row count maxes out at TABLE_PAGE_SIZE.
    Assert against the in-memory filtered count (search-count text + the
    `tableState.filtered` length exposed for tests).
    """
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.locator("#tab-table").click()
    page.locator("#filters-toggle").click()
    page.wait_for_selector("#filters:not([hidden])")

    page.evaluate(
        "() => { const sel = document.getElementById('f-state');"
        " const opt = Array.from(sel.options).find(o => o.value);"
        " sel.value = opt.value; sel.dispatchEvent(new Event('change')); }"
    )
    page.wait_for_function(
        "document.getElementById('search-count').textContent.indexOf(' of ') > -1"
    )
    text = page.locator("#search-count").text_content()
    # Format: "N of TOTAL in ST · X ac (…)"
    import re
    m = re.match(r"([\d,]+) of ([\d,]+)", text)
    assert m, f"unexpected count text: {text!r}"
    filtered = int(m.group(1).replace(",", ""))
    total = int(m.group(2).replace(",", ""))
    assert 0 < filtered < total


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
    """All four programs are on by default. Once all lazy loads complete,
    the legend shows Superfund, Brownfield, FUDS, and BRAC rows."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    legend_text = page.locator(".legend").text_content()
    assert "Brownfield" in legend_text
    # After all lazy loads complete, the legend must show all four programs.
    assert "FUDS" in legend_text
    assert "BRAC" in legend_text


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


# ----- Regression tests for UAT 2026-04-29 fixes -----


def test_app_ready_signal(page, base_url):
    """`window.__APP_READY__` flips true and `brownfield:ready` event fires
    after Superfund + ACRES hydration completes. UAT had no reliable
    hydration hook; tests had to poll header text or network status."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    rows = page.evaluate("document.querySelectorAll('#sites-table tbody tr').length")
    # Pagination: cap at TABLE_PAGE_SIZE on first paint, not all 38k.
    assert rows <= 300, f"expected paginated table, got {rows} rows"


def test_table_is_paginated(page, base_url):
    """Table starts paginated at TABLE_PAGE_SIZE and scrolling near the end
    triggers IntersectionObserver-driven append. Replaces the previous
    behavior of injecting all 37,911 rows on first paint."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.locator("#tab-table").click()
    initial_rows = page.evaluate("document.querySelectorAll('#sites-table tbody tr').length")
    assert 100 <= initial_rows <= 300

    page.evaluate("""
        () => { const w = document.querySelector('.table-wrap'); w.scrollTop = w.scrollHeight; }
    """)
    page.wait_for_function(
        f"document.querySelectorAll('#sites-table tbody tr').length > {initial_rows}",
        timeout=5000,
    )


def test_dom_size_under_5k_nodes(page, base_url):
    """Page weight regression test: total DOM nodes must stay under ~5k.
    UAT measured ~265k (37,911 rows × 7 cells); pagination drops it to ~3k."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    nodes = page.evaluate("document.querySelectorAll('*').length")
    assert nodes < 5000, f"DOM has {nodes} nodes — pagination is broken"


def test_npl_status_checkboxes(page, base_url):
    """NPL Status filter is now four checkboxes (was a `<select multiple>`
    with hidden Cmd-click semantics). Selecting Final NPL narrows the set."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#filters-toggle").click()
    page.wait_for_selector("#filters:not([hidden])")

    # All four checkboxes present and unchecked initially.
    for code in ("F", "P", "D", "N"):
        loc = page.locator(f"#f-status-checks input[data-status='{code}']")
        assert loc.is_visible()
        assert not loc.is_checked()

    page.locator("#f-status-checks input[data-status='F']").check()
    page.wait_for_function(
        "document.getElementById('search-count').textContent.length > 0"
    )
    text = page.locator("#search-count").text_content()
    assert " of " in text


def test_state_dropdown_shows_full_names(page, base_url):
    """Bug: dropdown only showed postal codes. Now shows 'Alabama (AL)' etc.,
    with territories grouped under <optgroup label="Territories">."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.locator("#filters-toggle").click()

    first_state_label = page.evaluate(
        "() => Array.from(document.querySelectorAll('#f-state > option')).filter(o=>o.value)[0].textContent"
    )
    # Sorted by full name → first non-empty real state is "Alabama (AL)".
    assert "Alabama" in first_state_label
    assert "(AL)" in first_state_label

    territory_count = page.evaluate(
        "document.querySelectorAll(\"#f-state optgroup[label='Territories'] option\").length"
    )
    assert territory_count > 0


def test_acreage_slider_has_visible_ticks(page, base_url):
    """Slider was an unlabeled log10 0–6 — users had no scale reference.
    Tick labels (1, 10, 100, 1k, 10k, 100k, 1M) are now rendered below."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#filters-toggle").click()
    labels = page.evaluate(
        "Array.from(document.querySelectorAll('.acreage-ticks-labels span')).map(s => s.textContent)"
    )
    assert labels == ["1", "10", "100", "1k", "10k", "100k", "1M"]


def test_detail_panel_truly_hides_on_close(page, base_url):
    """Bug: `.detail[hidden]` had `display: block` overriding the [hidden]
    attribute, leaving a visible sliver of stale text. Fix uses
    `visibility: hidden` synced to the slide-out transform (180 ms delay
    so the slide animation plays out before visibility flips)."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    page.locator("#sites-table tbody tr").first.click()
    page.wait_for_selector("#detail:not([hidden])")
    page.locator("#detail-close").click()
    page.wait_for_selector("#detail[hidden]")

    # aria-hidden flips synchronously.
    aria_hidden = page.evaluate(
        "document.getElementById('detail').getAttribute('aria-hidden')"
    )
    assert aria_hidden == "true"

    # visibility transition is 180ms — wait it out and verify the panel is
    # truly off-screen (no stale-content sliver on the right edge).
    page.wait_for_function(
        "getComputedStyle(document.getElementById('detail')).visibility === 'hidden'",
        timeout=2000,
    )
    rect = page.evaluate(
        "() => { const r = document.getElementById('detail').getBoundingClientRect();"
        " return { x: r.x, w: r.width, vw: window.innerWidth }; }"
    )
    # Panel left-edge must be at or past the viewport's right edge.
    assert rect["x"] >= rect["vw"] - 1, f"panel still in viewport: {rect}"


def test_unknown_site_id_shows_toast(page, base_url):
    """Bug: `?site=BOGUS` opened an empty detail panel with em-dashes.
    Fix shows a non-blocking toast and keeps the URL intact so the user
    can copy/correct the ID."""
    page.goto(f"{base_url}/index.html?site=BOGUS_NOT_REAL_ID")
    # Wait long enough for ACRES lazy-load to either land or fail before the
    # "not found" toast fires (the click path also waits on acresLoadingPromise).
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.wait_for_selector("#toast.visible", timeout=2000)
    text = page.locator("#toast").text_content()
    assert "not found" in text.lower()
    assert page.locator("#detail").is_hidden()


def test_url_unwinds_on_filter_clear(page, base_url):
    """Bug per UAT: clearing search left `?q=` in the URL. `min_ac=0` left
    `?min_ac=` in the URL. Verify the URL writer drops keys at default."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#filters-toggle").click()

    # Search round-trip
    page.locator("#search").fill("philly")
    page.wait_for_function("location.search.indexOf('q=philly') > -1")
    page.locator("#search").fill("")
    # Re-fire the input event — fill('') doesn't always emit input on some browsers.
    page.evaluate(
        "document.getElementById('search').dispatchEvent(new Event('input', {bubbles:true}))"
    )
    page.wait_for_function("location.search.indexOf('q=') === -1", timeout=2000)

    # Acreage round-trip
    page.evaluate(
        "() => { const a = document.getElementById('f-acreage'); a.value = '2'; a.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    page.wait_for_function("location.search.indexOf('min_ac=') > -1")
    page.evaluate(
        "() => { const a = document.getElementById('f-acreage'); a.value = '0'; a.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    page.wait_for_function("location.search.indexOf('min_ac=') === -1", timeout=2000)


def test_search_auto_fits_map(page, base_url):
    """When a filter narrows to a small set, the map auto-fits to the
    visible bbox. UAT: searching 'picillo' (1 result) left the lower-48
    view active and the marker was nearly invisible."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    initial_zoom = page.evaluate("window.__map.getZoom()")
    page.locator("#search").fill("picillo")
    # refit is debounced 350ms
    page.wait_for_function(
        f"window.__map.getZoom() > {initial_zoom + 2}",
        timeout=4000,
    )


def test_skip_link_and_landmarks(page, base_url):
    """A11y: skip-to-content link, toolbar nav landmark, main role."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    skip = page.locator("a.skip-link")
    assert skip.get_attribute("href") == "#main"
    assert page.locator("nav.topbar-controls[aria-label='Toolbar']").count() == 1
    assert page.locator("main#main").count() == 1
    assert page.locator("aside#detail[aria-hidden='true']").count() == 1


def test_federal_facility_decoded_cleanly(page, base_url):
    """Bug: detail panel showed 'Code Not a Federal Facility' (raw EPA code
    leaked through). Fix decodes to a clean label and collapses the upstream
    double-space EPA ships in 'Not a  Federal Facility'."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    # First Superfund row (ACRES rows have no NPL status → use program filter)
    page.evaluate(
        "() => { const tr = Array.from(document.querySelectorAll('#sites-table tbody tr'))"
        ".find(r => r.querySelector('[data-program=\"superfund\"]')); tr.click(); }"
    )
    page.wait_for_selector("#detail:not([hidden])")
    fed = page.locator("#d-fed").text_content()
    # Must not show "Code …" prefix and must not have double-space.
    assert not fed.startswith("Code ")
    assert "  " not in fed
    # Should be one of the two clean labels.
    assert fed in ("Federal Facility", "Not a Federal Facility", "—")


def test_owner_section_uses_user_friendly_copy(page, base_url):
    """Bug: detail panel showed 'N/A — see backlog' (project jargon) for
    Current owner, Historical owners, Encumbrances, and Infrastructure
    proximity. Fix shows 'Not available' instead."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    page.locator("#sites-table tbody tr").first.click()
    page.wait_for_selector("#detail:not([hidden])")
    for sel in ("#d-owner", "#d-owners-hist", "#d-encumb"):
        text = page.locator(sel).text_content()
        assert "see backlog" not in text.lower()
        assert text == "Not available"


# ----- v1.8 design refresh + UAT 2026-04-30 fixes -----


def test_hero_strip_renders(page, base_url):
    """v1.8: hero strip with eyebrow, serif H2, dek, and KPI deck above the map."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    # Hero copy (visible on desktop)
    assert page.locator(".hero h2").count() == 1
    assert "America" in page.locator(".hero h2").text_content()
    # Hero refresh stamp filled in (not the dash placeholder)
    refresh = page.locator("#hero-refresh").text_content()
    assert refresh.startswith("Updated") and "—" not in refresh
    # KPI deck — four cells, each with a non-dash number
    for kpi_id in ("kpi-total", "kpi-acres", "kpi-dc", "kpi-states"):
        text = page.locator(f"#{kpi_id}").text_content()
        assert text != "—" and text != "", f"{kpi_id} still showing placeholder: {text!r}"


def test_footer_with_sources(page, base_url):
    """v1.8: footer cites the five data sources + refresh date + GitHub link."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    footer = page.locator("footer.site-footer")
    assert footer.count() == 1
    text = footer.text_content()
    for source in ("EPA Superfund", "EPA ACRES", "USACE FUDS", "DOD BRAC", "EPA RE-Powering"):
        assert source in text, f"missing source: {source}"
    refresh = page.locator("#footer-refresh").text_content()
    assert refresh.startswith("Refreshed") and "—" not in refresh


def test_meta_text_shows_per_program_counts(page, base_url):
    """v1.8: meta text now reflects every loaded program — the previous
    "X Superfund + Y brownfields" template mislabeled the breakdown after
    FUDS/BRAC also lazy-loaded."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    text = page.locator("#meta").text_content()
    # All four programs should be named in the meta after ready.
    assert "Superfund" in text
    assert "brownfields" in text
    assert "FUDS" in text
    assert "BRAC" in text
    # And it should still carry the refreshed date.
    assert "refreshed" in text.lower()


def test_filter_chip_hidden_by_default_visible_when_active(page, base_url):
    """v1.8: chip badge on the gear button counts active filters.
    Bug fix: `display: inline-flex` was overriding `[hidden]` so the chip
    always showed (with stale "0") regardless of state."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    # No filters yet → chip is display:none.
    chip_display = page.evaluate(
        "getComputedStyle(document.getElementById('filters-chip')).display"
    )
    assert chip_display == "none", f"chip leaking on first paint: {chip_display}"

    # Apply a filter → chip becomes visible with count 1.
    page.locator("#search").fill("philly")
    page.wait_for_function(
        "getComputedStyle(document.getElementById('filters-chip')).display !== 'none'",
        timeout=2000,
    )
    chip_text = page.locator("#filters-chip").text_content()
    assert chip_text == "1"

    # Clear the search → chip hides again.
    page.locator("#search").fill("")
    page.evaluate(
        "document.getElementById('search').dispatchEvent(new Event('input', {bubbles:true}))"
    )
    page.wait_for_function(
        "getComputedStyle(document.getElementById('filters-chip')).display === 'none'",
        timeout=2000,
    )


def test_city_and_county_titlecased(page, base_url):
    """v1.8: source data ships ALL CAPS for city/county. `prettyPlace()`
    title-cases at ingest time so the table doesn't shout."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    page.wait_for_selector("#sites-table tbody tr")
    # Pull the first 20 rows' city/county cells. None should be all-caps
    # words (allow short uppercase tokens like "AFB", "DC" to pass).
    rows = page.evaluate(
        "() => Array.from(document.querySelectorAll('#sites-table tbody tr')).slice(0,20).map(r => ({"
        " city: r.children[5].textContent.trim(),"
        " county: r.children[6].textContent.trim() })) "
    )
    for r in rows:
        for field in ("city", "county"):
            v = r[field]
            if not v or v == "—":
                continue
            words = [w for w in v.split() if len(w) > 3 and w.isalpha()]
            for w in words:
                assert w != w.upper(), (
                    f"row has un-prettified {field}: {v!r} (word: {w!r})"
                )


def test_address_titlecased_in_detail_panel(page, base_url):
    """v1.8: bug — `s.city` was prettified at ingest but `s.address` was not,
    so detail panel showed 'FOX RIVER AND GREEN BAY, Green Bay, WI'."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    # Pick a Superfund row (those are the records that carry s.address).
    page.evaluate(
        "() => { const tr = Array.from(document.querySelectorAll('#sites-table tbody tr'))"
        ".find(r => r.querySelector('[data-program=\"superfund\"]')); tr.click(); }"
    )
    page.wait_for_selector("#detail:not([hidden])")
    addr = page.locator("#d-addr").text_content().strip()
    if addr in ("—", ""):
        return  # row had no address — try not to flake on a sparse record
    # Address often contains tokens like "WI" / "USA" / "NW" that should stay
    # uppercase. Look only at multi-char alphabetic words.
    words = [w for w in addr.replace(",", " ").split() if len(w) > 3 and w.isalpha()]
    for w in words:
        assert w != w.upper(), f"address still ALL CAPS: {addr!r} (word: {w!r})"


def test_detail_panel_program_stripe(page, base_url):
    """v1.8: 4px program-color top stripe set via `--detail-stripe` CSS var.
    Verify the var is set to the expected program color when a row is clicked."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    # Click a Superfund row — stripe should be the --program-superfund color.
    page.evaluate(
        "() => { const tr = Array.from(document.querySelectorAll('#sites-table tbody tr'))"
        ".find(r => r.querySelector('[data-program=\"superfund\"]')); tr.click(); }"
    )
    page.wait_for_selector("#detail:not([hidden])")
    stripe = page.evaluate(
        "document.getElementById('detail').style.getPropertyValue('--detail-stripe')"
    )
    expected = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--program-superfund').trim()"
    )
    assert stripe.strip().lower() == expected.lower(), f"stripe {stripe!r} != program color {expected!r}"


def test_table_sort_glyph_appears(page, base_url):
    """v1.8: active sort column header gets a ▲/▼ glyph via
    `data-sort-glyph` attr; CSS reads it through `[aria-sort]::after`."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("document.getElementById('meta').textContent.indexOf('sites') > -1")
    page.locator("#tab-table").click()
    # Default sort is acreage desc — the Acreage <th> should carry the glyph.
    glyph = page.evaluate(
        "document.querySelector('#sites-table thead th[data-sort=\"acreage\"]').getAttribute('data-sort-glyph')"
    )
    assert glyph in ("▲", "▼")


def test_chip_count_hidden_attribute_works(page, base_url):
    """Regression for the [hidden] vs `display: inline-flex` trap.
    The class of bug bit detail-panel once already; the same trap is on
    `.chip-count`. Add a CSS rule `[hidden] { display: none }` for any
    element that has both an explicit `display:` rule and a `hidden` attr."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    chip = page.locator("#filters-chip")
    assert chip.evaluate("el => el.hidden") is True
    display = page.evaluate(
        "getComputedStyle(document.getElementById('filters-chip')).display"
    )
    assert display == "none", (
        f"chip with hidden=true rendered as display:{display} — "
        "the [hidden] trap is back. Add `.chip-count[hidden] { display: none }`."
    )


# ----- v1.9: federal acreage / ownership / documents enrichment -----


def test_owner_source_label_shown_for_fuds(page, base_url):
    """v1.9: detail panel shows owner-source citation alongside current owner.
    Picks a FUDS site (which always has an owner from USACE) by clicking
    its row in the table after filtering programs to FUDS only."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    # Programmatically pick a FUDS site with an owner — table sort/state may vary.
    site_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (s.program === 'fuds' && s.current_owner) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    assert site_id, "no FUDS site with current_owner found in loaded data"
    page.evaluate(f"window.__selectSite('{site_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    owner_source = page.locator("#d-owner-source").text_content()
    assert "FUDS" in owner_source, f"expected FUDS in owner source, got {owner_source!r}"


def test_documents_block_renders_for_enriched_site(page, base_url):
    """v1.9: detail panel renders Federal documents block when the site
    has been enriched by epa-superfund-docs. Skips silently if the
    sample dataset doesn't yet include any enriched sites."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    enriched_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (Array.isArray(s.documents) && s.documents.length > 0) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    if not enriched_id:
        import pytest
        pytest.skip("no docs-enriched sites in current dataset — re-run epa-superfund-docs")
    page.evaluate(f"window.__selectSite('{enriched_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    block = page.locator("#d-docs-block")
    assert block.evaluate("el => el.hidden") is False
    # Each document should render as a link with title text + date metadata.
    items = page.locator("#d-docs li")
    assert items.count() > 0
    first_link = items.first.locator("a").first
    assert first_link.get_attribute("href").startswith("https://semspub.epa.gov")
    # "All site documents on EPA →" deep-link should point at cumulis docdata
    more_href = page.locator("#d-docs-more").get_attribute("href")
    assert "second.docdata" in more_href
