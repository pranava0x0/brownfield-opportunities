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
`https://data.epa.gov/efservice/PUB_DIM_FACILITY/NAICS_CODE/<code>/ROWS/a:b/JSON`
returns one row per facility-reporting-year with `latitude`, `longitude`,
`facility_id`, `facility_name`, `naics_code`, `year`, `reporting_status`,
`parent_company`, `city`, `county`, `state`. ~8,000 large emitters report
annually since 2010.

The closure signal is EPA's OWN `reporting_status` field — values:
  - None                              → still actively reporting
  - STOPPED_REPORTING_VALID_REASON    → ceased reporting (closed / idled /
                                         dropped below threshold), reason given
  - STOPPED_REPORTING_UNKNOWN_REASON  → ceased reporting, no reason
We keep facilities whose LATEST-year row carries a STOPPED_REPORTING_* status —
far more reliable than inferring closure from a facility dropping out of the
data. This is a "stopped GHGRP reporting" signal, NOT a hard "demolished"
claim — labeled honestly in the UI.

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
EFSERVICE = "https://data.epa.gov/efservice/PUB_DIM_FACILITY/NAICS_CODE/{naics}/ROWS/{a}:{b}/JSON"
PAGE = 1000
USER_AGENT = "brownfield-opportunities/retired-industrial (data.epa.gov GHGRP)"

# DC-relevant heavy-industrial sectors — the ones whose closure strands a
# large grid interconnection and/or a big flat brownfield parcel. NAICS → label.
NAICS_SECTORS = {
    "331110": "Iron & steel mill",
    "331313": "Primary aluminum smelter",   # may 500 on the API — handled
    "331314": "Secondary aluminum smelter",
    "331410": "Nonferrous metal smelter",
    "331492": "Secondary nonferrous smelter",
    "327310": "Cement plant",
    "322110": "Pulp mill",
    "322120": "Paper mill",
    "322130": "Paperboard mill",
    "325110": "Petrochemical plant",
    "327211": "Flat glass plant",
}

_ACRONYMS = {"LLC", "LP", "INC", "CO", "US", "USA", "II", "III", "IV", "NGLP"}


def _http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _fetch_naics(naics: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        url = EFSERVICE.format(naics=naics, a=start, b=start + PAGE)
        page = _http_json(url)
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
    by_id: dict[int, dict] = {}
    latest_year = 0
    for naics, label in NAICS_SECTORS.items():
        try:
            rows = _fetch_naics(naics)
        except Exception as e:  # noqa: BLE001 — log + continue, one sector failing shouldn't abort
            log.warning("[%s %s] fetch failed (%s) — skipping sector", naics, label, type(e).__name__)
            continue
        # Group by facility, keep the most-recent reporting year per facility.
        facs: dict[int, dict] = {}
        for r in rows:
            fid = r.get("facility_id")
            yr = r.get("year")
            if fid is None or yr is None:
                continue
            latest_year = max(latest_year, yr)
            cur = facs.get(fid)
            if cur is None or yr > cur["year"]:
                facs[fid] = r
        kept = 0
        for fid, r in facs.items():
            status = str(r.get("reporting_status") or "")
            if not status.startswith("STOPPED_REPORTING"):
                continue
            lat, lon = r.get("latitude"), r.get("longitude")
            if lat is None or lon is None:
                continue
            by_id[fid] = {
                "id": f"GHGRP-{fid}",
                "name": _pretty_name(r.get("facility_name") or ""),
                "lat": float(lat),
                "lon": float(lon),
                "state": r.get("state"),
                "city": _pretty_name(r.get("city") or "") or None,
                "county": _pretty_name(r.get("county") or "") or None,
                "sector": label,
                "naics": naics,
                "last_report_year": r.get("year"),
                "reporting_status": "valid_reason"
                    if status == "STOPPED_REPORTING_VALID_REASON" else "unknown_reason",
                "parent_company": _pretty_name(r.get("parent_company") or "") or None,
            }
            kept += 1
        log.info("[%s %s] %d facilities, %d stopped-reporting with coords", naics, label, len(facs), kept)

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
