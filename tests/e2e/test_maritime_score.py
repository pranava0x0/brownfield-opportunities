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

def test_port_join_reapplies_after_restricted_boot_then_reset(page: Page, base_url: str) -> None:
    """Codex review (this PR): booting with ?program=superfund leaves the
    ACRES/FUDS/BRAC promises null, so the initial port-proximity apply only
    reaches Superfund. Pressing Reset later loads those programs — the
    cached join (applyPortProximityJoin) must re-apply so their matches
    carry port_mi for the rest of the session. Same pattern as
    test_coal_join_reapplies_after_restricted_boot_then_reset in
    test_coal_repowering.py."""
    page.goto(f"{base_url}/index.html?program=superfund&lens=port")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    page.wait_for_function("window.__sites.some(s => s._portChecked)", timeout=30_000)
    acres_id = page.evaluate(
        """(async () => {
          const j = await (await fetch('data/port-proximity.json')).json();
          const m = (j.sites || []).find(x => x.id.startsWith('ACRES-') && x.port_mi != null);
          return m ? m.id : null;
        })()"""
    )
    assert acres_id, "shipped port-proximity file has no ACRES port match — test needs updating"
    # Not loaded yet under the restricted URL.
    assert page.evaluate(f"window.__sites.some(s => s.id === '{acres_id}')") is False
    page.evaluate("document.getElementById('filters-reset').click()")
    page.wait_for_function(
        f"""(() => {{
          const s = window.__sites.find(x => x.id === '{acres_id}');
          return !!(s && s.port_mi != null);
        }})()""",
        timeout=30_000,
    )

def test_non_conus_port_markers_are_remapped_into_the_inset(page: Page, base_url: str) -> None:
    """Codex review (this PR): ports.json ships AK/HI/PR/VI ports with real
    coordinates outside the lower-48 US_BOUNDS — a raw marker there is
    unreachable behind maxBoundsViscosity. ensurePortsLoaded() must call
    applyInsetRemap() on each port before placing its marker, the same
    treatment every other overlay gets once it gains a non-CONUS row."""
    _ready(page, base_url)
    page.click("#tab-map")
    page.wait_for_function(
        "window.__map && document.querySelectorAll('.port-icon').length > 0",
        timeout=15_000,
    )
    result = page.evaluate(
        """() => {
          const bounds = window.__leafletMap.options.maxBounds;
          const layers = Object.values(window.__map._layers || {});
          const hiMarker = layers.find(
            (l) => l.getPopup && l.getPopup() && l.getPopup().getContent
              && String(l.getPopup().getContent()).includes('Honolulu')
          );
          if (!hiMarker) return { found: false };
          const ll = hiMarker.getLatLng();
          return {
            found: true,
            withinBounds: bounds.contains(ll),
            insetNoted: String(hiMarker.getPopup().getContent()).includes('shown in the HI inset'),
          };
        }"""
    )
    assert result["found"], "Honolulu port marker not found — is ports.json still shipping HI ports?"
    assert result["withinBounds"]
    assert result["insetNoted"]

def test_port_screen_lists_only_sites_near_a_port(page: Page, base_url: str) -> None:
    """The port screen applies to sites within 25 mi of a principal port; a
    shipyard-only match or a landlocked site is out of scope."""
    page.goto(f"{base_url}/index.html?lens=port")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45_000)
    page.wait_for_function("window.__sites.some(s => s._portChecked) && document.querySelectorAll('#candidates-table tbody tr').length > 0", timeout=30_000)
    bad = page.evaluate("""()=>Array.from(document.querySelectorAll('#candidates-table tbody tr')).filter(r=>{const s=window.__sites.find(s=>s.id===r.dataset.id);return !(s.port_mi<=25)}).length""")
    assert bad == 0
    expect(page.locator("#candidates-stats")).to_contain_text("principal port")

