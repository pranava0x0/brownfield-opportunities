#!/usr/bin/env python3
"""Shared machinery for PNNL nepa-mcp environmental screening builders.

This module is the reusable core extracted from ``build_janus_nepa.py`` so
that every curated screening product (Army Janus installations, the Hanford
DOE parcel explorer, the coal-repowering catalog, and any future site list)
runs on one audited code path instead of three diverging copies.

Design constraints it must uphold (see nepa-mcp-integration-spec.md):

* **nepa-mcp is never a project dependency.** It requires Python >= 3.12 and
  pulls shapely/pyproj C extensions; this repo's floor is 3.9 and its spatial
  code is pure-Python on purpose. Every ``import nepa_mcp`` therefore lives
  INSIDE a function body, so this module itself imports cleanly under 3.9
  (letting the pytest suite unit-test the normalizers and cache logic) while
  the network-touching entry points run under::

      uv run --python 3.12 --with nepa-mcp==0.1.1 python scripts/<builder>.py

* **The repo's network ethics apply inside nepa-mcp too.** nepa-mcp's own
  servers issue requests through ``requests``; ``install_request_throttle()``
  monkeypatches ``requests.Session.request`` to enforce the 1.5 s per-host
  floor and a descriptive User-Agent no matter which upstream a tool fans
  out to. ``prefer_ipv4()`` applies the known AAAA-blackhole fix.

* **Unavailable is never a no-hit.** Upstream timeouts and errors are cached
  as explicit ``{"status": "unavailable"}`` records so re-runs are fast and
  the UI can render "Unavailable" instead of a silent zero. Screening output
  is evidence for humans, never an agency determination or a score input.

* **Every response is cached to disk** under a caller-supplied cache dir, so
  a killed run loses nothing and a full rebuild is nearly free. Callers own
  cache-file naming (via a ``cache_path_fn``) because the Janus builder
  shipped cache files with a legacy naming quirk (``--padus-0p1mi``) that
  must keep resolving.
"""
from __future__ import annotations

import json
import logging
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

import requests

# Pin the exact nepa-mcp release every builder was validated against. 0.1.1's
# tool catalog is generated from the live tools/list contract and WILL drift
# between releases — verify_nepa_mcp_version() fails loud on any mismatch so
# a silent upgrade can't change response shapes under us.
NEPA_MCP_VERSION = "0.1.1"

# Repo-wide network ethics floor (CLAUDE.md "Network Ethics & Rate Limiting").
REQUEST_DELAY_S = 1.5
# One upstream query gets this long before we record it as unavailable. Federal
# GIS hosts sometimes accept the socket and then stall past their own read
# timeout, hence the thread-based bound in run_with_timeout().
SOURCE_TIMEOUT_S = 40
DEFAULT_USER_AGENT = "BrownfieldOpportunities/0.2 (NEPA screening; research)"

log = logging.getLogger("nepa-screening")


class SourceTimeoutError(TimeoutError):
    """Raised when one upstream query exceeds the bounded collection window."""


