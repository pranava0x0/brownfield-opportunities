"""Shared evidence filters survive links and constrain the exported records."""
import csv
import io

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_all_met_filter_survives_links_and_matches_the_export(page, base_url):
    page.goto(f"{base_url}/index.html?program=superfund&lens=solar&allmet=1")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45000)
    expect(page.locator("#screen-all-met")).to_be_checked()
    page.wait_for_function("document.querySelectorAll('#candidates-table tbody tr').length > 0", timeout=30000)
    rows = list(csv.DictReader(io.StringIO(page.evaluate("window.__buildCsv()"))))
    assert rows and all(r["checks_met"] == "4" for r in rows)
    stated = int(page.locator("#candidates-stats").inner_text().split(" of ")[0].replace(",", ""))
    assert len(rows) == stated
    # FEMA's attributed source index remains raw data; no composite totals.
    assert {key for key in rows[0] if "score" in key.lower()} <= {"nri_risk_score"}


def test_nuclear_csv_has_unique_headers_for_raw_notes_and_findings(page, base_url):
    page.goto(f"{base_url}/index.html?program=superfund#ap1000")
    page.wait_for_function("window.__APP_READY__ === true", timeout=45000)
    page.wait_for_function("window.__buildAp1000Csv && window.__buildAp1000Csv().split('\\n').length > 2")
    headers = next(csv.reader(io.StringIO(page.evaluate("window.__buildAp1000Csv()"))))
    assert len(headers) == len(set(headers))
    for field in ["water_reason", "water_context_note", "fiber_reason", "fiber_context_note", "water_rights_reason", "water_rights_context_note"]:
        assert field in headers
