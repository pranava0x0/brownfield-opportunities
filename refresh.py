"""Refresh Superfund site data for the dashboard.

Pulls EPA's NPL Superfund Site Boundaries layer (FeatureServer), filters
to features with acreage, sorts by area desc, takes the top N, and writes
a single JSON file consumed by the static frontend.

Usage:
    python refresh.py                # default: top 100 by acreage, all NPL statuses
    python refresh.py --limit 200
    python refresh.py --fetch-only   # cache raw API response, skip JSON write
    python refresh.py --dry-run      # use cached data only

Source:
    https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/
        FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import requests

# ----- Constants -----
ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache"
OUTPUT_PATH = ROOT / "docs" / "data" / "sites.json"

EPA_FEATURE_SERVER = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0/query"
)
SOURCE_LABEL = "EPA NPL Superfund Site Boundaries (Public)"
SOURCE_URL = (
    "https://hub.arcgis.com/datasets/EPA::"
    "npl-superfund-site-boundaries-epa-public-2022/about"
)

# NPL status codes from the layer's coded-value domain.
NPL_STATUS_LABELS: dict[str, str] = {
    "A": "Site is Part of NPL Site",
    "D": "Deleted from the Final NPL",
    "F": "Currently on the Final NPL",
    "N": "Not on the NPL",
    "O": "Not Valid Site or Incident",
    "P": "Proposed for NPL",
    "R": "Removed from Proposed",
}

OUTFIELDS = [
    "OBJECTID",
    "EPA_ID",
    "SITE_NAME",
    "NPL_STATUS_CODE",
    "FEDERAL_FACILITY_DETER_CODE",
    "REGION_CODE",
    "STREET_ADDR_TXT",
    "CITY_NAME",
    "COUNTY",
    "STATE_CODE",
    "ZIP_CODE",
    "GIS_AREA",
    "GIS_AREA_UNITS",
    "URL_ALIAS_TXT",
    "FEATURE_INFO_URL",
    "LAST_CHANGE_DATE",
    "ORIGINAL_CREATION_DATE",
]

USER_AGENT = "BrownfieldOpportunities/0.1 (research; static dashboard)"
REQUEST_TIMEOUT_S = 60
REQUEST_DELAY_S = 1.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("refresh")


# ----- Helpers -----
def _cache_path(params: dict[str, Any]) -> Path:
    key = hashlib.sha256(
        json.dumps(params, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return CACHE_DIR / f"epa_superfund_{key}.json"


def fetch(params: dict[str, Any], use_cache: bool = True) -> dict[str, Any]:
    """GET the EPA FeatureServer with disk caching."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(params)
    if use_cache and path.exists():
        log.info("cache hit  %s", path.name)
        return json.loads(path.read_text())

    log.info("fetching   %s", params.get("orderByFields") or params.get("where"))
    time.sleep(REQUEST_DELAY_S)
    resp = requests.get(
        EPA_FEATURE_SERVER,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"EPA API error: {data['error']}")
    path.write_text(json.dumps(data))
    log.info("cached     %s (%d features)", path.name, len(data.get("features", [])))
    return data


def envelope_center(rings: list[list[list[float]]]) -> tuple[float, float]:
    """Compute polygon envelope (bounding-box) center.

    Good enough for marker placement on a country-wide map. Polygon
    rendering is a backlog item.
    """
    xs: list[float] = []
    ys: list[float] = []
    for ring in rings:
        for x, y in ring:
            xs.append(x)
            ys.append(y)
    if not xs:
        raise ValueError("empty geometry")
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def normalize(feature: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one ArcGIS feature to our flat record shape."""
    a = feature.get("attributes", {})
    geom = feature.get("geometry") or {}
    rings = geom.get("rings")
    if not rings:
        return None

    units = a.get("GIS_AREA_UNITS")
    raw_area = a.get("GIS_AREA")
    acres: float | None
    if units == "Acres" and raw_area is not None:
        acres = float(raw_area)
    elif units == "Square Miles" and raw_area is not None:
        acres = float(raw_area) * 640.0
    else:
        acres = None  # exclude from "by acreage" sort

    if acres is None:
        return None

    lon, lat = envelope_center(rings)
    status_code = a.get("NPL_STATUS_CODE")
    profile_url = a.get("URL_ALIAS_TXT") or a.get("FEATURE_INFO_URL")

    return {
        "epa_id": a.get("EPA_ID"),
        "name": a.get("SITE_NAME"),
        "acreage": round(acres, 1),
        "npl_status_code": status_code,
        "npl_status": NPL_STATUS_LABELS.get(status_code or "", "Unknown"),
        "federal_facility": a.get("FEDERAL_FACILITY_DETER_CODE"),
        "region": a.get("REGION_CODE"),
        "address": a.get("STREET_ADDR_TXT"),
        "city": a.get("CITY_NAME"),
        "county": a.get("COUNTY"),
        "state": a.get("STATE_CODE"),
        "zip": a.get("ZIP_CODE"),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "profile_url": profile_url,
        "last_updated": a.get("LAST_CHANGE_DATE"),
        # Fields documented in backlog as TBD:
        "current_owner": None,
        "historical_owners": None,
        "encumbrances": None,
        "remediation_detail": None,
        "proximity": None,
    }


def fetch_top_n(limit: int, use_cache: bool) -> list[dict[str, Any]]:
    """Fetch sites ordered by GIS_AREA desc; over-fetch to allow filtering."""
    # Fetch a bit more than `limit` because some features lack acreage units
    # we accept (Miles, null).
    over_fetch = min(limit * 3, 600)
    params = {
        "where": "GIS_AREA IS NOT NULL AND GIS_AREA > 0",
        "outFields": ",".join(OUTFIELDS),
        "orderByFields": "GIS_AREA DESC",
        "resultRecordCount": str(over_fetch),
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    data = fetch(params, use_cache=use_cache)
    features = data.get("features", [])
    log.info("retrieved  %d raw features", len(features))

    records: list[dict[str, Any]] = []
    for feat in features:
        rec = normalize(feat)
        if rec is not None:
            records.append(rec)
        if len(records) >= limit:
            break
    log.info("normalized %d records", len(records))
    return records


def write_output(records: list[dict[str, Any]], limit: int) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": SOURCE_LABEL,
        "source_url": SOURCE_URL,
        "limit": limit,
        "count": len(records),
        "sites": records,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    log.info("wrote      %s (%d sites)", OUTPUT_PATH, len(records))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=100,
                   help="number of top sites by acreage (default 100)")
    p.add_argument("--fetch-only", action="store_true",
                   help="fetch + cache raw API response; do not write JSON")
    p.add_argument("--dry-run", action="store_true",
                   help="use cached data only; never hit the network")
    p.add_argument("--no-cache", action="store_true",
                   help="ignore cache; force a fresh fetch")
    args = p.parse_args()

    use_cache = not args.no_cache
    if args.dry_run:
        # dry-run requires a prior cache; if missing, fetch() will hit the net.
        # Block that explicitly.
        if not any(CACHE_DIR.glob("epa_superfund_*.json")):
            log.error("dry-run: no cached EPA response found in %s", CACHE_DIR)
            return 2

    records = fetch_top_n(args.limit, use_cache=use_cache)
    if args.fetch_only:
        log.info("--fetch-only: skipping output write")
        return 0
    if not records:
        log.error("no records normalized; aborting")
        return 1
    write_output(records, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
