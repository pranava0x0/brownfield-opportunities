"""Parcel-owner enrichment — verify each site's owner against public
state/county cadastral (parcel) records by point-in-polygon.

The problem (see CLAUDE.md structural gap #7)
---------------------------------------------
There is NO free nationwide parcel-owner dataset. Commercial sources (Regrid,
CoreLogic) are paid; the only universal public owner signal we had was FUDS
`current_owner` (a USACE owner-TYPE category, ~26% of FUDS). But MANY states
publish a free statewide parcels layer with owner NAMES via ArcGIS REST. This
connector queries those, per state, by the site's lat/lon, and fills
`current_owner` + `current_owner_source` for any program.

Verified 2026-06-19 (spot-check): NC OneMap `NC1Map_Parcels` layer 1 (polygons)
returns `ownname` by point — e.g. Ore Knob Mine Superfund site → owner
"REEVES THOMAS G & EVELYN", and its `gisacres` (147.1) matched our acreage
(148.2), confirming the right parcel. Owners seen: individuals, "CITY OF
GREENSBORO", "CSX RAILROAD". Misses are federal megasites (military
reservations aren't in county parcels) and ACRES address-geocodes that land
just off-parcel.

Design — a per-state registry is the single extensibility point
---------------------------------------------------------------
`STATE_PARCEL_SOURCES[ST]` holds the endpoint + field names for one state.
Going broad = add one verified entry per state. Coverage is intentionally
incremental: states with a clean free statewide layer first (NC proven; TX
StratMap via TxGIO pending host confirmation in the deploy env — `feature.
tnris.org` did not resolve from the dev sandbox 2026-06-19).

Resumable, like the flood backfill: seeds prior owners from the on-disk output,
does up to `--parcel-limit` NEW point queries (cached), writes the merged set.
Run narrow first: `python3 refresh.py --source parcel-owner --parcel-state NC
--parcel-limit 50`. The base-class disk cache makes re-runs cheap.

Output: docs/data/parcel-owner.json — [{id, program, current_owner,
current_owner_source, parcel_acreage, parcel_id}]. All schema-clean. The parcel
acreage answers "how many acres are actually available for development" at the
parcel level and is the ONLY land-size signal for ACRES brownfields, whose
source ships no acreage column at all (CLAUDE.md gap #1). A site can now be
emitted with a parcel_acreage even when the parcel carries no owner name.

Records resolved in runs BEFORE parcel_acreage was emitted are backfilled for
free: their parcel response is already cached (it always contained the acreage,
we just discarded it), so a cache-only "acreage upgrade" pass fills them in
without a new query, without spending `--parcel-limit`, and without touching
the network. Only owner-resolved records qualify; tombstones stay untouched.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import requests

from connectors.base import Connector

log = logging.getLogger("connector.parcel_owner")

# Per-state public statewide parcel sources. Each: an ArcGIS REST layer that
# supports point-intersect queries and exposes an owner-name field.
#   base        — FeatureServer/MapServer layer URL (…/<n>)
#   owner_field — attribute holding the owner name
#   acreage_field / parcel_id_field — for validation / provenance (optional)
#   source      — provenance label written to current_owner_source
# ADD A STATE: verify its endpoint + field names with a point query, then drop
# one entry here. That is the only change needed to extend coverage.
STATE_PARCEL_SOURCES: dict[str, dict[str, Any]] = {
    # Verified 2026-06-19. "secure" path needs no token for Query.
    "NC": {
        "base": "https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1",
        "owner_field": "ownname",
        "acreage_field": "gisacres",
        "parcel_id_field": "parno",
        "source": "NC OneMap (NC1Map statewide parcels)",
    },
    # Verified 2026-06-19 — Montana Cadastral (MT Dept. of Revenue ORION). Point
    # query returned owner "ARCO ENVIRONMENTAL REMEDIATION LLC" for the Anaconda
    # Smelter Superfund site (the correct PRP), with GISAcres matching.
    "MT": {
        "base": "https://gisservicemt.gov/arcgis/rest/services/MSDI_Framework/Parcels/MapServer/0",
        "owner_field": "OwnerName",
        "acreage_field": "GISAcres",
        "parcel_id_field": "PARCELID",
        "source": "Montana Cadastral (MT Dept. of Revenue)",
    },
    # Verified 2026-06-19 — Wisconsin V8 Statewide Parcel Map (DOA). Use the
    # DYNAMIC service (the DW_Map_Cached tile service doesn't support Query).
    "WI": {
        "base": "https://uadnrmaps.wi.gov/arcgis/rest/services/DW_Map_Dynamic/EN_County_Tax_Parcels_WTM_Ext_Dynamic_L16/MapServer/0",
        "owner_field": "OWNERNME1",
        "acreage_field": "GISACRES",
        "parcel_id_field": "PARCELID",
        "source": "WI V8 Statewide Parcels (WI DOA)",
    },
    # Verified 2026-07-05 — NJ Parcels & MOD-IV Composite (NJOGIS). Point query
    # at a Camden ACRES site hit CALC_ACRE 1.92 / PAMS_PIN 0408_1279.01_8. Owner
    # (OWNER_NAME) is frequently blank in the composite, so many NJ records land
    # as acreage-only (which the parcel_acreage-without-owner path handles).
    "NJ": {
        "base": "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0",
        "owner_field": "OWNER_NAME",
        "acreage_field": "CALC_ACRE",
        "parcel_id_field": "PAMS_PIN",
        "source": "NJOGIS (Parcels & MOD-IV Composite of NJ)",
    },
    # Verified 2026-07-05 — VT Statewide Standardized Parcels (VCGI). Sample
    # owner "WEST NANCY"; acreage is ACRESGL (grand-list acres, 0 → dropped).
    "VT": {
        "base": "https://services1.arcgis.com/BkFxaEFNwHqX3tAw/arcgis/rest/services/FS_VCGI_OPENDATA_Cadastral_VTPARCELS_poly_standardized_parcels_SP_v1/FeatureServer/0",
        "owner_field": "OWNER1",
        "acreage_field": "ACRESGL",
        "parcel_id_field": "MAPID",
        "source": "VCGI (VT Statewide Standardized Parcels)",
    },
    # Verified 2026-07-05 — CT CAMA & Parcel Layer 2024 (CT GIS Office). Sample
    # owner "CACCHIONE ROBERT" / Land_Acres 1.13 / Parcel_ID 134-41A.
    "CT": {
        "base": "https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest/services/Connecticut_CAMA_and_Parcel_Layer_2024/FeatureServer/0",
        "owner_field": "Owner",
        "acreage_field": "Land_Acres",
        "parcel_id_field": "Parcel_ID",
        "source": "CT GIS Office (Connecticut CAMA & Parcel Layer 2024)",
    },
    # Verified 2026-07-05 — MassGIS Standardized Property Tax Parcels. Lot size
    # is LOT_SIZE + a per-record LOT_UNITS ("Acres" 2.28M / "Sq. Ft." 264k), so
    # it uses the acreage_units_field/_map conversion below. Owner OWNER1.
    "MA": {
        "base": "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0",
        "owner_field": "OWNER1",
        "acreage_field": "LOT_SIZE",
        "acreage_units_field": "LOT_UNITS",
        "acreage_units_map": {"ACRES": 1.0, "SQ. FT.": 1.0 / 43560.0},
        "parcel_id_field": "LOC_ID",
        "source": "MassGIS (Standardized Property Tax Parcels)",
    },
    # NY "Tax Parcels Public" layer 0 is municipal boundaries and the public
    # parcels carry no owner — dropped.
    # TX StratMap (TxGIO). Endpoint CONFIRMED current as of 2026-06-19
    # (tnris.org/stratmap/land-parcels.html) but `feature.tnris.org` was
    # unreachable from BOTH the dev sandbox socket and WebFetch — a network
    # restriction here, not a dead host. Enable + verify the owner field name
    # in the deploy environment (best guess OWNER_NAME, unconfirmed).
    # "TX": {
    #     "base": "https://feature.tnris.org/arcgis/rest/services/Parcels/stratmap25_land_parcels_48/MapServer/0",
    #     "owner_field": "OWNER_NAME",
    #     "acreage_field": "GIS_ACRES",
    #     "parcel_id_field": "PROP_ID",
    #     "source": "TX StratMap (TxGIO statewide land parcels)",
    # },
}

_PROGRAM_FILES = ["superfund-npl", "epa-acres", "dod-fuds", "dod-brac"]


class ParcelOwner(Connector):
    slug = "parcel-owner"
    # Reads the per-program files (lat/lon + state), so run after producers.
    run_order = 500

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        p.add_argument("--parcel-state", default=None,
                       help="Only query this state code (e.g. NC). Default: all covered states.")
        p.add_argument("--parcel-limit", type=int, default=200,
                       help="Max NEW point queries this run (resumable; cache makes re-runs cheap). 0 = unlimited.")

    # ---- site loading -----------------------------------------------------
    def _load_sites(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        data_dir = self.OUTPUT_DIR
        for slug in _PROGRAM_FILES:
            path = data_dir / f"{slug}.json"
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text())
            except Exception as e:  # noqa: BLE001
                log.warning("could not read %s: %s", path.name, e)
                continue
            for r in payload.get("sites", []):
                if r.get("lat") is not None and r.get("lon") is not None and r.get("state"):
                    out.append(r)
        return out

    # ---- cache key (shared by the query + the free acreage-upgrade pass) ---
    @staticmethod
    def _cache_key(src: dict[str, Any], lat: float, lon: float) -> dict[str, Any]:
        # Stable cache key on rounded coords so tiny float drift still hits cache.
        return {"src": src["source"], "lat": round(lat, 6), "lon": round(lon, 6)}

    def _cache_exists(self, src: dict[str, Any], lat: float, lon: float) -> bool:
        """True when this coord's parcel response is already on disk — the
        acreage-upgrade pass only touches cached responses so it never spends
        the query budget or hits the network."""
        return self.cache_path(self._cache_key(src, lat, lon)).exists()

    # ---- per-site parcel query -------------------------------------------
    def _query_owner(self, src: dict[str, Any], lat: float, lon: float,
                     use_cache: bool) -> dict[str, Any] | None:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": ",".join(
                f for f in (src["owner_field"], src.get("acreage_field"),
                            src.get("acreage_units_field"), src.get("parcel_id_field")) if f
            ),
            "returnGeometry": "false",
            "f": "json",
        }
        data = self.http_get_json(f"{src['base']}/query", params, use_cache=use_cache,
                                  cache_key=self._cache_key(src, lat, lon))
        feats = data.get("features") or []
        if not feats:
            return None
        attrs = feats[0].get("attributes") or {}
        owner = attrs.get(src["owner_field"])
        owner = str(owner).strip() if owner and str(owner).strip() else None
        # Parcel acreage answers "how many acres are actually available for
        # development" and is the only land-size signal for ACRES sites.
        acreage: float | None = None
        af = src.get("acreage_field")
        if af and attrs.get(af) is not None:
            try:
                raw = float(attrs[af])
                # Some layers report lot size in mixed units per-record (e.g.
                # MassGIS LOT_SIZE + LOT_UNITS = "Acres" | "Sq. Ft."). When an
                # acreage_units_field is configured, convert to acres via the
                # source's multiplier map; an UNKNOWN unit code yields None
                # rather than a silently-wrong number.
                mult: float | None = 1.0
                uf = src.get("acreage_units_field")
                if uf:
                    umap = src.get("acreage_units_map") or {}
                    ucode = str(attrs.get(uf) or "").strip().upper()
                    mult = umap.get(ucode)
                if mult is None:
                    acreage = None
                else:
                    a = round(raw * mult, 2)
                    acreage = a if a > 0 else None
            except (TypeError, ValueError):
                acreage = None
        pid: str | None = None
        pf = src.get("parcel_id_field")
        if pf and attrs.get(pf) not in (None, ""):
            pid = str(attrs[pf]).strip() or None
        # A feature with neither an owner name nor parcel acreage is no signal.
        if owner is None and acreage is None:
            return None
        return {"owner": owner, "parcel_acreage": acreage, "parcel_id": pid}

    # ---- main -------------------------------------------------------------
    def fetch_records(self, args: argparse.Namespace, use_cache: bool) -> list[dict[str, Any]]:
        only_state = (getattr(args, "parcel_state", None) or "").upper() or None
        limit = getattr(args, "parcel_limit", 200)

        covered = set(STATE_PARCEL_SOURCES)
        if only_state:
            covered &= {only_state}
        if not covered:
            log.error("no covered states selected (have: %s)", sorted(STATE_PARCEL_SOURCES))
            return []

        # Seed prior owners from on-disk output so progress is never lost.
        seeded: dict[str, dict[str, Any]] = {r["id"]: r for r in self.existing_records() if r.get("id")}
        log.info("seeded %d owners from existing output", len(seeded))

        sites = [s for s in self._load_sites() if s.get("state") in covered]
        log.info("%d candidate sites in covered states %s", len(sites), sorted(covered))

        new_queries = 0
        hits = 0
        upgraded = 0
        for s in sites:
            sid = s.get("id")
            if not sid:
                continue
            # Skip any site already ATTEMPTED in a prior run — whether it
            # resolved to an owner OR is a null-owner tombstone. Keying on
            # `sid in seeded` (not `.get("current_owner")`) is load-bearing:
            # the output serializes with exclude_none, so a tombstone comes
            # back from existing_records() as just {id, program} with no
            # current_owner. The old `.get("current_owner")` check was falsy
            # for tombstones, so every known no-match re-consumed the budget
            # on every run. Guarded by test_seeded_null_owner_is_not_requeried.
            if sid in seeded:
                # FREE acreage-upgrade: owner-resolved records from runs before
                # parcel_acreage was emitted lack it, but their parcel response
                # is already cached (with gisacres). Backfill from cache only —
                # never a new query, never the budget, never the network. Only
                # owner-resolved records qualify; tombstones (no parcel) are left
                # untouched so they stay un-requeried.
                rec = seeded[sid]
                if rec.get("current_owner") and rec.get("parcel_acreage") is None:
                    src = STATE_PARCEL_SOURCES.get(s.get("state"))
                    try:
                        latf, lonf = float(s["lat"]), float(s["lon"])
                    except (TypeError, ValueError):
                        continue
                    if src and self._cache_exists(src, latf, lonf):
                        try:
                            res = self._query_owner(src, latf, lonf, use_cache=True)
                        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
                            res = None
                        if res and res.get("parcel_acreage") is not None:
                            rec["parcel_acreage"] = res["parcel_acreage"]
                            rec["parcel_id"] = res.get("parcel_id")
                            upgraded += 1
                continue
            if limit and new_queries >= limit:
                break
            src = STATE_PARCEL_SOURCES[s["state"]]
            try:
                res = self._query_owner(src, float(s["lat"]), float(s["lon"]), use_cache)
                new_queries += 1
            except (requests.ConnectionError, requests.Timeout) as e:
                log.warning("[%s] network error (%s) — skipping", sid, type(e).__name__)
                continue
            except requests.HTTPError as e:
                log.warning("[%s] HTTP error (%s) — skipping", sid, e)
                continue
            if res is None:
                # Record the attempt with a null owner so we don't re-query it
                # every run (tombstone — "tried, no parcel match").
                seeded[sid] = {"id": sid, "program": s.get("program"),
                               "current_owner": None, "current_owner_source": None}
                continue
            rec: dict[str, Any] = {"id": sid, "program": s.get("program")}
            if res.get("owner"):
                rec["current_owner"] = res["owner"]
                hits += 1
            if res.get("parcel_acreage") is not None:
                rec["parcel_acreage"] = res["parcel_acreage"]
                rec["parcel_id"] = res.get("parcel_id")
            # Cite the state layer whenever we got ANY parcel data — owner OR
            # acreage-only (NJ's composite is frequently owner-blank) — so the
            # detail panel shows a precise source, not the generic fallback.
            if "current_owner" in rec or "parcel_acreage" in rec:
                rec["current_owner_source"] = src["source"]
            seeded[sid] = rec

        log.info("parcel-owner: %d new queries, %d owner hits, %d acreage upgrades "
                 "(from cache) this run; %d total records",
                 new_queries, hits, upgraded, len(seeded))
        # Emit every record; null-owner tombstones keep the resumable set honest.
        return list(seeded.values())
