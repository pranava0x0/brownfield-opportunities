#!/usr/bin/env python3
"""List the sites the technology-specific tabs actually show.

Every later validation step (live re-measurement, local-records research, the
verify map) works from this one manifest, so a run is reproducible and
`--top` is the only knob on cost.

A site is "in a tab" when it is
  * in the first N rows of a corpus screen (dc, solar, port, nickel), or
  * the cleanup record joined to a retired-industry row (tracked_site_*), or
  * a brownfield listed beside a civilian nuclear site.

Output: data/validation/tab-sites.json
  {"generated_at", "top", "corpus_sites": [...], "overlay_sites": [...]}

Usage:
  python3 scripts/tab_sites.py --top 10
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
OUT = ROOT / "data" / "validation" / "tab-sites.json"
CORPUS_SCREENS = ("dc", "solar", "port", "nickel")
OVERLAY_SCREENS = {"ap1000": "ap1000", "smr": "ap1000", "micro": "ap1000",
                   "civilian": "civilian", "coal": "coal", "retired": "retired"}
SITE_FIELDS = ("id", "program", "name", "address", "city", "county", "state", "zip", "lat", "lon",
               "acreage", "parcel_acreage", "current_owner", "current_owner_source", "parcel_id")

log = logging.getLogger("tab_sites")


def screen_top(key: str, n: int) -> list[dict]:
    proc = subprocess.run(["node", str(ROOT / "scripts" / "screen.js"), "top", key, str(n), "--json"],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"screen.js top {key} failed: {proc.stderr[:300]}")
    return json.loads(proc.stdout)


def corpus_index() -> dict[str, dict]:
    """Program record with the parcel-owner join filled in where empty."""
    index: dict[str, dict] = {}
    for fname in ("sites.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json"):
        for rec in json.loads((DATA / fname).read_text())["sites"]:
            index.setdefault(rec["id"], dict(rec))
    for rec in json.loads((DATA / "parcel-owner.json").read_text())["sites"]:
        target = index.get(rec["id"])
        if target is None:
            continue
        for k, v in rec.items():
            if k not in ("id", "program") and v is not None and target.get(k) is None:
                target[k] = v
    return index


def build(top: int) -> dict:
    index = corpus_index()
    corpus: dict[str, dict] = {}

    def add(site_id: str, tab: str, rank: int | None = None, via: str | None = None) -> None:
        rec = index.get(site_id)
        if rec is None:
            log.warning("tab references unknown corpus id %s (%s)", site_id, tab)
            return
        entry = corpus.setdefault(site_id, {**{k: rec.get(k) for k in SITE_FIELDS}, "tabs": []})
        entry["tabs"].append({"tab": tab, "rank": rank, "via": via})

    for key in CORPUS_SCREENS:
        for row in screen_top(key, top):
            add(row["site"]["id"], key, row["rank"])

    overlay: list[dict] = []
    for key in ("retired", "coal", "civilian", "ap1000"):
        for row in screen_top(key, top if key != "ap1000" else 14):
            s = row["site"]
            overlay.append({"screen": key, "rank": row["rank"], "id": s["id"], "name": s.get("name"),
                            "state": s.get("state"), "lat": s.get("lat"), "lon": s.get("lon"),
                            "county": s.get("county"), "met": row["ev"]["met"], "total": row["ev"]["total"]})
            if key == "retired" and s.get("tracked_site_id"):
                add(s["tracked_site_id"], "retired", row["rank"], via=s["id"])

    # Brownfields listed beside the top civilian nuclear sites.
    nuc_top = {o["id"] for o in overlay if o["screen"] == "civilian"}
    prox = json.loads((DATA / "nuclear-brownfield-proximity.json").read_text())["records"]
    for rec in prox:
        if rec["nuclear_site_id"] in nuc_top:
            for nb in rec["nearby_brownfields"][:3]:
                add(nb["id"], "civilian", via=rec["nuclear_site_id"])
    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "top": top, "corpus_sites": sorted(corpus.values(), key=lambda s: s["id"]),
            "overlay_sites": overlay}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=10, help="Rows per screen.")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    manifest = build(args.top)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    log.info("%d corpus sites, %d overlay rows -> %s", len(manifest["corpus_sites"]),
             len(manifest["overlay_sites"]), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
