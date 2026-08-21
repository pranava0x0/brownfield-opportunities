"""EPA NPL Superfund Site Boundaries connector.

Source: ArcGIS FeatureServer hosted by EPA.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from connectors.base import Connector
from connectors.geom import polygon_acreage
from connectors.text import collapse_sentinel

log = logging.getLogger("connector.superfund_npl")

EPA_FEATURE_SERVER = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "FAC_Superfund_Site_Boundaries_EPA_Public/FeatureServer/0"
)
QUERY_URL = EPA_FEATURE_SERVER + "/query"
LAYER_META_URL = EPA_FEATURE_SERVER  # `?f=json` returns coded-value domains

EPA_PROFILE_URL_TEMPLATE = (
    "https://cumulis.epa.gov/supercpad/CurSites/csitinfo.cfm?id={epa_id}"
)

# Static fallback used when layer metadata can't be fetched (offline tests,
# EPA outage). Kept in sync with the layer's coded-value domain via the
# `_fetch_coded_value_labels` call at runtime.
NPL_STATUS_LABELS: dict[str, str] = {
    "A": "Site is Part of NPL Site",
    "D": "Deleted from the Final NPL",
    "F": "Currently on the Final NPL",
    "N": "Not on the NPL",
    "O": "Not Valid Site or Incident",
    "P": "Proposed for NPL",
    "R": "Removed from Proposed",
    "S": "Pre-proposal Site",
    "W": "Withdrawn",
}

OUTFIELDS = [
    "OBJECTID",
    "EPA_ID",
    "SITE_NAME",
    "NPL_STATUS_CODE",
    "FEDERAL_FACILITY_DETER_CODE",
    "REGION_CODE",
    "STREET_ADDR_TXT",
    "CITY_NAME",
    "COUNTY",
    "STATE_CODE",
    "ZIP_CODE",
    "GIS_AREA",
    "GIS_AREA_UNITS",
    "URL_ALIAS_TXT",
    "FEATURE_INFO_URL",
    "LAST_CHANGE_DATE",
    "ORIGINAL_CREATION_DATE",
]

# Fraction of dropped-during-normalize features above which we warn loudly.
DROP_RATIO_WARN_THRESHOLD = 0.5


class SuperfundNPL(Connector):
    slug = "superfund-npl"
    authoritative_inventory = True
    source_label = "EPA NPL Superfund Site Boundaries (Public)"
    source_url = (
        "https://hub.arcgis.com/datasets/EPA::"
        "npl-superfund-site-boundaries-epa-public-2022/about"
    )

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap the number of sites (default: unlimited — all NPL).",
        )
        p.add_argument(
            "--include-no-acreage",
            action="store_true",
            default=True,
            help="Include sites with non-areal units / null GIS_AREA (default: on).",
        )
        p.add_argument(
            "--no-include-no-acreage",
            dest="include_no_acreage",
            action="store_false",
            help="Exclude sites without acreage (legacy behavior).",
        )
        p.add_argument(
            "--dedupe-children",
            action="store_true",
            default=True,
            help="Drop NPL status 'A' (sub-site) rows from main list (default: on).",
        )
        p.add_argument(
            "--no-dedupe-children",
            dest="dedupe_children",
            action="store_false",
            help="Keep all rows including sub-sites.",
        )

    # ----- main entry point -----

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        layer_meta = self._fetch_layer_metadata(use_cache=use_cache)
        fed_labels = self._coded_value_labels(layer_meta, "FEDERAL_FACILITY_DETER_CODE")
        npl_labels = {**NPL_STATUS_LABELS,
                      **self._coded_value_labels(layer_meta, "NPL_STATUS_CODE")}
        raw_features = self._fetch_features(use_cache=use_cache)
        features = self._merge_by_epa_id(raw_features)

        records: list[dict[str, Any]] = []
        dropped = 0
        for feat in features:
            rec = self.normalize(
                feat,
                federal_facility_labels=fed_labels,
                npl_status_labels=npl_labels,
                include_no_acreage=args.include_no_acreage,
            )
            if rec is None:
                dropped += 1
                continue
            records.append(rec)

        total = len(features)
        if total > 0 and dropped / total > DROP_RATIO_WARN_THRESHOLD:
            log.warning(
                "dropped %d/%d features during normalize (%.0f%%) — investigate source",
                dropped, total, 100 * dropped / total,
            )

        if args.dedupe_children:
            records = self._dedupe_status_a(records)

        # Sort: acreage-bearing sites first (desc), then no-acreage alphabetically.
        records.sort(
            key=lambda r: (
                r["acreage"] is None,
                -(r["acreage"] or 0),
                (r.get("name") or "").lower(),
            )
        )

        if args.limit is not None:
            records = records[: args.limit]

        log.info("normalized %d records (dropped %d)", len(records), dropped)
        return records

    # ----- fetch helpers -----

    def _fetch_features(self, use_cache: bool) -> list[dict[str, Any]]:
        """Page through the FeatureServer (max 2000 records/request)."""
        all_features: list[dict[str, Any]] = []
        page_size = 2000
        offset = 0
        while True:
            params = {
                "where": "1=1",  # everything; we filter in normalize()
                "outFields": ",".join(OUTFIELDS),
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": str(page_size),
                "resultOffset": str(offset),
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            }
            data = self.http_get_json(QUERY_URL, params, use_cache=use_cache)
            page = data.get("features", [])
            log.info("page offset=%d got=%d", offset, len(page))
            if not page:
                break
            all_features.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        log.info("retrieved %d total features", len(all_features))
        return all_features

    def _fetch_layer_metadata(self, use_cache: bool) -> dict[str, Any]:
        """Pull layer metadata (one request, cached) — source of coded-value domains."""
        try:
            return self.http_get_json(
                LAYER_META_URL,
                {"f": "json"},
                use_cache=use_cache,
                cache_key={"meta": "layer"},
            )
        except Exception as e:
            log.warning("could not fetch layer metadata: %s — using static labels", e)
            return {}

    @staticmethod
    def _coded_value_labels(meta: dict[str, Any], field_name: str) -> dict[str, str]:
        """Extract one field's coded-value domain. Strips trailing whitespace from labels."""
        for field in meta.get("fields", []) or []:
            if field.get("name") == field_name:
                domain = field.get("domain") or {}
                coded = domain.get("codedValues") or []
                labels = {
                    str(cv["code"]): str(cv["name"]).strip()
                    for cv in coded if "code" in cv
                }
                log.info("decoded %d %s labels", len(labels), field_name)
                return labels
        return {}

    # ----- multi-polygon merge -----

    @staticmethod
    def _merge_by_epa_id(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Combine features sharing one EPA_ID into a single feature.

        Some Superfund sites (e.g. Portland Harbor) are stored as many
        fragmented polygons sharing one EPA_ID. We collapse them so the
        dashboard shows one site per ID:
          - rings: concatenated across all features
          - GIS_AREA: summed (when units match), else first non-null
          - other attrs: first non-null wins
        Features without EPA_ID pass through untouched.
        """
        by_id: dict[str, dict[str, Any]] = {}
        passthrough: list[dict[str, Any]] = []
        for feat in features:
            attrs = feat.get("attributes", {}) or {}
            epa_id = attrs.get("EPA_ID")
            if not epa_id:
                passthrough.append(feat)
                continue
            existing = by_id.get(epa_id)
            if existing is None:
                # Deep-ish copy: clone attributes + ring list, keep ring contents.
                by_id[epa_id] = {
                    "attributes": dict(attrs),
                    "geometry": {"rings": list((feat.get("geometry") or {}).get("rings") or [])},
                }
                continue
            ex_attrs = existing["attributes"]
            ex_rings = existing["geometry"]["rings"]
            new_rings = (feat.get("geometry") or {}).get("rings") or []
            ex_rings.extend(new_rings)

            # Sum acreage when units match; otherwise drop to None so we don't mix.
            if (
                ex_attrs.get("GIS_AREA_UNITS") == attrs.get("GIS_AREA_UNITS")
                and ex_attrs.get("GIS_AREA") is not None
                and attrs.get("GIS_AREA") is not None
            ):
                ex_attrs["GIS_AREA"] = float(ex_attrs["GIS_AREA"]) + float(attrs["GIS_AREA"])
            elif ex_attrs.get("GIS_AREA") is None:
                ex_attrs["GIS_AREA"] = attrs.get("GIS_AREA")
                ex_attrs["GIS_AREA_UNITS"] = attrs.get("GIS_AREA_UNITS")

            # Prefer the first non-null value for everything else.
            for k, v in attrs.items():
                if k in ("GIS_AREA", "GIS_AREA_UNITS"):
                    continue
                if ex_attrs.get(k) in (None, "") and v not in (None, ""):
                    ex_attrs[k] = v

        merged = list(by_id.values()) + passthrough
        if len(merged) < len(features):
            log.info("merged %d features → %d unique EPA_IDs", len(features), len(merged))
        return merged

    # ----- normalize -----

    @staticmethod
    def envelope_center(rings: list[list[list[float]]]) -> tuple[float, float]:
        xs: list[float] = []
        ys: list[float] = []
        for ring in rings:
            for x, y in ring:
                xs.append(x)
                ys.append(y)
        if not xs:
            raise ValueError("empty geometry")
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    def normalize(
        self,
        feature: dict[str, Any],
        federal_facility_labels: dict[str, str] | None = None,
        npl_status_labels: dict[str, str] | None = None,
        include_no_acreage: bool = True,
    ) -> dict[str, Any] | None:
        a = feature.get("attributes", {})
        geom = feature.get("geometry") or {}
        rings = geom.get("rings")
        if not rings:
            return None

        units = a.get("GIS_AREA_UNITS")
        raw_area = a.get("GIS_AREA")
        # `units` is the source's hint about what GIS_AREA means. Acres /
        # Square Miles → use it. Anything else (Miles for linear features,
        # null for sites EPA never tagged) → compute acreage from the
        # polygon rings ourselves. The rings are present for every NPL
        # feature; without this fallback, ~8% of records ship with
        # `acreage: null` even though we have enough geometry to compute it.
        acres: float | None
        if units == "Acres" and raw_area is not None:
            acres = round(float(raw_area), 1)
        elif units == "Square Miles" and raw_area is not None:
            acres = round(float(raw_area) * 640.0, 1)
        else:
            acres = polygon_acreage(rings)

        # A computed area of zero means the rings collapsed (degenerate or
        # sub-precision geometry), not that the site occupies no land. Zero
        # is a *claim*: it sorts as the smallest site in the table and feeds
        # 0 into the acreage component of all three scoring lenses, whereas
        # None correctly leaves the site unscored on land. 50 records shipped
        # `acreage: 0.0` this way before it was caught on 2026-08-09.
        if acres is not None and acres <= 0:
            acres = None

        if acres is None and not include_no_acreage:
            return None

        try:
            lon, lat = self.envelope_center(rings)
        except ValueError:
            return None

        status_code = a.get("NPL_STATUS_CODE")
        epa_id = a.get("EPA_ID")
        profile_url = (
            a.get("URL_ALIAS_TXT")
            or a.get("FEATURE_INFO_URL")
            or (EPA_PROFILE_URL_TEMPLATE.format(epa_id=epa_id) if epa_id else None)
        )

        fed_code = a.get("FEDERAL_FACILITY_DETER_CODE")
        fed_label = (federal_facility_labels or {}).get(fed_code or "", fed_code)
        labels = npl_status_labels or NPL_STATUS_LABELS

        # Records without an EPA_ID still get a synthetic id so the frontend
        # can key by it. We hash the OBJECTID + name as a stable fallback.
        record_id = epa_id or f"NPL-O{a.get('OBJECTID')}"
        return {
            "id": record_id,
            "program": "superfund",
            "epa_id": epa_id,
            "name": a.get("SITE_NAME"),
            "acreage": acres,
            "npl_status_code": status_code,
            "npl_status": labels.get(status_code or "", "Unknown"),
            "federal_facility": fed_label,
            "federal_facility_code": fed_code,
            "region": a.get("REGION_CODE"),
            "address": collapse_sentinel(a.get("STREET_ADDR_TXT")),
            "city": collapse_sentinel(a.get("CITY_NAME")),
            "county": collapse_sentinel(a.get("COUNTY")),
            "state": a.get("STATE_CODE"),
            "zip": a.get("ZIP_CODE"),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "profile_url": profile_url,
            "last_updated": a.get("LAST_CHANGE_DATE"),
        }

    # ----- dedupe -----

    @staticmethod
    def _dedupe_status_a(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Drop status-'A' sub-sites whose parent is in the dataset.

        EPA assigns sub-sites IDs that share a stem with their parent; without
        an explicit parent column we use the conservative rule: drop any
        status-'A' site whose name starts with another (non-A) site's name.

        Sub-sites without a discoverable parent are kept (so we never silently
        lose data) and tagged with `parent_epa_id = None`. Parents accumulate
        a `children` list of `{id, name}` so the UI can surface the
        relationship without re-fetching the dropped sub-site rows.
        """
        non_a_by_name = {
            (r.get("name") or "").lower(): r
            for r in records
            if r.get("npl_status_code") != "A"
        }
        kept: list[dict[str, Any]] = []
        merged = 0
        for r in records:
            if r.get("npl_status_code") != "A":
                kept.append(r)
                continue
            name = (r.get("name") or "").lower()
            parent = None
            for parent_name, parent_rec in non_a_by_name.items():
                if name.startswith(parent_name) and name != parent_name:
                    parent = parent_rec
                    break
            if parent is not None:
                r["parent_epa_id"] = parent.get("epa_id")
                # Attach a compact summary onto the parent for UI surfacing.
                parent.setdefault("children", []).append({
                    "id": r.get("id") or r.get("epa_id"),
                    "name": r.get("name"),
                })
                merged += 1
                continue  # drop from main list
            kept.append(r)
        if merged:
            log.info("deduped %d status-'A' sub-sites under parents", merged)
        return kept
