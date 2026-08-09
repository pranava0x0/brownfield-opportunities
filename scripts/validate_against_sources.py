#!/usr/bin/env python3
"""Sampled ground-truth validation of `docs/data/` against the live sources.

`scripts/validate_data.py` proves the corpus is INTERNALLY consistent. That is
necessary but not sufficient: every record could be consistently wrong. This
script closes the gap by re-asking the authoritative service.

Two families:

  attrs  — re-query the owning FeatureServer for a random sample of site ids
           and diff name / state / coordinates / acreage against what we
           shipped. Catches stale pulls and coordinate drift.

  evidence — exercise the per-site verification links the UI publishes in its
           "Sources & evidence" panel. A citation that 404s, errors, or comes
           back empty is worse than no citation: it looks like proof and
           reads as a contradiction. Every bbox link must return at least one
           feature, because its radius is derived from the very distance it
           is meant to evidence.

  infra  — independently recompute the nearest-infrastructure distances. For
           each sampled site we ask the SOURCE layer for the features inside
           a bounding box around the site, then compute the minimum distance
           locally with the same geometry primitives the connector uses.
           This is the only check that can falsify `transmission_mi` and
           friends, because it never touches our own spatial index.

Network notes
-------------
Requests are IPv4-pinned. Several of these hosts (EPA, ArcGIS Online, Census)
publish AAAA records that blackhole from some networks, and urllib3 burns its
full timeout on the v6 address before falling back — turning a 200 ms call
into 60 s. `curl` is unaffected because it happy-eyeballs. See the
2026-08-04/05 backlog entry.

Usage:
    python3 scripts/validate_against_sources.py --sample 25
    python3 scripts/validate_against_sources.py --only infra --sample 12
    python3 scripts/validate_against_sources.py --ids MND039045430,ACRES-192724
"""
from __future__ import annotations

import argparse
import json
import math
import random
import socket
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
CACHE = ROOT / ".cache" / "validation"
sys.path.insert(0, str(ROOT))

from connectors.spatial import SegmentIndex, haversine_mi  # noqa: E402

USER_AGENT = "BrownfieldOpportunities/0.2 (data validation; static dashboard)"
REQUEST_DELAY_S = 1.5
TIMEOUT_S = 45


# --------------------------------------------------------------------------
# IPv4 pinning
# --------------------------------------------------------------------------

def force_ipv4() -> None:
    """Make every outbound resolution return A records only.

    Without this, hosts whose AAAA address is unroutable from the current
    network cost a full connect timeout per request before the IPv4 retry.
    """
    original = socket.getaddrinfo

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only


# --------------------------------------------------------------------------
# HTTP with an on-disk cache
# --------------------------------------------------------------------------

_last_call = {"t": 0.0}


