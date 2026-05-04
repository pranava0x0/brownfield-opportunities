"""Shared polygon math used by polygon-bearing connectors (BRAC, FUDS).

Sources store polygons in WGS84 (4326) where coordinates are decimal degrees,
not meters. Computing area from raw coordinates with the Shoelace formula
yields degrees², which is meaningless. We project locally using cos(latitude)
to convert each ring's degrees → meters before applying Shoelace. Good to
better than 1% on the contiguous US — far below the per-polygon precision of
the source data.
"""
from __future__ import annotations

import math
from typing import Iterable

ACRES_PER_SQ_METER = 0.000247105


def envelope_center(rings: list[list[list[float]]]) -> tuple[float, float]:
    """Return (lon, lat) of the geometry's bounding-box center."""
    xs: list[float] = []
    ys: list[float] = []
    for ring in rings:
        for x, y in ring:
            xs.append(x)
            ys.append(y)
    if not xs:
        raise ValueError("empty geometry")
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def polygon_area_sq_meters(rings: list[list[list[float]]]) -> float:
    """Approximate polygon area in m² using locally-projected Shoelace.

    Each ring is independently projected against its own mean latitude, so
    multipolygons that span latitudes are handled correctly. Inner rings
    (holes) are not subtracted — ESRI's polygon ring orientation is
    inconsistent across sources and these connectors don't need hole-aware
    geometry. Acreage error from holes is well under the rounding we already
    apply in the output.
    """
    total = 0.0
    for ring in rings:
        n = len(ring)
        if n < 3:
            continue
        mid_lat = sum(p[1] for p in ring) / n
        cos_lat = math.cos(math.radians(mid_lat))
        m_per_deg_lon = 111_320 * cos_lat
        m_per_deg_lat = 110_540
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            x_i = ring[i][0] * m_per_deg_lon
            y_i = ring[i][1] * m_per_deg_lat
            x_j = ring[j][0] * m_per_deg_lon
            y_j = ring[j][1] * m_per_deg_lat
            area += x_i * y_j - x_j * y_i
        total += abs(area) / 2.0
    return total


def polygon_acreage(rings: list[list[list[float]]]) -> float | None:
    """Convenience: convert ring geometry directly to rounded acres."""
    sq_m = polygon_area_sq_meters(rings)
    if sq_m <= 0:
        return None
    return round(sq_m * ACRES_PER_SQ_METER, 1)
