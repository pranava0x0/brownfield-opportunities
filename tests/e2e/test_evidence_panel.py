"""E2E tests for the "Sources & evidence" panel.

The dashboard's value depends on a reader being able to walk any number back
to the agency that published it. These tests assert the panel does that: one
row per claim the record actually carries, each naming a publisher, stating
how the value was derived, dating it from its own source file, and — where
the upstream service allows — linking to that site's own record.

They do NOT hit the network. Link *integrity* (does each URL resolve, and
does it return data when the claim is positive) is checked by
`scripts/validate_against_sources.py --only evidence`, which is cached and
rate-limited and has no place in a fast test suite.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.wait_for_function(
        "typeof window.buildEvidence === 'function'", timeout=15_000
    )
    # Infra enrichment drives most rows; wait for it to land.
    page.wait_for_function(
        "(window.__sites || []).some(s => s.transmission_mi != null)",
        timeout=60_000,
    )


def _open_evidence(page: Page, site_id: str):
    page.evaluate("(id) => window.__selectSite(id)", site_id)
    block = page.locator("#d-evidence-block")
    block.evaluate("(b) => { b.open = true; b.dispatchEvent(new Event('toggle')); }")
    return block


def _a_superfund_id(page: Page) -> str:
    return page.evaluate(
        """() => (window.__sites || []).find(
            s => s.program === 'superfund' && s.transmission_mi != null).id"""
    )


def test_evidence_is_not_built_until_opened(page: Page, base_url: str):
    """The panel is in the DOM at first paint; a full evidence table is ~150
    nodes against a 5,000-node budget, so it must stay unbuilt while closed."""
    _ready(page, base_url)
    page.evaluate("(id) => window.__selectSite(id)", _a_superfund_id(page))
    assert page.locator("#d-evidence-body").evaluate("(el) => el.childNodes.length") == 0
    assert page.locator(".evidence-row").count() == 0


def test_opening_builds_one_row_per_claim(page: Page, base_url: str):
    _ready(page, base_url)
    _open_evidence(page, _a_superfund_id(page))
    assert page.locator(".evidence-row").count() >= 10


def test_every_row_names_a_publisher_and_a_derivation(page: Page, base_url: str):
    """A source without a derivation is a citation you can't judge."""
    _ready(page, base_url)
    sid = _a_superfund_id(page)
    rows = page.evaluate(
        "(id) => window.buildEvidence(window.__sites.find(s => s.id === id))", sid
    )
    assert rows
    for r in rows:
        assert r["publisher"], r
        assert r["derivation"], r
        assert r["label"], r


def test_rows_only_appear_for_values_the_site_actually_has(page: Page, base_url: str):
    """Never cite a source for a value that isn't on the record."""
    _ready(page, base_url)
    result = page.evaluate(
        """() => {
            const s = (window.__sites || []).find(
                x => x.program === 'brownfield' && x.transmission_mi != null);
            const rows = window.buildEvidence(s);
            return {
                id: s.id,
                // ACRES publishes no acreage and no NPL documents.
                hasAcreage: s.acreage != null,
                citesAcreage: rows.some(r => r.key === 'acreage'),
                citesDocuments: rows.some(r => r.key === 'documents'),
                hasDocuments: Array.isArray(s.documents) && s.documents.length > 0,
            };
        }"""
    )
    assert result["citesAcreage"] == result["hasAcreage"], result
    assert result["citesDocuments"] == result["hasDocuments"], result


def test_as_of_dates_are_per_source_file_not_global(page: Page, base_url: str):
    """infra-proximity and the program files refresh on different cadences;
    one global date would misdate most rows."""
    _ready(page, base_url)
    dates = page.evaluate(
        """(id) => {
            const rows = window.buildEvidence(
                window.__sites.find(s => s.id === id));
            const out = {};
            for (const r of rows) if (r.asOf) out[r.key] = r.asOf;
            return out;
        }""",
        _a_superfund_id(page),
    )
    assert len(dates) >= 5
    assert len(set(dates.values())) > 1, (
        f"every row shares one date, so per-file capture is not working: {dates}"
    )


