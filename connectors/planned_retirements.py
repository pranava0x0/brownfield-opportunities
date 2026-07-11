"""Planned-retirements proximity enrichment connector.

Marks every brownfield site with the distance to the nearest large
OPERATING power plant that has an ANNOUNCED retirement date (≥100 MW,
dispatchable fuel) from EIA-860M's "Operating" sheet `Planned Retirement
Year` column.

Why this matters — the forward-looking counterpart to eia-retired-plants:
A retired plant's interconnect is already stranded; a *planned*-retirement
plant's interconnect frees on a KNOWN future date, and the repowering /
co-location deals are struck BEFORE shutdown (the Homer City pattern —
the buyer contracts the site while the plant is still running so the
switchyard, ROW, and network upgrades transfer without a queue re-study).
The nearer the announced retirement, the more actionable the signal.

Source: the same 90-plant overlay `scripts/build_planned_retirements.py`
already distilled from the EIA-860M "Operating" sheet — we read that JSON
rather than re-parsing the workbook (DRY; the script owns the fuel /
capacity / dispatchability filtering). Each overlay plant carries
lat/lon/mw/fuel and `first_retirement_year` / `last_retirement_year`.

Output: docs/data/planned-retirements-proximity.json
  Per-site records: {id, program, planned_retirement_mi, planned_retirement_mw,
                     planned_retirement_fuel, planned_retirement_year,
                     planned_retirement_name}
  Only records within MAX_DISTANCE_MI are emitted; "no entry" means "no
  large planned-retirement plant nearby" (same semantics as
  eia-retired-plants, not the infra-proximity tombstone convention).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import PointIndex

log = logging.getLogger("connector.planned_retirements")

# Beyond 5 mi the "adjacent plant frees up" narrative breaks down. Scoring
# fires at ≤3 mi (full ≤1 mi, half 1–3 mi), matching eia-retired-plants.
MAX_DISTANCE_MI = 5.0

# The overlay is already filtered to ≥100 MW dispatchable, but we re-guard
# on capacity so a future overlay change can't silently pull in tiny plants.
MIN_PLANT_MW = 100.0

# The curated overlay produced by scripts/build_planned_retirements.py.
OVERLAY_FILE = "planned-retirements.json"

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


class PlannedRetirements(Connector):
    # NOTE: slug MUST differ from the overlay file `planned-retirements.json`
    # (produced by scripts/build_planned_retirements.py) — the connector's
    # output path is docs/data/<slug>.json, so a matching slug would clobber
    # the overlay. This connector READS that overlay and WRITES the join.
    slug = "planned-retirements-proximity"
    source_label = (
        "EIA Form EIA-860M — Preliminary Monthly Electric Generator Inventory "
        "(Operating sheet, Planned Retirement Year; April 2026)"
    )
    source_url = "https://www.eia.gov/electricity/data/eia860m/"

    # Enrichment: runs after the producers and after eia-retired-plants (325),
    # before ai-summary (400). Reads the per-program JSON files + the overlay.
    run_order = 326

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
        sites = list(self._load_sites())
        if not sites:
            log.error(
                "no per-program JSON files found in %s — run --all (or each "
                "producer connector) before --source planned-retirements",
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

        idx = self._build_plant_index()
        if idx.point_count == 0:
            log.error("planned-retirement index empty — aborting")
            # Under --missing-only, never truncate the on-disk join to empty
            # just because the overlay went missing/corrupt this run — return
            # what's already written (the ECHO/truncation gotcha; see CLAUDE.md
            # "verify len before commit"). A full run legitimately writes empty.
            return self.existing_records() if missing_only else []
        log.info("[planned-retirements] indexed %d plants", idx.point_count)

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
                "planned_retirement_mi": round(dist_mi, 2),
            }
            if attr.get("mw") is not None:
                rec["planned_retirement_mw"] = round(float(attr["mw"]), 1)
            if attr.get("fuel"):
                rec["planned_retirement_fuel"] = str(attr["fuel"])
            if attr.get("year") is not None:
                rec["planned_retirement_year"] = int(attr["year"])
            if attr.get("name"):
                rec["planned_retirement_name"] = str(attr["name"])
            records.append(rec)
            matched += 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        log.info(
            "[planned-retirements] %d / %d sites have a planned-retirement plant within %.0f mi",
            matched, len(sites), MAX_DISTANCE_MI,
        )

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
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as e:
                log.warning("failed to read %s: %s — skipping", fname, e)
                continue
            for site in payload.get("sites") or []:
                yield site
            self._loaded_program_count += 1

    def _build_plant_index(self) -> PointIndex:
        """Index the curated planned-retirement overlay plants.

        Each overlay row already represents one plant (units summed by the
        build script), so no grouping is needed — we just re-guard on
        capacity/geometry and take `last_retirement_year` as the year the
        whole plant is finally offline (the interconnect fully frees then).
        """
        path = self._data_dir() / OVERLAY_FILE
        if not path.exists():
            log.error(
                "overlay %s missing — run scripts/build_planned_retirements.py first",
                OVERLAY_FILE,
            )
            return PointIndex()
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.error("failed to read %s: %s", OVERLAY_FILE, e)
            return PointIndex()
        # The overlay wraps its plant list under "sites" (same envelope the
        # build script writes); tolerate a bare list too.
        plants = payload.get("sites") if isinstance(payload, dict) else payload
        plants = plants or []

        idx = PointIndex()
        indexed = 0
        skipped_mw = 0
        skipped_geom = 0
        for p in plants:
            lat = p.get("lat")
            lon = p.get("lon")
            mw = p.get("mw")
            if lat is None or lon is None:
                skipped_geom += 1
                continue
            try:
                mw_f = float(mw) if mw is not None else 0.0
            except (TypeError, ValueError):
                mw_f = 0.0
            if mw_f < MIN_PLANT_MW:
                skipped_mw += 1
                continue
            # last unit's retirement year = when the plant is fully offline.
            year = p.get("last_retirement_year") or p.get("first_retirement_year")
            attr = {
                "name": p.get("name"),
                "mw": mw_f,
                "fuel": p.get("fuel"),
                "year": year,
            }
            try:
                added = idx.add_point(float(lat), float(lon), attr=attr)
            except (TypeError, ValueError):
                skipped_geom += 1
                continue
            if added:
                indexed += 1

        log.info(
            "[planned-retirements] parsed %d overlay plants: indexed=%d "
            "skipped(mw<%.0f)=%d skipped(no-geom)=%d",
            len(plants), indexed, MIN_PLANT_MW, skipped_mw, skipped_geom,
        )
        return idx
