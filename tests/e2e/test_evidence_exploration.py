"""User-visible evidence categories, responsive access and demand-driven loading."""
from __future__ import annotations

import csv
import io
import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def _open(page, base_url, suffix=""):
    page.goto(f"{base_url}/index.html{suffix}")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45000)


@pytest.mark.parametrize("width,height", [(375, 812), (768, 1024), (1280, 900), (1440, 900)])
def test_default_explore_exposes_categories_without_page_overflow(page, base_url, width, height):
    page.set_viewport_size({"width": width, "height": height})
    _open(page, base_url)
    expect(page.locator("#view-candidates")).to_be_visible()
    row = page.locator("#candidates-table tbody tr").first
    expect(row).to_be_visible()
    for category in ["grid", "fiber", "water", "land", "logistics"]:
        cell = row.locator(f'td[data-category="{category}"]')
        expect(cell).to_be_visible()
        expect(cell.locator(".evidence-finding")).not_to_have_text("")
        expect(cell.locator(".evidence-confidence")).to_have_text(
            re.compile(r"^(High|Medium|Low) confidence$|^Not assessed$")
        )
        # Scrolling inside an intentionally wide desktop table is allowed;
        # phone readers must receive each first-row category without panning.
        if width < 640:
            box = cell.bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    headers = page.locator("#candidates-table thead").inner_text()
    assert not re.search(r"\b(score|rank)\b|#", headers, re.I)


def test_unknown_fiber_is_visible_and_does_not_remove_all_sites(page, base_url):
    _open(page, base_url)
    page.locator("#evidence-category-filter").select_option("fiber")
    page.locator("#evidence-status-filter").select_option("unknown")
    rows = page.locator("#candidates-table tbody tr")
    expect(rows.first).to_be_visible()
    for cell in rows.locator('[data-category="fiber"] .evidence-finding').all():
        expect(cell).to_have_text("Unknown")
    page.locator("#evidence-confidence-filter").select_option("High")
    expect(rows).to_have_count(0)
    page.locator("#evidence-confidence-filter").select_option("")
    expect(rows.first).to_be_visible()


