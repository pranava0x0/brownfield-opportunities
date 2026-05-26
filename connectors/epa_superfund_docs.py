"""EPA Superfund site documents (RODs, Five Year Reviews, fact sheets) connector.

EPA exposes per-site document collections through the Superfund Site Profile
(`cumulis.epa.gov`) and a JSON document index at
`semspub.epa.gov/src/cachejson/<region>/<type>/<colid>`. The connector walks
three hops to assemble the per-site document list:

1. **EPA pretty page → SF_SITE_ID.** Our master Superfund table carries
   `URL_ALIAS_TXT` (e.g. `https://www.epa.gov/superfund/portland-harbor`).
   That page links out to the cumulis profile, which embeds the numeric
   SF_SITE_ID we need for the next hop. EPA_ID and SF_SITE_ID are
   unrelated — there's no public cross-walk dataset, so this scrape is
   the only path. Sites without a pretty URL are skipped.
2. **docdata HTML → collections.** Given the SF_SITE_ID, fetch the Site
   Documents & Data page and extract `(colid, region, type)` tuples for
   the curated "Reports and Documents" collections (Key Documents, SPP
   Decision Documents, SPP Public Available Documents, SPP Technical
   Reports and Studies). The Administrative Records collections are
   intentionally skipped — they're docket dumps of every piece of
   correspondence on a site, low signal-to-noise for a brownfield buyer.
3. **cachejson → document records.** Each collection has a JSON index
   at `semspub.epa.gov/src/cachejson/<region>/<type>/<colid>`. Documents
   carry title, semspub URL, date, OU ID, author, page count, file size.

This is an *enrichment-only* connector — it doesn't add new sites. Output
records carry only `id`, `program: "superfund"`, `epa_id`, and `documents`.
The combined sites.json frontend joins these onto the master Superfund
records by `epa_id`.

The full inventory has ~1,900 sites and ~5–10 collections per site →
~15k HTTP requests at 1.5s each, ~6 hours wall clock unbounded. The
default `--docs-limit 100` keeps a single refresh under 15 minutes; the
cache makes re-runs cheap. Use `--docs-skip` to stripe coverage across
multiple runs (`--docs-limit 100 --docs-skip 100` for the next 100).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import requests

from connectors.base import Connector

log = logging.getLogger("connector.epa_superfund_docs")

DOCDATA_URL = "https://cumulis.epa.gov/supercpad/SiteProfiles/index.cfm"
CACHEJSON_URL = "https://semspub.epa.gov/src/cachejson/{region}/{type}/{colid}"
SEMS_DOCUMENT_URL = "https://semspub.epa.gov/src/document/{region}/{doc_id}"

# EPA pretty pages link out to the cumulis profile with the numeric
# SF_SITE_ID embedded as `csitinfo.cfm?id=NNNNNNN`. We pull that out to
# bridge EPA_ID → SF_SITE_ID since the two ID systems aren't otherwise
# cross-walked anywhere public.
SF_SITE_ID_RE = re.compile(r"csitinfo\.cfm\?id=(\d+)", re.IGNORECASE)

# Filter by doctype, not by label string. Cumulis tags every collection with
# `type=SC` (curated "Reports and Documents") or `type=AR` (administrative
# record docket dumps). The SC vs AR line is EPA's own — every curated
# public-facing collection is type=SC. The previous label-allowlist approach
# missed ~28% of F/D sites because curators use a long tail of label
# variations ("Publicly Available Documents", "PUBLICLY AVAILABLE DOCUMENTS",
# "Five Year Review Reports", "Five-Year Reviews", "Decision Documents"
# without the SPP prefix, etc.). Switched to the doctype gate 2026-05-12.
INCLUDED_DOCTYPE = "SC"

# Kept as documentation of which curated labels we expect to see — not
# enforced. The doctype filter above is the source of truth for inclusion.
EXPECTED_CURATED_LABELS = {
    "Key Documents",
    "Publicly Available Documents",
    "SPP Public Available Documents",
    "Decision Documents",
    "SPP Decision Documents",
    "Technical Reports and Studies",
    "SPP Technical Reports and Studies",
    "Five Year Review Reports",
    "Five-Year Review Reports",
    "Five Year Reviews",
    "Fact Sheets and Public Meeting Documents",
    "SPP Public Meeting Documents",
    "Enforcement and Settlement Documents",
    "SPP Enforcement and Settlement Documents",
}

# Per-site cap on emitted documents. Beyond this we'd bloat the per-record
# payload — the dashboard only renders the top few in the detail panel.
DEFAULT_DOCS_PER_SITE = 8

# Pulled from cachejson — `docTitle` arrives as a full <a href="..." ...>TITLE</a>
# string. Regex preferred over BeautifulSoup so we don't add a runtime dep.
TITLE_HREF_RE = re.compile(r'href=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
TITLE_TEXT_RE = re.compile(r'>([^<]+)</a>', re.IGNORECASE)
COLLECTION_LINK_RE = re.compile(
    r'fuseaction=second\.(?P<type>scs|ars)&id=(?P<id>\d+)'
    r'&doc=Y&colid=(?P<colid>\d+)&region=(?P<region>\d{2})&type=(?P<doctype>SC|AR)'
)
COLLECTION_LABEL_RE = re.compile(
    r'colid=\d+&region=\d{2}&type=(?:SC|AR)"[^>]*>([^<]+)</a>'
)
# Used when EPA returns a 404 / empty body for a collection — surfaces in the log
# but doesn't abort the run.
TRANSIENT_HTTP_CODES = {404, 500, 502, 503}


class EpaSuperfundDocs(Connector):
    slug = "epa-superfund-docs"
    source_label = "EPA Superfund Documents (SEMS)"
    source_url = "https://semspub.epa.gov/"

    # Reads docs/data/superfund-npl.json — must run after the Superfund
    # producer in --all mode, otherwise on cold runs it sees no sites.
    run_order = 200

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
            "--docs-limit",
            type=int,
            default=100,
            help="Max number of Superfund sites to enrich with documents per run "
                 "(default: 100). Cache makes incremental runs cheap.",
        )
        p.add_argument(
            "--docs-skip",
            type=int,
            default=0,
            help="Skip the first N sites — for resumable batch coverage "
                 "(use with --docs-limit).",
        )
        p.add_argument(
            "--docs-per-site",
            type=int,
            default=DEFAULT_DOCS_PER_SITE,
            help=f"Max documents kept per site (default: {DEFAULT_DOCS_PER_SITE}).",
        )
        p.add_argument(
            "--docs-status",
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

        status_filter = self._parse_status_filter(getattr(args, "docs_status", "F,D"))
        if status_filter is not None:
            sites = [s for s in sites if s.get("npl_status_code") in status_filter]
            log.info("status filter %s: %d eligible sites", sorted(status_filter), len(sites))

        # Sort by acreage desc then name so the largest, most-notable sites
        # get enriched first when a `--docs-limit` cap is in play.
        sites.sort(
            key=lambda s: (
                s.get("acreage") is None,
                -(s.get("acreage") or 0),
                (s.get("name") or "").lower(),
            )
        )

        # `--missing-only`: drop sites already covered in the existing output
        # before applying skip/take, so the cap targets uncovered work.
        missing_only = bool(getattr(args, "missing_only", False))
        if missing_only:
            covered = self.existing_ids()
            if covered:
                before = len(sites)
                sites = [s for s in sites if (s.get("epa_id") or s.get("id")) not in covered]
                log.info("--missing-only: %d/%d sites already covered, %d remaining",
                         before - len(sites), before, len(sites))

        skip = max(0, getattr(args, "docs_skip", 0) or 0)
        take = getattr(args, "docs_limit", DEFAULT_DOCS_PER_SITE) or 0
        target_sites = sites[skip: skip + take] if take else sites[skip:]
        log.info("enriching %d sites (skip=%d, take=%d)", len(target_sites), skip, take or -1)

        per_site_cap = max(1, getattr(args, "docs_per_site", DEFAULT_DOCS_PER_SITE))

        records: list[dict[str, Any]] = []
        skipped_no_url = 0
        skipped_no_sf_id = 0
        for i, site in enumerate(target_sites, 1):
            epa_id = site.get("epa_id") or site.get("id")
            if not epa_id:
                continue
            pretty_url = site.get("profile_url") or ""
            if not pretty_url.startswith("https://www.epa.gov/superfund/"):
                # The numeric SF_SITE_ID lookup needs the EPA pretty page;
                # without it we have no path to the docdata endpoint.
                skipped_no_url += 1
                continue
            try:
                sf_site_id = self._resolve_sf_site_id(pretty_url, use_cache=use_cache)
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else None
                if code in TRANSIENT_HTTP_CODES:
                    log.warning("[%s] pretty-page HTTP %s — skipping", epa_id, code)
                    continue
                raise
            except (requests.ConnectionError, requests.Timeout) as e:
                # cumulis.epa.gov is flaky during long runs — a single
                # network timeout shouldn't abort the whole 500-site batch.
                log.warning("[%s] pretty-page network error: %s — skipping",
                            epa_id, type(e).__name__)
                continue
            if not sf_site_id:
                skipped_no_sf_id += 1
                log.info("[%s] no SF_SITE_ID in %s", epa_id, pretty_url)
                continue
            try:
                docs = self._fetch_site_documents(sf_site_id, use_cache=use_cache)
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else None
                if code in TRANSIENT_HTTP_CODES:
                    log.warning("[%s] docdata HTTP %s — skipping", epa_id, code)
                    continue
                raise
            except (requests.ConnectionError, requests.Timeout) as e:
                log.warning("[%s] docdata network error: %s — skipping",
                            epa_id, type(e).__name__)
                continue
            except (requests.exceptions.JSONDecodeError, json.JSONDecodeError, ValueError) as e:
                # semspub.epa.gov occasionally returns truncated or malformed
                # JSON for cachejson collections. Skip the offending site
                # rather than abort the whole batch — same containment shape
                # as the network-error branch above. The response isn't
                # cached on parse failure, so a future run will retry.
                log.warning("[%s] docdata JSON parse error: %s — skipping",
                            epa_id, e)
                continue
            if not docs:
                log.info("[%s] no documents found (SF_SITE_ID=%s)", epa_id, sf_site_id)
                continue
            docs = docs[:per_site_cap]
            records.append({
                "id": epa_id,
                "program": "superfund",
                "epa_id": epa_id,
                "documents": docs,
            })
            log.info("[%d/%d] %s (SF=%s) → %d docs",
                     i, len(target_sites), epa_id, sf_site_id, len(docs))

        if skipped_no_url:
            log.info("skipped %d sites lacking an EPA pretty URL", skipped_no_url)
        if skipped_no_sf_id:
            log.info("skipped %d sites whose pretty page had no SF_SITE_ID", skipped_no_sf_id)

        if getattr(args, "limit", None):
            records = records[: args.limit]

        log.info(
            "enriched %d sites with documents (avg %.1f docs/site)",
            len(records),
            (sum(len(r["documents"]) for r in records) / max(1, len(records))),
        )

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

    def _resolve_sf_site_id(self, pretty_url: str, use_cache: bool) -> str | None:
        """Scrape EPA's pretty Superfund page to extract the numeric SF_SITE_ID.

        EPA_ID (e.g. ORSFN1002155) and SF_SITE_ID (e.g. 1002155) are
        unrelated identifiers — there's no public cross-walk dataset, so
        the pretty page is the cheapest hop. Cached aggressively because
        it never changes for a given site.
        """
        html = self.http_get_text(pretty_url, params=None, use_cache=use_cache)
        m = SF_SITE_ID_RE.search(html)
        return m.group(1) if m else None

    def _fetch_site_documents(
        self, sf_site_id: str, use_cache: bool
    ) -> list[dict[str, Any]]:
        """Two-step fetch: (1) docdata HTML → collections, (2) per-collection cachejson."""
        html = self.http_get_text(
            DOCDATA_URL,
            params={"fuseaction": "second.docdata", "id": sf_site_id},
            use_cache=use_cache,
        )
        collections = self._parse_collections(html)
        if not collections:
            return []

        all_docs: list[dict[str, Any]] = []
        for col in collections:
            if col["type"] != INCLUDED_DOCTYPE:
                continue
            try:
                col_data = self.http_get_json(
                    CACHEJSON_URL.format(**col),
                    params={},
                    use_cache=use_cache,
                )
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else None
                if code in TRANSIENT_HTTP_CODES:
                    log.warning("collection %s HTTP %s — skipping",
                                col["colid"], code)
                    continue
                raise
            except (requests.ConnectionError, requests.Timeout) as e:
                # Same flakiness applies to semspub.epa.gov — never let one
                # collection's network blip take down the whole site's run.
                log.warning("collection %s network error: %s — skipping",
                            col["colid"], type(e).__name__)
                continue
            for entry in col_data.get("data") or []:
                doc = self._normalize_document(entry, col)
                if doc is not None:
                    all_docs.append(doc)

        # Sort newest-first; ties broken by docId for stability across runs.
        all_docs.sort(
            key=lambda d: (d.get("date") or "0000-00-00", d.get("doc_id") or ""),
            reverse=True,
        )
        # Dedupe — Key Documents collection often re-lists items that also
        # appear in Decision Documents.
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for d in all_docs:
            doc_id = d.get("doc_id")
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            unique.append(d)
        return unique

    @staticmethod
    def _parse_collections(html: str) -> list[dict[str, Any]]:
        """Extract per-collection (colid, region, type, label) tuples from docdata HTML.

        The docdata page is structured as a series of `<a href="..."
        title="..">LABEL (N documents)</a>` rows grouped under the
        "Reports and Documents" / "Administrative Records" headings. We
        regex-match the links — minimal HTML parser, no extra dep.
        """
        collections: list[dict[str, Any]] = []
        for m in re.finditer(
            r'<a href="[^"]*' + COLLECTION_LINK_RE.pattern + r'"[^>]*>(?P<label>[^<]+)</a>',
            html,
        ):
            label = m.group("label").strip()
            # Trim "(N documents)" suffix for clean labels in the output.
            label_clean = re.sub(r"\s*\(\d+\s+documents?\)\s*$", "", label)
            collections.append({
                "colid": m.group("colid"),
                "region": m.group("region"),
                "type": m.group("doctype"),
                "label": label_clean,
            })
        return collections

    @staticmethod
    def _normalize_document(entry: dict[str, Any], col: dict[str, Any]) -> dict[str, Any] | None:
        title_html = entry.get("docTitle") or ""
        href_match = TITLE_HREF_RE.search(title_html)
        text_match = TITLE_TEXT_RE.search(title_html)
        title = (text_match.group(1).strip() if text_match else title_html).strip()
        url = href_match.group(1) if href_match else None
        doc_id = entry.get("docId")
        if not doc_id:
            return None
        # Prefer a canonical URL if cachejson didn't ship one.
        if not url:
            url = SEMS_DOCUMENT_URL.format(region=col["region"], doc_id=doc_id)

        # Date arrives as MM/DD/YYYY — convert to ISO so we can sort lexically.
        raw_date = (entry.get("docDate") or "").strip()
        iso_date = None
        if raw_date and "/" in raw_date:
            try:
                m, d, y = raw_date.split("/")
                iso_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            except (ValueError, TypeError):
                pass

        out: dict[str, Any] = {
            "doc_id": str(doc_id),
            "title": title or f"Document {doc_id}",
            "url": url,
            "category": col["label"],
        }
        if iso_date:
            out["date"] = iso_date
        if entry.get("ouId"):
            out["ou_id"] = str(entry["ouId"]).strip() or None
            if not out["ou_id"]:
                out.pop("ou_id")
        if entry.get("contentSize"):
            out["size"] = entry["contentSize"]
        if entry.get("pageCount"):
            try:
                out["pages"] = int(entry["pageCount"])
            except (TypeError, ValueError):
                pass
        return out
