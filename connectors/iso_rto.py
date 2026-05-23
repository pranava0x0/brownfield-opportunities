"""ISO/RTO region attribution.

Assigns lower-48 sites to the regional transmission organization /
independent system operator polygon they sit inside: PJM, MISO, ERCOT,
CAISO, SPP, NYISO, ISO-NE, or `non-RTO` when no polygon covers the point.

The official EIA Atlas item (`eia::rto-regions`) is public in metadata but
permission-blocked for anonymous API reads. Its metadata credits EIA/HIFLD
and documents the same fields used here (`RTO_ISO`, `LOC_TYPE`, `LOC_NAME`).
This connector fetches a public ArcGIS mirror with those fields and treats
the EIA/HIFLD metadata as the authoritative source description.

RTO polygons are approximate: EIA notes that RTOs do not all have strict
geographic boundaries, and the shapefiles may overlap or have gaps. We use
them as a speed-to-power screening signal, not a legal service-territory map.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import PolygonIndex

log = logging.getLogger("connector.iso_rto")

RTO_QUERY_URL = (
    "https://services3.arcgis.com/dNDFv7tc3OwOgyit/arcgis/rest/services/"
    "RTO_Regions/FeatureServer/0/query"
)
PAGE_SIZE = 2000

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]

LOWER_48_AND_DC = {
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
    "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}

RTO_CODE_NORMALIZATION = {
    "ISONE": "ISO-NE",
    "ISO-NE": "ISO-NE",
    "NYISO": "NYISO",
    "PJM": "PJM",
    "MISO": "MISO",
    "ERCOT": "ERCOT",
    "CAISO": "CAISO",
    "SPP": "SPP",
}

LOC_TYPE_PRIORITY = {"REG": 0, "ZON": 1, "HUB": 2}


class IsoRto(Connector):
    slug = "iso-rto"
    source_label = "EIA/HIFLD RTO Regions"
    source_url = "https://atlas.eia.gov/datasets/eia::rto-regions/about"

    # Run after producer connectors and other fast spatial enrichments.
    run_order = 365

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
            log.error("ISO/RTO index empty after fetch — aborting")
            return []
        log.info("[iso-rto] indexed %d polygons", idx.polygon_count)

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        skipped_outside_scope = 0
        counts: dict[str, int] = {}
        for site in sites:
            sid = site.get("id")
            program = site.get("program")
            state = site.get("state")
            lat = site.get("lat")
            lon = site.get("lon")
            if not sid or not program or lat is None or lon is None:
                skipped_no_geom += 1
                continue
            if state not in LOWER_48_AND_DC:
                skipped_outside_scope += 1
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                skipped_no_geom += 1
                continue
            matches = idx.containing_all(lat_f, lon_f)
            picked = _pick_rto(matches)
            rto = picked["iso_rto"] if picked else "non-RTO"
            records.append({"id": sid, "program": program, "iso_rto": rto})
            counts[rto] = counts.get(rto, 0) + 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        if skipped_outside_scope:
            log.info("skipped %d sites outside lower-48/DC RTO source scope", skipped_outside_scope)
        log.info("enriched %d records — ISO/RTO counts: %s", len(records), counts)

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
                "outFields": "RTO_ISO,LOC_ABBREV,NAME,LOC_TYPE,LOC_NAME,ALIAS,LOC_NAME_T",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometryPrecision": "6",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "f": "json",
            }
            data = self.http_get_json(
                RTO_QUERY_URL,
                params,
                use_cache=use_cache,
                cache_key={"src": "iso_rto", "offset": offset},
            )
            features = data.get("features") or []
            log.info("[iso-rto] page offset=%d got=%d", offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                rings = geom.get("rings") or []
                if not rings:
                    continue
                attrs = feat.get("attributes") or {}
                rto = _normalize_rto(attrs.get("RTO_ISO"))
                if not rto:
                    continue
                idx.add_polygon(
                    rings,
                    attr={
                        "iso_rto": rto,
                        "loc_type": _clean_str(attrs.get("LOC_TYPE")),
                        "loc_name": _clean_str(attrs.get("LOC_NAME_T"))
                                    or _clean_str(attrs.get("LOC_NAME"))
                                    or _clean_str(attrs.get("NAME")),
                    },
                )
            if len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return idx


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_rto(value: Any) -> str | None:
    text = _clean_str(value)
    if not text:
        return None
    return RTO_CODE_NORMALIZATION.get(text.upper(), text.upper())


def _pick_rto(matches: list[object]) -> dict[str, Any] | None:
    typed = [m for m in matches if isinstance(m, dict) and m.get("iso_rto")]
    if not typed:
        return None
    typed.sort(
        key=lambda m: (
            LOC_TYPE_PRIORITY.get(str(m.get("loc_type") or "").upper(), 9),
            str(m.get("iso_rto")),
            str(m.get("loc_name") or ""),
        )
    )
    return typed[0]
