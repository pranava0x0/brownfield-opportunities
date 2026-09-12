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
this field is regional hydrologic context. It cannot rule a site out, rank
site water availability, or establish that water is available. Every
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
import datetime as dt
import hashlib
import math
import re
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
    "WV", "WI", "WY", "PR",  # Other territories are outside this catalog scope.
]

# Numeric US state identity comes from each returned row, never request scope.
STATE_FIPS = dict(zip(
    "01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56 72".split(),
    STATES))
_last_request = 0.0
_FLOW_METADATA: dict[str, dict] = {}
_FAILED_BATCHES: list[list[str]] = []
_CACHE_ONLY = False


def _retrieved_at(body: str) -> str | None:
    """USGS response timestamp; cache replay never makes this date newer."""
    match = re.search(r"^# retrieved:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*([+-]\d{2}:\d{2})", body, re.M)
    if not match:
        return None
    return dt.datetime.fromisoformat(match[1] + match[2]).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")



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
    if _CACHE_ONLY:
        log.warning("cache-only: missing %s", key)
        return None
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
    return [dict(row, _source_retrieved_at=_retrieved_at(body)) for row in _parse_rdb(body)]


def _fetch_flows(gage_ids: list[str], refresh: bool) -> dict[str, list[float]]:
    """Annual mean discharge per gage, batched at the service's 10-site cap."""
    by_year: dict[str, dict[str, list[float]]] = {}
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
            _FAILED_BATCHES.append(batch)
            continue
        snapshot = _retrieved_at(body)
        for row in _parse_rdb(body):
            site = row.get("site_no")
            raw = row.get("mean_va")
            year = row.get("year_nu")
            if not site or not raw or not year:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if not math.isfinite(value) or not year.isdigit():
                log.warning("invalid annual flow for %s: %s (%s)", site, raw, year)
                continue
            _FLOW_METADATA[site] = {"source_retrieved_at": snapshot}
            # Key by (site, WATER YEAR), not by row. NWIS publishes the same
            # site-year under multiple time-series ids — gage 06208500 returns
            # 170 rows across ts_ids 81537 and 247095 for just 85 distinct
            # years. Appending rows double-counted every duplicated year in
            # the mean and made `record_years` a row count, so that gage
            # claimed 170 years of record (Codex review). Twelve gages were
            # reporting over 130 years this way.
            by_year.setdefault(site, {}).setdefault(year, []).append(value)
    for site, years in by_year.items():
        _FLOW_METADATA[site].update(record_start_year=min(map(int, years)),
                                    record_end_year=max(map(int, years)))
    # One value per year: average the duplicate time-series for that year
    # rather than letting the year vote twice.
    return {site: [statistics.fmean(vals) for _year, vals in sorted(years.items())]
            for site, years in by_year.items()}


