"""Offline TIGER county point-in-polygon lookup.

Decodes the TopoJSON we already ship at `docs/data/us-counties-topo.json` and
exposes `CountyIndex.lookup(lat, lon) -> str | None`. Used by `epa-acres` to
fill the ~51% of records where the source FeatureServer omits `COUNTY`.

No external dependency: the file is small enough (~3,231 polygons, ~822 KB on
disk) that a pure-Python decode + spatial bucket grid runs in well under a
second for the full ACRES pass. We intentionally avoid bringing in
shapely/rtree — same trade-off as `connectors/spatial.py`.

Decoding follows the TopoJSON 1.0 spec: arcs are delta-encoded over an
integer grid; polygons reference arc indices (negative = traverse reversed,
~i = i-th arc reversed). Point-in-polygon is the standard ray-casting odd/even
rule, which handles holes and concave polygons natively.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# Coarse grid for spatial filtering. 0.5° ≈ 35 mi at the equator. CONUS spans
# ~25-49°N × ~67-125°W, which is ~50 × 116 cells — the cell map stays under
# 6k entries even with multi-cell polygons. Sized so the average county
# touches ~2 cells; an ACRES query typically needs 1-3 polygons tested.
DEFAULT_CELL_DEG = 0.5


def _accumulate_arc(
    deltas: list[list[int]],
    transform: dict,
) -> list[tuple[float, float]]:
    """Decode one TopoJSON arc to a list of (lon, lat) pairs."""
    sx, sy = transform["scale"]
    tx, ty = transform["translate"]
    x = 0
    y = 0
    out: list[tuple[float, float]] = []
    for d in deltas:
        x += d[0]
        y += d[1]
        out.append((x * sx + tx, y * sy + ty))
    return out


def _stitch_ring(
    arc_indices: list[int],
    decoded_arcs: list[list[tuple[float, float]]],
) -> list[tuple[float, float]]:
    """Concatenate referenced arcs into a single ring of (lon, lat) pairs.

    Negative indices encode reversed arcs (`~i` is the standard TopoJSON
    convention; `~i == -i - 1`). When stitching consecutive arcs we drop the
    duplicate vertex at the seam so the ring stays closed without doubled
    points.
    """
    ring: list[tuple[float, float]] = []
    for raw_idx in arc_indices:
        if raw_idx >= 0:
            arc = decoded_arcs[raw_idx]
        else:
            arc = list(reversed(decoded_arcs[~raw_idx]))
        if ring and arc and ring[-1] == arc[0]:
            ring.extend(arc[1:])
        else:
            ring.extend(arc)
    return ring


def _polygons_for_geometry(
    geom: dict,
    decoded_arcs: list[list[tuple[float, float]]],
) -> list[list[list[tuple[float, float]]]]:
    """Return a list of polygons, each a list of rings (outer + holes)."""
    gtype = geom.get("type")
    arcs = geom.get("arcs") or []
    if gtype == "Polygon":
        rings = [_stitch_ring(idxs, decoded_arcs) for idxs in arcs]
        return [rings] if rings else []
    if gtype == "MultiPolygon":
        out: list[list[list[tuple[float, float]]]] = []
        for poly_arcs in arcs:
            rings = [_stitch_ring(idxs, decoded_arcs) for idxs in poly_arcs]
            if rings:
                out.append(rings)
        return out
    return []


def _ring_bbox(
    ring: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """Standard ray-casting odd/even point-in-polygon. Boundary points are
    not specially handled — for our ACRES use case (lat/lon to 6 decimals)
    a boundary hit is vanishingly unlikely."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)):
            x_at = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_at:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(
    lon: float, lat: float, polygon: list[list[tuple[float, float]]]
) -> bool:
    """Polygon = outer ring + 0+ inner rings (holes). Inside iff the point
    is in the outer ring AND not in any hole."""
    if not polygon:
        return False
    if not _point_in_ring(lon, lat, polygon[0]):
        return False
    for hole in polygon[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _cells_for_bbox(
    bbox: tuple[float, float, float, float], cell_deg: float
) -> Iterable[tuple[int, int]]:
    """Yield every grid cell the bbox touches."""
    minx, miny, maxx, maxy = bbox
    cx_lo = int(math.floor(minx / cell_deg))
    cx_hi = int(math.floor(maxx / cell_deg))
    cy_lo = int(math.floor(miny / cell_deg))
    cy_hi = int(math.floor(maxy / cell_deg))
    for cy in range(cy_lo, cy_hi + 1):
        for cx in range(cx_lo, cx_hi + 1):
            yield (cy, cx)


class CountyIndex:
    """Spatial point-in-polygon index over US TIGER counties.

    Each county maps to its name (and, when present, the FIPS-derived state
    code from the geometry id). Lookup returns the county name only — state
    is already on the ACRES record.
    """

    # Source 2-letter postal codes, keyed by 2-digit state FIPS. Used to
    # validate that a TIGER hit matches the ACRES record's state field
    # before we trust the county name.
    FIPS_TO_STATE = {
        "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
        "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
        "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
        "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
        "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
        "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
        "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
        "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
        "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
        "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
        "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR",
        "78": "VI",
    }

    def __init__(self, cell_deg: float = DEFAULT_CELL_DEG):
        self.cell_deg = cell_deg
        # Each entry: (name, state_code | None, polygon, bbox)
        self._records: list[
            tuple[str, str | None, list[list[tuple[float, float]]],
                  tuple[float, float, float, float]]
        ] = []
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)

    @classmethod
    def from_topojson(cls, topo: dict, cell_deg: float = DEFAULT_CELL_DEG) -> CountyIndex:
        idx = cls(cell_deg=cell_deg)
        transform = topo["transform"]
        decoded_arcs = [_accumulate_arc(arc, transform) for arc in topo["arcs"]]
        counties = topo["objects"]["counties"]["geometries"]
        for geom in counties:
            name = (geom.get("properties") or {}).get("name")
            if not name:
                continue
            fips = str(geom.get("id") or "")
            state = cls.FIPS_TO_STATE.get(fips[:2]) if len(fips) >= 2 else None
            for polygon in _polygons_for_geometry(geom, decoded_arcs):
                if not polygon:
                    continue
                bbox = _ring_bbox(polygon[0])
                rec_idx = len(idx._records)
                idx._records.append((name, state, polygon, bbox))
                for cell in _cells_for_bbox(bbox, cell_deg):
                    idx._cells[cell].append(rec_idx)
        return idx

    @classmethod
    def from_path(cls, path: Path, cell_deg: float = DEFAULT_CELL_DEG) -> CountyIndex:
        return cls.from_topojson(json.loads(path.read_text()), cell_deg=cell_deg)

    @property
    def polygon_count(self) -> int:
        return len(self._records)

    def lookup(
        self, lat: float, lon: float, expected_state: str | None = None
    ) -> str | None:
        """Return the county name containing (lat, lon), or None if no match.

        When `expected_state` is provided (the record's `state` field), only
        polygons in that state are considered — guards against fringe cases
        where a lat/lon sits within the bounding box of an adjacent state's
        county due to rounding, and saves work on the ACRES happy path.
        """
        cell_deg = self.cell_deg
        cy = int(math.floor(lat / cell_deg))
        cx = int(math.floor(lon / cell_deg))
        candidate_indices = self._cells.get((cy, cx))
        if not candidate_indices:
            return None
        for idx in candidate_indices:
            name, state, polygon, bbox = self._records[idx]
            if expected_state and state and state != expected_state:
                continue
            minx, miny, maxx, maxy = bbox
            if lon < minx or lon > maxx or lat < miny or lat > maxy:
                continue
            if _point_in_polygon(lon, lat, polygon):
                return name
        return None
