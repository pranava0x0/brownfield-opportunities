#!/usr/bin/env python3
"""Build docs/data/manufacturing-facilities.json from researched, verified rows.

Pipeline (validation-pipeline.md, "Manufacturing catalog"):

  1. Haiku researchers write data/validation/manufacturing/research/<topic>.json
     (brief: data/validation/manufacturing/RESEARCH_BRIEF.md).
  2. Sonnet verifiers re-open every source and write
     data/validation/manufacturing/verdicts/<topic>.json:
       {"topic", "verifier", "rows": [{"kind": "facility"|"requirement", "index",
         "source_url", "verdict": supported|unsupported|contradicted|unverifiable,
         "corrections": {field: value}, "reason"}]}
  3. `adjudicate` re-fetches every page, looks for the (corrected) quote, and
     applies local_records.decide(). Disputes are listed for Opus, whose
     decisions go in data/validation/manufacturing/opus.json
     ({"<topic>:<kind>:<index>": {"status": ..., "reason": ...}}).
  4. `build` keeps accepted rows, places each plant at its Census place point,
     validates against schema.ManufacturingCatalog and writes the catalog.

Usage:
  python3 scripts/manufacturing_catalog.py adjudicate
  python3 scripts/manufacturing_catalog.py build
  python3 scripts/manufacturing_catalog.py report
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from local_records import SHIPPED_STATUSES, code_check_for, decide, https_url  # noqa: E402

WORK = ROOT / "data" / "validation" / "manufacturing"
OUTPUT = ROOT / "docs" / "data" / "manufacturing-facilities.json"
TOPIC_SECTOR = {"robotics": "robotics", "turbine": "turbine", "transformer": "transformer",
                "minerals": "minerals", "doe_minerals": "minerals", "doe_awards": "minerals", "robotics2": "robotics", "transformer2": "transformer", "minerals2": "minerals"}
AWARD_TOPICS = {"doe_minerals", "doe_awards"}
CORRECTABLE = {"name", "company", "product", "status", "city", "state", "address", "investment_usd", "jobs", "acres",
               "announced", "doe_award", "brownfield", "former_use", "published", "quote", "source_title",
               "claim", "value", "factor"}
# Census place names carry a legal suffix; unincorporated places are absent.
PLACE_SUFFIXES = ("city", "town", "village", "CDP", "borough", "municipality", "city and borough",
                  "consolidated government (balance)", "metro government (balance)", "urban county", "")
# A plant in a place the Gazetteer does not list: the nearest listed place, disclosed in `locality`.
LOCALITY_OVERRIDES: dict[tuple[str, str], str] = {
    ("PA", "Lyndora"): "Homeacre-Lyndora",   # Census lists the combined CDP
}
# Researchers name factors freely; map the common synonyms onto the schema's list.
FACTOR_ALIASES = {"brownfield": "reuse", "site_reuse": "reuse", "existing_building": "reuse", "heavy_lift": "heavy_haul",
                  "electricity": "power", "natural_gas": "gas", "labor": "workforce", "jobs": "workforce", "logistics": "road",
                  "highway": "road", "incentives": "other", "funding": "other", "status": "other", "site": "land", "size": "land"}
log = logging.getLogger("manufacturing_catalog")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def load_topic(sub: str) -> dict[str, dict]:
    out = {}
    for p in sorted((WORK / sub).glob("*.json")):
        out[p.stem] = json.loads(p.read_text())
    return out


def row_key(topic: str, kind: str, index: int) -> str:
    return f"{topic}:{kind}:{index}"


def apply_corrections(row: dict, corrections: Optional[dict]) -> dict:
    out = dict(row)
    for k, v in (corrections or {}).items():
        if k in CORRECTABLE:
            out[k] = v
    return out


def adjudicate_rows(research: dict, verdicts: Optional[dict], check=None) -> list[dict]:
    """Every research row with its verdict, code check and decision. Pure except `check` (default: fetch the page)."""
    check = check or code_check_for
    by_index = {}
    for v in (verdicts or {}).get("rows", []):
        by_index[(v.get("kind"), v.get("index"))] = v
    out = []
    for kind, rows in (("requirement", research.get("requirements", [])), ("facility", research.get("facilities", []))):
        for i, raw in enumerate(rows):
            v = by_index.get((kind, i))
            # A verdict is bound to its row by index AND url: a reordered file must not borrow another row's verdict.
            if v and v.get("source_url") and https_url(v["source_url"]) != https_url(str(raw.get("source_url", ""))):
                v = None
            row = apply_corrections(raw, v.get("corrections") if v else None)
            row["source_url"] = https_url(str(row.get("source_url", "")))
            if not row["source_url"].startswith("https://") or len(str(row.get("quote") or "")) < 12:
                code = "dead"
            else:
                code = check(row["source_url"], str(row["quote"]))
            status, by = decide(code, v.get("verdict") if v else None)
            out.append({"kind": kind, "index": i, "row": row, "code_check": code,
                        "verifier": v.get("verdict") if v else None, "reason": (v or {}).get("reason"),
                        "status": status, "decided_by": by})
    return out


def cmd_adjudicate(args: argparse.Namespace) -> int:
    research, verdicts = load_topic("research"), load_topic("verdicts")
    opus = json.loads((WORK / "opus.json").read_text()) if (WORK / "opus.json").exists() else {}
    adjudicated, disputes = {}, []
    for topic, r in research.items():
        rows = adjudicate_rows(r, verdicts.get(topic))
        for a in rows:
            key = row_key(topic, a["kind"], a["index"])
            if a["status"] == "disputed" and key in opus:
                a["status"], a["decided_by"], a["reason"] = opus[key]["status"], "opus", opus[key].get("reason")
            # Opus may also strike a field a verifier accepted, when later evidence shows it is no longer true
            # (an award cancelled after the cited page). Only fields can be removed, never invented.
            for field in (opus.get(key) or {}).get("remove_fields", []):
                if a["row"].pop(field, None) is not None:
                    a["decided_by"], a["reason"] = "opus", opus[key].get("reason")
            if a["status"] == "disputed":
                disputes.append({"key": key, **a})
        adjudicated[topic] = rows
        counts = {}
        for a in rows:
            counts[a["status"]] = counts.get(a["status"], 0) + 1
        log.info("%-13s %s", topic, counts)
    (WORK / "adjudicated.json").write_text(json.dumps(adjudicated, indent=1, ensure_ascii=False) + "\n")
    (WORK / "disputes.json").write_text(json.dumps(disputes, indent=1, ensure_ascii=False) + "\n")
    log.info("%d disputes -> %s", len(disputes), WORK / "disputes.json")
    return 0


def _gazetteer() -> dict[tuple[str, str], tuple[float, float]]:
    from build_nickel_anchors import _load_gazetteer
    return _load_gazetteer()


def place_point(gaz: dict, city: str, state: str) -> Optional[tuple[str, tuple[float, float]]]:
    city = LOCALITY_OVERRIDES.get((state, city), city).strip()
    variants = {city, city.replace("Saint ", "St. "), city.replace("St. ", "Saint "), city.replace("Ft. ", "Fort ")}
    for name in variants:
        for suffix in PLACE_SUFFIXES:
            key = (state, f"{name} {suffix}".strip())
            if key in gaz:
                return key[1], gaz[key]
    return None


def _num(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def to_facility(sector: str, row: dict, status: str, gaz: dict, today: str) -> tuple[Optional[dict], Optional[str]]:
    city, state = str(row.get("city") or "").strip(), str(row.get("state") or "").strip().upper()
    if not city or not re.fullmatch(r"[A-Z]{2}", state):
        return None, "no city/state"
    hit = place_point(gaz, city, state)
    if hit is None:
        return None, f"no Census place for {city}, {state}"
    locality, (lat, lon) = hit
    award = row.get("doe_award") or row.get("federal_award")
    fa = None
    if isinstance(award, dict) and award.get("program"):
        fa = {"program": str(award["program"])[:200], "agency": str(award.get("agency") or "DOE")[:40],
              "amount_usd": _num(award.get("amount_usd"))}
    rec = {
        "id": f"MFG-{slug(sector + '-' + str(row.get('name')) + '-' + state)}",
        "sector": sector, "name": str(row.get("name") or "").strip()[:160],
        "company": row.get("company") or None, "product": (row.get("product") or None),
        "status": row.get("status"), "city": city, "state": state,
        "lat": round(lat, 5), "lon": round(lon, 5), "locality": locality,
        "investment_usd": _num(row.get("investment_usd")), "jobs": int(row["jobs"]) if _num(row.get("jobs")) is not None else None,
        "acres": _num(row.get("acres")) if (_num(row.get("acres")) or 0) > 0 else None,
        "announced": row.get("announced") or None, "federal_award": fa,
        "brownfield": row.get("brownfield") if isinstance(row.get("brownfield"), bool) else None,
        "former_use": row.get("former_use") or None, "source_url": row["source_url"],
        "source_title": (row.get("source_title") or None), "published": row.get("published") or None,
        "quote": str(row.get("quote")).strip()[:400], "check": status, "verified_at": today,
    }
    from schema import ManufacturingFacility
    try:
        return ManufacturingFacility.model_validate(rec).model_dump(exclude_none=True), None
    except Exception as exc:  # noqa: BLE001 - the reason is reported, the row held back
        return None, str(exc).splitlines()[0][:160] + " | " + str(exc).splitlines()[1][:120]


def to_requirement(sector: str, row: dict, status: str, today: str) -> tuple[Optional[dict], Optional[str]]:
    from schema import ManufacturingRequirement
    factor = str(row.get("factor") or "").strip().lower().replace("-", "_").replace(" ", "_")
    rec = {"sector": sector, "factor": FACTOR_ALIASES.get(factor, factor), "claim": str(row.get("claim") or "")[:300],
           "value": (str(row["value"])[:120] if row.get("value") else None), "source_url": row["source_url"],
           "source_title": row.get("source_title") or None, "published": row.get("published") or None,
           "quote": str(row.get("quote")).strip()[:400], "check": status, "verified_at": today}
    try:
        return ManufacturingRequirement.model_validate(rec).model_dump(exclude_none=True), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc).splitlines()[0][:160]


def plant_key(rec: dict) -> tuple:
    """Same sector, same town, same company (first word): one plant reported by two topics."""
    company = re.sub(r"[^a-z0-9 ]", "", str(rec.get("company") or rec.get("name") or "").lower()).split()
    return (rec["sector"], (company or [""])[0], rec["city"].lower(), rec["state"])


def cmd_build(args: argparse.Namespace) -> int:
    from schema import ManufacturingCatalog
    adjudicated = json.loads((WORK / "adjudicated.json").read_text())
    gaz, today = _gazetteer(), dt.date.today().isoformat()
    sites, reqs, held, seen, by_key, merged = [], [], 0, set(), {}, 0
    # Plant topics first, award topics last, so a plant's own page (status, reuse) is the row kept and
    # an award found separately is attached to it rather than replacing it.
    for topic, rows in sorted(adjudicated.items(), key=lambda kv: (kv[0] in AWARD_TOPICS, kv[0])):
        sector = TOPIC_SECTOR.get(topic)
        if sector is None:
            log.warning("unknown topic %s skipped", topic)
            continue
        for a in rows:
            if a["status"] not in SHIPPED_STATUSES:
                held += 1
                continue
            if a["kind"] == "requirement":
                rec, why = to_requirement(sector, a["row"], a["status"], today)
            else:
                rec, why = to_facility(sector, a["row"], a["status"], gaz, today)
                key = plant_key(rec) if rec else None
                if rec and (rec["id"] in seen or key in by_key):
                    # The same plant from two topics (a minerals row and a DOE-award row): keep the first
                    # and carry the award, with its own source, onto it.
                    first = by_key.get(key)
                    if first is not None and rec.get("federal_award") and not first.get("federal_award"):
                        first.update(federal_award=rec["federal_award"], award_source_url=rec["source_url"],
                                     award_quote=rec["quote"])
                        merged += 1
                    rec, why = None, "duplicate"
            if rec is None:
                held += 1
                log.info("held back %s:%s:%s — %s", topic, a["kind"], a["index"], why)
                continue
            if a["kind"] == "requirement":
                reqs.append(rec)
            else:
                seen.add(rec["id"])
                by_key[plant_key(rec)] = rec
                sites.append(rec)
    sites.sort(key=lambda r: (r["sector"], r["state"], r["name"]))
    payload = {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": "Researched (Claude Haiku 5.5), re-read (Claude Sonnet 5.5), quote re-fetched by code; "
                         "plant points are 2024 Census Gazetteer place points",
               "count": len(sites), "sites": sites, "requirements": reqs, "held_back": held}
    ManufacturingCatalog.model_validate(payload)
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s: %d plants, %d requirements, %d held back, %d awards merged onto existing plants",
             OUTPUT, len(sites), len(reqs), held, merged)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cat = json.loads(OUTPUT.read_text())
    by = {}
    for s in cat["sites"]:
        by.setdefault(s["sector"], []).append(s)
    for sector, rows in sorted(by.items()):
        print(f"{sector}: {len(rows)} plants, {sum(1 for r in cat['requirements'] if r['sector'] == sector)} requirements")
        for r in rows:
            print(f"   {r['status']:18} {r['name'][:60]:60} {r['city']}, {r['state']}")
    return 0


MEMO = ROOT / "research" / "manufacturing-siting-2026-11.md"
SECTOR_HEADING = {"robotics": "Robotics", "turbine": "Gas turbines", "transformer": "Transformers",
                  "minerals": "Critical minerals"}


def _usd(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"${v / 1e9:.2f}B" if v >= 1e9 else f"${v / 1e6:.0f}M"


def cmd_memo(args: argparse.Namespace) -> int:
    """Write the research memo's generated sections from the shipped catalog and screens.js."""
    import subprocess
    cat = json.loads(OUTPUT.read_text())
    screens = json.loads(subprocess.run(
        ["node", "-e", "const S=require(process.argv[1]);process.stdout.write(JSON.stringify(Object.fromEntries("
         "['robotics','turbine','transformer','minerals'].map(k=>[k,{method:S.SCREENS[k].method,criteria:S.SCREENS[k].criteria.map(c=>({label:c.label,rule:c.rule,kind:c.kind,note:c.note||''}))}]))))",
         str(ROOT / "docs" / "screens.js")], capture_output=True, text=True, check=True).stdout)
    intro = (MEMO.read_text().split("<!-- generated below -->")[0] if MEMO.exists() else "# Manufacturing siting\n\n")
    out = [intro.rstrip() + "\n\n<!-- generated below -->\n"]
    for sector, heading in SECTOR_HEADING.items():
        out.append(f"\n## {heading}\n\n{screens[sector]['method']}\n\n**Checks**\n")
        for c in screens[sector]["criteria"]:
            out.append(f"- {c['label']} (`{c['rule']}`, {'agency' if c['kind'] == 'R' else 'ours'}). {c['note']}".rstrip())
        reqs = [r for r in cat["requirements"] if r["sector"] == sector]
        out.append("\n**What built plants show** (quotes are verbatim from the linked page)\n")
        for r in reqs:
            out.append(f"- {r['factor'].replace('_', ' ')}: {r['claim']} — \"{r['quote']}\" ([source]({r['source_url']}))")
        if not reqs:
            out.append("- No requirement statement passed verification.")
        out.append("\n**Plants**\n\n| Plant | Place | Status | Investment | Federal award | Source |\n|---|---|---|---|---|---|")
        for f in [s for s in cat["sites"] if s["sector"] == sector]:
            award = f"{f['federal_award']['agency']} {_usd(f['federal_award'].get('amount_usd'))}".strip() if f.get("federal_award") else ""
            out.append(f"| {f['name']} | {f['city']}, {f['state']} | {f['status'].replace('_', ' ')} | {_usd(f.get('investment_usd'))} "
                       f"| {award} | [link]({f['source_url']}) |")
    MEMO.write_text("\n".join(out) + "\n")
    log.info("wrote %s", MEMO)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("adjudicate", "build", "report", "memo"):
        sub.add_parser(name)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return {"adjudicate": cmd_adjudicate, "build": cmd_build, "report": cmd_report, "memo": cmd_memo}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
