"""The detail panel shows researched county, city and state records, and says what it could not find."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, expect

DATA = Path(__file__).resolve().parents[2] / "docs" / "data" / "local-records.json"


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)


def _sample():
    sites = json.loads(DATA.read_text())["sites"]
    return next(s for s in sites if s["portals"] and s.get("facts")), next(s for s in sites if not s["portals"] and not s.get("facts"))


def test_block_renders_portals_facts_and_gaps_for_a_researched_site(page: Page, base_url: str):
    rich, _ = _sample()
    _ready(page, base_url)
    page.evaluate("(id) => window.__selectSite(id)", rich["id"])
    block = page.locator("#d-local-block")
    page.wait_for_function("document.getElementById('d-local-block') && !document.getElementById('d-local-block').hidden", timeout=30_000)
    expect(block).to_be_visible()
    block.locator("> summary").click()
    assert block.locator(".local-portals li").count() == len(rich["portals"])
    assert block.locator(".local-facts li").count() == len(rich["facts"])
    assert block.locator("a[href^='https://']").count() >= len(rich["portals"])
    assert "not absence of a record" in block.inner_text()


def test_block_is_hidden_for_a_site_with_no_record(page: Page, base_url: str):
    _ready(page, base_url)
    researched = {s["id"] for s in json.loads(DATA.read_text())["sites"]}
    unresearched = page.evaluate("(ids) => window.__sites.find(s => !ids.includes(s.id)).id", sorted(researched))
    page.evaluate("(id) => window.__selectSite(id)", unresearched)
    page.wait_for_function("window.__localRecords && window.__localRecords.size > 0", timeout=30_000)
    assert page.locator("#d-local-block").is_hidden()


def test_every_shipped_fact_is_https_and_has_a_quote_and_a_second_reader(page: Page, base_url: str):
    for site in json.loads(DATA.read_text())["sites"]:
        for f in site["facts"]:
            assert f["source_url"].startswith("https://") and len(f["quote"]) >= 8
            assert f["status"] in ("accepted", "accepted_code_only", "accepted_model_only"), (site["id"], f)
            assert f.get("verifier") or f.get("adjudicated_by") == "opus", ("no second reader", site["id"], f["source_url"])
