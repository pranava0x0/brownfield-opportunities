#!/usr/bin/env python3
"""Build docs/data/nickel-anchors.json — the US nickel supply-chain catalog.

What this is
------------
A curated catalog of the places that make a nickel refinery site good or bad:
where the feedstock is, where the offtake is, where bulk sulfuric acid comes
from, and the one site in the country that has actually been a nickel refinery
before. The `nickel-anchor-proximity` connector distance-joins it onto all
46,759 corpus sites; docs/nickel-score.js scores against those distances.

An OVERLAY like coal-conversions.json, NOT a SiteRecord set — it stays out of
schema.py's Payload pipeline, but every row IS validated against
schema.NickelAnchor here and again in CI.

Why curated
-----------
There is no authoritative public GIS layer of US mineral processing plants.
The USGS "Active Mines and Mineral Processing Plants" dataset is a 2003 layer
package, and the ArcGIS-Online search for a live equivalent returns only
third-party storymap copies (probed 2026-09-08, data-source-research.md §34).
So this follows the coal-conversions contract: per-row citation plus a
verified_at date, re-audited on a quarterly cadence.

Coordinates: two tiers, and the distinction is enforced
-------------------------------------------------------
`site` rows carry a lat/lon from a source that located that specific facility.
`locality` rows carry the **Census Gazetteer internal point** for a named
place, fetched live from the 2024 national place file — good to a few miles.

The tiering exists because the alternative was typing town coordinates from
memory, which is fabrication wearing a plausible number's clothing. A demand
centre 500 miles away does not need site precision; it needs an honest label
saying it does not have it. `coord_precision` carries that label and
schema.NickelAnchor forbids omitting it.

Re-run: `python3 scripts/build_nickel_anchors.py`
"""
from __future__ import annotations

import io
import json
import logging
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema import NickelAnchor  # noqa: E402

log = logging.getLogger("build_nickel_anchors")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_PATH = ROOT / "docs" / "data" / "nickel-anchors.json"
CACHE = ROOT / "data" / "cache" / "census_gazetteer_place_2024.txt"
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
    "2024_Gaz_place_national.zip"
)
USER_AGENT = "brownfield-opportunities/nickel-anchors (census.gov gazetteer)"

