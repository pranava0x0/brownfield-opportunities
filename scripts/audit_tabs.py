#!/usr/bin/env python3
"""Deterministic audit of the technology-specific siting tabs.

No model is involved. Every check re-derives a value a tab shows from an
independent source and reports OK / MISMATCH / ERROR / INCONCLUSIVE:

  coverage   per screen criterion: how many sites pass, fail or are unknown
  citations  every screen source URL and curated overlay URL still resolves
  lines      transmission / rail / road / gas distances (and the voltage-
             qualified transmission distances the screens use) re-measured
             from the source layer for the sites the tabs list
  seismic    ASCE 7 peak ground acceleration for each Nuclear installation
  flow       USGS annual mean flow at each Nuclear supply gauge
  poprings   nearest city of 25,000 or more, recomputed from the Census file
  state      each tab site's coordinate sits inside its stated state

Output: data/validation/audit-report.json plus a one-line-per-check summary.
INCONCLUSIVE means the host throttled or blocked us (HTTP 403/429), never
that the link is dead.

Usage:
  python3 scripts/audit_tabs.py                     # everything, top 10 per screen
  python3 scripts/audit_tabs.py --only coverage state
  python3 scripts/audit_tabs.py --only lines --limit 12
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import validate_against_sources as vas  # noqa: E402
from connectors.spatial import PolygonIndex, haversine_mi  # noqa: E402

DATA = ROOT / "docs" / "data"
MANIFEST = ROOT / "data" / "validation" / "tab-sites.json"
REPORT = ROOT / "data" / "validation" / "audit-report.json"
CHECKS = ("coverage", "citations", "lines", "seismic", "flow", "poprings", "state")
DELTA_MI = 0.35          # same tolerance as validate_against_sources: 0.1 mi rounding both sides + projection drift
PGA_TOLERANCE_G = 0.02
FLOW_TOLERANCE = 0.15    # the stored flow is an annual mean; a refreshed mean moves a few percent
log = logging.getLogger("audit_tabs")

HIFLD = vas.INFRA_LAYERS["transmission_mi"]["url"]
VOLT_THRESHOLDS = (69, 115, 230)


def row(check: str, id_: str, field: str, status: str, detail: str) -> dict:
    return {"check": check, "id": id_, "field": field, "status": status, "detail": detail}


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def node(*args: str) -> Any:
    proc = subprocess.run(["node", str(ROOT / "scripts" / "screen.js"), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"screen.js {' '.join(args)}: {proc.stderr[:300]}")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------- coverage

def check_coverage() -> list[dict]:
    out = []
    for screen, v in node("coverage").items():
        for cid, c in v["criteria"].items():
            pct = 100 * c["unknown"] / max(v["scope"], 1)
            # A criterion the tab cannot evaluate for most sites is a finding even
            # though nothing is "wrong": the ranking leans on what it does know.
            status = "WARN" if pct >= 50 else "OK"
            out.append(row("coverage", screen, cid, status,
                           f"{c['pass']} pass / {c['fail']} fail / {c['unknown']} unknown of {v['scope']} "
                           f"({pct:.0f}% unknown) · rule: {c['rule']} [{c['kind']}]"))
    return out


# --------------------------------------------------------------- citations

def _classify(url: str) -> tuple[str, str]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BrownfieldOpportunities link audit)"}
    try:
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True, stream=True)
        resp.close()
    except requests.RequestException as exc:
        return "ERROR", f"{type(exc).__name__}"           # no answer at all: counts toward the run's error gate
    if resp.status_code < 400:
        return "OK", f"HTTP {resp.status_code}"
    if resp.status_code in (401, 403, 405, 429, 503):
        return "INCONCLUSIVE", f"HTTP {resp.status_code} (blocked or throttled)"
    return "MISMATCH", f"HTTP {resp.status_code}"


def _overlay_urls() -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for s in load("ap1000-sites.json")["sites"]:
        for k in ("acreage_source", "water_source_url", "af_rflp_source_url", "af_rflp_article_url",
                  "af_rflp_status_url", "workforce_source_url", "water_rights_source_url", "iso_rto_source_url"):
            if str(s.get(k) or "").startswith("http"):
                urls.append((f"ap1000:{s['id']}:{k}", s[k]))
    for n in load("nuclear-civilian-sites.json")["sites"]:
        for k, v in n.items():
            if k.endswith("_url") and str(v or "").startswith("http"):
                urls.append((f"civilian:{n['id']}:{k}", v))
    return urls


def check_citations(limit: Optional[int]) -> list[dict]:
    items = [(f"{s['screen']}:{s['criterion']}", s["url"]) for s in node("sources")] + _overlay_urls()
    seen: dict[str, str] = {}
    out = []
    for label, url in items:
        if url not in seen:
            seen[url] = label
    pairs = list(seen.items())[:limit] if limit else list(seen.items())
    for url, label in pairs:
        status, detail = _classify(url)
        out.append(row("citations", label, url, status, detail))
    return out


# ------------------------------------------------------------------- lines

def _segments_min(lat: float, lon: float, feats: list[dict], keep=None) -> Optional[float]:
    sx = 111320.0 * math.cos(math.radians(lat)) / 1609.344
    sy = 110540.0 / 1609.344
    best = None
    for f in feats:
        if keep is not None and not keep(f.get("attributes") or {}):
            continue
        for path in (f.get("geometry") or {}).get("paths") or []:
            for a, b in zip(path, path[1:]):
                ax, ay = (a[0] - lon) * sx, (a[1] - lat) * sy
                bx, by = (b[0] - lon) * sx, (b[1] - lat) * sy
                dx, dy = bx - ax, by - ay
                den = dx * dx + dy * dy
                t = max(0.0, min(1.0, -(ax * dx + ay * dy) / den)) if den else 0.0
                d = math.hypot(ax + t * dx, ay + t * dy)
                best = d if best is None else min(best, d)
    return best


def _bbox_features(url: str, lat: float, lon: float, radius_mi: float, where: str = "1=1", out_fields: str = "") -> list[dict]:
    dlat = radius_mi / 69.0
    dlon = radius_mi / (69.0 * max(math.cos(math.radians(lat)), 0.05))
    params = {"geometry": f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}", "geometryType": "esriGeometryEnvelope",
              "inSR": "4326", "outSR": "4326", "spatialRel": "esriSpatialRelIntersects", "outFields": out_fields,
              "returnGeometry": "true", "f": "json", "where": where}
    payload = vas.get_json(url, params, "tabaudit")
    if payload.get("exceededTransferLimit") or "features" not in payload:
        raise ValueError("incomplete source response (transfer limit or no features key)")
    return payload["features"]


def _compare(check: str, id_: str, field: str, stored: Optional[float], measured: Optional[float], radius: float) -> dict:
    if measured is None:
        ok = stored is None or stored >= radius - 0.6
        return row(check, id_, field, "OK" if ok else "MISMATCH", f"stored={stored}, nothing in {radius:.0f} mi box")
    if stored is None:
        return row(check, id_, field, "MISMATCH", f"stored=None, source has one at {measured:.2f} mi")
    delta = abs(measured - stored)
    return row(check, id_, field, "OK" if delta <= DELTA_MI else "MISMATCH",
               f"stored={stored} measured={measured:.2f} delta={delta:.2f}")


def measure_site(id_: str, lat: float, lon: float, stored: dict, fields: list[str]) -> list[dict]:
    out = []
    for field in fields:
        layer = vas.INFRA_LAYERS[field]
        s = stored.get(field)
        radius = max(6.0, (s or 0) * 1.6 + 3.0)
        if radius > 45:
            out.append(row("lines", id_, field, "SKIP", f"stored={s} needs a box over 45 mi"))
            continue
        try:
            feats = _bbox_features(layer["url"], lat, lon, radius, layer.get("where", "1=1"),
                                   "VOLTAGE" if field == "transmission_mi" else "")
            m = _segments_min(lat, lon, feats)
            out.append(_compare("lines", id_, field, s, None if m is None else m, radius))
            if field == "transmission_mi":
                for kv in VOLT_THRESHOLDS:
                    key = f"transmission_{kv}kv_mi"
                    if key not in stored and s is None:
                        continue
                    mk = _segments_min(lat, lon, feats, lambda a, kv=kv: (a.get("VOLTAGE") or -1) >= kv)
                    r2 = radius
                    sv = stored.get(key)
                    if mk is None and sv is not None and sv > r2:
                        out.append(row("lines", id_, key, "SKIP", f"stored={sv} beyond the {r2:.0f} mi box"))
                    else:
                        out.append(_compare("lines", id_, key, sv, mk, r2))
        except Exception as exc:  # noqa: BLE001 - every failure becomes a visible ERROR row
            out.append(row("lines", id_, field, "ERROR", f"{type(exc).__name__}: {str(exc)[:100]}"))
    return out


def check_lines(limit: Optional[int]) -> list[dict]:
    manifest = json.loads(MANIFEST.read_text())
    infra = {r["id"]: r for r in load("infra-proximity.json")["sites"]}
    fields = ["transmission_mi", "rail_mi", "highway_mi", "gas_pipeline_mi"]
    out: list[dict] = []
    sites = manifest["corpus_sites"][:limit] if limit else manifest["corpus_sites"]
    for s in sites:
        if s.get("lat") is None:
            continue
        out += measure_site(s["id"], s["lat"], s["lon"], infra.get(s["id"], {}), fields)
    # Nuclear installations and coal plants carry their own distance fields.
    for inst in load("ap1000-sites.json")["sites"][:limit or 99]:
        out += measure_site("ap1000:" + inst["id"], inst["lat"], inst["lon"], inst, ["transmission_mi"])
    for plant in [p for p in load("coal-plants.json")["plants"]][:limit or 99]:
        stored = {"transmission_mi": plant.get("line_mi"), **{f"transmission_{k}kv_mi": plant.get(f"line_{k}kv_mi") for k in VOLT_THRESHOLDS}}
        out += measure_site("coal:" + plant["id"], plant["lat"], plant["lon"], stored, ["transmission_mi"])
    return out


# ----------------------------------------------------------- nuclear inputs

def check_seismic() -> list[dict]:
    out = []
    for inst in load("ap1000-sites.json")["sites"]:
        api = inst.get("usgs_api_source")
        if not api or inst.get("usgs_pgam") is None:
            out.append(row("seismic", inst["id"], "usgs_pgam", "SKIP", "no stored value or API URL"))
            continue
        try:
            base, qs = api.split("?", 1)
            params = dict(p.split("=", 1) for p in qs.split("&"))
            payload = vas.get_json(base, params, "usgs-seismic")
            pga = (payload.get("response", {}).get("data") or {}).get("pgam")
            if pga is None:
                out.append(row("seismic", inst["id"], "usgs_pgam", "ERROR", "response has no data.pgam"))
                continue
            delta = abs(pga - inst["usgs_pgam"])
            out.append(row("seismic", inst["id"], "usgs_pgam", "OK" if delta <= PGA_TOLERANCE_G else "MISMATCH",
                           f"stored={inst['usgs_pgam']} live={pga:.3f} delta={delta:.3f} g (limit 0.30 g)"))
        except Exception as exc:  # noqa: BLE001
            out.append(row("seismic", inst["id"], "usgs_pgam", "ERROR", f"{type(exc).__name__}: {str(exc)[:100]}"))
    return out


def check_flow() -> list[dict]:
    out = []
    for inst in load("ap1000-sites.json")["sites"]:
        gauge, stored = inst.get("supply_gauge"), inst.get("supply_flow_cfs")
        if not gauge or stored is None:
            out.append(row("flow", inst["id"], "supply_flow_cfs", "SKIP", "no supply gauge on record"))
            continue
        try:
            text = _nwis_stat(gauge)
            mean = _parse_rdb_mean(text)
            if mean is None:
                out.append(row("flow", inst["id"], "supply_flow_cfs", "ERROR", f"gauge {gauge}: no annual mean in NWIS reply"))
                continue
            rel = abs(mean - stored) / max(stored, 1)
            out.append(row("flow", inst["id"], "supply_flow_cfs", "OK" if rel <= FLOW_TOLERANCE else "MISMATCH",
                           f"gauge {gauge}: stored={stored} cfs, NWIS mean of annual means={mean:.0f} cfs ({rel:.0%} apart)"))
        except Exception as exc:  # noqa: BLE001
            out.append(row("flow", inst["id"], "supply_flow_cfs", "ERROR", f"{type(exc).__name__}: {str(exc)[:100]}"))
    return out


def _nwis_stat(gauge: str) -> str:
    import hashlib
    url = "https://waterservices.usgs.gov/nwis/stat/"
    params = {"format": "rdb", "sites": gauge, "statReportType": "annual", "statTypeCd": "mean", "parameterCd": "00060"}
    key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()[:12]
    path = vas.CACHE / f"nwis-{key}.txt"
    vas.CACHE.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text()
    resp = requests.get(url, params=params, timeout=45, headers={"User-Agent": vas.USER_AGENT})
    resp.raise_for_status()
    path.write_text(resp.text)
    return resp.text


def _parse_rdb_mean(text: str) -> Optional[float]:
    rows = [ln.split("\t") for ln in text.splitlines() if ln and not ln.startswith("#")]
    if len(rows) < 3:
        return None
    header = rows[0]
    if "mean_va" not in header:
        return None
    i = header.index("mean_va")
    vals = [float(r[i]) for r in rows[2:] if len(r) > i and r[i].strip()]
    return sum(vals) / len(vals) if vals else None


def check_poprings() -> list[dict]:
    places = load("population-centers.json")["places"]
    out = []
    targets = [(i["id"], i) for i in load("ap1000-sites.json")["sites"]] + \
              [(n["id"], n) for n in load("nuclear-civilian-sites.json")["sites"]]
    for id_, rec in targets:
        if rec.get("lat") is None or rec.get("pop_center_mi") is None:
            continue
        best = min(places, key=lambda p: haversine_mi(rec["lat"], rec["lon"], p["lat"], p["lon"]))
        d = haversine_mi(rec["lat"], rec["lon"], best["lat"], best["lon"])
        delta = abs(d - rec["pop_center_mi"])
        ok = delta <= 0.2 and f"{best['name']}, {best['state']}" == rec.get("pop_center_name")
        out.append(row("poprings", id_, "pop_center_mi", "OK" if ok else "MISMATCH",
                       f"stored={rec['pop_center_mi']} {rec.get('pop_center_name')}; recomputed={d:.1f} {best['name']}, {best['state']}"))
    return out


# ------------------------------------------------------------------ state

def _state_index() -> PolygonIndex:
    idx = PolygonIndex(cell_deg=0.5)
    for feat in load("us-states.json")["features"]:
        geom = feat["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            if poly:
                idx.add_polygon(poly, attr=feat["properties"]["name"])
    return idx


STATE_NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
               "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
               "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
               "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
               "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
               "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
               "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
               "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
               "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
               "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}


def check_state() -> list[dict]:
    idx = _state_index()
    manifest = json.loads(MANIFEST.read_text())
    recs = [("corpus:" + s["id"], s) for s in manifest["corpus_sites"]] + \
           [(f"{o['screen']}:{o['id']}", o) for o in manifest["overlay_sites"]]
    out = []
    for label, r in recs:
        st, lat, lon = r.get("state"), r.get("lat"), r.get("lon")
        if not st or lat is None or st not in STATE_NAMES:
            out.append(row("state", label, "state", "SKIP", f"state={st} lat={lat}"))
            continue
        hit = idx.containing(lat, lon)
        near = {idx.containing(lat + dy, lon + dx) for dy in (-0.02, 0, 0.02) for dx in (-0.025, 0, 0.025)}
        if hit == STATE_NAMES[st]:
            out.append(row("state", label, "state", "OK", f"{st} contains ({lat:.4f}, {lon:.4f})"))
        elif STATE_NAMES[st] in near:
            out.append(row("state", label, "state", "OK", f"within ~1.5 mi of the {st} border (polygon is generalised)"))
        else:
            out.append(row("state", label, "state", "MISMATCH", f"stated {st}, coordinate falls in {hit}"))
    return out


# ------------------------------------------------------------------ driver

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", choices=CHECKS, default=list(CHECKS))
    ap.add_argument("--limit", type=int, default=None, help="Cap sites / URLs per network check (smoke runs).")
    ap.add_argument("--out", type=Path, default=REPORT)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    vas.force_ipv4()
    fns = {"coverage": check_coverage, "citations": lambda: check_citations(args.limit), "lines": lambda: check_lines(args.limit),
           "seismic": check_seismic, "flow": check_flow, "poprings": check_poprings, "state": check_state}
    rows: list[dict] = []
    for name in args.only:
        log.info("── %s", name)
        got = fns[name]()
        rows += got
        c = Counter(r["status"] for r in got)
        log.info("   %d rows: %s", len(got), ", ".join(f"{v} {k}" for k, v in sorted(c.items())))
        for r in got:
            if r["status"] in ("MISMATCH", "ERROR", "WARN"):
                log.info("   [%s] %s %s — %s", r["status"], r["id"], r["field"], r["detail"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    log.info("report → %s", args.out)
    # A run where most of a network check errored (offline, throttled, host down) proved nothing: fail it.
    broken = [c for c in args.only if (lambda g: g and sum(r["status"] == "ERROR" for r in g) / len(g) > 0.25)([r for r in rows if r["check"] == c])]
    if broken:
        log.error("more than a quarter of the rows errored for: %s", ", ".join(broken))
    return 1 if broken or any(r["status"] == "MISMATCH" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
