"""Browser contracts for category evidence; legacy numeric suitability is retired."""
from __future__ import annotations
import csv
import io
import pytest
from playwright.sync_api import Page, expect
pytestmark = pytest.mark.e2e

def _ready(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.SiteEvidence && window.__APP_READY__ === true", timeout=45000)

def _assess(page, record, lens="dc"):
    return page.evaluate("([s,l]) => SiteEvidence.assessSite(s,l)", [record,lens])

def _open_tab(page: Page, base_url: str) -> None:
    """The microreactor catalog is a collapsed section of the Nuclear tab."""
    _ready(page, base_url)
    page.click("#tab-ap1000")
    page.click("#micro-catalog > summary")
    page.wait_for_selector("#micro-content table.micro-table tbody tr", timeout=30_000)

def test_catalog_renders_fleet_and_commitments(page: Page, base_url: str):
    _open_tab(page, base_url)
    page.wait_for_selector(".janus-table tbody tr", timeout=15_000)
    tables = page.locator("#micro-content table.micro-table")
    assert tables.count() == 3
    assert tables.nth(0).locator("tbody tr").count() >= 11        # the fleet
    assert tables.nth(1).locator("tbody tr").count() >= 30        # commitments + track headers
    # Every fleet and commitment row must expose at least one source link.
    assert page.locator("#micro-content .micro-src a").count() >= 40

def test_janus_screen_has_nine_traceable_installations(page: Page, base_url: str):
    _open_tab(page, base_url)
    page.wait_for_selector(".janus-table tbody tr", timeout=15_000)
    assert page.locator(".janus-table tbody tr").count() == 9
    page.locator("button.janus-site-button").first.click()
    page.wait_for_selector("#janus-detail")
    assert page.locator(".janus-source-card").count() == 6
    assert page.locator(".janus-source-card a").count() >= 6
    detail = page.locator("#janus-detail").inner_text()
    assert "Screening, not siting" in detail
    assert "unavailable is different from a result of zero" in detail

def test_janus_deep_link_and_lazy_map_package(page: Page, base_url: str):
    _ready(page, base_url)
    page.goto(f"{base_url}/index.html?janus=fort-benning-ga#micro")
    page.wait_for_selector("#janus-detail", timeout=20_000)
    assert "Fort Benning" in page.locator("#janus-detail").inner_text()
    page.click("button.janus-map-button")
    page.wait_for_selector("#view-map:not([hidden])", timeout=20_000)
    page.wait_for_function("() => window.__janusMapFeatureCount() > 0", timeout=20_000)
    assert page.evaluate("() => window.__janusMapFeatureCount()") > 1_000

def test_old_micro_hash_opens_the_nuclear_catalog(page: Page, base_url: str):
    _ready(page, base_url)
    page.goto(f"{base_url}/index.html#micro")
    page.wait_for_selector("#view-ap1000:not([hidden])", timeout=15_000)
    assert page.locator("#tab-ap1000").get_attribute("aria-selected") == "true"
    assert page.evaluate("document.getElementById('micro-catalog').open") is True

def test_commitment_markers_and_legend_row(page: Page, base_url: str):
    _open_tab(page, base_url)
    page.click("#tab-map")
    page.wait_for_function("window.__MAP_READY__ === true", timeout=45000)
    page.wait_for_selector(".micro-commit-icon", timeout=15_000)
    count = page.locator(".micro-commit-icon").count()
    assert count >= 20, count
    legend = page.locator(".legend").inner_text()
    assert "Microreactor commitment" in legend
    assert str(count) in legend

def test_alaska_commitments_are_remapped_into_the_inset(page: Page, base_url: str):
    """Eielson AFB and the Fort Wainwright Janus installation are two of the
    highest-value rows in the set, and their real coordinates sit outside
    US_BOUNDS — a raw marker would be unreachable behind maxBoundsViscosity."""
    _open_tab(page, base_url)
    page.click("#tab-map")
    page.wait_for_function("window.__MAP_READY__ === true", timeout=45000)
    page.wait_for_function("() => window.__leafletMap.getBounds().contains(US_BOUNDS)", timeout=10000)
    page.wait_for_selector(".micro-commit-icon", timeout=15_000)
    ak = page.evaluate("""() => (window.__microFleet().commitments || [])
        .filter(c => c.state === "AK" && c.lat_real != null)
        .map(c => ({ id: c.id, inset: c._inset, lat: c.lat, latReal: c.lat_real }))""")
    assert len(ak) == 2, ak
    for row in ak:
        assert row["inset"] == "AK", row
        assert row["latReal"] > 60, row          # the real Alaskan latitude survives
        assert 18 < row["lat"] < 30, row         # remapped into the inset box
    # Leaflet transforms are relative to its moving pane, not the map element.
    # Compare actual screen-space centers after hydration instead.
    offscreen = page.evaluate("""() => {
      const map = document.getElementById("map").getBoundingClientRect();
      return [...document.querySelectorAll(".micro-commit-icon")].filter(el => {
        const r = el.getBoundingClientRect(), y = (r.top + r.bottom) / 2;
        return y < map.top || y > map.bottom;
      }).length;
    }""")
    assert offscreen == 0, f"{offscreen} commitment markers render outside the map"

def test_fleet_load_failure_offers_a_retry_that_recovers(page: Page, base_url: str):
    """A failed fetch must NOT render "0 designs" — that would be a false
    negative about the industry rather than about the network, the same trap
    the civilian-nuclear overlay documents. It must say so and offer a retry,
    and the retry has to actually recover rather than re-render the error.

    The failure has to be made PERSISTENT to reach the error state at all: the
    fleet loads once eagerly at boot (for the map markers) and again on tab
    activation, and the boot attempt nulls its own promise on failure, so a
    single transient failure silently self-heals the moment the tab opens.
    That is good behaviour, and it is exactly why an intermittent 500 is the
    wrong thing to assert on here.
    """
    state = {"fail": True, "attempts": 0}

    def handler(route):
        state["attempts"] += 1
        if state["fail"]:
            route.fulfill(status=500, body="")
        else:
            route.continue_()

    page.route("**/data/microreactor-fleet.json", handler)
    _ready(page, base_url)
    page.click("#tab-ap1000")
    page.click("#micro-catalog > summary")
    page.wait_for_selector("#micro-retry", timeout=20_000)
    text = page.locator("#micro-content").inner_text()
    assert "could not be loaded" in text
    assert "0 designs" not in text and "0 commitments" not in text

    # Let the network recover, then confirm the button is wired to a real
    # refetch and not just a re-render of the same error.
    before = state["attempts"]
    state["fail"] = False
    page.click("#micro-retry")
    page.wait_for_selector(".janus-table", timeout=30_000)
    assert state["attempts"] > before, "the retry never re-fetched"
    assert page.locator("#micro-content table.micro-table").count() == 3

def test_tombstones_do_not_establish_isolation_or_federal_pathway(page,base_url):
    _ready(page,base_url)
    a=_assess(page,{'program':'fuds','_infraChecked':True},'micro')
    assert a['grid']['status']==a['regulatory']['status']==a['demand']['status']=='unknown'
    assert page.evaluate('typeof window.computeMicroreactorScore')=='undefined'

def test_nearby_generation_does_not_establish_customer_load(page,base_url):
    _ready(page,base_url)
    for fuel in ['solar','petroleum','nuclear']:
        assert _assess(page,{'power_plant_mi':0.1,'power_plant_mw':5,'power_plant_fuel':fuel},'micro')['demand']['status']=='unknown'

def test_micro_land_threshold_remains_unknown_when_unpublished(page,base_url):
    _ready(page,base_url)
    assert page.evaluate('microreactorMeetsAcreageThreshold({})') is None
    assert page.evaluate('microreactorMeetsAcreageThreshold({acreage:4.9})') is False
    assert page.evaluate('microreactorMeetsAcreageThreshold({acreage:5})') is True