def get_json(url: str, params: dict, label: str) -> Any:
    """GET JSON with a disk cache and a polite inter-request delay."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = json.dumps([url, params], sort_keys=True)
    path = CACHE / f"{label}-{abs(hash(key)) & 0xFFFFFFFFFFFF:012x}.json"
    if path.exists():
        return json.loads(path.read_text())

    wait = REQUEST_DELAY_S - (time.time() - _last_call["t"])
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, params=params, timeout=TIMEOUT_S,
                        headers={"User-Agent": USER_AGENT})
    _last_call["t"] = time.time()
    resp.raise_for_status()
    payload = resp.json()
    # ArcGIS reports query errors with HTTP 200 and an `error` object. Left
    # unchecked, a bad field name reads downstream as "the source has no such
    # record" — a validation script that silently turns its own bugs into
    # findings is worse than no script.
    if isinstance(payload, dict) and "error" in payload:
        err = payload["error"]
        raise RuntimeError(
            f"ArcGIS error {err.get('code')}: {err.get('message')} "
            f"{'; '.join(err.get('details') or [])}"[:200]
        )
    path.write_text(json.dumps(payload))
    return payload


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

SUPERFUND_URL = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0/query"
)
ACRES_URL = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "All%20ACRES%20Properties%208_30_2021/FeatureServer/0/query"
)
FUDS_URL = (
    "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/"
    "fuds/FeatureServer/1/query"
)
BRAC_URL = (
    "https://services.arcgis.com/hRUr1F8lE8Jq2uJo/arcgis/rest/services/"
    "milbases/FeatureServer/0/query"
)

# Polyline layers we can independently re-measure. `id_field` is only used
# for reporting which feature won.
INFRA_LAYERS = {
    "transmission_mi": {
        "url": "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/"
               "services/Electric_Power_Transmission_Lines/FeatureServer/0/query",
        "esri": True,
    },
    "highway_mi": {
        "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
               "Transportation/MapServer/2/query",
        "esri": True,
        "where": "MTFCC='S1100'",
    },
    "rail_mi": {
        "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
               "Transportation/MapServer/9/query",
        "esri": True,
    },
    "gas_pipeline_mi": {
        "url": "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/"
               "services/Natural_Gas_Interstate_and_Intrastate_Pipelines_1/"
               "FeatureServer/0/query",
        "esri": True,
    },
}


# Enrichment files merged into the sampled records. The evidence check needs
# these: `buildEvidence()` only emits a row for a field the site actually
# carries, so a bare program record would produce identity rows and nothing
# else — the infra and overlay citations, which are most of the value, would
# never be exercised. (First cut of the evidence sweep did exactly that and
# "passed" 40/40 while testing one field.)
ENRICHMENT_FOR_EVIDENCE = (
    "infra-proximity.json", "opportunity-zone.json", "ira-energy-community.json",
    "fema-nri.json", "climate-zone.json", "iso-rto.json", "epa-echo.json",
    "eia-retired-plants.json", "planned-retirements-proximity.json",
    "coord-quality.json", "epa-redev.json", "epa-superfund-docs.json",
    "parcel-owner.json", "ai-summary.json", "acres-cleanup.json",
)


def load_universe() -> dict[str, dict]:
    universe = {}
    for fname in ("superfund-npl.json", "epa-acres.json", "dod-fuds.json",
                  "dod-brac.json"):
        for rec in json.loads((DATA / fname).read_text())["sites"]:
            universe[rec["id"]] = rec

    infra = {r["id"]: r
             for r in json.loads((DATA / "infra-proximity.json").read_text())["sites"]}
    for sid, rec in universe.items():
        rec["_infra"] = infra.get(sid, {})

    # Fill-if-empty, mirroring every ensure*Loaded() join in app.js so the
    # sampled record matches what a browser actually holds.
    for fname in ENRICHMENT_FOR_EVIDENCE:
        path = DATA / fname
        if not path.exists():
            continue
        for rec in json.loads(path.read_text()).get("sites", []):
            target = universe.get(rec.get("id"))
            if target is None:
                continue
            for key, val in rec.items():
                if key in ("id", "program") or val is None:
                    continue
                if target.get(key) is None:
                    target[key] = val
    return universe


# --------------------------------------------------------------------------
# Attribute round-trip
# --------------------------------------------------------------------------

def check_attrs(sites: list[dict]) -> list[dict]:
    """Re-query each site's owning service and diff the core attributes."""
    results = []
    for rec in sites:
        program = rec["program"]
        try:
            if program == "superfund":
                got = _fetch_superfund(rec["id"])
            elif program == "brownfield":
                got = _fetch_acres(rec["id"].removeprefix("ACRES-"))
            elif program == "fuds":
                got = _fetch_fuds(rec["id"].removeprefix("FUDS-"))
            elif program == "brac":
                got = _fetch_brac(rec["id"].removeprefix("BRAC-"))
            else:
                continue
        except Exception as exc:
            results.append({"id": rec["id"], "status": "ERROR",
                            "detail": f"{type(exc).__name__}: {exc}"})
            continue

        if got is None:
            results.append({"id": rec["id"], "status": "NOT-FOUND",
                            "detail": "source no longer returns this id"})
            continue

        diffs = []
        if got.get("state") and rec.get("state") and got["state"].upper() != rec["state"]:
            diffs.append(f"state ours={rec['state']} source={got['state'].upper()}")
        tol = COORD_TOLERANCE_MI.get(program, 0.25)
        if got.get("lat") is not None and rec.get("lat") is not None:
            d = haversine_mi(rec["lat"], rec["lon"], got["lat"], got["lon"])
            if d > tol:
                diffs.append(f"coords {round(d, 2)} mi apart "
                             f"(ours={rec['lat']},{rec['lon']} "
                             f"source={round(got['lat'], 6)},{round(got['lon'], 6)})")
        if got.get("acreage") is not None and rec.get("acreage"):
            ratio = got["acreage"] / rec["acreage"]
            if ratio > 1.5 or ratio < 0.66:
                diffs.append(f"acreage ours={rec['acreage']} source={got['acreage']}")
        results.append({
            "id": rec["id"], "program": program,
            "status": "MISMATCH" if diffs else "OK",
            "detail": "; ".join(diffs) or "name/state/coords/acreage agree",
        })
    return results


