#!/usr/bin/env python3
"""Census places of 25,000 or more people, with coordinates.

10 CFR 100.3 defines a "population center distance" from the reactor to the
nearest densely populated center of about 25,000 residents. The nuclear screens
use the distance to the nearest such place as a first check (the real test also
needs the low-population-zone radius, so it is labelled a proxy).

Sources (both Census Bureau, no key):
  - Vintage 2024 population estimates for incorporated places (sub-est2024.csv,
    summary level 162)
  - 2024 Gazetteer place file for the internal point of each place

Census-designated places (unincorporated) are not in the estimates file, so
a few large suburbs are missed; the screen says so.

  python3 scripts/build_population_centers.py     # writes docs/data/population-centers.json
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "docs" / "data" / "population-centers.json"
POP_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/cities/totals/sub-est2024.csv"
GAZ_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip"
GAZ_CACHE = CACHE / "census_gazetteer_place_2024.txt"   # shared with build_nickel_anchors.py
POP_CACHE = CACHE / "census_sub_est2024.csv"
MIN_POP = 25_000
USER_AGENT = "brownfield-opportunities/population-centers (census.gov popest)"


def fetch(url: str, path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    path.write_bytes(data)
    return data


def main() -> int:
    if not GAZ_CACHE.exists():
        raise SystemExit(f"missing {GAZ_CACHE}; run scripts/build_nickel_anchors.py first (it caches the Gazetteer)")
    coords = {}
    for row in csv.DictReader(io.StringIO(GAZ_CACHE.read_text()), delimiter="\t"):
        row = {k.strip(): v.strip() for k, v in row.items()}
        coords[row["GEOID"]] = (float(row["INTPTLAT"]), float(row["INTPTLONG"]), row["USPS"])
    text = fetch(POP_URL, POP_CACHE).decode("latin-1")
    places, missing = [], 0
    for row in csv.DictReader(io.StringIO(text)):
        if row["SUMLEV"] != "162":
            continue
        pop = int(row["POPESTIMATE2024"])
        if pop < MIN_POP:
            continue
        geoid = row["STATE"] + row["PLACE"]
        if geoid not in coords:
            missing += 1
            continue
        lat, lon, usps = coords[geoid]
        places.append({"geoid": geoid, "name": row["NAME"], "state": usps, "pop_2024": pop, "lat": lat, "lon": lon})
    places.sort(key=lambda p: -p["pop_2024"])
    OUT.write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "US Census Bureau Vintage 2024 place estimates + 2024 Gazetteer",
        "source_url": POP_URL,
        "rule": f"incorporated places with 2024 population >= {MIN_POP:,}",
        "count": len(places),
        "places": places,
    }, separators=(",", ":")) + "\n")
    print(f"wrote {len(places)} places (>= {MIN_POP:,}); {missing} without a Gazetteer point")
    return 0


def nearest_center(lat: float, lon: float, places: list[dict] | None = None) -> dict | None:
    """Nearest place of 25,000+ to (lat, lon): {name, state, pop_2024, mi}. Haversine."""
    import math
    if places is None:
        places = json.loads(OUT.read_text())["places"]
    best = None
    for p in places:
        p1, p2 = math.radians(lat), math.radians(p["lat"])
        a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(p["lon"] - lon) / 2) ** 2
        mi = 3958.8 * 2 * math.asin(math.sqrt(a))
        if best is None or mi < best["mi"]:
            best = {"name": p["name"], "state": p["state"], "pop_2024": p["pop_2024"], "mi": round(mi, 1)}
    return best


if __name__ == "__main__":
    sys.exit(main())
