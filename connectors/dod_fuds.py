"""DOD FUDS (Formerly Used Defense Sites) connector.

Source: USACE ArcGIS FeatureServer — point geometry, ~10k properties.
These are properties the DOD formerly owned/leased, now administered by USACE
for environmental cleanup. Distinct from Superfund: most are not on the NPL,
many are rural, and UXO/munitions cleanup is common.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from connectors.base import Connector

log = logging.getLogger("connector.dod_fuds")

FUDS_FEATURE_SERVER = (
    "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/"
    "fuds/FeatureServer/1"
)
QUERY_URL = FUDS_FEATURE_SERVER + "/query"
PAGE_SIZE = 2000

OUTFIELDS = [
    "OBJECTID",
    "DODFUDSPROPERTYIDPK",
    "FEATURENAME",
    "CLOSESTCITY",
    "COUNTY",
    "STATE",
    "EPAREGION",
    "LATITUDE",
    "LONGITUDE",
    "STATUS",
    "STATUSCODE",
    "ELIGIBILITY",
    "CURRENTOWNER",
    "HAS_PROJECTS",
    "CONGRESSIONALDISTRICT",
    "EMSMGMTACTIONPLANLINK",
    "FISCALYEAR",
]

DROP_RATIO_WARN_THRESHOLD = 0.5


class DodFuds(Connector):
    slug = "dod-fuds"
    source_label = "USACE Formerly Used Defense Sites (FUDS) FY24"
    source_url = (
        "https://geospatial-usace.opendata.arcgis.com/maps/"
        "3f8354667d5b4b1b8ad7a6e00c3cf3b1"
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
        p.add_argument(
            "--fuds-state",
            default=None,
            help="Two-letter state code filter for FUDS (e.g. CA). Default: all states.",
        )
        p.add_argument(
            "--fuds-eligible-only",
            action="store_true",
            default=False,
            help="Only include FUDS properties with Eligible status.",
        )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        state_filter = (getattr(args, "fuds_state", None) or "").strip().lower() or None
        raw_features = self._fetch_features(use_cache=use_cache, state=state_filter)

        eligible_only = getattr(args, "fuds_eligible_only", False)
        records: list[dict[str, Any]] = []
        dropped = 0
        for feat in raw_features:
            rec = self.normalize(feat, eligible_only=eligible_only)
            if rec is None:
                dropped += 1
                continue
            records.append(rec)

        total = len(raw_features)
        if total > 0 and dropped / total > DROP_RATIO_WARN_THRESHOLD:
            log.warning(
                "dropped %d/%d features during normalize (%.0f%%) — investigate source",
                dropped, total, 100 * dropped / total,
            )

        records.sort(key=lambda r: ((r.get("state") or "").upper(),
                                    (r.get("name") or "").lower()))

        if getattr(args, "limit", None):
            records = records[: args.limit]

        log.info("normalized %d records (dropped %d)", len(records), dropped)
        return records

    def _fetch_features(
        self, use_cache: bool, state: str | None = None
    ) -> list[dict[str, Any]]:
        all_features: list[dict[str, Any]] = []
        offset = 0
        where = "1=1" if not state else f"STATE='{state}'"
        while True:
            params = {
                "where": where,
                "outFields": ",".join(OUTFIELDS),
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            }
            data = self.http_get_json(QUERY_URL, params, use_cache=use_cache)
            page = data.get("features", [])
            log.info("page offset=%d got=%d", offset, len(page))
            if not page:
                break
            all_features.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        log.info("retrieved %d total features", len(all_features))
        return all_features

    @staticmethod
    def normalize(
        feature: dict[str, Any],
        eligible_only: bool = False,
    ) -> dict[str, Any] | None:
        a = feature.get("attributes", {}) or {}
        geom = feature.get("geometry") or {}

        property_id = a.get("DODFUDSPROPERTYIDPK")
        if property_id is None:
            return None

        eligibility = a.get("ELIGIBILITY")
        if eligible_only and eligibility != "Eligible":
            return None

        lat = geom.get("y") or a.get("LATITUDE")
        lon = geom.get("x") or a.get("LONGITUDE")
        if lat is None or lon is None:
            return None
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return None
        if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
            return None
        if abs(lat_f) < 0.5 and abs(lon_f) < 0.5:
            return None

        state = (a.get("STATE") or "").upper() or None

        region_raw = a.get("EPAREGION")
        region: int | None = None
        if region_raw is not None:
            try:
                region = int(region_raw)
            except (TypeError, ValueError):
                pass

        profile_url = a.get("EMSMGMTACTIONPLANLINK") or None

        record_id = f"FUDS-{property_id}"
        return {
            "id": record_id,
            "program": "fuds",
            "name": a.get("FEATURENAME"),
            "city": a.get("CLOSESTCITY"),
            "county": a.get("COUNTY"),
            "state": state,
            "region": region,
            "lat": round(lat_f, 6),
            "lon": round(lon_f, 6),
            "profile_url": profile_url,
            "current_owner": a.get("CURRENTOWNER"),
            "eligibility": eligibility,
            "fuds_status": a.get("STATUS"),
            "has_projects": a.get("HAS_PROJECTS"),
            "congressional_district": a.get("CONGRESSIONALDISTRICT"),
            "npl_status": a.get("STATUSCODE"),
        }