def utc_now() -> str:
    """ISO-8601 UTC timestamp with a Z suffix (matches every repo artifact)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_with_timeout(query: Callable[[], Any], seconds: int = SOURCE_TIMEOUT_S) -> Any:
    """Bound an upstream call even when a socket ignores its read timeout.

    A daemon worker thread runs the query; if it has not finished inside
    ``seconds`` we abandon it and raise. The thread may keep running in the
    background until its own socket dies — that is acceptable for a batch
    builder and unavoidable without process isolation.
    """
    outcome: list = []  # single (succeeded, value) tuple appended by worker

    def run() -> None:
        try:
            outcome.append((True, query()))
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller thread
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
    """Avoid the known AAAA-first blackhole affecting federal GIS hosts.

    Same fix as ``connectors.base.prefer_ipv4()`` — duplicated here (rather
    than imported) because the builders run on an isolated Python 3.12
    interpreter where the project package is not necessarily importable.
    Idempotent: tags the wrapper so repeat calls don't nest.
    """
    original = socket.getaddrinfo
    if getattr(original, "_nepa_ipv4_pinned", False):
        return

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        return original(host, port, socket.AF_INET, type, proto, flags)

    ipv4_only._nepa_ipv4_pinned = True  # type: ignore[attr-defined]
    socket.getaddrinfo = ipv4_only


def install_request_throttle(user_agent: str = DEFAULT_USER_AGENT) -> None:
    """Enforce the repo's 1.5-second per-host floor inside nepa-mcp calls.

    nepa-mcp's servers each manage their own HTTP sessions, so the only
    reliable single choke point is ``requests.Session.request`` itself.
    Thread-safe (the map-composer collector can parallelize) and idempotent.
    """
    original = requests.sessions.Session.request
    if getattr(original, "_nepa_rate_limited", False):
        return

    lock = threading.Lock()
    last_started: dict = {}

    def throttled(session, method, url, **kwargs):
        host = urlparse_netloc(str(url))
        with lock:
            elapsed = time.monotonic() - last_started.get(host, 0.0)
            if elapsed < REQUEST_DELAY_S:
                time.sleep(REQUEST_DELAY_S - elapsed)
            last_started[host] = time.monotonic()
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault("User-Agent", user_agent)
        kwargs["headers"] = headers
        return original(session, method, url, **kwargs)

    throttled._nepa_rate_limited = True  # type: ignore[attr-defined]
    requests.sessions.Session.request = throttled


def urlparse_netloc(url: str) -> str:
    """Lowercased netloc for per-host throttling (tiny helper, testable)."""
    from urllib.parse import urlparse

    return urlparse(url).netloc.lower()


def verify_nepa_mcp_version() -> None:
    """Fail loud if the interpreter carries a different nepa-mcp release."""
    from nepa_mcp import __version__

    if __version__ != NEPA_MCP_VERSION:
        raise RuntimeError(f"expected nepa-mcp {NEPA_MCP_VERSION}, found {__version__}")


# ---------------------------------------------------------------------------
# Disk cache — one JSON file per (site, source) so every response survives a
# killed run and an ordinary rebuild is nearly free.
# ---------------------------------------------------------------------------

def error_result(exc: Exception) -> dict:
    """Uniform 'unavailable' record. Never conflated with an empty result."""
    return {"status": "unavailable", "error": str(exc), "retrieved_at": utc_now()}


def _atomic_write(path: Path, text: str) -> None:
    """Write via a same-directory temp file + rename so a killed run can
    never leave a truncated cache file behind (Codex PR #22 round 2)."""
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def read_cache(path: Path) -> Optional[dict]:
    """Read a cache file, treating a missing OR unreadable file as a miss.

    A run killed mid-write (pre-atomic-write caches) or a corrupted disk
    must degrade to 'query again', never to a parse error that the caller's
    failure isolation would then persist as a permanent 'unavailable'
    (Codex PR #22 round 2)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        log.warning("unreadable cache %s (%s) — treating as a miss", path.name, exc)
        return None


def cached_query(
    path: Path,
    label: str,
    query: Callable[[], Any],
    normalize: Callable[[Any], dict],
    use_cache: bool,
    timeout_s: int = SOURCE_TIMEOUT_S,
) -> dict:
    """Run one upstream query through the timeout + normalize + cache chain.

    ``label`` is only for log lines. The normalized record gains ``status``
    and ``retrieved_at`` before hitting disk, so a cache file is always a
    complete, renderable evidence record on its own.
    """
    if use_cache:
        cached = read_cache(path)
        if cached is not None:
            log.info("cache hit  %s", path.name)
            return cached
    log.info("querying   %s", label)
    raw = run_with_timeout(query, timeout_s)
    normalized = normalize(raw)
    normalized["status"] = "ok"
    normalized["retrieved_at"] = utc_now()
    _atomic_write(path, json.dumps(normalized, indent=2) + "\n")
    return normalized


def cache_error_at(path: Path, exc: Exception) -> dict:
    """Persist explicit unavailability so an ordinary rerun is fast and stable.

    Deliberate trade-off: a transient upstream blip is cached as unavailable
    until someone re-runs with the cache disabled for that site. That beats
    the alternative (hammering a struggling federal host on every rebuild),
    and the UI renders 'Unavailable', never a false no-hit.
    """
    result = error_result(exc)
    _atomic_write(path, json.dumps(result, indent=2) + "\n")
    return result


# ---------------------------------------------------------------------------
# Normalizers — trim each nepa-mcp response to the fields the product renders,
# and attach the honesty rails (limitation strings) the UI must carry.
# Each takes the raw tool response dict and returns a JSON-serializable dict.
# ---------------------------------------------------------------------------

def normalize_ipac(data: dict) -> dict:
    """USFWS IPaC: ESA species, critical habitat, refuges, wetland types."""
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


def normalize_tribal(data: dict) -> dict:
    """Census TIGERweb AIANNHA: mapped tribal geographies.

    Mapped geography means consultation CONTEXT — never land title, treaty
    rights (which extend far beyond mapped boundaries), or a consultation
    conclusion. The UI copy must keep saying so.
    """
    return {
        "count": data.get("total", 0),
        "tribal_lands": data.get("tribal_lands", []),
        "warnings": data.get("warnings", []),
    }


def normalize_nrhp(data: dict) -> dict:
    """NPS National Register: LISTED properties only, not eligible-unlisted."""
    return {
        "count": data.get("total", 0),
        "national_historic_landmarks": data.get("nhl_count", 0),
        "properties": data.get("properties", []),
        "warnings": data.get("warnings", []),
        "data_unavailable": bool(data.get("data_unavailable")),
    }


def make_normalize_padus(query_buffer_miles: float) -> Callable[[dict], dict]:
    """PAD-US normalizer factory.

    PAD-US ROI calls proved too large/unreliable for wide buffers during the
    Janus probe, so builders query a small point-context buffer and the
    normalizer records exactly which buffer produced the counts — the number
    is meaningless without it.
    """
    from collections import Counter

    def normalize_padus(data: dict) -> dict:
        records = data.get("records", [])
        owners = Counter(record.get("owner_type") or "Unknown" for record in records)
        designations = Counter(
            record.get("designation_type") or "Unspecified" for record in records
        )
        ranked = sorted(records, key=lambda row: row.get("gis_acres") or 0, reverse=True)
        return {
            "query_buffer_miles": query_buffer_miles,
            "count": data.get("total_records", len(records)),
            "owner_types": dict(owners.most_common()),
            "designation_types": dict(designations.most_common()),
            "largest_records": ranked[:25],
            "records_truncated": max(0, len(records) - 25),
            "warnings": data.get("warnings", []),
        }

    return normalize_padus


# The exact limitation sentence the Janus contract test asserts on. USACE
# results identify the district and delineation region only — treating them
# as wetland presence or a CWA jurisdictional determination would be wrong.
USACE_LIMITATION = (
    "District and delineation-region context only. This does not show "
    "wetland presence or make a Clean Water Act jurisdictional determination."
)


def normalize_usace(data: dict) -> dict:
    """USACE regulatory context: district + wetland delineation regions."""
    districts = data.get("regulatory_districts", {})
    regions = data.get("wetland_regions", {})
    subregions = data.get("wetland_subregions", {})
    warnings: list = []
    for section in (districts, regions, subregions):
        warnings.extend(section.get("warnings", []))
    return {
        "districts": districts.get("districts", []),
        "wetland_regions": regions.get("regions", []),
        "wetland_subregions": subregions.get("subregions", []),
        "warnings": warnings,
        "limitation": USACE_LIMITATION,
    }


def normalize_nepa_assist(data: dict) -> dict:
    """EPA NEPAssist: proximity flags grouped by resource category."""
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


def normalize_noaa_habitat(data: dict) -> dict:
    """NOAA West Coast critical habitat (salmon / steelhead / eulachon...).

    Complements IPaC: NMFS species are consulted through NOAA Fisheries, not
    USFWS, so a Columbia River site can look clean in IPaC's USFWS lens while
    sitting inside NMFS-designated critical habitat. Kept separately so the
    UI can name the consulting agency. Response shape verified live against
    nepa-mcp 0.1.1: {habitats: [...], total, species_count, designation_count}.
    """
    habitats = data.get("habitats") or data.get("critical_habitats") or []
    return {
        "count": data.get("total", len(habitats)),
        "species_count": data.get("species_count"),
        "designation_count": data.get("designation_count"),
        "habitats": habitats,
        "warnings": data.get("warnings", []),
    }


def normalize_efh_salmon(data: dict) -> dict:
    """NOAA Essential Fish Habitat (salmon) under the Magnuson-Stevens Act.

    EFH consultation is a separate statutory hook from ESA Section 7 — a
    federal action in mapped salmon EFH triggers it even for healthy,
    unlisted runs (exactly the Hanford Reach fall-Chinook situation).
    Response shape verified live: {watersheds: [{huc_8, huc_8_name,
    chinook_efh, coho_efh, ...}], total} — rows are HUC-8 watershed flags.
    """
    watersheds = data.get("watersheds") or data.get("areas") or []
    return {
        "count": data.get("total", len(watersheds)),
        "watersheds": watersheds,
        "warnings": data.get("warnings", []),
    }


def normalize_flood_zones(data: dict) -> dict:
    """FEMA NFHL flood zones near the point (small-radius context).

    The project already carries per-site ``flood_zone`` / ``in_sfha`` for the
    46,759-record corpus; this normalizer exists for CURATED screening sites
    (Hanford parcels, coal plants) that are not corpus records. Zone counts
    summarize which zones exist within the query radius — they do not place
    the facility footprint inside any zone. Zero zones frequently means the
    area is UNMAPPED in NFHL (true for most of Hanford), not flood-free —
    the ``total_zones`` + warnings fields keep that distinction renderable.
    Response shape verified live: {zones: [...], total_zones,
    summary: {sfha_count, sfha_percentage, zone_counts}, truncated}.
    """
    summary = data.get("summary") or {}
    return {
        "count": data.get("total_zones", len(data.get("zones") or [])),
        "zone_counts": summary.get("zone_counts", {}),
        "sfha_count": summary.get("sfha_count", 0),
        "sfha_percentage": summary.get("sfha_percentage"),
        "truncated": bool(data.get("truncated")),
        "warnings": data.get("warnings", []),
    }


def normalize_gbif(data: dict) -> dict:
    """GBIF threatened-species occurrence records inside the buffer.

    Occurrence data is presence-only citizen/museum evidence: a record is a
    sighting, absence of records is absence of OBSERVERS, not of species.
    Counts are summarized by species so one well-photographed hawk doesn't
    read as 400 species. Response shape verified live: {occurrences: [...],
    total_occurrences, unique_species, summary: {by_threat_status}}.
    """
    occurrences = data.get("occurrences") or []
    by_species: dict = {}
    for occ in occurrences:
        name = (
            occ.get("common_name")
            or occ.get("scientific_name")
            or occ.get("species")
            or "Unidentified"
        )
        by_species[name] = by_species.get(name, 0) + 1
    top = sorted(by_species.items(), key=lambda kv: kv[1], reverse=True)
    summary = data.get("summary") or {}
    return {
        "occurrence_count": data.get("total_occurrences", len(occurrences)),
        "species_count": data.get("unique_species", len(by_species)),
        "by_threat_status": summary.get("by_threat_status", {}),
        "top_species": [
            {"species": name, "occurrences": n} for name, n in top[:15]
        ],
        "warnings": data.get("warnings", []),
    }


# ---------------------------------------------------------------------------
# Source matrix runner — the generic loop the Janus builder pioneered:
# for each source, load its nepa-mcp server module once, then screen every
# site through the cache -> timeout -> normalize chain, converting per-site
# failures into explicit 'unavailable' records instead of aborting the batch.
# ---------------------------------------------------------------------------

class SourceDef:
    """One tabular screening source.

    Attributes
    ----------
    key:        Output/cache key for this source (e.g. ``"ipac"``,
                ``"efh_salmon"``). Unique within a builder.
    server:     nepa-mcp server module name to load (e.g. ``"efh"``). Several
                sources may share one server.
    function:   Attribute name of the callable on the loaded server module.
    normalize:  Callable trimming the raw response to the renderable record.
    invoke:     ``invoke(fn, site) -> raw`` — adapts the site row to the
                tool's signature (buffer naming differs across servers:
                ``buffer_miles`` vs ``radius_miles`` vs extra args).
    """

    def __init__(
        self,
        key: str,
        server: str,
        function: str,
        normalize: Callable[[dict], dict],
        invoke: Callable[[Callable[..., Any], Mapping[str, Any]], Any],
    ) -> None:
        self.key = key
        self.server = server
        self.function = function
        self.normalize = normalize
        self.invoke = invoke


def purge_server_src_namespace() -> int:
    """Drop nepa-mcp server-private ``src``/``src.*`` entries from sys.modules.

    Every nepa-mcp 0.1.1 server ships its OWN ``src`` package, and whichever
    server loads first claims the ``src`` name in sys.modules — after which
    every other server's ``import src.apis.<x>_api`` resolves against the
    WRONG server's package and fails (observed 2026-08-24: a cache-resumed
    run loaded map_composer before the tabular servers, and every later
    tabular load died with "No module named 'src.apis.ipac_api'", which was
    then CACHED as unavailable). Purging before each load makes every server
    re-import its own namespace; already-loaded modules keep their bound
    references, so this is safe to call between loads. Returns the number of
    entries removed (for the regression test)."""
    stale = [m for m in sys.modules if m == "src" or m.startswith("src.")]
    for name in stale:
        del sys.modules[name]
    return len(stale)


def _isolated_load_server_module(server_name: str):
    from nepa_mcp.loader import load_server_module

    purge_server_src_namespace()
    return load_server_module(server_name)


def run_source_matrix(
    sites: Sequence[Mapping[str, Any]],
    source_defs: Iterable[SourceDef],
    cache_path_fn: Callable[[str, str], Path],
    use_cache: bool = True,
    module_loader: Optional[Callable[[str], Any]] = None,
) -> dict:
    """Screen every site through every source; return {site_id: {key: record}}.

    ``module_loader`` exists so unit tests can inject fake server modules and
    exercise the caching / failure-isolation contract without Python 3.12 or
    the network. Production callers leave it None and get nepa-mcp's loader
    (wrapped in the src-namespace purge — see purge_server_src_namespace).
    """
    if module_loader is None:
        verify_nepa_mcp_version()
        module_loader = _isolated_load_server_module

    results: dict = {site["id"]: {} for site in sites}
    for source in source_defs:
        try:
            module = module_loader(source.server)
            function = getattr(module, source.function)
        except Exception as exc:  # a missing server must not kill the others
            log.exception("loading server %s failed", source.server)
            for site in sites:
                path = cache_path_fn(site["id"], source.key)
                # A loader failure must never clobber previously collected
                # evidence: serve the existing cache when one exists, and
                # persist the unavailable record only for sites that had
                # nothing yet (Codex PR #22 round 2, P1).
                cached = read_cache(path) if use_cache else None
                results[site["id"]][source.key] = (
                    cached if cached is not None else cache_error_at(path, exc)
                )
            continue
        for site in sites:
            path = cache_path_fn(site["id"], source.key)
            try:
                results[site["id"]][source.key] = cached_query(
                    path,
                    f"{site['id']} / {source.key}",
                    lambda fn=function, row=site, src=source: src.invoke(fn, row),
                    source.normalize,
                    use_cache,
                )
            except Exception as exc:  # one upstream must not kill the other evidence
                log.exception("%s / %s failed", site["id"], source.key)
                results[site["id"]][source.key] = cache_error_at(path, exc)
    return results


# ---------------------------------------------------------------------------
# Map Composer GeoJSON — one combined FeatureCollection per site, collected
# layer-by-layer so a single flaky layer degrades to a status entry instead
# of sinking the whole map package.
# ---------------------------------------------------------------------------

def collect_map_geojson(
    site: Mapping[str, Any],
    layers: Sequence[str],
    buffer_miles: float,
    cache_file: Path,
    layer_buffer_overrides: Optional[Mapping[str, float]] = None,
    use_cache: bool = True,
    limitations: str = (
        "Reference-point screening only; project parcel unknown. "
        "Unavailable layers are not no-hit findings."
    ),
    module_loader: Optional[Callable[[str], Any]] = None,
) -> dict:
    """Collect the requested Map Composer layers into one FeatureCollection.

    ``layer_buffer_overrides`` lets a builder shrink expensive layers (the
    Janus probe found PAD-US/federal_lands ROI calls unreliable beyond a
    point-context buffer) without giving up the wide buffer everywhere else.
    """
    if use_cache:
        cached = read_cache(cache_file)
        if cached is not None:
            log.info("cache hit  %s", cache_file.name)
            return cached

    if module_loader is None:
        module_loader = _isolated_load_server_module

    overrides = dict(layer_buffer_overrides or {})
    module = module_loader("map_composer")
    combined_features: list = []
    statuses: dict = {}
    for layer in layers:
        layer_buffer_miles = overrides.get(layer, buffer_miles)
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
            "buffer_miles": buffer_miles,
            "layers": statuses,
            "limitations": limitations,
        },
    }
    _atomic_write(cache_file, json.dumps(result, separators=(",", ":")))
    return result


def summarize_map_package(geojson: Mapping[str, Any]) -> dict:
    """Small header block the UIs render before offering the full package."""
    statuses = geojson.get("metadata", {}).get("layers", {})
    return {
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
