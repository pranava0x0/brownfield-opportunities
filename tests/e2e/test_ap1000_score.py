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


def test_no_nuclear_total_and_unknown_fiber_retained(page, base_url):
    _ready(page, base_url)
    assert page.evaluate("typeof window.computeAp1000Score") == "undefined"
    a = _assess(page, {"fiber": "excellent", "acreage_source": "https://example.org/land", "water_rights_class": "obtainable"}, "nuclear")
    assert a["fiber"]["status"] == a["water_rights"]["status"] == "unknown"

def test_ap1000_rows_are_alphabetical_and_class_change_preserves_evidence(page, base_url):
    _ready(page, base_url);page.click("#tab-ap1000")
    page.wait_for_selector(".ap1000-row")
    assert page.locator(".ap1000-row").count() == 14
    names=page.locator(".ap1000-expand").all_inner_texts()
    assert names == sorted(names)
    before=page.locator('.ap1000-row [data-category="fiber"]').all_inner_texts()
    page.click('[data-reactor-class="micro"]')
    assert page.locator('[data-reactor-class="micro"]').get_attribute('aria-pressed') == 'true'
    assert page.locator('.ap1000-row [data-category="fiber"]').all_inner_texts() == before

def test_ap1000_csv_preserves_source_values_and_separate_categories(page, base_url):
    _ready(page, base_url);page.click("#tab-ap1000");page.wait_for_selector(".ap1000-row")
    rows=list(csv.DictReader(io.StringIO(page.evaluate("window.__buildAp1000Csv()"))))
    assert len(rows)==14
    keys=set(rows[0]); assert "score" not in keys and "rank" not in keys
    assert {"grid_finding","fiber_finding","water_finding","water_sources","developable_acreage","developable_acreage_source_url"} <= keys
    assert all(x['fiber_finding']=='Unknown' for x in rows)

def test_ap1000_keyboard_expansion_and_table_semantics(page, base_url):
    _ready(page, base_url);page.click("#tab-ap1000");page.wait_for_selector(".ap1000-row")
    assert page.locator('.ap1000-table caption').count()==1
    assert page.locator('.ap1000-table thead th').count()==6
    assert page.locator('.ap1000-table thead th:not([scope="col"])').count()==0
    first=page.locator('.ap1000-expand').first;first.focus();page.keyboard.press('Enter')
    assert first.get_attribute('aria-expanded')=='true'
    expect(page.locator('.ap1000-detail:not([hidden])')).to_be_visible()

def test_reactor_classes_keep_design_uncertainty_and_land_thresholds(page, base_url):
    _ready(page, base_url)
    c=page.evaluate('window.REACTOR_CLASSES')
    assert c['ap1000']['group']==c['apr1400']['group']=='Large PWR'
    assert c['ap300']['group']=='SMR' and c['micro']['group']=='Microreactor'
    assert c['micro']['mwe'] is None and c['micro']['dry_cooling_viable'] is None
    assert all(x.get('spec_source') and x.get('water_source') for x in c.values())
    assert page.evaluate('ap1000MeetsAcreageThreshold({})') is None
    assert page.evaluate('ap1000MeetsAcreageThreshold({developable_acreage:499})') is False
    assert page.evaluate('ap1000MeetsAcreageThreshold({developable_acreage:500})') is True

def test_nuclear_details_keep_offered_parcel_and_geohazard_sources(page, base_url):
    _ready(page, base_url);page.click('#tab-ap1000');page.wait_for_selector('.ap1000-row')
    row=page.locator('.ap1000-row').filter(has_text='Arnold').first;row.locator('button').click()
    detail=row.locator('xpath=following-sibling::tr[1]')
    assert '274' in detail.inner_text()
    assert detail.locator('a[href*="sam.gov"]').count() >= 1
    expect(detail.locator('.ap1000-flags-cell')).to_contain_text('0.18g')
    expect(detail.locator('.ap1000-flags-cell')).to_contain_text('SDC C')
    assert detail.locator('a[href*="earthquake.usgs.gov"]').count() >= 1
    assert page.locator('.ap1000-class-context a').count() >= 1

def test_ap1000_air_force_rflp_provenance_is_emitted(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    rflp = page.evaluate(
        """async () => {
          const payload = await fetch('data/ap1000-sites.json').then((r) => r.json());
          return payload.sites
            .filter((s) => s.af_rflp_site)
            .map((s) => ({ id: s.id, acres: s.af_rflp_acres, source: s.af_rflp_source_url }));
        }"""
    )
    assert {r["id"] for r in rflp} == {
        "arnold-afb-tn",
        "davis-monthan-afb-az",
        "edwards-afb-ca",
        "jbmdl-nj",
        "robins-afb-ga",
    }
    assert sum(r["acres"] for r in rflp) == 3132
    assert all("sam.gov" in r["source"] for r in rflp)

def test_mobile_nuclear_details_stay_hidden_until_expanded(page,base_url):
    page.set_viewport_size({"width":375,"height":812})
    _ready(page,base_url);page.click("#tab-ap1000");page.wait_for_selector(".ap1000-row")
    assert page.locator(".ap1000-detail").count()==14
    assert page.locator(".ap1000-detail:visible").count()==0
    page.locator(".ap1000-expand").first.click()
    assert page.locator(".ap1000-detail:visible").count()==1
