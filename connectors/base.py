"""Connector ABC. Each data source implements `fetch_records()`.

The driver (`refresh.py`) handles caching infra, schema validation, and
output writing. Connectors only own their fetch + normalize logic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import socket
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests

USER_AGENT = "BrownfieldOpportunities/0.2 (research; static dashboard)"
REQUEST_TIMEOUT_S = 60
REQUEST_DELAY_S = 1.5

log = logging.getLogger("connector")


def prefer_ipv4(enabled: bool = True) -> None:
    """Restrict outbound DNS resolution to A records.

    Every EPA host (`www.epa.gov`, `cumulis.epa.gov`, `semspub.epa.gov`) and
    several ArcGIS / Census hosts resolve AAAA-first. On a network whose IPv6
    path is blackholed — a SYN to the v6 address draws no RST, just silence —
    urllib3 walks `getaddrinfo()` serially and burns the FULL
    `REQUEST_TIMEOUT_S` on IPv6 before falling back to IPv4. Measured on an
    identical URL: `curl` 0.59 s (it implements Happy Eyeballs, RFC 8305) vs
    `requests` 60.3 s, both HTTP 200. That tax turned a 21-minute document
    backfill into a projected 6.6 hours before it was root-caused on
    2026-08-04/05.

    This is opt-out via `--allow-ipv6` because it is a global, process-wide
    monkeypatch: it is the right default for this project's hosts, but a
    future IPv6-only endpoint would need it off.

    Idempotent — calling it repeatedly will not stack wrappers.
    """
    if not enabled:
        return
    if getattr(socket.getaddrinfo, "_ipv4_pinned", False):
        return
    original = socket.getaddrinfo

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    ipv4_only._ipv4_pinned = True  # type: ignore[attr-defined]
    ipv4_only._original = original  # type: ignore[attr-defined]
    socket.getaddrinfo = ipv4_only
    log.debug("DNS resolution pinned to IPv4")


class Connector(ABC):
    """Base class for a data-source connector."""

    #: Slug used in CLI / registry / cache filenames. Override.
    slug: str = ""
    #: Human-readable label written into the output payload's `source` field.
    source_label: str = ""
    #: URL describing the upstream source (about page / docs).
    source_url: str = ""
    #: Lower runs first in `--all` mode. Producer connectors stay at the
    #: default 100; enrichment connectors that read another connector's
    #: per-program JSON file (e.g. infra_proximity) override to 200/300 so
    #: they run after the files they depend on are written.
    run_order: int = 100
    #: True only for connectors that own a complete program inventory. An
    #: empty response from one of these sources is an outage, never a valid
    #: payload to overwrite the deployed data file with.
    authoritative_inventory: bool = False

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # --- subclass hooks ---

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        """Register connector-specific CLI flags. Default: no flags."""
        return

    @abstractmethod
    def fetch_records(self, args: argparse.Namespace, use_cache: bool) -> list[dict[str, Any]]:
        """Fetch + normalize. Returns plain dicts matching schema.SiteRecord."""

    # --- shared infra ---

    OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"

    def existing_output_path(self) -> Path:
        """Where this connector's prior output JSON lives (`docs/data/<slug>.json`)."""
        return self.OUTPUT_DIR / f"{self.slug}.json"

    def existing_records(self) -> list[dict[str, Any]]:
        """Return the records list from the prior output, or [] if absent/malformed.

        Used by enrichment connectors in `--missing-only` mode to (a) figure
        out which IDs are already covered and (b) preserve them in the
        merged write so a partial backfill never DROPS existing records.
        """
        path = self.existing_output_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("[%s] could not read existing output: %s", self.slug, e)
            return []
        sites = data.get("sites") or []
        return sites if isinstance(sites, list) else []

    def existing_ids(self) -> set[str]:
        """Set of `id` values already in the prior output. Empty when none."""
        return {r.get("id") for r in self.existing_records() if r.get("id")}

    @staticmethod
    def merge_records_by_id(
        new_records: list[dict[str, Any]],
        existing_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge two record lists keyed by `id`. New wins on collision.

        Used by `--missing-only` mode: the connector fetches only sites it
        hasn't covered yet, then merges those new records with everything
        already on disk so the write doesn't truncate the file.
        """
        by_id: dict[str, dict[str, Any]] = {}
        for r in existing_records:
            rid = r.get("id")
            if rid:
                by_id[rid] = r
        for r in new_records:
            rid = r.get("id")
            if rid:
                by_id[rid] = r
        return list(by_id.values())

    def cache_path(self, key_obj: Any) -> Path:
        key = hashlib.sha256(
            json.dumps(key_obj, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        return self.cache_dir / f"{self.slug}_{key}.json"

    def http_get_json(
        self,
        url: str,
        params: dict[str, Any],
        use_cache: bool = True,
        cache_key: Any = None,
    ) -> dict[str, Any]:
        """GET JSON with disk-backed caching. Cache key = url+params unless overridden."""
        path = self.cache_path(cache_key if cache_key is not None else {"url": url, "params": params})
        if use_cache and path.exists():
            log.info("cache hit  %s", path.name)
            return json.loads(path.read_text())

        log.info("fetching   %s", path.name)
        time.sleep(REQUEST_DELAY_S)
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"API error from {url}: {data['error']}")
        path.write_text(json.dumps(data))
        log.info("cached     %s", path.name)
        return data

    def http_get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        use_cache: bool = True,
        cache_key: Any = None,
    ) -> str:
        """GET arbitrary text (HTML, XML) with disk-backed caching.

        Used by enrichment connectors that scrape EPA / DOD profile pages
        which don't expose a JSON API. Failures (4xx/5xx) raise
        requests.HTTPError; the caller is responsible for catching and
        deciding whether to skip the record or abort the run.
        """
        path = self.cache_path(
            cache_key if cache_key is not None else {"url": url, "params": params or {}}
        )
        # Use a distinct extension so JSON / text caches don't collide for the same key.
        path = path.with_suffix(".txt")
        if use_cache and path.exists():
            log.info("cache hit  %s", path.name)
            return path.read_text()

        log.info("fetching   %s", path.name)
        time.sleep(REQUEST_DELAY_S)
        resp = requests.get(
            url,
            params=params or {},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        text = resp.text
        path.write_text(text)
        log.info("cached     %s", path.name)
        return text