# Per-program coordinate tolerance, in miles. FUDS is loose on purpose: our
# lat/lon prefers the layer-4 polygon centroid when USACE has digitized a
# boundary, while this check reads layer 1's point. For a property spanning
# miles those legitimately differ — only a gross disagreement is a finding.
COORD_TOLERANCE_MI = {"superfund": 0.25, "brownfield": 0.25, "fuds": 3.0}


def _envelope_center(rings) -> tuple[Optional[float], Optional[float]]:
    """Bounding-box midpoint across all rings.

    Deliberately matches `SuperfundNPL.envelope_center` rather than using an
    area-weighted centroid — comparing against a different definition would
    manufacture disagreement on every multi-polygon site.
    """
    xs, ys = [], []
    for ring in rings or []:
        for pt in ring:
            if pt and len(pt) >= 2:
                xs.append(pt[0])
                ys.append(pt[1])
    if not xs:
        return None, None
    return (min(ys) + max(ys)) / 2.0, (min(xs) + max(xs)) / 2.0


def _fetch_superfund(epa_id: str) -> Optional[dict]:
    payload = get_json(SUPERFUND_URL, {
        "where": f"EPA_ID='{epa_id}'",
        "outFields": "EPA_ID,SITE_NAME,STATE_CODE,GIS_AREA,GIS_AREA_UNITS,NPL_STATUS_CODE",
        "returnGeometry": "true", "outSR": "4326", "f": "json",
    }, "sf")
    feats = payload.get("features") or []
    if not feats:
        return None
    attrs = feats[0]["attributes"]
    lat = lon = None
    rings = []
    for f in feats:
        rings.extend((f.get("geometry") or {}).get("rings") or [])
    if rings:
        lat, lon = _envelope_center(rings)
    area = attrs.get("GIS_AREA")
    units = (attrs.get("GIS_AREA_UNITS") or "").strip().lower()
    acreage = None
    if area is not None:
        if units == "acres":
            acreage = float(area)
        elif units == "square miles":
            acreage = float(area) * 640.0
    return {"state": attrs.get("STATE_CODE"), "lat": lat, "lon": lon,
            "acreage": acreage, "name": attrs.get("SITE_NAME")}


def _fetch_acres(property_id: str) -> Optional[dict]:
    payload = get_json(ACRES_URL, {
        "where": f"PROPERTY_ID={property_id}",
        "outFields": "PROPERTY_ID,PROPERTY_NAME,LABEL_STATE,CITY,COUNTY,"
                     "LATITUDE_MEASURE,LONGITUDE_MEASURE",
        "returnGeometry": "false", "f": "json",
    }, "acres")
    feats = payload.get("features") or []
    if not feats:
        return None
    a = feats[0]["attributes"]
    return {"state": a.get("LABEL_STATE"), "lat": a.get("LATITUDE_MEASURE"),
            "lon": a.get("LONGITUDE_MEASURE"), "acreage": None,
            "name": a.get("PROPERTY_NAME"), "city": a.get("CITY")}


