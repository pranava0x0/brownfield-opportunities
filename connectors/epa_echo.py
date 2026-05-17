"""EPA ECHO (Enforcement & Compliance History Online) enrichment.

Open enforcement actions, recent violations, or unpaid penalties make a site
materially untransactable — high-signal field for due diligence. This
enrichment joins ECHO's facility-level enforcement summary onto every
program-level record we already track (Superfund, ACRES, FUDS, BRAC) by
querying the public ECHO REST service.

Two-hop lookup per site (this is the canonical ECHO REST flow — search
returns a server-side QueryID; the actual rows download via `get_qid`):

1. **EPA_ID → QueryID.** ECHO's facility universe is keyed by
   `REGISTRY_ID` (FRS), not EPA's Superfund EPA_ID. We pivot via
   `echo_rest_services.get_facilities` with `p_pid=<EPA_ID>` (program-id
   match — Superfund EPA_IDs are exposed under that filter). The response
   is a query summary plus a `QueryID` that the next call dereferences.
2. **QueryID → facility row(s).** `echo_rest_services.get_qid` with
   `qid=<QueryID>` and `qcolumns=...` returns the actual facility row(s).
   We pull column 6 (REGISTRY_ID), 36 (FAC_COMPLIANCE_STATUS), 41
   (FAC_INSPECTION_COUNT, 5yr), 43 (FAC_DATE_LAST_INSPECTION), 49
   (FAC_INFORMAL_COUNT, 5yr), 54 (FAC_FORMAL_ACTION_COUNT, 5yr), 55
   (FAC_DATE_LAST_FORMAL_ACTION), 60 (FAC_TOTAL_PENALTIES), 61
   (FAC_PENALTY_COUNT), 62 (FAC_DATE_LAST_PENALTY).

This is an *enrichment-only* connector — no new sites. Output records carry
`id`, `program`, and an `enforcement` dict with the fields above. The
frontend lazy-loads the file, joins onto `sitesById` by `id`, and renders
an "Enforcement & compliance" block in the detail panel.

Performance: 2 HTTP requests per site at the public 1.5 s rate limit ⇒
~90 minutes for 1.8k Final/Deleted Superfund sites unbounded. Default
`--echo-limit 100 --echo-status F,D` keeps a single run ~5 min; cache
makes incremental coverage cheap.

History: the v1.11 implementation called `get_facilities` with `p_si`,
which was silently ignored (returned the full 5.6M-row queryset error)
and the wrong qcolumns (1,2,3,4,5,12,17,18,19,23,24,25,26,30 — those
are FAC_NAME / FAC_STREET / FAC_CITY / FAC_STATE / FAC_ZIP /
FAC_INDIAN_SPATIAL_FLG / FAC_LAT / FAC_LONG / AIR_IDS / CAA_PERMIT_TYPES,
none of which are enforcement counters). Result: zero records emitted
across the whole F/D universe. Fixed in v1.11.2.

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
ECHO_GET_QID_URL = (
    "https://echodata.epa.gov/echo/echo_rest_services.get_qid"
)
ECHO_DFR_URL = "https://echo.epa.gov/detailed-facility-report"

# Columns we want back from get_qid. `qcolumns` is a CSV of column NUMBERS
# from the ECHO ResultColumns metadata. Keeping the request narrow keeps
# the response small. Verified against
# echodata.epa.gov/echo/echo_rest_services.metadata?output=JSON 2026-05-05.
ECHO_QCOLUMNS = (
    "1,"      #  1: FAC_NAME
    "4,"      #  4: FAC_STATE
    "6,"      #  6: REGISTRY_ID
    "36,"     # 36: FAC_COMPLIANCE_STATUS
    "41,"     # 41: FAC_INSPECTION_COUNT (5yr)
    "43,"     # 43: FAC_DATE_LAST_INSPECTION
    "49,"     # 49: FAC_INFORMAL_COUNT (5yr)
    "54,"     # 54: FAC_FORMAL_ACTION_COUNT (5yr)
    "55,"     # 55: FAC_DATE_LAST_FORMAL_ACTION
    "60,"     # 60: FAC_TOTAL_PENALTIES (5yr)
    "61,"     # 61: FAC_PENALTY_COUNT
    "62"      # 62: FAC_DATE_LAST_PENALTY
)

DEFAULT_LIMIT = 100
DEFAULT_PER_PAGE_TIMEOUT = 60
TRANSIENT_HTTP_CODES = {404, 408, 429, 500, 502, 503, 504}

# ECHO has aggressive bot detection — sustained 1.5 s/call cadence (the
# project default) trips it within ~100 requests, after which every
# response comes back as `{"Error": {"ErrorMessage": "Your query has been
# identified as a robotic or programmed query, and has been blocked..."}}`.
# We detect this string and treat the response as a transient error: do
# NOT cache it (otherwise the bad response is permanent), back off, and
# retry. If the block persists after BOT_BLOCK_MAX_RETRIES we abort the
# run so the user can come back later — partial cache survives.
BOT_BLOCK_MARKERS = ("robotic or programmed query", "robotic query")
BOT_BLOCK_BACKOFFS_S = (30, 60, 120, 240, 480)  # 5 retries, ~16 min worst case


class _EchoBotBlocked(RuntimeError):
    """Raised when ECHO returns its bot-block error. Caught at the loop
    boundary so a single block can be retried per-call rather than
    aborting the whole run on first sight."""


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


# `get_qid` ships dates as `MM/DD/YYYY`; older snapshots used ISO. Normalize
# to ISO so the frontend renders consistently across enrichment runs.
import re as _re
_DATE_MMDDYYYY = _re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _safe_date(v: Any) -> str | None:
    s = _safe_str(v)
    if s is None:
        return None
    m = _DATE_MMDDYYYY.match(s)
    if m:
        mm, dd, yyyy = m.groups()
        return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"
    return s  # already ISO or some other format — pass through


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

        # `--missing-only`: drop sites already in the existing output before
        # applying skip/take, so the cap targets uncovered work.
        missing_only = bool(getattr(args, "missing_only", False))
        if missing_only:
            covered = self.existing_ids()
            if covered:
                before = len(sites)
                sites = [s for s in sites if s.get("id") not in covered]
                log.info("--missing-only: %d/%d sites already covered, %d remaining",
                         before - len(sites), before, len(sites))

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

        # In `--missing-only` mode, merge the new delta with what's on disk
        # so the file write doesn't truncate previously-enriched records.
        if missing_only:
            existing = self.existing_records()
            merged = self.merge_records_by_id(records, existing)
            log.info("--missing-only: merged %d new + %d existing = %d total",
                     len(records), len(existing), len(merged))
            return merged
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

    @staticmethod
    def _detect_bot_block(data: dict[str, Any]) -> str | None:
        """Return the bot-block ErrorMessage string if `data` is one of
        ECHO's robotic-query rejections, else None.

        The error appears at *both* top-level (`{"Error": {...}}`) and
        nested-under-Results (`{"Results": {"Error": {...}}}`) depending on
        the endpoint. Both shapes have to be checked.
        """
        for block in (data, data.get("Results") or {}):
            err = (block.get("Error") or {}).get("ErrorMessage") if isinstance(block, dict) else None
            if not err:
                continue
            err_lc = err.lower()
            if any(marker in err_lc for marker in BOT_BLOCK_MARKERS):
                return err
        return None

    def _http_get_json_no_botcache(
        self, url: str, params: dict[str, Any], use_cache: bool, cache_key: Any
    ) -> dict[str, Any]:
        """Wrap `http_get_json` with bot-block detection.

        If the response is a bot-block, the cache file (which the base
        class always writes after a 200) is deleted and `_EchoBotBlocked`
        is raised so the retry loop can back off without poisoning future
        cache hits. Non-bot errors are passed through unchanged.
        """
        data = self.http_get_json(url, params=params, use_cache=use_cache, cache_key=cache_key)
        msg = self._detect_bot_block(data)
        if msg:
            # Purge the just-written cache so a retry won't re-serve the bad body.
            try:
                self.cache_path(cache_key).unlink(missing_ok=True)
            except OSError:
                pass
            raise _EchoBotBlocked(msg)
        return data

    def _http_get_with_backoff(
        self, url: str, params: dict[str, Any], use_cache: bool, cache_key: Any
    ) -> dict[str, Any]:
        """Call ECHO with exponential backoff on bot-block responses.

        First attempt is normal; subsequent attempts wait
        BOT_BLOCK_BACKOFFS_S seconds. The cache key is stable, so a
        successful retry caches under the same key the bot-block attempt
        had. After all retries are exhausted the exception propagates and
        the caller aborts the run (loud failure rather than silent
        zero-record output).
        """
        import time as _time
        attempt = 0
        while True:
            try:
                return self._http_get_json_no_botcache(url, params, use_cache, cache_key)
            except _EchoBotBlocked as e:
                if attempt >= len(BOT_BLOCK_BACKOFFS_S):
                    raise
                wait = BOT_BLOCK_BACKOFFS_S[attempt]
                log.warning("ECHO bot-block on %s — backing off %ds (attempt %d/%d)",
                            cache_key, wait, attempt + 1, len(BOT_BLOCK_BACKOFFS_S))
                _time.sleep(wait)
                attempt += 1

    def _lookup_facility(self, epa_id: str, use_cache: bool) -> dict[str, Any] | None:
        """Query ECHO for the facility matching the Superfund EPA_ID.

        Two-hop: `get_facilities?p_pid=<EPA_ID>` returns a `QueryID`; then
        `get_qid?qid=<QueryID>` returns the actual facility row(s). We
        return the first row. Duplicates here are rare for Superfund — the
        same EPA_ID can resolve to >1 ECHO facility when the site spans
        multiple FRS-keyed addresses, but the first row is the canonical
        FRS-mastered one for this program ID.
        """
        # --- Hop 1: program-id search → QueryID
        try:
            search = self._http_get_with_backoff(
                ECHO_GET_FACILITIES_URL,
                params={"output": "JSON", "p_pid": epa_id},
                use_cache=use_cache,
                cache_key={"echo_pid_search": epa_id},
            )
        except RuntimeError as e:
            log.warning("[%s] ECHO get_facilities error: %s", epa_id, e)
            return None
        results_block = search.get("Results") or {}
        if results_block.get("Error"):
            log.warning("[%s] ECHO error: %s",
                        epa_id, results_block["Error"].get("ErrorMessage"))
            return None
        qid = _safe_str(results_block.get("QueryID"))
        try:
            query_rows = int(results_block.get("QueryRows") or 0)
        except (TypeError, ValueError):
            query_rows = 0
        if not qid or query_rows == 0:
            return None

        # --- Hop 2: QueryID → facility row(s)
        try:
            data = self._http_get_with_backoff(
                ECHO_GET_QID_URL,
                params={
                    "output": "JSON",
                    "qid": qid,
                    "qcolumns": ECHO_QCOLUMNS,
                    "responseset": "1",
                },
                use_cache=use_cache,
                # Cache key must NOT include the volatile QueryID — those
                # rotate every call. Key by the stable EPA_ID instead.
                cache_key={"echo_qid_rows": epa_id, "qcolumns": ECHO_QCOLUMNS},
            )
        except RuntimeError as e:
            log.warning("[%s] ECHO get_qid error: %s", epa_id, e)
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
        # ECHO uses different column names across endpoints (`get_qid`
        # returns ObjectName-style keys like `FacInspectionCount`; the DFR
        # endpoint returns short keys like `Insp5yr`; older snapshots used
        # `EpaInspections`). Be tolerant of all three across every counter.
        inspections_5yr = _safe_int(
            facility.get("Insp5yr")
            or facility.get("EpaInspections")
            or facility.get("FacInspectionCount")
        )
        formal_actions_5yr = _safe_int(
            facility.get("FEA5yr")
            or facility.get("EpaFormalActions")
            or facility.get("FormalActions5yr")
            or facility.get("FacFormalActionCount")
        )
        informal_actions_5yr = _safe_int(
            facility.get("IEA5yr")
            or facility.get("EpaInformalActions")
            or facility.get("InformalActions5yr")
            or facility.get("FacInformalCount")
        )
        penalties_5yr_usd = _safe_float(
            facility.get("Penalties")
            or facility.get("PenaltyAmount")
            or facility.get("EpaTotalPenalties")
            or facility.get("FacTotalPenalties")
        )
        last_violation = _safe_date(
            facility.get("LastViolation") or facility.get("DateLastViolation")
        )
        last_inspection = _safe_date(
            facility.get("LastInspection")
            or facility.get("DateLastInspection")
            or facility.get("FacDateLastInspection")
        )
        last_formal_action = _safe_date(
            facility.get("FacDateLastFormalAction")
            or facility.get("DateLastFormalAction")
        )
        compliance = _safe_str(
            facility.get("CurrentCompliance")
            or facility.get("CurrVioFlag")
            or facility.get("CurrentSnc")
            or facility.get("FacComplianceStatus")
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
        text_signals = [last_violation, last_inspection, last_formal_action, compliance, programs]
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
        if last_formal_action:
            out["last_formal_action_date"] = last_formal_action
        if compliance:
            out["current_compliance"] = compliance
        if programs:
            out["programs"] = programs
        return out
