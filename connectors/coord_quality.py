"""Coordinate-quality enrichment — how much to trust a site's location.

Every marker on the map currently looks equally authoritative. The 2026-08-09
corpus audit showed they are not: 118 sites sit more than a mile outside the
polygon of their own `state` field (13 of them more than 25 mi, two outside
the United States entirely), 17 carry whole- or half-degree placeholder
coordinates, and 3,728 share an exact coordinate with at least two other
sites — the signature of a geocoder falling back to a city or county
centroid rather than locating the parcel.

None of that is fixable from our side; the state attribute and the geometry
are populated by independent paths inside EPA ACRES and USACE FUDS, and
neither source cross-validates them. What IS fixable is presenting a
coordinate as more precise than it is. This connector labels each record so
the UI can say so.

Flags emitted (a record can carry several):

  state_mismatch   The point falls outside its own state's polygon by more
                   than STATE_TOLERANCE_MI. `coord_state_gap_mi` carries how
                   far, and `coord_actual_state` which state it landed in.
  outside_us       The point is not inside CONUS or any US territory box.
  placeholder      Whole or half degree, or |lat| == |lon| — typed, not
                   surveyed.
  shared_point     At least two other records share this exact coordinate.
                   `coord_shared_count` carries the cluster size.
  low_precision    Two or fewer decimal places (~1.1 km resolution or worse).

Deliberately OFFLINE — it reads `docs/data/us-states.json`, which the repo
already ships for the basemap, and reuses `connectors.spatial.PolygonIndex`.
No network, so it costs nothing to run on every refresh and can gate CI.

Deliberately NON-DESTRUCTIVE — it never edits, drops or "corrects" a
coordinate. A wrong coordinate flagged is honest; a coordinate we invented is
not. Records with nothing wrong are omitted entirely, so the output file
stays small and absence means "no known problem".

    python refresh.py --source coord-quality
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from connectors.base import Connector
from connectors.spatial import PolygonIndex

log = logging.getLogger("connector.coord_quality")

# A point this far outside its claimed state's polygon is an error rather
# than generalized-polygon noise. Chosen from the corpus distribution: 213
# mismatches sit within a mile of the border (real sites on a state line),
# and the next one out is already several miles in.
STATE_TOLERANCE_MI = 1.0

# Cluster size at which a shared coordinate stops looking like coincidence.
# Two sites can genuinely share a point (a facility split into two records);
# three or more at identical six-decimal precision is a centroid.
SHARED_POINT_MIN = 3

PROGRAM_FILES = (
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
)

STATE_NAME_TO_CODE = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Puerto Rico": "PR", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}

# CONUS plus every territory box the corpus legitimately reaches, including
# the western Aleutians (positive longitudes past the antimeridian), the
# Northwestern Hawaiian Islands, and Swains Island in American Samoa.
REGION_BOXES = {
    "conus": (24.0, -125.5, 49.5, -66.5),
    "AK": (51.0, -180.0, 72.0, -129.0),
    "AK-west": (51.0, 172.0, 54.0, 180.0),
    "HI": (18.5, -178.5, 28.5, -154.5),
    "PR": (17.8, -67.5, 18.6, -65.2),
    "VI": (17.6, -65.1, 18.5, -64.5),
    "GU": (13.2, 144.6, 13.7, 145.0),
    "MP": (14.0, 145.1, 20.6, 146.1),
    "AS": (-14.6, -171.2, -10.9, -168.1),
    "FM": (1.0, 137.0, 10.0, 163.5),
    "MH": (4.5, 160.0, 15.0, 172.5),
    "UM": (-1.0, -178.0, 29.0, 167.0),
}


class CoordQuality(Connector):
    slug = "coord-quality"
    source_label = "Coordinate quality flags (derived)"
    source_url = (
        "https://github.com/pranava0x0/brownfield-opportunities"
        "/blob/main/connectors/coord_quality.py"
    )
    # After the producer connectors, before the geo-dependent enrichments.
    run_order = 150

    DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        sites = self._load_sites()
        if not sites:
            log.warning("no program files found; nothing to flag")
            return []

        states = self._state_index()
        rings = self._state_rings()
        clusters = self._coordinate_clusters(sites)

        records: list[dict[str, Any]] = []
        tally: dict[str, int] = defaultdict(int)

        for site in sites:
            lat, lon = site.get("lat"), site.get("lon")
            if lat is None or lon is None:
                continue
            flags: list[str] = []
            extra: dict[str, Any] = {}

            if not _inside_any_region(lat, lon):
                flags.append("outside_us")

            claimed = site.get("state")
            if claimed in STATE_NAME_TO_CODE.values():
                landed = states.containing(lat, lon)
                actual = STATE_NAME_TO_CODE.get(str(landed)) if landed else None
                if actual and actual != claimed:
                    gap = _distance_to_state_mi(lat, lon, claimed, rings)
                    # A point barely over a generalized border is noise, not
                    # an error — 213 corpus records are legitimately on a
                    # state line.
                    if gap is None or gap > STATE_TOLERANCE_MI:
                        flags.append("state_mismatch")
                        extra["coord_actual_state"] = actual
                        if gap is not None:
                            extra["coord_state_gap_mi"] = round(gap, 1)

            if _is_placeholder(lat, lon):
                flags.append("placeholder")

            n = clusters.get((round(lat, 6), round(lon, 6)), 0)
            if n >= SHARED_POINT_MIN:
                flags.append("shared_point")
                extra["coord_shared_count"] = n

            if max(_decimals(lat), _decimals(lon)) <= 2:
                flags.append("low_precision")

            if not flags:
                continue
            for f in flags:
                tally[f] += 1
            records.append({
                "id": site["id"],
                "program": site["program"],
                "coord_flags": flags,
                **extra,
            })

        log.info(
            "flagged %d/%d sites — %s",
            len(records), len(sites),
            ", ".join(f"{k}={v}" for k, v in sorted(tally.items())) or "none",
        )
        return records

    # ----- helpers -----

    def _load_sites(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in PROGRAM_FILES:
            path = self.DATA_DIR / name
            if not path.exists():
                log.warning("missing program file %s — skipping", name)
                continue
            payload = json.loads(path.read_text())
            out.extend(payload.get("sites") or [])
        return out

    def _state_index(self) -> PolygonIndex:
        idx = PolygonIndex(cell_deg=0.5)
        geo = json.loads((self.DATA_DIR / "us-states.json").read_text())
        for feat in geo.get("features", []):
            name = (feat.get("properties") or {}).get("name")
            geom = feat.get("geometry") or {}
            polys = ([geom.get("coordinates")] if geom.get("type") == "Polygon"
                     else geom.get("coordinates") or [])
            for poly in polys:
                if poly:
                    idx.add_polygon(poly, attr=name)
        return idx

    def _state_rings(self) -> dict[str, list]:
        out: dict[str, list] = defaultdict(list)
        geo = json.loads((self.DATA_DIR / "us-states.json").read_text())
        for feat in geo.get("features", []):
            code = STATE_NAME_TO_CODE.get((feat.get("properties") or {}).get("name"))
            if not code:
                continue
            geom = feat.get("geometry") or {}
            polys = ([geom.get("coordinates")] if geom.get("type") == "Polygon"
                     else geom.get("coordinates") or [])
            for poly in polys:
                if poly:
                    out[code].append(poly[0])
        return dict(out)

    @staticmethod
    def _coordinate_clusters(sites: list[dict]) -> dict[tuple, int]:
        counts: dict[tuple, int] = defaultdict(int)
        for s in sites:
            lat, lon = s.get("lat"), s.get("lon")
            if lat is None or lon is None:
                continue
            counts[(round(lat, 6), round(lon, 6))] += 1
        return counts


def _inside_any_region(lat: float, lon: float) -> bool:
    return any(
        lo_lat <= lat <= hi_lat and lo_lon <= lon <= hi_lon
        for (lo_lat, lo_lon, hi_lat, hi_lon) in REGION_BOXES.values()
    )


def _is_placeholder(lat: float, lon: float) -> bool:
    if float(lat).is_integer() and float(lon).is_integer():
        return True
    if (abs(lat * 2 - round(lat * 2)) < 1e-9
            and abs(lon * 2 - round(lon * 2)) < 1e-9):
        return True
    return abs(abs(lat) - abs(lon)) < 1e-9


def _decimals(v: float) -> int:
    s = repr(float(v))
    if "e" in s or "E" in s:
        return 10
    return len(s.split(".")[1].rstrip("0")) if "." in s else 0


def _distance_to_state_mi(
    lat: float, lon: float, code: str, rings_by_state: dict
) -> Optional[float]:
    """Shortest distance from the point to the claimed state's boundary."""
    rings = rings_by_state.get(code)
    if not rings:
        return None
    coslat = math.cos(math.radians(lat))
    best = float("inf")
    for ring in rings:
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        dx = max(min(lons) - lon, lon - max(lons), 0.0) * coslat
        dy = max(min(lats) - lat, lat - max(lats), 0.0)
        if math.hypot(dx, dy) * 69.0 > best:
            continue
        prev = ring[0]
        for cur in ring[1:]:
            d = _point_seg(lon, lat, prev[0], prev[1], cur[0], cur[1], coslat)
            if d < best:
                best = d
            prev = cur
    return None if best == float("inf") else best * 69.0


def _point_seg(px, py, ax, ay, bx, by, coslat) -> float:
    apx, apy = (px - ax) * coslat, py - ay
    abx, aby = (bx - ax) * coslat, by - ay
    denom = abx * abx + aby * aby
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
    return math.hypot(apx - t * abx, apy - t * aby)
