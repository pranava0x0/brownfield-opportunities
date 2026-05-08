"""Universal infrastructure-proximity enrichment.

Computes nearest-distance to electric transmission, freight rail, major
highway, and natural-gas pipeline from every site we already know about
(Superfund, ACRES, FUDS, BRAC), so the data-center thesis ("post-remediation
industrial land + grid + rail + road + behind-the-meter gas = AI siting
target") works for ~47k records, not just the ~1.9k that EPA's Redevelopment
mapper covers today.

Sources (all public, no auth):
- **Transmission lines**: HIFLD `Electric_Power_Transmission_Lines`
  (~52k polyline features, includes voltage where reported).
- **Rail**: US Census TIGERweb Railroads (~112k features). Census is the
  cleanest single national source — HIFLD's NTAD layer has more attributes
  but for proximity-only we don't need the metadata.
- **Highways**: US Census TIGERweb Primary Roads (~17k features, MTFCC=S1100,
  i.e. Interstates + US/state routes that meet primary-road criteria).
- **Natural gas pipelines**: HIFLD `Natural Gas Interstate and Intrastate
  Pipelines (EIA)` — ~33k polylines spanning interstate + intrastate +
  gathering. <2 mi to a major line is the threshold for behind-the-meter
  gas-turbine viability (Stargate Texas pattern: VoltaGrid 2.3 GW BTM gas
  + GE Vernova 29 turbines). NGL (natural-gas-liquids) layer intentionally
  excluded — DCs care about methane, not propane.

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
            for layer, idx in indexes.items():
                # Transmission carries a per-segment kV attribute; rail and
                # highway are geometry-only. Branch so we don't pay the
                # tuple-allocation cost on layers that don't need it.
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
                        # Round to 1 kV so 138.0 / 230.0 / 345.0 read clean
                        # in the JSON. HIFLD reports many lines as integer
                        # kV but a handful are floats (e.g. 138.5).
                        rec["transmission_kv"] = round(float(kv), 1)
                else:
                    d = idx.nearest_distance_mi(lat_f, lon_f)
                    if d is None or d > MAX_DISTANCE_MI:
                        out_of_range[layer] += 1
                        continue
                    rec[DISTANCE_FIELD[layer]] = round(d, 1)
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
