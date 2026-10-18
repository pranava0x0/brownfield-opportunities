#!/usr/bin/env python3
"""Every US coal plant with at least 100 MW of coal retired or scheduled to
retire, from EIA-860M. Replaces hand-picking: the Coal tab ranks all of them.

Per EIA plant ID:
  coal_mw            nameplate of coal units retired or with a planned retirement
  status             "retired" (no coal unit still operating) or "retiring"
  retire_year        last coal unit's retirement (actual or planned)
  other_operating_mw nameplate of non-coal units still operating at the plant
                     (a gas conversion or new unit occupying the interconnection)
  line_kv, line_mi   nearest mapped transmission line (HIFLD, cached index)

Curated deal notes from docs/data/coal-conversions.json are attached by plant
name and state where they match, so the tab can show what is already happening.

Inputs are the cached EIA-860M workbook (connectors/eia860m_source.py pin) and
the cached HIFLD transmission pages; run `refresh.py --source eia-retired-plants`
and `--source infra-proximity` first if the caches are cold.

  python3 scripts/build_coal_plants.py      # writes docs/data/coal-plants.json
"""
from __future__ import annotations

import datetime as dt
import io
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connectors.eia860m_source import EIA_CACHE_FILENAME, EIA_860M_URL, EIA_WORKBOOK_MONTH  # noqa: E402
from connectors.infra_proximity import LAYERS, InfraProximity  # noqa: E402

OUT = ROOT / "docs" / "data" / "coal-plants.json"
CURATED = ROOT / "docs" / "data" / "coal-conversions.json"
CACHE = ROOT / "data" / "cache"
COAL_CODES = {"BIT", "SUB", "LIG", "ANT", "RC", "WC", "SGC", "SC"}
MIN_COAL_MW = 100
log = logging.getLogger("coal-plants")


def read_sheet(wb, name: str):
    """Yield one dict per generator row (header row located by 'Plant Name')."""
    header = None
    for row in wb[name].iter_rows(values_only=True):
        if header is None:
            if row and "Plant Name" in row:
                header = [c for c in row]
            continue
        if row and row[header.index("Plant ID")] is not None:
            yield dict(zip(header, row))


def mw(row) -> float:
    try:
        return float(row.get("Nameplate Capacity (MW)") or 0)
    except (TypeError, ValueError):
        return 0.0


def norm(name: str) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"\(.*?\)|power plant|generating station|steam station|station|plant|fossil|steam|energy|center", "", name.lower()))


def main() -> int:
    import openpyxl
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    wb = openpyxl.load_workbook(io.BytesIO((CACHE / EIA_CACHE_FILENAME).read_bytes()), read_only=True)
    plants = defaultdict(lambda: {"coal_retired_mw": 0.0, "coal_planned_mw": 0.0, "coal_operating_mw": 0.0,
                                  "other_operating_mw": 0.0, "years": [], "info": None})
    for row in read_sheet(wb, "Retired"):
        if str(row["Energy Source Code"]).upper() in COAL_CODES:
            p = plants[row["Plant ID"]]
            p["coal_retired_mw"] += mw(row)
            if str(row.get("Retirement Year") or "").isdigit():
                p["years"].append(int(row["Retirement Year"]))
            p["info"] = p["info"] or row
    for row in read_sheet(wb, "Operating"):
        p = plants[row["Plant ID"]]
        if str(row["Energy Source Code"]).upper() in COAL_CODES:
            p["coal_operating_mw"] += mw(row)
            planned = str(row.get("Planned Retirement Year") or "").strip()
            if planned.isdigit():
                p["coal_planned_mw"] += mw(row)
                p["years"].append(int(planned))
            p["info"] = row
        else:
            p["other_operating_mw"] += mw(row)
            p["info"] = p["info"] or row

    infra = InfraProximity(cache_dir=CACHE)
    lines = infra._build_index("transmission", LAYERS["transmission"], use_cache=True)
    curated = {(norm(c["plant_name"]), c["state"]): c for c in json.loads(CURATED.read_text())["assets"]}

    out = []
    for pid, p in plants.items():
        coal_mw = p["coal_retired_mw"] + p["coal_planned_mw"]
        info = p["info"]
        if coal_mw < MIN_COAL_MW or info is None or info.get("Latitude") in (None, ""):
            continue
        # A plant with coal still running and no retirement date is not in scope.
        if p["coal_operating_mw"] > p["coal_planned_mw"] + 0.1:
            continue
        lat, lon = float(info["Latitude"]), float(info["Longitude"])
        hit = lines.nearest_with_attr(lat, lon, 40)
        rec = {
            "id": f"EIA-{pid}", "eia_plant_id": int(pid), "name": str(info["Plant Name"]),
            "state": info["Plant State"], "county": info["County"], "operator": info["Entity Name"],
            "balancing_authority": info.get("Balancing Authority Code"),
            "lat": lat, "lon": lon,
            "coal_mw": round(coal_mw, 1),
            "status": "retired" if p["coal_operating_mw"] == 0 else "retiring",
            "retire_year": max(p["years"]) if p["years"] else None,
            "other_operating_mw": round(p["other_operating_mw"], 1),
        }
        if hit:
            rec["line_mi"] = round(hit[0], 1)
            if isinstance(hit[1], dict) and hit[1].get("kv"):
                rec["line_kv"] = hit[1]["kv"]
        deal = curated.get((norm(rec["name"]), rec["state"])) or next(
            (c for c in curated.values() if c["state"] == rec["state"]
             and abs(c["latitude"] - lat) < 0.04 and abs(c["longitude"] - lon) < 0.05), None)  # ~3 mi
        if deal:
            rec["deal_note"], rec["deal_source_url"] = deal.get("note"), deal.get("source_url")
        out.append(rec)
    out.sort(key=lambda r: -r["coal_mw"])
    OUT.write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": f"EIA-860M Preliminary Monthly Electric Generator Inventory ({EIA_WORKBOOK_MONTH}); HIFLD transmission lines",
        "source_url": EIA_860M_URL,
        "rule": f"coal units >= {MIN_COAL_MW} MW retired or with a planned retirement year; no unscheduled coal still running",
        "count": len(out),
        "plants": out,
    }, separators=(",", ":")) + "\n")
    log.info("wrote %d plants (%d retired, %d retiring, %d with curated deal notes)", len(out),
             sum(r["status"] == "retired" for r in out), sum(r["status"] == "retiring" for r in out),
             sum("deal_note" in r for r in out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
