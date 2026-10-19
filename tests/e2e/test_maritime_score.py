"""Browser contracts for category evidence; legacy numeric suitability is retired."""
from __future__ import annotations
import csv
import io
import re
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


def test_failed_program_load_shows_retry_and_joins_after_recovery(page: Page, base_url: str) -> None:
    """A failed ACRES load is reported, not ranked around; once it loads on
    retry its sites get the infrastructure join (Codex review, PR #43)."""
    state = {"fail": True}
    page.route("**/data/epa-acres.json",
               lambda route: route.fulfill(status=500, body="") if state["fail"] else route.continue_())
    page.goto(f"{base_url}/index.html")
    page.wait_for_selector("#screen-retry", timeout=45_000)
    expect(page.locator("#candidates-stats")).to_contain_text("ACRES brownfield")
    state["fail"] = False
    page.click("#screen-retry")
    expect(page.locator("#candidates-stats")).to_contain_text("meet every check", timeout=60_000)
    joined = page.evaluate("""() => window.__sites.filter(s => s.program === 'brownfield')
        .some(s => s._infraChecked && s.transmission_mi != null)""")
    assert joined


def test_missing_parcel_file_shows_retry(page: Page, base_url: str) -> None:
    """Parcel area is a land input; a 404 is a failed load (Codex review, PR #43)."""
    state = {"fail": True}
    page.route("**/data/parcel-owner.json",
               lambda route: route.fulfill(status=404, body="") if state["fail"] else route.continue_())
    page.goto(f"{base_url}/index.html")
    page.wait_for_selector("#screen-retry", timeout=45_000)
    expect(page.locator("#candidates-stats")).to_contain_text("parcel")
    state["fail"] = False
    page.click("#screen-retry")
    expect(page.locator("#candidates-stats")).to_contain_text("meet every check", timeout=30_000)
    assert page.evaluate("window.__sites.some(s => s.parcel_acreage != null)")


def test_failed_coordinate_manifest_is_reported(page: Page, base_url: str) -> None:
    """Without the manifest the geographic fields are withheld; the screen must
    say so instead of presenting a ranking of unknowns (Codex review, PR #43)."""
    page.route("**/data/evidence-invalidations.json", lambda route: route.fulfill(status=500, body=""))
    page.goto(f"{base_url}/index.html")
    page.wait_for_selector("#screen-retry", timeout=45_000)
    expect(page.locator("#candidates-stats")).to_contain_text("coordinate validation")


def test_empty_screen_exports_an_empty_screen_csv(page: Page, base_url: str) -> None:
    """Zero visible rows export the screen header only, not the corpus (Codex review, PR #43)."""
    page.goto(f"{base_url}/index.html?q=zzzz-no-site-matches")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45_000)
    expect(page.locator("#candidates-table tbody tr")).to_have_count(0)
    lines = page.evaluate("window.__buildCsv()").strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("rank,checks_met")


def test_open_drawer_drops_a_land_pass_when_acreage_flags_land(page: Page, base_url: str) -> None:
    """A drawer opened before acreage-flags.json loads re-renders when it does,
    so a county-outline acreage never stays a land pass (Codex review, PR #43)."""
    held = []
    page.route("**/data/acreage-flags.json", lambda route: held.append(route))
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__sites && window.__sites.some(s => s.id === 'WI0001954841')", timeout=45_000)
    page.evaluate("window.__selectSite('WI0001954841')")  # Fox River: 1.13M ac, a river, flagged
    chip = page.locator("#d-suit-dc .screen-chip", has_text="Land").first
    expect(chip).not_to_have_attribute("data-status", "pass")  # withheld while the flags load
    assert held, "acreage-flags.json was never requested"
    held[0].continue_()
    # The drawer re-renders with the flag: the land value now says why.
    expect(chip).to_have_attribute("title", re.compile("area not a parcel"), timeout=30_000)
    expect(chip).not_to_have_attribute("data-status", "pass")


def test_ranking_waits_for_the_coordinate_manifest(page: Page, base_url: str) -> None:
    """No rows are ranked while stale joins could still be on the sites (Codex review, PR #43)."""
    held = []
    page.route("**/data/evidence-invalidations.json", lambda route: held.append(route))
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__sites && window.__sites.length > 1000", timeout=45_000)
    expect(page.locator("#candidates-stats")).to_contain_text("coordinate validation")
    assert page.locator("#candidates-table tbody tr").count() == 0
    assert page.evaluate("window.__buildCsv()").strip().count("\n") == 0
    held[0].continue_()
    expect(page.locator("#candidates-stats")).to_contain_text("meet every check", timeout=45_000)
    assert page.locator("#candidates-table tbody tr").count() > 0


def test_late_program_gets_the_full_infrastructure_payload(page: Page, base_url: str) -> None:
    """A program enabled after the site panel loaded infra-proximity.json still
    gets asset ids and evidence (Codex review, PR #43)."""
    page.goto(f"{base_url}/index.html?program=superfund")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45_000)
    page.evaluate("ensureInfraEvidenceLoaded()")
    page.wait_for_function("window.__sites.some(s => s.infra_evidence && s.program === 'superfund')", timeout=45_000)
    page.evaluate("ensureFudsLoaded()")
    page.wait_for_function("""() => window.__sites.some(s => s.program === 'fuds'
        && s.transmission_asset_id && s.infra_evidence)""", timeout=60_000)
