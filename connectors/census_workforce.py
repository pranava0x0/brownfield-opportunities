"""County workforce enrichment from the 2024 ACS 5-Year profile.

The Census API requires CENSUS_API_KEY as of 2026. One request per state
fetches all counties; sites then join locally by state and normalized county.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.county_lookup import CountyIndex

log = logging.getLogger("connector.census_workforce")

ACS_YEAR = 2024
ACS_URL = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/profile"
VARIABLES = "NAME,DP03_0003E,DP03_0034E,DP03_0062E"
PROGRAM_FILES = ["superfund-npl.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json"]
STATE_TO_FIPS = {state: fips for fips, state in CountyIndex.FIPS_TO_STATE.items()}


def normalize_county(name: Any) -> str:
    text = str(name or "").casefold().replace("saint ", "st. ")
    text = re.sub(r"\b(county|parish|borough|census area|municipio|city and borough|city)\b", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _integer(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


class CensusWorkforce(Connector):
    slug = "census-workforce"
    source_label = "U.S. Census Bureau 2024 ACS 5-Year Selected Economic Characteristics"
    source_url = "https://www.census.gov/data/developers/data-sets/acs-5year.html"
    run_order = 370

    @classmethod
    def add_cli_args(cls, parser: argparse.ArgumentParser) -> None:
        existing = {action.dest for action in parser._actions}
        if "limit" not in existing:
            parser.add_argument("--limit", type=int, default=None)

    @staticmethod
    def _data_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "docs" / "data"

    def _load_sites(self) -> Iterable[dict[str, Any]]:
        for filename in PROGRAM_FILES:
            path = self._data_dir() / filename
            if path.exists():
                yield from (json.loads(path.read_text()).get("sites") or [])

    def _fetch_counties(self, state: str, api_key: str, use_cache: bool) -> dict[str, dict[str, Any]]:
        fips = STATE_TO_FIPS[state]
        data = self.http_get_json(
            ACS_URL,
            {"get": VARIABLES, "for": "county:*", "in": f"state:{fips}", "key": api_key},
            use_cache=use_cache,
            cache_key={"src": "acs_workforce", "year": ACS_YEAR, "state": fips},
        )
        if not isinstance(data, list) or len(data) < 2:
            raise RuntimeError(f"ACS returned no county rows for {state}")
        header = data[0]
        out = {}
        for values in data[1:]:
            row = dict(zip(header, values))
            county_name = str(row.get("NAME") or "").split(",", 1)[0]
            out[normalize_county(county_name)] = row
        return out

    def fetch_records(self, args: argparse.Namespace, use_cache: bool) -> list[dict[str, Any]]:
        api_key = os.environ.get("CENSUS_API_KEY")
        if not api_key:
            raise RuntimeError("CENSUS_API_KEY is required by the Census Data API")
        sites = list(self._load_sites())
        if not sites:
            log.error("no program files available; run producer connectors first")
            return []
        needed_states = sorted({s.get("state") for s in sites if s.get("state") in STATE_TO_FIPS})
        counties = {state: self._fetch_counties(state, api_key, use_cache) for state in needed_states}
        records = []
        matched = 0
        for site in sites:
            if not site.get("id") or not site.get("program"):
                continue
            rec = {"id": site["id"], "program": site["program"]}
            row = counties.get(site.get("state"), {}).get(normalize_county(site.get("county")))
            if row:
                rec.update({
                    "workforce_county": str(row["NAME"]).split(",", 1)[0],
                    "workforce_data_year": ACS_YEAR,
                    "county_labor_force": _integer(row.get("DP03_0003E")),
                    "county_construction_employment": _integer(row.get("DP03_0034E")),
                    "county_median_household_income": _integer(row.get("DP03_0062E")),
                })
                rec = {key: value for key, value in rec.items() if value is not None}
                matched += 1
            records.append(rec)
        if getattr(args, "limit", None):
            records = records[: args.limit]
        log.info("[census-workforce] %d / %d sites matched ACS counties", matched, len(records))
        return records
