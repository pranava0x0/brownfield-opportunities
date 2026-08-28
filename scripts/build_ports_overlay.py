#!/usr/bin/env python3
"""Build docs/data/ports.json — a map overlay of BTS/USACE Principal Ports.

Why this matters
-----------------
The Maritime Siting tab ranks brownfield sites for floating/offshore nuclear
and coastal on-site generation/data-center suitability, both of which
depend on proximity to a real, navigable, deep-enough port — not just "near
water". This overlay is the port catalog (for map markers + the
port-proximity connector's spatial index); it is NOT a SiteRecord set.

Source (live-fetched, not curated)
-----------------------------------
`NTAD_Hazard_Exposure_Principal_Ports`, hosted on USDOT/BTS's public ArcGIS
Online org (`services.arcgis.com/xOi1kZaI0eWDREZv`) — the top 150 US ports by
annual tonnage (US Army Corps of Engineers' Principal Ports list, refreshed
periodically by BTS's National Transportation Atlas Database). No API key.
Polygon geometry; `TYPE` is `Coastal`, `Great Lakes`, or `Internal`.

We keep ONLY Coastal + Great Lakes ports — internal river ports (e.g.
Memphis-Shelby, Kaskaskia) are excluded because this tab's thesis is
saltwater/Great-Lakes-Seaway coastal access (eventual tow-out for a floating
reactor; deep-water vessel calls for heavy equipment), which an internal
river port doesn't provide. See data-source-research.md §33 for the probe
history — NOAA's mirror of this same dataset is token-gated; this BTS org
hosts it publicly.

`lat`/`lon` are the polygon's bounding-box center (`envelope_center` — the
same convention `connectors/dod_brac.py` uses for polygon geometry), not a
true area-weighted centroid; port polygons are compact enough that this is
within margin-of-error for a proximity join. The layer also carries FEMA
NRI hurricane-frequency data per port, kept as `hurricane_freq` — a free
coastal-hazard proxy for the offshore-nuclear scoring lens.

Re-run: `python3 scripts/build_ports_overlay.py` (BTS updates the source
periodically; no caching needed at 150 rows / one query).
"""
from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema import Port  # noqa: E402

# Load envelope_center directly from geom.py to avoid pulling in the full
# connectors package (and its `requests` dependency chain) for one helper —
# same sandboxing rationale as build_coal_conversions.py's PointIndex load.
_geom_spec = importlib.util.spec_from_file_location("geom", str(ROOT / "connectors" / "geom.py"))
_geom_mod = importlib.util.module_from_spec(_geom_spec)
_geom_spec.loader.exec_module(_geom_mod)
envelope_center = _geom_mod.envelope_center

log = logging.getLogger("build_ports_overlay")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_PATH = ROOT / "docs" / "data" / "ports.json"
SOURCE_URL = "https://www.bts.gov/ntad"
QUERY_URL = (
    "https://services.arcgis.com/xOi1kZaI0eWDREZv/ArcGIS/rest/services/"
    "NTAD_Hazard_Exposure_Principal_Ports/FeatureServer/0/query"
)
USER_AGENT = "brownfield-opportunities/ports-overlay (services.arcgis.com NTAD)"
KEPT_TYPES = {"Coastal", "Great Lakes"}
VERIFIED_AT = "2026-08-27"

# Every NTAD PRINCIPAL_PORT name ends with its 2-letter state/territory code
# ("Galveston, TX", "Honolulu, O'ahu, HI") — confirmed against all 108 kept
# rows on 2026-08-28. Used only to remap AK/HI/PR/VI ports into the map's
# cartographic insets (see applyInsetRemap() in app.js) — those markers use
# raw coordinates otherwise and are unreachable outside the lower-48
# US_BOUNDS (Codex review, this PR).
_STATE_SUFFIX_RE = re.compile(r",\s*([A-Z]{2})$")


def _parse_state(name: str) -> str | None:
    m = _STATE_SUFFIX_RE.search(name)
    return m.group(1) if m else None


def _fetch() -> list[dict]:
    params = {
        "where": "1=1",
        "outFields": "PRINCIPAL_PORT,TYPE,Hurricane_NRI_AnnualFreq",
        "returnGeometry": "true",
        "f": "json",
    }
    url = QUERY_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"ArcGIS API error: {data['error']}")
    return data.get("features") or []


def build() -> None:
    features = _fetch()
    log.info("fetched %d principal-port features", len(features))

    rows: list[dict] = []
    skipped_type = 0
    skipped_geom = 0
    for feat in features:
        attrs = feat.get("attributes") or {}
        port_type = attrs.get("TYPE")
        if port_type not in KEPT_TYPES:
            skipped_type += 1
            continue
        name = attrs.get("PRINCIPAL_PORT")
        rings = (feat.get("geometry") or {}).get("rings")
        if not name or not rings:
            skipped_geom += 1
            continue
        try:
            lon, lat = envelope_center(rings)
        except ValueError:
            skipped_geom += 1
            continue
        freq = attrs.get("Hurricane_NRI_AnnualFreq")
        raw = {
            "name": name,
            "port_type": port_type,
            "state": _parse_state(name),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "hurricane_freq": round(float(freq), 4) if freq is not None else None,
            "source_url": SOURCE_URL,
            "verified_at": VERIFIED_AT,
        }
        rec = Port.model_validate(raw)
        rows.append(json.loads(rec.model_dump_json(exclude_none=True)))

    log.info(
        "kept %d ports (Coastal/Great Lakes); skipped %d Internal-type, %d missing geometry",
        len(rows), skipped_type, skipped_geom,
    )

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "BTS/USACE NTAD Principal Ports (top 150 US ports by tonnage; "
                  "Coastal + Great Lakes types only)",
        "source_url": SOURCE_URL,
        "count": len(rows),
        "sites": rows,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s (%d ports, %d bytes)", OUT_PATH, len(rows), OUT_PATH.stat().st_size)


if __name__ == "__main__":
    build()
