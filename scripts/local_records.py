#!/usr/bin/env python3
"""County, city and state land-record research for the sites the tabs list.

Three roles, and only the first two use a model:

  Haiku researchers   find portals and dated records, each with a verbatim quote
  Sonnet verifiers    open every cited page and judge each claim independently
  Code (this file)    builds the work queue, re-queries the state parcel layer,
                      re-fetches every cited page to look for the quote, applies
                      the adjudication rules, and writes the shipped file

Where code and the Sonnet verifier disagree the fact is "disputed" and goes to
an Opus adjudicator; `apply-opus` records its decision. Nothing a researcher
wrote reaches docs/data/local-records.json without passing through `adjudicate`.

Workflow (files live under data/validation/local-records/):

  queue        tab-sites.json -> queue.json + batches/batch-NN.json (4 sites each)
  parcels      live parcel-layer re-query for sites in states with a statewide layer
  (agents)     research/<batch>.json  <- Haiku;  verdicts/<batch>.json  <- Sonnet
  adjudicate   fetch + quote-check + decide -> adjudicated.json, disputes.json
  (agent)      opus/<batch>.json  <- Opus, for disputes only
  apply-opus   fold the Opus decisions in
  publish      write docs/data/local-records.json (accepted facts only)
  report       one-screen summary

Usage:
  python3 scripts/local_records.py queue --batch-size 4
  python3 scripts/local_records.py parcels
  python3 scripts/local_records.py adjudicate
  python3 scripts/local_records.py publish
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import logging
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WORK = ROOT / "data" / "validation" / "local-records"
MANIFEST = ROOT / "data" / "validation" / "tab-sites.json"
OUTPUT = ROOT / "docs" / "data" / "local-records.json"
PAGE_CACHE = ROOT / ".cache" / "local-records"
SHIPPED_STATUSES = ("accepted", "accepted_code_only", "accepted_model_only")
SOURCE_LABEL = "County, city and state land records for tab sites (researched, verified, adjudicated)"
USER_AGENT = "Mozilla/5.0 (compatible; BrownfieldOpportunities record check)"
REQUEST_DELAY_S = 1.5
log = logging.getLogger("local_records")
_last = {"t": 0.0}


# ------------------------------------------------------------ pure helpers

def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    return html.unescape(re.sub(r"<[^>]+>", " ", raw))


def normalize_text(text: str) -> str:
    """Case, whitespace, quote and dash differences must not hide a real match."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[‐-―−]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def quote_in_text(quote: str, page_text: str) -> bool:
    q = normalize_text(quote).strip(" .\"'")
    return len(q) >= 8 and q in normalize_text(page_text)


def decide(code_check: str, verifier: Optional[str]) -> tuple[str, str]:
    """Adjudication rule: (status, decided_by). `disputed` goes to the Opus adjudicator.

    code_check: quote_found | quote_missing | unfetchable | non_text | dead
    verifier:   supported | unsupported | contradicted | unverifiable | None (not yet verified)

    "unverifiable" means the second model could not judge the claim, so a quote that merely
    exists on the page is `accepted_code_only`: the words are real, nobody has checked that the
    summary, date or amount matches them. The panel labels each status differently.
    """
    if verifier is None or code_check == "dead":
        return "rejected", "code"                     # never ship what no second model read, or a page that is gone
    if verifier == "contradicted":
        return ("disputed", "code") if code_check == "quote_found" else ("rejected", "code")
    if code_check == "quote_found":
        if verifier == "supported":
            return "accepted", "code"
        return ("accepted_code_only", "code") if verifier == "unverifiable" else ("disputed", "code")
    if code_check == "quote_missing":
        return ("disputed", "code") if verifier == "supported" else ("rejected", "code")
    # The page could not be read by code (JS portal, PDF, throttled): the verifier's read stands, flagged.
    return ("accepted_model_only", "code") if verifier == "supported" else ("rejected", "code")


# ------------------------------------------------------------------ fetching

