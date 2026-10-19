#!/usr/bin/env python3
"""Write docs/data/infra-proximity-core.json: the distance and voltage fields
from infra-proximity.json, without asset ids, evidence records or source
metadata.

The website loads the core file at startup (screens, table, map) and the full
file only when a site panel opens. Core is ~0.8 MB gzipped against ~2.4 MB for
the full file. Values are copied, never recomputed, so the two cannot disagree;
scripts/validate_data.py check `infra-core-in-sync` fails if they do.

  python3 scripts/build_infra_core.py     # run after every infra-proximity refresh
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "docs" / "data"
FULL = DATA / "infra-proximity.json"
CORE = DATA / "infra-proximity-core.json"
CORE_FIELDS = ("transmission_mi", "transmission_kv", "transmission_69kv_mi", "transmission_115kv_mi",
               "transmission_230kv_mi", "transmission_unknown_kv_mi", "substation_mi", "substation_kv", "substation_role",
               "highway_mi", "rail_mi", "gas_pipeline_mi", "power_plant_mi", "power_plant_mw",
               "power_plant_fuel", "flood_zone", "in_sfha")


def core_payload(full: dict) -> dict:
    sites = [{"id": s["id"], **{k: s[k] for k in CORE_FIELDS if s.get(k) is not None}} for s in full["sites"]]
    # Layer-level metadata (snapshot dates, source URLs) without the per-asset
    # catalogs, so confidence labels match before the full file loads.
    meta = {layer: ({k: v for k, v in m.items() if k != "assets_by_id"} if isinstance(m, dict) else m)
            for layer, m in (full.get("source_metadata") or {}).items()}
    return {"generated_at": full["generated_at"], "source": full.get("source"), "source_url": full.get("source_url"),
            "derived_from": "infra-proximity.json", "source_metadata": meta, "count": len(sites), "sites": sites}


def main() -> int:
    payload = core_payload(json.loads(FULL.read_text()))
    CORE.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    print(f"wrote {payload['count']} sites to {CORE.name} ({CORE.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
