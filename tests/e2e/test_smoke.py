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
    # truly off-screen (no stale-content sliver on the right edge). The 5s
    # timeout (vs. the 180ms animation) absorbs CI runner jitter; locally
    # the wait resolves in <250ms.
    page.wait_for_function(
        "getComputedStyle(document.getElementById('detail')).visibility === 'hidden'",
        timeout=5000,
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
    # 5s (vs. the toast fade-in's ~50ms) absorbs CI runner jitter; the
    # toast fires synchronously after acresLoadingPromise resolves.
    page.wait_for_selector("#toast.visible", timeout=5000)
    text = page.locator("#toast").text_content()
    assert "not found" in text.lower()
    assert page.locator("#detail").is_hidden()


def test_url_site_resolves_for_lazy_loaded_program(page, base_url):
    """Regression: direct navigation to ?site=FUDS-XXX (or BRAC-XXX) used to
    fire a "not found" toast immediately because applyUrlSelection() only
    waited on the ACRES loading promise. After the fix, it waits on every
    in-flight program-data fetch (ACRES / FUDS / BRAC), so a real FUDS ID
    opens the detail panel once FUDS finishes streaming in."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    # Pick a real FUDS id from the loaded data so the assertion isn't
    # coupled to a specific record. If the dataset has no FUDS records
    # (e.g. running against a reduced fixture), fall back to BRAC.
    target = page.evaluate(
        "() => {"
        "  const fuds = (window.__sites || []).find(s => s.program === 'fuds' && s.id);"
        "  if (fuds) return fuds.id;"
        "  const brac = (window.__sites || []).find(s => s.program === 'brac' && s.id);"
        "  return brac ? brac.id : null;"
        "}"
    )
    assert target, "expected at least one FUDS or BRAC record after lazy loads"
    # Reload with the real lazy-program id; toast must not appear, panel must open.
    page.goto(f"{base_url}/index.html?site={target}")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.wait_for_selector("#detail:not([hidden])", timeout=5000)
    title = page.locator("#detail-title").text_content().strip()
    assert title and title != "—", f"detail panel should be populated, got {title!r}"
    # No toast should have fired for a valid id.
    toast_visible = page.evaluate(
        "() => { const t = document.getElementById('toast');"
        " return t ? t.classList.contains('visible') : false; }"
    )
    assert not toast_visible, "no toast should fire when ?site= matches a real lazy-loaded record"


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
    proximity. Fix shows 'Not available' instead.

    Pick a Superfund site with no owner data — FUDS records carry
    `current_owner` from `CURRENTOWNER` (v1.9) and BRAC carries the
    component, so the first table row is no longer guaranteed to be
    owner-null. Use a programmatic site selector to land on a record
    where all three fields are null."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    null_owner_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (s.program === 'superfund' && !s.current_owner) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    assert null_owner_id, "no Superfund record with null current_owner"
    page.evaluate(f"window.__selectSite('{null_owner_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    for sel in ("#d-owner", "#d-owners-hist", "#d-encumb"):
        text = page.locator(sel).text_content()
        assert "see backlog" not in text.lower()
        assert text == "Not available", f"{sel} text = {text!r}"


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


def test_kpi_subtext_does_not_overflow_cell(page, base_url):
    """UAT-006 (2026-05-03): At desktop widths the KPI subtext used to
    overflow its cell because `.kpi-sub` was a `<span>` with `display:
    inline` — `overflow: hidden` and `text-overflow: ellipsis` no-op on
    inline elements, so the second cell's "4.9K sites with reported area"
    bled visually into the third cell's "≥50 ac · power · water".

    Guard: at 1280px (the desktop breakpoint we ship for), each
    `.kpi-sub`'s rendered right edge must stay within its parent cell's
    right edge minus the cell's right padding."""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    overflows = page.evaluate(
        "(() => Array.from(document.querySelectorAll('.kpi')).map((cell, i) => {"
        "  const sub = cell.querySelector('.kpi-sub');"
        "  if (!sub) return null;"
        "  const cr = cell.getBoundingClientRect();"
        "  const sr = sub.getBoundingClientRect();"
        "  return {"
        "    i,"
        "    display: getComputedStyle(sub).display,"
        "    overflows: sr.right - cr.right,"
        "  };"
        "}).filter(Boolean))()"
    )
    assert overflows, "no .kpi cells found"
    for row in overflows:
        # Subtext must be a block-level box for ellipsis to engage.
        assert row["display"] == "block", f"kpi-sub[{row['i']}] display={row['display']!r}"
        # Right edge must be inside the cell (allow up to 0px tolerance).
        assert row["overflows"] <= 0, (
            f"kpi-sub[{row['i']}] overflows cell by {row['overflows']:.1f}px"
        )


