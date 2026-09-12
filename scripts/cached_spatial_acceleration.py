"""Optional NumPy acceleration for offline cache reconstruction.

Uses the same cells, segment projection, radius and stopping bound as the
production index. NumPy is optional; callers retain the pure-Python fallback.
"""
from __future__ import annotations

import math

from connectors.spatial import SegmentIndex, _cell_for, _cells_in_ring, _query_rings, _wrap_cell, SEARCH_RADIUS_MI

try:
    import numpy as np
except ImportError:
    np = None


class AcceleratedSegmentIndex(SegmentIndex):
    def _nearest(self, lat: float, lon: float, max_rings: int | None, return_idx: bool) -> tuple[float, int] | tuple[float] | None:
        if np is None:
            return super()._nearest(lat, lon, max_rings, return_idx)
        if not self._segments or not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        if not hasattr(self, "_array") or len(self._array) != len(self._segments):
            self._array = np.asarray(self._segments, dtype=np.float64)
        physical_radius = max_rings is None
        rings = _query_rings(lat, self.cell_deg) if max_rings is None else max_rings
        cy, cx = _cell_for(lat, lon, self.cell_deg)
        sx, sy = 111320.0 * math.cos(math.radians(lat)), 110540.0
        best, best_id = float("inf"), -1
        seen: set[int] = set()
        exhaustive = physical_radius and rings > 100
        for ring in range(1 if exhaustive else rings + 1):
            candidates = set()
            for cell in self._cells if exhaustive else _cells_in_ring(cy, cx, ring):
                candidates.update(self._cells.get(_wrap_cell(cell, self.cell_deg), ()))
            candidates.difference_update(seen)
            if candidates:
                ids = np.fromiter(sorted(candidates), dtype=np.int64)
                seen.update(candidates)
                points = self._array[ids]
                shift = 360 * np.rint((lon - (points[:, 1] + points[:, 3]) / 2) / 360)
                ax, ay = (points[:, 1] + shift) * sx, points[:, 0] * sy
                bx, by = (points[:, 3] + shift) * sx, points[:, 2] * sy
                dx, dy = bx - ax, by - ay
                denom = dx * dx + dy * dy
                numerator = (lon * sx - ax) * dx + (lat * sy - ay) * dy
                t = np.zeros_like(denom)
                np.divide(numerator, denom, out=t, where=denom > 0)
                np.clip(t, 0, 1, out=t)
                distances = np.hypot(lon * sx - (ax + t * dx), lat * sy - (ay + t * dy))
                pos = int(np.argmin(distances))
                if distances[pos] < best:
                    best, best_id = float(distances[pos]), int(ids[pos])
            if best <= ring * self.cell_deg * min(sx, sy):
                break
        distance = best / 1609.344
        if best_id < 0 or physical_radius and distance > SEARCH_RADIUS_MI:
            return None
        return (distance, best_id) if return_idx else (distance,)
