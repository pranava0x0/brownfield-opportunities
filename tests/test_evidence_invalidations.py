"""Coordinate changes cannot silently reuse geographic evidence."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location('evidence_invalidations', ROOT / 'scripts/build_evidence_invalidations.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_threshold_keeps_rounding_changes_but_invalidates_spatial_evidence(tmp_path):
    mod = _module()
    before = tmp_path / 'before'; before.mkdir()
    data = tmp_path / 'data'; data.mkdir()
    previous = [{'id': 'A', 'lat': 40, 'lon': -80}, {'id': 'B', 'lat': 40, 'lon': -80}]
    current = [{'id': 'A', 'lat': 40.000001, 'lon': -80},
               {'id': 'B', 'lat': 40.001, 'lon': -80, 'current_owner': 'USACE owner', 'current_owner_source': 'USACE FUDS'}]
    for slug in mod.CORE:
        (before / f'{slug}-prior.json').write_text(json.dumps({'generated_at': '2026-01-01', 'sites': previous if slug == 'dod-fuds' else []}))
        (data / f'{slug}.json').write_text(json.dumps({'generated_at': '2026-09-12', 'sites': current if slug == 'dod-fuds' else []}))
    for slug, fields in [('parcel-owner', {'current_owner': 'STALE', 'current_owner_source': 'parcel', 'parcel_id': 'old', 'profile_url': 'https://wrong/', 'city': 'WRONG', 'acreage': 999}),
                         ('coord-quality', {'coord_flags': ['state_mismatch']}),
                         ('water-proximity', {'water_gage_mi': 1}),
                         ('nickel-anchor-proximity', {'nickel_feedstock_mi': 1, 'nickel_feedstock_id': 'NIA-a'}),
                         ('infra-proximity', {'transmission_mi': 1, 'flood_zone': 'AE', 'in_sfha': True}),
                         ('epa-echo', {'enforcement': {'x': 1}})]:
        (data / f'{slug}.json').write_text(json.dumps({'sites': [{'id': 'B', **fields}]}))
    result = mod.build(before, data)
    assert result['count'] == 2 and result['invalidated_count'] == 1
    assert result['by_id']['A']['clear_fields'] == []
    b = result['by_id']['B']
    assert {'current_owner', 'current_owner_source', 'parcel_id', 'coord_flags'} <= set(b['clear_fields'])
    assert not {'profile_url', 'city', 'acreage'} & set(b['clear_fields'])
    assert b['restore_core_fields']['current_owner'] == 'USACE owner'
    assert 'water_gage_mi' not in b['clear_fields']
    assert 'transmission_mi' not in b['clear_fields']
    assert not any(field.startswith('nickel_') for field in b['clear_fields'])
    assert result['dependency_catalog']['nickel-anchor-proximity.json']['status'] == 'rebuilt'
    assert {'flood_zone', 'in_sfha'} <= set(b['clear_fields'])
    assert 'enforcement' not in b['clear_fields']
    assert result['source_snapshots']['dod-fuds']['before_generated_at'] == '2026-01-01'


def test_unrebuilt_geographic_layer_does_not_inherit_rebuilt_status(tmp_path):
    mod = _module()
    before = tmp_path / 'before'; before.mkdir()
    data = tmp_path / 'data'; data.mkdir()
    for slug in mod.CORE:
        (before / f'{slug}-prior.json').write_text(json.dumps({'sites': [{'id': slug, 'lat': 40, 'lon': -80}]}))
        (data / f'{slug}.json').write_text(json.dumps({'sites': [{'id': slug, 'lat': 41, 'lon': -80}]}))
    (data / 'water-proximity.json').write_text(json.dumps({'sites': [{'id': 'dod-fuds', 'water_gage_mi': 1}]}))
    result = mod.build(before, data, rebuilt=())
    assert 'water_gage_mi' in result['by_id']['dod-fuds']['clear_fields']


def test_raw_artifact_disclosure_preserves_dates_and_untouched_files(tmp_path):
    mod = _module()
    source = tmp_path / 'parcel-owner.json'
    source.write_text(json.dumps({'generated_at': '2026-01-01', 'sites': [{'id': 'A', 'parcel_id': 'old'}]}))
    untouched = tmp_path / 'climate-zone.json'
    unchanged = '{"generated_at":"2026-01-01","sites":[{"id":"OTHER"}]}'
    untouched.write_text(unchanged)
    manifest = {'by_id': {'A': {'dependencies': [
        {'artifact': 'parcel-owner.json', 'status': 'invalidate', 'fields': ['parcel_id']},
        {'artifact': 'climate-zone.json', 'status': 'invalidate', 'fields': ['climate_zone']},
    ]}}}
    assert mod.annotate_stale_sources(manifest, tmp_path) == {'parcel-owner.json': 1}
    payload = json.loads(source.read_text())
    assert payload['generated_at'] == '2026-01-01'
    assert payload['sites'][0]['parcel_id'] == 'old'
    assert payload['source_metadata']['coordinate_updates_pending'] == ['A']
    assert payload['source_metadata']['coordinate_pending_fields'] == ['parcel_id']
    assert untouched.read_text() == unchanged
    first = source.read_bytes()
    mod.annotate_stale_sources(manifest, tmp_path)
    assert source.read_bytes() == first


def test_rebuilt_artifact_removes_pending_disclosure_without_losing_sources(tmp_path):
    mod = _module()
    path = tmp_path / 'nickel-anchor-proximity.json'
    path.write_text(json.dumps({'generated_at': '2026-09-12', 'source_metadata': {
        'anchors_by_id': {'A': {'verified_at': '2026-09-08'}},
        'coordinate_updates_pending': ['B'], 'coordinate_pending_fields': ['nickel_anchor_mi'],
        'coordinate_invalidation_manifest': 'evidence-invalidations.json',
        'coordinate_evidence_note': 'historical'}, 'sites': []}))
    manifest = {'by_id': {}, 'dependency_catalog': {path.name: {'status': 'rebuilt'}}}
    mod.annotate_stale_sources(manifest, tmp_path)
    result = json.loads(path.read_text())
    assert result['generated_at'] == '2026-09-12'
    assert result['source_metadata'] == {'anchors_by_id': {'A': {'verified_at': '2026-09-08'}}}
