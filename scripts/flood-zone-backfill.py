#!/usr/bin/env python3
"""Incremental flood_zone backfill for docs/data/infra-proximity.json.

The infra-proximity connector's flood_zone field is opt-in and the
connector design rewrites the whole file at end-of-run, so a partial
run loses all in-flight work. This script updates the file in place
every CHECKPOINT_EVERY records, so a 20-hour multi-session backfill is
resumable across sessions / process kills.

Usage:
    scripts/flood-zone-backfill.py             # run until exhausted
    scripts/flood-zone-backfill.py --limit 500 # cap at N sites this run
    scripts/flood-zone-backfill.py --budget-mins 60

Cache compatibility: re-uses InfraProximity._query_flood_zone() and the
shared data/cache directory, so cached FEMA responses from a normal
`refresh.py --source infra-proximity` run (no --infra-skip-flood-zone)
are picked up and vice-versa.
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connectors.infra_proximity import InfraProximity  # noqa: E402

CACHE_DIR = ROOT / "data" / "cache"
INFRA_FILE = ROOT / "docs" / "data" / "infra-proximity.json"
PRODUCER_FILES = [
    ROOT / "docs" / "data" / "superfund-npl.json",
    ROOT / "docs" / "data" / "epa-acres.json",
    ROOT / "docs" / "data" / "dod-fuds.json",
    ROOT / "docs" / "data" / "dod-brac.json",
]
CHECKPOINT_EVERY = 50

log = logging.getLogger("flood-backfill")


def load_site_coords() -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    for path in PRODUCER_FILES:
        if not path.exists():
            log.warning("producer file missing: %s", path.name)
            continue
        payload = json.loads(path.read_text())
        for site in payload.get("sites", []):
            sid = site.get("id")
            lat = site.get("lat")
            lon = site.get("lon")
            if sid and lat is not None and lon is not None:
                try:
                    coords[sid] = (float(lat), float(lon))
                except (TypeError, ValueError):
                    pass
    return coords


def write_checkpoint(payload: dict, n_new: int, n_total: int) -> None:
    tmp = INFRA_FILE.with_suffix(".json.tmp")
    payload["count"] = len(payload["sites"])
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(INFRA_FILE)
    log.info("checkpoint: +%d new, %d total flood-enriched records on disk",
             n_new, n_total)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap the number of new lookups this run.")
    ap.add_argument("--budget-mins", type=float, default=None,
                    help="Exit gracefully after N minutes of wall time.")
    args = ap.parse_args()

    if not INFRA_FILE.exists():
        log.error("infra-proximity.json missing — run `refresh.py --source infra-proximity` first")
        return 1

    coords = load_site_coords()
    log.info("loaded %d site coordinates from producer files", len(coords))

    payload = json.loads(INFRA_FILE.read_text())
    records: list[dict] = payload["sites"]
    log.info("loaded %d infra-proximity records", len(records))

    needs_flood = [r for r in records if r.get("flood_zone") is None]
    log.info("flood_zone missing on %d / %d records (%.1f%%)",
             len(needs_flood), len(records), 100 * len(needs_flood) / len(records))

    if not needs_flood:
        log.info("nothing to do — flood_zone already populated on every record")
        return 0

    inst = InfraProximity(cache_dir=CACHE_DIR)
    stop_requested = False
    def _handle_sigterm(*_):
        nonlocal stop_requested
        log.info("signal received — finishing current record and checkpointing")
        stop_requested = True
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    cap = args.limit if args.limit and args.limit > 0 else None
    deadline = (time.time() + 60 * args.budget_mins) if args.budget_mins else None

    new_lookups = 0
    populated = 0
    skipped_no_coord = 0
    errored = 0
    for i, rec in enumerate(needs_flood, 1):
        if stop_requested:
            log.info("stop_requested — breaking after %d", i - 1)
            break
        if cap is not None and new_lookups >= cap:
            log.info("--limit %d reached; stopping", cap)
            break
        if deadline is not None and time.time() >= deadline:
            log.info("--budget-mins exhausted; stopping")
            break
        sid = rec.get("id")
        if not sid:
            continue
        latlon = coords.get(sid)
        if not latlon:
            skipped_no_coord += 1
            continue
        lat, lon = latlon
        try:
            fz, sfha = inst._query_flood_zone(lat, lon, use_cache=True)
        except Exception as e:  # pragma: no cover - network / transient
            log.warning("[%s] flood query failed: %s — skipping", sid, type(e).__name__)
            errored += 1
            continue
        new_lookups += 1
        if fz is not None:
            rec["flood_zone"] = fz
            populated += 1
        if sfha is not None:
            rec["in_sfha"] = sfha

        if new_lookups % CHECKPOINT_EVERY == 0:
            n_with_zone = sum(1 for r in records if r.get("flood_zone") is not None)
            write_checkpoint(payload, populated, n_with_zone)

        if new_lookups % 10 == 0:
            log.info("[%d/%d] lookups=%d, populated=%d, errors=%d",
                     i, len(needs_flood), new_lookups, populated, errored)

    # Final write
    n_with_zone = sum(1 for r in records if r.get("flood_zone") is not None)
    write_checkpoint(payload, populated, n_with_zone)
    log.info("DONE. lookups=%d, populated=%d (with zone), missing-coord=%d, errors=%d",
             new_lookups, populated, skipped_no_coord, errored)
    log.info("flood_zone coverage now %d/%d (%.1f%%)",
             n_with_zone, len(records), 100 * n_with_zone / len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
