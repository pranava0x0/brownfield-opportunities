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

def test_duplicate_filter_groups_removed(page, base_url):
    """The unsynced Min-tier / Readiness button groups are gone — those
    predicates live in the global filter strip (persona buttons, OZ
    checkbox, DC-candidate KPI toggle). Only the lens toggle remains,
    plus a note pointing at the global filters."""
    _ready(page, base_url)
    counts = page.evaluate(
        "() => ({"
        "  tier: document.querySelectorAll('[data-cand-tier]').length,"
        "  ready: document.querySelectorAll('[data-cand-ready]').length,"
        "  lens: document.querySelectorAll('[data-cand-lens]').length,"
        "  note: !!document.querySelector('.cand-filter-note')"
        "})"
    )
    assert counts["tier"] == 0
    assert counts["ready"] == 0
    assert counts["lens"] == 3
    assert counts["note"] is True

def test_detail_panel_npdes_row_renders(page, base_url):
    """The detail panel's "Water permit (NPDES)" row (#d-echo-npdes) reflects
    the ECHO `has_npdes_permit` flag with the ready-tinted affirmative text."""
    _ready(page, base_url)
    page.evaluate("() => ensureDetailEvidenceLoaded()")
    site_id = page.evaluate(
        "() => {"
        "  const s = window.__sites.find(s => s.transmission_mi != null);"
        "  if (!s) return null;"
        "  s.enforcement = Object.assign({}, s.enforcement, {has_npdes_permit: true});"
        "  window.__selectSite(s.id);"
        "  return s.id;"
        "}"
    )
    assert site_id, "expected a scored site to select"
    page.wait_for_selector("#detail:not([hidden])", timeout=5000)
    row = page.evaluate(
        "() => { const n = document.getElementById('d-echo-npdes');"
        " return { text: n.textContent.trim(), cls: n.className }; }"
    )
    assert "Yes" in row["text"], f"expected affirmative NPDES text, got {row['text']!r}"
    assert "ready" in row["cls"], f"expected ready tint, got {row['cls']!r}"

def test_detail_panel_planned_retirement_row_renders(page, base_url):
    """The detail panel's "Retiring plant" row (#d-planned-retire-mi) renders
    the distance + a name/MW/fuel/year chip when a planned-retirement plant is
    joined onto the site."""
    _ready(page, base_url)
    site_id = page.evaluate(
        "() => {"
        "  const s = window.__sites.find(s => s.transmission_mi != null);"
        "  if (!s) return null;"
        "  s.planned_retirement_mi = 0.4;"
        "  s.planned_retirement_mw = 2600;"
        "  s.planned_retirement_fuel = 'coal';"
        "  s.planned_retirement_year = 2028;"
        "  s.planned_retirement_name = 'Cumberland';"
        "  window.__selectSite(s.id);"
        "  return s.id;"
        "}"
    )
    assert site_id, "expected a scored site to select"
    page.wait_for_selector("#detail:not([hidden])", timeout=5000)
    cell = page.evaluate(
        "() => document.getElementById('d-planned-retire-mi').textContent"
    )
    assert "Cumberland" in cell, f"expected the plant name in the cell, got {cell!r}"
    assert "2,600 MW" in cell
    assert "ret. 2028" in cell