def _fetch_fuds(prop_id: str) -> Optional[dict]:
    payload = get_json(FUDS_URL, {
        "where": f"DODFUDSPROPERTYIDPK='{prop_id}'",
        # Layer 1's name field is FEATURENAME, not PROPERTYNAME. It also
        # carries LATITUDE/LONGITUDE attributes alongside the point geometry.
        "outFields": "DODFUDSPROPERTYIDPK,FEATURENAME,STATE,ELIGIBILITY,"
                     "LATITUDE,LONGITUDE",
        "returnGeometry": "true", "outSR": "4326", "f": "json",
    }, "fuds")
    feats = payload.get("features") or []
    if not feats:
        return None
    a = feats[0]["attributes"]
    g = feats[0].get("geometry") or {}
    lat = g.get("y") if g.get("y") is not None else a.get("LATITUDE")
    lon = g.get("x") if g.get("x") is not None else a.get("LONGITUDE")
    state = a.get("STATE")
    return {"state": state.upper() if state else None, "lat": lat, "lon": lon,
            "acreage": None, "name": a.get("FEATURENAME")}


def _fetch_brac(objectid: str) -> Optional[dict]:
    """BRAC ids are `BRAC-<OBJECTID>`.

    Note this contradicts CLAUDE.md, which documents the namespace as
    `BRAC-<slugified SITE_NAME>`; `dod_brac.normalize()` actually keys on
    OBJECTID and only falls back to the name when OBJECTID is absent.
    """
    if not objectid.isdigit():
        return None
    payload = get_json(BRAC_URL, {
        "where": f"OBJECTID={objectid} AND BRAC_SITE='YES'",
        "outFields": "OBJECTID,SITE_NAME,STPOSTAL,COMPONENT",
        "returnGeometry": "true", "outSR": "4326", "f": "json",
    }, "brac")
    feats = payload.get("features") or []
    if not feats:
        return None
    a = feats[0]["attributes"]
    rings = (feats[0].get("geometry") or {}).get("rings") or []
    lat, lon = _envelope_center(rings)
    acreage = None
    if rings:
        # Match dod_brac exactly: Shoelace + cos(lat), via the shared helper.
        from connectors.geom import ACRES_PER_SQ_METER, polygon_area_sq_meters
        area = polygon_area_sq_meters(rings)
        acreage = round(area * ACRES_PER_SQ_METER, 1) if area > 0 else None
    return {"state": a.get("STPOSTAL"), "lat": lat, "lon": lon,
            "acreage": acreage, "name": a.get("SITE_NAME")}


# --------------------------------------------------------------------------
# Independent infra re-measurement
# --------------------------------------------------------------------------

def check_infra(sites: list[dict], fields: list[str]) -> list[dict]:
    """Re-measure nearest-feature distance straight from the source layer.

    We ask the service for everything inside a box around the site, load only
    those features into a throwaway index, and take the minimum. If the box
    turns up nothing, the stored value must be at least the box radius —
    that's still a real (one-sided) test, so we report it rather than skip.
    """
    results = []
    for rec in sites:
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        for field in fields:
            stored = rec["_infra"].get(field)
            layer = INFRA_LAYERS[field]
            # Box must comfortably exceed the stored distance so the true
            # nearest feature is inside it.
            radius_mi = max(6.0, (stored or 0) * 1.6 + 3.0)
            if radius_mi > 45:
                results.append({"id": rec["id"], "field": field, "status": "SKIP",
                                "detail": f"stored={stored} needs too large a box"})
                continue
            try:
                measured, n = _measure(lat, lon, layer, radius_mi)
            except Exception as exc:
                results.append({"id": rec["id"], "field": field, "status": "ERROR",
                                "detail": f"{type(exc).__name__}: {str(exc)[:90]}"})
                continue

            if measured is None:
                status = "OK" if stored is None or stored >= radius_mi - 0.6 else "MISMATCH"
                detail = (f"no features within {radius_mi:.0f} mi box "
                          f"(stored={stored})")
            elif stored is None:
                status = "MISMATCH"
                detail = f"stored=None but source has one at {measured:.2f} mi"
            else:
                delta = abs(measured - stored)
                status = "OK" if delta <= 0.35 else "MISMATCH"
                detail = (f"stored={stored} measured={measured:.2f} "
                          f"delta={delta:.2f} ({n} feats)")
            results.append({"id": rec["id"], "field": field,
                            "status": status, "detail": detail})
    return results


