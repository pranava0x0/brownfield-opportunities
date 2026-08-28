#!/usr/bin/env python3
"""Build docs/data/shipyards.json — a curated map overlay of major US
heavy-shipbuilding / fabrication yards.

Why this matters
-----------------
A floating or offshore-moored nuclear plant (the Akademik Lomonosov pattern,
or a US barge-mounted SMR concept) has to be assembled, outfitted, and
launched somewhere with a graving dock or heavy-lift crane rated for
reactor-scale modules — the same capability the offshore oil & gas industry
uses to build platform topsides. That capability is concentrated in a small
number of US yards; most of the country's ~150 active shipyards (MARAD's own
count) build much smaller vessels and aren't candidates.

Why curated, not connector-fetched
-----------------------------------
No public GIS layer of US shipyards exists. MARAD's Office of Shipyards &
Marine Engineering publishes an annual PDF survey, not a geodata service
(confirmed 2026-08-27 — see the port-proximity research note in
data-source-research.md). This follows the reference-campuses.json /
coal-conversions.json curated-provenance contract: every row carries
`source_url` (verified resolving, curl-checked 2026-08-27) + `verified_at`.
Coordinates are facility- or city-approximate (`coord_note` says which) —
these are all large waterfront properties, so ±0.01° is well inside the
property boundary for the proximity join's purposes.

`capability` drives the offshore-nuclear scoring lens in
docs/maritime-score.js: `heavy_module` (offshore module/topsides fabrication
— a graving dock or heavy-lift crane rated for reactor-scale modules) is the
capability actually analogous to floating-reactor assembly; `large_hull` is
general new-construction shipbuilding (naval or commercial hulls, not
necessarily heavy modules); `naval_repair` is drydock/overhaul capacity
without new-construction fabrication.

Output is an OVERLAY (like reference-campuses.json), NOT a SiteRecord set —
it stays out of the schema.py / refresh.py Payload pipeline and is
lazy-loaded by the frontend. Validated against schema.Shipyard so a curated
typo fails loud at build time, same as the coal-conversions catalog.

Re-run: `python3 scripts/build_shipyards.py` (re-audit citations annually —
shipyard ownership/capability changes slowly but does change, e.g. Austal
USA's ownership, VT Halter's sale to Bollinger).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schema import Shipyard  # noqa: E402

log = logging.getLogger("build_shipyards")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUT_PATH = ROOT / "docs" / "data" / "shipyards.json"

VERIFIED = "2026-08-27"

# Curated benchmark of major US shipyards capable of large hull or heavy
# offshore-module construction. Every source_url was curl-checked 200 on
# 2026-08-27. Coordinates are facility-approximate (waterfront property
# center), not surveyed.
SHIPYARDS: list[dict] = [
    {
        "id": "kiewit-offshore-ingleside",
        "name": "Kiewit Offshore Services",
        "operator": "Kiewit Corporation",
        "city": "Ingleside", "state": "TX",
        "lat": 27.8500, "lon": -97.2080,
        "coord_note": "Facility-approximate (2440 Kiewit Rd, on Corpus Christi Bay).",
        "capability": "heavy_module",
        "note": "400-acre deepwater fabrication yard; houses the largest onshore "
                "lifting device in the Western Hemisphere (12,500-ton rated "
                "capacity) — builds offshore platform hulls/topsides (Appomattox, "
                "Jack & St. Malo). The single most directly analogous US "
                "capability to floating-reactor module assembly.",
        "source_url": "https://clui.org/ludb/site/kiewit-offshore-services-ingleside-yard",
        "verified_at": VERIFIED,
    },
    {
        "id": "gulf-island-fabrication-houma",
        "name": "Gulf Island Fabrication — Houma Facility",
        "operator": "Gulf Island Fabrication, Inc.",
        "city": "Houma", "state": "LA",
        "lat": 29.5800, "lon": -90.7000,
        "coord_note": "Facility-approximate (east bank of the Houma Navigation Canal).",
        "capability": "heavy_module",
        "note": "630-acre fabrication yard ~30 mi from the Gulf of Mexico via the "
                "navigation canal; 400'x160' floating drydock rated to 15,000 tons. "
                "Heavy lifts, TLP/platform module integration, hull construction.",
        "source_url": "https://www.gulfisland.com/facilities/houma-facility/",
        "verified_at": VERIFIED,
    },
    {
        "id": "hii-ingalls-pascagoula",
        "name": "Ingalls Shipbuilding",
        "operator": "Huntington Ingalls Industries",
        "city": "Pascagoula", "state": "MS",
        "lat": 30.3660, "lon": -88.5210,
        "coord_note": "Facility-approximate (Pascagoula River waterfront).",
        "capability": "large_hull",
        "note": "Largest private employer in Mississippi; new-construction "
                "shipyard for Navy destroyers (Arleigh Burke class) and "
                "amphibious ships.",
        "source_url": "https://en.wikipedia.org/wiki/Ingalls_Shipbuilding",
        "verified_at": VERIFIED,
    },
    {
        "id": "hii-newport-news",
        "name": "Newport News Shipbuilding",
        "operator": "Huntington Ingalls Industries",
        "city": "Newport News", "state": "VA",
        "lat": 37.0700, "lon": -76.4300,
        "coord_note": "Facility-approximate (James River waterfront).",
        "capability": "large_hull",
        "note": "Largest US shipyard by employment; sole builder of Navy "
                "aircraft carriers and co-builder of Virginia-class submarines. "
                "Nuclear-vessel construction experience directly relevant to "
                "reactor-module handling and radiological work practices.",
        "source_url": "https://en.wikipedia.org/wiki/Newport_News_Shipbuilding",
        "verified_at": VERIFIED,
    },
    {
        "id": "bath-iron-works",
        "name": "Bath Iron Works",
        "operator": "General Dynamics",
        "city": "Bath", "state": "ME",
        "lat": 43.9101, "lon": -69.8214,
        "coord_note": "Facility-approximate (Kennebec River waterfront).",
        "capability": "large_hull",
        "note": "Arleigh Burke-class destroyer new construction on the Kennebec River.",
        "source_url": "https://en.wikipedia.org/wiki/Bath_Iron_Works",
        "verified_at": VERIFIED,
    },
    {
        "id": "electric-boat-groton",
        "name": "Electric Boat — Groton",
        "operator": "General Dynamics",
        "city": "Groton", "state": "CT",
        "lat": 41.3495, "lon": -72.0787,
        "coord_note": "Facility-approximate (Thames River waterfront).",
        "capability": "large_hull",
        "note": "Submarine (Virginia-class, Columbia-class) new construction. "
                "Deep nuclear-vessel construction and shielding-fabrication "
                "experience.",
        "source_url": "https://en.wikipedia.org/wiki/Electric_Boat",
        "verified_at": VERIFIED,
    },
    {
        "id": "electric-boat-quonset-point",
        "name": "Electric Boat — Quonset Point",
        "operator": "General Dynamics",
        "city": "North Kingstown", "state": "RI",
        "lat": 41.5928, "lon": -71.4095,
        "coord_note": "Facility-approximate (Narragansett Bay waterfront).",
        "capability": "heavy_module",
        "note": "Submarine hull-module fabrication yard — large steel modules "
                "built here and barged to Groton for final assembly, a supply-"
                "chain shape similar to what a barge-built floating reactor "
                "module would need.",
        "source_url": "https://en.wikipedia.org/wiki/Electric_Boat",
        "verified_at": VERIFIED,
    },
    {
        "id": "nassco-san-diego",
        "name": "NASSCO (National Steel and Shipbuilding Company)",
        "operator": "General Dynamics",
        "city": "San Diego", "state": "CA",
        "lat": 32.6870, "lon": -117.1370,
        "coord_note": "Facility-approximate (San Diego Bay waterfront).",
        "capability": "large_hull",
        "note": "Largest full-service shipyard on the US West Coast; Navy "
                "auxiliary/support ship and commercial tanker new construction.",
        "source_url": "https://en.wikipedia.org/wiki/National_Steel_and_Shipbuilding_Company",
        "verified_at": VERIFIED,
    },
    {
        "id": "austal-usa-mobile",
        "name": "Austal USA",
        "operator": "Austal Limited",
        "city": "Mobile", "state": "AL",
        "lat": 30.6444, "lon": -88.0431,
        "coord_note": "Facility-approximate (Mobile River waterfront).",
        "capability": "large_hull",
        "note": "Independence-class Littoral Combat Ship and Spearhead-class "
                "expeditionary fast transport new construction (aluminum hulls).",
        "source_url": "https://en.wikipedia.org/wiki/Austal_USA",
        "verified_at": VERIFIED,
    },
    {
        "id": "philly-shipyard",
        "name": "Philly Shipyard",
        "operator": "Philly Shipyard, Inc.",
        "city": "Philadelphia", "state": "PA",
        "lat": 39.8895, "lon": -75.1723,
        "coord_note": "Facility-approximate (former Philadelphia Naval Shipyard, "
                       "Delaware River waterfront).",
        "capability": "large_hull",
        "note": "Commercial vessel new construction (product tankers, "
                "container/RoRo ships) on the former Philadelphia Naval "
                "Shipyard site — itself a brownfield-to-shipyard conversion.",
        "source_url": "https://en.wikipedia.org/wiki/Philly_Shipyard",
        "verified_at": VERIFIED,
    },
    {
        "id": "fincantieri-marinette-marine",
        "name": "Fincantieri Marinette Marine",
        "operator": "Fincantieri",
        "city": "Marinette", "state": "WI",
        "lat": 45.1000, "lon": -87.6306,
        "coord_note": "Facility-approximate (Menominee River / Green Bay waterfront).",
        "capability": "large_hull",
        "note": "Great Lakes shipyard; Constellation-class frigate new "
                "construction. The Great Lakes-Seaway system's principal "
                "large-vessel yard.",
        "source_url": "https://en.wikipedia.org/wiki/Fincantieri_Marinette_Marine",
        "verified_at": VERIFIED,
    },
    {
        "id": "vigor-portland",
        "name": "Vigor Portland (Swan Island)",
        "operator": "Vigor / Titan Acquisition Holdings",
        "city": "Portland", "state": "OR",
        "lat": 45.5920, "lon": -122.7610,
        "coord_note": "Facility-approximate (Swan Island, Willamette River).",
        "capability": "naval_repair",
        "note": "Large-vessel repair, conversion, and heavy fabrication on the "
                "Willamette River; no major new-hull construction program.",
        "source_url": "https://en.wikipedia.org/wiki/Vigor_Industrial",
        "verified_at": VERIFIED,
    },
    {
        "id": "vigor-seattle-harbor-island",
        "name": "Vigor Seattle (Harbor Island)",
        "operator": "Vigor / Titan Acquisition Holdings",
        "city": "Seattle", "state": "WA",
        "lat": 47.5824, "lon": -122.3554,
        "coord_note": "Facility-approximate (Harbor Island, Elliott Bay).",
        "capability": "naval_repair",
        "note": "Ferry and vessel repair, heavy steel fabrication.",
        "source_url": "https://en.wikipedia.org/wiki/Vigor_Industrial",
        "verified_at": VERIFIED,
    },
    {
        "id": "puget-sound-naval-shipyard",
        "name": "Puget Sound Naval Shipyard",
        "operator": "US Navy",
        "city": "Bremerton", "state": "WA",
        "lat": 47.5673, "lon": -122.6413,
        "coord_note": "Facility-approximate (Sinclair Inlet waterfront).",
        "capability": "naval_repair",
        "note": "Largest naval shipyard on the West Coast by employment; "
                "aircraft-carrier and submarine overhaul/refueling — deep "
                "nuclear-vessel maintenance experience, no new construction.",
        "source_url": "https://en.wikipedia.org/wiki/Puget_Sound_Naval_Shipyard",
        "verified_at": VERIFIED,
    },
    {
        "id": "norfolk-naval-shipyard",
        "name": "Norfolk Naval Shipyard",
        "operator": "US Navy",
        "city": "Portsmouth", "state": "VA",
        "lat": 36.8073, "lon": -76.3002,
        "coord_note": "Facility-approximate (Elizabeth River waterfront).",
        "capability": "naval_repair",
        "note": "Oldest and largest US naval shipyard; carrier and submarine "
                "overhaul, no new construction.",
        "source_url": "https://en.wikipedia.org/wiki/Norfolk_Naval_Shipyard",
        "verified_at": VERIFIED,
    },
    {
        "id": "portsmouth-naval-shipyard",
        "name": "Portsmouth Naval Shipyard",
        "operator": "US Navy",
        "city": "Kittery", "state": "ME",
        "lat": 43.0837, "lon": -70.7478,
        "coord_note": "Facility-approximate (Piscataqua River, Seavey Island).",
        "capability": "naval_repair",
        "note": "Submarine overhaul and refueling; no new construction.",
        "source_url": "https://en.wikipedia.org/wiki/Portsmouth_Naval_Shipyard",
        "verified_at": VERIFIED,
    },
]


def build() -> None:
    rows = []
    for raw in SHIPYARDS:
        rec = Shipyard.model_validate(raw)
        rows.append(json.loads(rec.model_dump_json()))
    payload = {
        "generated_at": VERIFIED + "T00:00:00Z",
        "source": "Curated benchmark of major US heavy-shipbuilding / "
                  "fabrication yards (no public GIS layer exists; see "
                  "scripts/build_shipyards.py docstring)",
        "source_url": "https://www.maritime.dot.gov/data-reports",
        "count": len(rows),
        "sites": rows,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    log.info("wrote %s (%d shipyards, %d bytes)", OUT_PATH, len(rows), OUT_PATH.stat().st_size)


if __name__ == "__main__":
    build()
