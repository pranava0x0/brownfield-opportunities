"""Opportunity Zone enrichment.

Marks each site as inside or outside a Treasury-designated Qualified
Opportunity Zone (QOZ) by point-in-polygon containment against HUD's
`Opportunity_Zones` FeatureServer layer (8,765 census tracts nationwide).

A QOZ designation is a financial sweetener for buyers / investors: capital
gains invested in a Qualified Opportunity Fund deployed inside an OZ get
tax deferral (10% step-up at 5 yrs, 15% at 7 yrs) plus permanent exclusion
of post-investment gains held 10+ yrs. The 2017 designations remain in
effect for 10 years from designation; investment benefits run through
2026-12-31.

For the data-center / energy-infra siting use case this isn't a technical-
suitability signal — a brownfield is no easier to build on because it's in
an OZ. It IS a finance / IRR signal: a $100M build inside an OZ has
meaningfully different after-tax math than one outside.

Source: HUD `Opportunity_Zones/FeatureServer/13` (canonical post-2025 mirror;
EPA / Treasury reference the same item ID f4cd5504...96097). Polygon
geometry, 8,765 features, fields: GEOID10, STATE, COUNTY, TRACT,
STUSAB, STATE_NAME, Rural.

This is an *enrichment-only* connector — reads the per-program JSON files
from disk, computes containment for each site, and writes
`docs/data/opportunity-zone.json`. The frontend lazy-loads it and joins
onto `sitesById` by id.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import PolygonIndex

log = logging.getLogger("connector.opportunity_zone")

OZ_QUERY_URL = (
    "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/"
    "Opportunity_Zones/FeatureServer/13/query"
)
PAGE_SIZE = 2000

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


class OpportunityZone(Connector):
    slug = "opportunity-zone"
    source_label = "HUD Qualified Opportunity Zones (Treasury 2018 designation)"
    source_url = "https://opportunityzones.hud.gov/"

    # Run AFTER all producer connectors. Treasury OZ designations are stable
    # — re-running is cheap because of the cache.
    run_order = 350

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
                "no per-program JSON files found in %s — run --all (or each "
                "producer connector individually) before --source opportunity-zone",
                self._data_dir(),
            )
            return []
        log.info("loaded %d sites across %d program files",
                 len(sites), self._loaded_program_count)

        # `--missing-only`: drop sites already in the existing output.
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

        idx = self._build_oz_index(use_cache=use_cache)
        if idx.polygon_count == 0:
            log.error("OZ index empty after fetch — aborting")
            return []
        log.info("[opportunity-zone] indexed %d polygons", idx.polygon_count)

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        in_oz = 0
        rural_oz = 0
        # Per-program telemetry.
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
            hit = idx.containing(lat_f, lon_f)
            rec: dict[str, Any] = {"id": sid, "program": program}
            if hit is not None:
                # Hit is the attr dict we attached at index-build time.
                rec["in_opportunity_zone"] = True
                geoid = hit.get("geoid")
                if geoid:
                    rec["oz_tract_geoid"] = str(geoid)
                if hit.get("rural") is not None:
                    rec["oz_rural"] = bool(hit["rural"])
                in_oz += 1
                if hit.get("rural"):
                    rural_oz += 1
            else:
                rec["in_opportunity_zone"] = False
            records.append(rec)
            program_counts[program] = program_counts.get(program, 0) + 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        log.info("[opportunity-zone] %d / %d sites in a QOZ (%d rural)",
                 in_oz, len(records), rural_oz)
        log.info("enriched %d records — by program: %s",
                 len(records), program_counts)

        if getattr(args, "limit", None):
            records = records[: args.limit]

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

    def _build_oz_index(self, use_cache: bool) -> PolygonIndex:
        """Paginate HUD's OZ FeatureServer and index all polygons.

        Each feature's `rings` field is the standard ESRI polygon shape:
        `[[[lon, lat], ...], ...]` — one or more rings, first is exterior.
        We pass the rings list directly to PolygonIndex which handles holes.
        """
        log.info("[opportunity-zone] fetching from %s", OZ_QUERY_URL)
        idx = PolygonIndex()
        offset = 0
        rural_seen = 0
        while True:
            params = {
                "where": "1=1",
                "outFields": "GEOID10,STATE_NAME,COUNTY,TRACT,Rural",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometryPrecision": "6",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "f": "json",
            }
            data = self.http_get_json(
                OZ_QUERY_URL, params,
                use_cache=use_cache,
                cache_key={"src": "opportunity_zones", "offset": offset},
            )
            features = data.get("features") or []
            log.info("[opportunity-zone] page offset=%d got=%d", offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                rings = geom.get("rings") or []
                if not rings:
                    continue
                a = feat.get("attributes") or {}
                rural_raw = a.get("Rural")
                # HUD ships Rural as either "Y"/"N" string, "Yes"/"No", or
                # 1/0 integer — handle all three so a schema drift doesn't
                # silently flip the flag.
                rural: bool | None = None
                if rural_raw is not None:
                    if isinstance(rural_raw, str):
                        s = rural_raw.strip().upper()
                        if s in ("Y", "YES", "1", "TRUE"):
                            rural = True
                        elif s in ("N", "NO", "0", "FALSE", ""):
                            rural = False
                    elif isinstance(rural_raw, (int, float)):
                        rural = bool(int(rural_raw))
                if rural:
                    rural_seen += 1
                attr = {
                    "geoid": a.get("GEOID10"),
                    "state": a.get("STATE_NAME"),
                    "county": a.get("COUNTY"),
                    "tract": a.get("TRACT"),
                    "rural": rural,
                }
                idx.add_polygon(rings, attr=attr)
            if len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        log.info("[opportunity-zone] %d / %d polygons flagged rural",
                 rural_seen, idx.polygon_count)
        return idx
