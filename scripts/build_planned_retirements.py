#!/usr/bin/env python3
"""Build docs/data/planned-retirements.json — a map overlay of large OPERATING
power plants with an ANNOUNCED retirement date (EIA-860M "Operating" sheet,
`Planned Retirement Year` column).

Why this matters — the forward-looking generation opportunity
-------------------------------------------------------------
The `eia-retired-plants` connector and the retired-industrial overlay both
surface interconnects that ALREADY went dark. But the best generation-siting
deals are struck BEFORE retirement: an operating coal or gas plant with a
filed retirement date is a known, dated hand-off of a large interconnection
(Homer City announced 2023 → 4.5 GW gas campus FID 2025). As of the April
2026 EIA-860M, ~90 plants ≥100 MW (~75 GW) have announced retirement dates
2026–2043 — each one is a candidate site for repowering (nuclear per DOE's
coal-to-nuclear studies, gas, solar+storage) or a co-located large load.

Source — EIA Form EIA-860M "Operating" sheet (same workbook the
`eia-retired-plants` connector already caches; no API key). Generators with a
non-null `Planned Retirement Year` and a dispatchable fuel are grouped by
Plant ID; MW summed across retiring units; plant kept when total ≥100 MW.

Output envelope mirrors the other overlay files (reference-campuses /
retired-industrial): it is an OVERLAY, NOT a SiteRecord set — stays out of
schema.py / refresh.py and is lazy-loaded by the frontend.

Re-run monthly-ish alongside EIA-860M releases:
  `python3 scripts/build_planned_retirements.py`
"""
from __future__ import annotations

import datetime as dt
import io
import json
import logging
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

log = logging.getLogger("build_planned_retirements")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "planned-retirements.json"

# Same workbook + cache file as connectors/eia_retired_plants.py — the archive
# URL is the working one (the primary /xls/ path returns an HTML page).
EIA_860M_URL = (
    "https://www.eia.gov/electricity/data/eia860m/archive/xls/april_generator2026.xlsx"
)
_EIA_CACHE_FILENAME = "51f37f3890e1b51e.bin"

MIN_PLANT_MW = 100.0

# Mirrors DISPATCHABLE_FUELS in connectors/eia_retired_plants.py — solar/wind
# retirements don't leave the interconnect footprint we're screening for.
DISPATCHABLE_FUELS = frozenset({
    "BIT", "SUB", "LIG", "NG", "DFO", "RFO", "JF", "KER", "NUC",
    "PC", "RC", "SC", "WC", "SGC", "OIL",
})

FUEL_LABEL = {
    "BIT": "coal", "SUB": "coal", "LIG": "coal", "PC": "coal", "RC": "coal",
    "SC": "coal", "WC": "coal", "SGC": "coal",
    "NG": "gas", "DFO": "oil", "RFO": "oil", "JF": "oil", "KER": "oil",
    "OIL": "oil", "NUC": "nuclear",
}


def _get_eia_bytes() -> bytes | None:
    """EIA-860M bytes from the connector's binary cache, else download."""
    candidate = Path(__file__).resolve().parent
    for _ in range(8):
        bin_path = candidate / "data" / "cache" / _EIA_CACHE_FILENAME
        if bin_path.exists():
            log.info("EIA-860M: cache hit %s", bin_path)
            return bin_path.read_bytes()
        candidate = candidate.parent

    log.info("EIA-860M: downloading %s …", EIA_860M_URL)
    try:
        req = urllib.request.Request(
            EIA_860M_URL,
            headers={"User-Agent": "BrownfieldOpportunities/0.2 (research; static dashboard)"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 — log + abort, nothing to salvage
        log.error("EIA-860M: download failed (%s)", exc)
        return None


def main() -> int:
    try:
        import openpyxl  # type: ignore
    except ImportError:
        log.error("openpyxl is required (pip install openpyxl)")
        return 1

    data = _get_eia_bytes()
    if data is None:
        return 1

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    ws = wb["Operating"]
    hdr: dict[str, int] | None = None
    plants: dict = defaultdict(lambda: {
        "mw": 0.0, "fuels": set(), "years": [], "name": None, "lat": None,
        "lon": None, "state": None, "county": None, "ba": None,
        "entity": None, "units": 0,
    })
    for row in ws.iter_rows(values_only=True):
        if hdr is None:
            if row and any(c == "Plant Name" for c in row):
                hdr = {c: i for i, c in enumerate(row) if c}
            continue

        def col(key):  # noqa: B023 — row rebinds per iteration by design
            i = hdr.get(key)
            return row[i] if i is not None and i < len(row) else None

        ret_year = str(col("Planned Retirement Year") or "").strip()
        if not ret_year.isdigit():
            continue
        fuel = str(col("Energy Source Code") or "").strip().upper()
        if fuel not in DISPATCHABLE_FUELS:
            continue
        try:
            mw = float(col("Nameplate Capacity (MW)") or 0)
        except (TypeError, ValueError):
            continue
        pl = plants[col("Plant ID")]
        pl["mw"] += mw
        pl["units"] += 1
        pl["fuels"].add(FUEL_LABEL.get(fuel, fuel.lower()))
        pl["years"].append(int(ret_year))
        pl["name"] = col("Plant Name")
        pl["lat"], pl["lon"] = col("Latitude"), col("Longitude")
        pl["state"], pl["county"] = col("Plant State"), col("County")
        pl["ba"] = col("Balancing Authority Code")
        pl["entity"] = col("Entity Name")

    sites = []
    for pid, pl in plants.items():
        if pl["mw"] < MIN_PLANT_MW or pl["lat"] is None or pl["lon"] is None:
            continue
        sites.append({
            "id": f"EIA-PLANNED-{pid}",
            "name": str(pl["name"]),
            "lat": float(pl["lat"]),
            "lon": float(pl["lon"]),
            "state": pl["state"],
            "county": pl["county"],
            "mw": round(pl["mw"], 1),
            "units_retiring": pl["units"],
            "fuel": "/".join(sorted(pl["fuels"])),
            "first_retirement_year": min(pl["years"]),
            "last_retirement_year": max(pl["years"]),
            "balancing_authority": pl["ba"],
            "operator": pl["entity"],
        })
    sites.sort(key=lambda s: (s["first_retirement_year"], -s["mw"]))
    total_mw = round(sum(s["mw"] for s in sites))
    log.info("kept %d plants ≥%.0f MW with announced retirements (%d MW total)",
             len(sites), MIN_PLANT_MW, total_mw)

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "EIA-860M Preliminary Monthly Electric Generator Inventory — "
                  "operating generators with announced retirement dates (April 2026)",
        "source_url": "https://www.eia.gov/electricity/data/eia860m/",
        "count": len(sites),
        "total_mw": total_mw,
        "sites": sites,
    }
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")))
    log.info("wrote %s (%d sites)", OUT_PATH, len(sites))
    return 0


if __name__ == "__main__":
    sys.exit(main())
