"""Compare our shipped data files against their upstream sources' edit dates.

The efficient-refresh primitive (spec 13d): before spending a multi-hour
connector run, ask each upstream service WHEN it last changed. ArcGIS
Feature/Map services expose `editingInfo.lastEditDate` (epoch ms) via
`<layer>?f=json`; EIA-860M publishes a predictable monthly XLSX path we can
probe with cheap HEAD/GET requests. Output is one row per source:

    SOURCE | ours (generated_at) | upstream last edit | verdict

Verdicts: STALE (upstream newer than our file), current (we're newer or
equal), UNKNOWN (service doesn't expose a date, or network failed —
UNKNOWN is never treated as current). Exit code: 1 if any STALE, else 0 —
so a cron can gate "run the real refresh" on this ~30-second check
instead of re-pulling everything on a timer.

Network ethics: one metadata request per layer, ≥1.5 s between requests
to the same host, informative UA, IPv4 pinned (the AAAA-blackhole fix).
Offline-tolerant: failures report UNKNOWN, never crash the sweep.

Run::

    python3 scripts/check_upstream_freshness.py            # human table
    python3 scripts/check_upstream_freshness.py --json     # machine output
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
SCRIPTS_DIR = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402  (project floor dependency)

from connectors.base import prefer_ipv4  # noqa: E402

USER_AGENT = "BrownfieldOpportunities/0.2 (upstream freshness check; research)"
HOST_DELAY_S = 1.5
TIMEOUT_S = 25

# One row per refreshable source: our shipped file + the upstream layer
# whose editingInfo answers "did it change since we pulled?". Layers with
# no exposed edit date (TIGERweb MapServers, Overpass, FEMA NFHL) are
# listed with kind="none" so the report says UNKNOWN out loud instead of
# silently skipping them — absence of a freshness signal is a finding.
SOURCES: "list[dict[str, Any]]" = [
    {"name": "superfund-npl", "file": "superfund-npl.json",
     "kind": "arcgis", "url": "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0"},
    {"name": "epa-acres", "file": "epa-acres.json",
     "kind": "arcgis", "url": "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/All%20ACRES%20Properties%208_30_2021/FeatureServer/0"},
    {"name": "dod-fuds (layer 1)", "file": "dod-fuds.json",
     "kind": "arcgis", "url": "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/fuds/FeatureServer/1"},
    {"name": "dod-brac", "file": "dod-brac.json",
     "kind": "arcgis", "url": "https://services.arcgis.com/hRUr1F8lE8Jq2uJo/arcgis/rest/services/milbases/FeatureServer/0"},
    {"name": "epa-redev", "file": "epa-redev.json",
     "kind": "arcgis", "url": "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/RedevelopmentAppSitePoints/FeatureServer/0"},
    {"name": "transmission (HIFLD)", "file": "infra-proximity.json",
     "kind": "arcgis", "url": "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0"},
    {"name": "gas pipelines (HIFLD)", "file": "infra-proximity.json",
     "kind": "arcgis", "url": "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer/0"},
    {"name": "power plants (HIFLD)", "file": "infra-proximity.json",
     "kind": "arcgis", "url": "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Power_Plants_in_the_US/FeatureServer/0"},
    {"name": "highways (TIGER S1100)", "file": "infra-proximity.json",
     "kind": "none", "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/2",
     "note": "TIGERweb exposes no editingInfo; vintage tracks the annual TIGER release"},
    {"name": "railroads (TIGER)", "file": "infra-proximity.json",
     "kind": "none", "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/9",
     "note": "TIGERweb exposes no editingInfo; vintage tracks the annual TIGER release"},
    {"name": "substations (OSM Overpass)", "file": "infra-proximity.json",
     "kind": "none", "url": "https://overpass-api.de/api/interpreter",
     "note": "OSM is continuously edited; no single layer date — re-pull cadence is a judgment call"},
    {"name": "flood zones (FEMA NFHL)", "file": "infra-proximity.json",
     "kind": "none", "url": "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28",
     "note": "per-site query layer; NFHL updates county-by-county continuously"},
    {"name": "opportunity zones (HUD)", "file": "opportunity-zone.json",
     "kind": "arcgis", "url": "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/Opportunity_Zones/FeatureServer/13"},
    {"name": "IRA coal closure (NETL)", "file": "ira-energy-community.json",
     "kind": "arcgis", "url": "https://arcgis.netl.doe.gov/server/rest/services/Hosted/2024_Coal_Closure_Energy_Communities/FeatureServer/0"},
    {"name": "IRA MSA/non-MSA (NETL)", "file": "ira-energy-community.json",
     "kind": "arcgis", "url": "https://arcgis.netl.doe.gov/server/rest/services/Hosted/2024_MSAs_NonMSAs_that_are_Energy_Communities/FeatureServer/0"},
    {"name": "FEMA NRI counties", "file": "fema-nri.json",
     "kind": "arcgis", "url": "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0"},
    {"name": "EIA-860M workbook", "file": "eia-retired-plants.json",
     "kind": "eia860m", "url": "https://www.eia.gov/electricity/data/eia860m/archive/xls/{month}_generator{year}.xlsx"},
]

_last_hit: "dict[str, float]" = {}


def _throttle(url: str) -> None:
    host = urlparse(url).netloc
    wait = _last_hit.get(host, 0) + HOST_DELAY_S - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def _get(url: str, **kwargs: Any) -> requests.Response:
    _throttle(url)
    return requests.get(url, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, **kwargs)


def our_date(fname: str) -> Optional[dt.date]:
    path = DATA_DIR / fname
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return None
    stamp = payload.get("generated_at") if isinstance(payload, dict) else None
    if not stamp:
        return None
    try:
        return dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def our_eia_workbook_month() -> Optional[dt.date]:
    """The month of the EIA-860M workbook the connector actually PARSES —
    from EIA_860M_URL in the connector source, never our generated_at (a
    June re-run of the April workbook is still April data; comparing
    generated_at hid exactly that on this script's first live run)."""
    import re
    src = (ROOT / "connectors" / "eia_retired_plants.py").read_text()
    m = re.search(r"(\w+)_generator(\d{4})\.xlsx", src)
    if not m or m.group(1).lower() not in _EIA_MONTHS:
        return None
    return dt.date(int(m.group(2)), _EIA_MONTHS.index(m.group(1).lower()) + 1, 1)


def arcgis_last_edit(url: str) -> Optional[dt.date]:
    resp = _get(url, params={"f": "json"})
    resp.raise_for_status()
    meta = resp.json()
    if "error" in meta:  # ArcGIS reports errors with HTTP 200 (house rule)
        raise RuntimeError(str(meta["error"])[:120])
    info = meta.get("editingInfo") or {}
    stamp = info.get("dataLastEditDate") or info.get("lastEditDate")
    if not stamp:
        return None
    return dt.datetime.fromtimestamp(stamp / 1000, tz=dt.timezone.utc).date()


_EIA_MONTHS = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]


