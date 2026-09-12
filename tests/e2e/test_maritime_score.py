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
    page.goto(f"{base_url}/index.html?program=superfund")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    page.click("#tab-maritime")
    page.wait_for_selector("#maritime-table tbody tr")
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

def test_coastal_lens_excludes_shipyard_only_sites(page: Page, base_url: str) -> None:
    """Codex round 2 (this PR): computeCoastalGenerationScore has NO shipyard
    component and the tab's own copy says 'within reach of a port' for this
    lens — a shipyard-only match (port_mi null, shipyard_mi set) is not a
    coastal candidate even though it passes the offshore lens's eligibility
    test. Every rendered row on the coastal lens must have a real port_mi."""
    _ready(page, base_url)
    page.evaluate("document.getElementById('tab-maritime').click()")
    page.wait_for_selector("#maritime-table tbody tr", timeout=15_000)
    page.evaluate('document.querySelector(\'[data-maritime-lens="coastal"]\').click()')
    page.wait_for_function(
        "document.querySelector('[data-maritime-lens=\"coastal\"]').classList.contains('active')"
    )
    page.wait_for_selector("#maritime-table tbody tr", timeout=15_000)
    result = page.evaluate(
        """() => {
          const rows = Array.from(document.querySelectorAll('#maritime-table tbody tr'));
          const bad = rows.filter((tr) => {
            const s = window.__sites.find((x) => x.id === tr.dataset.id);
            return !s || s.port_mi == null;
          }).length;
          return { total: rows.length, bad };
        }"""
    )
    assert result["total"] > 0
    assert result["bad"] == 0

def test_detail_panel_distinguishes_checked_negative_from_not_loaded(page: Page, base_url: str) -> None:
    """Codex round 2 (this PR): `_portChecked === true` with a null port_mi
    is a real negative result (checked, nothing within 75 mi), not the same
    'not yet loaded' state — the two must render different text."""
    _ready(page, base_url)
    page.click("#tab-map")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    page.click("#tab-maritime")
    page.wait_for_function("window.__sites.some(s => s._portChecked)")
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

def test_maritime_table_excludes_unmatched_locations(page,base_url):
    _ready(page,base_url);page.click('#tab-maritime');page.wait_for_selector('#maritime-table tbody tr')
    bad=page.evaluate("""()=>Array.from(document.querySelectorAll('#maritime-table tbody tr')).filter(r=>{const s=window.__sites.find(s=>s.id===r.dataset.id);return s.port_mi==null && s.shipyard_mi==null}).length""")
    assert bad==0
    assert page.locator('#maritime-table [data-category="grid"]').count()>0