def _f(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except ValueError:
        return None


def _existing_rows() -> list[dict]:
    """Whatever is already in the catalog, or [] if there is none."""
    if not OUT_PATH.exists():
        return []
    try:
        return json.loads(OUT_PATH.read_text()).get("sites") or []
    except (OSError, json.JSONDecodeError) as e:
        log.warning("could not read existing %s (%s) — treating as empty",
                    OUT_PATH.name, e)
        return []


def build(states: list[str], refresh: bool) -> int:
    rows: list[dict] = []
    # UTC, to match the payload's own generated_at — a local stamp put rows a
    # day behind the file on any evening run west of Greenwich.
    _FLOW_METADATA.clear()
    _FAILED_BATCHES.clear()
    failed_states: list[str] = []
    complete_states: list[str] = []

    for state in states:
        sites = _fetch_sites(state, refresh)
        if not sites:
            log.warning("[%s] no gage inventory returned", state)
            failed_states.append(state)
            continue
        by_id = {}
        invalid_inventory = False
        for s in sites:
            sid = (s.get("site_no") or "").strip()
            lat = _f(s.get("dec_lat_va"))
            lon = _f(s.get("dec_long_va"))
            if not sid or lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                invalid_inventory = True
                log.warning("[%s] invalid inventory identity/coordinates for %s", state, sid)
                continue
            by_id[sid] = s
        failures_before = len(_FAILED_BATCHES)
        flows = _fetch_flows(sorted(by_id), refresh)
        state_complete = len(_FAILED_BATCHES) == failures_before and not invalid_inventory
        if state_complete:
            complete_states.append(state)
        else:
            failed_states.append(state)

        kept = 0
        for sid, s in by_id.items():
            annual = flows.get(sid) or []
            if not annual:
                continue
            mean_flow = statistics.fmean(annual)
            if mean_flow < MIN_MEAN_FLOW_CFS:
                continue
            metadata = _FLOW_METADATA.get(sid, {})
            snapshot = metadata.get("source_retrieved_at")
            geographic_state = (STATE_FIPS.get((s.get("state_cd") or "").zfill(2))
                                if s.get("country_cd", "US") == "US" else None)
            raw = {
                "gage_id": sid,
                "name": (s.get("station_nm") or "").strip(),
                "state": geographic_state,
                "requested_region": state,
                "state_identity_note": None if geographic_state else "No recognized US state code in source; request region is not geographic identity.",
                "lat": round(_f(s.get("dec_lat_va")), 5),
                "lon": round(_f(s.get("dec_long_va")), 5),
                "mean_flow_cfs": round(mean_flow, 1),
                "record_years": len(annual),
                "drainage_sqmi": _f(s.get("drain_area_va")),
                "source_url": f"https://waterdata.usgs.gov/monitoring-location/USGS-{sid}/",
                "verified_at": snapshot[:10] if snapshot else None,
                "source_inventory_retrieved_at": s.get("_source_retrieved_at"),
                **metadata,
            }
            if raw["drainage_sqmi"] is not None and raw["drainage_sqmi"] <= 0:
                raw["drainage_sqmi"] = None
            try:
                rows.append(Streamgage.model_validate(raw).model_dump(exclude_none=True))
            except Exception as e:  # noqa: BLE001 — report and continue
                if state in complete_states:
                    complete_states.remove(state)
                if state not in failed_states:
                    failed_states.append(state)
                log.warning("[%s] gage %s failed validation: %s", state, sid, e)
                continue
            kept += 1
        log.info("[%s] %d gages inventoried, %d with usable mean flow",
                 state, len(by_id), kept)

    # NEVER let a partial run truncate the catalog. A scoped build
    # (`--states MI,ME`, which this module's own docstring recommends) or a
    # transient NWIS failure would otherwise replace the national artifact
    # with whatever subset happened to succeed — and the downstream water join
    # turns those missing gages into negative tombstones and lower scores,
    # silently (Codex review, this PR). Merge over what is already on disk,
    # keyed by gage_id, with freshly fetched rows winning.
    # Replace only a fully fetched requested region. Incomplete regions retain
    # prior rows, while successful scopes retire no-longer-qualifying gages.
    merged: dict[str, dict] = {
        r["gage_id"]: r for r in _existing_rows()
        if (r.get("requested_region") or r.get("state")) not in complete_states
    }
    before = len(merged)
    merged.update({r["gage_id"]: r for r in rows})
    if before:
        log.info("merged %d fetched rows into %d existing = %d total",
                 len(rows), before, len(merged))
    rows = list(merged.values())

    rows.sort(key=lambda r: (r.get("state") or "", r["gage_id"]))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "USGS NWIS (site inventory + annual mean discharge)",
        "source_url": SOURCE_URL,
        "note": (
            "mean_flow_cfs is the mean of annual mean discharges over the "
            "period of record — a long-run average, NOT a permittable low-flow "
            "(7Q10) statistic. Screens candidates; never clears one."
        ),
        "coverage": {
            "requested_regions": states, "complete_regions": complete_states,
            "incomplete_regions": failed_states,
            "failed_stat_batches": len(_FAILED_BATCHES),
            "catalog_regions": STATES,
            "selection": "Active discharge streamgages with mean annual flow >= 5 cfs; not all water sources.",
            "supply_assessment": "unassessed",
            "api_migration": "WaterServices retirement scheduled Q1 2027; modern API migration required.",
        },
        "count": len(rows),
        "sites": rows,
    }
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s (%d gages, %.1f KB)",
             OUT_PATH, len(rows), OUT_PATH.stat().st_size / 1024)
    if failed_states:
        log.error("inventory failed for %d state(s): %s — their prior rows "
                  "were preserved, but re-run before treating the catalog as "
                  "current", len(failed_states), ",".join(failed_states))
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--states", default=None,
                    help="Comma-separated state codes (default: all).")
    ap.add_argument("--refresh", action="store_true",
                    help="Ignore the on-disk cache and refetch.")
    ap.add_argument("--cache-only", action="store_true", help="Rebuild retained snapshots without network calls.")
    args = ap.parse_args()
    global _CACHE_ONLY
    _CACHE_ONLY = args.cache_only
    states = [s.strip().upper() for s in args.states.split(",")] if args.states else STATES
    return build(states, args.refresh)


if __name__ == "__main__":
    raise SystemExit(main())
