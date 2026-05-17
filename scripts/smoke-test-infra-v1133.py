#!/usr/bin/env python3
"""Smoke test for the v1.13.3 infra-proximity additions.

Runs the connector against a hand-picked Alabama subset (10 sites covering
geographic diversity) with substation + power_plant + flood_zone enabled.
Verifies that:
- Substation index builds across all 7 Overpass bboxes
- Power plant index pulls down (~13k nationwide via HIFLD pagination)
- Per-site FEMA flood lookups complete with realistic data
- The enriched record carries the new fields with sensible values

NOT part of the unit test suite — hits real APIs, takes ~3 min cold and
~10s warm. Run before the full nationwide enrichment to catch source-side
breakage early.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connectors.infra_proximity import InfraProximity  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# 10 Alabama sites with geographic diversity: north (Huntsville), central
# (Birmingham/Anniston/Auburn), south (Mobile), Gulf coast.
AL_SAMPLE = [
    {"id": "AL7210020742", "program": "superfund",
     "name": "USARMY/NASA REDSTONE ARSENAL",
     "lat": 34.629981, "lon": -86.653678, "state": "AL"},
    {"id": "AL3210020027", "program": "superfund",
     "name": "ANNISTON ARMY DEPOT",
     "lat": 33.633, "lon": -85.948, "state": "AL"},
    {"id": "AL2210020743", "program": "superfund",
     "name": "OLIN CORP MCINTOSH PLANT",
     "lat": 31.272, "lon": -88.027, "state": "AL"},
    {"id": "ACRES-AL-1", "program": "brownfield",
     "name": "AL Brownfield 1 (Birmingham)",
     "lat": 33.5207, "lon": -86.8025, "state": "AL"},
    {"id": "ACRES-AL-2", "program": "brownfield",
     "name": "AL Brownfield 2 (Mobile)",
     "lat": 30.6954, "lon": -88.0399, "state": "AL"},
    {"id": "ACRES-AL-3", "program": "brownfield",
     "name": "AL Brownfield 3 (Montgomery)",
     "lat": 32.3617, "lon": -86.2792, "state": "AL"},
    {"id": "ACRES-AL-4", "program": "brownfield",
     "name": "AL Brownfield 4 (Auburn)",
     "lat": 32.6099, "lon": -85.4808, "state": "AL"},
    {"id": "ACRES-AL-5", "program": "brownfield",
     "name": "AL Brownfield 5 (Tuscaloosa)",
     "lat": 33.2098, "lon": -87.5692, "state": "AL"},
    {"id": "FUDS-AL-1", "program": "fuds",
     "name": "AL FUDS 1 (Decatur)",
     "lat": 34.6059, "lon": -86.9833, "state": "AL"},
    {"id": "FUDS-AL-2", "program": "fuds",
     "name": "AL FUDS 2 (Dothan)",
     "lat": 31.2232, "lon": -85.3905, "state": "AL"},
]


def main() -> int:
    cache_dir = ROOT / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    inst = InfraProximity(cache_dir=cache_dir)

    # Run with all 7 layers (4 polyline + 2 point + flood).
    args = argparse.Namespace(
        limit=None,
        infra_skip_transmission=False,
        infra_skip_highway=False,
        infra_skip_rail=False,
        infra_skip_gas_pipeline=False,
        infra_skip_substation=False,
        infra_skip_power_plant=False,
        infra_skip_flood_zone=False,
        missing_only=False,
    )

    with patch.object(inst, "_load_sites", return_value=iter(AL_SAMPLE)):
        # Mimic the `_load_sites()` side effect that sets `_loaded_program_count`.
        inst._loaded_program_count = 3  # superfund + brownfield + fuds
        records = inst.fetch_records(args, use_cache=True)

    print()
    print(f"=== Smoke test results: {len(records)} records ===\n")

    # Field coverage across the sample.
    new_fields = ["substation_mi", "substation_kv", "power_plant_mi",
                  "power_plant_mw", "power_plant_fuel", "flood_zone", "in_sfha"]
    for f in new_fields:
        n = sum(1 for r in records if f in r)
        print(f"  {f:20s}  {n}/{len(records)}")

    print("\n--- Detail ---")
    for r in records:
        sid = r["id"]
        name = next((s["name"] for s in AL_SAMPLE if s["id"] == sid), "?")
        bits = [name[:30]]
        for f in ["substation_mi", "substation_kv", "power_plant_mi",
                  "power_plant_mw", "power_plant_fuel", "flood_zone", "in_sfha"]:
            v = r.get(f)
            if v is not None:
                bits.append(f"{f}={v}")
        print("  " + "  ".join(bits))

    return 0


if __name__ == "__main__":
    sys.exit(main())
