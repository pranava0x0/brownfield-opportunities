"""Connector ABC. Each data source implements `fetch_records()`.

The driver (`refresh.py`) handles caching infra, schema validation, and
output writing. Connectors only own their fetch + normalize logic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests

USER_AGENT = "BrownfieldOpportunities/0.2 (research; static dashboard)"
REQUEST_TIMEOUT_S = 60
REQUEST_DELAY_S = 1.5

log = logging.getLogger("connector")


class Connector(ABC):
    """Base class for a data-source connector."""

    #: Slug used in CLI / registry / cache filenames. Override.
    slug: str = ""
    #: Human-readable label written into the output payload's `source` field.
    source_label: str = ""
    #: URL describing the upstream source (about page / docs).
    source_url: str = ""

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
