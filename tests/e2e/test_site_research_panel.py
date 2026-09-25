"""Research dossiers in the detail panel (docs/data/site-research.json).

The dossier file loads with the other detail-panel evidence the first time a
site is selected. These tests cover the rendered dossier and the retry after a
transient fetch failure (PR #38 review: the aggregate detail promise settled
once, so a failed dossier fetch hid all research until a page reload).
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page

DATA = Path(__file__).resolve().parents[2] / "docs" / "data" / "site-research.json"


def _researched_superfund_id() -> str:
    # Superfund records load eagerly, so a Superfund dossier is selectable as
    # soon as the app is ready.
    sites = json.loads(DATA.read_text())["sites"]
    ids = [s["id"] for s in sites if not s["id"].startswith(("ACRES-", "FUDS-", "BRAC-"))]
    assert ids, "site-research.json has no Superfund dossier to test against"
    return ids[0]


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)


def test_dossier_renders_for_a_researched_site(page, base_url):
    site_id = _researched_superfund_id()
    _ready(page, base_url)
    page.evaluate("(id) => window.__selectSite(id)", site_id)
    page.wait_for_selector("#d-research-teaser:not([hidden])", timeout=15_000)
    assert "Researched" in page.locator("#d-research-teaser").inner_text()
    page.locator("#dtab-summary").click()
    card = page.locator("#d-research")
    card.wait_for(state="visible")
    text = card.inner_text()
    assert "next review" in text
    # Every link in the dossier is https (the renderer refuses anything else).
    hrefs = page.eval_on_selector_all("#d-research a", "els => els.map(a => a.href)")
    assert hrefs and all(h.startswith("https://") for h in hrefs), hrefs


def test_dossier_load_retries_after_a_transient_failure(page, base_url):
    site_id = _researched_superfund_id()
    calls = {"n": 0}

    def handle(route):
        calls["n"] += 1
        if calls["n"] == 1:
            route.fulfill(status=503, body="unavailable")
        else:
            route.continue_()

    page.route("**/data/site-research.json", handle)
    _ready(page, base_url)
    with page.expect_response("**/data/site-research.json") as first:
        page.evaluate("(id) => window.__selectSite(id)", site_id)
    assert first.value.status == 503
    # The first fetch failed; the dossier still appears once the retry lands,
    # without reloading the page.
    page.wait_for_selector("#d-research-teaser:not([hidden])", timeout=15_000)
    assert calls["n"] == 2


def test_persistent_failure_does_not_loop(page, base_url):
    site_id = _researched_superfund_id()
    calls = {"n": 0}

    def handle(route):
        calls["n"] += 1
        route.fulfill(status=503, body="unavailable")

    page.route("**/data/site-research.json", handle)
    _ready(page, base_url)
    page.evaluate("(id) => window.__selectSite(id)", site_id)
    page.wait_for_timeout(2_000)
    # One attempt from the detail loader and at most one retry per selection.
    assert calls["n"] <= 2, calls["n"]
    assert page.evaluate("() => document.querySelector('#d-research-teaser').hidden")
    # The panel itself still renders the site.
    assert page.locator("#detail").get_attribute("hidden") is None
