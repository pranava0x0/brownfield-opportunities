"""Universal infrastructure-proximity enrichment.

Computes nearest-distance to seven layers of infrastructure relevant to data-
center and energy-infrastructure siting from every site we already know about
(Superfund, ACRES, FUDS, BRAC), so the DC thesis ("post-remediation industrial
land + grid + rail + road + behind-the-meter gas = AI siting target") works
for ~47k records, not just the ~1.9k that EPA's Redevelopment mapper covers.

Sources (all public, no auth):
- **Transmission lines**: HIFLD `Electric_Power_Transmission_Lines`
  (~52k polyline features, includes voltage where reported).
- **Rail**: US Census TIGERweb Railroads (~112k features).
- **Highways**: US Census TIGERweb Primary Roads (~17k features, MTFCC=S1100,
  i.e. Interstates + US/state routes that meet primary-road criteria).
- **Natural gas pipelines**: HIFLD `Natural Gas Interstate and Intrastate
  Pipelines (EIA)` — ~33k polylines spanning interstate + intrastate +
  gathering. <2 mi to a major line enables behind-the-meter gas-turbine
  viability.
- **Substations**: OpenStreetMap `power=substation` via Overpass API,
  CONUS-chunked. ~80-100k features nationwide. A 500 kV transmission line
  half a mile away is only actionable if a substation is close enough to
  interconnect; this layer is the missing half of the transmission signal.
- **Power plants**: HIFLD `Power_Plants_in_the_US` (EIA-860 sourced, ~13k
  points). Co-location with existing generation = PPA / behind-the-meter
  candidate + demonstrated local grid capacity.
- **Flood zone**: FEMA NFHL `Flood Hazard Zones` layer 28, queried per-site
  via ArcGIS `query` operation (one HTTP call per site; the underlying ~12M
  polygons are too many to pre-index in memory). Returns the FEMA zone code
  (`A`, `AE`, `X`, `V`, etc.) and the boolean SFHA flag (Special Flood
  Hazard Area = 100-yr floodplain). A site in an SFHA is a permitting
  screen-out for critical infrastructure.

This is an *enrichment-only* connector — it doesn't add new sites. It reads
the per-program JSON files written by the producer connectors and writes a
compact lookup file. The frontend lazy-loads it after first paint and joins
onto `sitesById` by `id`.

Performance:
- The four polyline + two point layers fetch in ~3 min on a cold run; cached
  on disk thereafter, so subsequent re-runs are seconds.
- Pure-Python grid index in `connectors.spatial` — no shapely/rtree.
- Flood zone is the slow one: per-site FEMA REST query at 1.5s/site → ~20h
  for a full 47k-site nationwide run. Cache makes incremental runs cheap.
  Use `--infra-skip-flood-zone` to iterate quickly without paying the cost.
- Distances >100 mi are dropped (treated as out-of-CONUS) to keep the
  enrichment file lean.

CLI:
    python refresh.py --source infra-proximity            # enrichment-only run
    python refresh.py --all                               # part of the full refresh
    python refresh.py --source infra-proximity --infra-skip-rail   # subset
    python refresh.py --source infra-proximity --infra-skip-flood-zone  # skip the slow one
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

import requests

from connectors.base import Connector
from connectors.spatial import PointIndex, SegmentIndex

log = logging.getLogger("connector.infra_proximity")

# Hard cap on a useful distance. Past this we drop the field rather than
# carry a misleadingly precise huge number — many AK/HI sites are 500+ mi
# from any rail or transmission line and that's not a usable signal.
MAX_DISTANCE_MI = 100.0

# ---- Source definitions ---------------------------------------------------

TRANSMISSION_QUERY_URL = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Power_Transmission_Lines/FeatureServer/0/query"
)

# Census TIGERweb — Primary Roads (MTFCC=S1100 == Interstates + major US/state
# routes that meet "primary road" classification).
HIGHWAY_QUERY_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Transportation/MapServer/2/query"
)

RAIL_QUERY_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Transportation/MapServer/9/query"
)

# HIFLD natural-gas interstate + intrastate + gathering pipelines, EIA-sourced.
# ~32.9k polylines. The legacy `gii.dhs.gov/HIFLD` portal shut down 2025-08-26;
# the canonical service moved to `services2.arcgis.com/FiaPA4ga0iQKduv3`.
# Distinct from "Natural Gas Liquid Pipelines" which carries NGLs (propane,
# ethane), not methane — DC siting cares about methane for behind-the-meter
# turbines (Stargate Texas pattern), so we only ingest the methane layer.
GAS_PIPELINE_QUERY_URL = (
    "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/"
    "Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer/0/query"
)

# Layer-specific page size. HIFLD caps at 2000. TIGERweb advertises
# maxRecordCount=100000, but the actual response-payload limit with geometry
# kicks in well before that (10k pages return HTTP 500). 1000 is the largest
# safe page for TIGER polylines.
#
# Per-layer `out_fields`: HIFLD's transmission layer carries `VOLTAGE`
# (Double, kV) and `VOLT_CLASS` (String, e.g. "230"). Capturing these lets
# the `transmission_kv` enrichment field flow through to the frontend so
# the data-center scorer can apply the ≥230 kV hyperscale rule. Rail,
# highway, and gas pipelines don't need attributes — geometry-only for v0.
# (Future iteration could carry `TYPEPIPE` to distinguish interstate vs
# gathering, but the distance-only signal is already actionable.)
LAYERS: dict[str, dict[str, Any]] = {
    "transmission": {
        "url": TRANSMISSION_QUERY_URL,
        "page_size": 2000,
        "where": "1=1",
        "out_fields": "VOLTAGE,VOLT_CLASS",
        "label": "HIFLD Electric Power Transmission Lines",
    },
    "highway": {
        "url": HIGHWAY_QUERY_URL,
        "page_size": 1000,
        "where": "MTFCC='S1100'",
        "out_fields": "",
        "label": "US Census TIGERweb Primary Roads (Interstates + Major US/State)",
    },
    "rail": {
        "url": RAIL_QUERY_URL,
        "page_size": 1000,
        "where": "1=1",
        "out_fields": "",
        "label": "US Census TIGERweb Railroads",
    },
    "gas_pipeline": {
        "url": GAS_PIPELINE_QUERY_URL,
        "page_size": 2000,
        "where": "1=1",
        "out_fields": "",
        "label": "HIFLD Natural Gas Interstate + Intrastate Pipelines (EIA)",
    },
}

# HIFLD null sentinel for missing voltage; ~12% of segments. Treat as null
# so downstream consumers don't see "−999999 kV" anywhere.
TRANSMISSION_NULL_KV = -999999.0
# Map of HIFLD `VOLT_CLASS` strings to representative kV for the cases
# where `VOLTAGE` is null but `VOLT_CLASS` is populated. Conservative —
# we pick the lower bound of each class so the ≥230kV filter is strict.
VOLT_CLASS_TO_KV: dict[str, float] = {
    "UNDER 100": 69.0,
    "100-161": 100.0,
    "220-287": 220.0,
    "345": 345.0,
    "500": 500.0,
    "735 AND ABOVE": 735.0,
    "DC": 500.0,  # HVDC ties — typically ≥500kV; conservative.
}

# Sites whose JSON we'll enrich. Order doesn't matter — each record carries
# its own `id` and `program`. Missing files are skipped (e.g. a partial run).
PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]

# Field on each enriched record per layer. Must match SiteRecord schema.
DISTANCE_FIELD: dict[str, str] = {
    "transmission": "transmission_mi",
    "highway": "highway_mi",
    "rail": "rail_mi",
    "gas_pipeline": "gas_pipeline_mi",
    "substation": "substation_mi",
    "power_plant": "power_plant_mi",
}

# ---- Point layers (substations + power plants) ----

# HIFLD Power Plants (EIA-860 sourced). Public, paginated like transmission.
POWER_PLANT_QUERY_URL = (
    "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/"
    "Power_Plants_in_the_US/FeatureServer/0/query"
)

# CONUS bounding-box chunks for the Overpass substation pull. The Overpass
# API rate-limits + payload-caps large queries, so we split the US into
# regions. South + Florida have higher substation density; we keep them as
# their own chunks to avoid timeouts. Format: (south, west, north, east).
OVERPASS_SUBSTATION_BBOXES: list[tuple[float, float, float, float]] = [
    # CONUS quadrants — 38°N + 100°W splits at roughly Kansas City.
    (38.0, -125.0, 50.0, -100.0),   # CONUS-NW
    (38.0, -100.0, 50.0,  -65.0),   # CONUS-NE (high density: NYC-Boston corridor)
    (24.0, -125.0, 38.0, -100.0),   # CONUS-SW
    (24.0, -100.0, 38.0,  -65.0),   # CONUS-SE
    # Alaska — large area but very sparse infra; one chunk fine.
    (50.0, -180.0, 72.0, -130.0),
    # Hawaii.
    (17.0, -162.0, 23.0, -154.0),
    # Puerto Rico + USVI.
    (17.0,  -68.0, 19.0,  -64.0),
]

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_S = 180  # Overpass server-side query timeout

# OSM voltage tag is in volts. Multi-value tags use `;` separator
# (e.g. "230000;115000"). We take the highest value.
def _parse_osm_voltage(raw: object) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    best: float | None = None
    for part in s.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            v = float(part)
        except ValueError:
            continue
        if v <= 0:
            continue
        # Convert volts → kV.
        kv = v / 1000.0
        if best is None or kv > best:
            best = kv
    return best


# ---- Flood-zone (per-site) ----

# FEMA NFHL Layer 28 = Flood Hazard Zones (polygon).
FLOOD_QUERY_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/"
    "28/query"
)
# HTTP codes we treat as transient — log + continue rather than abort the
# whole multi-hour batch. FEMA's service is occasionally slow / 500s.
FLOOD_TRANSIENT_HTTP_CODES = {404, 408, 429, 500, 502, 503, 504}


def _flood_cache_key(lat: float, lon: float) -> dict[str, Any]:
    """Cache key for a per-site FEMA flood-zone query.

    Single source of truth shared by `_query_flood_zone` (the fetch) and the
    `--infra-flood-budget` gate (the "is this already cached?" check) so the
    two never drift. Keyed per (lat, lon) rounded to 5 decimals (~1 m — far
    finer than FEMA polygon edges).
    """
    return {
        "src": "fema_flood",
        "lat": round(float(lat), 5),
        "lon": round(float(lon), 5),
    }


class InfraProximity(Connector):
    slug = "infra-proximity"
    source_label = "HIFLD + Census TIGER (transmission, rail, highways, gas pipelines)"
    source_url = "https://hifld-geoplatform.opendata.arcgis.com/"

    # Run AFTER all producer connectors have written their per-source JSON.
    # See refresh.py — connectors with a higher run_order run later in --all.
    run_order = 300

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument(
                "--limit",
                type=int,
                default=None,
                help="Cap the number of records to enrich (default: unlimited).",
            )
        # Per-layer skip toggles for fast iteration during development. All
        # seven layers (4 polyline + 2 point + 1 per-site polygon) accept
        # `--infra-skip-<layer_name>`, matching the existing convention.
        all_layers = list(LAYERS.keys()) + ["substation", "power_plant", "flood_zone"]
        for layer in all_layers:
            p.add_argument(
                f"--infra-skip-{layer}",
                dest=f"infra_skip_{layer}",
                action="store_true",
                default=False,
                help=f"Skip the {layer} layer (no related fields emitted).",
            )
        if "infra_flood_budget" not in existing:
            p.add_argument(
                "--infra-flood-budget",
                dest="infra_flood_budget",
                type=int,
                default=0,
                help="Cap the number of NEW per-site FEMA flood-zone fetches "
                     "this run (0 = unlimited). The flood layer is the slow one "
                     "(~1.5s/site, ~15h for the full 47k). With a budget, a run "
                     "tops up the cache by N fetches then writes the full record "
                     "set — prior flood values are seeded from the existing "
                     "docs/data/infra-proximity.json so progress is never lost. "
                     "Cached sites and already-populated sites don't consume "
                     "budget. Use this for resumable checkpointed backfills.",
            )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        sites = list(self._load_sites())
        if not sites:
            log.error(
                "no per-program JSON files found in %s — run --all (or each "
                "producer connector individually) before --source infra-proximity",
                self._data_dir(),
            )
            return []
        log.info("loaded %d sites across %d program files",
                 len(sites), self._loaded_program_count)

        # `--missing-only`: drop sites already enriched in the existing output.
        # The connector emits a record per site (even when every layer is out
        # of range — see the tombstone comment in the loop below), so "id in
        # existing output" is the exact predicate for "we already tried this
        # one." Useful when the producer connectors added new sites since the
        # last infra-proximity run.
        missing_only = bool(getattr(args, "missing_only", False))
        if missing_only:
            covered = self.existing_ids()
            if covered:
                before = len(sites)
                sites = [s for s in sites if s.get("id") not in covered]
                log.info("--missing-only: %d/%d sites already covered, %d remaining",
                         before - len(sites), before, len(sites))
            # No new sites to enrich → skip the ~6-minute index build entirely.
            if not sites:
                existing = self.existing_records()
                log.info("--missing-only: nothing to fetch; returning %d existing records",
                         len(existing))
                return existing

        # Build one SegmentIndex per polyline layer.
        seg_indexes: dict[str, SegmentIndex] = {}
        for layer, cfg in LAYERS.items():
            if getattr(args, f"infra_skip_{layer}", False):
                log.info("skipping layer %s per --infra-skip-%s", layer, layer)
                continue
            idx = self._build_index(layer, cfg, use_cache=use_cache)
            if idx.segment_count == 0:
                log.warning(
                    "[%s] index empty after fetch — distance field will be "
                    "absent from all records", layer,
                )
                continue
            seg_indexes[layer] = idx

        # Build a PointIndex per point layer (substation, power plant).
        point_indexes: dict[str, PointIndex] = {}
        if not getattr(args, "infra_skip_substation", False):
            sub_idx = self._build_substation_index(use_cache=use_cache)
            if sub_idx.point_count:
                point_indexes["substation"] = sub_idx
        else:
            log.info("skipping layer substation per --infra-skip-substation")
        if not getattr(args, "infra_skip_power_plant", False):
            pp_idx = self._build_power_plant_index(use_cache=use_cache)
            if pp_idx.point_count:
                point_indexes["power_plant"] = pp_idx
        else:
            log.info("skipping layer power_plant per --infra-skip-power_plant")

        # Per-site flood-zone is opt-in via flag presence — the slow one.
        do_flood = not getattr(args, "infra_skip_flood_zone", False)
        if not do_flood:
            log.info("skipping layer flood_zone per --infra-skip-flood_zone")

        if not seg_indexes and not point_indexes and not do_flood:
            log.error("no infrastructure layers built — aborting enrichment")
            return []

        # Seed prior flood-zone results from the existing on-disk output so a
        # budgeted/partial run never loses progress: every `rec` is rebuilt
        # fresh from the spatial indexes each pass, so without this seed an
        # interrupted flood backfill would re-null the sites it populated last
        # run. We only seed sites that already carry a flood field — sites with
        # null flood are left for retry. Cheap (one file read) and a no-op on a
        # cold cache (no existing file → empty seed).
        flood_seed: dict[str, tuple[str | None, bool | None]] = {}
        flood_budget = int(getattr(args, "infra_flood_budget", 0) or 0)
        if do_flood:
            for prev in self.existing_records():
                pid = prev.get("id")
                if pid is None:
                    continue
                fz = prev.get("flood_zone")
                sf = prev.get("in_sfha")
                if fz is not None or sf is not None:
                    flood_seed[pid] = (fz, sf)
            log.info("[flood_zone] seeded %d sites from existing output%s",
                     len(flood_seed),
                     f", new-fetch budget={flood_budget}" if flood_budget else "")

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        out_of_range: dict[str, int] = {
            **{layer: 0 for layer in seg_indexes},
            **{layer: 0 for layer in point_indexes},
        }
        flood_lookups = 0
        flood_in_sfha = 0
        flood_skipped = 0
        flood_seeded = 0
        flood_fetches = 0          # actual NEW fetches (cache misses) this run
        flood_budget_skipped = 0   # sites left unqueried because budget ran out
        # Per-program counts for telemetry.
        program_counts: dict[str, int] = {}
        for site in sites:
            sid = site.get("id")
            program = site.get("program")
            lat = site.get("lat")
            lon = site.get("lon")
            if not sid or not program or lat is None or lon is None:
                skipped_no_geom += 1
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                skipped_no_geom += 1
                continue
            rec: dict[str, Any] = {"id": sid, "program": program}

            # ---- polyline layers ----
            for layer, idx in seg_indexes.items():
                if layer == "transmission":
                    hit = idx.nearest_with_attr(lat_f, lon_f)
                    if hit is None:
                        out_of_range[layer] += 1
                        continue
                    d, kv = hit
                    if d > MAX_DISTANCE_MI:
                        out_of_range[layer] += 1
                        continue
                    rec[DISTANCE_FIELD[layer]] = round(d, 1)
                    if kv is not None:
                        rec["transmission_kv"] = round(float(kv), 1)
                else:
                    d = idx.nearest_distance_mi(lat_f, lon_f)
                    if d is None or d > MAX_DISTANCE_MI:
                        out_of_range[layer] += 1
                        continue
                    rec[DISTANCE_FIELD[layer]] = round(d, 1)

            # ---- point layers (substation + power plant) ----
            for layer, pidx in point_indexes.items():
                hit = pidx.nearest_with_attr(lat_f, lon_f)
                if hit is None:
                    out_of_range[layer] += 1
                    continue
                d, attr = hit
                if d > MAX_DISTANCE_MI:
                    out_of_range[layer] += 1
                    continue
                rec[DISTANCE_FIELD[layer]] = round(d, 1)
                if isinstance(attr, dict):
                    if layer == "substation" and attr.get("kv") is not None:
                        rec["substation_kv"] = round(float(attr["kv"]), 1)
                    elif layer == "power_plant":
                        if attr.get("mw") is not None:
                            rec["power_plant_mw"] = round(float(attr["mw"]), 1)
                        if attr.get("fuel"):
                            rec["power_plant_fuel"] = str(attr["fuel"])
                        # HIFLD Status: RE/OA/OS = retired; OP/SB = operating.
                        # None when older cache lacks the field — emit nothing
                        # so callers distinguish "no" from "unknown."
                        status = attr.get("status")
                        if status is not None:
                            rec["power_plant_retired"] = str(status).upper() in {
                                "RE", "OA", "OS"
                            }

            # ---- per-site flood zone ----
            if do_flood:
                seeded = flood_seed.get(sid)
                if seeded is not None:
                    # Already populated in a prior run — carry it forward
                    # verbatim, no query (the FEMA answer for a fixed lat/lon
                    # doesn't change between runs).
                    s_fz, s_sfha = seeded
                    if s_fz is not None:
                        rec["flood_zone"] = s_fz
                    if s_sfha is not None:
                        rec["in_sfha"] = s_sfha
                        if s_sfha:
                            flood_in_sfha += 1
                    flood_seeded += 1
                else:
                    cache_exists = self.cache_path(
                        _flood_cache_key(lat_f, lon_f)
                    ).exists()
                    # Free when cached; otherwise gated by the new-fetch budget
                    # (0 = unlimited). Cache hits never consume budget.
                    if cache_exists or flood_budget == 0 or flood_fetches < flood_budget:
                        try:
                            fz, sfha = self._query_flood_zone(lat_f, lon_f, use_cache=use_cache)
                            if not cache_exists:
                                flood_fetches += 1
                            flood_lookups += 1
                            if fz is not None:
                                rec["flood_zone"] = fz
                            if sfha is not None:
                                rec["in_sfha"] = sfha
                                if sfha:
                                    flood_in_sfha += 1
                        except (requests.ConnectionError, requests.Timeout) as e:
                            log.warning("[%s] FEMA NFHL network error: %s — skipping flood field",
                                        sid, type(e).__name__)
                            flood_skipped += 1
                        except requests.HTTPError as e:
                            code = e.response.status_code if e.response is not None else None
                            if code in FLOOD_TRANSIENT_HTTP_CODES:
                                log.warning("[%s] FEMA NFHL HTTP %s — skipping flood field",
                                            sid, code)
                                flood_skipped += 1
                            else:
                                raise
                    else:
                        flood_budget_skipped += 1

            # Always emit the record — even when every layer is out-of-range —
            # so the file's `id` set is the cross-program join key, and the
            # frontend can distinguish "this site has no infra within reach"
            # (record present, fields absent) from "enrichment never ran for
            # this id" (record absent). Pre-2026-05 we dropped the record on
            # all-out-of-range; that silently hid 542 sites (mostly off-grid
            # AK + Pacific territories, where HIFLD has no transmission
            # coverage at all and TIGER primary-road / rail are sparse).
            records.append(rec)
            program_counts[program] = program_counts.get(program, 0) + 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        for layer, n in out_of_range.items():
            log.info("[%s] %d sites had no feature within %d mi",
                     layer, n, int(MAX_DISTANCE_MI))
        if do_flood:
            log.info("[flood_zone] %d seeded, %d lookups (%d new fetches, %d in SFHA, "
                     "%d skipped on network errors, %d deferred over budget)",
                     flood_seeded, flood_lookups, flood_fetches, flood_in_sfha,
                     flood_skipped, flood_budget_skipped)
        log.info("enriched %d records — by program: %s",
                 len(records), program_counts)

        if getattr(args, "limit", None):
            records = records[: args.limit]

        # In `--missing-only` mode, merge the new delta with what's on disk
        # so the file write doesn't truncate previously-enriched records.
        if missing_only:
            existing = self.existing_records()
            merged = self.merge_records_by_id(records, existing)
            log.info("--missing-only: merged %d new + %d existing = %d total",
                     len(records), len(existing), len(merged))
            return merged
        return records

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _data_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "docs" / "data"

    def _load_sites(self) -> Iterable[dict[str, Any]]:
        """Iterate sites across all per-program JSON files that exist on disk."""
        self._loaded_program_count = 0
        for fname in PROGRAM_FILES:
            path = self._data_dir() / fname
            if not path.exists():
                log.info("program file %s missing — skipping", fname)
                continue
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as e:
                log.warning("failed to read %s: %s — skipping", fname, e)
                continue
            for site in payload.get("sites") or []:
                yield site
            self._loaded_program_count += 1

    def _build_index(
        self,
        layer: str,
        cfg: dict[str, Any],
        use_cache: bool,
    ) -> SegmentIndex:
        """Fetch all polyline features for a layer and build a spatial index."""
        log.info("[%s] fetching from %s", layer, cfg["url"])
        idx = SegmentIndex()
        polylines_added = 0
        offset = 0
        page_size = cfg["page_size"]
        out_fields = cfg.get("out_fields", "") or ""
        kv_features = 0  # telemetry: how many transmission features carry kV
        while True:
            params = {
                "where": cfg["where"],
                "outFields": out_fields,
                "returnGeometry": "true",
                "outSR": "4326",
                "geometryPrecision": "5",
                "resultRecordCount": str(page_size),
                "resultOffset": str(offset),
                "f": "json",
            }
            data = self.http_get_json(
                cfg["url"], params,
                use_cache=use_cache,
                # Include `out_fields` in the cache key so the v1.10 cache
                # (which fetched no attributes) doesn't shadow the v1.12
                # transmission fetch that needs VOLTAGE / VOLT_CLASS.
                cache_key={
                    "layer": layer,
                    "offset": offset,
                    "where": cfg["where"],
                    "out_fields": out_fields,
                },
            )
            features = data.get("features") or []
            log.info("[%s] page offset=%d got=%d", layer, offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                # ESRI polyline: { "paths": [[[lon, lat], ...], ...] }
                paths = geom.get("paths") or []
                attr = self._extract_attr(layer, feat.get("attributes") or {})
                if layer == "transmission" and attr is not None:
                    kv_features += 1
                for path in paths:
                    added = idx.add_polyline(path, attr=attr)
                    if added > 0:
                        polylines_added += 1
            if len(features) < page_size:
                break
            offset += page_size
        if layer == "transmission":
            log.info("[transmission] %d / %d polylines carry kV",
                     kv_features, polylines_added)
        log.info("[%s] indexed %d polylines / %d segments",
                 layer, polylines_added, idx.segment_count)
        return idx

    @staticmethod
    def _extract_attr(layer: str, attrs: dict[str, Any]) -> float | None:
        """Pull the per-feature attribute we want carried on the segment.

        For transmission: prefer `VOLTAGE` (Double, kV); fall back to
        `VOLT_CLASS` mapped via `VOLT_CLASS_TO_KV`. Sentinel value
        `-999999` (HIFLD's null marker) collapses to None.

        Returns None for layers that don't carry attributes.
        """
        if layer != "transmission":
            return None
        v = attrs.get("VOLTAGE")
        if v is not None:
            try:
                vf = float(v)
                if vf > 0 and vf != TRANSMISSION_NULL_KV:
                    return vf
            except (TypeError, ValueError):
                pass
        vclass = attrs.get("VOLT_CLASS")
        if isinstance(vclass, str):
            mapped = VOLT_CLASS_TO_KV.get(vclass.strip().upper())
            if mapped is not None:
                return mapped
        return None

    # ---- point-layer fetchers ----

    def _build_substation_index(self, use_cache: bool) -> PointIndex:
        """Fetch OSM substations via Overpass across CONUS+AK+HI+PR bboxes
        and bucket the (lat, lon, kv) tuples into a PointIndex.

        OSM ways tagged `power=substation` are stored as polygons; we use
        Overpass's `out center` to receive the centroid as `center.{lat,lon}`,
        so the index treats every substation — node or way — as a single
        point. Voltage tag is parsed via `_parse_osm_voltage` (volts → kV,
        max across `;`-separated multi-values).
        """
        log.info("[substation] fetching OSM via Overpass across %d bboxes",
                 len(OVERPASS_SUBSTATION_BBOXES))
        idx = PointIndex()
        for i, bbox in enumerate(OVERPASS_SUBSTATION_BBOXES, 1):
            elements = self._fetch_overpass_substations(bbox, use_cache=use_cache)
            log.info("[substation] bbox %d/%d %s → %d features",
                     i, len(OVERPASS_SUBSTATION_BBOXES), bbox, len(elements))
            for el in elements:
                # node: lat/lon at top level; way: center.lat/lon.
                lat = el.get("lat") or (el.get("center") or {}).get("lat")
                lon = el.get("lon") or (el.get("center") or {}).get("lon")
                if lat is None or lon is None:
                    continue
                tags = el.get("tags") or {}
                kv = _parse_osm_voltage(tags.get("voltage"))
                attr = {"kv": kv} if kv is not None else None
                idx.add_point(lat, lon, attr=attr)
        log.info("[substation] indexed %d points", idx.point_count)
        return idx

    def _fetch_overpass_substations(
        self,
        bbox: tuple[float, float, float, float],
        use_cache: bool,
    ) -> list[dict[str, Any]]:
        """Single Overpass query for one bbox. Caches the response on disk
        keyed by the bbox tuple."""
        s, w, n, e = bbox
        # `out center tags` brings way centroids + tag dicts in one response.
        ql = (
            f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];"
            f"(node[\"power\"=\"substation\"]({s},{w},{n},{e});"
            f"way[\"power\"=\"substation\"]({s},{w},{n},{e}););"
            f"out center tags;"
        )
        cache_key = {"src": "overpass_substations", "bbox": list(bbox)}
        path = self.cache_path(cache_key)
        if use_cache and path.exists():
            log.info("cache hit  %s", path.name)
            try:
                return json.loads(path.read_text()).get("elements", [])
            except (OSError, json.JSONDecodeError):
                log.warning("[substation] cache file %s unreadable; refetching", path.name)

        import time as _time
        from connectors.base import REQUEST_DELAY_S, REQUEST_TIMEOUT_S, USER_AGENT
        log.info("fetching   %s (bbox %s)", path.name, bbox)
        _time.sleep(REQUEST_DELAY_S)
        # Overpass is sensitive to UA + accepts GET with data= param.
        resp = requests.get(
            OVERPASS_URL,
            params={"data": ql},
            headers={"User-Agent": USER_AGENT},
            timeout=max(REQUEST_TIMEOUT_S, OVERPASS_TIMEOUT_S + 30),
        )
        resp.raise_for_status()
        data = resp.json()
        path.write_text(json.dumps(data))
        log.info("cached     %s (%d elements)", path.name, len(data.get("elements", [])))
        return data.get("elements", [])

    def _build_power_plant_index(self, use_cache: bool) -> PointIndex:
        """Fetch HIFLD Power Plants (paginated FeatureServer) into a PointIndex.

        Carries `Total_MW` and `PrimSource` (fuel type) on the attr so the
        nearest-power-plant lookup can surface "what kind of generation is
        nearby" without a second join.
        """
        log.info("[power_plant] fetching HIFLD Power_Plants_in_the_US")
        idx = PointIndex()
        offset = 0
        page_size = 2000
        while True:
            params = {
                "where": "1=1",
                # NOTE: HIFLD Power_Plants_in_the_US only includes ACTIVE
                # generators — retired plants are not present in this dataset.
                # `power_plant_retired` is populated by the separate
                # `eia-retired-plants` enrichment connector (not yet built)
                # which reads EIA-860 Form 3_3 retired generators.
                # Cache key `power_plants` preserved from v1 to avoid
                # invalidating existing cache on every refresh.
                "outFields": "Plant_Name,Total_MW,PrimSource",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometryPrecision": "5",
                "resultRecordCount": str(page_size),
                "resultOffset": str(offset),
                "f": "json",
            }
            data = self.http_get_json(
                POWER_PLANT_QUERY_URL, params,
                use_cache=use_cache,
                cache_key={"src": "power_plants", "offset": offset},
            )
            features = data.get("features") or []
            log.info("[power_plant] page offset=%d got=%d", offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                lon = geom.get("x")
                lat = geom.get("y")
                if lat is None or lon is None:
                    continue
                a = feat.get("attributes") or {}
                attr = {
                    "name": a.get("Plant_Name"),
                    "mw": a.get("Total_MW"),
                    "fuel": a.get("PrimSource"),
                    # `status` populated by eia-retired-plants connector, not here.
                    "status": None,
                }
                idx.add_point(lat, lon, attr=attr)
            if len(features) < page_size:
                break
            offset += page_size
        log.info("[power_plant] indexed %d points", idx.point_count)
        return idx

    # ---- per-site flood-zone ----

    def _query_flood_zone(
        self,
        lat: float,
        lon: float,
        use_cache: bool,
    ) -> tuple[str | None, bool | None]:
        """Ask FEMA NFHL: what flood-zone polygon contains this point?

        Returns `(FLD_ZONE, in_sfha)` where:
        - `FLD_ZONE`: source-side code (`A`, `AE`, `X`, `V`, `VE`, `D`, ...);
          None if the site lies outside any mapped FEMA flood study area.
        - `in_sfha`: True / False / None for SFHA_TF == `T` / `F` / missing.

        One HTTP call per site. Cached per (lat, lon) rounded to 5 decimals
        (~1 m precision — way finer than the FEMA polygon edges).
        """
        cache_key = _flood_cache_key(lat, lon)
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outFields": "FLD_ZONE,SFHA_TF,ZONE_SUBTY",
            "returnGeometry": "false",
            "f": "json",
        }
        data = self.http_get_json(
            FLOOD_QUERY_URL, params,
            use_cache=use_cache,
            cache_key=cache_key,
        )
        features = data.get("features") or []
        if not features:
            return (None, None)
        # FEMA polygons don't overlap; one feature is the expected case. If
        # multiple ever come back, prefer the one with a non-empty FLD_ZONE.
        for feat in features:
            attrs = feat.get("attributes") or {}
            zone = attrs.get("FLD_ZONE")
            if zone:
                sfha_raw = attrs.get("SFHA_TF")
                in_sfha: bool | None = None
                if isinstance(sfha_raw, str):
                    s = sfha_raw.strip().upper()
                    if s == "T":
                        in_sfha = True
                    elif s == "F":
                        in_sfha = False
                return (str(zone), in_sfha)
        # All features had empty FLD_ZONE — treat as no signal.
        return (None, None)
