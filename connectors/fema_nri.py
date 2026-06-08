"""FEMA National Risk Index (NRI) enrichment.

Joins county-level natural-hazard risk onto every site by point-in-polygon
containment against FEMA's NRI county FeatureServer. One layer covers all 18
NRI hazards; we surface the composite plus the three hazards that actually
move a data-center / energy-infra siting decision:

- **Wildfire** — the marquee climate hazard. A Very-High wildfire county is
  an insurability and business-continuity problem for critical infra.
- **Drought** — proxy for cooling-water availability stress (evaporative
  cooling is ~1.8 L/kWh; a drought-stressed basin can't sustain it).
- **Heat wave** — raises cooling load and cuts free-cooling hours, hurting
  PUE. Displayed for context; not penalized in scoring.

Structural hazards (earthquake, hurricane, tornado, flooding) are folded
into the composite `RISK_SCORE` rather than surfaced individually — flood
already has a dedicated FEMA NFHL layer (`flood_zone` / `in_sfha`), and
seismic has its own backlog item (USGS ASCE 7-22).

FEMA's official **rating buckets** are carried verbatim ('Very Low' →
'Very High' / 'Insufficient Data') rather than re-derived from the score —
the buckets are percentile breaks against the national distribution, not a
simple score threshold, so re-deriving them would drift from FEMA's
published rating.

Source: FEMA NRI county FeatureServer on ArcGIS Online
(`services.arcgis.com/XG15cJAlne2vxtgt/.../National_Risk_Index_Counties`,
3,232 counties, polygon geometry). The legacy `hazards.fema.gov/nri`
download portal 301-redirects post-2025; this hosted layer is the working
endpoint.

This is an *enrichment-only* connector — reads the per-program JSON files
from disk, computes containment for each site, and writes
`docs/data/fema-nri.json`. The frontend lazy-loads it and joins onto
`sitesById` by id.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import PolygonIndex

log = logging.getLogger("connector.fema_nri")

NRI_QUERY_URL = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
    "National_Risk_Index_Counties/FeatureServer/0/query"
)
PAGE_SIZE = 1000  # geometry-heavy county polygons — keep pages modest

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _rating(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


class FemaNri(Connector):
    slug = "fema-nri"
    source_label = "FEMA National Risk Index (county, 2024)"
    source_url = "https://hazards.fema.gov/nri/"

    # After IRA energy community (355); FEMA NRI ratings update ~annually.
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
                "no per-program JSON files found in %s — run --all (or each "
                "producer connector individually) before --source fema-nri",
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

        idx = self._build_nri_index(use_cache=use_cache)
        if idx.polygon_count == 0:
            log.error("NRI index empty after fetch — aborting")
            return []
        log.info("[fema-nri] indexed %d county polygons", idx.polygon_count)

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        matched = 0
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
            hit = idx.containing(lat_f, lon_f)
            if hit is not None:
                # Only attach fields that carry a value — keeps the payload
                # compact and lets `exclude_none` drop the rest.
                for k in ("nri_risk_score", "nri_risk_rating",
                          "nri_wildfire_rating", "nri_drought_rating",
                          "nri_heatwave_rating"):
                    if hit.get(k) is not None:
                        rec[k] = hit[k]
                if len(rec) > 2:
                    matched += 1
            records.append(rec)
            program_counts[program] = program_counts.get(program, 0) + 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        log.info("[fema-nri] %d / %d sites matched a county risk record",
                 matched, len(records))
        log.info("enriched %d records — by program: %s", len(records), program_counts)

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

    def _build_nri_index(self, use_cache: bool) -> PolygonIndex:
        """Paginate FEMA's NRI county FeatureServer and index all polygons.

        Each feature carries the composite + per-hazard risk ratings we keep
        as the polygon attr, so a point-in-polygon hit directly yields the
        site's county risk record — no separate FIPS join needed.
        """
        log.info("[fema-nri] fetching from %s", NRI_QUERY_URL)
        idx = PolygonIndex()
        offset = 0
        while True:
            params = {
                "where": "1=1",
                "outFields": "STCOFIPS,RISK_SCORE,RISK_RATNG,"
                             "WFIR_RISKR,DRGT_RISKR,HWAV_RISKR",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometryPrecision": "5",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "f": "json",
            }
            data = self.http_get_json(
                NRI_QUERY_URL, params,
                use_cache=use_cache,
                cache_key={"src": "fema_nri_counties", "offset": offset},
            )
            features = data.get("features") or []
            log.info("[fema-nri] page offset=%d got=%d", offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                rings = geom.get("rings") or []
                if not rings:
                    continue
                a = feat.get("attributes") or {}
                attr = {
                    "fips": a.get("STCOFIPS"),
                    "nri_risk_score": _num(a.get("RISK_SCORE")),
                    "nri_risk_rating": _rating(a.get("RISK_RATNG")),
                    "nri_wildfire_rating": _rating(a.get("WFIR_RISKR")),
                    "nri_drought_rating": _rating(a.get("DRGT_RISKR")),
                    "nri_heatwave_rating": _rating(a.get("HWAV_RISKR")),
                }
                idx.add_polygon(rings, attr=attr)
            if len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return idx
