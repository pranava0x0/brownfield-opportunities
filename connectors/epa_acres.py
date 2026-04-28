"""EPA ACRES (Brownfields) Properties connector.

Source: ArcGIS FeatureServer hosted by EPA — point geometry, ~36k records.
Distinct from Superfund NPL: smaller properties, often urban, further along
in cleanup. ACRES has no acreage column (point features only) and no NPL
status; records land in the dashboard's "N/A acreage" bucket and carry
`program: "brownfield"`.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from connectors.base import Connector

log = logging.getLogger("connector.epa_acres")

# URL-encoded once because the service name has spaces.
ACRES_FEATURE_SERVER = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "All%20ACRES%20Properties%208_30_2021/FeatureServer/0"
)
QUERY_URL = ACRES_FEATURE_SERVER + "/query"
PAGE_SIZE = 1000  # service caps at 1000

# EPA ACRES property profile — `acres_id` corresponds to PROPERTY_ID.
ACRES_PROFILE_URL_TEMPLATE = "https://acres6.epa.gov/acres/cms/PropertyProfileReports/Output/{property_id}.html"

OUTFIELDS = [
    "PROPERTY_ID",
    "PROPERTY_NAME",
    "RS_REGION_ID_1000",
    "LABEL_STATE",
    "ADDRESS1",
    "CITY",
    "COUNTY",
    "ZIP_CODE",
    "LATITUDE_MEASURE",
    "LONGITUDE_MEASURE",
]

DROP_RATIO_WARN_THRESHOLD = 0.5


class EpaAcres(Connector):
    slug = "epa-acres"
    source_label = "EPA ACRES Brownfield Properties"
    source_url = (
        "https://www.epa.gov/cleanups/"
        "assessment-cleanup-and-redevelopment-exchange-system-acres"
    )

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        # Reuse `--limit` if SuperfundNPL already registered it; otherwise add.
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument(
                "--limit",
                type=int,
                default=None,
                help="Cap the number of sites (default: unlimited).",
            )
        p.add_argument(
            "--acres-state",
            default=None,
            help="Two-letter state code filter for ACRES (e.g. NY). Default: all states.",
        )

    # ----- main entry point -----

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        state_filter = (getattr(args, "acres_state", None) or "").strip().upper() or None
        raw_features = self._fetch_features(use_cache=use_cache, state=state_filter)

        records: list[dict[str, Any]] = []
        dropped = 0
        for feat in raw_features:
            rec = self.normalize(feat)
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

        # Stable sort: state, then name. Useful for diffability of the JSON.
        records.sort(key=lambda r: ((r.get("state") or "").upper(),
                                    (r.get("name") or "").lower()))

        if getattr(args, "limit", None):
            records = records[: args.limit]

        log.info("normalized %d records (dropped %d)", len(records), dropped)
        return records

    # ----- fetch helpers -----

    def _fetch_features(
        self, use_cache: bool, state: str | None = None
    ) -> list[dict[str, Any]]:
        all_features: list[dict[str, Any]] = []
        offset = 0
        where = "1=1" if not state else f"LABEL_STATE='{state}'"
        while True:
            params = {
                "where": where,
                "outFields": ",".join(OUTFIELDS),
                "orderByFields": "PROPERTY_ID ASC",
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

    # ----- normalize -----

    @staticmethod
    def normalize(feature: dict[str, Any]) -> dict[str, Any] | None:
        a = feature.get("attributes", {}) or {}
        geom = feature.get("geometry") or {}

        property_id = a.get("PROPERTY_ID")
        if property_id is None:
            return None

        # Coordinates: prefer the geometry payload; fall back to the
        # LATITUDE_MEASURE / LONGITUDE_MEASURE attribute fields.
        lat = geom.get("y")
        lon = geom.get("x")
        if lat is None or lon is None:
            lat = a.get("LATITUDE_MEASURE")
            lon = a.get("LONGITUDE_MEASURE")
        if lat is None or lon is None:
            return None
        # Filter out null-island and obviously bad values.
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return None
        if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
            return None
        if abs(lat_f) < 0.5 and abs(lon_f) < 0.5:
            return None

        record_id = f"ACRES-{property_id}"
        return {
            "id": record_id,
            "program": "brownfield",
            "name": a.get("PROPERTY_NAME"),
            "region": a.get("RS_REGION_ID_1000"),
            "state": a.get("LABEL_STATE"),
            "address": a.get("ADDRESS1"),
            "city": a.get("CITY"),
            "county": a.get("COUNTY"),
            "zip": a.get("ZIP_CODE"),
            "lat": round(lat_f, 6),
            "lon": round(lon_f, 6),
            "profile_url": ACRES_PROFILE_URL_TEMPLATE.format(property_id=property_id),
            # acreage / NPL status / federal-facility do not apply.
        }
