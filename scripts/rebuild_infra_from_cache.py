#!/usr/bin/env python3
"""Recompute infrastructure safely from local raw snapshots, without network.

Skipped flood observations survive with explicit legacy provenance. This is a
recalculation, not a claim that upstream infrastructure was refreshed today.
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from connectors.infra_proximity import InfraProximity, LAYERS
from schema import Payload


class CachedInfrastructure(InfraProximity):
    def http_get_json(self, url: str, params: dict, use_cache: bool = True, cache_key: object = None) -> dict:
        path = self.cache_path(cache_key if cache_key is not None else {"url": url, "params": params})
        if not path.exists():
            raise FileNotFoundError(f"Cache-only rebuild needs {path}; output preserved")
        return json.loads(path.read_text())

    def _fetch_overpass_substations(self, bbox: tuple, use_cache: bool) -> list[dict]:
        path = self.cache_path({"src": "overpass_substations", "bbox": list(bbox)})
        if not path.exists():
            raise FileNotFoundError(f"Cache-only rebuild needs {path}; output preserved")
        return super()._fetch_overpass_substations(bbox, True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pure-python", action="store_true", help="Disable optional installed NumPy acceleration")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/data/infra-proximity.json")
    args = parser.parse_args()
    if not args.pure_python:
        import connectors.infra_proximity as infra_module
        from scripts.cached_spatial_acceleration import AcceleratedSegmentIndex
        infra_module.SegmentIndex = AcceleratedSegmentIndex
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    previous = json.loads((ROOT / "docs/data/infra-proximity.json").read_text())
    layers = list(LAYERS) + ["substation", "power_plant"]
    merged: dict[str, dict] = {}
    metadata: dict = {}
    for layer in layers:
        logging.info("Rebuilding %s; only this layer's spatial index is resident", layer)
        connector = CachedInfrastructure(ROOT / "data/cache")
        flags = argparse.Namespace(limit=None, missing_only=False, infra_skip_flood_zone=True)
        for other in layers:
            setattr(flags, "infra_skip_" + other, other != layer)
        batch = connector.fetch_records(flags, True)
        if not merged:
            merged = {row["id"]: row for row in batch}
        else:
            for row in batch:
                target = merged[row["id"]]
                for key in list(target):
                    if key.startswith(layer + "_"):
                        del target[key]
                target.update({key: value for key, value in row.items() if key.startswith(layer + "_")})
                target["infra_evidence"][layer] = row["infra_evidence"][layer]
        metadata[layer] = connector.source_metadata.get(layer, {})
        del batch, connector
        gc.collect()
    rows = list(merged.values())
    if len(rows) < previous["count"]:
        raise ValueError(f"Refusing smaller infrastructure coverage: {len(rows)} < {previous['count']}")
    connector = CachedInfrastructure(ROOT / "data/cache")
    connector.source_metadata = metadata
    connector._metadata("flood_zone", source_url="https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28",
                        snapshot_basis="retained_legacy_values; coordinate and retrieval date unverified", source_snapshot_at=None)
    rows = connector.compact_evidence(rows)
    payload = Payload(generated_at=datetime.now(timezone.utc).isoformat(), source=connector.source_label,
                      source_url=connector.source_url, source_metadata=connector.source_metadata,
                      count=len(rows), sites=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    staged = args.output.with_suffix(".staged.json")
    staged.write_text(payload.model_dump_json(exclude_none=True))
    Payload.model_validate_json(staged.read_text())
    staged.replace(args.output)
    logging.info("Validated and replaced %s: %d sites; raw sources remain historical snapshots", args.output, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
