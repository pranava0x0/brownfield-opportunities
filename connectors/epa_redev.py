"""EPA Superfund Redevelopment enrichment connector.

Source: ArcGIS FeatureServer — RedevelopmentAppSitePoints, ~1,905 sites.
This isn't a standalone program — it enriches existing Superfund records
with infrastructure-proximity fields from EPA's Redevelopment mapper and
computes a `data_center_reuse_candidate` boolean.

Usage:
    python refresh.py --source epa-redev          # fetch-only enrichment data
    python refresh.py --all                        # runs as part of full refresh

The enrichment is applied by matching EPA_ID between the Superfund connector's
output and this connector's records. Records that don't match a known Superfund
site are still kept (they carry SAA sites not in the NPL boundary layer).
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from connectors.base import Connector

log = logging.getLogger("connector.epa_redev")

REDEV_FEATURE_SERVER = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "RedevelopmentAppSitePoints/FeatureServer/0"
)
QUERY_URL = REDEV_FEATURE_SERVER + "/query"
PAGE_SIZE = 1000

OUTFIELDS = [
    "OBJECTID",
    "EPA_ID",
    "Site_Name",
    "Region",
    "Address",
    "City",
    "State",
    "County",
    "ZIP",
    "Latitude",
    "Longitude",
    "NPL_Status",
    "Acres",
    "InOppZone",
    "NearRR",
    "NearHwy",
    "NearElectL",
    "PopDensity",
    "In_Reuse",
    "InWaterServiceArea",
    "NearWastewaterFacility",
    "NearWater",
    "RAU_Status",
]

DROP_RATIO_WARN_THRESHOLD = 0.5


def is_dc_candidate(rec: dict[str, Any]) -> bool:
    """Compute data-center suitability per EPA guidance criteria.

    A site qualifies when it has:
    - Power access (near electrical transmission line)
    - Sufficient acreage (>= 50 acres)
    - Water supply (within municipal water service area)
    """
    near_elec = (rec.get("near_electric_transmission") or "").startswith("Yes")
    acres = rec.get("acreage")
    has_acreage = acres is not None and acres >= 50
    water = (rec.get("near_water_supply") or "").startswith("Yes")
    return near_elec and has_acreage and water


class EpaRedev(Connector):
    slug = "epa-redev"
    source_label = "EPA Superfund Redevelopment Mapper"
    source_url = (
        "https://www.epa.gov/superfund-redevelopment/"
        "superfund-redevelopment-mapper"
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

        dc_count = sum(1 for r in records if r.get("data_center_reuse_candidate"))
        log.info(
            "normalized %d records (dropped %d), %d flagged as DC candidates",
            len(records), dropped, dc_count,
        )
        return records

    def _fetch_features(self, use_cache: bool) -> list[dict[str, Any]]:
        all_features: list[dict[str, Any]] = []
        offset = 0
        while True:
            params = {
                "where": "1=1",
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
    def normalize(feature: dict[str, Any]) -> dict[str, Any] | None:
        a = feature.get("attributes", {}) or {}
        geom = feature.get("geometry") or {}

        epa_id = a.get("EPA_ID")
        if not epa_id:
            return None

        lat = geom.get("y") or a.get("Latitude")
        lon = geom.get("x") or a.get("Longitude")
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

        raw_acres = a.get("Acres")
        acreage: float | None = None
        if raw_acres is not None:
            try:
                acreage = round(float(raw_acres), 1)
            except (TypeError, ValueError):
                pass

        region_raw = a.get("Region")
        region: int | None = None
        if region_raw is not None:
            try:
                region = int(region_raw)
            except (TypeError, ValueError):
                pass

        rec: dict[str, Any] = {
            "id": epa_id,
            "program": "superfund",
            "epa_id": epa_id,
            "name": a.get("Site_Name"),
            "acreage": acreage,
            "npl_status": a.get("NPL_Status"),
            "region": region,
            "address": a.get("Address"),
            "city": a.get("City"),
            "state": a.get("State"),
            "county": a.get("County"),
            "zip": a.get("ZIP"),
            "lat": round(lat_f, 6),
            "lon": round(lon_f, 6),
            "near_electric_transmission": a.get("NearElectL"),
            "near_highway": a.get("NearHwy"),
            "near_railroad": a.get("NearRR"),
            "near_water_supply": a.get("InWaterServiceArea"),
            "near_wastewater": a.get("NearWastewaterFacility"),
            "near_water_body": a.get("NearWater"),
            "pop_density": a.get("PopDensity"),
            "in_opp_zone": a.get("InOppZone"),
            "in_reuse": a.get("In_Reuse"),
            "rau_status": _clean_rau_status(a.get("RAU_Status")),
        }

        rec["data_center_reuse_candidate"] = is_dc_candidate(rec)

        return rec


def _clean_rau_status(raw: Any) -> str | None:
    """Normalize EPA's SWRAU status string; collapse blanks to None.

    EPA ships one of five values (incl. null). Whitespace-only or empty
    strings are treated as "not measured" rather than a literal label.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None