def _measure(lat: float, lon: float, layer: dict,
             radius_mi: float) -> tuple[Optional[float], int]:
    """Min distance from (lat, lon) to any source feature in a bbox."""
    dlat = radius_mi / 69.0
    dlon = radius_mi / (69.0 * max(math.cos(math.radians(lat)), 0.05))
    params = {
        "geometry": f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "", "returnGeometry": "true", "f": "json",
        "where": layer.get("where", "1=1"),
    }
    payload = get_json(layer["url"], params, "infra")
    feats = payload.get("features") or []
    if not feats:
        return None, 0
    idx = SegmentIndex()
    for f in feats:
        for path in (f.get("geometry") or {}).get("paths") or []:
            idx.add_polyline(path)
    return idx.nearest_distance_mi(lat, lon), len(feats)


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Evidence-link integrity
# --------------------------------------------------------------------------

NODE_HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
// provenance.js is an IIFE that assigns onto `window`.
const window = {};
(new Function('window', src))(window);
const sites = JSON.parse(process.argv[3]);
const out = [];
for (const s of sites) {
  for (const row of window.buildEvidence(s)) {
    if (row.verifyUrl) out.push({ id: s.id, key: row.key, url: row.verifyUrl,
                                  expectsFeatures: row.expectsFeatures !== false });
  }
}
process.stdout.write(JSON.stringify(out));
"""


def check_evidence(sites: list[dict]) -> list[dict]:
    """Ask provenance.js for each site's verification links, then fetch them.

    The registry lives in JavaScript because the browser renders it, so we
    evaluate the real module with node rather than reimplementing it here —
    a second copy of the URL-building logic would be the thing most likely
    to drift out of agreement with what users actually click.
    """
    import subprocess
    import tempfile

    prov = ROOT / "docs" / "provenance.js"
    if not prov.exists():
        return [{"id": "-", "field": "-", "status": "ERROR",
                 "detail": "docs/provenance.js not found"}]

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(NODE_HARNESS)
        harness = fh.name
    try:
        proc = subprocess.run(
            ["node", harness, str(prov),
             json.dumps([{k: v for k, v in s.items() if not k.startswith("_")}
                         for s in sites])],
            capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        return [{"id": "-", "field": "-", "status": "SKIP",
                 "detail": "node not available"}]
    if proc.returncode != 0:
        return [{"id": "-", "field": "-", "status": "ERROR",
                 "detail": f"node harness failed: {proc.stderr[:200]}"}]

    links = json.loads(proc.stdout or "[]")
    # One site's record-query link is identical across its identity fields;
    # fetching it once per field would just burn rate limit.
    seen: set[str] = set()
    results = []
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        if not link["url"].startswith("http"):
            results.append({**link, "status": "ERROR", "detail": "not an http url"})
            continue
        # Landing pages (energycommunities.gov, FEMA NRI, OSM) are plain HTML
        # portals with no queryable contract — reachability is all we can
        # assert. Query URLs get the stronger "must return data" check.
        is_query = "/query?" in link["url"]
        try:
            resp = requests.get(link["url"], timeout=TIMEOUT_S,
                                headers={"User-Agent": USER_AGENT})
        except Exception as exc:
            results.append({**link, "status": "ERROR",
                            "detail": f"{type(exc).__name__}: {str(exc)[:80]}"})
            continue
        if resp.status_code != 200:
            results.append({**link, "status": "DEAD",
                            "detail": f"HTTP {resp.status_code}"})
            continue
        if not is_query:
            results.append({**link, "status": "OK", "detail": "reachable"})
            continue
        try:
            payload = resp.json()
        except Exception:
            results.append({**link, "status": "DEAD",
                            "detail": "query did not return JSON"})
            continue
        if isinstance(payload, dict) and "error" in payload:
            results.append({**link, "status": "DEAD",
                            "detail": f"service error {payload['error'].get('code')}"})
            continue
        n = len(payload.get("features") or [])
        if n == 0 and not link.get("expectsFeatures", True):
            # A negative claim is evidenced by an empty result.
            results.append({**link, "status": "OK",
                            "detail": "no features — correct for a negative claim"})
            continue
        if n == 0:
            results.append({**link, "status": "EMPTY",
                            "detail": "returned no features — the citation "
                                      "contradicts the claim it supports"})
            continue
        results.append({**link, "status": "OK", "detail": f"{n} features"})
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=20, help="Sites per program.")
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--only", nargs="*", default=["attrs", "infra"],
                    choices=["attrs", "infra", "evidence"])
    ap.add_argument("--ids", default=None, help="Comma-separated ids instead of a sample.")
    ap.add_argument("--fields", nargs="*", default=list(INFRA_LAYERS))
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    force_ipv4()
    universe = load_universe()
    rng = random.Random(args.seed)

    if args.ids:
        sample = [universe[i] for i in args.ids.split(",") if i in universe]
        missing = [i for i in args.ids.split(",") if i not in universe]
        for m in missing:
            print(f"[warn] id not in corpus: {m}", file=sys.stderr)
    else:
        sample = []
        for program in ("superfund", "brownfield", "fuds", "brac"):
            pool = [r for r in universe.values()
                    if r["program"] == program and r.get("lat") is not None]
            sample.extend(rng.sample(pool, min(args.sample, len(pool))))

    print(f"sampling {len(sample)} sites  (seed={args.seed})\n", file=sys.stderr)
    out: dict[str, list] = {}

    if "attrs" in args.only:
        print("── ATTRIBUTE ROUND-TRIP " + "─" * 46)
        res = check_attrs(sample)
        out["attrs"] = res
        for r in res:
            if r["status"] != "OK":
                print(f"  [{r['status']:9}] {r['id']:<16} {r['detail']}")
        _tally(res)

    if "infra" in args.only:
        print("\n── INDEPENDENT INFRA RE-MEASUREMENT " + "─" * 34)
        res = check_infra(sample, args.fields)
        out["infra"] = res
        for r in res:
            if r["status"] not in ("OK", "SKIP"):
                print(f"  [{r['status']:9}] {r['id']:<16} {r['field']:<17} {r['detail']}")
        _tally(res)

    if "evidence" in args.only:
        print("\n── EVIDENCE-LINK INTEGRITY " + "─" * 43)
        res = check_evidence(sample)
        out["evidence"] = res
        for r in res:
            if r["status"] != "OK":
                print(f"  [{r['status']:9}] {r.get('id', '-'):<16} "
                      f"{r.get('key', '-'):<22} {r['detail']}")
        _tally(res)

    if args.json:
        args.json.write_text(json.dumps(out, indent=1))
        print(f"\nfull detail → {args.json}")
    return 0


def _tally(res: list[dict]) -> None:
    from collections import Counter
    c = Counter(r["status"] for r in res)
    total = len(res)
    ok = c.get("OK", 0)
    print(f"  → {ok}/{total} OK · " +
          " · ".join(f"{v} {k}" for k, v in sorted(c.items()) if k != "OK"))


if __name__ == "__main__":
    sys.exit(main())
