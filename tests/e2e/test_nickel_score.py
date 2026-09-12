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


@pytest.mark.parametrize("site,expected", [({},None),({"acreage":299},False),({"acreage":300},True),({"acreage":None,"parcel_acreage":301},True),({"acreage":-1},None)])
def test_land_threshold_remains_tri_state(page,base_url,site,expected):
    _ready(page,base_url)
    assert page.evaluate('(s)=>nickelAcreageStatus(s)',site) is expected

def test_recycling_threshold_is_distinct(page,base_url):
    _ready(page,base_url)
    assert page.evaluate('nickelAcreageStatus({acreage:100},NICKEL_MIN_ACRES_RECYCLING)') is True
    assert page.evaluate('nickelAcreageStatus({acreage:100})') is False

def test_water_join_cannot_establish_supply_or_rights(page,base_url):
    _ready(page,base_url)
    before=_assess(page,{},'nickel');after=_assess(page,{'_waterChecked':True,'water_gage_mi':0,'water_flow_cfs':20000},'nickel')
    assert before['water']['status']=='unknown' and after['water']['status']=='context'
    assert after['water_reliability']['status']==after['water_rights']['status']=='unknown'

def test_feedstock_catalog_is_not_a_contract(page,base_url):
    _ready(page,base_url)
    a=_assess(page,{'nickel_feedstock_mi':1},'nickel')
    assert a['feedstock']['confidence']=='Low' and 'agreement' in a['feedstock']['reason']
    assert page.evaluate('typeof window.computeNickelImportScore')=='undefined'

def test_missing_water_does_not_erase_grid_and_known_flood(page,base_url):
    _ready(page,base_url)
    a=_assess(page,{'substation_mi':1,'in_sfha':True},'nickel')
    assert a['grid']['status']=='context' and a['water']['status']=='unknown'
    assert a['hazards']['status']=='constraint'