def test_program_rows_link_to_this_records_own_query(page: Page, base_url: str):
    """A link to 'the EPA layer' is documentation; a link that returns THIS
    row is evidence."""
    _ready(page, base_url)
    sid = _a_superfund_id(page)
    url = page.evaluate(
        """(id) => {
            const s = window.__sites.find(x => x.id === id);
            const r = window.buildEvidence(s).find(x => x.key === 'name');
            return r.verifyUrl;
        }""",
        sid,
    )
    assert "FeatureServer" in url
    assert sid in url, "the query must be scoped to this record's own id"


def test_bbox_links_always_span_the_distance_they_evidence(page: Page, base_url: str):
    """A box smaller than the claim returns nothing and reads as a refutation.

    This regressed once: a fixed 60 mi ceiling produced empty results for
    sites 60-100 mi from their nearest feature.
    """
    _ready(page, base_url)
    bad = page.evaluate(
        """() => {
            const FIELDS = ['transmission_mi', 'rail_mi', 'highway_mi',
                            'gas_pipeline_mi', 'power_plant_mi'];
            const out = [];
            const sample = (window.__sites || [])
                .filter(s => s.transmission_mi != null).slice(0, 400);
            for (const s of sample) {
                for (const r of window.buildEvidence(s)) {
                    if (!FIELDS.includes(r.key) || !r.verifyUrl) continue;
                    const m = r.verifyUrl.match(/geometry=([^&]+)/);
                    if (!m) continue;
                    const p = decodeURIComponent(m[1]).split(',').map(Number);
                    const halfMi = ((p[3] - p[1]) / 2) * 69;
                    if (s[r.key] != null && halfMi < s[r.key]) {
                        out.push({ id: s.id, key: r.key,
                                   claim: s[r.key], halfMi: +halfMi.toFixed(1) });
                    }
                }
            }
            return out.slice(0, 10);
        }"""
    )
    assert bad == [], bad


def test_negative_claims_declare_they_expect_no_features(page: Page, base_url: str):
    """"Not in an Opportunity Zone" is evidenced by an empty result — the row
    must say so, or a link checker reads a correct negative as a dead link."""
    _ready(page, base_url)
    page.wait_for_function(
        "(window.__sites || []).some(s => s.in_opportunity_zone === false)",
        timeout=60_000,
    )
    flags = page.evaluate(
        """() => {
            const s = (window.__sites || []).find(
                x => x.in_opportunity_zone === false && x.transmission_mi != null);
            const r = window.buildEvidence(s).find(x => x.key === 'in_opportunity_zone');
            return r ? r.expectsFeatures : 'missing-row';
        }"""
    )
    assert flags is False


def test_derived_fields_are_labelled_as_derived_not_sourced(page: Page, base_url: str):
    """Values this project computes must not masquerade as agency data."""
    _ready(page, base_url)
    page.wait_for_function(
        "(window.__sites || []).some(s => s.coord_flags)", timeout=60_000
    )
    row = page.evaluate(
        """() => {
            const s = (window.__sites || []).find(x => x.coord_flags);
            return window.buildEvidence(s).find(r => r.key === 'coord_flags');
        }"""
    )
    assert row is not None
    assert "derived" in row["publisher"].lower() or "this project" in row["publisher"].lower()
    assert row["code"], "a derived value must cite the code that computed it"


def test_evidence_collapses_when_switching_sites(page: Page, base_url: str):
    """Otherwise a stale table from the previous site stays on screen."""
    _ready(page, base_url)
    ids = page.evaluate(
        """() => (window.__sites || [])
            .filter(s => s.program === 'superfund' && s.transmission_mi != null)
            .slice(0, 2).map(s => s.id)"""
    )
    _open_evidence(page, ids[0])
    assert page.locator(".evidence-row").count() > 0
    page.evaluate("(id) => window.__selectSite(id)", ids[1])
    expect(page.locator("#d-evidence-block")).not_to_have_attribute("open", "")
    assert page.locator(".evidence-row").count() == 0
