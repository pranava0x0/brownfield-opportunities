"""Universal infrastructure-proximity enrichment.

Computes nearest-distance to electric transmission, freight rail, and major
highway from every site we already know about (Superfund, ACRES, FUDS, BRAC),
so the data-center thesis ("post-remediation industrial land + grid + rail
+ road = AI siting target") works for ~47k records, not just the ~1.9k that
EPA's Redevelopment mapper covers today.

Sources (all public, no auth):
- **Transmission lines**: HIFLD `Electric_Power_Transmission_Lines`
  (~52k polyline features, includes voltage where reported).
- **Rail**: US Census TIGERweb Railroads (~112k features). Census is the
  cleanest single national source — HIFLD's NTAD layer has more attributes
  but for proximity-only we don't need the metadata.
- **Highways**: US Census TIGERweb Primary Roads (~17k features, MTFCC=S1100,
  i.e. Interstates + US/state routes that meet primary-road criteria).

This is an *enrichment-only* connector — it doesn't add new sites. It reads
the per-program JSON files written by the producer connectors, computes
three distance fields per record, and writes a compact lookup file. The
frontend lazy-loads it after first paint and joins onto `sitesById` by `id`.

Performance:
- ~180k polyline features fetched in ~1 minute on a cold run; cached on
  disk thereafter, so re-runs are seconds.
- Pure-Python grid index in `connectors.spatial` — no shapely/rtree.
- Distance lookup is O(log n) amortized via 0.25° grid cells.
- Distances >100 mi are dropped (treated as out-of-CONUS) to keep the
  enrichment file lean. ~600 KB gzipped at full coverage.

CLI:
    python refresh.py --source infra-proximity            # enrichment-only run
    python refresh.py --all                               # part of the full refresh
    python refresh.py --source infra-proximity --infra-skip-rail   # subset
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import SegmentIndex

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

# Layer-specific page size. HIFLD caps at 2000. TIGERweb advertises
# maxRecordCount=100000, but the actual response-payload limit with geometry
# kicks in well before that (10k pages return HTTP 500). 1000 is the largest
# safe page for TIGER polylines.
LAYERS: dict[str, dict[str, Any]] = {
    "transmission": {
        "url": TRANSMISSION_QUERY_URL,
        "page_size": 2000,
        "where": "1=1",
        "label": "HIFLD Electric Power Transmission Lines",
    },
    "highway": {
        "url": HIGHWAY_QUERY_URL,
        "page_size": 1000,
        "where": "MTFCC='S1100'",
        "label": "US Census TIGERweb Primary Roads (Interstates + Major US/State)",
    },
    "rail": {
        "url": RAIL_QUERY_URL,
        "page_size": 1000,
        "where": "1=1",
        "label": "US Census TIGERweb Railroads",
    },
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
}


class InfraProximity(Connector):
    slug = "infra-proximity"
    source_label = "HIFLD + Census TIGER (transmission, rail, highways)"
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
        # Per-layer skip toggles for fast iteration during development.
        for layer in LAYERS:
            p.add_argument(
                f"--infra-skip-{layer}",
                dest=f"infra_skip_{layer}",
                action="store_true",
                default=False,
                help=f"Skip the {layer} layer (no {DISTANCE_FIELD[layer]} field emitted).",
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

        # Build one SegmentIndex per layer. Skipped layers leave the field
        # absent from emitted records (frontend renders "Not available").
        indexes: dict[str, SegmentIndex] = {}
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
            indexes[layer] = idx

        if not indexes:
            log.error("no infrastructure layers built — aborting enrichment")
            return []

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        out_of_range = {layer: 0 for layer in indexes}
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
            any_field = False
            for layer, idx in indexes.items():
                d = idx.nearest_distance_mi(lat_f, lon_f)
                if d is None or d > MAX_DISTANCE_MI:
                    out_of_range[layer] += 1
                    continue
                rec[DISTANCE_FIELD[layer]] = round(d, 1)
                any_field = True
            if not any_field:
                # No layer is reachable → omit the record entirely. The
                # frontend already treats absent records as "no enrichment."
                continue
            records.append(rec)
            program_counts[program] = program_counts.get(program, 0) + 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        for layer, n in out_of_range.items():
            log.info("[%s] %d sites had no segment within %d mi",
                     layer, n, int(MAX_DISTANCE_MI))
        log.info("enriched %d records — by program: %s",
                 len(records), program_counts)

        if getattr(args, "limit", None):
            records = records[: args.limit]

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
        while True:
            params = {
                "where": cfg["where"],
                "outFields": "",
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
                cache_key={"layer": layer, "offset": offset, "where": cfg["where"]},
            )
            features = data.get("features") or []
            log.info("[%s] page offset=%d got=%d", layer, offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                # ESRI polyline: { "paths": [[[lon, lat], ...], ...] }
                paths = geom.get("paths") or []
                for path in paths:
                    added = idx.add_polyline(path)
                    if added > 0:
                        polylines_added += 1
            if len(features) < page_size:
                break
            offset += page_size
        log.info("[%s] indexed %d polylines / %d segments",
                 layer, polylines_added, idx.segment_count)
        return idx
