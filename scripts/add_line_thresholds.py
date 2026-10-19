#!/usr/bin/env python3
"""Add per-voltage line distances to docs/data/infra-proximity.json without a
full infra-proximity refresh (which rebuilds every layer and takes ~20 min).

For each site with a transmission distance, writes transmission_69kv_mi,
transmission_115kv_mi, transmission_230kv_mi and transmission_unknown_kv_mi,
measured from the site's assessed coordinates against the cached HIFLD
transmission index. It calls the connector's own line_threshold_fields(), so a
later full refresh produces the same values.

  python3 scripts/add_line_thresholds.py     # then: python3 scripts/build_infra_core.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connectors.infra_proximity import LAYERS, InfraProximity, line_threshold_fields  # noqa: E402

FULL = ROOT / "docs" / "data" / "infra-proximity.json"
FIELDS = ("transmission_69kv_mi", "transmission_115kv_mi", "transmission_230kv_mi", "transmission_unknown_kv_mi")


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    payload = json.loads(FULL.read_text())
    lines = InfraProximity(cache_dir=ROOT / "data" / "cache")._build_index(
        "transmission", LAYERS["transmission"], use_cache=True)
    done = 0
    for site in payload["sites"]:
        for field in FIELDS:
            site.pop(field, None)
        lat, lon = site.get("infra_assessed_lat"), site.get("infra_assessed_lon")
        if site.get("transmission_mi") is None or lat is None or lon is None:
            continue
        site.update(line_threshold_fields(lines, lat, lon))
        done += 1
    FULL.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    print(f"added per-voltage line distances to {done:,} of {len(payload['sites']):,} sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
