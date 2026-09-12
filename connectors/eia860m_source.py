"""Shared, pinned EIA-860M vintage and published-link discovery.

Bump the pin only after validating the workbook and rebuilding both producers.
Cache identity includes its URL so an older workbook cannot acquire a new label.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

EIA_INDEX_URL = "https://www.eia.gov/electricity/data/eia860m/"
EIA_860M_URL = EIA_INDEX_URL + "xls/july_generator2026.xlsx"
EIA_WORKBOOK_MONTH = "2026-07"
EIA_CACHE_KEY = {"src": "eia_860m_retired", "url": EIA_860M_URL}
EIA_CACHE_FILENAME = hashlib.sha256(json.dumps(EIA_CACHE_KEY, sort_keys=True).encode()).hexdigest()[:16] + ".bin"
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")


def published_workbooks(html: str) -> list[tuple[dt.date, str]]:
    """Extract actual official XLSX hrefs; never guess archive paths."""
    results: dict[dt.date, str] = {}
    class Links(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag != "a":
                return
            href = dict(attrs).get("href")
            if not href:
                return
            url = urljoin(EIA_INDEX_URL, href)
            parsed = urlparse(url)
            match = re.search(r"/([a-z]+)_generator(\d{4})\.xlsx$", parsed.path, re.I)
            if parsed.scheme != "https" or parsed.hostname != "www.eia.gov" or not match:
                return
            month = match.group(1).lower()
            if month in MONTHS:
                results[dt.date(int(match.group(2)), MONTHS.index(month) + 1, 1)] = url
    Links().feed(html)
    return sorted(results.items(), reverse=True)
