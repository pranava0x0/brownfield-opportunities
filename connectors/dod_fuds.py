"""DOD FUDS (Formerly Used Defense Sites) connector.

Source: USACE ArcGIS FeatureServer.
- Layer 1 (FUDS Property Point) is the master list — ~10k properties with
  centroid coordinates, current owner, and eligibility metadata.
- Layer 4 (FUDS Property Polygon) carries property boundaries for ~3k of
  those properties. We pull this layer to compute acreage from the polygon
  geometry (Shape__Area is in degrees², so we compute m² ourselves via
  Shoelace + cos(lat) — see connectors.geom).

The two layers are joined by DODFUDSPROPERTYIDPK. Layer 1 stays the source of
truth for record identity and field values; layer 4 only contributes acreage
and a more accurate centroid where its polygon exists. Properties without a
polygon keep their point-coordinate location and `acreage: null`.

Distinct from Superfund: most FUDS are not on the NPL, many are rural, and
UXO/munitions cleanup is common.
"""
from __future__ import annotations

import argparse
import logging
import re
from typing import Any

from connectors.base import Connector
from connectors.geom import envelope_center, polygon_acreage

log = logging.getLogger("connector.dod_fuds")

FUDS_FEATURE_SERVER = (
    "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/"
    "fuds/FeatureServer"
)
POINT_QUERY_URL = FUDS_FEATURE_SERVER + "/1/query"
POLYGON_QUERY_URL = FUDS_FEATURE_SERVER + "/4/query"
PAGE_SIZE = 2000

