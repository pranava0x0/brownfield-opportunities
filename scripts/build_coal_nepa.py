#!/usr/bin/env python3
"""Build per-plant NEPA permitting screens for the coal repowering catalog.

Coal-to-nuclear and coal-to-data-center conversions live or die on
speed-to-power, and the slowest gate is usually environmental review — yet
the coal catalog (docs/data/coal-conversions.json) carries grid, water,
rail, and valuation signals with no permitting context at all. This builder
runs each of the 18 cataloged plants through seven PNNL nepa-mcp sources
(USFWS IPaC, tribal geography, NRHP, PAD-US point context, USACE district,
FEMA NFHL flood zones, EPA NEPAssist) and emits docs/data/coal-nepa.json,
which the Coal Repowering drawer renders as a "Permitting screen" section.

Run with the isolated Python 3.12 interpreter (nepa-mcp is never a project
dependency — see nepa-mcp-integration-spec.md)::

    uv run --python 3.12 --with nepa-mcp==0.1.1 \
      python scripts/build_coal_nepa.py

Same honesty rails as every screening product here: coordinates are plant
reference points, counts mean features intersect the buffer (not a project
footprint), no result is an agency determination, and an unavailable source
is never a no-hit. Screens are keyed by ``plant_name`` — the same join key
the coal markers and drawer already use.

Why these seven sources and not the Hanford ten: the NOAA West Coast
critical-habitat and salmon-EFH layers only cover Pacific states (the
catalog is mostly interior/eastern), and GBIF occurrence counts add noise,
not signal, to a permitting summary. Add them per-site in Tier A if a
specific western plant needs the NMFS lens.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import nepa_screening as screening

ROOT = SCRIPTS_DIR.parent
CATALOG_PATH = ROOT / "docs" / "data" / "coal-conversions.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "coal-nepa.json"
CACHE_DIR = ROOT / "data" / "cache" / "coal-nepa"

USER_AGENT = "BrownfieldOpportunities/0.2 (Coal repowering NEPA screening; research)"

# Coal plants are compact industrial sites; a 5-mile context (vs the Janus
# 10-mile installation buffer) keeps neighboring-county noise out of the
# drawer summary. Flood uses the tight NFHL radius, PAD-US the point context
# (same reliability constraint the Janus probe established).
BUFFER_MILES = 5.0
PADUS_POINT_BUFFER_MILES = 0.1
FLOOD_RADIUS_MILES = 2.0

log = logging.getLogger("coal-nepa")

SOURCE_META = {
    "ipac": {
        "label": "USFWS IPaC",
        "url": "https://ipac.ecosphere.fws.gov/",
        "covers": "ESA species, critical habitat, migratory birds, wetlands, refuges",
    },
    "tribal": {
        "label": "Census TIGERweb AIANNHA",
        "url": "https://tigerweb.geo.census.gov/tigerwebmain/TIGERweb_apps.html",
        "covers": "mapped tribal geographies; not consultation obligations",
    },
    "nrhp": {
        "label": "National Park Service NRHP",
        "url": "https://www.nps.gov/subjects/nationalregister/database-research.htm",
        "covers": "listed historic properties; not eligible but unlisted resources",
    },
    "padus": {
        "label": "USGS PAD-US 4.1",
        "url": "https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-overview",
        "covers": "protected-area context at the plant reference point (0.1-mile query)",
    },
    "usace": {
        "label": "USACE regulatory boundaries and wetland regions",
        "url": "https://regulatory.ops.usace.army.mil/",
        "covers": "district and delineation method; not wetland presence or jurisdiction",
    },
    "fema_nfhl": {
        "label": "FEMA National Flood Hazard Layer",
        "url": "https://www.fema.gov/flood-maps/national-flood-hazard-layer",
        "covers": "mapped flood zones within 2 miles; zone counts, not a footprint placement",
    },
    "nepa_assist": {
        "label": "EPA NEPAssist",
        "url": "https://nepassisttool.epa.gov/nepassist/nepamap.aspx",
        "covers": "environmental proximity flags from EPA screening services",
    },
}

LIMITATIONS = [
    "Coordinates are plant reference points, not project footprints.",
    "Counts mean features intersect the screening buffer, not the parcel.",
    "No result is an agency determination, permit conclusion, or score input.",
    "An unavailable source is never treated as a no-hit.",
    "Riverine coal plants sit next to water by design — mapped flood zones nearby are expected context, not a disqualifier.",
]


def plant_slug(name: str) -> str:
    """Stable cache-file slug for a plant name (names carry spaces/punct)."""
    keep = [c.lower() if c.isalnum() else "-" for c in name]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def cache_path(site_id: str, source: str) -> Path:
    return CACHE_DIR / f"{site_id}--{source}.json"


def load_plants(selected: "set[str] | None" = None) -> "list[dict]":
    payload = json.loads(CATALOG_PATH.read_text())
    rows = []
    for asset in payload.get("assets", []):
        if selected and asset["plant_name"] not in selected:
            continue
        rows.append(
            {
                # `id` feeds cache naming + the source-matrix result keys;
                # `plant_name` is the frontend join key and stays verbatim.
                "id": plant_slug(asset["plant_name"]),
                "plant_name": asset["plant_name"],
                "eia_plant_id": asset.get("eia_plant_id"),
                "state": asset["state"],
                "status": asset["status"],
                "lat": asset["latitude"],
                "lon": asset["longitude"],
            }
        )
    if not rows:
        raise SystemExit("no coal plants selected")
    rows.sort(key=lambda row: row["plant_name"])
    return rows


def _source_defs() -> "tuple[screening.SourceDef, ...]":
    normalize_padus = screening.make_normalize_padus(PADUS_POINT_BUFFER_MILES)
    return (
        screening.SourceDef(
            "ipac", "ipac", "get_ipac_resources_in_roi", screening.normalize_ipac,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "tribal", "tribal", "get_tribal_lands_in_roi", screening.normalize_tribal,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "nrhp", "nrhp", "get_nrhp_properties_in_roi", screening.normalize_nrhp,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "padus", "padus", "get_padus_in_roi", normalize_padus,
            lambda fn, s: fn(s["lat"], s["lon"], PADUS_POINT_BUFFER_MILES),
        ),
        screening.SourceDef(
            "usace", "usace", "analyze_usace_jurisdiction", screening.normalize_usace,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "fema_nfhl", "fema_nfhl", "get_flood_zones", screening.normalize_flood_zones,
            lambda fn, s: fn(s["lat"], s["lon"], FLOOD_RADIUS_MILES),
        ),
        screening.SourceDef(
            "nepa_assist", "nepa_assist", "query_nepa_assist", screening.normalize_nepa_assist,
            lambda fn, s: fn(s["lat"], s["lon"], BUFFER_MILES, f"Coal repowering — {s['plant_name']}"),
        ),
    )


def write_output(plants: "list[dict]", tabular: dict) -> None:
    out = []
    for plant in plants:
        out.append(
            {
                "plant_name": plant["plant_name"],
                "eia_plant_id": plant["eia_plant_id"],
                "state": plant["state"],
                "status": plant["status"],
                "lat": plant["lat"],
                "lon": plant["lon"],
                "screening": tabular.get(plant["id"], {}),
            }
        )
    payload = {
        "generated_at": screening.utc_now(),
        "nepa_mcp_version": screening.NEPA_MCP_VERSION,
        "screening_buffer_miles": BUFFER_MILES,
        "flood_radius_miles": FLOOD_RADIUS_MILES,
        "plant_count": len(out),
        "method": (
            "PNNL nepa-mcp structured APIs, cached and rate-limited to at "
            "least 1.5 seconds between requests per host; one screen per "
            "cataloged coal repowering asset."
        ),
        "limitations": LIMITATIONS,
        "sources": SOURCE_META,
        "plants": out,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    log.info("wrote %s (%d plants)", OUTPUT_PATH, len(out))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plant", action="append", default=[], help="Only screen this plant_name")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached source responses")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    screening.prefer_ipv4()
    screening.install_request_throttle(USER_AGENT)
    plants = load_plants(set(args.plant) or None)
    tabular = screening.run_source_matrix(
        plants, _source_defs(), cache_path_fn=cache_path, use_cache=not args.no_cache
    )
    write_output(plants, tabular)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
