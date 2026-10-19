#!/usr/bin/env python3
"""Find reported site acreages that cannot describe a single site.

Two deterministic tests, both offline:

  county_outline  acreage >= 50% of the county that contains the site point.
                  EPA draws some Superfund boundaries as the whole county or
                  watershed (Tar Creek: 310,173 ac vs ~25,600 ac per Oklahoma
                  DEQ), and the site point is then the county center.
  region          acreage > 100,000 ac. WWII FUDS "maneuver areas" were
                  training regions, not parcels.
  water_or_plume  a Superfund site whose name says the polygon is a river,
                  lake, harbor, groundwater plume or well field (Hudson River
                  PCBs, Griggs & Walnut Ground Water Plume). Its area measures
                  contamination, not developable land. Names that also name a
                  facility or a federal installation are not flagged.

Flagged acreage is treated as unknown by the siting screens (docs/screens.js)
and noted in the detail panel. Nothing here edits a source value.

Usage:
  python3 scripts/check_acreage_artifacts.py            # table of flagged sites
  python3 scripts/check_acreage_artifacts.py --json     # id -> flag mapping
  python3 scripts/check_acreage_artifacts.py --write    # docs/data/acreage-flags.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connectors.county_lookup import CountyIndex  # noqa: E402
from connectors.geom import polygon_acreage  # noqa: E402

DATA = ROOT / "docs" / "data"
PROGRAM_FILES = ["superfund-npl.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json"]
COUNTY_SHARE = 0.5        # site claims half its county or more
REGION_ACRES = 100_000    # larger than any single industrial or military parcel we screen for
# Name tests for Superfund polygons that trace water or a plume (see docstring).
PLUME_WORDS = re.compile(r"\b(GROUND ?WATER|GW|PLUMES?|AQUIFER|SEDIMENTS?|WELLS?|WELL ?FIELD|WELLFIELD|NRDA|CONTAMINATION|CONTAMINATED)\b")
# A water word counts only as the name's head noun: last in the name, before
# punctuation, or before a word that keeps it a place ("HUDSON RIVER PCBS",
# "LOWER DARBY CREEK AREA"). "PACIFIC SOUND RESOURCES" and "RIVER CITY METAL
# FINISHING" are companies, not water bodies.
WATER_WORDS = re.compile(r"\b(RIVERS?|CREEK|LAKE|BAY|HARBOR|HARBOUR|CANAL|RESERVOIR|ESTUARY|WATERWAY|SOUND)\b"
                         r"(?=\s*($|[,/&()\-]|(SITE|AREA|SEDIMENTS?|PCBS?|BASIN|SYSTEM|AND)\b))")
FACILITY_WORDS = re.compile(r"\b(PLANT|CORP|CORPORATION|CO|INC|COMPANY|MILLS?|LANDFILL|MGP|PIT|SMELTER|WORKS|FACILITY|"
                            r"DEPOT|DUMP|DRUM|SALVAGE|STATION|YARD|FOUNDRY|LAB|LABORATORY|TERMINAL|AIRPORT|REFINERY|SHIPBUILDING|SHIPYARD)\b")
FEDERAL_WORDS = re.compile(r"\b(USDOE|USAF|USN|USARMY|USNAVY|NAVAL|NAS|AFB|AIR FORCE|ARMY|MARINE|ARSENAL|BASE|COMPLEX)\b")


def names_water_or_plume(name: str) -> bool:
    n = (name or "").upper()
    if FEDERAL_WORDS.search(n):
        return False
    if PLUME_WORDS.search(n):
        return True
    return bool(WATER_WORDS.search(n)) and not FACILITY_WORDS.search(n)


def load_sites() -> list[dict]:
    sites = []
    for name in PROGRAM_FILES:
        path = DATA / name
        if path.exists():
            sites += json.loads(path.read_text())["sites"]
    return sites


def acreage_flags(sites: list[dict], counties: CountyIndex) -> dict[str, dict]:
    """Return {site_id: {flag, acreage, county, county_acres, share}} for flagged sites."""
    area_cache: dict[tuple[str, str | None], float | None] = {}
    flags = {}
    for s in sites:
        acres = s.get("acreage")
        lat, lon = s.get("lat_real", s.get("lat")), s.get("lon_real", s.get("lon"))
        if not isinstance(acres, (int, float)) or acres <= 0 or lat is None or lon is None:
            continue
        hit = counties.lookup_polygon(lat, lon, s.get("state"))
        county_acres = None
        if hit:
            # Whole county, all components: one island of the Aleutians East
            # Borough is not the borough.
            key = (hit[0], hit[1])
            if key not in area_cache:
                parts = [polygon_acreage([[list(p) for p in ring] for ring in poly])
                         for poly in counties.county_polygons(*key)]
                area_cache[key] = sum(a for a in parts if a) or None
            county_acres = area_cache[key]
        share = acres / county_acres if county_acres else None
        flag = None
        if s.get("program") == "superfund" and names_water_or_plume(s.get("name")):
            flag = "water_or_plume"
        # Federal reservations legitimately span counties (Savannah River Site
        # covers parts of three), so only the region rule applies to them.
        elif share is not None and share >= COUNTY_SHARE and not FEDERAL_WORDS.search((s.get("name") or "").upper()):
            flag = "county_outline"
        elif acres > REGION_ACRES:
            flag = "region"
        if flag:
            flags[s["id"]] = {
                "flag": flag,
                "acreage": acres,
                "county": f"{hit[0]}, {hit[1]}" if hit else None,
                "county_acres": county_acres,
                "share": round(share, 2) if share is not None else None,
            }
    return flags


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="print the id -> flag mapping as JSON")
    ap.add_argument("--write", action="store_true", help="write docs/data/acreage-flags.json for the website")
    args = ap.parse_args()
    counties = CountyIndex.from_path(DATA / "us-counties-topo.json")
    sites = load_sites()
    flags = acreage_flags(sites, counties)
    if args.write:
        out = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source": "scripts/check_acreage_artifacts.py",
            "rule": (f"water_or_plume: Superfund name describes water or a groundwater plume; "
                     f"county_outline: acreage >= {COUNTY_SHARE:.0%} of the containing county; region: acreage > {REGION_ACRES:,} ac"),
            "count": len(flags),
            "sites": [{"id": k, "acreage_flag": v["flag"], "acreage_flag_county": v["county"], "acreage_flag_share": v["share"]}
                      for k, v in sorted(flags.items())],
        }
        (DATA / "acreage-flags.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
        print(f"wrote {len(flags)} flags to docs/data/acreage-flags.json")
        return 0
    if args.json:
        print(json.dumps(flags, indent=1, sort_keys=True))
        return 0
    names = {s["id"]: s.get("name", "") for s in sites}
    print(f"{len(flags)} of {len(sites)} sites flagged")
    for sid, f in sorted(flags.items(), key=lambda kv: -kv[1]["acreage"]):
        share = f"{f['share']:.0%}" if f["share"] is not None else "n/a"
        print(f"{f['flag']:<15} {sid:<20} {f['acreage']:>12,.0f} ac  {share:>6} of {f['county'] or '?'}  {names[sid][:45]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