def test_planned_retirement_join_covers_all_programs(page, base_url):
    """Regression (PR #19 / Codex P1): the tiny planned-retirements-proximity
    file can resolve before the large ACRES/FUDS program files ingest, so the
    join's `!existing` guard would silently drop the brownfield/FUDS records
    (the majority of the 614). After full load, EVERY record in the file whose
    id is present in the loaded set must be joined — not just Superfund.

    The race is timing-dependent (on a fast local server ACRES can win), so we
    FORCE it: delay the ACRES + FUDS responses so the tiny proximity file lands
    first. Without the await-guard fix, this deterministically drops the
    non-Superfund joins; with it, the loader waits for the program promises."""
    def _slow(route):
        import time as _t
        _t.sleep(0.8)
        route.continue_()
    page.route("**/epa-acres.json", _slow)
    page.route("**/dod-fuds.json", _slow)
    page.goto(f"{base_url}/index.html", wait_until="domcontentloaded")
    page.wait_for_function("typeof acresLoadingPromise !== 'undefined' && acresLoadingPromise !== null")
    # This enrichment is detail-lazy. Start it while program responses are delayed
    # so the regression still exercises the join-order guard.
    page.evaluate("() => ensurePlannedRetireProxLoaded()")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60000)
    stats = page.evaluate(
        """async () => {
          const byId = new Map(window.__sites.map(s => [s.id, s]));
          const r = await fetch('data/planned-retirements-proximity.json');
          const j = await r.json();
          let present = 0, joined = 0, joinedNonSuperfund = 0;
          for (const rec of j.sites) {
            const s = byId.get(rec.id);
            if (!s) continue;             // program not loaded (all four are on by default)
            present++;
            if (s.planned_retirement_mi != null) {
              joined++;
              if (s.program !== 'superfund') joinedNonSuperfund++;
            }
          }
          return { total: j.sites.length, present, joined, joinedNonSuperfund };
        }"""
    )
    # Every present record is joined (no silent drops from the load-order race).
    assert stats["joined"] == stats["present"], (
        f"{stats['present'] - stats['joined']} of {stats['present']} present "
        f"records were dropped by the load-order race"
    )
    # And the join genuinely reaches non-Superfund programs (proves the race fix,
    # not just that Superfund — eagerly loaded — happened to be present).
    assert stats["joinedNonSuperfund"] > 50, (
        f"expected many ACRES/FUDS joins, got {stats['joinedNonSuperfund']}"
    )

def test_tribal_area_join_covers_lazy_programs(page, base_url):
    """The all-program AIANNHA enrichment must wait for ACRES/FUDS ingest."""
    def _slow(route):
        import time as _t
        _t.sleep(0.8)
        route.continue_()

    page.route("**/epa-acres.json", _slow)
    page.route("**/dod-fuds.json", _slow)
    _ready(page, base_url)
    page.evaluate("() => ensureTribalAreasLoaded()")
    stats = page.evaluate(
        """async () => {
          const byId = new Map(window.__sites.map(s => [s.id, s]));
          const payload = await (await fetch('data/tribal-areas.json')).json();
          let present = 0, joined = 0, joinedNonSuperfund = 0;
          for (const rec of payload.sites) {
            const site = byId.get(rec.id);
            if (!site) continue;
            present++;
            if (site.in_aiannha_area === rec.in_aiannha_area) {
              joined++;
              if (site.program !== 'superfund') joinedNonSuperfund++;
            }
          }
          return { present, joined, joinedNonSuperfund };
        }"""
    )
    assert stats["joined"] == stats["present"]
    assert stats["joinedNonSuperfund"] > 1000

def test_global_state_filter_rebuilds_explore(page,base_url):
    _ready(page,base_url)
    page.evaluate("()=>{const n=document.getElementById('f-state');n.value='AK';n.dispatchEvent(new Event('change'))}")
    expect(page.locator('#candidates-table tbody tr').first).to_be_visible()
    assert page.evaluate("""()=>Array.from(document.querySelectorAll('#candidates-table tbody tr')).every(r=>window.__sites.find(s=>s.id===r.dataset.id).state==='AK')""")

@pytest.mark.parametrize('lens',['gen','mfg'])
def test_lens_roundtrip_keeps_alphabetical_evidence_order(page,base_url,lens):
    _ready(page,base_url);page.click(f'[data-cand-lens="{lens}"]')
    page.wait_for_function('(lens)=>location.search.includes("lens="+lens)',arg=lens)
    expect(page.locator('#candidates-stats')).to_contain_text('alphabetical')
    before=page.locator('#candidates-table .site-evidence-open').all_inner_texts()
    assert page.evaluate('names=>names.every((n,i)=>!i||names[i-1].localeCompare(n)<=0)',before)
    page.reload();page.wait_for_function('window.__APP_READY__===true',timeout=45000)
    assert 'active' in page.locator(f'[data-cand-lens="{lens}"]').get_attribute('class')
    assert page.locator('#candidates-table .site-evidence-open').all_inner_texts()==before

def test_environmental_context_does_not_establish_ready_land(page,base_url):
    _ready(page,base_url)
    a=_assess(page,{'npl_status_code':'D','enforcement':{'has_npdes_permit':True},'in_sfha':True})
    assert a['hazards']['status']=='constraint'
    assert a['land']['status']==a['water_rights']['status']=='unknown'
