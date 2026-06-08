"""EPA ACRES cleanup status + brownfield grant history enrichment.

Two data sources joined onto existing ACRES brownfield records:

1. **ACRES Cleanups FeatureServer** — CA_Status (Completed / In Progress /
   Not Started), Cleanup_Completion_Date, Cleanup_Type per PROPERTY_ID.
   Only ~110 records publicly available (October 2021 snapshot); sparse but
   authoritative for the sites it covers.

2. **EPA Brownfield Grant Awards (Envirofacts BF_GRANT_AWARD)** — dollar
   amounts, award types (Assessment / Cleanup / RLF), grantee, award date,
   keyed by PROPERTY_ID. Falls back gracefully when Envirofacts is
   unavailable (the BF_* table family has historically returned "table not
   available" on the Envirofacts endpoint; we try and log, never crash).

Output: docs/data/acres-cleanup.json as an enrichment payload with records
carrying `{id, cleanup_status, cleanup_complete_date, grant_total_usd,
grant_count, grant_types}`. Frontend lazy-loads via
ensureAcresCleanupLoaded() and merges onto sitesById by id.

run_order = 200 — must run after epa-acres produces epa-acres.json so we
can read the PROPERTY_ID → id mapping.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from connectors.base import Connector

log = logging.getLogger("connector.acres-cleanup")

# ACRES Cleanups FeatureServer — same ArcGIS org as the main ACRES service.
CLEANUPS_QUERY_URL = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
    "ACRES_cleanups_10_19_21/FeatureServer/0/query"
)
CLEANUPS_PAGE_SIZE = 500

CLEANUPS_FIELDS = "*"  # fetch all fields; layer has ~110 records so payload is tiny

# Envirofacts BF_GRANT_AWARD — try bulk first, then per-property fallback.
# If Envirofacts is unavailable (historically returns "table not available"),
# we skip grants and log a warning rather than crashing the run.
ENVIROFACTS_GRANT_URL = "https://data.epa.gov/efservice/BF_GRANT_AWARD"
ENVIROFACTS_PAGE_SIZE = 5000

# Normalise the grant type labels from the source to a clean short set.
GRANT_TYPE_MAP = {
    "assessment": "Assessment",
    "cleanup": "Cleanup",
    "rlf": "RLF",
    "revolving loan fund": "RLF",
    "multi-purpose": "Multi-purpose",
    "job training": "Job Training",
}


def _iso_date(raw: Any) -> str | None:
    """Parse MM/DD/YYYY or YYYY-MM-DD or epoch ms into YYYY-MM-DD."""
    if not raw:
        return None
    s = str(raw).strip()
    # Epoch milliseconds (ArcGIS default)
    if s.isdigit():
        try:
            return datetime.utcfromtimestamp(int(s) / 1000).strftime("%Y-%m-%d")
        except (OSError, ValueError):
            return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _safe_int(v: Any) -> int | None:
    if v is None or v == "" or v == "--":
        return None
    try:
        return int(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


class EpaAcresCleanup(Connector):
    slug = "acres-cleanup"
    source_label = "EPA ACRES Brownfield Cleanup Status & Grant History"
    source_url = (
        "https://www.epa.gov/brownfields/"
        "assessment-cleanup-and-redevelopment-exchange-system-acres"
    )
    run_order = 200  # after epa-acres

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--cleanup-state",
            default=None,
            help="Two-letter state code to limit ACRES cleanup fetch. Default: all.",
        )
        p.add_argument(
            "--skip-grants",
            action="store_true",
            default=False,
            help="Skip the Envirofacts grant-awards fetch (faster for testing).",
        )

    # ----- helpers -----

    def _fetch_cleanups(self, use_cache: bool) -> dict[str, dict]:
        """Fetch ACRES cleanups FeatureServer. Returns {property_id: {...}}."""
        records: dict[str, dict] = {}
        offset = 0
        while True:
            params: dict[str, Any] = {
                "where": "1=1",
                "outFields": CLEANUPS_FIELDS,
                "resultOffset": offset,
                "resultRecordCount": CLEANUPS_PAGE_SIZE,
                "f": "json",
                "returnGeometry": "false",
            }
            cache_key = f"acres_cleanups_{offset}"
            try:
                data = self.http_get_json(CLEANUPS_QUERY_URL, params, cache_key, use_cache)
            except Exception as exc:
                log.warning("ACRES cleanups fetch failed at offset %d: %s", offset, exc)
                break

            features = data.get("features") or []
            for feat in features:
                attrs = feat.get("attributes") or {}
                # ArcGIS returns mixed-case field names (Property_ID, CA_Status, etc.)
                pid = str(attrs.get("Property_ID") or attrs.get("PROPERTY_ID") or "").strip()
                if not pid:
                    continue
                status_raw = (attrs.get("CA_Status") or attrs.get("CA_STATUS") or "").strip()
                status = status_raw if status_raw else None
                records[pid] = {
                    "cleanup_status": status,
                    "cleanup_complete_date": _iso_date(
                        attrs.get("Cleanup_Completion_Date") or attrs.get("COMPLETION_DATE")
                    ),
                    "cleanup_type": (
                        attrs.get("CA_Type") or attrs.get("CLEANUP_TYPE") or ""
                    ).strip() or None,
                    "grantee": (
                        attrs.get("CA_Recipient") or attrs.get("GRANTEE_NAME") or ""
                    ).strip() or None,
                    "award_amount": _safe_int(
                        attrs.get("CA_Number") or attrs.get("AWARD_AMOUNT")
                    ),
                }

            exceeded = data.get("exceededTransferLimit", False)
            if not exceeded or not features:
                break
            offset += CLEANUPS_PAGE_SIZE

        log.info("ACRES cleanups: fetched %d records", len(records))
        return records

    def _fetch_grants_envirofacts(self, use_cache: bool) -> dict[str, list[dict]]:
        """Fetch BF_GRANT_AWARD from Envirofacts. Returns {property_id: [grants]}.
        Logs a warning and returns empty dict if the endpoint is unavailable."""
        grants: dict[str, list[dict]] = {}
        offset = 0
        while True:
            url = f"{ENVIROFACTS_GRANT_URL}/rows/{offset}:{offset + ENVIROFACTS_PAGE_SIZE - 1}/JSON"
            cache_key = f"bf_grant_award_{offset}"
            try:
                data = self.http_get_json(url, {}, cache_key, use_cache)
            except Exception as exc:
                msg = str(exc)
                if "table not" in msg.lower() or "not available" in msg.lower() or "404" in msg:
                    log.warning(
                        "Envirofacts BF_GRANT_AWARD unavailable — skipping grants. "
                        "Error: %s", exc
                    )
                else:
                    log.warning("Envirofacts grant fetch error at offset %d: %s", offset, exc)
                break

            if not isinstance(data, list) or not data:
                break

            for row in data:
                pid = str(row.get("PROPERTY_ID") or row.get("property_id") or "").strip()
                if not pid:
                    continue
                gtype_raw = (
                    row.get("GRANT_TYPE") or row.get("grant_type") or ""
                ).lower().strip()
                gtype = GRANT_TYPE_MAP.get(gtype_raw, gtype_raw.title() or "Other")
                amount = _safe_int(
                    row.get("AWARD_AMOUNT") or row.get("award_amount")
                )
                award_date = _iso_date(
                    row.get("AWARD_DATE") or row.get("award_date")
                )
                grantee = (
                    row.get("GRANTEE_NAME") or row.get("grantee_name") or ""
                ).strip() or None
                grants.setdefault(pid, []).append({
                    "type": gtype,
                    "amount_usd": amount,
                    "date": award_date,
                    "grantee": grantee,
                })
            offset += ENVIROFACTS_PAGE_SIZE

        log.info("Envirofacts grants: fetched data for %d properties", len(grants))
        return grants

    # ----- main entry point -----

    def fetch_records(self, args: argparse.Namespace, use_cache: bool) -> list[dict[str, Any]]:
        # Load the existing ACRES records to get the property_id → id mapping.
        acres_json = Connector.OUTPUT_DIR / "epa-acres.json"
        if not acres_json.exists():
            log.error(
                "epa-acres.json not found — run `--source epa-acres` first. "
                "No cleanup enrichment produced."
            )
            return []

        with acres_json.open() as f:
            acres_payload = json.load(f)

        # Build property_id → ACRES-prefixed id map.
        pid_to_id: dict[str, str] = {}
        pid_to_state: dict[str, str] = {}
        for site in acres_payload.get("sites", []):
            epa_id = site.get("epa_id") or ""
            site_id = site.get("id") or ""
            pid = epa_id.replace("ACRES-", "") if epa_id.startswith("ACRES-") else ""
            if not pid and site_id.startswith("ACRES-"):
                pid = site_id.replace("ACRES-", "")
            if pid:
                pid_to_id[pid] = site_id
                pid_to_state[pid] = site.get("state") or ""

        log.info("Loaded %d ACRES property IDs from epa-acres.json", len(pid_to_id))

        # Apply state filter if requested.
        state_filter = (getattr(args, "cleanup_state", None) or "").upper().strip()
        if state_filter:
            pid_to_id = {
                pid: sid for pid, sid in pid_to_id.items()
                if pid_to_state.get(pid, "").upper() == state_filter
            }
            log.info("State filter %s: %d properties in scope", state_filter, len(pid_to_id))

        # Fetch cleanup status records.
        cleanup_by_pid = self._fetch_cleanups(use_cache)

        # Fetch grants unless skipped.
        skip_grants = getattr(args, "skip_grants", False)
        grants_by_pid: dict[str, list[dict]] = {}
        if not skip_grants:
            grants_by_pid = self._fetch_grants_envirofacts(use_cache)

        # Merge into output records, one per ACRES site that has any data.
        out: list[dict[str, Any]] = []
        covered: set[str] = set()

        for pid, sid in pid_to_id.items():
            cl = cleanup_by_pid.get(pid)
            gr = grants_by_pid.get(pid)
            if not cl and not gr:
                continue

            rec: dict[str, Any] = {"id": sid, "program": "brownfield"}
            if cl:
                rec["cleanup_status"] = cl["cleanup_status"]
                rec["cleanup_complete_date"] = cl["cleanup_complete_date"]

            if gr:
                total = sum(g["amount_usd"] for g in gr if g["amount_usd"] is not None)
                types = sorted({g["type"] for g in gr if g["type"]})
                rec["grant_total_usd"] = total if total else None
                rec["grant_count"] = len(gr)
                rec["grant_types"] = types if types else None

            out.append(rec)
            covered.add(pid)

        log.info(
            "acres-cleanup: %d records with cleanup status, %d with grant data",
            sum(1 for r in out if "cleanup_status" in r),
            sum(1 for r in out if "grant_count" in r),
        )
        return out
