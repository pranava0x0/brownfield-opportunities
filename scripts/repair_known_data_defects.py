#!/usr/bin/env python3
"""Apply the connector-level fixes from 2026-08-09 to the already-shipped JSON.

The connectors are fixed, but their output only changes on the next full
refresh — which needs hours of network time. This script applies the exact
same deterministic transformations to the files on disk so the data and the
code agree in the meantime.

It only does things that are pure functions of what is already on disk. It
does NOT invent values, re-fetch anything, or touch the coordinate problems
(those need upstream corrections, and are tracked as WARN in the validator).

Nor does it delete merely SUSPICIOUS values. An earlier draft dropped
RE-Powering acreages that disagreed with the NPL boundary by more than 100x;
that rule also removed a 153.7-acre figure whose only sin was sitting against
a 1.0-acre baseline, because small denominators make ratios explode. Values
that are implausible but not provably wrong stay put and stay reported by
`redev-acreage-agreement`.

Each repair mirrors a specific connector change:

  duplicate-ids      dod_fuds.fetch_records() now dedupes by id
  zero-acreage       superfund_npl.normalize() now coerces acreage <= 0 to None
  zero-plant-mw      HIFLD Total_MW of 0 is a missing value, not a measurement
  low-voltage-subs   OSM sub-1 kV gear is not an interconnection candidate

Idempotent: running it twice changes nothing the second time.

    python3 scripts/repair_known_data_defects.py --dry-run
    python3 scripts/repair_known_data_defects.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"

# Below this a "substation" is distribution / traction gear, not a grid
# interconnection point.
MIN_TRANSMISSION_KV = 1.0

# Files that carry a row per site id and so inherited the duplicate.
DUPLICATE_BEARING_FILES = [
    "dod-fuds.json", "fema-nri.json", "infra-proximity.json",
    "ira-energy-community.json", "opportunity-zone.json",
]


def load(name: str) -> tuple[dict, str]:
    raw = (DATA / name).read_text()
    return json.loads(raw), raw


def dump(name: str, payload: dict) -> None:
    """Write back in the connector's exact serialization (minified, UTF-8)."""
    (DATA / name).write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    )


def repair_duplicate_ids(changes: list[str], dry: bool) -> None:
    for name in DUPLICATE_BEARING_FILES:
        payload, _ = load(name)
        sites = payload.get("sites") or []
        seen, kept = set(), []
        removed = []
        for rec in sites:
            sid = rec.get("id")
            if sid in seen:
                removed.append(sid)
                continue
            seen.add(sid)
            kept.append(rec)
        if not removed:
            continue
        changes.append(f"{name}: removed {len(removed)} duplicate row(s) "
                       f"({', '.join(sorted(set(removed)))})")
        if not dry:
            payload["sites"] = kept
            payload["count"] = len(kept)
            dump(name, payload)


def repair_zero_acreage(changes: list[str], dry: bool) -> None:
    """acreage <= 0 means 'unknown', which the schema spells as absent."""
    for name in ("superfund-npl.json", "epa-redev.json"):
        payload, _ = load(name)
        n = 0
        for rec in payload.get("sites") or []:
            ac = rec.get("acreage")
            if ac is not None and ac <= 0:
                del rec["acreage"]
                n += 1
        if n:
            changes.append(f"{name}: dropped {n} non-positive acreage value(s)")
            if not dry:
                dump(name, payload)


def repair_infra_sentinels(changes: list[str], dry: bool) -> None:
    payload, _ = load("infra-proximity.json")
    zero_mw = low_kv = 0
    for rec in payload.get("sites") or []:
        mw = rec.get("power_plant_mw")
        if mw is not None and mw <= 0:
            del rec["power_plant_mw"]
            zero_mw += 1
        kv = rec.get("substation_kv")
        if kv is not None and kv < MIN_TRANSMISSION_KV:
            del rec["substation_kv"]
            low_kv += 1
    if zero_mw:
        changes.append(f"infra-proximity.json: dropped {zero_mw} power_plant_mw=0")
    if low_kv:
        changes.append(
            f"infra-proximity.json: dropped {low_kv} sub-{MIN_TRANSMISSION_KV:g}kV "
            f"substation_kv value(s)"
        )
    if (zero_mw or low_kv) and not dry:
        dump("infra-proximity.json", payload)


def mirror_sites_json(changes: list[str], dry: bool) -> None:
    """sites.json must stay a byte-exact mirror of superfund-npl.json."""
    src = (DATA / "superfund-npl.json").read_text()
    dst_path = DATA / "sites.json"
    if dst_path.read_text() == src:
        return
    changes.append("sites.json: re-mirrored from superfund-npl.json")
    if not dry:
        dst_path.write_text(src)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change without writing.")
    args = ap.parse_args()

    changes: list[str] = []
    repair_duplicate_ids(changes, args.dry_run)
    repair_zero_acreage(changes, args.dry_run)
    repair_infra_sentinels(changes, args.dry_run)
    # Must run last: it copies the repaired superfund file.
    mirror_sites_json(changes, args.dry_run)

    if not changes:
        print("nothing to repair — data already matches the fixed connectors")
        return 0
    verb = "would apply" if args.dry_run else "applied"
    print(f"{verb} {len(changes)} repair(s):")
    for c in changes:
        print(f"  - {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