def fetch_page(url: str) -> tuple[str, Optional[str]]:
    """(status, text). status: ok | non_text | unfetchable. Cached on disk by URL."""
    import requests
    PAGE_CACHE.mkdir(parents=True, exist_ok=True)
    path = PAGE_CACHE / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".json")
    if path.exists():
        c = json.loads(path.read_text())
        return c["status"], c.get("text")
    wait = REQUEST_DELAY_S - (time.time() - _last["t"])
    if wait > 0:
        time.sleep(wait)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=40)
        _last["t"] = time.time()
        ctype = resp.headers.get("content-type", "").lower()
        if resp.status_code in (404, 410):
            out = {"status": "dead", "text": None, "http": resp.status_code}
        elif resp.status_code >= 400:
            out = {"status": "unfetchable", "text": None, "http": resp.status_code}
        elif "html" in ctype or "text" in ctype or "xml" in ctype or "json" in ctype:
            out = {"status": "ok", "text": html_to_text(resp.text), "http": resp.status_code}
        else:
            out = {"status": "non_text", "text": None, "http": resp.status_code}
    except requests.RequestException as exc:
        # A timeout or TLS blip is not a property of the page: report it, but never cache it.
        return "unfetchable", None
    path.write_text(json.dumps(out))
    return out["status"], out.get("text")


def https_url(url: str) -> str:
    """Researchers sometimes write http:// for a site that serves https; the schema only ships https."""
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def invalid_fact(fact: dict) -> Optional[str]:
    """Why a researcher's fact cannot be ranked at all, or None. Uses the shipped schema, minus the fields only code sets."""
    from schema import LocalFact
    fact["source_url"] = https_url(str(fact.get("source_url", "")))
    try:
        LocalFact.model_validate({k: v for k, v in fact.items() if k not in ("status", "code_check", "verifier", "adjudicated_by", "reject_reason")})
    except Exception as exc:  # noqa: BLE001 - pydantic's message is the reason shown
        return str(exc).splitlines()[0][:160]
    return None


def invalid_portal(portal: dict) -> bool:
    from schema import LocalPortal
    try:
        LocalPortal.model_validate(portal)
    except Exception:  # noqa: BLE001
        return True
    return False


def code_check_for(url: str, quote: str) -> str:
    status, text = fetch_page(url)
    if status == "dead":
        return "dead"
    if status == "non_text":
        return "non_text"
    if status != "ok" or not text:
        return "unfetchable"
    return "quote_found" if quote_in_text(quote, text) else "quote_missing"


# -------------------------------------------------------------------- queue

def _county_fips() -> Any:
    from connectors.county_lookup import CountyIndex
    return CountyIndex.from_path(ROOT / "docs" / "data" / "us-counties-topo.json")


def _best_rank(site: dict) -> Optional[int]:
    ranks = [t["rank"] for t in site["tabs"] if t.get("rank") is not None]
    return min(ranks) if ranks else None