# Curated rows. `lat`/`lon` present => site precision, and the source_url must
# be the thing that located it. `locality` present => resolved from the
# gazetteer below. Never both.
ANCHORS: list[dict] = [
    # --- Feedstock: the only US primary nickel mine, and its mill ----------
    {
        "id": "NIA-eagle-mine", "name": "Eagle Mine", "kind": "feedstock_mine",
        "state": "MI", "lat": 46.746, "lon": -87.881, "coord_precision": "site",
        "status": "Operating (Talon Metals, acquired January 2026)",
        "note": "The only operating primary nickel-copper mine in the United "
                "States. Its concentrate currently leaves the country to be "
                "smelted at Sudbury, Ontario — the gap a domestic refinery "
                "would close.",
        "source_url": "https://talonmetals.com/talon-metals-completes-previously-announced-acquisition-of-lundin-minings-eagle-mine-and-humboldt-mill-operations-creating-a-multi-asset-u-s-nickel-copper-company/",
    },
    {
        "id": "NIA-humboldt-mill", "name": "Humboldt Mill", "kind": "feedstock_mine",
        "state": "MI", "lat": 46.484, "lon": -87.898, "coord_precision": "site",
        "status": "Operating; a candidate processing site in Talon's own review",
        "note": "Eagle Mine's concentrator, on a Cleveland-Cliffs iron-ore "
                "brownfield, rail-served by a CN spur. Talon was reported in "
                "July 2026 to be weighing a Michigan processing facility here "
                "against its North Dakota site.",
        "source_url": "https://kfgo.com/2026/07/28/plans-for-north-dakota-nickel-processing-unclear-as-company-also-evaluates-michigan-site-2/",
    },
    {
        "id": "NIA-tamarack", "name": "Tamarack nickel-copper project",
        "kind": "feedstock_mine", "state": "MN", "locality": "Tamarack city",
        "coord_precision": "locality",
        "status": "Environmental review; scoping comment period Jul–Sep 2026",
        "note": "The most advanced US nickel sulfide deposit in permitting. "
                "Talon holds a Tesla agreement for 75,000 t of concentrate.",
        "source_url": "https://www.dnr.state.mn.us/input/environmentalreview/tamarack-nickel-project.html",
    },
    {
        "id": "NIA-madison-mine", "name": "Madison Mine (US Strategic Metals)",
        "kind": "feedstock_mine", "state": "MO", "lat": 37.560, "lon": -90.294,
        "coord_precision": "site",
        "status": "Operating; hydrometallurgical facility near completion",
        "note": "1,800-acre cobalt-nickel-copper site 90 miles south of "
                "St. Louis, producing concentrate since 2019 with a "
                "hydrometallurgical facility near completion.",
        "source_url": "https://www.prnewswire.com/news-releases/missouri-cobalt-nears-completion-of-key-facility-advancing-its-leadership-goal-in-domestic-battery-grade-cobalt-and-nickel-301323342.html",
    },
    {
        "id": "NIA-warren-union", "name": "Warren/Union nickel deposit (Exiro)",
        "kind": "feedstock_mine", "state": "ME", "lat": 44.191, "lon": -69.245,
        "coord_precision": "site",
        "status": "Exploration, apparently stalled since 2023; organised local opposition",
        "note": "Nickel-copper-cobalt sulfide around Crawford Pond. No public "
                "grade or tonnage. Maine's Chapter 200 rules constrain the "
                "mine but explicitly do not reach a refinery.",
        "source_url": "https://www.bangordailynews.com/2023/02/27/midcoast/exiro-mining-warren-union/",
    },
    # --- Feedstock: recycled ------------------------------------------------
    {
        "id": "NIA-rev-nickel", "name": "REV Nickel (Revex Technologies)",
        "kind": "feedstock_recycled", "state": "MI", "locality": "Ishpeming city",
        "coord_precision": "locality",
        "status": "Awarded; $398M project",
        "note": "Reprocesses Eagle Mine tailings and spent lithium-ion "
                "batteries into nickel concentrate. $145M DOE grant plus $50M "
                "from Michigan — the state has already co-funded nickel "
                "processing in Marquette County.",
        "source_url": "https://www.uppermichiganssource.com/2025/03/10/revex-technologies-receives-145m-grant-production-critical-minerals/",
    },
    # --- Refineries: planned ------------------------------------------------
    {
        "id": "NIA-westwin-lawton", "name": "Westwin Elements nickel refinery",
        "kind": "refinery_planned", "state": "OK", "locality": "Lawton city",
        "coord_precision": "locality",
        "status": "Pilot operating; Phase 1 target 18,000 t/yr by 2028",
        "note": "The most advanced dedicated US nickel refinery. 480-acre "
                "tract in a rail industrial park — the landlocked, rail-fed "
                "counterpart to the port-fed model.",
        "source_url": "https://www.fastmarkets.com/insights/first-us-nickel-refinery-westwin-elements-enters-1-4-billion-offtake-agreements-with-traxys/",
    },
    {
        "id": "NIA-beulah-bmpf", "name": "Talon Battery Minerals Processing Facility",
        "kind": "refinery_planned", "state": "ND", "locality": "Beulah city",
        "coord_precision": "locality",
        "status": "Permitting; construction targeted 2027",
        "note": "$114.8M DOE award on a former Westmoreland coal mine. Talon "
                "sited processing away from its Minnesota mine explicitly to "
                "narrow the mine's environmental review — legacy-industrial "
                "reuse used as permitting strategy.",
        "source_url": "https://talonmetals.com/talon-metals-battery-minerals-processing-facility-selected-by-us-department-of-energy-for-114-million-in-bipartisan-infrastructure-law-funding/",
    },
    # --- Refinery: historic, and the reuse precedent ------------------------
    {
        "id": "NIA-port-nickel", "name": "Port Nickel (former AMAX Metals Recovery)",
        "kind": "refinery_historic", "state": "LA", "lat": 29.858, "lon": -89.963,
        "coord_precision": "site",
        "status": "387-acre tract for sale or lease, listed as of 2026-07-19",
        "note": "Built by Freeport Sulphur to refine Moa Bay ore and run as a "
                "nickel-cobalt refinery from 1958 to 2000. Deep-water "
                "Mississippi dock, Norfolk Southern on an active on-site spur "
                "with reciprocal switching, Foreign Trade Zone, in the Gulf "
                "Coast sulfuric-acid supply region.",
        "source_url": "https://www.epa.gov/system/files/documents/2025-05/amax-metals-ready-for-reuse-determination.pdf",
    },
    # --- Demand -------------------------------------------------------------
    {
        "id": "NIA-nas-ghent", "name": "North American Stainless, Ghent",
        "kind": "demand_stainless", "state": "KY", "locality": "Ghent city",
        "coord_precision": "locality", "status": "Operating; expanding",
        "note": "The largest integrated US stainless producer, on a 1,400-acre "
                "Ohio River site. Stainless is the majority of world nickel "
                "demand, though this mill runs heavily on scrap.",
        "source_url": "https://www.ky71alliance.com/news-center/p/item/48606/north-american-stainlesss-kentucky-operation-to-grow-with-expansion-and-job-opportunities",
    },
    {
        "id": "NIA-ultium-spring-hill", "name": "Ultium Cells, Spring Hill",
        "kind": "demand_battery", "state": "TN", "locality": "Spring Hill city",
        "coord_precision": "locality", "status": "Operating",
        "note": "Cell plant in the Tennessee node of the battery corridor "
                "Electra names as a siting driver.",
        "source_url": "https://news.gm.com/home.detail.html/Pages/news/us/en/2025/jul/0714-Tennessee-Michigan-battery-powered-future.html",
    },
    {
        "id": "NIA-ultium-warren", "name": "Ultium Cells, Warren",
        "kind": "demand_battery", "state": "OH", "locality": "Warren city",
        "coord_precision": "locality", "status": "Operating",
        "note": "The Ohio Valley anchor of the same corridor.",
        "source_url": "https://news.gm.com/home.detail.html/Pages/news/us/en/2025/jul/0714-Tennessee-Michigan-battery-powered-future.html",
    },
    {
        "id": "NIA-blueoval-glendale", "name": "BlueOval SK, Glendale",
        "kind": "demand_battery", "state": "KY", "locality": "Elizabethtown city",
        "coord_precision": "locality", "status": "Operating",
        "note": "Ford/SK cell plant at Glendale, Hardin County. Glendale is unincorporated and absent from the Census place file, so this row carries the Elizabethtown internal point ~10 mi away — locality precision, and the note is the disclosure.",
        "source_url": "https://www.ky71alliance.com/news-center/p/item/48606/north-american-stainlesss-kentucky-operation-to-grow-with-expansion-and-job-opportunities",
    },
    # --- Bulk sulfuric acid -------------------------------------------------
    {
        "id": "NIA-acid-mulberry", "name": "Central Florida phosphate acid complex",
        "kind": "reagent_acid", "state": "FL", "locality": "Mulberry city",
        "coord_precision": "locality", "status": "Operating",
        "note": "Bulk sulfuric acid in the US comes mainly from the Florida "
                "and Louisiana phosphate-fertilizer complexes. A hydromet "
                "refinery either buys acid here or burns sulfur on site.",
        "source_url": "https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-sulfur.pdf",
    },
    {
        "id": "NIA-acid-garfield", "name": "Kennecott Garfield smelter acid plant",
        "kind": "reagent_acid", "state": "UT", "locality": "Magna metro township",
        "coord_precision": "locality", "status": "Operating",
        "note": "One of two operating US copper smelters; its acid plant is a "
                "byproduct sulfuric acid source.",
        "source_url": "https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-sulfur.pdf",
    },
    {
        "id": "NIA-acid-miami-az", "name": "Freeport-McMoRan Miami smelter acid plant",
        "kind": "reagent_acid", "state": "AZ", "locality": "Miami town",
        "coord_precision": "locality", "status": "Operating",
        "note": "The other operating US copper smelter, and the other "
                "byproduct acid source in the West.",
        "source_url": "https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-sulfur.pdf",
    },
]

