"""Unit tests for the EPA ACRES cleanup enrichment connector.

Covers the ArcGIS mixed-case field-name handling, date parsing, and
the ACRES property_id → site_id join. No network calls.
"""
from __future__ import annotations

import pytest
from connectors.epa_acres_cleanup import EpaAcresCleanup, _iso_date, _safe_int


# ---- helper: _iso_date ----

def test_iso_date_epoch_ms():
    """ArcGIS default timestamp: epoch milliseconds → YYYY-MM-DD."""
    assert _iso_date("1122768000000") == "2005-07-31"


def test_iso_date_mmddyyyy():
    assert _iso_date("07/31/2005") == "2005-07-31"


def test_iso_date_yyyymmdd_passthrough():
    assert _iso_date("2005-07-31") == "2005-07-31"


def test_iso_date_none_returns_none():
    assert _iso_date(None) is None
    assert _iso_date("") is None


# ---- field-name case handling in _fetch_cleanups ----

def test_fetch_cleanups_handles_mixed_case_field_names(monkeypatch, tmp_path):
    """ArcGIS returns mixed-case field names (Property_ID, CA_Status,
    Cleanup_Completion_Date, CA_Type, CA_Recipient). The connector must
    join correctly and not return 0 records due to an all-caps mismatch.

    This is a regression test for the v1.14.1 fix where PROPERTY_ID /
    CA_STATUS / COMPLETION_DATE (wrong casing) yielded 0 matches even
    though all 110 ACRES cleanup records were fetched successfully.
    """
    connector = EpaAcresCleanup(cache_dir=tmp_path)

    # Simulate a single-page ArcGIS response with mixed-case field names
    fake_page = {
        "features": [
            {
                "attributes": {
                    "Property_ID": 23241,
                    "CA_Status": "Closed",
                    "Cleanup_Completion_Date": 1122768000000,
                    "CA_Type": "Section 128(a) State/Tribal",
                    "CA_Recipient": "Ute Mountain Ute Tribe",
                    "ObjectId": 1,
                }
            },
            {
                "attributes": {
                    "Property_ID": 99999,
                    "CA_Status": "Open",
                    "Cleanup_Completion_Date": None,
                    "CA_Type": "Cleanup",
                    "CA_Recipient": "Test Grantee",
                    "ObjectId": 2,
                }
            },
        ],
        "exceededTransferLimit": False,
    }

    call_count = {"n": 0}

    def fake_http_get_json(url, params, cache_key, use_cache):
        call_count["n"] += 1
        return fake_page

    monkeypatch.setattr(connector, "http_get_json", fake_http_get_json)

    result = connector._fetch_cleanups(use_cache=False)

    assert len(result) == 2, "Both records should be extracted with mixed-case field names"
    assert "23241" in result
    assert result["23241"]["cleanup_status"] == "Closed"
    assert result["23241"]["cleanup_complete_date"] == "2005-07-31"
    assert result["23241"]["cleanup_type"] == "Section 128(a) State/Tribal"
    assert result["23241"]["grantee"] == "Ute Mountain Ute Tribe"
    assert "99999" in result
    assert result["99999"]["cleanup_status"] == "Open"


def test_fetch_cleanups_falls_back_to_uppercase_field_names(monkeypatch, tmp_path):
    """If ArcGIS returns all-uppercase field names (as originally expected),
    the connector must still work via the fallback `or` clause."""
    connector = EpaAcresCleanup(cache_dir=tmp_path)

    fake_page = {
        "features": [
            {
                "attributes": {
                    "PROPERTY_ID": 12345,
                    "CA_STATUS": "Closed",
                    "COMPLETION_DATE": 1122768000000,
                    "CLEANUP_TYPE": "Cleanup",
                    "GRANTEE_NAME": "Some Grantee",
                    "ObjectId": 1,
                }
            }
        ],
        "exceededTransferLimit": False,
    }

    monkeypatch.setattr(connector, "http_get_json", lambda *a, **kw: fake_page)

    result = connector._fetch_cleanups(use_cache=False)
    assert "12345" in result
    assert result["12345"]["cleanup_status"] == "Closed"
    assert result["12345"]["grantee"] == "Some Grantee"