def cmd_queue(args: argparse.Namespace) -> int:
    """Write batches for sites not yet researched. Existing batch files that already have research are kept."""
    from connectors.parcel_owner import STATE_PARCEL_SOURCES
    manifest = json.loads(MANIFEST.read_text())
    sites = manifest["corpus_sites"]
    if args.per_screen:
        # Sites in the first N rows of a screen, plus those listed beside civilian nuclear sites (unranked).
        sites = [s for s in sites if (_best_rank(s) or 10**6) <= args.per_screen or any(t["tab"] == "civilian" for t in s["tabs"])]
    if args.limit:
        sites = sites[: args.limit]
    for sub in ("batches", "research", "verdicts", "opus"):
        (WORK / sub).mkdir(parents=True, exist_ok=True)
    done = set(_load_dir("research"))
    keep = {p.name for p in (WORK / "batches").glob("batch-*.json")
            if p.stem in {f.stem for f in (WORK / "research").glob("*.json")}}
    for p in (WORK / "batches").glob("batch-*.json"):
        if p.name not in keep:
            p.unlink()
    packets = []
    for s in sites:
        if s["id"] in done:
            continue
        packets.append({
            "id": s["id"], "name": s["name"], "program": s["program"], "address": s.get("address"), "city": s.get("city"),
            "county": s.get("county"), "state": s["state"], "zip": s.get("zip"), "lat": s["lat"], "lon": s["lon"],
            "acreage": s.get("acreage"), "tabs": sorted({t["tab"] for t in s["tabs"]}),
            "atlas_owner": s.get("current_owner"), "atlas_owner_source": s.get("current_owner_source"),
            "atlas_parcel_id": s.get("parcel_id"),
            "state_parcel_layer": bool(STATE_PARCEL_SOURCES.get(s["state"])),
        })
    first = max([int(re.search(r"\d+", n).group()) for n in keep] or [0]) + 1
    n = args.batch_size
    batches = [packets[i:i + n] for i in range(0, len(packets), n)]
    for i, batch in enumerate(batches, first):
        (WORK / "batches" / f"batch-{i:02d}.json").write_text(json.dumps({"batch": f"batch-{i:02d}", "sites": batch}, indent=1))
    (WORK / "queue.json").write_text(json.dumps({"generated_at": _now(), "sites_queued": len(packets), "already_researched": len(done),
                                                 "batches": len(batches), "first_batch": first}, indent=1))
    log.info("%d sites queued in %d batches (batch-%02d onward); %d already researched", len(packets), len(batches), first, len(done))
    return 0


# ------------------------------------------------------------------ parcels

def cmd_parcels(args: argparse.Namespace) -> int:
    """Live re-query of the state parcel layer: does it still say what the atlas says?"""
    import requests
    from connectors.parcel_owner import NON_PARCEL_ID, STATE_PARCEL_SOURCES
    out = {}
    packets = [s for b in sorted((WORK / "batches").glob("batch-*.json")) for s in json.loads(b.read_text())["sites"]]
    today = dt.date.today().isoformat()
    for s in packets:
        src = STATE_PARCEL_SOURCES.get(s["state"])
        base = {"atlas_owner": s["atlas_owner"], "atlas_parcel_id": s["atlas_parcel_id"], "checked_at": today}
        if not src:
            out[s["id"]] = {**base, "status": "no_layer"}
            continue
        params = {"geometry": f"{s['lon']},{s['lat']}", "geometryType": "esriGeometryPoint", "inSR": "4326",
                  "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "false", "f": "json",
                  "outFields": ",".join(f for f in (src.get("owner_field"), src.get("parcel_id_field")) if f)}
        try:
            time.sleep(REQUEST_DELAY_S)
            resp = requests.get(f"{src['base']}/query", params=params, timeout=45, headers={"User-Agent": USER_AGENT})
            try:
                data = resp.json()
            except ValueError:
                raise RuntimeError(f"HTTP {resp.status_code}, reply was not JSON") from None
            if "error" in data:
                raise RuntimeError(str(data["error"].get("message")))
            feats = data.get("features") or []
            attrs = (feats[0].get("attributes") or {}) if feats else {}
            owner = str(attrs.get(src["owner_field"]) or "").strip() or None if src.get("owner_field") else None
            pid = str(attrs.get(src.get("parcel_id_field")) or "").strip() or None
            if not feats or NON_PARCEL_ID.search(pid or ""):
                out[s["id"]] = {**base, "status": "no_match", "source": src["source"]}
                continue
            comparable = bool(owner) and bool(s["atlas_owner"])
            owner_same = comparable and owner.lower() == s["atlas_owner"].lower()
            pid_same = s["atlas_parcel_id"] is None or (pid or "") == s["atlas_parcel_id"]
            # FUDS rows carry USACE's ownership TYPE ("Private — ...", "Federal — ..."), not a named owner, and the
            # parcel join never replaces it. A live named owner against that category is an upgrade, not a conflict.
            category = s["program"] == "fuds" and bool(re.match(r"(?i)^(private|federal|state|local government|tribal|other|dod)\b", s["atlas_owner"] or ""))
            if category and owner:
                status = "atlas_is_category"
            elif not comparable:
                status = "owner_not_comparable"     # one side has no owner name (layer has no owner field, or the atlas has none)
            else:
                status = "confirmed" if owner_same and pid_same else "differs"
            out[s["id"]] = {**base, "status": status, "live_owner": owner,
                            "live_parcel_id": pid, "source": src["source"]}
        except Exception as exc:  # noqa: BLE001 - recorded per site, never fatal to the batch
            out[s["id"]] = {**base, "status": "error", "source": f"{type(exc).__name__}: {str(exc)[:120]}"}
    (WORK / "parcel-checks.json").write_text(json.dumps(out, indent=1))
    from collections import Counter
    log.info("parcel checks: %s", dict(Counter(v["status"] for v in out.values())))
    return 0


