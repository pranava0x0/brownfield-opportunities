"""Unit tests for the water-proximity connector and the gage builder's parsing.

The connector is a thin PointIndex join, so the tests here concentrate on the
two things that are easy to get wrong and invisible when wrong: the tombstone
convention, and the RDB parser.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_streamgages_overlay",
        str(ROOT / "scripts" / "build_streamgages_overlay.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- RDB parsing -----------------------------------------------------------

RDB = "\n".join([
    "# a comment line",
    "#",
    "agency_cd\tsite_no\tstation_nm\tdec_lat_va\tdec_long_va\tdrain_area_va",
    "5s\t15s\t50s\t16s\t16s\t8s",
    "USGS\t04001000\tWASHINGTON CREEK AT WINDIGO, MI\t47.92138906\t-89.14590845\t13.2",
    "USGS\t04040500\tSTURGEON RIVER NEAR SIDNAW, MI\t46.51\t-88.71\t171",
])


def test_rdb_parser_drops_comments_and_the_type_row():
    """USGS RDB puts a format row ('5s', '15s', '16s') straight after the
    header. Treating it as data yields a phantom gage at latitude '16s'."""
    mod = _load_builder()
    rows = mod._parse_rdb(RDB)
    assert len(rows) == 2
    assert rows[0]["site_no"] == "04001000"
    assert rows[0]["dec_lat_va"] == "47.92138906"
    assert all(r["agency_cd"] == "USGS" for r in rows)


def test_stat_batch_respects_the_services_documented_ceiling():
    """The stat service returns HTTP 400 above ten sites per request (probed
    2026-09-08). The batch size is not a tuning knob."""
    mod = _load_builder()
    assert mod.STAT_BATCH == 10


def test_a_sub_creek_flow_floor_is_set_low_so_filtering_happens_in_scoring():
    """The floor exists to keep creeks out of the index, not to make the
    siting judgement — that belongs in the scoring curve."""
    mod = _load_builder()
    assert 0 < mod.MIN_MEAN_FLOW_CFS <= 10


# --- the connector ---------------------------------------------------------

@pytest.fixture()
def connector(tmp_path, monkeypatch):
    from connectors.water_proximity import WaterProximity

    data = tmp_path / "docs" / "data"
    data.mkdir(parents=True)
    (data / "superfund-npl.json").write_text(json.dumps({"sites": [
        {"id": "A1", "program": "superfund", "lat": 46.50, "lon": -88.70},
        {"id": "A2", "program": "superfund", "lat": 25.00, "lon": -80.00},
        {"id": "A3", "program": "superfund", "lat": None, "lon": None},
    ]}))
    (data / "streamgages.json").write_text(json.dumps({"sites": [
        {"gage_id": "04040500", "name": "STURGEON RIVER", "lat": 46.51,
         "lon": -88.71, "mean_flow_cfs": 340.5},
    ]}))
    monkeypatch.setattr(WaterProximity, "_data_dir", staticmethod(lambda: data))
    return WaterProximity(cache_dir=tmp_path / "cache")


def test_every_site_with_coordinates_gets_a_record_even_with_no_water(connector):
    """The tombstone convention (infra-proximity v1.11.5). Without it, a
    missing entry is ambiguous between 'nothing in range' and 'never ran' —
    which is exactly the distinction the frontend's `_waterChecked` marker and
    the score gate depend on."""
    recs = connector.fetch_records(argparse.Namespace(limit=None), True)
    by_id = {r["id"]: r for r in recs}
    assert set(by_id) == {"A1", "A2"}, "A3 has no coordinates and is skipped"
    assert "water_flow_cfs" in by_id["A1"]
    assert "water_flow_cfs" not in by_id["A2"], "Florida site is 1,500 mi away"
    assert by_id["A2"]["program"] == "superfund"


def test_the_nearest_gage_and_its_flow_are_carried_through(connector):
    recs = connector.fetch_records(argparse.Namespace(limit=None), True)
    a1 = next(r for r in recs if r["id"] == "A1")
    assert a1["water_flow_cfs"] == 340.5
    assert a1["water_gage_id"] == "04040500"
    assert a1["water_gage_mi"] < 1.0


def test_an_empty_gage_index_aborts_rather_than_writing_a_waterless_file(
        tmp_path, monkeypatch):
    """A silently water-less join would set `_waterChecked` on every site and
    make the whole corpus read as 'checked, no water' — worse than not
    running, because the score gate would then let it through."""
    from connectors.water_proximity import WaterProximity

    data = tmp_path / "docs" / "data"
    data.mkdir(parents=True)
    (data / "superfund-npl.json").write_text(json.dumps({"sites": [
        {"id": "A1", "program": "superfund", "lat": 46.5, "lon": -88.7}]}))
    (data / "streamgages.json").write_text(json.dumps({"sites": []}))
    monkeypatch.setattr(WaterProximity, "_data_dir", staticmethod(lambda: data))
    assert WaterProximity(cache_dir=tmp_path / "cache").fetch_records(argparse.Namespace(limit=None), True) == []


def test_run_order_places_the_join_after_the_producers():
    from connectors.water_proximity import WaterProximity
    assert WaterProximity.run_order > 100


def test_a_scoped_build_never_truncates_the_national_catalog(tmp_path, monkeypatch):
    """`--states MI,ME` is a documented invocation. Writing only the fetched
    subset would replace the national artifact with two states, and the water
    join turns every dropped gage into a negative tombstone and a lower score
    — silently. Fetched rows win; everything else is preserved."""
    mod = _load_builder()
    out = tmp_path / "streamgages.json"
    out.write_text(json.dumps({"sites": [
        {"gage_id": "11111111", "name": "OLD A", "state": "CA", "lat": 34.0,
         "lon": -118.0, "mean_flow_cfs": 100.0, "record_years": 10,
         "drainage_sqmi": None, "source_url": "https://x/", "verified_at": "2026-01-01"},
        {"gage_id": "22222222", "name": "OLD B", "state": "ME", "lat": 44.0,
         "lon": -69.0, "mean_flow_cfs": 200.0, "record_years": 10,
         "drainage_sqmi": None, "source_url": "https://x/", "verified_at": "2026-01-01"},
    ]}))
    monkeypatch.setattr(mod, "OUT_PATH", out)
    monkeypatch.setattr(mod, "_fetch_sites", lambda st, r: [
        {"site_no": "22222222", "station_nm": "NEW B", "dec_lat_va": "44.5",
         "dec_long_va": "-69.5", "drain_area_va": "50"}])
    monkeypatch.setattr(mod, "_fetch_flows", lambda ids, r: {"22222222": [250.0]})

    assert mod.build(["ME"], False) == 0
    rows = {r["gage_id"]: r for r in json.loads(out.read_text())["sites"]}
    assert set(rows) == {"11111111", "22222222"}, "California gage was dropped"
    assert rows["22222222"]["name"] == "NEW B", "fetched row should win"
    assert rows["11111111"]["mean_flow_cfs"] == 100.0


def test_a_failed_state_preserves_its_rows_and_reports_nonzero(tmp_path, monkeypatch):
    """A transient NWIS failure must not look like a clean run."""
    mod = _load_builder()
    out = tmp_path / "streamgages.json"
    out.write_text(json.dumps({"sites": [
        {"gage_id": "33333333", "name": "KEEP", "state": "WY", "lat": 43.0,
         "lon": -107.0, "mean_flow_cfs": 300.0, "record_years": 5,
         "drainage_sqmi": None, "source_url": "https://x/", "verified_at": "2026-01-01"}]}))
    monkeypatch.setattr(mod, "OUT_PATH", out)
    monkeypatch.setattr(mod, "_fetch_sites", lambda st, r: [])
    monkeypatch.setattr(mod, "_fetch_flows", lambda ids, r: {})

    assert mod.build(["WY"], False) == 1, "a failed inventory must exit nonzero"
    rows = json.loads(out.read_text())["sites"]
    assert [r["gage_id"] for r in rows] == ["33333333"]


def test_the_radius_cap_is_applied_to_the_exact_distance():
    """PointIndex measures with a local equirectangular projection, and near
    the cap that approximation decides membership. ANIAK AIRWAY & AIR COMM
    (FUDS-F10AK0520) has gage 15304010 at 49.99 mi by haversine, which the
    projection reported as 50.19 — just over the 50 mi cap, so the site
    shipped as having no gage at all. The index's winner is now re-measured
    exactly before the cap is applied.
    """
    from connectors.water_proximity import _haversine_mi, MAX_DISTANCE_MI

    aniak = (61.575431, -159.53038)
    gage_15304010 = (61.89, -158.15444)   # CROOKED C AB AIRPORT RD, per the catalog
    exact = _haversine_mi(*aniak, *gage_15304010)
    assert exact < MAX_DISTANCE_MI, (
        f"the real pair must fall inside the cap, got {exact:.2f} mi")
    assert exact == pytest.approx(50.0, abs=1.0)


def test_ring_budget_grows_with_latitude(connector):
    """A 0.25-degree cell is ~17 mi wide at the equator and ~5.6 mi at 71N, so
    a fixed eight-ring budget stops reaching the 50 mi cap in the far north."""
    from connectors.water_proximity import _rings_for_latitude
    assert _rings_for_latitude(30.0) >= 8
    assert _rings_for_latitude(71.0) > _rings_for_latitude(30.0)


def test_cache_replay_retains_usgs_snapshot_date_and_record_period(tmp_path, monkeypatch):
    mod = _load_builder()
    monkeypatch.setattr(mod, 'OUT_PATH', tmp_path / 'streamgages.json')
    inventory = '# retrieved: 2026-01-02 23:30:00 -04:00\n' + RDB
    inventory = inventory.replace('station_nm\t', 'state_cd\tstation_nm\t').replace('USGS\t04001000\t', 'USGS\t04001000\t26\t').replace('USGS\t04040500\t', 'USGS\t04040500\t26\t')
    stat = ('# retrieved: 2026-01-03 01:00:00 -04:00\n'
            'site_no\tyear_nu\tmean_va\n'
            '04001000\t2001\t10\n04001000\t2010\t30\n'
            '04040500\t2000\t100\n')
    monkeypatch.setattr(mod, '_cached', lambda key, url, refresh: inventory if key.startswith('sites:') else stat)
    assert mod.build(['MI'], False) == 0
    rows = json.loads(mod.OUT_PATH.read_text())['sites']
    row = next(r for r in rows if r['gage_id'] == '04001000')
    assert row['verified_at'] == '2026-01-03'
    assert row['source_retrieved_at'] == '2026-01-03T05:00:00Z'
    assert (row['record_start_year'], row['record_end_year'], row['record_years']) == (2001, 2010, 2)
    assert row['state'] == 'MI'
    assert row['mean_flow_cfs'] == 20


def test_failed_statistics_preserve_prior_region_and_report_incomplete(tmp_path, monkeypatch):
    mod = _load_builder()
    out = tmp_path / 'streamgages.json'
    prior = {'gage_id': '04001000', 'state': 'MI', 'mean_flow_cfs': 77}
    out.write_text(json.dumps({'sites': [prior]}))
    monkeypatch.setattr(mod, 'OUT_PATH', out)
    monkeypatch.setattr(mod, '_cached', lambda key, url, refresh: RDB if key.startswith('sites:') else None)
    assert mod.build(['MI'], False) == 1
    payload = json.loads(out.read_text())
    assert payload['sites'] == [prior]
    assert payload['coverage']['incomplete_regions'] == ['MI']
    assert payload['coverage']['failed_stat_batches'] == 1


def test_successful_region_replacement_retires_old_gages(tmp_path, monkeypatch):
    mod = _load_builder()
    out = tmp_path / 'streamgages.json'
    out.write_text(json.dumps({'sites': [
        {'gage_id': '99999999', 'state': 'MI'}, {'gage_id': '88888888', 'state': 'CA'}]}))
    monkeypatch.setattr(mod, 'OUT_PATH', out)
    monkeypatch.setattr(mod, '_fetch_sites', lambda st, r: [
        {'site_no': '04001000', 'station_nm': 'NEW', 'state_cd': '26',
         'dec_lat_va': '46', 'dec_long_va': '-88'}])
    monkeypatch.setattr(mod, '_fetch_flows', lambda ids, r: {'04001000': [10]})
    assert mod.build(['MI'], False) == 0
    assert {r['gage_id'] for r in json.loads(out.read_text())['sites']} == {'04001000', '88888888'}


def test_request_scope_is_not_geographic_state_and_missing_dates_stay_unknown(tmp_path, monkeypatch):
    mod = _load_builder()
    monkeypatch.setattr(mod, 'OUT_PATH', tmp_path / 'streamgages.json')
    monkeypatch.setattr(mod, '_fetch_sites', lambda st, r: [
        {'site_no': '12355000', 'station_nm': 'CANADA', 'state_cd': '08',
         'country_cd': 'CA', 'dec_lat_va': '49', 'dec_long_va': '-114'}])
    monkeypatch.setattr(mod, '_fetch_flows', lambda ids, r: {'12355000': [10]})
    assert mod.build(['AK'], False) == 0
    row = json.loads(mod.OUT_PATH.read_text())['sites'][0]
    assert row.get('state') is None
    assert row['requested_region'] == 'AK'
    assert row.get('verified_at') is None


def test_unsupported_region_is_not_negative_water_evidence(connector, monkeypatch):
    monkeypatch.setattr(connector, '_load_sites', lambda: iter([
        {'id': 'VI1', 'program': 'fuds', 'lat': 46.5, 'lon': -88.7, 'state': 'VI'}]))
    row = connector.fetch_records(argparse.Namespace(limit=None), True)[0]
    assert row['water_evidence_status'] == 'unsupported_region'
    assert 'water_flow_cfs' not in row


def test_join_carries_statistic_period_and_snapshot(connector):
    path = connector._data_dir() / 'streamgages.json'
    payload = json.loads(path.read_text())
    payload['sites'][0].update(record_years=3, record_start_year=2000, record_end_year=2002,
                              source_retrieved_at='2026-01-02T00:00:00Z',
                              source_url='https://waterdata.usgs.gov/monitoring-location/USGS-04040500/')
    path.write_text(json.dumps(payload))
    row = connector.fetch_records(argparse.Namespace(limit=None), True)[0]
    assert connector.source_metadata['statistic'] == 'mean_of_annual_means'
    metadata = connector.source_metadata['gages_by_id'][row['water_gage_id']]
    assert row['water_evidence_status'] == 'matched_context'
    assert metadata['water_gage_record_years'] == 3
    assert metadata['water_gage_record_end_year'] == 2002
    assert metadata['water_gage_source_retrieved_at'] == '2026-01-02T00:00:00Z'


def test_signed_annual_flows_and_duplicate_years_are_preserved(monkeypatch):
    mod = _load_builder()
    # Reversing/tidal flows can be negative. Dropping them inflates the mean.
    rdb = 'site_no\tyear_nu\tmean_va\n04001000\t2000\t-10\n04001000\t2000\t-10\n04001000\t2001\t30\n'
    monkeypatch.setattr(mod, '_cached', lambda *a: rdb)
    values = mod._fetch_flows(['04001000'], False)['04001000']
    assert values == [-10, 30]
    assert mod._FLOW_METADATA['04001000']['record_start_year'] == 2000


def test_cache_only_never_requests_missing_snapshot(tmp_path, monkeypatch):
    mod = _load_builder()
    monkeypatch.setattr(mod, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(mod, '_CACHE_ONLY', True)
    def unexpected_get(url):
        raise AssertionError('cache-only accessed the network')
    monkeypatch.setattr(mod, '_get', unexpected_get)
    assert mod._cached('missing', 'https://example.org/', False) is None


def test_invalid_inventory_geometry_preserves_prior_scope(tmp_path, monkeypatch):
    mod = _load_builder()
    out = tmp_path / 'streamgages.json'
    prior = {'gage_id': '04001000', 'state': 'MI'}
    out.write_text(json.dumps({'sites': [prior]}))
    monkeypatch.setattr(mod, 'OUT_PATH', out)
    monkeypatch.setattr(mod, '_fetch_sites', lambda st, r: [
        {'site_no': '04001000', 'dec_lat_va': 'NaN', 'dec_long_va': '-88'}])
    monkeypatch.setattr(mod, '_fetch_flows', lambda *a: {})
    assert mod.build(['MI'], False) == 1
    assert json.loads(out.read_text())['sites'] == [prior]


def test_missing_only_keeps_shared_gage_provenance_when_all_ids_exist(connector, monkeypatch):
    monkeypatch.setattr(connector, 'existing_ids', lambda: {'A1', 'A2', 'A3'})
    monkeypatch.setattr(connector, 'existing_records', lambda: [{'id': 'A1', 'program': 'superfund'}])
    result = connector.fetch_records(argparse.Namespace(limit=None, missing_only=True), True)
    assert result
    assert '04040500' in connector.source_metadata['gages_by_id']
