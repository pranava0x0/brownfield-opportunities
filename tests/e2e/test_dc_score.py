"""Browser contracts for category evidence; legacy numeric suitability is retired."""
from __future__ import annotations
import csv
import io
import pytest
from playwright.sync_api import Page, expect
pytestmark = pytest.mark.e2e

def _ready(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.SiteEvidence && window.__APP_READY__ === true", timeout=45000)

def _assess(page, record, lens="dc"):
    return page.evaluate("([s,l]) => SiteEvidence.assessSite(s,l)", [record,lens])


@pytest.mark.parametrize("name", ["computeDcCompositeScore", "computeGenerationScore", "computeManufacturingScore"])
def test_legacy_numeric_scorer_not_exposed(page, base_url, name):
    _ready(page, base_url)
    assert page.evaluate("n => typeof window[n]", name) == "undefined"

@pytest.mark.parametrize("lens", ["dc", "gen", "mfg"])
def test_missing_grid_does_not_remove_other_evidence(page, base_url, lens):
    _ready(page, base_url)
    a = _assess(page, {"acreage": 300, "rail_mi": 0.5}, lens)
    assert a["grid"]["status"] == "unknown"
    assert a["land"]["status"] == a["logistics"]["status"] == "context"
    assert "score" not in a and "total" not in a

def test_substation_only_retains_its_own_voltage_and_capacity_unknown(page, base_url):
    _ready(page, base_url)
    a = _assess(page, {"transmission_mi": 20, "transmission_kv": 500, "substation_mi": 0.1})
    assert "Substation" in a["grid"]["finding"] and "500" not in a["grid"]["finding"]
    assert a["grid_capacity"]["status"] == "unknown"

def test_retired_plant_does_not_establish_reusable_capacity(page, base_url):
    _ready(page, base_url)
    a = _assess(page, {"retired_plant_mw": 1200, "retired_plant_mi": 0, "retired_plant_year": 2026})
    assert a["grid_capacity"]["status"] == "unknown"

def test_parcel_area_fills_missing_program_area_without_availability_claim(page, base_url):
    _ready(page, base_url)
    a = _assess(page, {"parcel_acreage": 300})
    assert "300" in a["land"]["finding"]
    assert "availability require verification" in a["land"]["reason"]

def test_table_grid_column_contains_a_finding_not_a_score(page, base_url):
    _ready(page, base_url)
    page.locator("#tab-table").click()
    expect(page.locator("#sites-table tbody tr").first).to_be_visible()
    expect(page.locator("#th-dc-score")).to_contain_text("Grid context")
    assert page.locator("#th-dc-score").get_attribute("data-sort") == "transmission_mi"
    assert not page.locator("#sites-table tbody tr td").last.inner_text().isdigit()

def test_suitability_block_is_above_owner_in_panel(page, base_url):
    """UAT 2026-05-31: the suitability block — the headline DC/generation
    judgment the whole tool is built around — must sit near the TOP of the
    detail panel (right after the core KV grid), not buried below the
    Owner / Documents / Tax sections. Guards against accidental re-burial.
    `compareDocumentPosition` returns DOCUMENT_POSITION_FOLLOWING (4) when
    the owner block comes after the suitability block in document order."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    suit_before_owner = page.evaluate(
        "() => {"
        "  const suit = document.getElementById('d-suitability-block');"
        "  const owner = document.querySelector(\"#detail [data-section='owner']\");"
        "  if (!suit || !owner) return null;"
        "  return !!(suit.compareDocumentPosition(owner) & Node.DOCUMENT_POSITION_FOLLOWING);"
        "}"
    )
    assert suit_before_owner is True, (
        "suitability block must appear before the Owner section in the detail panel"
    )