"""The verify map re-measures grid and corridor distances from live source layers and
sets them beside the atlas's own numbers. The sources are stubbed here, so these tests
prove the comparison logic, not the availability of HIFLD, TIGERweb or Overpass."""
from __future__ import annotations

import json
import math
import re

from playwright.sync_api import Page, expect

SITE = "arnold-afb-tn"            # atlas claims transmission_mi = 0.8
LAT, LON = 35.371111, -86.215556


def _stub_sources(page: Page, transmission_offset_mi: float) -> None:
    dlat = transmission_offset_mi / (110540 / 1609.344)
    line = {"features": [{"attributes": {"VOLTAGE": 161, "VOLT_CLASS": "100-161", "OWNER": "TVA", "STATUS": "IN SERVICE"},
                          "geometry": {"paths": [[[LON - 0.05, LAT + dlat], [LON + 0.05, LAT + dlat]]]}}]}

    def handle(route):
        url = route.request.url
        if "Electric_Power_Transmission_Lines" in url:
            body = line
        elif "overpass" in url:
            body = {"elements": []}
        else:
            body = {"features": []}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(re.compile(r"(arcgis|tigerweb|overpass)"), handle)
    page.route(re.compile(r"tile\.openstreetmap\.org"), lambda r: r.fulfill(status=200, content_type="image/png", body=b""))


def _rows(page: Page) -> dict[str, str]:
    return page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#results tbody tr')]
        .map(r => [r.children[0].textContent, r.children[3].textContent + '|' + r.children[2].textContent]))""")


def test_matching_distance_is_reported_as_matching(page: Page, base_url: str):
    _stub_sources(page, 0.8)
    page.goto(f"{base_url}/verify.html?site={SITE}")
    page.wait_for_function("window.__verifyDone === true", timeout=30_000)
    rows = _rows(page)
    assert rows["Transmission lines"].startswith("matches")
    assert rows["Lines ≥ 115 kV"].startswith("matches")


def test_a_wrong_stored_distance_is_flagged(page: Page, base_url: str):
    _stub_sources(page, 3.0)       # the source has the line 3.0 mi away; the atlas says 0.8
    page.goto(f"{base_url}/verify.html?site={SITE}")
    page.wait_for_function("window.__verifyDone === true", timeout=30_000)
    assert rows_text(page, "Transmission lines").startswith("differs by")
    assert "bad" in page.locator("#results tbody tr").first.locator("td").nth(3).get_attribute("class")


def rows_text(page: Page, layer: str) -> str:
    return _rows(page)[layer]


def test_source_failure_is_visible_not_silent(page: Page, base_url: str):
    page.route(re.compile(r"(arcgis|tigerweb|overpass)"), lambda r: r.fulfill(status=500, body="boom"))
    page.route(re.compile(r"tile\.openstreetmap\.org"), lambda r: r.fulfill(status=200, content_type="image/png", body=b""))
    page.goto(f"{base_url}/verify.html?site={SITE}")
    page.wait_for_function("window.__verifyDone === true", timeout=30_000)
    assert rows_text(page, "Transmission lines").startswith("source error")
    expect(page.locator("#status")).to_contain_text("Checked 0 of")


def test_unknown_site_says_so(page: Page, base_url: str):
    page.goto(f"{base_url}/verify.html?site=NOPE-123")
    expect(page.locator("#status")).to_contain_text("No site with id")


def test_fiber_panel_is_honest_about_missing_geometry(page: Page, base_url: str):
    _stub_sources(page, 0.8)
    page.goto(f"{base_url}/verify.html?site={SITE}")
    expect(page.locator("#fiber-note")).to_contain_text("No public source publishes fiber routes")
    assert page.locator("#fiber-links a[href^='https://broadbandmap.fcc.gov']").count() == 1


def test_geometry_helper_distance_is_exact_for_a_known_offset(page: Page, base_url: str):
    page.goto(f"{base_url}/verify.html?lat=40&lon=-100&name=probe")
    d = page.evaluate("""() => VerifyGeo.nearestOnPaths(40, -100, [[[-101, 40.0145], [-99, 40.0145]]]).mi""")
    assert math.isclose(d, 0.0145 * 110540 / 1609.344, rel_tol=1e-6)


def test_name_parameter_is_never_interpreted_as_html(page: Page, base_url: str):
    """?name= is user input and Leaflet sets string tooltips with innerHTML."""
    _stub_sources(page, 0.8)
    page.goto(f"{base_url}/verify.html?lat=35.37&lon=-86.21&name=%3Cimg%20src%3Dx%20onerror%3D%22window.__pwned%3D1%22%3E")
    page.wait_for_function("window.__verifyDone === true", timeout=30_000)
    opened = page.evaluate("""() => { let n = 0;
        window.__verifyMap.eachLayer(l => { if (l.getTooltip && l.getTooltip() && !l.getTooltip().getContent?.().includes?.('mi')) { l.openTooltip(); n++; } });
        return n; }""")
    assert opened >= 1, "the site marker's tooltip was never opened, so this test would pass vacuously"
    page.wait_for_timeout(300)
    assert page.evaluate("window.__pwned") is None
    assert page.locator("#who").inner_text().startswith("<img")


def test_overlay_rows_do_not_claim_a_comparison_the_atlas_cannot_make(page: Page, base_url: str):
    """A coal plant stores line distances only; a power plant 'source has one' flag there would be a false alarm."""
    _stub_sources(page, 0.1)
    page.goto(f"{base_url}/verify.html?site=EIA-1733")
    page.wait_for_function("window.__verifyDone === true", timeout=30_000)
    assert rows_text(page, "Power plants").startswith("no atlas figure to compare")
    assert rows_text(page, "Gas pipelines").startswith("no atlas figure to compare")


def test_gas_and_valve_substations_are_not_measured_like_the_atlas_does_not(page: Page, base_url: str):
    """The connector drops OSM substation roles gas/valve/compression/heat-exchanger/internet; so must the check."""
    def handle(route):
        url = route.request.url
        if "overpass" in url:
            near_gas = {"type": "node", "id": 1, "lat": LAT + 0.002, "lon": LON, "tags": {"power": "substation", "substation": "gas"}}
            far_elec = {"type": "node", "id": 2, "lat": LAT + 0.0116, "lon": LON, "tags": {"power": "substation", "substation": "transmission"}}
            body = {"elements": [near_gas, far_elec]}
        else:
            body = {"features": []}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    page.route(re.compile(r"(arcgis|tigerweb|overpass)"), handle)
    page.route(re.compile(r"tile\.openstreetmap\.org"), lambda r: r.fulfill(status=200, content_type="image/png", body=b""))
    page.goto(f"{base_url}/verify.html?site={SITE}")
    page.wait_for_function("window.__verifyDone === true", timeout=30_000)
    assert rows_text(page, "Substations (OpenStreetMap)").split("|")[1].startswith("0.8 mi")   # the electric one, not the 0.1 mi gas station


def test_a_partial_overpass_answer_is_an_error_not_a_measurement(page: Page, base_url: str):
    def handle(route):
        body = {"elements": [], "remark": "runtime error: Query timed out"} if "overpass" in route.request.url else {"features": []}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    page.route(re.compile(r"(arcgis|tigerweb|overpass)"), handle)
    page.route(re.compile(r"tile\.openstreetmap\.org"), lambda r: r.fulfill(status=200, content_type="image/png", body=b""))
    page.goto(f"{base_url}/verify.html?site={SITE}")
    page.wait_for_function("window.__verifyDone === true", timeout=30_000)
    assert rows_text(page, "Substations (OpenStreetMap)").startswith("source error")