def eia860m_latest(url_template: str, today: dt.date) -> Optional[dt.date]:
    """Probe backward from the current month for the newest published
    workbook (EIA publishes ~2 months in arrears; the URL pattern is
    stable). Returns the first month whose XLSX exists."""
    probe = dt.date(today.year, today.month, 1)
    for _ in range(8):
        url = url_template.format(month=_EIA_MONTHS[probe.month - 1], year=probe.year)
        try:
            resp = _get(url, stream=True)
            ok = resp.status_code == 200 and "html" not in (resp.headers.get("Content-Type") or "")
            resp.close()
        except requests.RequestException:
            ok = False
        if ok:
            return probe
        probe = (probe.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    return None


def check_source(src: "dict[str, Any]", today: dt.date) -> "dict[str, Any]":
    ours = our_date(src["file"])
    upstream: Optional[dt.date] = None
    error: Optional[str] = None
    if src["kind"] == "arcgis":
        try:
            upstream = arcgis_last_edit(src["url"])
        except Exception as exc:
            error = str(exc)[:100]
    elif src["kind"] == "eia860m":
        ours = our_eia_workbook_month() or ours
        try:
            upstream = eia860m_latest(src["url"], today)
        except Exception as exc:
            error = str(exc)[:100]
    if upstream is None:
        verdict = "UNKNOWN"
    elif ours is None:
        verdict = "STALE"  # we have nothing (or no stamp); upstream exists
    elif upstream > ours:
        verdict = "STALE"
    else:
        verdict = "current"
    return {
        "name": src["name"], "file": src["file"],
        "ours": ours.isoformat() if ours else None,
        "upstream": upstream.isoformat() if upstream else None,
        "verdict": verdict,
        "note": src.get("note") or error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    prefer_ipv4()
    today = dt.date.today()
    rows = [check_source(src, today) for src in SOURCES]
    if args.json:
        print(json.dumps(rows, indent=1))
    else:
        w = max(len(r["name"]) for r in rows) + 2
        print(f"{'SOURCE':<{w}} {'OURS':<12} {'UPSTREAM':<12} VERDICT  NOTE")
        for r in rows:
            print(f"{r['name']:<{w}} {str(r['ours'] or '—'):<12} {str(r['upstream'] or '—'):<12} "
                  f"{r['verdict']:<8} {r['note'] or ''}")
        stale = sum(1 for r in rows if r["verdict"] == "STALE")
        unknown = sum(1 for r in rows if r["verdict"] == "UNKNOWN")
        print(f"\n{stale} STALE · {sum(1 for r in rows if r['verdict']=='current')} current · {unknown} unknown "
              f"(UNKNOWN is never treated as current)")
    return 1 if any(r["verdict"] == "STALE" for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
