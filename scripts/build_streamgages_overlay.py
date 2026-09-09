#!/usr/bin/env python3
"""Build docs/data/streamgages.json — active USGS gages with mean annual flow.

Why this exists
---------------
Every infrastructure layer this dashboard collects (transmission, substation,
rail, highway, gas pipeline, power plants, ports) is about moving electrons,
freight, or fuel. None of them is about WATER, and water is the binding
constraint for the metallurgical and thermal facility types the siting tabs
screen for. The only water fields on SiteRecord before this pass were
`near_water_supply` / `near_water_body` — qualitative EPA RE-Powering strings
("Yes - 1 mile") covering ~1,905 Superfund sites out of 46,759.

This overlay is the quantitative replacement: a national point catalog of
ACTIVE USGS streamflow gages, each carrying the mean of its annual mean
discharges over the full period of record.

What the number is, and what it is NOT
--------------------------------------
`mean_flow_cfs` is a long-run AVERAGE. An industrial withdrawal permit is
written against a LOW-flow statistic (7Q10 / drought-of-record), which is
routinely an order of magnitude below the annual mean on a flashy river. So
this field is a screen, never a clearance: it can rule a site out, and it can
rank two candidates, but it cannot establish that water is available. Every
surface that renders it must say so. Same discipline as the AP1000 tab, which
carries analyst-researched water adequacy precisely because no national layer
answered the question (see ap1000-water-validation.md).

Source (live-fetched, no API key)
---------------------------------
USGS NWIS RDB web services — data-source-research.md §16 established these as
the scriptable contract (the waterdata.usgs.gov monitoring-location pages are
JavaScript-rendered and useless to a fetcher):

  1. Site inventory, per state:
     waterservices.usgs.gov/nwis/site/?format=rdb&stateCd=<ST>
       &parameterCd=00060&hasDataTypeCd=dv&siteType=ST&siteStatus=active
       &siteOutput=expanded
     -> dec_lat_va / dec_long_va / station_nm / drain_area_va

  2. Annual mean discharge, per gage:
     waterservices.usgs.gov/nwis/stat/?format=rdb&sites=<up to 10>
       &statReportType=annual&statTypeCd=mean&parameterCd=00060
     -> one row per site per water year; we average them.

The stat service caps `sites` at TEN per request (probed 2026-09-08: 40 sites
returns HTTP 400 "the number of siteNo elements input by the user exceeds the
maximum limit for this web service [max=[10]]"), and it does NOT accept
stateCd. That 10-site ceiling is why this is a batched, cached, resumable
script rather than a one-shot fetch.

Resumability
------------
Every stat batch is cached to .cache/streamgages/<hash>.rdb. A re-run costs
nothing for batches already on disk, so an interrupted run resumes for free —
the same durable-progress property the flood backfill relies on.

Re-run: `python3 scripts/build_streamgages_overlay.py`
        `--states MI,ME` to scope, `--refresh` to ignore the cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema import Streamgage  # noqa: E402

log = logging.getLogger("build_streamgages")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_PATH = ROOT / "docs" / "data" / "streamgages.json"
CACHE_DIR = ROOT / "data" / "cache" / "streamgages"
SITE_URL = "https://waterservices.usgs.gov/nwis/site/"
STAT_URL = "https://waterservices.usgs.gov/nwis/stat/"
SOURCE_URL = "https://waterservices.usgs.gov/"
USER_AGENT = "brownfield-opportunities/streamgage-overlay (waterservices.usgs.gov)"

# The stat service's own documented ceiling. Raising it returns HTTP 400.
STAT_BATCH = 10
RATE_LIMIT_S = 1.5

# A gage below this is a creek, not an industrial water source. The smallest
# facility type screened here (a hydromet refinery at ~1-3 MGD process +
# cooling makeup) is ~2-5 cfs of consumption, and a withdrawal is not
# permittable at anywhere near 100% of mean flow, so a sub-5 cfs gage carries
# no siting signal and only bloats the index. Kept deliberately low so the
# FILTERING happens in the scoring curve, not here.
MIN_MEAN_FLOW_CFS = 5.0

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "PR", "VI",
]

_last_request = 0.0


def _get(url: str) -> str:
    """Throttled GET returning text. Raises on non-2xx."""
    global _last_request
    wait = RATE_LIMIT_S - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    finally:
        _last_request = time.monotonic()
    return body


def _cached(key: str, url: str, refresh: bool) -> str | None:
    """Fetch `url`, memoizing to disk under `key`. None on a hard failure.

    A failure is NOT cached: NWIS returns transient 500s under load, and
    caching one would poison the resume path (the nepa-mcp lesson — cached
    errors are served straight back and a code fix alone cannot heal them).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{hashlib.sha1(key.encode()).hexdigest()}.rdb"
    if path.exists() and not refresh:
        return path.read_text()
    try:
        body = _get(url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        log.warning("fetch failed (%s): %s", key, e)
        return None
    if body.lstrip().startswith("<"):
        log.warning("non-RDB response for %s (HTML error page)", key)
        return None
    path.write_text(body)
    return body


def _parse_rdb(text: str) -> list[dict[str, str]]:
    """Parse USGS RDB: '#' comments, a header row, a type row, then data."""
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if header is None:
            header = parts
            continue
        # The type row ("5s", "15s", "12n", ...) immediately follows the header.
        if all(p and p[-1] in "sndf" and p[:-1].isdigit() for p in parts if p):
            continue
        rows.append(dict(zip(header, parts)))
    return rows


def _fetch_sites(state: str, refresh: bool) -> list[dict[str, str]]:
    params = {
        "format": "rdb", "stateCd": state.lower(), "parameterCd": "00060",
        "hasDataTypeCd": "dv", "siteType": "ST", "siteStatus": "active",
        "siteOutput": "expanded",
    }
    url = SITE_URL + "?" + urllib.parse.urlencode(params)
    body = _cached(f"sites:{state}", url, refresh)
    if body is None:
        return []
    return _parse_rdb(body)


def _fetch_flows(gage_ids: list[str], refresh: bool) -> dict[str, list[float]]:
    """Annual mean discharge per gage, batched at the service's 10-site cap."""
    out: dict[str, list[float]] = {}
    for i in range(0, len(gage_ids), STAT_BATCH):
        batch = gage_ids[i:i + STAT_BATCH]
        params = {
            "format": "rdb", "sites": ",".join(batch),
            "statReportType": "annual", "statTypeCd": "mean",
            "parameterCd": "00060",
        }
        url = STAT_URL + "?" + urllib.parse.urlencode(params)
        body = _cached("stat:" + ",".join(batch), url, refresh)
        if body is None:
            continue
        for row in _parse_rdb(body):
            site = row.get("site_no")
            raw = row.get("mean_va")
            if not site or not raw:
                continue
            try:
                out.setdefault(site, []).append(float(raw))
            except ValueError:
                continue
    return out


def _f(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def build(states: list[str], refresh: bool) -> None:
    rows: list[dict] = []
    verified_at = time.strftime("%Y-%m-%d")

    for state in states:
        sites = _fetch_sites(state, refresh)
        if not sites:
            log.warning("[%s] no gage inventory returned", state)
            continue
        by_id = {}
        for s in sites:
            sid = (s.get("site_no") or "").strip()
            lat = _f(s.get("dec_lat_va"))
            lon = _f(s.get("dec_long_va"))
            if not sid or lat is None or lon is None:
                continue
            by_id[sid] = s
        flows = _fetch_flows(sorted(by_id), refresh)

        kept = 0
        for sid, s in by_id.items():
            annual = flows.get(sid) or []
            if not annual:
                continue
            mean_flow = statistics.fmean(annual)
            if mean_flow < MIN_MEAN_FLOW_CFS:
                continue
            raw = {
                "gage_id": sid,
                "name": (s.get("station_nm") or "").strip(),
                "state": state,
                "lat": round(_f(s.get("dec_lat_va")), 5),
                "lon": round(_f(s.get("dec_long_va")), 5),
                "mean_flow_cfs": round(mean_flow, 1),
                "record_years": len(annual),
                "drainage_sqmi": _f(s.get("drain_area_va")),
                "source_url": SOURCE_URL,
                "verified_at": verified_at,
            }
            if raw["drainage_sqmi"] is not None and raw["drainage_sqmi"] <= 0:
                raw["drainage_sqmi"] = None
            try:
                rows.append(Streamgage.model_validate(raw).model_dump())
            except Exception as e:  # noqa: BLE001 — report and continue
                log.warning("[%s] gage %s failed validation: %s", state, sid, e)
                continue
            kept += 1
        log.info("[%s] %d gages inventoried, %d with usable mean flow",
                 state, len(by_id), kept)

    rows.sort(key=lambda r: (r["state"] or "", r["gage_id"]))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "USGS NWIS (site inventory + annual mean discharge)",
        "source_url": SOURCE_URL,
        "note": (
            "mean_flow_cfs is the mean of annual mean discharges over the "
            "period of record — a long-run average, NOT a permittable low-flow "
            "(7Q10) statistic. Screens candidates; never clears one."
        ),
        "count": len(rows),
        "sites": rows,
    }
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s (%d gages, %.1f KB)",
             OUT_PATH, len(rows), OUT_PATH.stat().st_size / 1024)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--states", default=None,
                    help="Comma-separated state codes (default: all).")
    ap.add_argument("--refresh", action="store_true",
                    help="Ignore the on-disk cache and refetch.")
    args = ap.parse_args()
    states = [s.strip().upper() for s in args.states.split(",")] if args.states else STATES
    build(states, args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
