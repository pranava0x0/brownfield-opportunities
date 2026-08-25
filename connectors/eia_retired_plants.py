"""EIA-860M Retired Plants enrichment connector.

Marks every brownfield site with the distance to the nearest large
RETIRED power plant (≥100 MW, dispatchable fuel) from EIA's Preliminary
Monthly Electric Generator Inventory (Form EIA-860M).

Why this matters — the Conesville / Widows Creek pattern:
A retired coal or gas plant within 1 mile means:
  - Stranded high-voltage interconnection → fastest path to energising a
    data-center campus (the transmission line is there, the inter­connect
    agreement is already grandfathered in many RTO tariffs)
  - Brownfield site may already be zoned heavy-industrial
  - Cooling infrastructure (ponds, water access) often survives retirement
  - Grid-scale capacity that no active load is competing for

HIFLD `Power_Plants_in_the_US` only exposes ACTIVE generators and has no
retirement-status field.  EIA-860M "Retired" sheet (available as a public
Excel download, no API key required) is the canonical US source for retired
generator locations post-2002.

Source: EIA Form EIA-860M, "Preliminary Monthly Electric Generator Inventory"
  URL:  https://www.eia.gov/electricity/data/eia860m/
  File: https://www.eia.gov/electricity/data/eia860m/archive/xls/april_generator2026.xlsx
  Freq: monthly update; April 2026 = most current as of 2026-06-08.
  Note: "Starting with March 2017 data, the Preliminary Monthly Electric
        Generator Inventory includes a comprehensive list of generators which
        retired since 2002."  — We parse the "Retired" sheet only.

Output: docs/data/eia-retired-plants.json
  Per-site records: {id, program, retired_plant_mi, retired_plant_mw,
                     retired_plant_fuel, retired_plant_year, retired_plant_name}
  Only records within MAX_DISTANCE_MI are emitted; sites with nothing in
  range are omitted (unlike infra-proximity tombstones — "no entry" clearly
  means "no large retired plant nearby" for this connector).
"""
from __future__ import annotations

import argparse
import io
import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    import openpyxl  # type: ignore
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

from connectors.base import Connector
from connectors.spatial import PointIndex

log = logging.getLogger("connector.eia_retired_plants")

# Maximum distance we store; beyond this the "adjacent retired plant"
# narrative breaks down.  Scoring only fires at ≤1 mi, but showing 5 mi
# gives analysts context about a nearly-qualifying site.
MAX_DISTANCE_MI = 5.0

# Minimum plant capacity to index.  Below 100 MW a retired plant won't
# have inherited the transmission or interconnect footprint we're looking for.
MIN_PLANT_MW = 100.0

# EIA energy-source codes we consider "dispatchable" (can firm up a DC load).
# Solar + wind are excluded — they don't provide behind-the-meter firmness
# and don't leave the transmission/interconnect legacy the scoring relies on.
DISPATCHABLE_FUELS: frozenset[str] = frozenset({
    "BIT", "SUB", "LIG",        # coal varieties
    "NG",                        # natural gas
    "DFO", "RFO", "JF", "KER",  # oil
    "NUC",                       # nuclear
    "PC", "RC", "SC", "WC",     # coal derivatives
    "SGC",                       # syngas/coal
    "OIL",                       # generic oil
})

# Public download URL (no auth required).  The April 2026 file is the most
# current as of 2026-06-08 and covers all retirements through that date.
# NOTE: the `/archive/xls/` path, NOT the primary `/xls/` one.  EIA retired the
# primary path — it 301s to a 503 and serves a ~67 KB HTML error page, which
# fails openpyxl with BadZipFile.  This shipped broken from ~June to 2026-08-25
# and broke every refresh, local and CI alike.
#
# `scripts/build_planned_retirements.py` and `scripts/build_ap1000_sites.py` read
# the same workbook under the same cache key and must keep the same URL — they
# moved to /archive/ long before this connector did, which is the drift that hid
# the bug.  `tests/test_eia_retired_plants.py` guards both facts.
EIA_860M_URL = (
    "https://www.eia.gov/electricity/data/eia860m/archive/xls/april_generator2026.xlsx"
)

# Source-file column indices (0-based) in the "Retired" sheet.
# Row 0 = title banner, row 1 = blank, row 2 = header — data starts row 3.
_COL_PLANT_ID  = 2
_COL_PLANT_NAME = 3
_COL_STATE      = 6
_COL_MW         = 13   # Net Summer Capacity (MW)
_COL_FUEL       = 16   # Energy Source Code
_COL_RET_YEAR   = 21   # Retirement Year
_COL_LAT        = 24
_COL_LON        = 25

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


