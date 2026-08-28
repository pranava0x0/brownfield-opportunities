"""Port / shipyard proximity enrichment connector.

Marks every brownfield site with the distance to the nearest BTS/USACE
Principal Port (Coastal or Great Lakes type) and the nearest curated major
US heavy-shipbuilding / fabrication yard. Feeds the Maritime Siting tab's
two scoring lenses in docs/maritime-score.js:

  * Floating/offshore nuclear — needs a shipyard with heavy-lift or
    graving-dock capacity to assemble and launch a barge-mounted reactor,
    plus deep-enough coastal/Great-Lakes water access for eventual tow-out
    and mooring.
  * Coastal on-site generation / data centers — port access is a heavy-
    equipment (transformers, turbines, SMR modules) delivery mode, a
    supplement to the rail/highway signals infra-proximity already scores.

Sources (both PRE-BUILT overlays this connector reads, not fetches):
  * docs/data/ports.json — live-fetched by scripts/build_ports_overlay.py
    from the public NTAD_Hazard_Exposure_Principal_Ports FeatureServer
    (top 150 US ports by tonnage; Coastal + Great Lakes types kept).
  * docs/data/shipyards.json — curated by scripts/build_shipyards.py (no
    public GIS layer of US shipyards exists — MARAD publishes PDF surveys
    only; see data-source-research.md §33).

Output: docs/data/port-proximity.json
  Tombstone convention (infra-proximity, v1.11.5): EVERY site in the four
  program files gets a `{id, program}` record, even when nothing is within
  range — a missing field means "checked, nothing within MAX_DISTANCE_MI",
  not "not yet checked". The frontend distinguishes the two via a
  `_portChecked` stamp set by ensurePortProximityLoaded(), mirroring
  `_infraChecked`.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import PointIndex

log = logging.getLogger("connector.port_proximity")

# Past this radius "nearest port" stops being a meaningful coastal-siting
# signal — interior sites should read as landlocked (null), not "412 mi to
# the coast". Ports layer has 108 features (Coastal + Great Lakes) after
# filtering, sparser than infra-proximity's transmission-line network, so
# the radius is wider than that connector's typical few-mile bands.
MAX_DISTANCE_MI_PORT = 75.0

# Only 16 curated yards nationwide, so a wider radius than ports — but still
# tight enough that "150 mi to the nearest shipyard" reads honestly as far,
# not close. The scoring curve (maritime-score.js) decays well before this
# cap; the cap only controls when the field is present at all.
MAX_DISTANCE_MI_SHIPYARD = 150.0

PORTS_FILE = "ports.json"
SHIPYARDS_FILE = "shipyards.json"

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


class PortProximity(Connector):
    slug = "port-proximity"
    source_label = (
        "BTS/USACE NTAD Principal Ports (docs/data/ports.json) + curated "
        "major US shipyards (docs/data/shipyards.json)"
    )
    source_url = "https://www.bts.gov/ntad"

    # Enrichment: runs after the producers, alongside the other proximity
    # joins (eia-retired-plants=325, planned-retirements-proximity=326).
    run_order = 327

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
                "producer connector) before --source port-proximity",
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

        port_idx = self._build_index(PORTS_FILE, self._port_attr)
        yard_idx = self._build_index(SHIPYARDS_FILE, self._yard_attr)
        if port_idx.point_count == 0:
            log.error(
                "port index empty — run scripts/build_ports_overlay.py first; aborting"
            )
            return self.existing_records() if missing_only else []
        if yard_idx.point_count == 0:
            log.warning(
                "shipyard index empty — run scripts/build_shipyards.py first "
                "(continuing with port-only output)"
            )
        log.info("[port-proximity] indexed %d ports, %d shipyards",
                 port_idx.point_count, yard_idx.point_count)

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        matched_port = 0
        matched_yard = 0

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

            rec: dict[str, Any] = {"id": sid, "program": program}

            port_hit = port_idx.nearest_with_attr(lat_f, lon_f)
            if port_hit is not None:
                dist_mi, attr = port_hit
                if dist_mi <= MAX_DISTANCE_MI_PORT:
                    rec["port_mi"] = round(dist_mi, 2)
                    rec["port_name"] = attr["name"]
                    rec["port_type"] = attr["port_type"]
                    if attr.get("hurricane_freq") is not None:
                        rec["port_hurricane_freq"] = attr["hurricane_freq"]
                    matched_port += 1

            yard_hit = yard_idx.nearest_with_attr(lat_f, lon_f) if yard_idx.point_count else None
            if yard_hit is not None:
                dist_mi, attr = yard_hit
                if dist_mi <= MAX_DISTANCE_MI_SHIPYARD:
                    rec["shipyard_mi"] = round(dist_mi, 2)
                    rec["shipyard_name"] = attr["name"]
                    rec["shipyard_capability"] = attr["capability"]
                    matched_yard += 1

            # Tombstone convention: always emit, even with neither field —
            # a missing entry would be ambiguous between "landlocked" and
            # "connector never ran" (the v1.11.5 infra-proximity lesson).
            records.append(rec)

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        log.info(
            "[port-proximity] %d / %d sites within %.0f mi of a port; "
            "%d / %d within %.0f mi of a shipyard",
            matched_port, len(records), MAX_DISTANCE_MI_PORT,
            matched_yard, len(records), MAX_DISTANCE_MI_SHIPYARD,
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

    @staticmethod
    def _port_attr(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": row.get("name"),
            "port_type": row.get("port_type"),
            "hurricane_freq": row.get("hurricane_freq"),
        }

    @staticmethod
    def _yard_attr(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": row.get("name"),
            "capability": row.get("capability"),
        }

    def _build_index(self, filename: str, attr_fn) -> PointIndex:
        path = self._data_dir() / filename
        idx = PointIndex()
        if not path.exists():
            log.error("overlay %s missing", filename)
            return idx
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.error("failed to read %s: %s", filename, e)
            return idx
        rows = payload.get("sites") if isinstance(payload, dict) else payload
        rows = rows or []
        indexed = 0
        skipped = 0
        for row in rows:
            lat = row.get("lat")
            lon = row.get("lon")
            if lat is None or lon is None:
                skipped += 1
                continue
            try:
                added = idx.add_point(float(lat), float(lon), attr=attr_fn(row))
            except (TypeError, ValueError):
                skipped += 1
                continue
            if added:
                indexed += 1
        if skipped:
            log.info("[%s] skipped %d rows with missing/invalid geometry", filename, skipped)
        return idx