VERIFIED_AT = "2026-09-08"


def _load_gazetteer() -> dict[tuple[str, str], tuple[float, float]]:
    """{(state, place name): (lat, lon)} from the Census place gazetteer."""
    if CACHE.exists():
        text = CACHE.read_text()
    else:
        req = urllib.request.Request(GAZETTEER_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            blob = resp.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".txt"))
            text = zf.read(name).decode("utf-8", errors="replace")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(text)
        log.info("cached Census gazetteer (%d KB)", len(text) // 1024)

    out: dict[tuple[str, str], tuple[float, float]] = {}
    lines = text.splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    ix = {h: i for i, h in enumerate(header)}
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) <= ix["INTPTLONG"]:
            continue
        try:
            key = (parts[ix["USPS"]].strip(), parts[ix["NAME"]].strip())
            out[key] = (float(parts[ix["INTPTLAT"]]), float(parts[ix["INTPTLONG"]]))
        except (ValueError, IndexError):
            continue
    return out


def build() -> int:
    gaz = _load_gazetteer()
    rows: list[dict] = []
    for raw in ANCHORS:
        row = dict(raw)
        has_site = "lat" in row and "lon" in row
        has_locality = "locality" in row
        if has_site == has_locality:
            log.error("%s: needs exactly one of explicit lat/lon or locality", row["id"])
            return 1
        if has_locality:
            key = (row["state"], row["locality"])
            hit = gaz.get(key)
            if hit is None:
                log.error("%s: gazetteer has no place %r in %s",
                          row["id"], row["locality"], row["state"])
                return 1
            row["lat"], row["lon"] = round(hit[0], 5), round(hit[1], 5)
        row["verified_at"] = VERIFIED_AT
        rows.append(NickelAnchor.model_validate(row).model_dump())

    rows.sort(key=lambda r: (r["kind"], r["id"]))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "Curated from research/nickel-*-2026-09.md; locality "
                  "coordinates from the 2024 Census Gazetteer place file",
        "source_url": GAZETTEER_URL,
        "count": len(rows),
        "sites": rows,
    }
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s (%d anchors)", OUT_PATH, len(rows))
    for r in rows:
        log.info("  %-22s %-18s %s (%s)", r["id"], r["kind"],
                 f'{r["lat"]},{r["lon"]}', r["coord_precision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
