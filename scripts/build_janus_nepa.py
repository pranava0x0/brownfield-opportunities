#!/usr/bin/env python3
"""Build Janus installation-level NEPA screening data with PNNL nepa-mcp.

Run with the isolated Python 3.12 dependency instead of adding it to this
project's Python 3.9 runtime::

    uv run --python 3.12 --with nepa-mcp==0.1.1 \
      python scripts/build_janus_nepa.py

The nine Janus coordinates are installation reference points, not proposed
reactor parcels. Results therefore describe a 10-mile installation context;
they are screening evidence, never an agency determination or score input.
"""
from __future__ import annotations

import argparse
import json
import logging
import socket
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
MICRO_FLEET_PATH = ROOT / "docs" / "data" / "microreactor-fleet.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "janus-nepa.json"
GEOJSON_DIR = ROOT / "docs" / "data" / "janus-nepa"
CACHE_DIR = ROOT / "data" / "cache" / "janus-nepa"

NEPA_MCP_VERSION = "0.1.1"
BUFFER_MILES = 10.0
PADUS_POINT_BUFFER_MILES = 0.1
REQUEST_DELAY_S = 1.5
SOURCE_TIMEOUT_S = 40
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
        "url": "https://pnnl.github.io/nepa-mcp/map-composer/",
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


class SourceTimeoutError(TimeoutError):
    """Raised when one upstream query exceeds the bounded collection window."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_with_timeout(query: Callable[[], Any], seconds: int = SOURCE_TIMEOUT_S) -> Any:
    """Bound an upstream call even when a socket ignores its read timeout."""
    outcome: list[tuple[bool, Any]] = []

    def run() -> None:
        try:
            outcome.append((True, query()))
        except BaseException as exc:
            outcome.append((False, exc))

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise SourceTimeoutError(f"source query exceeded {seconds} seconds")
    succeeded, value = outcome[0]
    if not succeeded:
        raise value
    return value


def prefer_ipv4() -> None:
    """Avoid the known AAAA-first blackhole affecting federal GIS hosts."""
    original = socket.getaddrinfo
    if getattr(original, "_janus_ipv4_pinned", False):
        return

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    ipv4_only._janus_ipv4_pinned = True  # type: ignore[attr-defined]
    socket.getaddrinfo = ipv4_only


def install_request_throttle() -> None:
    """Enforce the repo's 1.5-second per-host floor inside nepa-mcp calls."""
    original = requests.sessions.Session.request
    if getattr(original, "_janus_rate_limited", False):
        return

    lock = threading.Lock()
    last_started: dict[str, float] = {}

    def throttled(session, method, url, **kwargs):
        host = urlparse(str(url)).netloc.lower()
        with lock:
            elapsed = time.monotonic() - last_started.get(host, 0.0)
            if elapsed < REQUEST_DELAY_S:
                time.sleep(REQUEST_DELAY_S - elapsed)
            last_started[host] = time.monotonic()
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault("User-Agent", USER_AGENT)
        kwargs["headers"] = headers
        return original(session, method, url, **kwargs)

    throttled._janus_rate_limited = True  # type: ignore[attr-defined]
    requests.sessions.Session.request = throttled


def load_janus_sites(selected: set[str] | None = None) -> list[dict[str, Any]]:
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
    if source == "padus":
        source = "padus-0p1mi"
    return CACHE_DIR / f"{site_id}--{source}.json"


def cached_query(
    site: dict[str, Any],
    source: str,
    query: Callable[[], dict[str, Any]],
    normalize: Callable[[dict[str, Any]], dict[str, Any]],
    use_cache: bool,
) -> dict[str, Any]:
    path = cache_path(site["id"], source)
    if use_cache and path.exists():
        log.info("cache hit  %s", path.name)
        return json.loads(path.read_text())
    log.info("querying   %s / %s", site["id"], source)
    raw = run_with_timeout(query)
    normalized = normalize(raw)
    normalized["status"] = "ok"
    normalized["retrieved_at"] = utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2) + "\n")
    return normalized


