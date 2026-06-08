"""IRA Energy Community enrichment.

Marks each site as inside or outside an Inflation Reduction Act (IRA)
"energy community" by point-in-polygon containment against the two
authoritative DOE / NETL geographic layers (2024 edition).

Why this matters for the data-center / energy-infra siting use case: a
clean-energy project (solar, wind, storage, or behind-the-meter gas paired
with a data center) built inside an energy community earns a **+10
percentage-point bonus** on the IRA section 45 Production Tax Credit or
section 48 Investment Tax Credit. On a $1B behind-the-meter generation
build that bonus is worth ~$100M — a material IRR lever, and exactly the
financial sweetener that pushed the 2025-2026 wave of hyperscale DCs onto
retired coal-plant sites (Conesville, Widows Creek, Homer City all sit in
coal-closure energy communities).

Two of the three IRA energy-community categories are clean, unambiguous
GEOGRAPHIC layers and are the ones we assert here:

1. **Coal closure** — census tracts where a coal mine closed after 1999
   OR a coal-fired electric generating unit retired after 2009, PLUS any
   directly adjacent tract. Source: NETL `2024_Coal_Closure_Energy_Communities`
   (4,325 tract polygons). Every feature in this layer IS a qualifying
   community; the `mine_closure` / `generator_closure` / `adjacent_to_closure`
   flags say WHY.

2. **Fossil-fuel employment** — Metropolitan / non-Metropolitan Statistical
   Areas with >=0.17% direct fossil-fuel employment (or >=25% local tax
   revenue from fossil extraction) AND unemployment at or above the prior
   year's national average. Source: NETL
   `2024_MSAs_NonMSAs_that_are_Energy_Communities` (901 county polygons,
   filtered to `ec_qual_status='Yes'`).

The THIRD category — **brownfield sites** (CERCLA sec. 101(39)) — is
deliberately NOT auto-asserted here even though our entire dataset is
brownfield-adjacent. The statutory brownfield definition EXCLUDES sites on
the National Priorities List and carries Bona-Fide-Prospective-Purchaser
nuances that our coarse `program` flag can't resolve, so asserting it
blindly would overstate eligibility on ~1,900 Superfund NPL records. The
two geographic categories are defensible and source-cited; the brownfield
overlay is left to the user's counsel.

Precedence when a site falls in both: **coal_closure wins** — it's the more
localized (tract vs. county) and higher-confidence signal.

This is an *enrichment-only* connector — reads the per-program JSON files
from disk, computes containment for each site, and writes
`docs/data/ira-energy-community.json`. The frontend lazy-loads it and joins
onto `sitesById` by id.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector
from connectors.spatial import PolygonIndex

log = logging.getLogger("connector.ira_energy_community")

NETL_BASE = (
    "https://arcgis.netl.doe.gov/server/rest/services/Hosted/"
)
COAL_CLOSURE_URL = (
    NETL_BASE + "2024_Coal_Closure_Energy_Communities/FeatureServer/0/query"
)
FFE_URL = (
    NETL_BASE + "2024_MSAs_NonMSAs_that_are_Energy_Communities/FeatureServer/0/query"
)
PAGE_SIZE = 2000

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


def _yes(v: Any) -> bool:
    """NETL ships Yes/No flags as strings — tolerant truthy check."""
    return isinstance(v, str) and v.strip().upper() in ("YES", "Y", "TRUE", "1")


class IraEnergyCommunity(Connector):
    slug = "ira-energy-community"
    source_label = "DOE NETL IRA Energy Communities (2024 edition)"
    source_url = "https://energycommunities.gov/energy-community-tax-credit-bonus/"

    # Run AFTER all producer connectors and after opportunity-zone (350).
    # IRA energy-community designations update ~annually; cache makes
    # re-runs cheap.
    run_order = 355

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument(
                "--limit",
                type=int,
                default=None,
                help="Cap the number of enriched records (default: unlimited).",
            )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        sites = list(self._load_sites())
        if not sites:
            log.error(
                "no per-program JSON files found in %s — run --all (or each "
                "producer connector individually) before --source ira-energy-community",
                self._data_dir(),
            )
            return []
        log.info("loaded %d sites across %d program files",
                 len(sites), self._loaded_program_count)

        # `--missing-only`: drop sites already in the existing output.
        missing_only = bool(getattr(args, "missing_only", False))
        if missing_only:
            covered = self.existing_ids()
            if covered:
                before = len(sites)
                sites = [s for s in sites if s.get("id") not in covered]
                log.info("--missing-only: %d/%d sites already covered, %d remaining",
                         before - len(sites), before, len(sites))
            if not sites:
                existing = self.existing_records()
                log.info("--missing-only: nothing to fetch; returning %d existing records",
                         len(existing))
                return existing

        coal_idx = self._build_coal_closure_index(use_cache=use_cache)
        ffe_idx = self._build_ffe_index(use_cache=use_cache)
        if coal_idx.polygon_count == 0 and ffe_idx.polygon_count == 0:
            log.error("both IRA indexes empty after fetch — aborting")
            return []
        log.info("[ira-energy-community] indexed %d coal-closure + %d FFE polygons",
                 coal_idx.polygon_count, ffe_idx.polygon_count)

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        in_ec = 0
        coal_hits = 0
        ffe_hits = 0
        program_counts: dict[str, int] = {}
        for site in sites:
            sid = site.get("id")
            program = site.get("program")
            lat = site.get("lat")
            lon = site.get("lon")
            if not sid or not program or lat is None or lon is None:
                skipped_no_geom += 1
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                skipped_no_geom += 1
                continue

            rec: dict[str, Any] = {"id": sid, "program": program}
            coal_hit = coal_idx.containing(lat_f, lon_f)
            ffe_hit = ffe_idx.containing(lat_f, lon_f)

            if coal_hit is not None:
                # coal_closure takes precedence — more localized signal.
                rec["in_energy_community"] = True
                rec["energy_community_type"] = "coal_closure"
                detail = coal_hit.get("detail")
                if detail:
                    rec["energy_community_detail"] = detail
                in_ec += 1
                coal_hits += 1
            elif ffe_hit is not None:
                rec["in_energy_community"] = True
                rec["energy_community_type"] = "fossil_fuel_employment"
                area = ffe_hit.get("area")
                if area:
                    rec["energy_community_detail"] = area
                in_ec += 1
                ffe_hits += 1
            else:
                rec["in_energy_community"] = False

            records.append(rec)
            program_counts[program] = program_counts.get(program, 0) + 1

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        log.info("[ira-energy-community] %d / %d sites in an energy community "
                 "(%d coal-closure, %d fossil-fuel-employment)",
                 in_ec, len(records), coal_hits, ffe_hits)
        log.info("enriched %d records — by program: %s", len(records), program_counts)

        if getattr(args, "limit", None):
            records = records[: args.limit]

        if missing_only:
            existing = self.existing_records()
            merged = self.merge_records_by_id(records, existing)
            log.info("--missing-only: merged %d new + %d existing = %d total",
                     len(records), len(existing), len(merged))
            return merged
        return records

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _data_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "docs" / "data"

    def _load_sites(self) -> Iterable[dict[str, Any]]:
        """Iterate sites across all per-program JSON files that exist on disk."""
        self._loaded_program_count = 0
        for fname in PROGRAM_FILES:
            path = self._data_dir() / fname
            if not path.exists():
                log.info("program file %s missing — skipping", fname)
                continue
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as e:
                log.warning("failed to read %s: %s — skipping", fname, e)
                continue
            for site in payload.get("sites") or []:
                yield site
            self._loaded_program_count += 1

    def _build_coal_closure_index(self, use_cache: bool) -> PolygonIndex:
        """Paginate the NETL coal-closure tract layer and index all polygons.

        Every feature in this layer is a qualifying community; the
        mine/generator/adjacent flags say WHY. We pick the strongest reason
        for the human-readable `detail` (direct closures beat adjacency).
        """
        log.info("[ira-energy-community] fetching coal-closure from %s", COAL_CLOSURE_URL)
        idx = PolygonIndex()
        offset = 0
        while True:
            params = {
                "where": "1=1",
                "outFields": "geoid_tract_2020,mine_closure,generator_closure,"
                             "adjacent_to_closure,state_name,county_name",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometryPrecision": "6",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "f": "json",
            }
            data = self.http_get_json(
                COAL_CLOSURE_URL, params,
                use_cache=use_cache,
                cache_key={"src": "ira_coal_closure", "offset": offset},
            )
            features = data.get("features") or []
            log.info("[ira-energy-community] coal page offset=%d got=%d", offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                rings = geom.get("rings") or []
                if not rings:
                    continue
                a = feat.get("attributes") or {}
                # Strongest reason wins for the human-readable detail.
                if _yes(a.get("mine_closure")):
                    detail = "Coal mine closure"
                elif _yes(a.get("generator_closure")):
                    detail = "Coal generator retirement"
                elif _yes(a.get("adjacent_to_closure")):
                    detail = "Adjacent to coal closure"
                else:
                    detail = None
                attr = {
                    "geoid": a.get("geoid_tract_2020"),
                    "detail": detail,
                }
                idx.add_polygon(rings, attr=attr)
            if len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return idx

    def _build_ffe_index(self, use_cache: bool) -> PolygonIndex:
        """Paginate the NETL MSA/non-MSA fossil-fuel-employment county layer.

        Only counties with `ec_qual_status='Yes'` are energy communities, so
        we filter server-side. The polygon attr carries the statistical-area
        name for the detail panel.
        """
        log.info("[ira-energy-community] fetching FFE from %s", FFE_URL)
        idx = PolygonIndex()
        offset = 0
        while True:
            params = {
                "where": "ec_qual_status='Yes'",
                "outFields": "geoid_cty_2020,ec_qual_status,msa_area_name,"
                             "msa_nmsa_label,state_name",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometryPrecision": "6",
                "resultRecordCount": str(PAGE_SIZE),
                "resultOffset": str(offset),
                "f": "json",
            }
            data = self.http_get_json(
                FFE_URL, params,
                use_cache=use_cache,
                cache_key={"src": "ira_ffe", "offset": offset},
            )
            features = data.get("features") or []
            log.info("[ira-energy-community] ffe page offset=%d got=%d", offset, len(features))
            if not features:
                break
            for feat in features:
                geom = feat.get("geometry") or {}
                rings = geom.get("rings") or []
                if not rings:
                    continue
                a = feat.get("attributes") or {}
                if not _yes(a.get("ec_qual_status")):
                    continue
                attr = {
                    "geoid": a.get("geoid_cty_2020"),
                    "area": a.get("msa_area_name"),
                }
                idx.add_polygon(rings, attr=attr)
            if len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return idx