def test_site_details_separate_proximity_from_capacity_and_water_rights(page, base_url):
    _open(page, base_url)
    page.locator("#candidates-table .site-evidence-open").first.click()
    expect(page.locator("#detail")).to_be_visible()
    for category in ["grid_capacity", "water_rights", "water_reliability", "fiber"]:
        detail = page.locator(f'#detail .evidence-category[data-category="{category}"]')
        expect(detail.locator(".evidence-finding")).to_have_text("Unknown")
        detail.locator("summary").click()
        expect(detail.locator("p")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#detail")).to_be_hidden()


def test_empty_global_search_stays_empty_in_microreactors(page, base_url):
    _open(page, base_url)
    page.locator("#search").fill("zzzz-no-site-can-match-20260912")
    expect(page.locator("#candidates-table tbody tr")).to_have_count(0)
    page.locator("#tab-micro").click()
    page.wait_for_function("window.__microRankedCount && window.__microRankedCount() === 0", timeout=15000)
    expect(page.locator(".micro-rank-table tbody tr")).to_have_count(0)
    expect(page.locator("#view-micro")).to_contain_text("No sites match")


def test_csv_exports_findings_and_confidence_without_numeric_suitability(page, base_url):
    _open(page, base_url, "?program=superfund&q=Tar%20Creek")
    payload = page.evaluate("window.__buildCsv()")
    rows = list(csv.DictReader(io.StringIO(payload)))
    assert rows
    keys = rows[0].keys()
    for category in ["grid", "fiber", "water", "land", "logistics"]:
        assert f"{category}_finding" in keys
        assert f"{category}_confidence" in keys
    assert not ({"dc_score", "dc_composite_score", "generation_score", "manufacturing_score", "microreactor_score", "rank"} & set(keys))
    assert all(row["fiber_finding"] == "Unknown" for row in rows)


def test_initial_explore_defers_documents_summaries_and_map_catalogs(page, base_url):
    requested = []
    page.on("request", lambda request: requested.append(request.url))
    _open(page, base_url)
    paths = {url.split("?")[0].rsplit("/", 1)[-1] for url in requested}
    for name in ["infra-proximity.json", "water-proximity.json", "epa-acres.json"]:
        assert name in paths, name
    for name in ["epa-superfund-docs.json", "ai-summary.json", "reference-campuses.json", "hanford-e2e.json", "nickel-anchor-proximity.json", "fema-nri.json", "climate-zone.json", "planned-retirements-proximity.json"]:
        assert name not in paths, f"Unrequested surface loaded {name}"
    with page.expect_request("**/reference-campuses.json"):
        page.locator("#tab-map").click()
    expect(page.locator("#view-map")).to_be_visible()


def test_mobile_map_legend_disclosure_is_keyboard_usable(page, base_url):
    page.set_viewport_size({"width": 375, "height": 812})
    _open(page, base_url, "#map")
    disclosure = page.locator(".legend-disclosure")
    expect(disclosure).to_be_visible()
    assert disclosure.get_attribute("open") is None
    summary = disclosure.locator("summary")
    summary.focus()
    page.keyboard.press("Enter")
    expect(disclosure).to_have_attribute("open", "")
    page.keyboard.press("Enter")
    assert disclosure.get_attribute("open") is None


def test_data_methods_coverage_uses_loaded_population_and_discloses_source_limits(page,base_url):
    page.set_viewport_size({"width":375,"height":812})
    _open(page,base_url,"?program=superfund")
    page.locator("#tab-about").click()
    coverage=page.locator("#about-source-coverage")
    expect(coverage).to_contain_text("Core loading complete")
    population=page.evaluate("window.__sites.length")
    rows=coverage.locator("tbody tr")
    expect(rows).to_have_count(7)
    for row in rows.all():
        assert row.locator("td").first.inner_text().endswith(f" / {population:,}")
    fiber=rows.filter(has_text="Fiber")
    expect(fiber.locator("td").first).to_have_text(f"0 / {population:,}")
    expect(fiber).to_contain_text("no joined enterprise")
    expect(rows.filter(has_text="Water network / gages")).to_contain_text("supply unknown")
    assert coverage.locator('a[href^="https://"]').count() >= 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_approach_c_pilot_surfaces_scoped_water_and_fiber_evidence(page, base_url):
    _open(page, base_url, "?q=107%20Brattleboro%20Road")
    row = page.locator("#candidates-table tbody tr", has_text="107 Brattleboro Road")
    expect(row).to_have_count(1)
    expect(row.locator('[data-category="water"]')).to_contain_text("Network-linked reach")
    expect(row.locator('[data-category="fiber"]')).to_contain_text("regional footprint")
    row.click()
    page.wait_for_function("() => !document.querySelector('#detail').hidden", timeout=10000)
    evidence = page.locator("#d-suitability")
    expect(evidence).to_contain_text("Lower Green River")
    expect(evidence).to_contain_text("does not establish service at the parcel")
    expect(evidence).to_contain_text("Intake location")


@pytest.mark.parametrize("suffix", ["", "#map"])
def test_mobile_national_map_fits_west_east_and_insets_on_first_activation(page,base_url,suffix):
    page.set_viewport_size({"width":375,"height":812})
    _open(page,base_url,suffix)
    if not suffix:
        page.locator("#tab-map").click()
    page.wait_for_function("window.__MAP_READY__ === true",timeout=45000)
    # The overview must contain the entire atlas extent, including inset boxes.
    # A fixed minimum zoom of4 silently cropped the western states on phones.
    page.wait_for_function("""() => {
        const bounds=window.__leafletMap.getBounds();
        return bounds.contains(US_BOUNDS.getSouthWest()) && bounds.contains(US_BOUNDS.getNorthEast());
    }""",timeout=10000)
