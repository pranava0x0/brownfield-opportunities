"""Shared evidence filters survive links and constrain the exported records."""
import csv
import io

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_evidence_filter_url_and_csv_use_same_population(page, base_url):
    page.goto(f"{base_url}/index.html?program=superfund&evidence=fiber&finding=unknown&confidence=High")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45000)
    expect(page.locator("#evidence-category-filter")).to_have_value("fiber")
    expect(page.locator("#evidence-status-filter")).to_have_value("unknown")
    expect(page.locator("#evidence-confidence-filter")).to_have_value("High")
    assert list(csv.DictReader(io.StringIO(page.evaluate("window.__buildCsv()")))) == []
    page.locator("#evidence-confidence-filter").select_option("")
    page.wait_for_function("!new URLSearchParams(location.search).has('confidence')")
    page.reload()
    page.wait_for_function("window.__APP_READY__ === true", timeout=45000)
    expect(page.locator("#evidence-category-filter")).to_have_value("fiber")
    expect(page.locator("#evidence-status-filter")).to_have_value("unknown")
    rows = list(csv.DictReader(io.StringIO(page.evaluate("window.__buildCsv()"))))
    assert len(rows) > 1000
    assert all(row["fiber_finding"] == "Unknown" for row in rows)
    # FEMA's attributed source index remains raw data; our composite totals do not.
    assert {key for key in rows[0] if "score" in key.lower()} <= {"nri_risk_score"}


def test_nuclear_csv_has_unique_headers_for_raw_notes_and_findings(page, base_url):
    page.goto(f"{base_url}/index.html?program=superfund#ap1000")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45000)
    page.wait_for_function("window.__buildAp1000Csv && window.__buildAp1000Csv().split('\\n').length > 2")
    headers = next(csv.reader(io.StringIO(page.evaluate("window.__buildAp1000Csv()"))))
    assert len(headers) == len(set(headers))
    for field in ["water_reason", "water_context_note", "fiber_reason", "fiber_context_note", "water_rights_reason", "water_rights_context_note"]:
        assert field in headers
