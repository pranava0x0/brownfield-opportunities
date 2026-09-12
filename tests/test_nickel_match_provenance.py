"""Typed matches must retain their own citation, never the closest other kind."""
import argparse

from connectors.nickel_anchor_proximity import NickelAnchorProximity
from schema import SiteRecord


def test_typed_anchor_identity_and_original_observation_date(tmp_path, monkeypatch):
    connector = NickelAnchorProximity(cache_dir=tmp_path)
    monkeypatch.setattr(connector, '_load_sites', lambda: [
        {'id': 's', 'program': 'superfund', 'lat': 40, 'lon': -80},
        {'id': 'remote', 'program': 'fuds', 'lat': 65, 'lon': -150}])
    anchors = [
        {'id': 'demand', 'name': 'Nearby buyer', 'kind': 'demand_battery',
         'lat': 40, 'lon': -80, 'source_url': 'https://example.com/buyer',
         'verified_at': '2020-01-01'},
        {'id': 'feed', 'name': 'Distant mine', 'kind': 'feedstock_mine',
         'lat': 41, 'lon': -80, 'source_url': 'https://example.com/mine',
         'verified_at': '2021-02-03', 'status': 'Planned', 'coord_precision': 'locality'}]
    monkeypatch.setattr(connector, '_load_anchors', lambda: anchors)
    records = connector.fetch_records(argparse.Namespace(), use_cache=True)
    matched = records[0]
    assert matched['nickel_anchor_name'] == 'Nearby buyer'
    assert matched['nickel_feedstock_id'] == 'feed'
    assert matched['nickel_demand_id'] == 'demand'
    assert 'nickel_acid_id' not in matched
    source = connector.source_metadata['anchors_by_id'][matched['nickel_feedstock_id']]
    assert source['source_url'] == 'https://example.com/mine'
    assert source['verified_at'] == '2021-02-03'
    assert source['status'] == 'Planned'
    assert source['coord_precision'] == 'locality'
    assert records[1] == {'id': 'remote', 'program': 'fuds'}
    assert SiteRecord.model_validate(matched).nickel_feedstock_id == 'feed'


def test_non_nickel_chemistry_and_inactive_projects_are_not_demand(tmp_path, monkeypatch):
    connector = NickelAnchorProximity(cache_dir=tmp_path)
    monkeypatch.setattr(connector, '_load_sites', lambda: [
        {'id': 's', 'program': 'superfund', 'lat': 40, 'lon': -80}])
    anchors = [
        {'id': 'lfp', 'name': 'LFP plant', 'kind': 'demand_battery',
         'lat': 40, 'lon': -80, 'nickel_demand_eligible': False},
        {'id': 'inactive', 'name': 'Cancelled project', 'kind': 'demand_battery',
         'lat': 40, 'lon': -80, 'proximity_eligible': False},
        {'id': 'ncma', 'name': 'Nickel cell plant', 'kind': 'demand_battery',
         'lat': 41, 'lon': -80}]
    monkeypatch.setattr(connector, '_load_anchors', lambda: anchors)
    result = connector.fetch_records(argparse.Namespace(), True)[0]
    assert result['nickel_demand_id'] == 'ncma'
    assert result['nickel_anchor_name'] == 'LFP plant'  # manufacturing context retained
    assert connector._subset([anchors[1]], ('demand_battery',)) == []
    assert 'inactive' in connector.source_metadata['anchors_by_id']


def test_shipped_catalog_exclusions_and_row_dates():
    from scripts.build_nickel_anchors import ANCHORS
    rows = {a['id']: a for a in ANCHORS}
    assert rows['NIA-blueoval-glendale']['nickel_demand_eligible'] is False
    assert rows['NIA-beulah-bmpf']['proximity_eligible'] is False
    assert rows['NIA-humboldt-mill']['verified_at'] == '2026-09-12'