# --------------------------------------------------------------- adjudicate

def _load_dir(sub: str) -> dict[str, dict]:
    """site id -> object, from every file in a role's directory."""
    out: dict[str, dict] = {}
    for f in sorted((WORK / sub).glob("*.json")):
        data = json.loads(f.read_text())
        for rec in data.get("sites", [data] if "id" in data else []):
            out[rec["id"]] = rec
    return out


def _bind_verdicts(facts: list[dict], verdicts: list[dict]) -> dict[int, dict]:
    """Map fact index -> verdict, refusing a verdict that may belong to a different fact.

    A verdict that echoes `source_url` must match the fact at that index. A verdict file that
    does not echo it (older runs) is trusted only when it covers exactly as many facts as exist,
    so a re-run research file with added or reordered facts cannot inherit an old "supported".
    """
    out: dict[int, dict] = {}
    if any("source_url" not in x for x in verdicts) and len(verdicts) != len(facts):
        return out
    for x in verdicts:
        i = x.get("index")
        if not isinstance(i, int) or not 0 <= i < len(facts):
            continue
        if "source_url" in x and https_url(str(x["source_url"])) != https_url(str(facts[i].get("source_url", ""))):
            continue
        out[i] = x
    return out


def cmd_adjudicate(args: argparse.Namespace) -> int:
    research, verdicts = _load_dir("research"), _load_dir("verdicts")
    parcels = json.loads((WORK / "parcel-checks.json").read_text()) if (WORK / "parcel-checks.json").exists() else {}
    packets = {s["id"]: s for b in sorted((WORK / "batches").glob("batch-*.json")) for s in json.loads(b.read_text())["sites"]}
    adjudicated, disputes = {}, []
    for sid, r in research.items():
        v = verdicts.get(sid, {})
        by_index = _bind_verdicts(r.get("facts", []), v.get("fact_verdicts", []))
        portal_ok = {x["url"]: x for x in v.get("portal_verdicts", [])}
        facts = []
        for i, fact in enumerate(r.get("facts", [])):
            fact = dict(fact)
            problem = invalid_fact(fact)
            if problem:
                # A malformed claim is rejected and kept visible, never a crash that loses the rest of the batch.
                fact.update(status="rejected", adjudicated_by="code", code_check="unfetchable", reject_reason=problem)
                facts.append(fact)
                continue
            fact["code_check"] = code_check_for(fact["source_url"], fact["quote"])
            fact["verifier"] = (by_index.get(i) or {}).get("verdict")
            fact["status"], fact["adjudicated_by"] = decide(fact["code_check"], fact["verifier"])
            if fact["status"] == "disputed":
                disputes.append({"id": sid, "name": r.get("name"), "index": i, "fact": fact,
                                 "verifier_note": (by_index.get(i) or {}).get("note")})
            facts.append(fact)
        portals = []
        for p in r.get("portals", []):
            p = dict(p)
            p["url"] = https_url(p.get("url") or "")
            if not p["url"] or invalid_portal(p):
                continue
            pv = portal_ok.get(p["url"]) or portal_ok.get(p["url"].replace("https://", "http://", 1))
            status, _ = fetch_page(p["url"])
            # A portal stays when a verifier reached it or code could; a dead link is dropped.
            if (pv and pv.get("reachable")) or status in ("ok", "non_text"):
                portals.append(p)
        adjudicated[sid] = {"id": sid, "name": packets.get(sid, {}).get("name") or r.get("name"), "gaps": r.get("gaps"),
                            "county": packets.get(sid, {}).get("county"), "state": packets.get(sid, {}).get("state"),
                            "researchers": sorted(set(filter(None, [r.get("researcher"), v.get("verifier")]))),
                            "portals": portals, "facts": facts,
                            "parcel": parcels.get(sid)}
    (WORK / "adjudicated.json").write_text(json.dumps(adjudicated, indent=1, ensure_ascii=False))
    (WORK / "disputes.json").write_text(json.dumps(disputes, indent=1, ensure_ascii=False))
    from collections import Counter
    c = Counter(f["status"] for a in adjudicated.values() for f in a["facts"])
    log.info("facts: %s; %d disputes -> %s", dict(c), len(disputes), WORK / "disputes.json")
    return 0