def test_detail_panel_distinguishes_checked_negative_from_not_loaded(page: Page, base_url: str) -> None:
    """Codex round 2 (this PR): `_portChecked === true` with a null port_mi
    is a real negative result (checked, nothing within 75 mi), not the same
    'not yet loaded' state — the two must render different text."""
    _ready(page, base_url)
    page.click('[data-cand-lens="port"]')
    page.wait_for_function("window.__sites.some(s => s._portChecked)", timeout=30_000)
    result = page.evaluate(
        """() => {
          const landlocked = window.__sites.find(
            (s) => s._portChecked === true && s.port_mi == null
          );
          if (!landlocked) return { found: false };
          window.__selectSite(landlocked.id);
          const text = document.getElementById('d-port-mi').textContent;
          return { found: true, text };
        }"""
    )
    assert result["found"], "no checked-negative port record in the shipped data — test needs updating"
    assert "75 mi" in result["text"]
    assert "Not available" not in result["text"]

def test_shared_evidence_does_not_infer_maritime_service(page,base_url):
    _ready(page,base_url)
    a=_assess(page,{'_portChecked':True,'port_mi':0.1,'shipyard_mi':1},'maritime')
    assert a['water_rights']['status']==a['grid_capacity']['status']=='unknown'
    assert page.evaluate('typeof window.computeFloatingNuclearScore')=='undefined'


@pytest.mark.parametrize("status", [500, 404])
def test_failed_port_load_is_not_reported_as_zero_sites(page: Page, base_url: str, status: int) -> None:
    """A failed port join, including a missing file, must say so and offer a
    retry, never '0 of 0 sites'."""
    state = {"fail": True}
    page.route("**/data/port-proximity.json",
               lambda route: route.fulfill(status=status, body="") if state["fail"] else route.continue_())
    page.goto(f"{base_url}/index.html?lens=port")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45_000)
    page.wait_for_selector("#screen-retry", timeout=20_000)
    assert "meet every check" not in page.locator("#candidates-stats").inner_text()
    state["fail"] = False
    page.click("#screen-retry")
    expect(page.locator("#candidates-stats")).to_contain_text("meet every check", timeout=30_000)


def test_acreage_flags_failure_withholds_land_passes(page: Page, base_url: str) -> None:
    """Without acreage-flags.json a county/plume acreage must not pass the land
    check, and the screen says the input failed (Codex review, PR #43)."""
    state = {"fail": True}
    page.route("**/data/acreage-flags.json",
               lambda route: route.fulfill(status=500, body="") if state["fail"] else route.continue_())
    page.goto(f"{base_url}/index.html?q=Fox%20River%20NRDA")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45_000)
    page.wait_for_selector("#screen-retry", timeout=20_000)
    expect(page.locator("#candidates-stats")).to_contain_text("acreage flag")
    land = page.locator("#candidates-table tbody tr", has_text="Fox River").first.locator("td[data-status]").nth(1)
    expect(land).not_to_have_attribute("data-status", "pass")
    state["fail"] = False
    page.click("#screen-retry")
    expect(page.locator("#candidates-stats")).to_contain_text("meet every check", timeout=30_000)
    expect(land).not_to_have_attribute("data-status", "pass")  # now flagged as a plume


def test_missing_infra_core_shows_retry_not_a_ranking(page: Page, base_url: str) -> None:
    """A 404 on the infrastructure core file is a failed input (Codex review, PR #43)."""
    state = {"fail": True}
    page.route("**/data/infra-proximity-core.json",
               lambda route: route.fulfill(status=404, body="") if state["fail"] else route.continue_())
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45_000)
    page.wait_for_selector("#screen-retry", timeout=20_000)
    expect(page.locator("#candidates-stats")).to_contain_text("infrastructure")
    state["fail"] = False
    page.click("#screen-retry")
    expect(page.locator("#candidates-stats")).to_contain_text("meet every check", timeout=30_000)
