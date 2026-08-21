"""DOD BRAC (Base Realignment and Closure) connector.

Source: ArcGIS FeatureServer — USA Military Bases with BRAC_SITE flag.
Polygon geometry for ~27 installations closed/realigned across five BRAC
rounds (1988–2005). These are large-acreage former military installations,
many with explicit redevelopment targets.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from connectors.base import Connector
from connectors.geom import (
    ACRES_PER_SQ_METER,
    envelope_center,
    polygon_area_sq_meters,
)

log = logging.getLogger("connector.dod_brac")

MILBASES_FEATURE_SERVER = (
    "https://services.arcgis.com/hRUr1F8lE8Jq2uJo/arcgis/rest/services/"
    "milbases/FeatureServer/0"
)
QUERY_URL = MILBASES_FEATURE_SERVER + "/query"

OUTFIELDS = [
    "OBJECTID",
    "COMPONENT",
    "SITE_NAME",
    "JOINT_BASE",
    "STATE_TERR",
    "BRAC_SITE",
    "STPOSTAL",
]

class DodBrac(Connector):
    slug = "dod-brac"
    authoritative_inventory = True
    source_label = "DOD BRAC Military Installations"
    source_url = (
        "https://hub.arcgis.com/datasets/"
        "dd4f072ae4514c1faedb6d070623eca1_0/about"
    )

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument(
                "--limit",
                type=int,
                default=None,
                help="Cap the number of sites (default: unlimited).",
            )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        raw_features = self._fetch_features(use_cache=use_cache)

        records: list[dict[str, Any]] = []
        dropped = 0
        for feat in raw_features:
            rec = self.normalize(feat)
            if rec is None:
                dropped += 1
                continue
            records.append(rec)

        records.sort(
            key=lambda r: (
                r["acreage"] is None,
                -(r["acreage"] or 0),
                (r.get("name") or "").lower(),
            )
        )

        if getattr(args, "limit", None):
            records = records[: args.limit]

        log.info("normalized %d BRAC records (dropped %d)", len(records), dropped)
        return records

    def _fetch_features(self, use_cache: bool) -> list[dict[str, Any]]:
        params = {
            "where": "BRAC_SITE='YES'",
            "outFields": ",".join(OUTFIELDS),
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        }
        data = self.http_get_json(QUERY_URL, params, use_cache=use_cache)
        features = data.get("features", [])
        log.info("retrieved %d BRAC features", len(features))
        return features

    # Polygon math now lives in connectors.geom — see envelope_center +
    # polygon_area_sq_meters. Re-exported as static methods for the existing
    # test surface so tests/test_brac.py continues to import them as before.
    envelope_center = staticmethod(envelope_center)
    polygon_area_sq_meters = staticmethod(polygon_area_sq_meters)

    def normalize(self, feature: dict[str, Any]) -> dict[str, Any] | None:
        a = feature.get("attributes", {}) or {}
        geom = feature.get("geometry") or {}
        rings = geom.get("rings")
        if not rings:
            return None

        try:
            lon, lat = envelope_center(rings)
        except ValueError:
            return None

        area_sq_m = polygon_area_sq_meters(rings)
        acreage = round(area_sq_m * ACRES_PER_SQ_METER, 1) if area_sq_m > 0 else None

        site_name = a.get("SITE_NAME")
        if not site_name:
            return None

        state = a.get("STPOSTAL") or None
        record_id = f"BRAC-{a.get('OBJECTID', site_name.replace(' ', '_'))}"

        return {
            "id": record_id,
            "program": "brac",
            "name": site_name,
            "acreage": acreage,
            "state": state,
            "component": a.get("COMPONENT"),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
        }