class EiaRetiredPlants(Connector):
    slug = "eia-retired-plants"
    source_label = (
        "EIA Form EIA-860M — Preliminary Monthly Electric Generator Inventory "
        "(Retired sheet, April 2026)"
    )
    source_url = "https://www.eia.gov/electricity/data/eia860m/"

    # Run after all producer connectors (they write the per-program JSON files
    # we read here).  Placed between infra-proximity (300) and ai-summary (400).
    run_order = 325

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument(
                "--limit",
                type=int,
                default=None,
                help="Cap the number of enriched records (default: unlimited).",
            )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        if not _HAS_OPENPYXL:
            log.error(
                "openpyxl is required for eia-retired-plants — "
                "install it with: pip install openpyxl"
            )
            return []

        sites = list(self._load_sites())
        if not sites:
            log.error(
                "no per-program JSON files found in %s — run --all (or each "
                "producer connector) before --source eia-retired-plants",
                self._data_dir(),
            )
            return []
        log.info("loaded %d sites across %d program files",
                 len(sites), self._loaded_program_count)

        missing_only = bool(getattr(args, "missing_only", False))
        if missing_only:
            covered = self.existing_ids()
            if covered:
                before = len(sites)
                sites = [s for s in sites if s.get("id") not in covered]
                log.info(
                    "--missing-only: %d/%d sites already covered, %d remaining",
                    before - len(sites), before, len(sites),
                )
            if not sites:
                existing = self.existing_records()
                log.info(
                    "--missing-only: nothing to fetch; returning %d existing records",
                    len(existing),
                )
                return existing

        idx = self._build_retired_plant_index(use_cache=use_cache)
        if idx.point_count == 0:
            log.error("retired-plant index empty — aborting")
            return []
        log.info("[eia-retired-plants] indexed %d plants", idx.point_count)

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        matched = 0

        for site in sites:
            sid = site.get("id")
            program = site.get("program")
            lat = site.get("lat")
            lon = site.get("lon")
            if not sid or not program or lat is None or lon is None:
                skipped_no_geom += 1
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                skipped_no_geom += 1
                continue

            hit = idx.nearest_with_attr(lat_f, lon_f)
            if hit is None:
                continue
            dist_mi, attr = hit
            if dist_mi > MAX_DISTANCE_MI:
                continue

            rec: dict[str, Any] = {
                "id": sid,
                "program": program,
                "retired_plant_mi": round(dist_mi, 2),
            }
            if attr.get("mw") is not None:
                rec["retired_plant_mw"] = round(float(attr["mw"]), 1)
            if attr.get("fuel"):
                rec["retired_plant_fuel"] = str(attr["fuel"])
            if attr.get("ret_year") is not None:
                rec["retired_plant_year"] = int(attr["ret_year"])
            if attr.get("name"):
                rec["retired_plant_name"] = str(attr["name"])
            records.append(rec)
            matched += 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        log.info("[eia-retired-plants] %d / %d sites have a large retired plant within %.0f mi",
                 matched, len(sites), MAX_DISTANCE_MI)

        if getattr(args, "limit", None):
            records = records[: args.limit]

        if missing_only:
            existing = self.existing_records()
            merged = self.merge_records_by_id(records, existing)
            log.info(
                "--missing-only: merged %d new + %d existing = %d total",
                len(records), len(existing), len(merged),
            )
            return merged
        return records

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _data_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "docs" / "data"

    def _load_sites(self) -> Iterable[dict[str, Any]]:
        self._loaded_program_count = 0
        for fname in PROGRAM_FILES:
            path = self._data_dir() / fname
            if not path.exists():
                log.info("program file %s missing — skipping", fname)
                continue
            import json
            try:
                payload = json.loads(path.read_text())
            except (OSError, __import__("json").JSONDecodeError) as e:
                log.warning("failed to read %s: %s — skipping", fname, e)
                continue
            for site in payload.get("sites") or []:
                yield site
            self._loaded_program_count += 1

    def _build_retired_plant_index(self, use_cache: bool = True) -> PointIndex:
        """Download EIA-860M Excel, parse 'Retired' sheet, group by Plant ID.

        Multiple generator units at the same plant are aggregated:
          - MW:   sum across all units
          - Fuel: primary fuel of the highest-MW unit
          - Year: most recent retirement year across units
          - Lat/lon: taken from the last row that supplies coordinates

        Returns a PointIndex of all plants with MW ≥ MIN_PLANT_MW, dispatchable
        fuel, and valid lat/lon.
        """
        raw = self.http_get_bytes(
            EIA_860M_URL,
            params={},
            use_cache=use_cache,
            cache_key={"src": "eia_860m_retired"},
        )
        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
        sheet = workbook["Retired"]
        rows = list(sheet.iter_rows(values_only=True))

        # rows[0] = title banner, rows[1] = blank, rows[2] = header
        # Data rows start at index 3.
        data_rows = rows[3:]

        # Group generator rows by Plant ID.
        plants: dict[int, dict[str, Any]] = defaultdict(
            lambda: {
                "name": None, "state": None,
                "lat": None, "lon": None,
                "total_mw": 0.0,
                "primary_fuel_mw": 0.0,
                "fuel": None,
                "ret_year": None,
            }
        )

        for row in data_rows:
            plant_id = row[_COL_PLANT_ID]
            if not plant_id:
                continue
            try:
                plant_id = int(plant_id)
            except (TypeError, ValueError):
                continue

            p = plants[plant_id]

            if p["name"] is None:
                p["name"] = row[_COL_PLANT_NAME]
                p["state"] = row[_COL_STATE]

            # MW (Net Summer)
            mw_raw = row[_COL_MW]
            try:
                mw = float(mw_raw) if mw_raw is not None else 0.0
            except (TypeError, ValueError):
                mw = 0.0
            p["total_mw"] += mw

            # Fuel — keep the fuel of the highest-MW unit
            fuel_raw = row[_COL_FUEL]
            fuel = str(fuel_raw).strip().upper() if fuel_raw else None
            if fuel and mw >= p["primary_fuel_mw"]:
                p["fuel"] = fuel
                p["primary_fuel_mw"] = mw

            # Retirement year (latest across units)
            ret_raw = row[_COL_RET_YEAR]
            try:
                ret_yr = int(ret_raw) if ret_raw is not None else None
            except (TypeError, ValueError):
                ret_yr = None
            if ret_yr is not None and (p["ret_year"] is None or ret_yr > p["ret_year"]):
                p["ret_year"] = ret_yr

            # Coordinates (last row wins if there are multiple units)
            try:
                lat = float(row[_COL_LAT]) if row[_COL_LAT] is not None else None
                lon = float(row[_COL_LON]) if row[_COL_LON] is not None else None
            except (TypeError, ValueError):
                lat = lon = None
            if lat is not None and lon is not None:
                p["lat"] = lat
                p["lon"] = lon

        # Build index from qualified plants.
        idx = PointIndex()
        indexed = 0
        skipped_mw = 0
        skipped_fuel = 0
        skipped_geom = 0

        for plant_id, p in plants.items():
            if p["total_mw"] < MIN_PLANT_MW:
                skipped_mw += 1
                continue
            fuel = (p["fuel"] or "").upper()
            if fuel not in DISPATCHABLE_FUELS:
                skipped_fuel += 1
                continue
            if p["lat"] is None or p["lon"] is None:
                skipped_geom += 1
                continue
            attr = {
                "name": p["name"],
                "mw": p["total_mw"],
                "fuel": p["fuel"],
                "ret_year": p["ret_year"],
            }
            added = idx.add_point(p["lat"], p["lon"], attr=attr)
            if added:
                indexed += 1

        log.info(
            "[eia-retired-plants] parsed %d plants: indexed=%d "
            "skipped(mw<%.0f)=%d skipped(non-dispatchable)=%d skipped(no-geom)=%d",
            len(plants), indexed, MIN_PLANT_MW, skipped_mw, skipped_fuel, skipped_geom,
        )
        return idx

    def http_get_bytes(
        self,
        url: str,
        params: dict,
        use_cache: bool,
        cache_key: dict,
    ) -> bytes:
        """Fetch raw bytes (for binary files like Excel).

        Uses the standard Connector HTTP cache — key is SHA-256 of the
        canonical cache_key dict.  Falls back to a direct request when the
        cache is empty or use_cache=False.
        """
        import hashlib
        import json as _json

        key_str = _json.dumps(cache_key, sort_keys=True)
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:16]
        cache_path = self.cache_dir / f"{key_hash}.bin"

        if use_cache and cache_path.exists():
            log.debug("[eia-retired-plants] cache hit: %s", cache_path.name)
            return cache_path.read_bytes()

        import requests as _requests
        import time

        log.info("[eia-retired-plants] fetching %s", url)
        time.sleep(1.5)
        resp = _requests.get(
            url,
            headers={"User-Agent": "BrownfieldOpportunities/0.2 (research; static dashboard)"},
            timeout=120,
        )
        resp.raise_for_status()

        data = resp.content
        cache_path.write_bytes(data)
        log.info("[eia-retired-plants] cached %d bytes → %s", len(data), cache_path.name)
        return data
