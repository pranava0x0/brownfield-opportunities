"""Census TIGERweb AIANNHA containment for every corpus site.

This is consultation-planning context, not land title and not a conclusion
about which governments an agency must consult. Six current TIGERweb layers
are bulk-fetched once, indexed locally, then joined by point containment.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import PolygonIndex

log = logging.getLogger("connector.tribal_areas")

SERVICE = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/AIANNHA/MapServer"
LAYERS = {
    0: "Alaska Native Regional Corporation",
    1: "Tribal Subdivision",
    2: "Federal American Indian Reservation",
    3: "Off-Reservation Trust Land",
    4: "State American Indian Reservation",
    5: "Hawaiian Home Land",
}
PAGE_SIZE = 1000
PROGRAM_FILES = ["superfund-npl.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json"]


class TribalAreas(Connector):
    slug = "tribal-areas"
    source_label = "Census TIGERweb American Indian, Alaska Native, and Native Hawaiian Areas"
    source_url = "https://tigerweb.geo.census.gov/tigerwebmain/TIGERweb_restmapservice.html"
    run_order = 365

    @classmethod
    def add_cli_args(cls, parser: argparse.ArgumentParser) -> None:
        existing = {action.dest for action in parser._actions}
        if "limit" not in existing:
            parser.add_argument("--limit", type=int, default=None)

    @staticmethod
    def _data_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "docs" / "data"

    def _load_sites(self) -> Iterable[dict[str, Any]]:
        for filename in PROGRAM_FILES:
            path = self._data_dir() / filename
            if not path.exists():
                continue
            payload = json.loads(path.read_text())
            yield from payload.get("sites") or []

    def _build_index(self, use_cache: bool) -> PolygonIndex:
        index = PolygonIndex()
        successful_layers = 0
        for layer_id, category in LAYERS.items():
            offset = 0
            layer_count = 0
            while True:
                params = {
                    "where": "1=1",
                    "outFields": "NAME,BASENAME,GEOID,LSADC",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "geometryPrecision": "5",
                    "resultRecordCount": str(PAGE_SIZE),
                    "resultOffset": str(offset),
                    "f": "json",
                }
                data = self.http_get_json(
                    f"{SERVICE}/{layer_id}/query", params, use_cache=use_cache,
                    cache_key={"src": "tribal_areas", "layer": layer_id, "offset": offset},
                )
                features = data.get("features") or []
                for feature in features:
                    rings = (feature.get("geometry") or {}).get("rings") or []
                    attrs = feature.get("attributes") or {}
                    if index.add_polygon(rings, attr={
                        "name": attrs.get("NAME") or attrs.get("BASENAME") or "Unnamed area",
                        "geoid": attrs.get("GEOID"),
                        "category": category,
                    }):
                        layer_count += 1
                if len(features) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE
            log.info("[tribal-areas] %s: %d polygons", category, layer_count)
            successful_layers += 1
        if successful_layers != len(LAYERS):
            raise RuntimeError("not all TIGERweb tribal layers completed")
        return index

    def fetch_records(self, args: argparse.Namespace, use_cache: bool) -> list[dict[str, Any]]:
        sites = list(self._load_sites())
        if not sites:
            log.error("no program files available; run producer connectors first")
            return []
        index = self._build_index(use_cache)
        if not index.polygon_count:
            log.error("tribal-area index empty; refusing an all-false output")
            return []
        records = []
        examined = 0
        for site in sites:
            if not site.get("id") or site.get("lat") is None or site.get("lon") is None:
                continue
            examined += 1
            hits = index.containing_all(float(site["lat"]), float(site["lon"]))
            unique = []
            seen = set()
            for hit in hits:
                key = (hit.get("geoid"), hit.get("category"), hit.get("name"))
                if key in seen:
                    continue
                seen.add(key)
                unique.append(hit)
            # Sparse positive-only enrichment. The UI only makes a positive
            # consultation-context claim; emitting 44k explicit false rows
            # added 4 MB and a full-corpus join to every page load.
            if unique:
                records.append({
                    "id": site["id"],
                    "program": site["program"],
                    "in_aiannha_area": True,
                    "aiannha_area_count": len(unique),
                    "aiannha_areas": unique,
                })
        if getattr(args, "limit", None):
            records = records[: args.limit]
        log.info("[tribal-areas] %d sites examined; %d mapped hits", examined, len(records))
        return records
