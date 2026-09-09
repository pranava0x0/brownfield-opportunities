"""Water proximity enrichment — the corpus's first quantitative water signal.

Every infrastructure layer this project collects before this one moves
electrons, freight, or fuel: transmission, substations, rail, highways, gas
pipelines, power plants, ports. None of them is water. The only water fields on
SiteRecord were `near_water_supply` and `near_water_body` — qualitative EPA
RE-Powering strings ("Yes - 1 mile") covering ~1,905 Superfund sites out of
46,759, i.e. 4% of the corpus and none of the brownfields.

That gap is load-bearing for the Nickel Refining tab (a hydrometallurgical
refinery is a water plant with a metallurgy problem attached) and for the
Nuclear Siting tab, where water carries the single largest weight and is met
today by analyst research over 14 curated installations because no national
layer answered the question.

Source: docs/data/streamgages.json, built by
scripts/build_streamgages_overlay.py from the USGS NWIS RDB services.

What the number means
---------------------
`water_flow_cfs` is the mean of a gage's ANNUAL mean discharges over its period
of record. Withdrawal permits are written against low flow (7Q10), routinely an
order of magnitude below the annual mean on a flashy river. So this screens a
candidate and never clears one, and every rendering surface must say so.

`water_gage_mi` is distance to a GAGE, not to water. Gages sit tens of miles
apart on a big river, so a site on the bank can read as several miles from the
nearest gage. The distance is a locator for the flow figure; do not read it as
a pipeline length.

Output: docs/data/water-proximity.json, tombstone convention (infra-proximity,
v1.11.5) — every site gets a `{id, program}` record even when nothing is in
range, so a missing field means "checked, nothing within MAX_DISTANCE_MI"
rather than "not yet checked". The frontend distinguishes the two with a
`_waterChecked` stamp, mirroring `_infraChecked` / `_portChecked`.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import DEFAULT_CELL_DEG, PointIndex

log = logging.getLogger("connector.water_proximity")

# Past this a gage tells you nothing useful about the site's water. Wider than
# the transmission bands because the gage network is far sparser than the grid
# — but tight enough that the number still describes the site's own basin
# rather than the next watershed over.
MAX_DISTANCE_MI = 50.0
EARTH_RADIUS_MI = 3958.8
# Longitude degrees shrink with latitude, so a fixed ring budget covers fewer
# miles the further north a site sits. At 71°N a 0.25° cell is only ~5.6 mi
# wide, and the index's default eight rings reach ~45 mi — short of the cap.
MILES_PER_DEG_LAT = 69.17


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance, used to re-measure the index's candidate.

    PointIndex measures with a local equirectangular projection. Near the
    radius cap that approximation decides membership: ANIAK AIRWAY & AIR COMM
    (FUDS-F10AK0520) has gage 15304010 at 49.99 mi by haversine, which the
    projection reports as 50.19 mi — just over the 50 mi cap, so the site was
    emitted as having no gage at all. Re-measuring the winner is exact and
    costs one trig call per site.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlam = math.radians(lon2 - lon1)
    h = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2)
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def _rings_for_latitude(lat: float, cell_deg: float = DEFAULT_CELL_DEG) -> int:
    """Ring budget that actually reaches MAX_DISTANCE_MI at this latitude."""
    mi_per_cell = max(cell_deg * MILES_PER_DEG_LAT * math.cos(math.radians(lat)),
                      0.5)
    return max(8, int(math.ceil(MAX_DISTANCE_MI / mi_per_cell)) + 1)

GAGES_FILE = "streamgages.json"

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


class WaterProximity(Connector):
    slug = "water-proximity"
    source_label = "USGS NWIS streamgages (docs/data/streamgages.json)"
    source_url = "https://waterservices.usgs.gov/"

    # Alongside the other proximity joins (eia-retired-plants 325,
    # planned-retirements-proximity 326, port-proximity 327).
    run_order = 328

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument("--limit", type=int, default=None,
                           help="Cap the number of enriched records.")

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        sites = list(self._load_sites())
        if not sites:
            log.error("no per-program JSON files in %s — run the producers first",
                      self._data_dir())
            return []

        missing_only = bool(getattr(args, "missing_only", False))
        if missing_only:
            covered = self.existing_ids()
            if covered:
                before = len(sites)
                sites = [s for s in sites if s.get("id") not in covered]
                log.info("--missing-only: %d/%d covered, %d remaining",
                         before - len(sites), before, len(sites))
            if not sites:
                return self.existing_records()

        idx = self._build_index()
        if idx.point_count == 0:
            log.error("gage index empty — run scripts/build_streamgages_overlay.py "
                      "first; aborting rather than writing a water-less file")
            return self.existing_records() if missing_only else []
        log.info("[water-proximity] indexed %d gages", idx.point_count)

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        matched = 0
        for site in sites:
            sid, program = site.get("id"), site.get("program")
            lat, lon = site.get("lat"), site.get("lon")
            if not sid or not program or lat is None or lon is None:
                skipped_no_geom += 1
                continue
            try:
                lat_f, lon_f = float(lat), float(lon)
            except (TypeError, ValueError):
                skipped_no_geom += 1
                continue

            rec: dict[str, Any] = {"id": sid, "program": program}
            hit = idx.nearest_with_attr(
                lat_f, lon_f, max_rings=_rings_for_latitude(lat_f))
            if hit is not None:
                _projected, attr = hit
                # Cap on the EXACT distance, not the projection's estimate —
                # see _haversine_mi.
                dist_mi = _haversine_mi(lat_f, lon_f, attr["lat"], attr["lon"])
                if dist_mi <= MAX_DISTANCE_MI:
                    rec["water_gage_mi"] = round(dist_mi, 2)
                    rec["water_flow_cfs"] = attr["mean_flow_cfs"]
                    rec["water_gage_name"] = attr["name"]
                    rec["water_gage_id"] = attr["gage_id"]
                    matched += 1
            records.append(rec)

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        log.info("[water-proximity] %d / %d sites within %.0f mi of a gaged stream",
                 matched, len(records), MAX_DISTANCE_MI)

        if getattr(args, "limit", None):
            records = records[: args.limit]
        if missing_only:
            existing = self.existing_records()
            merged = self.merge_records_by_id(records, existing)
            log.info("--missing-only: merged %d new + %d existing = %d",
                     len(records), len(existing), len(merged))
            return merged
        return records

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _data_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "docs" / "data"

    def _load_sites(self) -> Iterable[dict[str, Any]]:
        for fname in PROGRAM_FILES:
            path = self._data_dir() / fname
            if not path.exists():
                log.info("program file %s missing — skipping", fname)
                continue
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as e:
                log.warning("failed to read %s: %s — skipping", fname, e)
                continue
            for site in payload.get("sites") or []:
                yield site

    def _build_index(self) -> PointIndex:
        idx = PointIndex()
        path = self._data_dir() / GAGES_FILE
        if not path.exists():
            log.error("overlay %s missing", GAGES_FILE)
            return idx
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.error("failed to read %s: %s", GAGES_FILE, e)
            return idx
        for row in payload.get("sites") or []:
            lat, lon = row.get("lat"), row.get("lon")
            flow = row.get("mean_flow_cfs")
            if lat is None or lon is None or not flow:
                continue
            idx.add_point(float(lat), float(lon), {
                "gage_id": row.get("gage_id"),
                "name": row.get("name"),
                "mean_flow_cfs": flow,
                # Carried so the winner can be re-measured exactly.
                "lat": float(lat),
                "lon": float(lon),
            })
        return idx
