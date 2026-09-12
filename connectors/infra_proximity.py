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
import hashlib
import math
from datetime import datetime, timezone
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
# Below this an OSM `power=substation` is LV distribution / traction gear
# rather than a transmission interconnection point. We keep the DISTANCE
# (something electrical is genuinely there) but withhold the voltage, so
# scoring can't mistake a 600 V rectifier for a switchyard.
MIN_SUBSTATION_KV = 1.0
# Voltage classes remain source labels; never invent a numeric voltage.

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
        if not math.isfinite(v) or v <= 0:
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
# Abort flood fetching after this many CONSECUTIVE FEMA NFHL failures — a
# sustained SSLError/timeout wave means the endpoint is unhealthy, and each
# attempt still burns the 1.5s delay + up to the 60s timeout. Cached successes
# are durable, so the next run resumes when FEMA recovers.
FLOOD_ERROR_CIRCUIT_BREAK = 25


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
    source_label = "HIFLD + Census TIGER + OpenStreetMap + FEMA (mapped infrastructure context)"
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

    def _source_inventory(self, url: str, where: str) -> tuple[int, str]:
        """Fresh metadata and expected count; fail before publishing partial pulls."""
        meta = self.http_get_json(url.removesuffix("/query"), {"f": "json"}, use_cache=False)
        if meta.get("error") or not meta.get("objectIdField"):
            raise ValueError("Infrastructure source lacks object ID metadata")
        count = self.http_get_json(url, {"f": "json", "where": where, "returnCountOnly": "true"}, use_cache=False)
        if not isinstance(count.get("count"), int):
            raise ValueError("Infrastructure source lacks expected count")
        if not hasattr(self, "_inventory_dates"):
            self._inventory_dates = {}
        stamp = (meta.get("editingInfo") or {}).get("dataLastEditDate")
        self._inventory_dates[url] = datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat() if stamp else None
        return count["count"], meta["objectIdField"]

    def _metadata(self, layer: str, **values: Any) -> None:
        if not hasattr(self, "source_metadata"):
            self.source_metadata: dict[str, dict[str, Any]] = {}
        self.source_metadata.setdefault(layer, {}).update(values)

    def compact_evidence(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Share asset provenance once; retain row exceptions and coordinates."""
        for layer, meta in getattr(self, "source_metadata", {}).items():
            if "assets_by_id" in meta:
                meta["assets_by_id"] = {key.replace(layer + ":geometry:", "local:"): value for key, value in meta["assets_by_id"].items()}
        legacy_flood = sum((r.get("infra_evidence", {}).get("flood_zone") or {}).get("status") == "legacy_coordinate_unverified" for r in records)
        if legacy_flood > len(records) / 2:
            self._metadata("flood_zone", status="legacy_coordinate_unverified")
        for rec in records:
            for layer in ("transmission", "substation", "power_plant"):
                key = layer + "_asset_id"
                if rec.get(key):
                    rec[key] = rec[key].replace(layer + ":geometry:", "local:")
            plant_id = rec.get("power_plant_asset_id")
            if plant_id and rec.get("power_plant_name"):
                self._metadata("power_plant")
                self.source_metadata["power_plant"].setdefault("assets_by_id", {}).setdefault(plant_id, {})["name"] = rec.pop("power_plant_name")
            for layer, observation in list((rec.get("infra_evidence") or {}).items()):
                status = observation.get("status")
                asset_id = rec.get(layer + "_asset_id")
                asset = {k: v for k, v in observation.items() if k not in {"status", "asset_id"}}
                if asset_id and asset:
                    self._metadata(layer)
                    self.source_metadata[layer].setdefault("assets_by_id", {}).setdefault(asset_id, {}).update(asset)
                if status == "matched_context":
                    self._metadata(layer)
                    self.source_metadata[layer].setdefault("status", "matched_context")
                default_status = getattr(self, "source_metadata", {}).get(layer, {}).get("status")
                if status and status == default_status:
                    del rec["infra_evidence"][layer]
                else:
                    rec["infra_evidence"][layer] = {"status": status or "not_assessed"}
        return records

    @staticmethod
    def _page_features(data: dict[str, Any]) -> list[dict[str, Any]]:
        if data.get("error") or data.get("remark"):
            raise RuntimeError(f"Incomplete infrastructure response: {data.get('error') or data.get('remark')}")
        if "features" not in data or not isinstance(data["features"], list):
            raise ValueError("Infrastructure response missing features array")
        if not data["features"] and data.get("exceededTransferLimit"):
            raise ValueError("Infrastructure paging made no progress")
        return data["features"]

    @staticmethod
    def _asset_id(feature: dict[str, Any], layer: str) -> tuple[str, str]:
        attrs = feature.get("attributes") or {}
        for key in ("GlobalID", "ID", "Plant_Code", "Plant_ID", "OBJECTID_1", "OBJECTID", "ObjectId"):
            if attrs.get(key) is not None:
                return f"{layer}:{attrs[key]}", "source_id"
        # Legacy geometry-only caches cannot recover source IDs. Mark the
        # local fingerprint explicitly; never present it as an agency ID.
        digest = hashlib.sha256(json.dumps(feature, sort_keys=True).encode()).hexdigest()[:16]
        return f"local:{digest}", "local_geometry_fingerprint"

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        self.source_metadata = {}
        if self.existing_output_path().exists():
            prior_meta = json.loads(self.existing_output_path().read_text()).get("source_metadata") or {}
            for layer, metadata in prior_meta.items():
                if getattr(args, f"infra_skip_{layer}", False):
                    self.source_metadata[layer] = metadata
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
                self.source_metadata = json.loads(self.existing_output_path().read_text()).get("source_metadata") or {}
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
        flood_seed: dict[str, dict[str, Any]] = {}
        flood_budget = int(getattr(args, "infra_flood_budget", 0) or 0)
        if do_flood:
            for prev in self.existing_records():
                pid = prev.get("id")
                if pid is None:
                    continue
                fz = prev.get("flood_zone")
                sf = prev.get("in_sfha")
                if fz is not None or sf is not None:
                    flood_seed[pid] = prev
            log.info("[flood_zone] seeded %d sites from existing output%s",
                     len(flood_seed),
                     f", new-fetch budget={flood_budget}" if flood_budget else "")

        previous_by_id = {r["id"]: r for r in self.existing_records()}
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
        flood_fetches = 0          # NEW network attempts (cache misses) this run — budget unit
        flood_budget_skipped = 0   # sites left unqueried because budget ran out
        consecutive_flood_errors = 0  # circuit-breaker counter for FEMA failure waves
        # Per-program counts for telemetry.
        program_counts: dict[str, int] = {}
        for site_number, site in enumerate(sites, 1):
            if site_number == 1 or site_number % 10000 == 0:
                log.info("infrastructure observations: %d/%d sites", site_number, len(sites))
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
            if not (math.isfinite(lat_f) and math.isfinite(lon_f) and -90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                skipped_no_geom += 1
                continue
            rec: dict[str, Any] = {"id": sid, "program": program,
                                   "infra_assessed_lat": lat_f, "infra_assessed_lon": lon_f}
            evidence: dict[str, dict[str, Any]] = {}
            previous = previous_by_id.get(sid, {})
            same_coordinate = (previous.get("infra_assessed_lat") == lat_f and
                               previous.get("infra_assessed_lon") == lon_f)
            for layer in list(LAYERS) + ["substation", "power_plant", "flood_zone"]:
                skipped = getattr(args, f"infra_skip_{layer}", False)
                available = layer in seg_indexes or layer in point_indexes or (layer == "flood_zone" and do_flood)
                evidence[layer] = {"status": "not_assessed" if skipped else "no_mapped_asset_within_radius" if available else "source_unavailable"}
                if skipped or not available:
                    prefix = "flood_" if layer == "flood_zone" else layer + "_"
                    for key, value in previous.items():
                        if key.startswith(prefix) or (layer == "flood_zone" and key == "in_sfha"):
                            rec[key] = value
                    if any(key.startswith(prefix) for key in previous):
                        evidence[layer] = dict((previous.get("infra_evidence") or {}).get(layer, {}))
                        old_status = evidence[layer].get("status") or self.source_metadata.get(layer, {}).get("status")
                        evidence[layer]["status"] = "source_unavailable" if not available and not skipped else old_status if old_status in {"legacy_coordinate_unverified", "unsupported_region", "not_assessed", "source_unavailable"} else "retained_previous" if same_coordinate else "legacy_coordinate_unverified"
            rec["infra_evidence"] = evidence

            # ---- polyline layers ----
            for layer, idx in seg_indexes.items():
                if layer == "transmission":
                    hit = idx.nearest_with_attr(lat_f, lon_f)
                    if hit is None:
                        out_of_range[layer] += 1
                        continue
                    d, attr = hit
                    kv = attr.get("kv") if isinstance(attr, dict) else attr
                    if isinstance(attr, dict):
                        evidence[layer] = {k: v for k, v in attr.items() if k != "kv" and v is not None}
                        rec["transmission_asset_id"] = attr["asset_id"]
                    if d > MAX_DISTANCE_MI:
                        out_of_range[layer] += 1
                        continue
                    rec[DISTANCE_FIELD[layer]] = round(d, 1)
                    evidence[layer]["status"] = "matched_context"
                    if kv is not None:
                        rec["transmission_kv"] = round(float(kv), 1)
                else:
                    d = idx.nearest_distance_mi(lat_f, lon_f)
                    if d is None or d > MAX_DISTANCE_MI:
                        out_of_range[layer] += 1
                        continue
                    rec[DISTANCE_FIELD[layer]] = round(d, 1)
                    evidence[layer]["status"] = "matched_context"

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
                evidence[layer]["status"] = "matched_context"
                if isinstance(attr, dict):
                    for key in ("asset_id", "id_basis", "role", "voltage_basis"):
                        if attr.get(key) is not None:
                            evidence[layer][key] = attr[key]
                    if attr.get("asset_id"):
                        rec[layer + "_asset_id"] = attr["asset_id"]
                    if layer == "substation":
                        rec["substation_role"] = attr.get("role", "unspecified")
                    if layer == "power_plant" and attr.get("name"):
                        rec["power_plant_name"] = attr["name"]
                    if layer == "substation" and attr.get("kv") is not None:
                        kv = round(float(attr["kv"]), 1)
                        # Sub-1 kV OSM `power=substation` nodes are traction /
                        # LV distribution gear (a 600 V trolley rectifier reads
                        # as 0.6 kV), not a grid interconnection point. Emitting
                        # the value made `_scoreSubstation` treat them as real
                        # substations at a x0.5 discount. Absent is the honest
                        # answer — the substation distance still stands, only
                        # the misleading voltage is withheld.
                        if kv >= MIN_SUBSTATION_KV:
                            rec["substation_kv"] = kv
                    elif layer == "power_plant":
                        # HIFLD reports Total_MW = 0 for a handful of plants;
                        # that is a missing value wearing a number's clothes.
                        if attr.get("mw") is not None and float(attr["mw"]) > 0:
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

            if not any(s <= lat_f <= n and w <= lon_f <= e for s, w, n, e in OVERPASS_SUBSTATION_BBOXES):
                evidence["substation"] = {"status": "unsupported_region"}
                for key in list(rec):
                    if key.startswith("substation_"):
                        del rec[key]

            # ---- per-site flood zone ----
            if do_flood:
                seeded = flood_seed.get(sid)
                if seeded is not None:
                    stamp = seeded.get("flood_source_observed_at")
                    try:
                        observed = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
                        fresh = observed is not None and 0 <= (datetime.now(timezone.utc) - observed).total_seconds() <= 365 * 86400
                    except (ValueError, TypeError):
                        fresh = False
                    if not (use_cache and fresh and seeded.get("flood_assessed_lat") == lat_f and seeded.get("flood_assessed_lon") == lon_f):
                        seeded = None
                if seeded is not None:
                    # Already populated in a prior run — carry it forward
                    # only while coordinates match and the observation is <=365 days old.
                    s_fz, s_sfha = seeded.get("flood_zone"), seeded.get("in_sfha")
                    for key in ("flood_assessed_lat", "flood_assessed_lon", "flood_source_observed_at"):
                        rec[key] = seeded[key]
                    evidence["flood_zone"] = {"status": "matched_context"}
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
                            flood_lookups += 1
                            rec["flood_assessed_lat"] = lat_f
                            rec["flood_assessed_lon"] = lon_f
                            evidence["flood_zone"] = {"status": "cached_snapshot_date_unknown" if cache_exists and use_cache else "matched_context"}
                            if not cache_exists or not use_cache:
                                rec["flood_source_observed_at"] = datetime.now(timezone.utc).isoformat()
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
                            consecutive_flood_errors += 1
                        except requests.HTTPError as e:
                            code = e.response.status_code if e.response is not None else None
                            if code in FLOOD_TRANSIENT_HTTP_CODES:
                                log.warning("[%s] FEMA NFHL HTTP %s — skipping flood field",
                                            sid, code)
                                flood_skipped += 1
                                consecutive_flood_errors += 1
                            else:
                                raise
                        else:
                            consecutive_flood_errors = 0
                        finally:
                            # Count every NETWORK attempt against the budget — not
                            # only successes — so a flaky / erroring endpoint
                            # (FEMA NFHL throws SSLError waves) can't make the run
                            # unbounded. Cache hits make no call, so they're free.
                            if not cache_exists:
                                flood_fetches += 1
                        # Circuit breaker: if FEMA is in a sustained failure wave,
                        # stop wasting the budget on it — cached successes are
                        # already durable, so resume on a later run when it's
                        # healthy. (Each failure still costs the 1.5s delay + up
                        # to the 60s timeout, so a long wave is pure waste.)
                        if consecutive_flood_errors >= FLOOD_ERROR_CIRCUIT_BREAK:
                            log.error("[flood_zone] %d consecutive FEMA errors — "
                                      "aborting flood fetches (resume later); "
                                      "%d done this run", consecutive_flood_errors, flood_fetches)
                            do_flood = False
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
        expected, oid = self._source_inventory(cfg["url"], cfg["where"]) if not use_cache else (None, None)
        fetched = 0
        seen_ids: set[str] = set()
        seen_pages: set[str] = set()
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
            if oid:
                params.update(outFields="*", orderByFields=oid)
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
            features = self._page_features(data)
            digest = hashlib.sha256(json.dumps(features, sort_keys=True).encode()).hexdigest()
            if features and digest in seen_pages:
                raise ValueError("Infrastructure endpoint repeated a page; refusing incomplete inventory")
            seen_pages.add(digest)
            log.info("[%s] page offset=%d got=%d", layer, offset, len(features))
            if not features:
                break
            fetched += len(features)
            for feat in features:
                if oid:
                    source_id = str((feat.get("attributes") or {}).get(oid))
                    if source_id == "None" or source_id in seen_ids:
                        raise ValueError("Missing or repeated infrastructure asset ID")
                    seen_ids.add(source_id)
                geom = feat.get("geometry") or {}
                # ESRI polyline: { "paths": [[[lon, lat], ...], ...] }
                paths = geom.get("paths") or []
                attrs = feat.get("attributes") or {}
                attr = self._extract_attr(layer, attrs)
                if layer == "transmission":
                    if attr is not None:
                        kv_features += 1
                    asset_id, basis = self._asset_id(feat, layer)
                    attr = {"kv": attr, "asset_id": asset_id, "id_basis": basis,
                            "voltage_basis": "reported" if attr is not None else "class_only" if attrs.get("VOLT_CLASS") else "unknown",
                            "voltage_class": attrs.get("VOLT_CLASS"), "asset_status": attrs.get("STATUS")}

                for path in paths:
                    added = idx.add_polyline(path, attr=attr)
                    if added > 0:
                        polylines_added += 1
            if len(features) < page_size and not data.get("exceededTransferLimit"):
                break
            offset += len(features)
        if layer == "transmission":
            log.info("[transmission] %d / %d polylines carry kV",
                     kv_features, polylines_added)
        log.info("[%s] indexed %d polylines / %d segments",
                 layer, polylines_added, idx.segment_count)
        if expected is not None and fetched != expected:
            raise ValueError(f"Incomplete {layer}: expected {expected}, fetched {fetched}")
        self._metadata(layer, source_url=cfg["url"].removesuffix("/query"),
                       source_snapshot_at=datetime.now(timezone.utc).isoformat() if not use_cache else None, feature_count=fetched,
                       snapshot_basis="legacy_cache_unknown_retrieval_date" if use_cache else "retrieved_this_run",
                       count_reconciled=expected is not None, search_radius_mi=MAX_DISTANCE_MI,
                       data_last_edit=getattr(self, "_inventory_dates", {}).get(cfg["url"]))
        return idx

    @staticmethod
    def _extract_attr(layer: str, attrs: dict[str, Any]) -> float | None:
        """Pull the per-feature attribute we want carried on the segment.

        For transmission: retain only reported `VOLTAGE` (Double, kV).
        Source `VOLT_CLASS` is preserved separately. Sentinel value
        `-999999` (HIFLD's null marker) collapses to None.

        Returns None for layers that don't carry attributes.
        """
        if layer != "transmission":
            return None
        v = attrs.get("VOLTAGE")
        if v is not None:
            try:
                vf = float(v)
                if math.isfinite(vf) and vf > 0 and vf != TRANSMISSION_NULL_KV:
                    return vf
            except (TypeError, ValueError):
                pass
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
        seen: set[tuple[str, int]] = set()
        for i, bbox in enumerate(OVERPASS_SUBSTATION_BBOXES, 1):
            elements = self._fetch_overpass_substations(bbox, use_cache=use_cache)
            log.info("[substation] bbox %d/%d %s → %d features",
                     i, len(OVERPASS_SUBSTATION_BBOXES), bbox, len(elements))
            for el in elements:
                identity = (el.get("type", "unknown"), el.get("id"))
                if identity[1] is not None and identity in seen:
                    continue
                seen.add(identity)
                # node: lat/lon at top level; way: center.lat/lon.
                lat = el.get("lat") or (el.get("center") or {}).get("lat")
                lon = el.get("lon") or (el.get("center") or {}).get("lon")
                if lat is None or lon is None:
                    continue
                tags = el.get("tags") or {}
                kv = _parse_osm_voltage(tags.get("voltage"))
                role = tags.get("substation", "unspecified")
                if role in {"gas", "valve", "compression", "heat-exchanger", "internet"}:
                    continue
                attr = {"kv": kv, "role": role,
                        "asset_id": f"osm:{identity[0]}/{identity[1]}" if identity[1] is not None else None,
                        "id_basis": "source_id" if identity[1] is not None else "unknown", "voltage_basis": "reported" if kv is not None else "unknown"}
                idx.add_point(lat, lon, attr=attr)
        log.info("[substation] indexed %d points", idx.point_count)
        self._metadata("substation", source_url="https://www.openstreetmap.org/copyright",
                       query_url=OVERPASS_URL, feature_count=idx.point_count,
                       geometry_basis="OSM node or bounding-box center; not a surveyed connection point",
                       geographic_coverage="CONUS, AK, HI, PR, VI; excludes GU, MP, AS",
                       feature_coverage="nodes and ways; legacy snapshots exclude relations",
                       search_radius_mi=MAX_DISTANCE_MI)
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
                data = json.loads(path.read_text())
                if data.get("remark") or not isinstance(data.get("elements"), list):
                    raise ValueError("Incomplete cached Overpass response")
                stamp = (data.get("osm3s") or {}).get("timestamp_osm_base")
                current = getattr(self, "source_metadata", {}).get("substation", {}).get("source_snapshot_at")
                self._metadata("substation", source_snapshot_at=min(stamp, current) if stamp and current else stamp or current,
                               snapshot_basis="osm_base_timestamp")
                return data["elements"]
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
        if data.get("remark") or not isinstance(data.get("elements"), list):
            raise ValueError("Incomplete Overpass response; refusing cache write")
        self._metadata("substation", source_snapshot_at=(data.get("osm3s") or {}).get("timestamp_osm_base"), snapshot_basis="osm_base_timestamp")
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
        expected, oid = self._source_inventory(POWER_PLANT_QUERY_URL, "1=1") if not use_cache else (None, None)
        fetched = 0
        seen_ids: set[str] = set()
        seen_pages: set[str] = set()
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
            if oid:
                params.update(outFields="*", orderByFields=oid)
            data = self.http_get_json(
                POWER_PLANT_QUERY_URL, params,
                use_cache=use_cache,
                cache_key={"src": "power_plants", "offset": offset},
            )
            features = self._page_features(data)
            digest = hashlib.sha256(json.dumps(features, sort_keys=True).encode()).hexdigest()
            if features and digest in seen_pages:
                raise ValueError("Infrastructure endpoint repeated a page; refusing incomplete inventory")
            seen_pages.add(digest)
            log.info("[power_plant] page offset=%d got=%d", offset, len(features))
            if not features:
                break
            fetched += len(features)
            for feat in features:
                if oid:
                    source_id = str((feat.get("attributes") or {}).get(oid))
                    if source_id == "None" or source_id in seen_ids:
                        raise ValueError("Missing or repeated power plant ID")
                    seen_ids.add(source_id)
                geom = feat.get("geometry") or {}
                lon = geom.get("x")
                lat = geom.get("y")
                if lat is None or lon is None:
                    continue
                a = feat.get("attributes") or {}
                asset_id, basis = self._asset_id(feat, "power_plant")
                attr = {
                    "asset_id": asset_id, "id_basis": basis,
                    "name": a.get("Plant_Name"),
                    "mw": a.get("Total_MW"),
                    "fuel": a.get("PrimSource"),
                    # `status` populated by eia-retired-plants connector, not here.
                    "status": None,
                }
                idx.add_point(lat, lon, attr=attr)
            if len(features) < page_size and not data.get("exceededTransferLimit"):
                break
            offset += len(features)
        log.info("[power_plant] indexed %d points", idx.point_count)
        if expected is not None and fetched != expected:
            raise ValueError(f"Incomplete plants: expected {expected}, fetched {fetched}")
        self._metadata("power_plant", source_url=POWER_PLANT_QUERY_URL.removesuffix("/query"),
                       feature_count=fetched, source_snapshot_at=datetime.now(timezone.utc).isoformat() if not use_cache else None,
                       capacity_basis="maximum_summer_capacity", count_reconciled=expected is not None,
                       data_last_edit=getattr(self, "_inventory_dates", {}).get(POWER_PLANT_QUERY_URL))
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
        features = self._page_features(data)
        if data.get("exceededTransferLimit"):
            raise ValueError("Truncated FEMA point query")
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
