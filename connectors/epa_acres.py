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
from pathlib import Path
from typing import Any

from connectors.base import Connector
from connectors.text import collapse_sentinel
from connectors.county_lookup import CountyIndex

log = logging.getLogger("connector.epa_acres")

# TIGER counties TopoJSON ships with the frontend; we re-use it for offline
# reverse-geocoding. Lives in docs/data alongside the per-program JSON files.
COUNTIES_TOPOJSON = (
    Path(__file__).resolve().parent.parent / "docs" / "data" / "us-counties-topo.json"
)

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
    authoritative_inventory = True
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

        # Fill missing county via TIGER spatial join. The ACRES FeatureServer
        # omits COUNTY for ~51% of records (worst in CA/TX/FL/MA/MN); every
        # record carries valid lat/lon so an offline point-in-polygon hit is
        # almost always available. ~17ms per lookup on a warm index → ~few
        # seconds for the full 36k pass.
        self._fill_missing_county(records)

        # Stable sort: state, then name. Useful for diffability of the JSON.
        records.sort(key=lambda r: ((r.get("state") or "").upper(),
                                    (r.get("name") or "").lower()))

        if getattr(args, "limit", None):
            records = records[: args.limit]

        log.info("normalized %d records (dropped %d)", len(records), dropped)
        return records

    @staticmethod
    def _fill_missing_county(records: list[dict[str, Any]]) -> None:
        """Reverse-geocode lat/lon → county for records missing the field.

        Builds the TIGER index lazily so callers that don't need it (tests,
        narrow runs) don't pay the decode cost. Mutates `records` in place.
        """
        needs_fill = [r for r in records if not r.get("county")]
        if not needs_fill:
            return
        if not COUNTIES_TOPOJSON.exists():
            log.warning("counties topojson missing at %s — skipping county fill",
                        COUNTIES_TOPOJSON)
            return
        log.info("county fill: %d records missing county; loading TIGER index",
                 len(needs_fill))
        idx = CountyIndex.from_path(COUNTIES_TOPOJSON)
        filled = 0
        for r in needs_fill:
            lat = r.get("lat")
            lon = r.get("lon")
            if lat is None or lon is None:
                continue
            name = idx.lookup(lat, lon, expected_state=r.get("state"))
            if name:
                r["county"] = name
                filled += 1
        log.info("county fill: filled %d/%d records (%.1f%% of missing)",
                 filled, len(needs_fill), 100 * filled / len(needs_fill))

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
            "address": collapse_sentinel(a.get("ADDRESS1")),
            "city": collapse_sentinel(a.get("CITY")),
            "county": collapse_sentinel(a.get("COUNTY")),
            "zip": a.get("ZIP_CODE"),
            "lat": round(lat_f, 6),
            "lon": round(lon_f, 6),
            "profile_url": ACRES_PROFILE_URL_TEMPLATE.format(property_id=property_id),
            # acreage / NPL status / federal-facility do not apply.
        }
