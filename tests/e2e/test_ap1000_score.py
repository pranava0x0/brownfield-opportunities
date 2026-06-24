"""Regression tests for the AP1000 military-installation siting overlay."""
from __future__ import annotations

from playwright.sync_api import Page


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function(
        "typeof window.computeAp1000Score === 'function'"
        " && typeof window.computeAp1000Breakdown === 'function'",
        timeout=10_000,
    )


def test_ap1000_weights_follow_priority_order(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    weights = page.evaluate("() => window.AP1000_WEIGHTS")
    assert sum(weights.values()) == 100
    assert weights == {
        "acreage": 30,
        "water": 27,
        "transmission": 14,
        "substation": 10,
        "workforce": 13,
        "fiber": 6,
    }
    assert weights["acreage"] > weights["water"]
    assert weights["water"] > weights["transmission"] + weights["substation"]
    assert weights["transmission"] + weights["substation"] > weights["workforce"]
    assert weights["workforce"] > weights["fiber"]


def test_ap1000_ranking_is_deterministic(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    rows = page.evaluate(
        """async () => {
          const payload = await fetch('data/ap1000-sites.json').then((r) => r.json());
          return payload.sites
            .map((s) => ({ id: s.id, score: window.computeAp1000Score(s) }))
            .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
        }"""
    )
    assert len(rows) == 14
    assert rows[0]["id"] == "jblm-wa"
    assert rows[0]["score"] == 88
    assert rows[-1]["id"] == "davis-monthan-afb-az"


def test_ap1000_air_force_rflp_provenance_is_emitted(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    rflp = page.evaluate(
        """async () => {
          const payload = await fetch('data/ap1000-sites.json').then((r) => r.json());
          return payload.sites
            .filter((s) => s.af_rflp_site)
            .map((s) => ({ id: s.id, acres: s.af_rflp_acres, source: s.af_rflp_source_url }));
        }"""
    )
    assert {r["id"] for r in rflp} == {
        "arnold-afb-tn",
        "davis-monthan-afb-az",
        "edwards-afb-ca",
        "jbmdl-nj",
        "robins-afb-ga",
    }
    assert sum(r["acres"] for r in rflp) == 3132
    assert all("sam.gov" in r["source"] for r in rflp)


def test_ap1000_tab_renders_ranking_and_rflp_badge(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    page.get_by_role("tab", name="AP1000").click()
    page.get_by_role("cell", name="Joint Base Lewis-McChord").wait_for(timeout=10_000)
    assert page.locator(".ap1000-row").count() == 14
    assert page.locator(".ap1000-rflp").count() == 5
    page.get_by_role("cell", name="Arnold AFB (AEDC)").click()
    assert page.locator(".ap1000-detail:not([hidden])").get_by_text(
        "Air Force AI data-center RFLP"
    ).is_visible()
