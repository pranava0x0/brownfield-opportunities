"""EPA ECHO (Enforcement & Compliance History Online) enrichment.

Open enforcement actions, recent violations, or unpaid penalties make a site
materially untransactable — high-signal field for due diligence. This
enrichment joins ECHO's facility-level enforcement summary onto every
program-level record we already track (Superfund, ACRES, FUDS, BRAC) by
querying the public ECHO REST service.

Two-step lookup per site:

1. **Site ID → ECHO Registry ID.** ECHO's facility universe is keyed by
   `REGISTRY_ID` (FRS) — not EPA's Superfund EPA_ID, ACRES property ID,
   or the DOD identifiers we use elsewhere. We pivot via
   `echo_rest_services.get_facilities`, which accepts a Superfund site ID
   (`p_si`) for Superfund and a name + state pair for the others. The first
   hit's `RegistryID` is our pivot.
2. **Registry ID → enforcement summary.** The same `get_facilities`
   response carries the headline enforcement counters (5-year inspections,
   formal/informal actions, total penalties, last-violation date,
   current-compliance bucket). We don't need to walk to the heavier DFR
   endpoint — those summary fields already cover the buyer-due-diligence
   surface we want to render.

This is an *enrichment-only* connector — no new sites. Output records carry
`id`, `program`, and an `enforcement` dict with the fields above. The
frontend lazy-loads the file, joins onto `sitesById` by `id`, and renders
an "Enforcement & compliance" block in the detail panel.

Performance: 1 HTTP request per site at the public 1.5 s rate limit ⇒
~25 minutes for 1k sites unbounded. Default `--echo-limit 100 --echo-status F,D`
keeps a single run ~2.5 min; cache makes incremental coverage cheap.

References:
- ECHO REST services: https://echo.epa.gov/tools/web-services
- Detailed Facility Report (DFR): https://echo.epa.gov/detailed-facility-report
- Field glossary: https://echo.epa.gov/help/reports/dfr-data-dictionary
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import requests

from connectors.base import Connector

log = logging.getLogger("connector.epa_echo")

ECHO_GET_FACILITIES_URL = (
    "https://echodata.epa.gov/echo/echo_rest_services.get_facilities"
)
ECHO_DFR_URL = "https://echo.epa.gov/detailed-facility-report"

# Columns we want back from get_facilities. ECHO defaults to a small slice;
# we explicitly request the enforcement-history fields the detail panel renders.
# `qcolumns` is a CSV of column NUMBERS (not names) — these are stable per
# ECHO's documented schema. Keeping the request narrow keeps the response small.
ECHO_QCOLUMNS = (
    # Identity
    "1,2,3,4,5,"     # Registry ID, Name, Address, City, State
    # Compliance + enforcement
    "12,17,18,19,"   # Compliance status, last inspection date, last formal/informal action
    "23,24,25,26,"   # 5yr inspections, 5yr informal, 5yr formal, 5yr penalties
    # Programs
    "30"             # active program list (CWA, CAA, RCRA, ...)
)

DEFAULT_LIMIT = 100
DEFAULT_PER_PAGE_TIMEOUT = 60
TRANSIENT_HTTP_CODES = {404, 408, 429, 500, 502, 503, 504}


def _safe_int(v: Any) -> int | None:
    if v is None or v == "" or v == "--":
        return None
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> float | None:
    if v is None or v == "" or v == "--":
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "--":
        return None
    return s


class EpaEcho(Connector):
    slug = "epa-echo"
    source_label = "EPA ECHO (Enforcement & Compliance History Online)"
    source_url = "https://echo.epa.gov/"

    # Reads docs/data/superfund-npl.json (and other per-program files in the
    # future) — must run after the producer connectors have written.
    run_order = 250

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument(
                "--limit",
                type=int,
                default=None,
                help="Cap the number of records (default: unlimited).",
            )
        p.add_argument(
            "--echo-limit",
            type=int,
            default=DEFAULT_LIMIT,
            help=f"Max sites to query ECHO for per run (default: {DEFAULT_LIMIT}). "
                 "Cache makes incremental runs cheap.",
        )
        p.add_argument(
            "--echo-skip",
            type=int,
            default=0,
            help="Skip the first N sites — for resumable batch coverage.",
        )
        p.add_argument(
            "--echo-status",
            default="F,D",
            help="Comma-separated NPL status codes to enrich (default: F,D — "
                 "Final + Deleted; the policy-relevant universe). "
                 "Use 'all' to ignore status.",
        )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        sites = self._load_superfund_sites()
        if not sites:
            log.error("no Superfund sites loaded — run --source superfund-npl first")
            return []

        status_filter = self._parse_status_filter(getattr(args, "echo_status", "F,D"))
        if status_filter is not None:
            sites = [s for s in sites if s.get("npl_status_code") in status_filter]
            log.info("status filter %s: %d eligible sites", sorted(status_filter), len(sites))

        # Sort by acreage desc so the largest, most-notable sites get enriched
        # first under a `--echo-limit` cap.
        sites.sort(
            key=lambda s: (
                s.get("acreage") is None,
                -(s.get("acreage") or 0),
                (s.get("name") or "").lower(),
            )
        )
        skip = max(0, getattr(args, "echo_skip", 0) or 0)
        take = getattr(args, "echo_limit", DEFAULT_LIMIT) or 0
        target_sites = sites[skip: skip + take] if take else sites[skip:]
        log.info("enriching %d sites (skip=%d, take=%d)",
                 len(target_sites), skip, take or -1)

        records: list[dict[str, Any]] = []
        skipped_no_match = 0
        for i, site in enumerate(target_sites, 1):
            sid = site.get("id")
            epa_id = site.get("epa_id") or sid
            if not sid or not epa_id:
                continue
            try:
                facility = self._lookup_facility(epa_id, use_cache=use_cache)
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else None
                if code in TRANSIENT_HTTP_CODES:
                    log.warning("[%s] ECHO HTTP %s — skipping", epa_id, code)
                    continue
                raise
            if not facility:
                skipped_no_match += 1
                log.info("[%s] no ECHO match", epa_id)
                continue
            enforcement = self.normalize_enforcement(facility)
            if enforcement is None:
                # Facility found but no enforcement signal — still emit so
                # the UI can show "no recorded enforcement" rather than
                # "Not available."
                enforcement = {
                    "registry_id": _safe_str(facility.get("RegistryID")),
                    "current_compliance": "No enforcement on file",
                }
            records.append({
                "id": sid,
                "program": "superfund",
                "epa_id": epa_id,
                "enforcement": enforcement,
            })
            log.info("[%d/%d] %s → registry=%s actions5=%s",
                     i, len(target_sites), epa_id,
                     enforcement.get("registry_id"),
                     enforcement.get("formal_actions_5yr"))

        if skipped_no_match:
            log.info("%d sites had no ECHO match", skipped_no_match)
        if getattr(args, "limit", None):
            records = records[: args.limit]
        log.info("enriched %d sites with ECHO data", len(records))
        return records

    # ----- helpers -----

    def _load_superfund_sites(self) -> list[dict[str, Any]]:
        path = Path(__file__).resolve().parent.parent / "docs" / "data" / "superfund-npl.json"
        if not path.exists():
            return []
        return json.loads(path.read_text()).get("sites", [])

    @staticmethod
    def _parse_status_filter(raw: str | None) -> set[str] | None:
        if not raw or raw.lower() == "all":
            return None
        return {s.strip() for s in raw.split(",") if s.strip()}

    def _lookup_facility(self, epa_id: str, use_cache: bool) -> dict[str, Any] | None:
        """Query ECHO for the facility matching the Superfund EPA_ID.

        ECHO's facility universe is keyed by REGISTRY_ID; the `p_si` parameter
        accepts a Superfund Site ID (which is what EPA_ID maps to in the
        Superfund program). The first matching facility's row is what we
        return — duplicates here are rare and the first row is the canonical
        FRS-mastered one.
        """
        params = {
            "output": "JSON",
            "p_si": epa_id,
            "qcolumns": ECHO_QCOLUMNS,
            "responseset": "1",
        }
        try:
            data = self.http_get_json(
                ECHO_GET_FACILITIES_URL,
                params=params,
                use_cache=use_cache,
                cache_key={"echo_si": epa_id},
            )
        except RuntimeError as e:
            # ECHO returns `{"Error": ...}` for some malformed queries; the
            # base class re-raises these as RuntimeError. Treat as "no match"
            # so the run continues.
            log.warning("[%s] ECHO error: %s", epa_id, e)
            return None
        results = self._extract_results(data)
        if not results:
            return None
        return results[0]

    @staticmethod
    def _extract_results(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Pull the `Results` row list out of ECHO's nested JSON envelope.

        ECHO wraps everything in `{"Results": {"QueryID": ..., "Facilities": [...]}}`.
        We've also seen `{"Results": {"Results": [...]}}` from some endpoints —
        defensively check both shapes.
        """
        results = data.get("Results") or {}
        for key in ("Facilities", "Results", "FacilityList"):
            v = results.get(key)
            if isinstance(v, list):
                return v
        return []

    @staticmethod
    def normalize_enforcement(facility: dict[str, Any]) -> dict[str, Any] | None:
        """Map an ECHO facility row to our compact enforcement dict.

        Returns None when none of the enforcement-relevant fields carry a
        value — caller decides whether to emit a "no enforcement on file"
        placeholder or skip entirely.
        """
        registry_id = _safe_str(facility.get("RegistryID"))
        # ECHO uses both `Insp5yr` and `EpaInspections` across endpoints — be
        # tolerant. Same for the formal/informal naming.
        inspections_5yr = _safe_int(
            facility.get("Insp5yr") or facility.get("EpaInspections")
        )
        formal_actions_5yr = _safe_int(
            facility.get("FEA5yr") or facility.get("EpaFormalActions") or facility.get("FormalActions5yr")
        )
        informal_actions_5yr = _safe_int(
            facility.get("IEA5yr") or facility.get("EpaInformalActions") or facility.get("InformalActions5yr")
        )
        penalties_5yr_usd = _safe_float(
            facility.get("Penalties") or facility.get("PenaltyAmount") or facility.get("EpaTotalPenalties")
        )
        last_violation = _safe_str(
            facility.get("LastViolation") or facility.get("DateLastViolation")
        )
        last_inspection = _safe_str(
            facility.get("LastInspection") or facility.get("DateLastInspection")
        )
        compliance = _safe_str(
            facility.get("CurrentCompliance")
            or facility.get("CurrVioFlag")
            or facility.get("CurrentSnc")
        )
        programs_raw = _safe_str(facility.get("Programs") or facility.get("ActiveProgramList"))
        programs = (
            [p.strip() for p in programs_raw.split(",") if p.strip()]
            if programs_raw
            else None
        )

        # If literally every signal is absent there's no value in emitting.
        # `is not None` rather than truthiness — `0 inspections` is a
        # meaningful "clean record" signal, not "no data on file".
        numeric_signals = [
            inspections_5yr,
            formal_actions_5yr,
            informal_actions_5yr,
            penalties_5yr_usd,
        ]
        text_signals = [last_violation, last_inspection, compliance, programs]
        if not any(v is not None for v in numeric_signals) and not any(text_signals):
            return None

        out: dict[str, Any] = {}
        if registry_id:
            out["registry_id"] = registry_id
            out["dfr_url"] = f"{ECHO_DFR_URL}?fid={registry_id}"
        if inspections_5yr is not None:
            out["inspections_5yr"] = inspections_5yr
        if formal_actions_5yr is not None:
            out["formal_actions_5yr"] = formal_actions_5yr
        if informal_actions_5yr is not None:
            out["informal_actions_5yr"] = informal_actions_5yr
        if penalties_5yr_usd is not None:
            out["penalties_5yr_usd"] = round(penalties_5yr_usd, 2)
        if last_violation:
            out["last_violation_date"] = last_violation
        if last_inspection:
            out["last_inspection_date"] = last_inspection
        if compliance:
            out["current_compliance"] = compliance
        if programs:
            out["programs"] = programs
        return out
