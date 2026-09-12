"""Moved source coordinates cannot recover stale evidence through later joins."""
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]


def test_late_join_and_csv_respect_coordinate_invalidation(page, base_url):
    record = json.loads((ROOT / 'docs/data/sites.json').read_text())['sites'][0]
    site_id = record['id']
    manifest = {'schema_version': 1, 'by_id': {site_id: {
        'invalidate': True, 'clear_fields': ['port_mi', 'parcel_acreage', 'in_sfha', 'summary', 'summary_meta'],
        'restore_core_fields': {'current_owner': 'Core owner'}, 'distance_m': 200}}}
    page.route('**/evidence-invalidations.json', lambda route: route.fulfill(json=manifest))
    page.goto(f'{base_url}/index.html?program=superfund')
    page.wait_for_function('window.__APP_READY__ === true', timeout=45000)
    state = page.evaluate('''id => {
        const s=window.__sites.find(s=>s.id===id);
        s.port_mi=0.01; s.parcel_acreage=99999; s.in_sfha=true; s.summary='Stale geographic advice';
        window.__selectSite(id);
        return {port:s.port_mi??null,area:s.parcel_acreage??null,flood:s.in_sfha??null,owner:s.current_owner};
    }''', site_id)
    assert state == {'port': None, 'area': None, 'flood': None, 'owner': 'Core owner'}
    assert page.locator('.evidence-invalidation').count() == 1
    # A summary loader has its own direct rendering path; it must sanitize too.
    page.evaluate('''id => {const s=window.__sites.find(s=>s.id===id); s.summary='Stale geographic advice'; renderSummary(s);}''', site_id)
    assert 'Stale geographic advice' not in page.locator('#d-summary-body').inner_text()


def test_missing_validation_manifest_withholds_geographic_claims(page, base_url):
    page.route('**/evidence-invalidations.json', lambda route: route.fulfill(status=503, body='Unavailable'))
    page.goto(f'{base_url}/index.html?program=superfund')
    page.wait_for_function('window.__APP_READY__ === true', timeout=45000)
    assert page.locator('#candidates-table [data-category="grid"] .evidence-finding').first.inner_text() == 'Unknown'
    page.locator('#candidates-table .site-evidence-open').first.click()
    assert 'Coordinate validation unavailable' in page.locator('#d-suit-dc').inner_text()
