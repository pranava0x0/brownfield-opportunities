#!/usr/bin/env python3
"""Build Janus installation-level NEPA screening data with PNNL nepa-mcp.

Run with the isolated Python 3.12 dependency instead of adding it to this
project's Python 3.9 runtime::

    uv run --python 3.12 --with nepa-mcp==0.1.1 \
      python scripts/build_janus_nepa.py

The nine Janus coordinates are installation reference points, not proposed
reactor parcels. Results therefore describe a 10-mile installation context;
they are screening evidence, never an agency determination or score input.

The generic query/cache/normalize machinery lives in
``scripts/nepa_screening.py`` (shared with the Hanford and coal screening
builders); this file keeps only what is Janus-specific — the site roster,
source list, buffers, cache naming, and output payload.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import nepa_screening as screening

ROOT = SCRIPTS_DIR.parent
MICRO_FLEET_PATH = ROOT / "docs" / "data" / "microreactor-fleet.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "janus-nepa.json"
GEOJSON_DIR = ROOT / "docs" / "data" / "janus-nepa"
CACHE_DIR = ROOT / "data" / "cache" / "janus-nepa"

NEPA_MCP_VERSION = screening.NEPA_MCP_VERSION
BUFFER_MILES = 10.0
PADUS_POINT_BUFFER_MILES = 0.1
USER_AGENT = "BrownfieldOpportunities/0.2 (Janus NEPA screening; research)"

MAP_LAYERS = (
    "roi",
    "tribal_lands",
    "critical_habitat",
    "wildlife_refuges",
    "usace_districts",
    "nhd_lakes",
    "nhd_reservoirs",
    "nhd_perennial_streams",
    "nhd_stream_areas",
    "federal_lands",
    "nps_boundaries",
    "fire_perimeters",
)

# federal_lands (PAD-US) ROI calls proved too large/unreliable at 10 miles
# during the original probe; it stays a point-context query.
MAP_LAYER_BUFFER_MILES = {
    "federal_lands": PADUS_POINT_BUFFER_MILES,
}

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
        "covers": (
            "protected-area context at the installation reference point (0.1-mile "
            "query); not cadastral title or a 10-mile inventory"
        ),
    },
    "usace": {
        "label": "USACE regulatory boundaries and wetland regions",
        "url": "https://regulatory.ops.usace.army.mil/",
        "covers": "district and delineation method; not wetland presence or jurisdiction",
    },
    "nepa_assist": {
        "label": "EPA NEPAssist",
        "url": "https://nepassisttool.epa.gov/nepassist/nepamap.aspx",
        "covers": "environmental proximity flags from EPA screening services",
    },
    "map_composer": {
        "label": "PNNL NEPA MCP Map Composer",
        "url": "https://pnnl.github.io/nepa-mcp/",
        "covers": "provenance-rich federal GIS features clipped to the screening buffer",
    },
}

DEPLOYMENT_PATHWAY = {
    "program": "Army Janus",
    "reactor_regulator": "United States Army",
    "acquisition": (
        "Defense Innovation Unit Commercial Solutions Opening with milestone-based "
        "Other Transaction awards."
    ),
    "site_status": (
        "Nine installations are under consideration. Final reactor count, site, "
        "design, and project footprint remain part of the acquisition process."
    ),
    "nepa_status": (
        "Executive Order 14299 directs DoD and DOE to consult CEQ on use, adoption, "
        "or creation of categorical exclusions and other NEPA procedures. A "
        "project-specific Janus NEPA review level has not been published."
    ),
    "limitations": (
        "This describes the announced program vehicle. Confirm the selected design, "
        "operator, authorization basis, lead agency, cooperating agencies, permits, "
        "and NEPA review in award and site-specific documents."
    ),
    "sources": [
        {
            "label": "Army Janus announcement — November 18, 2025",
            "url": (
                "https://www.army.mil/article-amp/289074/"
                "army_announces_next_steps_on_janus_program_for_next_generation_nuclear_energy"
            ),
        },
        {
            "label": "Executive Order 14299 — May 23, 2025",
            "url": (
                "https://www.whitehouse.gov/presidential-actions/2025/05/"
                "deploying-advanced-nuclear-reactor-technologies-for-national-security/"
            ),
        },
    ],
}

log = logging.getLogger("janus-nepa")

# Re-exported so existing callers and the contract tests keep one import site.
SourceTimeoutError = screening.SourceTimeoutError
utc_now = screening.utc_now
run_with_timeout = screening.run_with_timeout
prefer_ipv4 = screening.prefer_ipv4
error_result = screening.error_result
normalize_ipac = screening.normalize_ipac
normalize_tribal = screening.normalize_tribal
normalize_nrhp = screening.normalize_nrhp
normalize_usace = screening.normalize_usace
normalize_nepa_assist = screening.normalize_nepa_assist
normalize_padus = screening.make_normalize_padus(PADUS_POINT_BUFFER_MILES)


def install_request_throttle() -> None:
    """Janus keeps its historical User-Agent on the shared throttle."""
    screening.install_request_throttle(USER_AGENT)


def load_janus_sites(selected: "set[str] | None" = None) -> "list[dict[str, Any]]":
    payload = json.loads(MICRO_FLEET_PATH.read_text())
    rows = []
    for commitment in payload.get("commitments", []):
        if not commitment.get("janus"):
            continue
        site_id = commitment["ap1000_ref"]
        if selected and site_id not in selected:
            continue
        rows.append(
            {
                "id": site_id,
                "commitment_id": commitment["id"],
                "name": commitment["name"].replace(" (Army Janus)", ""),
                "state": commitment["state"],
                "location": commitment["location"],
                "lat": commitment["lat"],
                "lon": commitment["lon"],
            }
        )
    rows.sort(key=lambda row: row["name"])
    if not rows:
        raise ValueError("no Janus installations selected")
    return rows


def cache_path(site_id: str, source: str) -> Path:
    """Historical Janus cache naming — the padus suffix records its buffer.

    Existing cache files on disk use these exact names; keep them stable so
    re-runs stay free. Reads CACHE_DIR at call time so tests can patch it.
    """
    if source == "padus":
        source = "padus-0p1mi"
    return CACHE_DIR / f"{site_id}--{source}.json"


def cache_error(site: "dict[str, Any]", source: str, exc: Exception) -> "dict[str, Any]":
    """Persist explicit unavailability so an ordinary rerun is fast and stable."""
    return screening.cache_error_at(cache_path(site["id"], source), exc)


def _source_defs() -> "tuple[screening.SourceDef, ...]":
    """The six Janus tabular sources (key == server name for all of them)."""
    return (
        screening.SourceDef(
            "ipac", "ipac", "get_ipac_resources_in_roi", normalize_ipac,
            lambda fn, site: fn(site["lat"], site["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "tribal", "tribal", "get_tribal_lands_in_roi", normalize_tribal,
            lambda fn, site: fn(site["lat"], site["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "nrhp", "nrhp", "get_nrhp_properties_in_roi", normalize_nrhp,
            lambda fn, site: fn(site["lat"], site["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "padus", "padus", "get_padus_in_roi", normalize_padus,
            lambda fn, site: fn(site["lat"], site["lon"], PADUS_POINT_BUFFER_MILES),
        ),
        screening.SourceDef(
            "usace", "usace", "analyze_usace_jurisdiction", normalize_usace,
            lambda fn, site: fn(site["lat"], site["lon"], BUFFER_MILES),
        ),
        screening.SourceDef(
            "nepa_assist", "nepa_assist", "query_nepa_assist", normalize_nepa_assist,
            lambda fn, site: fn(
                site["lat"], site["lon"], BUFFER_MILES, f"Army Janus — {site['name']}"
            ),
        ),
    )


def run_tabular_sources(
    sites: "list[dict[str, Any]]", use_cache: bool
) -> "dict[str, dict[str, dict[str, Any]]]":
    return screening.run_source_matrix(
        sites,
        _source_defs(),
        cache_path_fn=cache_path,
        use_cache=use_cache,
    )


def build_site_geojson(site: "dict[str, Any]", use_cache: bool) -> "dict[str, Any]":
    return screening.collect_map_geojson(
        site,
        MAP_LAYERS,
        BUFFER_MILES,
        cache_file=cache_path(site["id"], "map-composer"),
        layer_buffer_overrides=MAP_LAYER_BUFFER_MILES,
        use_cache=use_cache,
        limitations=(
            "Installation-reference screening only; proposed reactor parcel unknown. "
            "Unavailable layers are not no-hit findings."
        ),
    )


def write_outputs(
    sites: "list[dict[str, Any]]",
    tabular: "dict[str, dict[str, dict[str, Any]]]",
    geojson_by_site: "dict[str, dict[str, Any]]",
    merge_existing: bool = False,
) -> None:
    output_sites = []
    GEOJSON_DIR.mkdir(parents=True, exist_ok=True)
    for site in sites:
        geojson = geojson_by_site.get(site["id"])
        geojson_url = None
        map_summary = None
        if geojson:
            geojson_path = GEOJSON_DIR / f"{site['id']}.geojson"
            geojson_path.write_text(json.dumps(geojson, separators=(",", ":")))
            geojson_url = f"data/janus-nepa/{site['id']}.geojson"
            map_summary = screening.summarize_map_package(geojson)
        output_sites.append(
            {
                **site,
                "screening": tabular[site["id"]],
                "geojson_url": geojson_url,
                "map_summary": map_summary,
            }
        )

    if merge_existing:
        if not OUTPUT_PATH.exists():
            raise RuntimeError("--site requires an existing complete janus-nepa.json")
        existing = json.loads(OUTPUT_PATH.read_text())
        by_id = {site["id"]: site for site in existing.get("sites", [])}
        by_id.update({site["id"]: site for site in output_sites})
        output_sites = sorted(by_id.values(), key=lambda row: row["name"])

    payload = {
        "generated_at": utc_now(),
        "nepa_mcp_version": NEPA_MCP_VERSION,
        "screening_buffer_miles": BUFFER_MILES,
        "site_count": len(output_sites),
        "method": (
            "PNNL nepa-mcp structured APIs and Map Composer layers, cached and "
            "rate-limited to at least 1.5 seconds between requests per host."
        ),
        "limitations": [
            "Coordinates are installation reference points, not proposed reactor parcels.",
            "Counts mean features intersect the screening buffer, not the project footprint.",
            "No result is an agency determination, permit conclusion, or suitability score.",
            "An unavailable source is never treated as a no-hit.",
        ],
        "sources": SOURCE_META,
        "deployment_pathway": DEPLOYMENT_PATHWAY,
        "sites": output_sites,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    log.info("wrote %s (%d sites)", OUTPUT_PATH, len(output_sites))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", action="append", default=[], help="Only build this AP1000/Janus site id")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached source responses")
    parser.add_argument("--no-geojson", action="store_true", help="Skip Map Composer GeoJSON")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    prefer_ipv4()
    install_request_throttle()
    sites = load_janus_sites(set(args.site) or None)
    tabular = run_tabular_sources(sites, use_cache=not args.no_cache)
    geojson_by_site = {}
    if not args.no_geojson:
        for site in sites:
            try:
                geojson_by_site[site["id"]] = build_site_geojson(
                    site, use_cache=not args.no_cache
                )
            except Exception as exc:
                log.exception("%s / map-composer failed", site["id"])
                geojson_by_site[site["id"]] = {
                    "type": "FeatureCollection",
                    "features": [],
                    "metadata": {"status": "unavailable", "error": str(exc)},
                }
    write_outputs(sites, tabular, geojson_by_site, merge_existing=bool(args.site))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
