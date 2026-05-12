"""Unit tests for the EPA Superfund Documents enrichment connector.

Covers HTML parsing of the docdata page, document-record normalization
from the SEMS cachejson payload, and the SF_SITE_ID extraction hop.
No network calls.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import requests

from connectors.epa_superfund_docs import (
    EpaSuperfundDocs,
    INCLUDED_DOCTYPE,
    SF_SITE_ID_RE,
)


# ----- collection-link parser -----

def test_parse_collections_extracts_curated_collections():
    html = """
    <h3 id="SC">Reports and Documents</h3>
    <a href="../SiteProfiles/index.cfm?fuseaction=second.scs&id=0200144&doc=Y&colid=70007&region=02&type=SC" title="Click">Key Documents (11 documents)</a>
    <a href="../SiteProfiles/index.cfm?fuseaction=second.scs&id=0200144&doc=Y&colid=30554&region=02&type=SC" title="Click">SPP Decision Documents (3 documents)</a>
    <h3 id="AR">Administrative Records</h3>
    <a href="../SiteProfiles/index.cfm?fuseaction=second.ars&id=0200144&doc=Y&colid=62885&region=02&type=AR" title="Click">FY2011 REMOVAL AR (3 documents)</a>
    """
    cols = EpaSuperfundDocs._parse_collections(html)
    labels = [c["label"] for c in cols]
    assert "Key Documents" in labels
    assert "SPP Decision Documents" in labels
    # AR collections come back too — the allowlist filter happens in _fetch_site_documents,
    # not here, so the parser is faithful to the page.
    assert "FY2011 REMOVAL AR" in labels


def test_parse_collections_strips_count_suffix():
    html = '<a href="../SiteProfiles/index.cfm?fuseaction=second.scs&id=0200144&doc=Y&colid=70007&region=02&type=SC">Key Documents (1 documents)</a>'
    cols = EpaSuperfundDocs._parse_collections(html)
    assert cols[0]["label"] == "Key Documents"


def test_parse_collections_extracts_region_and_type():
    html = '<a href="../SiteProfiles/index.cfm?fuseaction=second.scs&id=0200144&doc=Y&colid=70007&region=05&type=SC">Key Documents (1 documents)</a>'
    cols = EpaSuperfundDocs._parse_collections(html)
    assert cols[0]["region"] == "05"
    assert cols[0]["type"] == "SC"
    assert cols[0]["colid"] == "70007"


def test_parse_collections_handles_singular_document_label():
    html = '<a href="../SiteProfiles/index.cfm?fuseaction=second.scs&id=1&doc=Y&colid=1&region=01&type=SC">Key Documents (1 document)</a>'
    cols = EpaSuperfundDocs._parse_collections(html)
    assert cols[0]["label"] == "Key Documents"


def test_parse_collections_empty_html_returns_empty_list():
    assert EpaSuperfundDocs._parse_collections("") == []


# ----- document normalizer -----

def test_normalize_document_extracts_url_and_title():
    entry = {
        "docId": "114066",
        "docTitle": '<a href=\'https://semspub.epa.gov/src/document/02/114066\' target=_blank>RECORD OF DECISION FOR OU1</a> <span class=fileinfo>(62 pp, 2.7 MB)</span>',
        "docDate": "09/28/1993",
        "ouId": "01",
        "contentSize": "2.7 MB",
        "pageCount": "62",
    }
    col = {"region": "02", "type": "SC", "colid": "70007", "label": "Key Documents"}
    doc = EpaSuperfundDocs._normalize_document(entry, col)
    assert doc["doc_id"] == "114066"
    assert doc["title"] == "RECORD OF DECISION FOR OU1"
    assert doc["url"] == "https://semspub.epa.gov/src/document/02/114066"
    assert doc["date"] == "1993-09-28"
    assert doc["ou_id"] == "01"
    assert doc["category"] == "Key Documents"
    assert doc["size"] == "2.7 MB"
    assert doc["pages"] == 62


def test_normalize_document_falls_back_to_canonical_url_when_anchor_missing():
    entry = {"docId": "999", "docTitle": "PLAIN TEXT TITLE", "docDate": "01/15/2020"}
    col = {"region": "10", "type": "SC", "colid": "1", "label": "Key Documents"}
    doc = EpaSuperfundDocs._normalize_document(entry, col)
    assert doc["url"] == "https://semspub.epa.gov/src/document/10/999"
    assert doc["title"] == "PLAIN TEXT TITLE"


def test_normalize_document_drops_record_with_no_doc_id():
    col = {"region": "02", "type": "SC", "colid": "1", "label": "Key Documents"}
    assert EpaSuperfundDocs._normalize_document({"docTitle": "X"}, col) is None


def test_normalize_document_handles_invalid_date():
    entry = {"docId": "1", "docTitle": "X", "docDate": "not-a-date"}
    col = {"region": "02", "type": "SC", "colid": "1", "label": "Key Documents"}
    doc = EpaSuperfundDocs._normalize_document(entry, col)
    assert "date" not in doc


def test_normalize_document_handles_invalid_page_count():
    entry = {"docId": "1", "docTitle": "X", "pageCount": "many"}
    col = {"region": "02", "type": "SC", "colid": "1", "label": "Key Documents"}
    doc = EpaSuperfundDocs._normalize_document(entry, col)
    assert "pages" not in doc


def test_normalize_document_handles_missing_optional_fields():
    """Minimum-viable doc: just doc_id + title."""
    entry = {"docId": "1", "docTitle": "<a href='/x'>Title</a>"}
    col = {"region": "02", "type": "SC", "colid": "1", "label": "Key Documents"}
    doc = EpaSuperfundDocs._normalize_document(entry, col)
    assert doc["doc_id"] == "1"
    assert doc["title"] == "Title"
    assert "ou_id" not in doc
    assert "size" not in doc
    assert "pages" not in doc
    assert "date" not in doc


# ----- SF_SITE_ID extraction -----

def test_sf_site_id_re_extracts_numeric_id():
    html = 'links: <a href="csitinfo.cfm?id=1002155">Profile</a>'
    m = SF_SITE_ID_RE.search(html)
    assert m and m.group(1) == "1002155"


def test_sf_site_id_re_returns_none_when_absent():
    assert SF_SITE_ID_RE.search("no profile link here") is None


# ----- status filter -----

def test_status_filter_parses_csv():
    assert EpaSuperfundDocs._parse_status_filter("F,D") == {"F", "D"}


def test_status_filter_all_returns_none():
    assert EpaSuperfundDocs._parse_status_filter("all") is None


def test_status_filter_empty_returns_none():
    assert EpaSuperfundDocs._parse_status_filter("") is None
    assert EpaSuperfundDocs._parse_status_filter(None) is None


def test_status_filter_strips_whitespace():
    assert EpaSuperfundDocs._parse_status_filter("F, D , ") == {"F", "D"}


# ----- network resilience (audit fix 2026-05-04) -----


# ----- doctype filter (broadened 2026-05-12 from label allowlist) -----


def test_included_doctype_is_sc():
    """Curated public documents have type=SC on cumulis; AR is the
    administrative-record docket dump. The filter is doctype-based so
    label-string variations ("Publicly Available Documents" vs
    "PUBLICLY AVAILABLE DOCUMENTS" vs "SPP Public Available Documents") all
    pass through as long as cumulis classifies them as SC."""
    assert INCLUDED_DOCTYPE == "SC"


def test_fetch_records_includes_non_spp_curated_labels(tmp_path, monkeypatch):
    """Regression test: prior allowlist required "SPP Public Available Documents"
    exactly, missing the ~28% of F/D sites whose curators used variants like
    "Publicly Available Documents", "Five Year Review Reports", or
    "Decision Documents" (no SPP prefix). All of those are tagged type=SC by
    cumulis, so the doctype filter must let them through."""
    monkeypatch.setattr(
        EpaSuperfundDocs, "_load_superfund_sites",
        lambda self: [
            {
                "id": "EPAID-X",
                "epa_id": "EPAID-X",
                "npl_status_code": "F",
                "profile_url": "https://www.epa.gov/superfund/site-x",
                "acreage": 100,
                "name": "Site X",
            }
        ],
    )
    monkeypatch.setattr(EpaSuperfundDocs, "_resolve_sf_site_id",
                        lambda self, url, use_cache: "9999999")
    # docdata returns three collections: one SC with a non-allowlisted label,
    # one SC with an allowlisted label, and one AR (admin record) which must
    # stay excluded.
    docdata_html = """
    <a href="../SiteProfiles/index.cfm?fuseaction=second.scs&id=9999999&doc=Y&colid=11111&region=05&type=SC">Five Year Review Reports (3 documents)</a>
    <a href="../SiteProfiles/index.cfm?fuseaction=second.scs&id=9999999&doc=Y&colid=22222&region=05&type=SC">Key Documents (2 documents)</a>
    <a href="../SiteProfiles/index.cfm?fuseaction=second.ars&id=9999999&doc=Y&colid=33333&region=05&type=AR">REMEDIAL (15 documents)</a>
    """
    cachejson_calls: list[str] = []

    def fake_get_text(self, url, params=None, use_cache=True):
        return docdata_html

    def fake_get_json(self, url, params=None, use_cache=True):
        cachejson_calls.append(url)
        # Synthesize one doc per collection.
        return {"data": [{"docId": f"d{len(cachejson_calls)}", "docTitle": "Doc"}]}

    monkeypatch.setattr(EpaSuperfundDocs, "http_get_text", fake_get_text)
    monkeypatch.setattr(EpaSuperfundDocs, "http_get_json", fake_get_json)

    inst = EpaSuperfundDocs(cache_dir=tmp_path)
    args = argparse.Namespace(
        docs_limit=1, docs_skip=0, docs_per_site=8, docs_status="F", limit=None,
    )
    records = inst.fetch_records(args, use_cache=False)
    assert len(records) == 1
    # Both SC collections must have been queried; the AR collection must not.
    assert len(cachejson_calls) == 2, f"expected 2 SC cachejson calls, got {len(cachejson_calls)}"
    # Both docs land in the output (per-site cap = 8, we only emit 2).
    assert len(records[0]["documents"]) == 2


def test_fetch_records_skips_site_on_pretty_page_connection_error(tmp_path, monkeypatch):
    """A single network blip on cumulis.epa.gov used to abort the whole
    --docs-limit 500 batch. Connection / timeout errors are now treated
    as transient: log and continue on to the next site."""
    # Two superfund sites; the first will trip a ConnectTimeout, the second
    # will resolve normally so we verify the run continues, not aborts.
    sites_payload = {
        "sites": [
            {
                "id": "EPAID-A",
                "epa_id": "EPAID-A",
                "npl_status_code": "F",
                "profile_url": "https://www.epa.gov/superfund/timeout-site",
                "acreage": 100,
                "name": "Timeout Site",
            },
            {
                "id": "EPAID-B",
                "epa_id": "EPAID-B",
                "npl_status_code": "F",
                "profile_url": "https://www.epa.gov/superfund/ok-site",
                "acreage": 50,
                "name": "OK Site",
            },
        ]
    }

    def fake_load(self):
        return sites_payload["sites"]

    monkeypatch.setattr(EpaSuperfundDocs, "_load_superfund_sites", fake_load)

    def fake_resolve(self, pretty_url, use_cache):
        if "timeout-site" in pretty_url:
            raise requests.ConnectTimeout("cumulis is being cumulis")
        return "1234567"

    monkeypatch.setattr(EpaSuperfundDocs, "_resolve_sf_site_id", fake_resolve)

    monkeypatch.setattr(
        EpaSuperfundDocs, "_fetch_site_documents",
        lambda self, sf_id, use_cache: [
            {"doc_id": "X", "title": "T", "url": "https://semspub.epa.gov/x", "category": "Key Documents"}
        ],
    )

    inst = EpaSuperfundDocs(cache_dir=tmp_path)
    args = argparse.Namespace(
        docs_limit=10, docs_skip=0, docs_per_site=8, docs_status="F", limit=None,
    )
    records = inst.fetch_records(args, use_cache=False)
    # The OK site should have made it through; the timeout site is skipped.
    ids = [r["id"] for r in records]
    assert ids == ["EPAID-B"], f"expected only OK site, got {ids}"


def test_fetch_records_skips_site_on_docdata_connection_error(tmp_path, monkeypatch):
    """Same resilience guarantee for the second hop (cumulis docdata page)."""
    monkeypatch.setattr(
        EpaSuperfundDocs, "_load_superfund_sites",
        lambda self: [
            {
                "id": "EPAID-A",
                "epa_id": "EPAID-A",
                "npl_status_code": "F",
                "profile_url": "https://www.epa.gov/superfund/site-a",
                "acreage": 100,
            },
            {
                "id": "EPAID-B",
                "epa_id": "EPAID-B",
                "npl_status_code": "F",
                "profile_url": "https://www.epa.gov/superfund/site-b",
                "acreage": 50,
            },
        ],
    )
    monkeypatch.setattr(EpaSuperfundDocs, "_resolve_sf_site_id",
                        lambda self, url, use_cache: "1234567")

    def fake_fetch_docs(self, sf_id, use_cache):
        # First call timeouts, subsequent ones succeed.
        if not getattr(fake_fetch_docs, "called", False):
            fake_fetch_docs.called = True
            raise requests.ConnectionError("transient blip")
        return [{"doc_id": "X", "title": "T", "url": "u", "category": "Key Documents"}]

    monkeypatch.setattr(EpaSuperfundDocs, "_fetch_site_documents", fake_fetch_docs)

    inst = EpaSuperfundDocs(cache_dir=tmp_path)
    args = argparse.Namespace(
        docs_limit=10, docs_skip=0, docs_per_site=8, docs_status="F", limit=None,
    )
    records = inst.fetch_records(args, use_cache=False)
    assert len(records) == 1
    assert records[0]["id"] == "EPAID-B"