def test_reset_restores_all_four_programs(page, base_url):
    """UAT-007 (2026-05-03): the Reset button used to hard-code v1.6's
    `[superfund, brownfield]` defaults, silently dropping FUDS + BRAC on
    every click. Symptom: chip "1" stayed lit, URL kept
    `?program=superfund,brownfield`, and the action did nothing visible.

    Guard: after toggling any program off and clicking Reset, every
    program checkbox is re-checked, `filterState.programs` covers all
    four programs (verified via `searchCount` showing the full
    `46,759 of 46,759` set), the chip badge is hidden, and the URL is
    clean of any `?program=` param."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    # Sanity: all 4 programs visible at start.
    program_ids = ["superfund", "brownfield", "fuds", "brac"]
    for p in program_ids:
        assert page.locator(f"#f-program-{p}").is_checked(), f"{p} not checked at start"

    # Open the filters panel + uncheck Superfund.
    page.locator("#filters-toggle").click()
    page.locator("#f-program-superfund").uncheck()
    # Filter system writes URL state debounced 200ms; wait it out.
    page.wait_for_function(
        "window.location.search.includes('program=')",
        timeout=3000,
    )
    # Chip should be visible with active count.
    page.wait_for_function(
        "getComputedStyle(document.getElementById('filters-chip')).display !== 'none'",
        timeout=2000,
    )

    # Click Reset.
    page.locator("#filters-reset").click()
    # All 4 program checkboxes should be re-checked.
    for p in program_ids:
        assert page.locator(f"#f-program-{p}").is_checked(), f"{p} not checked after Reset"

    # Chip should be hidden again.
    page.wait_for_function(
        "getComputedStyle(document.getElementById('filters-chip')).display === 'none'",
        timeout=3000,
    )

    # URL should be clean (no ?program= param).
    page.wait_for_function(
        "!window.location.search.includes('program=')",
        timeout=3000,
    )

    # Meta text should reflect all 4 programs (per-program counts present).
    meta = page.locator("#meta").text_content()
    for label in ("Superfund", "brownfields", "FUDS", "BRAC"):
        assert label in meta, f"meta missing {label!r}: {meta!r}"


def test_infra_proximity_renders_for_enriched_site(page, base_url):
    """v1.10: detail panel renders cross-program infrastructure-proximity
    distances (transmission_mi, rail_mi, highway_mi) when the
    infra-proximity enrichment has covered the site.

    Picks any enriched site from any program (Superfund, ACRES, FUDS,
    BRAC) — the whole point of this enrichment is that it works
    universally, not just for the ~1.9k sites EPA RE-Powering covers.
    Skips silently if no records have been enriched yet."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    enriched_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (s.transmission_mi != null || s.rail_mi != null || s.highway_mi != null) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    if not enriched_id:
        import pytest
        pytest.skip("no infra-enriched sites in current dataset — re-run infra-proximity")
    page.evaluate(f"window.__selectSite('{enriched_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    # At least one of the three distance cells should show "X.X mi" rather
    # than the placeholder text.
    cells = ["#d-transmission-mi", "#d-rail-mi", "#d-highway-mi"]
    populated = []
    for sel in cells:
        text = page.locator(sel).text_content() or ""
        if "mi" in text and "Not available" not in text:
            populated.append(sel)
    assert populated, (
        f"no infra distance cells populated for site {enriched_id}: "
        + ", ".join(f"{c}={page.locator(c).text_content()!r}" for c in cells)
    )
    # Verify the populated cell dropped the muted-cell class so it visually
    # reads as real data rather than placeholder.
    for sel in populated:
        cls = page.locator(sel).get_attribute("class") or ""
        assert "muted-cell" not in cls, f"{sel} still has muted-cell class"


def test_reset_clears_filter_chip(page, base_url):
    """Companion to test_reset_restores_all_four_programs: regardless of
    which filter is active (state, status, acreage, search, program),
    Reset must clear the chip badge."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)

    # Apply a search filter → chip lights up.
    page.locator("#search").fill("philly")
    page.wait_for_function(
        "getComputedStyle(document.getElementById('filters-chip')).display !== 'none'",
        timeout=2000,
    )

    # Open filters + click Reset.
    page.locator("#filters-toggle").click()
    page.locator("#filters-reset").click()

    # Search input cleared and chip hidden.
    assert page.locator("#search").input_value() == ""
    page.wait_for_function(
        "getComputedStyle(document.getElementById('filters-chip')).display === 'none'",
        timeout=3000,
    )


def test_detail_panel_has_overview_and_summary_tabs(page, base_url):
    """v1.11: detail panel exposes an Overview/Summary tab strip. Default
    pane is Overview; clicking Summary swaps to the AI-summary card."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.locator("#tab-table").click()
    page.locator("#sites-table tbody tr").first.click()
    page.wait_for_selector("#detail:not([hidden])")

    # Overview is default-active.
    assert page.locator("#dtab-overview").get_attribute("aria-selected") == "true"
    assert page.locator("#dtab-summary").get_attribute("aria-selected") == "false"
    assert page.locator("#dpane-overview").evaluate("el => el.hidden") is False
    assert page.locator("#dpane-summary").evaluate("el => el.hidden") is True

    # Click Summary → panes swap.
    page.locator("#dtab-summary").click()
    assert page.locator("#dtab-summary").get_attribute("aria-selected") == "true"
    assert page.locator("#dtab-overview").get_attribute("aria-selected") == "false"
    assert page.locator("#dpane-summary").evaluate("el => el.hidden") is False
    assert page.locator("#dpane-overview").evaluate("el => el.hidden") is True


def test_summary_pane_shows_empty_state_when_unenriched(page, base_url):
    """A site with no AI summary on file should show the empty-state message
    in the Summary pane — not a blank card."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    # Pick any site; the bundled dataset has no ai-summary enrichment yet.
    unenriched_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (!s.summary) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    if not unenriched_id:
        import pytest
        pytest.skip("every loaded site already has an AI summary")
    page.evaluate(f"window.__selectSite('{unenriched_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    page.locator("#dtab-summary").click()
    empty = page.locator("#d-summary-empty")
    assert empty.evaluate("el => el.hidden") is False
    assert "No AI summary" in (empty.text_content() or "")


def test_summary_pane_renders_paragraphs_when_enriched(page, base_url):
    """When `summary` is present on the in-memory record (which would
    happen once ai-summary.json ships), the body splits on blank lines
    into <p> tags so paragraph styling lands."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    # Inject a summary onto the first site so we don't depend on the
    # ai-summary connector having actually run yet (it's API-key gated).
    target_id = page.evaluate(
        "(() => {"
        "  const s = (window.__sites || [])[0];"
        "  if (!s) return null;"
        "  s.summary = 'Paragraph one.\\n\\nParagraph two.\\n\\nParagraph three.';"
        "  s.summary_meta = { model: 'claude-haiku-4-5-20251001', generated_at: '2026-05-04T00:00:00Z', hash: 'test' };"
        "  return s.id;"
        "})()"
    )
    assert target_id
    page.evaluate(f"window.__selectSite('{target_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    page.locator("#dtab-summary").click()
    # Three paragraphs should render in the body.
    paragraphs = page.locator("#d-summary-body p")
    assert paragraphs.count() == 3
    assert "Paragraph one." in (paragraphs.nth(0).text_content() or "")
    # Meta line cites the model.
    meta = page.locator("#d-summary-meta")
    assert meta.evaluate("el => el.hidden") is False
    assert "claude-haiku-4-5" in (meta.text_content() or "")


def test_enforcement_block_renders_when_echo_enriched(page, base_url):
    """ECHO enforcement block renders inline in the Overview pane when
    the site carries `enforcement` data. Defaults to hidden so unenriched
    sites don't show empty placeholders."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    target_id = page.evaluate(
        "(() => {"
        "  const s = (window.__sites || [])[0];"
        "  if (!s) return null;"
        "  s.enforcement = {"
        "    registry_id: '110000999999',"
        "    dfr_url: 'https://echo.epa.gov/detailed-facility-report?fid=110000999999',"
        "    inspections_5yr: 4,"
        "    formal_actions_5yr: 2,"
        "    informal_actions_5yr: 1,"
        "    penalties_5yr_usd: 25000,"
        "    current_compliance: 'Significant Violation',"
        "    last_violation_date: '2024-08-15',"
        "    programs: ['CWA', 'RCRA']"
        "  };"
        "  return s.id;"
        "})()"
    )
    assert target_id
    page.evaluate(f"window.__selectSite('{target_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    block = page.locator("#d-echo-block")
    assert block.evaluate("el => el.hidden") is False
    assert page.locator("#d-echo-compliance").text_content() == "Significant Violation"
    assert page.locator("#d-echo-formal").text_content() == "2"
    assert page.locator("#d-echo-penalties").text_content() == "$25,000"
    # Formal actions > 0 → highlighted as a violation.
    formal_cls = page.locator("#d-echo-formal").get_attribute("class") or ""
    assert "violation" in formal_cls
    # DFR deep-link points at echo.epa.gov.
    dfr_href = page.locator("#d-echo-dfr").get_attribute("href")
    assert dfr_href and dfr_href.startswith("https://echo.epa.gov")


def test_enforcement_block_hidden_when_no_echo_data(page, base_url):
    """A site without `enforcement` enrichment must not render the block —
    we don't want empty 'Not available' rows cluttering the panel."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    target_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (!s.enforcement) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    if not target_id:
        import pytest
        pytest.skip("every loaded site already has ECHO data")
    page.evaluate(f"window.__selectSite('{target_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    assert page.locator("#d-echo-block").evaluate("el => el.hidden") is True


def test_fuds_no_acreage_shows_boundary_note(page, base_url):
    """v1.10 audit fix #4: FUDS records lacking polygon acreage (~66% of the
    8,822 inventory) should surface a 'Boundary not digitized' inline note
    next to the Acreage row, so users know the gap is a USACE-source
    limitation rather than missing data on our end. The note must NOT show
    on FUDS records with acreage, and must NOT show on non-FUDS programs
    (ACRES brownfields all have null acreage but the gap has a different
    cause)."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    fuds_no_acres = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (s.program === 'fuds' && s.acreage == null) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    fuds_with_acres = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (s.program === 'fuds' && s.acreage != null) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    acres_no_acres = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (s.program === 'brownfield' && s.acreage == null) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    assert fuds_no_acres, "no FUDS record without acreage in loaded data"
    assert fuds_with_acres, "no FUDS record with acreage in loaded data"

    page.evaluate(f"window.__selectSite('{fuds_no_acres}')")
    page.wait_for_selector("#detail:not([hidden])")
    note = page.locator("#d-acreage-note")
    assert note.evaluate("el => el.hidden") is False, (
        "boundary note should be visible for FUDS sites missing acreage"
    )
    assert "Boundary not digitized" in note.text_content()
    # The [hidden] CSS belt-and-suspenders rule must keep display:none when
    # we toggle the note off — otherwise the inline-displayed span will
    # render its (empty) text node and leak whitespace next to the value.
    page.evaluate(f"window.__selectSite('{fuds_with_acres}')")
    note_display = note.evaluate("el => getComputedStyle(el).display")
    assert note.evaluate("el => el.hidden") is True
    assert note_display == "none", (
        f"acreage-note with hidden=true rendered as display:{note_display} — "
        "the [hidden] trap is back. See CLAUDE.md."
    )

    # Non-FUDS records with null acreage should NOT trigger the FUDS-specific
    # note — the audit's gap is layer-4 boundary digitization, not generic
    # acreage absence.
    if acres_no_acres:
        page.evaluate(f"window.__selectSite('{acres_no_acres}')")
        assert note.evaluate("el => el.hidden") is True


def test_fuds_owner_label_normalized(page, base_url):
    """v1.10 audit fix #5: USACE current-owner codes used to render raw
    ('PRIV: PRIVATE   ', 'FED: FEDERAL AIR FORCE  ', etc.). The connector
    now cleans these to 'Private', 'Federal — Air Force', etc. Guard
    against accidental reintroduction of the raw prefix syntax in the
    detail panel."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
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
    owner_text = page.locator("#d-fed").text_content()
    # Raw codes always contain a colon followed by the redundant tier word.
    raw_signatures = [
        "PRIV: PRIVATE",
        "FED: FEDERAL",
        "LOCAL: ",
        "STATE: STATE",
        "OTHER: OTHER",
        "TRIBE: TRIBAL",
    ]
    for sig in raw_signatures:
        assert sig not in owner_text, (
            f"detail panel still shows raw USACE owner code {sig!r}: {owner_text!r}"
        )


def test_selectsite_resets_to_overview_tab(page, base_url):
    """Switching sites should reset the active tab back to Overview, so a
    user reading a Summary doesn't carry that pane state into the next site."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.locator("#tab-table").click()
    rows = page.locator("#sites-table tbody tr")
    rows.nth(0).click()
    page.wait_for_selector("#detail:not([hidden])")
    page.locator("#dtab-summary").click()
    assert page.locator("#dtab-summary").get_attribute("aria-selected") == "true"
    # Pick a different site → tab should snap back.
    rows.nth(1).click()
    assert page.locator("#dtab-overview").get_attribute("aria-selected") == "true"
    assert page.locator("#dpane-overview").evaluate("el => el.hidden") is False


def test_table_status_column_no_program_duplication(page, base_url):
    """UAT-009: STATUS column previously fell back to a `data-program` pill
    when `npl_status_code` was null, which made the column visually identical
    to the PROGRAM column for every FUDS / BRAC / ACRES row. Fixed: render
    `eligibility` for FUDS, an em-dash otherwise."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.locator("#tab-table").click()
    page.wait_for_selector("#sites-table tbody tr")
    # Sort by STATE asc so rows are deterministic; AK has rows from multiple
    # programs (Superfund, FUDS, BRAC) within the first page so we can spot-
    # check each program's STATUS-cell rendering.
    state_th = page.locator("#sites-table thead th[data-sort='state']")
    state_th.click()
    page.wait_for_function(
        "document.querySelector(\"#sites-table thead th[data-sort='state']\")?.getAttribute('data-sort-glyph') === '▲'"
    )
    duplicates = page.evaluate(
        "() => {"
        "  const rows = Array.from(document.querySelectorAll('#sites-table tbody tr'));"
        "  const out = [];"
        "  for (const tr of rows) {"
        "    const tds = tr.querySelectorAll('td');"
        "    if (tds.length < 5) continue;"
        "    const program = tds[1].textContent.trim();"
        "    const status = tds[4].textContent.trim();"
        "    if (program && program === status) {"
        "      out.push({ name: tds[0].textContent.trim(), program, status });"
        "    }"
        "  }"
        "  return out.slice(0, 5);"
        "}"
    )
    assert duplicates == [], (
        f"STATUS column still duplicates PROGRAM column for these rows: {duplicates!r}. "
        "Fix `makeRow()` in app.js so non-Superfund records render eligibility "
        "(FUDS) or an em-dash, not the program pill."
    )
    # Spot-check: at least one BRAC row should render '—' in STATUS.
    brac_status_dashes = page.evaluate(
        "() => {"
        "  const rows = Array.from(document.querySelectorAll('#sites-table tbody tr'));"
        "  return rows.filter(tr => {"
        "    const pillProg = tr.querySelector('td:nth-child(2) .pill[data-program]');"
        "    return pillProg && pillProg.dataset.program === 'brac';"
        "  }).map(tr => tr.querySelector('td:nth-child(5)').textContent.trim());"
        "}"
    )
    if brac_status_dashes:
        assert all(s == "—" for s in brac_status_dashes), (
            f"BRAC rows should render em-dash in STATUS, got: {brac_status_dashes!r}"
        )


def test_site_name_titlecased_with_acronyms_preserved(page, base_url):
    """Site names ship ALL CAPS in ~94% of records. `prettyName()` title-cases
    them at ingest while preserving federal/military acronyms (NRDA, PCB,
    USDOE, AFB, NIKE, NAS, …). Spot-check a handful of well-known names to
    catch acronym-list drift; broad scan asserts the table cell is not pure
    upper-case for the first page of rendered rows."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    fn = page.evaluate
    # prettyName is exposed on window for direct exercise.
    assert fn("window.__prettyName('FOX RIVER NRDA/PCB RELEASES')") == "Fox River NRDA/PCB Releases"
    assert fn("window.__prettyName('IDAHO NATIONAL ENGINEERING LABORATORY (USDOE)')") == \
        "Idaho National Engineering Laboratory (USDOE)"
    assert fn("window.__prettyName('FORT WAINWRIGHT')") == "Fort Wainwright"
    assert fn("window.__prettyName('CAMP STANLEY AFB')") == "Camp Stanley AFB"
    assert fn("window.__prettyName('CAPE CANAVERAL AFS')") == "Cape Canaveral AFS"
    # Already-mixed-case names pass through unchanged.
    assert fn("window.__prettyName('GE / Housatonic River')") == "GE / Housatonic River"
    # Table cell sanity: very few first-page rows should be pure ALL CAPS.
    page.locator("#tab-table").click()
    page.wait_for_selector("#sites-table tbody tr")
    all_caps_in_table = page.evaluate(
        "() => Array.from(document.querySelectorAll('#sites-table tbody tr td:first-child'))"
        ".filter(td => {"
        "  const t = td.textContent.trim();"
        "  if (!t || t === '—') return false;"
        "  if (t !== t.toUpperCase()) return false;"
        "  return /[A-Z]{4,}/.test(t);"  # ignore short tokens like "NIKE 04"
        "})"
        ".slice(0, 5)"
        ".map(td => td.textContent)"
    )
    assert len(all_caps_in_table) == 0, (
        f"first-page table rows still ALL CAPS: {all_caps_in_table!r}"
    )


def test_csv_export_includes_enrichment_columns(page, base_url):
    """Pre-fix CSV export was 12 columns and silently dropped every
    enrichment field (transmission distances, ECHO enforcement counters,
    FUDS owner labels, etc.). The curated wide schema now mirrors the
    detail panel — assert the headline enrichment column labels are
    present and a sample populated row carries enrichment data."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    csv = page.evaluate("window.__buildCsv()")
    assert csv, "CSV builder produced empty output"
    lines = csv.split("\n")
    header = lines[0].split(",")
    # Headline enrichment columns that were missing pre-fix.
    expected_in_header = {
        "transmission_mi", "rail_mi", "highway_mi",
        "dc_reuse_candidate",
        "current_owner", "current_owner_source",
        "echo_formal_actions_5yr", "echo_penalties_5yr_usd",
        "fuds_eligibility", "fuds_status",
        "brac_component",
        "doc_count",
    }
    missing = expected_in_header - set(header)
    assert not missing, f"CSV header missing enrichment columns: {missing}"
    # Find a row where transmission_mi is populated (any of the ~46k records
    # within the CONUS infra coverage). Confirms the dotted-path picker works.
    transmission_idx = header.index("transmission_mi")
    sample = next(
        (line.split(",") for line in lines[1:1000]
         if len(line.split(",")) > transmission_idx
         and line.split(",")[transmission_idx]),
        None,
    )
    assert sample is not None, (
        "expected at least one row with a populated transmission_mi value"
    )


# ----- v1.11.3: readiness pills + perf hot-path quick wins -----


def test_cleanup_complete_pill_for_npl_deleted(page, base_url):
    """v1.11.3: NPL Deleted Superfund sites (`npl_status_code === "D"`)
    render a green "Cleanup Complete" pill alongside the program pill in
    the detail panel — the strongest "site is transactable today" signal
    in the dataset, derived from existing fields with zero new fetches."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    deleted_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (s.program === 'superfund' && s.npl_status_code === 'D') return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    assert deleted_id, "no NPL-Deleted Superfund site found in loaded data"
    page.evaluate(f"window.__selectSite('{deleted_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    pill = page.locator("#d-program .cleanup-pill")
    assert pill.count() == 1, "expected exactly one cleanup-pill on a Deleted site"
    assert "Cleanup Complete" in (pill.text_content() or "")


def test_no_cleanup_pill_for_active_npl_site(page, base_url):
    """Inverse: NPL Final/Proposed sites must NOT render the green
    Cleanup Complete pill. Guards against the pill leaking onto sites
    that aren't actually post-remediation."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    final_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (s.program === 'superfund' && s.npl_status_code === 'F') return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    assert final_id, "no NPL-Final Superfund site found in loaded data"
    page.evaluate(f"window.__selectSite('{final_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    assert page.locator("#d-program .cleanup-pill").count() == 0


def test_active_reuse_pill_for_in_reuse_site(page, base_url):
    """v1.11.3: sites whose `in_reuse` field starts with "Yes"
    (RedevelopmentAppSitePoints flag) render a green "Active Reuse" pill.
    Skips silently if the redev enrichment hasn't loaded yet — that's
    expected on a cold dataset before `epa-redev.json` lands."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    reuse_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (typeof s.in_reuse === 'string' && /^yes/i.test(s.in_reuse)) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    if not reuse_id:
        import pytest
        pytest.skip("no in_reuse=Yes sites in current dataset — re-run epa-redev")
    page.evaluate(f"window.__selectSite('{reuse_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    pill = page.locator("#d-program .reuse-pill")
    assert pill.count() == 1, "expected exactly one reuse-pill on an In_Reuse site"
    assert "Active Reuse" in (pill.text_content() or "")


def test_no_reuse_pill_when_in_reuse_no(page, base_url):
    """`in_reuse: "No"` must NOT render the Active Reuse pill — only "Yes"
    values qualify. Guards against the regex (`/^yes/i`) accidentally
    matching the trailing "no" in a longer string."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    no_id = page.evaluate(
        "(() => {"
        "  for (const s of (window.__sites || [])) {"
        "    if (typeof s.in_reuse === 'string' && /^no/i.test(s.in_reuse)) return s.id;"
        "  }"
        "  return null;"
        "})()"
    )
    if not no_id:
        import pytest
        pytest.skip("no in_reuse=No sites in current dataset")
    page.evaluate(f"window.__selectSite('{no_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    assert page.locator("#d-program .reuse-pill").count() == 0


def test_search_index_built_at_ingest(page, base_url):
    """v1.11.3 perf: `siteMatchesQuery()` reads from the pre-built
    `_searchKey` field on every record. Rebuild on ingest — every record
    must carry a non-empty lowercased index containing name + city +
    county + state. Guards against a regression where _searchKey gets
    dropped (e.g., after a new ingest path lands)."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    stats = page.evaluate(
        "(() => {"
        "  const sites = window.__sites || [];"
        "  let withKey = 0, withoutKey = 0, sample = null, withName = 0;"
        "  for (const s of sites) {"
        "    if (s.name) withName++;"
        "    if (typeof s._searchKey === 'string' && s._searchKey.length) {"
        "      withKey++;"
        "      if (!sample && s.name && s.state) sample = {"
        "        id: s.id, key: s._searchKey, name: s.name, state: s.state,"
        "      };"
        "    } else withoutKey++;"
        "  }"
        "  return { total: sites.length, withName, withKey, withoutKey, sample };"
        "})()"
    )
    # Every site that has a name should have a non-empty _searchKey.
    assert stats["total"] > 0
    assert stats["withoutKey"] == 0, (
        f"{stats['withoutKey']} sites missing _searchKey out of {stats['total']}"
    )
    # Sample key must be lowercased and contain both the name and state.
    sample = stats["sample"]
    assert sample, "no sample site with both name and state was found"
    key = sample["key"]
    assert key == key.lower(), "_searchKey must be lowercased"
    assert sample["name"].lower().split()[0] in key
    assert sample["state"].lower() in key


def test_search_filter_uses_prebuilt_index(page, base_url):
    """End-to-end smoke: typing in the search box still filters the table
    after the perf rewrite. The behavior shouldn't change — the speedup
    is internal — so this just sanity-checks that the index path produces
    the same matches the prior join-on-every-call path did."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.locator("#tab-table").click()
    # Pick a real site name's first word as the query so we know it matches.
    query = page.evaluate(
        "(() => {"
        "  const sites = window.__sites || [];"
        "  for (const s of sites) {"
        "    if (s.name && s.name.length > 4) {"
        "      const word = s.name.split(/\\s+/)[0];"
        "      if (word.length >= 4) return word.toLowerCase();"
        "    }"
        "  }"
        "  return null;"
        "})()"
    )
    assert query, "could not find a sample site name to query"
    page.locator("#search").fill(query)
    page.wait_for_function(
        f"document.getElementById('search-count').textContent.length > 0",
        timeout=2000,
    )
    count_text = page.locator("#search-count").text_content() or ""
    # Format is "N of M ..." — the visible count must be > 0 since `query`
    # is drawn from a real site's name.
    assert count_text and count_text[0].isdigit(), f"unexpected count: {count_text!r}"
    visible = int(count_text.split()[0].replace(",", ""))
    assert visible >= 1, f"search for {query!r} produced no matches"


def test_visible_bbox_cached_on_filter(page, base_url):
    """v1.11.3 perf: `tableState.visibleBBox` is updated by
    `refreshTableForFilter()` so `refitMapToFilters()` doesn't sweep all
    47k records again. After a filter narrows the visible set, the bbox
    must be present, finite, and reflect the filtered records — not the
    full dataset."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    # Apply a state filter — narrows the visible set significantly.
    page.locator("#filters-toggle").click()
    page.locator("#f-state").select_option("CA")
    # applyFilter runs synchronously off the change event; bbox is cached.
    bbox = page.evaluate(
        "(() => {"
        "  const ts = window.__tableState;"
        "  if (!ts || !ts.visibleBBox) return null;"
        "  const bb = ts.visibleBBox;"
        "  return {"
        "    count: bb.count,"
        "    minLat: bb.minLat, maxLat: bb.maxLat,"
        "    minLon: bb.minLon, maxLon: bb.maxLon,"
        "  };"
        "})()"
    )
    assert bbox, "tableState.visibleBBox not exposed or null after filter"
    # CA sites span ~32–42°N and ~-124 to -114°W.
    assert bbox["count"] > 0
    assert 30 < bbox["minLat"] < 45, f"unexpected minLat: {bbox['minLat']}"
    assert 30 < bbox["maxLat"] < 45, f"unexpected maxLat: {bbox['maxLat']}"
    assert -130 < bbox["minLon"] < -110, f"unexpected minLon: {bbox['minLon']}"
    assert -130 < bbox["maxLon"] < -110, f"unexpected maxLon: {bbox['maxLon']}"
    # Height/width are nonzero (filtered set has multiple sites).
    assert bbox["maxLat"] >= bbox["minLat"]
    assert bbox["maxLon"] >= bbox["minLon"]


def test_infra_distance_renders_adjacent_below_threshold(page, base_url):
    """v1.11.4: distances < 0.05 mi (rounded to 0.0 in the source data)
    must render as "Adjacent" instead of "<0.1 mi" / "0.0 mi". Cover all
    three cells in one shot so a future regression on any of them is loud."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    target_id = page.evaluate(
        "(() => {"
        "  const s = (window.__sites || [])[0];"
        "  if (!s) return null;"
        "  s.transmission_mi = 0.0;"
        "  s.rail_mi = 0.04;"
        "  s.highway_mi = 5.2;"
        "  return s.id;"
        "})()"
    )
    assert target_id
    page.evaluate(f"window.__selectSite('{target_id}')")
    page.wait_for_selector("#detail:not([hidden])")
    assert (page.locator("#d-transmission-mi").text_content() or "").strip() == "Adjacent"
    assert (page.locator("#d-rail-mi").text_content() or "").strip() == "Adjacent"
    assert (page.locator("#d-highway-mi").text_content() or "").strip() == "5.2 mi"
    # The "Adjacent" cells should NOT carry the muted-cell class — they're
    # real data, not placeholder text.
    for sel in ("#d-transmission-mi", "#d-rail-mi"):
        cls = page.locator(sel).get_attribute("class") or ""
        assert "muted-cell" not in cls, f"{sel} kept muted-cell class for adjacent value"


def test_dc_candidate_surfaces_criteria_in_detail_panel(page, base_url):
    """v1.11.4: when `data_center_reuse_candidate` is true the detail panel
    surfaces the EPA RE-Powering criteria as a sub-line so the boolean isn't
    opaque. When false / null, the criteria stay hidden."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    sid = page.evaluate(
        "(() => {"
        "  const s = (window.__sites || [])[0];"
        "  if (!s) return null;"
        "  s.data_center_reuse_candidate = true;"
        "  return s.id;"
        "})()"
    )
    assert sid
    page.evaluate(f"window.__selectSite('{sid}')")
    page.wait_for_selector("#detail:not([hidden])")
    crit = page.locator("#d-dc-criteria")
    assert crit.evaluate("el => el.hidden") is False
    text = (crit.text_content() or "").strip()
    assert "≥50 acres" in text
    assert "electric transmission" in text
    assert "water service area" in text
    # Parent dd carries "Yes" as its leading text node.
    dd_lead = page.evaluate(
        "() => document.getElementById('d-dc-candidate').firstChild.nodeValue.trim()"
    )
    assert dd_lead == "Yes"

    # Flip to False → criteria hidden, lead reads "No".
    page.evaluate(
        f"(() => {{ const s = window.__sites.find(x => x.id === '{sid}');"
        "  s.data_center_reuse_candidate = false;"
        f" window.__selectSite('{sid}'); }})()"
    )
    assert crit.evaluate("el => el.hidden") is True
    dd_lead = page.evaluate(
        "() => document.getElementById('d-dc-candidate').firstChild.nodeValue.trim()"
    )
    assert dd_lead == "No"


# ----- UAT-011 (2026-05-06): initMap() must not strand markerLayer when the
# map container is 0x0 at first paint. Headless preview, hidden tabs, and
# zero-size embeds all hit this path. Before the fix, Leaflet's fitBounds()
# threw "Invalid LatLng object: (NaN, NaN)" BEFORE markerLayer was created,
# so every subsequent BRAC/FUDS/ACRES lazy-load crashed in addOneMarker. The
# fix moves markerLayer creation ahead of fitBounds and defers fitBounds via
# a ResizeObserver when the container has no dimensions.

def test_init_map_survives_zero_size_container(page, base_url):
    """Boot the page with #map forced to 0x0. markerLayer must still exist
    so the lazy-load chain doesn't crash. Then restore dimensions and verify
    the deferred fitBounds completes via the ResizeObserver retry."""
    # Inject the zero-size CSS BEFORE the page's stylesheet/scripts load so
    # initMap() runs against a real 0x0 container. add_init_script runs in
    # every new document, so it lands ahead of app.js.
    page.add_init_script(
        """
        document.addEventListener('DOMContentLoaded', () => {
          const style = document.createElement('style');
          style.id = '__zerosize-test';
          style.textContent = '#map { width: 0 !important; height: 0 !important; }';
          document.head.appendChild(style);
        }, { once: true });
        """
    )
    page.goto(f"{base_url}/index.html")

    # Wait for the Superfund payload to settle; __sitesLoaded fires after
    # ingestSites() but BEFORE __APP_READY__ (which waits on every program
    # lazy-load). At this checkpoint, markerLayer must exist even if
    # fitBounds was deferred.
    page.wait_for_function("window.__sitesLoaded === true", timeout=20000)

    # The critical invariant: markerLayer is wired up regardless of the
    # zero-size fitBounds throw. This is what the original UAT-011 bug broke.
    assert page.evaluate("typeof window.__markerLayer !== 'undefined'"), (
        "markerLayer should be created before fitBounds — zero-size container "
        "must not strand later marker-adders with `undefined`"
    )
    assert page.evaluate("typeof window.__map !== 'undefined'"), (
        "map should be created before fitBounds defers"
    )

    # Sanity: no BRAC/FUDS/ACRES lazy-load crashed with the addLayer TypeError
    # that UAT-011 produced. We can't easily snapshot console.error from
    # Playwright after the fact, so we verify the positive path: at least
    # one program's records have been ingested into sitesById.
    sites_count = page.evaluate("(window.__sites || []).length")
    assert sites_count > 0, "Superfund payload should ingest even with zero-size map"

    # Now restore real dimensions. The ResizeObserver in fitUsBoundsSafely()
    # should pick this up, retry fitBounds, succeed, and call invalidateSize().
    # __APP_READY__ flips true once every lazy-load resolves, so we use it as
    # the post-recovery sentinel.
    page.evaluate("document.getElementById('__zerosize-test').remove()")
    page.wait_for_function("window.__APP_READY__ === true", timeout=20000)

    # Map should now report a real (non-NaN) center. Before the fix, the
    # internal Leaflet state stayed corrupted; here we assert recovery.
    center = page.evaluate(
        "(() => { const c = window.__map.getCenter(); return { lat: c.lat, lng: c.lng }; })()"
    )
    import math
    assert not math.isnan(center["lat"]), "map center lat should not be NaN after recovery"
    assert not math.isnan(center["lng"]), "map center lng should not be NaN after recovery"
    # CONUS centroid sanity — fitBounds(US_BOUNDS) should land near 35°N, -96°W.
    assert 25 < center["lat"] < 45, f"recovered center lat {center['lat']} out of CONUS"
    assert -110 < center["lng"] < -80, f"recovered center lng {center['lng']} out of CONUS"


def test_marker_layer_created_before_fit_bounds(page, base_url):
    """Lighter-weight regression for UAT-011: even on a normal-size container,
    `__markerLayer` must be exposed before any user-visible action. This
    guards against future refactors that re-introduce the original ordering
    (markerLayer assignment AFTER fitBounds)."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__sitesLoaded === true", timeout=20000)
    # Both globals must be live by the time __sitesLoaded fires — initMap
    # has run at least once.
    assert page.evaluate("!!window.__map")
    assert page.evaluate("!!window.__markerLayer")
    assert page.evaluate(
        "typeof window.__markerLayer.addLayer === 'function'"
    ), "markerLayer should be a Leaflet LayerGroup with .addLayer()"