def cmd_apply_opus(args: argparse.Namespace) -> int:
    adj = json.loads((WORK / "adjudicated.json").read_text())
    n = 0
    for sid, dec in _load_dir("opus").items():
        for d in dec.get("decisions", []):
            fact = adj[sid]["facts"][d["index"]]
            if fact["status"] == "disputed":
                fact["status"] = "accepted" if d["decision"] == "accept" else "rejected"
                fact["adjudicated_by"] = "opus"
                n += 1
        adj[sid]["researchers"] = sorted(set(adj[sid]["researchers"]) | {dec.get("adjudicator", "Claude Opus 5.5")})
    (WORK / "adjudicated.json").write_text(json.dumps(adj, indent=1, ensure_ascii=False))
    log.info("applied %d Opus decisions", n)
    return 0


# ------------------------------------------------------------------ publish

def cmd_publish(args: argparse.Namespace) -> int:
    from schema import LocalRecordsPayload, LocalRecordSet
    adj = json.loads((WORK / "adjudicated.json").read_text())
    today = dt.date.today().isoformat()
    sites, held = [], 0
    for a in adj.values():
        keep = [f for f in a["facts"] if f["status"] in SHIPPED_STATUSES]
        held += len(a["facts"]) - len(keep)
        parcel = a.get("parcel")
        sites.append(LocalRecordSet.model_validate({
            "id": a["id"], "name": a["name"], "county": a.get("county"), "state": a.get("state"), "researched_at": today,
            "researchers": a["researchers"] or ["unrecorded"], "portals": a["portals"], "facts": keep,
            "gaps": a.get("gaps") or [], "parcel": parcel if parcel and parcel.get("status") else None}))
    payload = LocalRecordsPayload(generated_at=_now(), source=SOURCE_LABEL, count=len(sites),
                                  sites=sorted(sites, key=lambda s: s.id))
    OUTPUT.write_text(payload.model_dump_json(exclude_none=True, indent=None))
    log.info("%d sites, %d facts shipped, %d held back -> %s", len(sites), sum(len(s.facts) for s in sites), held, OUTPUT)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    adj = json.loads((WORK / "adjudicated.json").read_text())
    for a in adj.values():
        st = [f["status"] for f in a["facts"]]
        p = (a.get("parcel") or {}).get("status", "-")
        print(f"{a['id']:<18} {a['name'][:34]:<34} parcel:{p:<9} portals:{len(a['portals'])} facts:{len(st)} "
              f"(accepted {sum(st.count(x) for x in SHIPPED_STATUSES)}, rejected {st.count('rejected')}, disputed {st.count('disputed')})")
    return 0


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("queue"); q.add_argument("--batch-size", type=int, default=4); q.add_argument("--limit", type=int, default=None)
    q.add_argument("--per-screen", type=int, default=None, help="Only sites in the first N rows of any screen.")
    for name in ("parcels", "adjudicate", "apply-opus", "publish", "report"):
        sub.add_parser(name)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return {"queue": cmd_queue, "parcels": cmd_parcels, "adjudicate": cmd_adjudicate, "apply-opus": cmd_apply_opus,
            "publish": cmd_publish, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
