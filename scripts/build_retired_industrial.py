#!/usr/bin/env python3
"""Build docs/data/retired-industrial.json — a map overlay of large RETIRED
heavy-industrial facilities (smelters, mills, plants) as data-center siting
candidates.

Why this matters
----------------
A retired aluminum smelter, steel mill, or large chemical plant leaves behind
the single most valuable thing a hyperscale data center needs: a massive,
already-built grid interconnection. An aluminum smelter alone can be 300-700 MW
of continuous load. When it closes, that transmission capacity is stranded —
the Alcoa / Century / Google-Widows-Creek pattern. These sites are often NOT in
our Superfund / ACRES / FUDS / BRAC universe, so this overlay surfaces them.

Source — EPA GHGRP via the Envirofacts REST service (no API key)
----------------------------------------------------------------
`https://data.epa.gov/efservice/PUB_DIM_FACILITY/REPORTING_STATUS/<status>/ROWS/a:b/JSON`
returns one row per facility-reporting-year with `latitude`, `longitude`,
`facility_id`, `facility_name`, `naics_code`, `year`, `reporting_status`,
`parent_company`, `city`, `county`, `state`. ~8,000 large emitters report
annually since 2010.

The closure signal is EPA's OWN `reporting_status` field — values:
  - None                              → still actively reporting
  - STOPPED_REPORTING_VALID_REASON    → ceased reporting (closed / idled /
                                         dropped below threshold), reason given
  - STOPPED_REPORTING_UNKNOWN_REASON  → ceased reporting, no reason
We pull BOTH stopped-reporting statuses directly (one query each, paged), then
keep facilities whose NAICS is in manufacturing (sectors 31–33, which includes
petroleum refining 324). This is a "stopped GHGRP reporting" signal, NOT a hard
"demolished" claim — labeled honestly in the UI. Querying by status (vs. the
old per-NAICS enumeration) is comprehensive: ~558 manufacturing closures
nationwide across chemicals, primary metal, food, cement/glass, paper,
refineries, auto plants, etc. — not just the dozen sectors we used to list.

Output envelope mirrors the other docs/data/*.json files; it is an OVERLAY
(like reference-campuses.json), NOT a SiteRecord set, so it stays out of the
schema.py / refresh.py pipeline and is lazy-loaded by the frontend.

Re-run: `python3 scripts/build_retired_industrial.py` (refresh after each
annual GHGRP release, ~October).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("build_retired_industrial")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "retired-industrial.json"
EFSERVICE = "https://data.epa.gov/efservice/PUB_DIM_FACILITY/REPORTING_STATUS/{status}/ROWS/{a}:{b}/JSON"
PAGE = 1000
USER_AGENT = "brownfield-opportunities/retired-industrial (data.epa.gov GHGRP)"

STOPPED_STATUSES = ("STOPPED_REPORTING_VALID_REASON", "STOPPED_REPORTING_UNKNOWN_REASON")

# Manufacturing = NAICS sectors 31–33 (includes petroleum refining 324). We
# label by the 3-digit subsector, with finer 6-digit overrides for the
# marquee high-grid-load sectors (smelters, mills, refineries, auto plants).
NAICS3_LABEL = {
    "311": "Food-processing plant", "312": "Beverage / tobacco plant",
    "313": "Textile mill", "314": "Textile-product mill", "315": "Apparel plant",
    "316": "Leather plant", "321": "Wood-products mill", "322": "Pulp & paper mill",
    "323": "Printing plant", "324": "Petroleum & coal-products plant",
    "325": "Chemical plant", "326": "Plastics & rubber plant",
    "327": "Cement / glass / mineral plant", "331": "Primary-metal mill",
    "332": "Fabricated-metal plant", "333": "Machinery plant",
    "334": "Electronics plant", "335": "Electrical-equipment plant",
    "336": "Transportation-equipment plant", "337": "Furniture plant",
    "339": "Misc. manufacturing plant",
}
NAICS6_LABEL = {
    "331313": "Primary aluminum smelter", "331314": "Secondary aluminum smelter",
    "331110": "Iron & steel mill", "331410": "Primary nonferrous smelter",
    "331492": "Secondary nonferrous smelter", "331511": "Iron foundry",
    "324110": "Petroleum refinery", "327310": "Cement plant",
    "327211": "Flat-glass plant", "327213": "Glass-container plant",
    "322110": "Pulp mill", "322120": "Paper mill", "322130": "Paperboard mill",
    "336111": "Automobile assembly plant", "336112": "Light-truck assembly plant",
    "325110": "Petrochemical plant", "325311": "Nitrogen-fertilizer plant",
}

# Large-load MINING / ore-processing sites (NAICS 212) — big-footprint
# industrial sites that retain grid + sometimes adjacent generation. NOT oil &
# gas extraction (211 = scattered wellpads, not single large-load sites) and
# NOT power plants (2211, covered by eia-retired-plants).
NAICS_MINING_LABEL = {
    "212": "Mine / ore-processing site",
    "212111": "Coal mine / prep plant", "212112": "Coal mine / prep plant",
    "212113": "Anthracite mine", "212114": "Surface coal mine",
    "212210": "Iron-ore mine", "212220": "Gold / silver mine",
    "212230": "Copper / nickel / lead / zinc mine", "212290": "Metal-ore mine",
    "212311": "Crushed-stone quarry", "212312": "Limestone quarry",
    "212391": "Potash / soda / borate mine", "212393": "Chemical mineral mine",
}


def _sector(naics: str) -> str | None:
    n = str(naics or "")
    if n[:2] in ("31", "32", "33"):
        return NAICS6_LABEL.get(n) or NAICS3_LABEL.get(n[:3]) or "Manufacturing plant"
    if n[:3] == "212":  # mining / ore-processing (large-load, not oil & gas)
        return NAICS_MINING_LABEL.get(n) or NAICS_MINING_LABEL.get(n[:3])
    return None  # not a large-load manufacturing / mining site


def _category(naics: str) -> str:
    """Top-level grouping for the overlay legend / popup."""
    return "Mining" if str(naics or "")[:3] == "212" else "Manufacturing"


_ACRONYMS = {"LLC", "LP", "INC", "CO", "US", "USA", "II", "III", "IV", "NGLP"}


def _http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _fetch_status(status: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        page = _http_json(EFSERVICE.format(status=status, a=start, b=start + PAGE))
        rows.extend(page)
        if len(page) < PAGE:
            break
        start += PAGE
        time.sleep(0.3)
    return rows


def _pretty_name(raw: str) -> str:
    if not raw:
        return raw
    out = []
    for w in raw.split():
        core = w.strip(".,").upper()
        if core in _ACRONYMS:
            out.append(core)
        elif "-" in w:
            out.append("-".join(p.capitalize() for p in w.split("-")))
        else:
            out.append(w.capitalize())
    return " ".join(out)


def main() -> int:
    # Collect every facility-year row carrying a stopped-reporting status, then
    # dedupe to the most-recent year per facility.
    facs: dict[int, dict] = {}
    latest_year = 0
    for status in STOPPED_STATUSES:
        try:
            rows = _fetch_status(status)
        except Exception as e:  # noqa: BLE001 — log + continue
            log.warning("[%s] fetch failed (%s) — skipping", status, type(e).__name__)
            continue
        log.info("[%s] %d facility-year rows", status, len(rows))
        for r in rows:
            fid, yr = r.get("facility_id"), r.get("year")
            if fid is None or yr is None:
                continue
            latest_year = max(latest_year, yr)
            cur = facs.get(fid)
            if cur is None or yr > cur["year"]:
                facs[fid] = r

    by_id: dict[int, dict] = {}
    from collections import Counter
    sect_counts: Counter = Counter()
    for fid, r in facs.items():
        sector = _sector(r.get("naics_code"))
        if sector is None:  # not manufacturing (power, oil/gas, mining, waste…)
            continue
        lat, lon = r.get("latitude"), r.get("longitude")
        if lat is None or lon is None:
            continue
        status = str(r.get("reporting_status") or "")
        by_id[fid] = {
            "id": f"GHGRP-{fid}",
            "name": _pretty_name(r.get("facility_name") or ""),
            "lat": float(lat),
            "lon": float(lon),
            "state": r.get("state"),
            "city": _pretty_name(r.get("city") or "") or None,
            "county": _pretty_name(r.get("county") or "") or None,
            "sector": sector,
            "category": _category(r.get("naics_code")),
            "naics": str(r.get("naics_code") or ""),
            "last_report_year": r.get("year"),
            "reporting_status": "valid_reason"
                if status == "STOPPED_REPORTING_VALID_REASON" else "unknown_reason",
            "parent_company": _pretty_name(r.get("parent_company") or "") or None,
        }
        sect_counts[r.get("naics_code", "")[:3]] += 1
    log.info("kept %d manufacturing closures; by NAICS-3: %s",
             len(by_id), dict(sect_counts.most_common()))

    sites = sorted(by_id.values(), key=lambda s: (s.get("state") or "", s["name"]))
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "EPA Greenhouse Gas Reporting Program (GHGRP) — facilities that ceased reporting",
        "source_url": "https://www.epa.gov/ghgreporting",
        "ghgrp_latest_year": latest_year,
        "count": len(sites),
        "sites": sites,
    }
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")))
    log.info("wrote %s (%d sites, latest GHGRP year %d)", OUT_PATH, len(sites), latest_year)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
