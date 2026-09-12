"""Nickel supply-chain proximity enrichment.

Joins docs/data/nickel-anchors.json onto every corpus site: how far the site
is from nickel feedstock, from nickel offtake, and from bulk sulfuric acid.
Feeds the two lenses in docs/nickel-score.js.

Why three separate distances rather than one
--------------------------------------------
The two live US nickel refinery projects published opposite siting logic, and
the split is the whole point of the tab:

  * Electra is siting in the southeastern US for a **deep-water port** to land
    imported MHP/MSP plus **proximity to the battery corridor**. Feedstock
    distance is irrelevant to it — the feedstock arrives by ship.
  * Westwin built in landlocked Lawton, Oklahoma inside a **rail** industrial
    park because its feed is domestic ore and recycled batteries.

A single "nearest anchor" number would average those into nonsense. Feedstock,
demand and acid are scored separately and weighted differently per lens.

Ranges are continental, and that is why there is no spatial index
-----------------------------------------------------------------
Unlike every other proximity connector here, the useful range is hundreds of
miles: "how far is this site from the battery corridor" has a real answer at
600 miles and a different one at 60. MAX_DISTANCE_MI is 1,000, a cap that
mostly fires for Alaska, Hawaii and the territories.

The first cut reused `connectors.spatial.PointIndex` with a coarse 2-degree
grid, and at continental range it was wrong twice over. Measured against
brute-force haversine on a 2026-09-08 sample:

  * **Up to 19 miles of projection error.** PointIndex measures with the same
    local-equirectangular projection `SegmentIndex` uses, which its own
    docstring puts at better than 1% in CONUS — a bound written for the
    sub-100-mile nearest-infrastructure queries it was built for. 1% of 900
    miles is 9 miles, and the observed worst case was 18.9.
  * **False nulls at the cap.** Ring expansion gave up before reaching an
    anchor 992 miles away, emitting "nothing within 1,000 mi" for a site that
    had one.

With **sixteen anchors**, an index is the wrong tool: brute force is
46,759 x 16 haversine evaluations, a couple of seconds, and it is exact. The
index earns its keep at 100k substations; it does not here.

Output: docs/data/nickel-anchor-proximity.json, tombstone convention — every
site gets `{id, program}` even with nothing in range.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any, Iterable

from connectors.base import Connector

log = logging.getLogger("connector.nickel_anchor_proximity")

# Continental range — see the module docstring. Only AK/HI/territories exceed
# the default; demand reaches further because the scoring curve does.
#
# These caps MUST cover the range the matching curve in docs/nickel-score.js
# still awards credit over, or the join silently zeroes a term the scorer
# intended to be nonzero. `_nickelScoreDemand` tapers to zero at 1,200 mi, and
# a flat 1,000 mi cap dropped 1,501 sites whose nearest demand anchor sits in
# between (Codex review round 2). Change a curve's far anchor and this table
# changes with it.
MAX_DISTANCE_MI = 1000.0
MAX_DISTANCE_MI_BY_FIELD: dict[str, float] = {
    "nickel_demand_mi": 1200.0,
}
EARTH_RADIUS_MI = 3958.8

ANCHORS_FILE = "nickel-anchors.json"

# Which anchor kinds roll up into which scored distance. Iterated, never
# hardcoded at the call site — same drift-safe discipline as PROGRAM_LEGEND
# (UAT-007): a new kind in schema.NickelAnchor must be added here or it
# silently contributes to nothing.
KIND_GROUPS: dict[str, tuple[str, ...]] = {
    "nickel_feedstock_mi": ("feedstock_mine", "feedstock_recycled"),
    "nickel_demand_mi": ("demand_battery", "demand_stainless"),
    "nickel_acid_mi": ("reagent_acid",),
}

PROGRAM_FILES: list[str] = [
    "superfund-npl.json",
    "epa-acres.json",
    "dod-fuds.json",
    "dod-brac.json",
]


class NickelAnchorProximity(Connector):
    slug = "nickel-anchor-proximity"
    source_label = "Curated US nickel supply-chain anchors (docs/data/nickel-anchors.json)"
    source_url = "https://www.usgs.gov/centers/national-minerals-information-center/nickel-statistics-and-information"

    run_order = 329

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument("--limit", type=int, default=None,
                           help="Cap the number of enriched records.")

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        sites = list(self._load_sites())
        if not sites:
            log.error("no per-program JSON files in %s — run the producers first",
                      self._data_dir())
            return []

        missing_only = bool(getattr(args, "missing_only", False))
        if missing_only:
            covered = self.existing_ids()
            if covered:
                before = len(sites)
                sites = [s for s in sites if s.get("id") not in covered]
                log.info("--missing-only: %d/%d covered, %d remaining",
                         before - len(sites), before, len(sites))
            if not sites:
                return self.existing_records()

        anchors = self._load_anchors()
        if not anchors:
            log.error("anchor catalog empty — run scripts/build_nickel_anchors.py "
                      "first; aborting rather than writing an anchor-less file")
            return self.existing_records() if missing_only else []

        # Catalog audit stamps describe the retained observations, not this
        # compilation run. Keep each typed match traceable without repeating
        # source URLs and notes in tens of thousands of site records.
        self.source_metadata = {"anchors_by_id": {
            a["id"]: {k: a[k] for k in (
                "name", "kind", "source_url", "verified_at", "status",
                "coord_precision", "lat", "lon", "note", "nickel_demand_eligible", "proximity_eligible") if k in a}
            for a in anchors if a.get("id")
        }}

        # One anchor list per scored group, plus one over everything for the
        # "nearest anchor of any kind" label.
        groups = {field: [a for a in self._subset(anchors, kinds)
                          if field != "nickel_demand_mi" or a.get("nickel_demand_eligible") is not False]
                  for field, kinds in KIND_GROUPS.items()}
        every = self._subset(anchors, tuple(
            k for kinds in KIND_GROUPS.values() for k in kinds
        ) + ("refinery_planned", "refinery_historic"))
        log.info("[nickel-anchor-proximity] %d anchors; %s",
                 len(anchors),
                 ", ".join(f"{f}={len(g)}" for f, g in groups.items()))

        records: list[dict[str, Any]] = []
        skipped_no_geom = 0
        matched = 0
        for site in sites:
            sid, program = site.get("id"), site.get("program")
            lat, lon = site.get("lat"), site.get("lon")
            if not sid or not program or lat is None or lon is None:
                skipped_no_geom += 1
                continue
            try:
                lat_f, lon_f = float(lat), float(lon)
            except (TypeError, ValueError):
                skipped_no_geom += 1
                continue

            rec: dict[str, Any] = {"id": sid, "program": program}
            for field, group in groups.items():
                cap = MAX_DISTANCE_MI_BY_FIELD.get(field, MAX_DISTANCE_MI)
                hit = self._nearest(lat_f, lon_f, group)
                if hit is not None and hit[0] <= cap:
                    rec[field] = round(hit[0], 1)
                    if hit[1].get("id"):
                        rec[field.removesuffix("_mi") + "_id"] = hit[1]["id"]
            hit = self._nearest(lat_f, lon_f, every)
            if hit is not None and hit[0] <= MAX_DISTANCE_MI:
                dist_mi, anchor = hit
                rec["nickel_anchor_mi"] = round(dist_mi, 1)
                rec["nickel_anchor_name"] = anchor["name"]
                rec["nickel_anchor_kind"] = anchor["kind"]
                matched += 1
            records.append(rec)

        if skipped_no_geom:
            log.info("skipped %d sites with missing/invalid coordinates", skipped_no_geom)
        log.info("[nickel-anchor-proximity] %d / %d sites within %.0f mi of an anchor",
                 matched, len(records), MAX_DISTANCE_MI)

        if getattr(args, "limit", None):
            records = records[: args.limit]
        if missing_only:
            existing = self.existing_records()
            return self.merge_records_by_id(records, existing)
        return records

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _data_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "docs" / "data"

    def _load_sites(self) -> Iterable[dict[str, Any]]:
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

    def _load_anchors(self) -> list[dict[str, Any]]:
        path = self._data_dir() / ANCHORS_FILE
        if not path.exists():
            log.error("overlay %s missing", ANCHORS_FILE)
            return []
        try:
            return json.loads(path.read_text()).get("sites") or []
        except (OSError, json.JSONDecodeError) as e:
            log.error("failed to read %s: %s", ANCHORS_FILE, e)
            return []

    @staticmethod
    def _subset(anchors: list[dict[str, Any]],
                kinds: tuple[str, ...]) -> list[dict[str, Any]]:
        """Anchors of the given kinds, dropping any row that cannot be used.

        `_nearest` reads lat/lon/name directly, so a hand-edited or otherwise
        malformed row would raise KeyError and abort the whole 46,759-site
        pass. Filtering here (rather than guarding the hot loop) keeps the
        distance computation branch-free and matches what the sibling water
        connector's index build does.
        """
        out: list[dict[str, Any]] = []
        for a in anchors:
            if a.get("kind") not in kinds or a.get("proximity_eligible") is False:
                continue
            if a.get("lat") is None or a.get("lon") is None or not a.get("name"):
                log.warning("anchor %s missing name/lat/lon — skipped",
                            a.get("id") or "<no id>")
                continue
            out.append(a)
        return out

    @staticmethod
    def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance. Exact at continental range, where the local
        equirectangular projection the spatial indexes use is not."""
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = p2 - p1
        dlam = math.radians(lon2 - lon1)
        h = (math.sin(dphi / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2)
        return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))

    @classmethod
    def _nearest(cls, lat: float, lon: float,
                 anchors: list[dict[str, Any]]) -> tuple[float, dict] | None:
        best: tuple[float, dict] | None = None
        for a in anchors:
            d = cls._haversine_mi(lat, lon, a["lat"], a["lon"])
            if best is None or d < best[0]:
                best = (d, a)
        return best
