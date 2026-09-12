#!/usr/bin/env python3
"""Record coordinate changes and invalidate geographic joins not recomputed.

Run after source promotion, with retained pre-refresh producer snapshots:
  python3 scripts/build_evidence_invalidations.py --before-dir /path/to/snapshots

The manifest preserves every exact coordinate change. Changes at or below one
meter are treated as serialization precision only; larger changes require a
rebuilt join or an explicit unknown. This does not certify coordinate accuracy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE_M = 1.0
CORE = ('superfund-npl', 'dod-fuds')
REBUILT = ('infra-proximity', 'water-proximity', 'eia-retired-plants', 'planned-retirements-proximity', 'nickel-anchor-proximity')
STALE = ('port-proximity', 'opportunity-zone',
         'ira-energy-community', 'fema-nri', 'climate-zone', 'iso-rto',
         'parcel-owner', 'coord-quality', 'tribal-areas', 'coal-conversions-proximity',
         'ai-summary')
ID_JOINS = ('epa-redev', 'epa-superfund-docs', 'epa-echo', 'epa-acres-cleanup')
# Only fields actually assigned by each frontend join. Payload identity/context
# fields must never erase authoritative producer values.
OWNED_FIELDS = {
    'infra-proximity': 'transmission_mi transmission_kv substation_mi substation_kv gas_pipeline_mi rail_mi highway_mi power_plant_mi power_plant_mw power_plant_fuel flood_zone in_sfha infra_evidence',
    'water-proximity': 'water_gage_mi water_flow_cfs water_gage_name water_gage_id water_evidence_status water_statistic water_gage_record_years water_gage_record_start_year water_gage_record_end_year water_gage_source_retrieved_at water_gage_source_url',
    'eia-retired-plants': 'retired_plant_mi retired_plant_mw retired_plant_fuel retired_plant_year retired_plant_name',
    'planned-retirements-proximity': 'planned_retirement_mi planned_retirement_mw planned_retirement_fuel planned_retirement_year planned_retirement_name',
    'port-proximity': 'port_hurricane_freq port_mi port_name port_type shipyard_capability shipyard_mi shipyard_name',
    'nickel-anchor-proximity': 'nickel_acid_mi nickel_acid_id nickel_anchor_kind nickel_anchor_mi nickel_anchor_name nickel_demand_mi nickel_demand_id nickel_feedstock_mi nickel_feedstock_id',
    'opportunity-zone': 'in_opportunity_zone oz_rural oz_tract_geoid',
    'ira-energy-community': 'energy_community_detail energy_community_type in_energy_community',
    'fema-nri': 'nri_drought_rating nri_heatwave_rating nri_risk_rating nri_risk_score nri_wildfire_rating',
    'climate-zone': 'climate_zone',
    'iso-rto': 'iso_rto',
    'parcel-owner': 'current_owner current_owner_source parcel_acreage parcel_id',
    'coord-quality': 'coord_flags coord_actual_state coord_state_gap_mi coord_shared_count',
    'tribal-areas': 'in_aiannha_area aiannha_area_count aiannha_areas',
    'coal-conversions-proximity': 'coal_conversion_plant_name coal_conversion_plant_mi coal_conversion_mw coal_conversion_switchyard_kv coal_conversion_rail coal_conversion_water coal_conversion_stranded_val_usd coal_conversion_queue_fasttrack',
    'ai-summary': 'summary summary_meta',
}


def distance_m(before: dict, after: dict) -> float:
    """Spherical distance adequate for a one-meter serialization tolerance."""
    lat1, lat2 = math.radians(before['lat']), math.radians(after['lat'])
    dlat = lat2-lat1
    dlon = math.radians(after['lon']-before['lon'])
    value = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371008.8 * 2 * math.asin(min(1.0, math.sqrt(value)))


def build(before_dir: Path, data_dir: Path, rebuilt: tuple[str, ...] = REBUILT) -> dict:
    """Build deterministic dependencies and coordinate changes; do not write."""
    catalog = {}
    for slug in (*REBUILT, *STALE, *ID_JOINS):
        path = data_dir / f'{slug}.json'
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        fields = sorted(OWNED_FIELDS.get(slug, '').split())
        catalog[path.name] = {
            'artifact': path.name,
            'source': payload.get('source'),
            'source_url': payload.get('source_url'),
            'generated_at': payload.get('generated_at'),
            'fields': fields,
            'status': 'rebuilt' if slug in rebuilt else ('unchanged_id_join' if slug in ID_JOINS else 'invalidate'),
        }
    by_id = {}
    snapshots = {}
    for slug in CORE:
        prior = json.loads((before_dir / f'{slug}-prior.json').read_text())
        current = json.loads((data_dir / f'{slug}.json').read_text())
        snapshots[slug] = {'before_generated_at': prior.get('generated_at'),
                           'after_generated_at': current.get('generated_at'),
                           'source_url': current.get('source_url'),
                           'before_sha256': hashlib.sha256((before_dir / f'{slug}-prior.json').read_bytes()).hexdigest(),
                           'after_sha256': hashlib.sha256((data_dir / f'{slug}.json').read_bytes()).hexdigest()}
        previous = {r['id']: r for r in prior['sites']}
        for row in current['sites']:
            old = previous.get(row['id'])
            if not old or (old['lat'], old['lon']) == (row['lat'], row['lon']):
                continue
            moved = distance_m(old, row)
            invalidate = moved > TOLERANCE_M
            deps = []
            clear = set()
            for artifact, dep in catalog.items():
                status = dep['status'] if invalidate else 'within_serialization_tolerance'
                fields = dep['fields'] if status == 'invalidate' else []
                deps.append({'artifact': artifact, 'status': status, 'fields': fields})
                clear.update(fields)
                # Grid geometry was rebuilt, but cached FEMA point lookups were
                # explicitly preserved. They cannot follow a moved coordinate.
                if invalidate and artifact == 'infra-proximity.json' and status == 'rebuilt':
                    flood_fields = ['flood_zone', 'in_sfha']
                    deps.append({'artifact': artifact, 'component': 'flood',
                                 'status': 'invalidate', 'fields': flood_fields})
                    clear.update(flood_fields)
            by_id[row['id']] = {
                'before': {'lat': old['lat'], 'lon': old['lon']},
                'after': {'lat': row['lat'], 'lon': row['lon']},
                'distance_m': round(moved, 4),
                'invalidate': invalidate,
                'reason': ('Core source coordinate changed by more than 1 m. Geographic joins not rebuilt at the new coordinate remain unassessed.'
                           if invalidate else 'Coordinate change within documented 1 m serialization tolerance; existing geographic context retained.'),
                'dependencies': deps,
                'clear_fields': sorted(clear),
                'restore_core_fields': {key: row.get(key) for key in ('current_owner', 'current_owner_source') if key in clear},
            }
    return {
        'schema_version': 1,
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'source': 'Comparison of retained pre-refresh producer snapshots with refreshed EPA/USACE core records',
        'coordinate_tolerance_m': TOLERANCE_M,
        'tolerance_basis': 'At most 1 m treated as serialization precision; not a statement of coordinate accuracy.',
        'source_snapshots': snapshots,
        'dependency_catalog': catalog,
        'count': len(by_id),
        'invalidated_count': sum(r['invalidate'] for r in by_id.values()),
        'by_id': dict(sorted(by_id.items())),
    }


def annotate_stale_sources(manifest: dict, data_dir: Path) -> dict[str, int]:
    """Disclose pending joins to raw consumers without relabeling source dates."""
    pending: dict[str, dict[str, list[str]]] = {}
    for sid, change in manifest['by_id'].items():
        for dep in change['dependencies']:
            if dep['status'] == 'invalidate':
                pending.setdefault(dep['artifact'], {})[sid] = dep['fields']
    counts = {}
    for artifact, dependency in manifest.get('dependency_catalog', {}).items():
        if dependency['status'] != 'rebuilt' or artifact in pending:
            continue  # A rebuilt grid file can still carry historical flood results.
        path = data_dir / artifact
        payload = json.loads(path.read_text())
        metadata = dict(payload.get('source_metadata') or {})
        for key in ('coordinate_invalidation_manifest', 'coordinate_updates_pending',
                    'coordinate_pending_fields', 'coordinate_evidence_note'):
            metadata.pop(key, None)
        if metadata != (payload.get('source_metadata') or {}):
            payload['source_metadata'] = metadata
            path.write_text(json.dumps(payload, separators=(',', ':')))
    for artifact, candidates in pending.items():
        path = data_dir / artifact
        payload = json.loads(path.read_text())
        present = {r.get('id') for r in payload.get('sites', payload.get('matches', []))}
        ids = sorted(present & candidates.keys())
        if not ids:
            continue
        metadata = dict(payload.get('source_metadata') or {})
        metadata.update(
            coordinate_invalidation_manifest='evidence-invalidations.json',
            coordinate_updates_pending=ids,
            coordinate_pending_fields=sorted({field for sid in ids for field in candidates[sid]}),
            coordinate_evidence_note='Retained historical rows for these IDs were joined at earlier coordinates. Listed fields are unassessed at the refreshed coordinates; consult the invalidation manifest before reuse.',
        )
        if metadata != payload.get('source_metadata'):
            payload['source_metadata'] = metadata
            path.write_text(json.dumps(payload, separators=(',', ':')))
        counts[artifact] = len(ids)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-dir', required=True, type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'docs/data')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/data/evidence-invalidations.json')
    parser.add_argument('--rebuilt', default=','.join(REBUILT), help='Only joins actually recomputed at current coordinates.')
    parser.add_argument('--annotate-sources', action='store_true', help='Add pending-coordinate disclosures to affected retained artifacts without changing their dates.')
    args = parser.parse_args()
    payload = build(args.before_dir, args.data_dir, tuple(filter(None, args.rebuilt.split(','))))
    args.output.write_text(json.dumps(payload, separators=(',', ':')))
    if args.annotate_sources:
        annotate_stale_sources(payload, args.data_dir)
    logging.basicConfig(level=logging.INFO)
    logging.info('Recorded %d coordinate changes; %d require invalidation', payload['count'], payload['invalidated_count'])


if __name__ == '__main__':
    main()
