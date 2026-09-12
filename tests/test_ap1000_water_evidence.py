"""Curated water claims retain their actual statistic and evidence boundary."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location('ap1000_builder', ROOT / 'scripts/build_ap1000_sites.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_robins_drought_year_mean_cannot_masquerade_as_low_flow():
    mod = _builder()
    row = next(r for r in mod.SITES if r['id'] == 'robins-afb-ga')
    assert 'water_low_flow_cfs' not in row
    assert row['water_drought_year_mean_cfs'] == 854.1
    assert row['water_drought_year'] == 2012
    assert row['water_statistic'] == 'annual_mean'
    assert '02213000' in row['water_statistic_source_url']
    assert row['water_adequacy'] == 'unknown'


def test_unsourced_fiber_and_unallocated_water_remain_unknown():
    mod = _builder()
    assert all(row['fiber'] == 'unknown' for row in mod.SITES)
    assert all(row['water_adequacy'] == 'unknown' for row in mod.SITES)
    assert all(row['cls'] == 'unknown' for row in mod.WATER_RIGHTS.values())


def test_no_historical_use_claims_current_capacity_or_unlimited_supply():
    mod = _builder()
    arnold = next(r for r in mod.SITES if r['id'] == 'arnold-afb-tn')
    assert 'already withdraws' not in arnold['water_note']
    assert 'current' in arnold['water_note']
    for row in mod.SITES:
        assert 'effectively unlimited' not in row['water_note']


def test_published_curated_artifact_matches_repaired_source():
    mod = _builder()
    published = {r['id']: r for r in json.loads((ROOT / 'docs/data/ap1000-sites.json').read_text())['sites']}
    for source in mod.SITES:
        row = published[source['id']]
        for key in ('water_note', 'water_adequacy', 'fiber', 'fiber_note'):
            assert row[key] == source[key]
        assert row['water_rights_class'] == 'unknown'
        assert 'water_low_flow_cfs' not in row


def test_retired_plant_vintage_and_cache_identity_share_producer_pin():
    mod = _builder()
    from connectors.eia860m_source import EIA_860M_URL, EIA_CACHE_FILENAME, EIA_WORKBOOK_MONTH
    assert mod.EIA_860M_URL == EIA_860M_URL
    assert mod._EIA_CACHE_FILENAME == EIA_CACHE_FILENAME
    published = json.loads((ROOT / 'docs/data/ap1000-sites.json').read_text())
    assert published['retired_plant_source_month'] == EIA_WORKBOOK_MONTH
    assert published['retired_plant_source_url'] == EIA_860M_URL


def test_curated_grid_proxies_retain_asset_identity_and_limited_shared_metadata():
    infra = json.loads((ROOT / 'docs/data/infra-proximity.json').read_text())
    by_id = {r['id']: r for r in infra['sites']}
    curated = json.loads((ROOT / 'docs/data/ap1000-sites.json').read_text())
    for row in curated['sites']:
        source = by_id[row['infra_source_id']]
        for key in ('infra_evidence', 'infra_assessed_lat', 'infra_assessed_lon',
                    'transmission_asset_id', 'substation_asset_id', 'power_plant_asset_id', 'substation_role'):
            assert row.get(key) == source.get(key)
        assert row['infra_coordinate_basis'] == 'borrowed_reference_record'
        assert row['infra_confidence'] == 'low'
    for layer, metadata in curated['source_metadata']['infra'].items():
        if not isinstance(metadata, dict) or 'assets_by_id' not in metadata:
            continue
        referenced = {row.get(layer + '_asset_id') for row in curated['sites']}
        assert set(metadata['assets_by_id']) <= referenced
        original = infra['source_metadata'][layer]['assets_by_id']
        for asset_id, observation in metadata['assets_by_id'].items():
            assert observation == original[asset_id]
