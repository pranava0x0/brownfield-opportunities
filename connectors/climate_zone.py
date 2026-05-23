"""IECC / ASHRAE climate-zone enrichment.

Assigns every known site to its county-level DOE Building America / IECC
climate zone, e.g. `5B` or `3A`. For data-center siting this is a cooling
signal: dry 3B / 4B / 5B / 6B climates generally support more free cooling
than hot-humid or marine climates.

Source: DOE / PNNL Building America and IECC Climate Zones by U.S. County
Boundaries (Detailed), ArcGIS FeatureServer item 8e5c3c6e1fa94e379553e199dcc4e777.
The layer carries county polygons plus `IECC_Climate_Zone` and
`IECC_Moisture_Regime`.

This is an enrichment-only connector: it reads per-program JSON files from
`docs/data/`, computes point-in-polygon containment, and writes compact
records with `id`, `program`, and `climate_zone`.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import PolygonIndex

log = logging.getLogger("connector.climate_zone")

CLIMATE_ZONE_QUERY_URL = (
    "https://services8.arcgis.com/s3xegrS2bQ4HS3tU/arcgis/rest/services/"
    "Building_America_and_IECC_Climate_Zones_by_U_S__County_Boundaries_%28Detailed%29/"
    "FeatureServer/0/query"
)
# The service advertises maxRecordCount=2000, but geometry pages that large
# intermittently 504. Keep pages smaller so refreshes finish reliably.
PAGE_SIZE = 500

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


class ClimateZone(Connector):
    slug = "climate-zone"
    source_label = "DOE / PNNL Building America IECC Climate Zones"
    source_url = "https://basc.pnnl.gov/guide-determining-climate-zone-county-data-files"

    # Run after producer connectors and after other fast spatial enrichments.
    run_order = 360

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument(
                "--limit",
                type=int,
                default=None,
                help="Cap the number of enriched records (default: unlimited).",
            )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        sites = list(self._load_sites())
        if not sites:
            log.error(
                "no per-program JSON files found in %s — run producer connectors first",
                self._data_dir(),
            )
            return []
        log.info("loaded %d sites across %d program files",
                 len(sites), self._loaded_program_count)

        missing_only = bool(getattr(args, "missing_only", False))
        if missing_only:
            covered = self.existing_ids()
            if covered:
                before = len(sites)
                sites = [s for s in sites if s.get("id") not in covered]
                log.info("--missing-only: %d/%d sites already covered, %d remaining",
                         before - len(sites), before, len(sites))
            if not sites:
                existing = self.existing_records()
                log.info("--missing-only: nothing to fetch; returning %d existing records",
                         len(existing))
                return existing

        idx = self._build_index(use_cache=use_cache)
        if idx.polygon_count == 0:
            log.error("climate-zone index empty after fetch — aborting")
            return []
        log.info("[climate-zone] indexed %d county polygons", idx.polygon_count)

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        skipped_no_hit = 0
        zones: dict[str, int] = {}
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
            hit = idx.containing(lat_f, lon_f)
            if hit is None:
                skipped_no_hit += 1
                continue
            zone = hit.get("climate_zone") if isinstance(hit, dict) else None
            if not zone:
                skipped_no_hit += 1
                continue
            records.append({"id": sid, "program": program, "climate_zone": zone})
            zones[zone] = zones.get(zone, 0) + 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        if skipped_no_hit:
            log.info("skipped %d sites outside county climate-zone polygons", skipped_no_hit)
        log.info("enriched %d records — zones: %s", len(records), zones)

        if getattr(args, "limit", None):
            records = records[: args.limit]

        if missing_only:
            existing = self.existing_records()
            merged = self.merge_records_by_id(records, existing)
            log.info("--missing-only: merged %d new + %d existing = %d total",
                     len(records), len(existing), len(merged))
            return merged
        return records

    @staticmethod
    def _data_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "docs" / "data"

    def _load_sites(self) -> Iterable[dict[str, Any]]:
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

    def _build_index(self, use_cache: bool) -> PolygonIndex:
        idx = PolygonIndex()
        offset = 0
        while True:
            params = {
                "where": "1=1",
                "outFields": (
                    "FIPS,County_Name,STATE_NAME,IECC_Climate_Zone,"
                    "IECC_Moisture_Regime,BA_Climate_Zone"
                ),
                "returnGeometry": "true",
                "outSR": "4326",
                "geometryPrecision": "6",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "f": "json",
            }
            data = self.http_get_json(
                CLIMATE_ZONE_QUERY_URL,
                params,
                use_cache=use_cache,
                cache_key={"src": "climate_zone", "offset": offset, "page_size": PAGE_SIZE},
            )
            features = data.get("features") or []
            log.info("[climate-zone] page offset=%d got=%d", offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                rings = geom.get("rings") or []
                if not rings:
                    continue
                attrs = feat.get("attributes") or {}
                zone = _format_climate_zone(attrs)
                if not zone:
                    continue
                idx.add_polygon(
                    rings,
                    attr={
                        "climate_zone": zone,
                        "fips": attrs.get("FIPS"),
                        "county": attrs.get("County_Name"),
                        "state": attrs.get("STATE_NAME"),
                        "ba_zone": attrs.get("BA_Climate_Zone"),
                    },
                )
            if len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return idx


def _format_climate_zone(attrs: dict[str, Any]) -> str | None:
    raw_zone = attrs.get("IECC_Climate_Zone")
    raw_moisture = attrs.get("IECC_Moisture_Regime")
    if raw_zone is None or raw_zone == "":
        return None
    try:
        # ArcGIS ships integers for most rows; normalize 5.0 -> "5".
        zone = str(int(float(raw_zone)))
    except (TypeError, ValueError):
        zone = str(raw_zone).strip()
    moisture = "" if raw_moisture is None else str(raw_moisture).strip().upper()
    if moisture and moisture not in {"A", "B", "C"}:
        moisture = ""
    return f"{zone}{moisture}" if zone else None