POINT_OUTFIELDS = [
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

POLYGON_OUTFIELDS = [
    "DODFUDSPROPERTYIDPK",
    "Shape__Area",
]

DROP_RATIO_WARN_THRESHOLD = 0.5

# USACE owner codes use a `<TIER>: <CATEGORY> [<DETAIL>]` format that ships in
# raw form (e.g. "PRIV: PRIVATE   ", "FED: FEDERAL AIR FORCE  ",
# "LOCAL: CITY   ; PRIV: PRIVATE   "). We normalize to clean labels at
# ingest time so the dashboard doesn't render the raw codes — same approach
# the place-name prettifier takes for ALL CAPS city/county strings.
_OWNER_PREFIX_LABELS = {
    "PRIV": "Private",
    "LOCAL": "Local government",
    "FED": "Federal",
    "STATE": "State",
    "TRIBE": "Tribal",
    "OTHER": "Other",
}
_OWNER_TIER_RE = re.compile(r"^([A-Z]+)\s*:\s*(.*)$")
# Per-tier "category" word that the source duplicates after the colon
# (e.g. "PRIV: PRIVATE residential" → drop the leading PRIVATE). Some
# records repeat the word multiple times ("PRIV: PRIVATE PRIVATE" or
# "FED: FEDERAL FEDERAL"); the regex strips every leading occurrence so the
# detail tail starts at the first non-redundant token.
_OWNER_REDUNDANT_TAIL = {
    "PRIV": re.compile(r"^(?:PRIVATE\b\s*)+", re.IGNORECASE),
    "LOCAL": re.compile(r"^(?:LOCAL\b\s*)+", re.IGNORECASE),
    "FED": re.compile(r"^(?:FEDERAL\b\s*)+", re.IGNORECASE),
    "STATE": re.compile(r"^(?:STATE\b\s*)+", re.IGNORECASE),
    "TRIBE": re.compile(r"^(?:TRIBAL\b\s*)+", re.IGNORECASE),
    "OTHER": re.compile(r"^(?:OTHER\b\s*)+", re.IGNORECASE),
}


def _pretty_owner(raw: str | None) -> str | None:
    """Normalize a USACE owner code to a clean label.

    Examples:
        "PRIV: PRIVATE   "                       → "Private"
        "PRIV: PRIVATE RESIDENTIAL  "            → "Private — Residential"
        "FED: FEDERAL AIR FORCE  "               → "Federal — Air Force"
        "FED: FEDERAL FEDERAL"                   → "Federal"
        "LOCAL: CITY   "                         → "Local government — City"
        "STATE: STATE STATE OF HAWAII  "         → "State — State Of Hawaii"
        "OTHER: OTHER   "                        → "Other"
        "LOCAL: CITY ; PRIV: PRIVATE"            → "Local government — City / Private"
        "NPS"                                    → "NPS"
        None                                     → None
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    pieces = [p.strip() for p in text.split(";") if p.strip()]
    cleaned: list[str] = []
    for piece in pieces:
        # Collapse internal whitespace runs first.
        piece = re.sub(r"\s+", " ", piece)
        m = _OWNER_TIER_RE.match(piece)
        if not m:
            # No `TIER:` prefix — just title-case the free-text.
            cleaned.append(_titlecase_owner(piece))
            continue
        tier = m.group(1).upper()
        tail = m.group(2).strip()
        label = _OWNER_PREFIX_LABELS.get(tier)
        if not label:
            # Unknown tier — keep the raw piece (rare; agency acronyms etc.).
            cleaned.append(_titlecase_owner(piece))
            continue
        # Strip the tier's redundant category word (PRIV: PRIVATE → "").
        redundant_re = _OWNER_REDUNDANT_TAIL.get(tier)
        if redundant_re is not None:
            tail = redundant_re.sub("", tail).strip()
        if not tail:
            cleaned.append(label)
        else:
            cleaned.append(f"{label} — {_titlecase_owner(tail)}")
    if not cleaned:
        return None
    return " / ".join(cleaned)


# Acronyms / proper nouns that should stay all-caps in the cleaned label.
_OWNER_ACRONYMS = {
    "USA", "USAF", "USMC", "USDA", "USFS", "USFWS", "BLM", "NPS", "DOD",
    "VA", "GSA", "TVA", "DOE", "DOT", "EPA", "FAA", "FBI", "USPS", "AAFB",
    "AFB", "USCG", "USN", "NASA", "NRDA", "PCB", "USDOE",
    "I", "II", "III", "IV", "V",
}


def _titlecase_owner(s: str) -> str:
    """Title-case a free-text owner string while preserving common acronyms."""
    out: list[str] = []
    for word in s.split():
        if word.upper() in _OWNER_ACRONYMS:
            out.append(word.upper())
        else:
            # Handle hyphenated tokens (e.g. "ST-LOUIS" → "St-Louis").
            parts = word.split("-")
            out.append("-".join(
                p.upper() if p.upper() in _OWNER_ACRONYMS else p.capitalize()
                for p in parts
            ))
    return " ".join(out)


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
        p.add_argument(
            "--fuds-no-polygons",
            dest="fuds_polygons",
            action="store_false",
            default=True,
            help="Skip the layer-4 polygon join (acreage stays null). Use for fast iteration.",
        )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        state_filter = (getattr(args, "fuds_state", None) or "").strip().lower() or None
        raw_features = self._fetch_points(use_cache=use_cache, state=state_filter)

        polygon_acres: dict[str, float] = {}
        polygon_centers: dict[str, tuple[float, float]] = {}
        if getattr(args, "fuds_polygons", True):
            polygon_acres, polygon_centers = self._fetch_polygon_join(
                use_cache=use_cache
            )
            log.info(
                "polygon join: %d properties have boundary acreage",
                len(polygon_acres),
            )

        eligible_only = getattr(args, "fuds_eligible_only", False)
        records: list[dict[str, Any]] = []
        dropped = 0
        enriched_acreage = 0
        enriched_centroid = 0
        for feat in raw_features:
            rec = self.normalize(feat, eligible_only=eligible_only)
            if rec is None:
                dropped += 1
                continue
            prop_id = rec["id"].removeprefix("FUDS-")
            if prop_id in polygon_acres:
                rec["acreage"] = polygon_acres[prop_id]
                enriched_acreage += 1
            if prop_id in polygon_centers:
                lon, lat = polygon_centers[prop_id]
                rec["lat"] = round(lat, 6)
                rec["lon"] = round(lon, 6)
                enriched_centroid += 1
            records.append(rec)

        total = len(raw_features)
        if total > 0 and dropped / total > DROP_RATIO_WARN_THRESHOLD:
            log.warning(
                "dropped %d/%d features during normalize (%.0f%%) — investigate source",
                dropped, total, 100 * dropped / total,
            )

        log.info(
            "polygon enrichment: %d acreages, %d centroid swaps",
            enriched_acreage, enriched_centroid,
        )

        records.sort(key=lambda r: ((r.get("state") or "").upper(),
                                    (r.get("name") or "").lower()))

        if getattr(args, "limit", None):
            records = records[: args.limit]

        log.info("normalized %d records (dropped %d)", len(records), dropped)
        return records

    def _fetch_points(
        self, use_cache: bool, state: str | None = None
    ) -> list[dict[str, Any]]:
        all_features: list[dict[str, Any]] = []
        offset = 0
        where = "1=1" if not state else f"STATE='{state}'"
        while True:
            params = {
                "where": where,
                "outFields": ",".join(POINT_OUTFIELDS),
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            }
            data = self.http_get_json(POINT_QUERY_URL, params, use_cache=use_cache)
            page = data.get("features", [])
            log.info("points page offset=%d got=%d", offset, len(page))
            if not page:
                break
            all_features.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        log.info("retrieved %d total point features", len(all_features))
        return all_features

    def _fetch_polygon_join(
        self, use_cache: bool
    ) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
        """Page through layer 4 and build {property_id → acreage} + centroid maps.

        Some properties carry multiple polygon features (parcel fragments).
        Acreage is summed across fragments; the centroid is computed once
        from the union envelope so the marker sits on the visual middle of
        the property.
        """
        all_features: list[dict[str, Any]] = []
        offset = 0
        while True:
            params = {
                "where": "1=1",
                "outFields": ",".join(POLYGON_OUTFIELDS),
                "orderByFields": "DODFUDSPROPERTYIDPK ASC",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            }
            data = self.http_get_json(POLYGON_QUERY_URL, params, use_cache=use_cache)
            page = data.get("features", [])
            log.info("polygons page offset=%d got=%d", offset, len(page))
            if not page:
                break
            all_features.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        log.info("retrieved %d total polygon features", len(all_features))

        # Group by property ID — same property can have multiple parcel polygons.
        rings_by_id: dict[str, list[list[list[float]]]] = {}
        for feat in all_features:
            attrs = feat.get("attributes") or {}
            geom = feat.get("geometry") or {}
            prop_id = attrs.get("DODFUDSPROPERTYIDPK")
            rings = geom.get("rings")
            if not prop_id or not rings:
                continue
            rings_by_id.setdefault(prop_id, []).extend(rings)

        acreage_map: dict[str, float] = {}
        center_map: dict[str, tuple[float, float]] = {}
        for prop_id, rings in rings_by_id.items():
            acres = polygon_acreage(rings)
            if acres is not None and acres > 0:
                acreage_map[prop_id] = acres
            try:
                center_map[prop_id] = envelope_center(rings)
            except ValueError:
                pass
        return acreage_map, center_map

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
        owner = _pretty_owner(a.get("CURRENTOWNER"))
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
            "current_owner": owner,
            "current_owner_source": "USACE FUDS" if owner else None,
            "eligibility": eligibility,
            "fuds_status": a.get("STATUS"),
            "has_projects": a.get("HAS_PROJECTS"),
            "congressional_district": a.get("CONGRESSIONALDISTRICT"),
            "npl_status": a.get("STATUSCODE"),
        }
