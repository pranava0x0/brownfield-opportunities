"""Pure-Python spatial index for nearest-segment-distance lookups.

Used by the infrastructure-proximity enrichment connector to answer "what is
the distance from this site to the nearest HIFLD transmission line / TIGER
interstate / TIGER rail segment?" across all 47k records without pulling in
shapely/rtree.

The trick: bucket every polyline segment by its bounding-box cells in a
uniform lat/lon grid. A query at (lat, lon) checks the 9 cells around it,
expanding outward until the candidate segments' min-distance is provably a
lower bound on anything outside the searched ring. For typical CONUS infra
densities a 0.25° cell (≈17 mi) finds the nearest hit in 1–3 rings.

Distance math is local-projection: convert each lat/lon delta to meters via
cos(latitude) at the query point, then planar point-to-segment. Good to
better than 1% in CONUS — far below the precision the dashboard cares about
(distances rounded to 0.1 mi).
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

# Earth radius for haversine. Used only as an outer-bound sanity check —
# the per-cell math uses local projection.
EARTH_RADIUS_MI = 3958.7613

# Default grid cell size in degrees. 0.25° ≈ 17 mi at the equator, ≈ 12 mi
# at 45°N. Sized so that the average CONUS query finds hits in the first
# ring of cells.
DEFAULT_CELL_DEG = 0.25

# Hard cap on rings we'll expand before giving up. 8 rings × 0.25° ≈ 140 mi
# search radius — past that, "nearest infra" stops being a useful signal
# anyway (Alaskan FUDS sites, etc).
MAX_RINGS = 8


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two (lat, lon) pairs."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    c = 2 * math.asin(min(1.0, math.sqrt(a)))
    return EARTH_RADIUS_MI * c


def _project_meters(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    """Local equirectangular projection. Returns (x_m, y_m) relative to (0, 0)
    origin at lat=0, lon=0, scaled by cos(ref_lat) for longitude.

    `ref_lat` is the latitude of the query point — using a single reference
    keeps the projection consistent within one nearest-segment query.
    """
    cos_lat = math.cos(math.radians(ref_lat))
    x = lon * 111_320.0 * cos_lat
    y = lat * 110_540.0
    return x, y


def _segment_distance_m(
    px: float, py: float,
    ax: float, ay: float, bx: float, by: float,
) -> float:
    """Planar point-to-segment distance in the same units as the inputs.

    Standard projection-and-clamp formula. Returns 0 for a degenerate
    (zero-length) segment.
    """
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    cx = ax + t * dx
    cy = ay + t * dy
    return math.hypot(px - cx, py - cy)


def _cell_for(lat: float, lon: float, cell_deg: float) -> tuple[int, int]:
    return int(math.floor(lat / cell_deg)), int(math.floor(lon / cell_deg))


def _cells_in_ring(cy: int, cx: int, ring: int) -> Iterable[tuple[int, int]]:
    """Yield grid cells exactly `ring` steps from (cy, cx) in Chebyshev distance."""
    if ring == 0:
        yield (cy, cx)
        return
    for dy in range(-ring, ring + 1):
        for dx in range(-ring, ring + 1):
            if max(abs(dy), abs(dx)) == ring:
                yield (cy + dy, cx + dx)


class SegmentIndex:
    """Spatial grid over polyline segments.

    Build by calling `add_polyline(coords)` for each polyline (a list of
    `[lon, lat]` vertices). Then `nearest_distance_mi(lat, lon)` returns
    the minimum great-circle distance to any segment, capped at `max_rings
    * cell_deg`-degrees of search radius (returns None past that).

    Optional per-polyline attribute carryover: pass an `attr` to
    `add_polyline()` (any hashable Python value — typically a kV float for
    transmission lines) and call `nearest_with_attr()` instead of
    `nearest_distance_mi()` to receive `(distance_mi, attr)` for the
    nearest segment. Adds ~5 bytes per segment when used.
    """

    def __init__(self, cell_deg: float = DEFAULT_CELL_DEG):
        if cell_deg <= 0:
            raise ValueError("cell_deg must be positive")
        self.cell_deg = cell_deg
        # cell -> list of segment indices (into self._segments)
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        # parallel arrays to avoid object overhead at 47k+ scale.
        # Each segment is stored as (a_lat, a_lon, b_lat, b_lon).
        self._segments: list[tuple[float, float, float, float]] = []
        # Optional per-segment attributes. Lazily allocated — stays at None
        # for layers that never call `add_polyline(..., attr=...)` so the
        # rail / highway path keeps zero memory overhead.
        self._attrs: list | None = None
        self._segment_count = 0

    @property
    def segment_count(self) -> int:
        return self._segment_count

    def add_polyline(
        self,
        coords: list[list[float]],
        attr: object = None,
    ) -> int:
        """Add one polyline's segments. `coords` is a list of `[lon, lat]` pairs.

        Returns the number of segments added. Polylines with <2 points are
        skipped (degenerate). Points at exactly (0, 0) are also skipped —
        they're the typical sentinel for missing geometry from ESRI sources.

        `attr` is an optional value carried for every segment of this
        polyline — retrieve via `nearest_with_attr()`. Pass `None` (the
        default) to skip; the index stays attribute-free until the first
        non-None attr lands, after which all subsequent segments get an
        entry (attr=None for the ones added without one).
        """
        added = 0
        last_lon: float | None = None
        last_lat: float | None = None
        # Allocate the attrs list lazily on first non-None attr. Backfill
        # any prior segments with None so the parallel-array invariant
        # (len(_attrs) == len(_segments)) holds.
        if attr is not None and self._attrs is None:
            self._attrs = [None] * len(self._segments)
        for pt in coords:
            if not pt or len(pt) < 2:
                last_lon = last_lat = None
                continue
            try:
                lon = float(pt[0])
                lat = float(pt[1])
            except (TypeError, ValueError):
                last_lon = last_lat = None
                continue
            # Drop null-island sentinels and out-of-range coords.
            if abs(lon) < 0.5 and abs(lat) < 0.5:
                last_lon = last_lat = None
                continue
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                last_lon = last_lat = None
                continue
            if last_lat is not None and last_lon is not None:
                idx = len(self._segments)
                self._segments.append((last_lat, last_lon, lat, lon))
                if self._attrs is not None:
                    self._attrs.append(attr)
                self._segment_count += 1
                added += 1
                # Bucket by every cell the segment's bbox touches.
                lat_lo = min(last_lat, lat)
                lat_hi = max(last_lat, lat)
                lon_lo = min(last_lon, lon)
                lon_hi = max(last_lon, lon)
                cy_lo, cx_lo = _cell_for(lat_lo, lon_lo, self.cell_deg)
                cy_hi, cx_hi = _cell_for(lat_hi, lon_hi, self.cell_deg)
                for cy in range(cy_lo, cy_hi + 1):
                    for cx in range(cx_lo, cx_hi + 1):
                        self._cells[(cy, cx)].append(idx)
            last_lat = lat
            last_lon = lon
        return added

    def nearest_distance_mi(
        self,
        lat: float,
        lon: float,
        max_rings: int = MAX_RINGS,
    ) -> float | None:
        """Return min distance in miles from (lat, lon) to any segment.

        Returns None if no segment is found within `max_rings` of cells.
        Caller decides whether to interpret None as "out of CONUS" or
        "no infra in usable range."
        """
        result = self._nearest(lat, lon, max_rings, return_idx=False)
        return None if result is None else result[0]

    def nearest_with_attr(
        self,
        lat: float,
        lon: float,
        max_rings: int = MAX_RINGS,
    ) -> tuple[float, object] | None:
        """Return (distance_mi, attr) for the nearest segment.

        `attr` is the value passed to `add_polyline()` for the polyline that
        owns the matched segment, or None if no attr was attached.
        Returns None if no segment is found within `max_rings`.
        """
        result = self._nearest(lat, lon, max_rings, return_idx=True)
        if result is None:
            return None
        d_mi, idx = result
        attr = None
        if self._attrs is not None and 0 <= idx < len(self._attrs):
            attr = self._attrs[idx]
        return (d_mi, attr)

    def _nearest(
        self,
        lat: float,
        lon: float,
        max_rings: int,
        return_idx: bool,
    ) -> tuple[float, int] | tuple[float] | None:
        if not self._segments:
            return None
        cy, cx = _cell_for(lat, lon, self.cell_deg)
        best_m: float | None = None
        best_idx: int = -1
        # Project the query once; reuse for every candidate segment.
        cos_lat = math.cos(math.radians(lat))
        m_per_deg_lon = 111_320.0 * cos_lat
        m_per_deg_lat = 110_540.0
        px = lon * m_per_deg_lon
        py = lat * m_per_deg_lat
        seen: set[int] = set()
        for ring in range(max_rings + 1):
            for cell in _cells_in_ring(cy, cx, ring):
                for idx in self._cells.get(cell, ()):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    a_lat, a_lon, b_lat, b_lon = self._segments[idx]
                    ax = a_lon * m_per_deg_lon
                    ay = a_lat * m_per_deg_lat
                    bx = b_lon * m_per_deg_lon
                    by = b_lat * m_per_deg_lat
                    d = _segment_distance_m(px, py, ax, ay, bx, by)
                    if best_m is None or d < best_m:
                        best_m = d
                        best_idx = idx
            # Early exit: if we've found a hit closer than the inner edge
            # of the next ring, no segment outside that ring can beat it.
            if best_m is not None:
                # Inner edge of ring (ring + 1) is `ring * cell_deg` degrees
                # away in Chebyshev distance — convert to meters by the
                # smaller of (lon, lat) scale factors.
                next_inner_m = ring * self.cell_deg * min(m_per_deg_lat, m_per_deg_lon)
                if best_m <= next_inner_m:
                    break
        if best_m is None:
            return None
        d_mi = best_m / 1609.344  # meters → miles
        if return_idx:
            return (d_mi, best_idx)
        return (d_mi,)


class PointIndex:
    """Spatial grid over POINTS — companion to `SegmentIndex` for point-feature
    layers like substations and power plants.

    Same bucket-by-grid + Chebyshev-ring-expansion algorithm. Points are
    stored as parallel arrays of (lat, lon, attr) to avoid object overhead at
    the 70k-100k scale these layers reach nationwide. `attr` is opaque to the
    index — typically a dict capturing source-side fields (kV, MW, fuel type,
    name) that the caller wants to surface alongside the distance.

    Distance uses the same local-equirectangular projection as `SegmentIndex`
    so identical bounds apply (good to better than 1% in CONUS).
    """

    def __init__(self, cell_deg: float = DEFAULT_CELL_DEG):
        if cell_deg <= 0:
            raise ValueError("cell_deg must be positive")
        self.cell_deg = cell_deg
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        # Parallel arrays — keeps the per-point footprint to a single Python
        # int + tuple ref versus storing dicts in a list.
        self._lats: list[float] = []
        self._lons: list[float] = []
        self._attrs: list[object] = []

    @property
    def point_count(self) -> int:
        return len(self._lats)

    def add_point(
        self,
        lat: float,
        lon: float,
        attr: object = None,
    ) -> bool:
        """Add one point. Returns True if added, False if filtered out.

        Same sentinel filter as `SegmentIndex.add_polyline`: drops null-island
        and out-of-range coordinates rather than letting them poison nearest
        lookups. Out-of-range coords are common in ESRI sources for "missing
        geometry" rows.
        """
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return False
        if abs(lat_f) < 0.5 and abs(lon_f) < 0.5:
            return False
        if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
            return False
        idx = len(self._lats)
        self._lats.append(lat_f)
        self._lons.append(lon_f)
        self._attrs.append(attr)
        cy, cx = _cell_for(lat_f, lon_f, self.cell_deg)
        self._cells[(cy, cx)].append(idx)
        return True

    def nearest_with_attr(
        self,
        lat: float,
        lon: float,
        max_rings: int = MAX_RINGS,
    ) -> tuple[float, object] | None:
        """Return `(distance_mi, attr)` for the nearest point, or None if
        nothing is found within `max_rings * cell_deg` of search radius.
        """
        if not self._lats:
            return None
        cy, cx = _cell_for(lat, lon, self.cell_deg)
        best_m: float | None = None
        best_idx: int = -1
        cos_lat = math.cos(math.radians(lat))
        m_per_deg_lon = 111_320.0 * cos_lat
        m_per_deg_lat = 110_540.0
        px = lon * m_per_deg_lon
        py = lat * m_per_deg_lat
        seen: set[int] = set()
        for ring in range(max_rings + 1):
            for cell in _cells_in_ring(cy, cx, ring):
                for idx in self._cells.get(cell, ()):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    qx = self._lons[idx] * m_per_deg_lon
                    qy = self._lats[idx] * m_per_deg_lat
                    d = math.hypot(px - qx, py - qy)
                    if best_m is None or d < best_m:
                        best_m = d
                        best_idx = idx
            if best_m is not None:
                next_inner_m = ring * self.cell_deg * min(m_per_deg_lat, m_per_deg_lon)
                if best_m <= next_inner_m:
                    break
        if best_m is None:
            return None
        d_mi = best_m / 1609.344
        return (d_mi, self._attrs[best_idx])

    def nearest_distance_mi(
        self,
        lat: float,
        lon: float,
        max_rings: int = MAX_RINGS,
    ) -> float | None:
        """Convenience: distance only, no attr."""
        hit = self.nearest_with_attr(lat, lon, max_rings=max_rings)
        return None if hit is None else hit[0]


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test against a single ring of `[lon, lat]`
    vertices. Standard odd-crossings algorithm; vertex on boundary counts as
    inside (matches Esri's `esriSpatialRelIntersects` convention for the OZ
    use case where census-tract boundaries are deliberately drawn to include
    edge addresses)."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        # Edge crosses the horizontal ray at y=lat?
        if (yi > lat) != (yj > lat):
            # x-intercept of the edge at y=lat
            x_cross = (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


class PolygonIndex:
    """Spatial grid over POLYGONS for point-in-polygon containment lookups.

    Used by enrichment connectors that need "what polygon contains this site"
    rather than "what's the nearest feature" — e.g. Opportunity Zone census
    tracts (~8,765 nationwide), state polygons, congressional districts.

    Each polygon is stored as a list of rings (`[[[lon, lat], ...], ...]` —
    first ring is exterior, remaining rings are holes per the GeoJSON
    convention). The bucket-by-bbox grid identifies candidate polygons in
    O(1) cells; we then ray-cast against each candidate. For OZ-scale
    (~8,765 polygons spread across the US, average tract is small), most
    queries resolve in <5 ray-casts.

    Note this is intentionally NOT the same architecture as `SegmentIndex` /
    `PointIndex` — those use Chebyshev-ring expansion for *nearest* queries.
    Containment is a binary in-or-out test, not a distance query, so it
    only checks the cell(s) containing the query point and returns as soon
    as any polygon's bbox contains the point and ray-casting confirms.
    """

    def __init__(self, cell_deg: float = DEFAULT_CELL_DEG):
        if cell_deg <= 0:
            raise ValueError("cell_deg must be positive")
        self.cell_deg = cell_deg
        # cell -> list of polygon indices that touch the cell.
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        # Per-polygon: list of rings + bbox + attr.
        self._rings: list[list[list[list[float]]]] = []
        self._bboxes: list[tuple[float, float, float, float]] = []  # (lat_lo, lon_lo, lat_hi, lon_hi)
        self._attrs: list[object] = []

    @property
    def polygon_count(self) -> int:
        return len(self._rings)

    def add_polygon(
        self,
        rings: list[list[list[float]]],
        attr: object = None,
    ) -> bool:
        """Add one polygon. `rings` is GeoJSON-style — first ring is exterior,
        any subsequent rings are holes. Returns True if added, False if
        filtered out (degenerate / out-of-range).

        For ESRI polygons (`{"rings": [[[lon, lat], ...], ...]}`), pass the
        `rings` field directly.
        """
        if not rings or not rings[0] or len(rings[0]) < 3:
            return False
        # Compute bbox from the exterior ring (ring 0). Skip null-island
        # rings entirely.
        ext = rings[0]
        lats = [p[1] for p in ext if isinstance(p, (list, tuple)) and len(p) >= 2]
        lons = [p[0] for p in ext if isinstance(p, (list, tuple)) and len(p) >= 2]
        if len(lats) < 3 or len(lons) < 3:
            return False
        lat_lo, lat_hi = min(lats), max(lats)
        lon_lo, lon_hi = min(lons), max(lons)
        if not (-90 <= lat_lo <= 90) or not (-90 <= lat_hi <= 90):
            return False
        if not (-180 <= lon_lo <= 180) or not (-180 <= lon_hi <= 180):
            return False
        idx = len(self._rings)
        self._rings.append(rings)
        self._bboxes.append((lat_lo, lon_lo, lat_hi, lon_hi))
        self._attrs.append(attr)
        # Bucket by every cell the bbox touches.
        cy_lo, cx_lo = _cell_for(lat_lo, lon_lo, self.cell_deg)
        cy_hi, cx_hi = _cell_for(lat_hi, lon_hi, self.cell_deg)
        for cy in range(cy_lo, cy_hi + 1):
            for cx in range(cx_lo, cx_hi + 1):
                self._cells[(cy, cx)].append(idx)
        return True

    def containing(self, lat: float, lon: float) -> object | None:
        """Return the attr of the FIRST polygon that contains (lat, lon),
        or None if the point is outside every indexed polygon.

        Polygons don't overlap for OZ census tracts (Treasury designation
        is by tract; tracts partition the US), so "first match" is the
        natural semantic. If a future use case has overlapping polygons,
        add `containing_all()`.
        """
        cy, cx = _cell_for(lat, lon, self.cell_deg)
        for idx in self._cells.get((cy, cx), ()):
            lat_lo, lon_lo, lat_hi, lon_hi = self._bboxes[idx]
            # Coarse bbox filter — skip the ray-cast if the bbox doesn't even
            # contain the point.
            if not (lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi):
                continue
            rings = self._rings[idx]
            # Exterior contains the point?
            if not _point_in_ring(lon, lat, rings[0]):
                continue
            # Check holes (rings 1..). If point is in any hole, polygon
            # doesn't actually contain it.
            in_hole = False
            for hole in rings[1:]:
                if _point_in_ring(lon, lat, hole):
                    in_hole = True
                    break
            if not in_hole:
                return self._attrs[idx]
        return None