def error_result(exc: Exception) -> dict[str, Any]:
    return {"status": "unavailable", "error": str(exc), "retrieved_at": utc_now()}


def cache_error(site: dict[str, Any], source: str, exc: Exception) -> dict[str, Any]:
    """Persist explicit unavailability so an ordinary rerun is fast and stable."""
    result = error_result(exc)
    path = cache_path(site["id"], source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def normalize_ipac(data: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "species",
        "migratory_birds",
        "wetlands",
        "refuges",
        "field_offices",
        "critical_habitat",
        "marine_mammals",
        "fish_hatcheries",
        "coastal_barriers",
    )
    out = {key: data.get(key, []) for key in keep}
    out["counts"] = {
        "listed_species": len(out["species"]),
        "critical_habitat": len(out["critical_habitat"]),
        "migratory_birds": len(out["migratory_birds"]),
        "wetland_types": len(out["wetlands"]),
        "refuges": len(out["refuges"]),
    }
    return out


def normalize_tribal(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": data.get("total", 0),
        "tribal_lands": data.get("tribal_lands", []),
        "warnings": data.get("warnings", []),
    }


def normalize_nrhp(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": data.get("total", 0),
        "national_historic_landmarks": data.get("nhl_count", 0),
        "properties": data.get("properties", []),
        "warnings": data.get("warnings", []),
        "data_unavailable": bool(data.get("data_unavailable")),
    }


def normalize_padus(data: dict[str, Any]) -> dict[str, Any]:
    records = data.get("records", [])
    owners = Counter(record.get("owner_type") or "Unknown" for record in records)
    designations = Counter(record.get("designation_type") or "Unspecified" for record in records)
    ranked = sorted(records, key=lambda row: row.get("gis_acres") or 0, reverse=True)
    return {
        "query_buffer_miles": PADUS_POINT_BUFFER_MILES,
        "count": data.get("total_records", len(records)),
        "owner_types": dict(owners.most_common()),
        "designation_types": dict(designations.most_common()),
        "largest_records": ranked[:25],
        "records_truncated": max(0, len(records) - 25),
        "warnings": data.get("warnings", []),
    }


def normalize_usace(data: dict[str, Any]) -> dict[str, Any]:
    districts = data.get("regulatory_districts", {})
    regions = data.get("wetland_regions", {})
    subregions = data.get("wetland_subregions", {})
    warnings = []
    for section in (districts, regions, subregions):
        warnings.extend(section.get("warnings", []))
    return {
        "districts": districts.get("districts", []),
        "wetland_regions": regions.get("regions", []),
        "wetland_subregions": subregions.get("subregions", []),
        "warnings": warnings,
        "limitation": (
            "District and delineation-region context only. This does not show "
            "wetland presence or make a Clean Water Act jurisdictional determination."
        ),
    }


def normalize_nepa_assist(data: dict[str, Any]) -> dict[str, Any]:
    categories = (
        "air_quality",
        "water_resources",
        "contaminated_sites",
        "community_features",
        "natural_resources",
        "cultural_resources",
        "other",
    )
    return {
        "summary": data.get("summary", {}),
        "categories": {key: data.get(key, {}) for key in categories if data.get(key)},
        "report_url": data.get("metadata", {}).get("api_url"),
    }


def run_tabular_sources(
    sites: list[dict[str, Any]], use_cache: bool
) -> dict[str, dict[str, dict[str, Any]]]:
    from nepa_mcp import __version__
    from nepa_mcp.loader import load_server_module

    if __version__ != NEPA_MCP_VERSION:
        raise RuntimeError(f"expected nepa-mcp {NEPA_MCP_VERSION}, found {__version__}")

    results = {site["id"]: {} for site in sites}
    source_defs = (
        (
            "ipac",
            "get_ipac_resources_in_roi",
            normalize_ipac,
            lambda fn, site: fn(site["lat"], site["lon"], BUFFER_MILES),
        ),
        (
            "tribal",
            "get_tribal_lands_in_roi",
            normalize_tribal,
            lambda fn, site: fn(site["lat"], site["lon"], BUFFER_MILES),
        ),
        (
            "nrhp",
            "get_nrhp_properties_in_roi",
            normalize_nrhp,
            lambda fn, site: fn(site["lat"], site["lon"], BUFFER_MILES),
        ),
        (
            "padus",
            "get_padus_in_roi",
            normalize_padus,
            lambda fn, site: fn(site["lat"], site["lon"], PADUS_POINT_BUFFER_MILES),
        ),
        (
            "usace",
            "analyze_usace_jurisdiction",
            normalize_usace,
            lambda fn, site: fn(site["lat"], site["lon"], BUFFER_MILES),
        ),
        (
            "nepa_assist",
            "query_nepa_assist",
            normalize_nepa_assist,
            lambda fn, site: fn(
                site["lat"], site["lon"], BUFFER_MILES, f"Army Janus — {site['name']}"
            ),
        ),
    )

    for source, function_name, normalize, invoke in source_defs:
        module = load_server_module(source)
        function = getattr(module, function_name)
        for site in sites:
            try:
                results[site["id"]][source] = cached_query(
                    site,
                    source,
                    lambda fn=function, row=site: invoke(fn, row),
                    normalize,
                    use_cache,
                )
            except Exception as exc:  # one upstream must not kill the other evidence
                log.exception("%s / %s failed", site["id"], source)
                results[site["id"]][source] = cache_error(site, source, exc)
    return results


def build_site_geojson(site: dict[str, Any], use_cache: bool) -> dict[str, Any]:
    from nepa_mcp.loader import load_server_module

    path = cache_path(site["id"], "map-composer")
    if use_cache and path.exists():
        log.info("cache hit  %s", path.name)
        return json.loads(path.read_text())

    module = load_server_module("map_composer")
    combined_features = []
    statuses = {}
    for layer in MAP_LAYERS:
        layer_buffer_miles = MAP_LAYER_BUFFER_MILES.get(layer, BUFFER_MILES)
        log.info("mapping    %s / %s", site["id"], layer)
        try:
            collection = run_with_timeout(
                lambda: module.collect_all_layers(
                    site["lat"], site["lon"], layer_buffer_miles, [layer], False
                )
            )
        except Exception as exc:
            log.exception("%s / %s map layer failed", site["id"], layer)
            statuses[layer] = {
                "status": "failed",
                "feature_count": 0,
                "warnings": [str(exc)],
                "query_buffer_miles": layer_buffer_miles,
            }
            continue
        feature_collection = collection.layers.get(layer, {})
        combined_features.extend(feature_collection.get("features", []))
        statuses[layer] = collection.statuses.get(
            layer,
            {"status": "failed", "feature_count": 0, "warnings": ["No status returned"]},
        )
        statuses[layer]["query_buffer_miles"] = layer_buffer_miles

    result = {
        "type": "FeatureCollection",
        "features": combined_features,
        "metadata": {
            "site_id": site["id"],
            "retrieved_at": utc_now(),
            "nepa_mcp_version": NEPA_MCP_VERSION,
            "buffer_miles": BUFFER_MILES,
            "layers": statuses,
            "limitations": (
                "Installation-reference screening only; proposed reactor parcel unknown. "
                "Unavailable layers are not no-hit findings."
            ),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, separators=(",", ":")))
    return result


def write_outputs(
    sites: list[dict[str, Any]],
    tabular: dict[str, dict[str, dict[str, Any]]],
    geojson_by_site: dict[str, dict[str, Any]],
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
            statuses = geojson.get("metadata", {}).get("layers", {})
            map_summary = {
                "feature_count": len(geojson.get("features", [])),
                "layers_ok": sum(
                    status.get("status") in {"ok", "empty"} for status in statuses.values()
                ),
                "layers_partial": sum(
                    status.get("status") == "partial" for status in statuses.values()
                ),
                "layers_failed": sum(
                    status.get("status") == "failed" for status in statuses.values()
                ),
            }
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
