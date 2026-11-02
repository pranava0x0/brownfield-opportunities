"""How the Screens view behaves while its data is still arriving, and how fast it answers a tap."""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_skeleton_and_progress_show_while_inputs_download_and_nothing_is_ranked(page: Page, base_url: str):
    held = []
    page.route("**/data/infra-proximity-core.json", lambda route: held.append(route))   # park one required input
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__sitesLoaded === true", timeout=45_000)
    stats = page.locator("#candidates-stats")
    expect(stats).to_contain_text("Loading", timeout=15_000)
    expect(stats).to_contain_text("ready)")
    assert page.locator("#candidates-skeleton").is_visible()
    assert page.locator("#candidates-wrap").get_attribute("aria-busy") == "true"
    assert page.locator("#candidates-table tbody tr").count() == 0, "a partial corpus must not be ranked"
    for route in held:
        route.continue_()
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    expect(page.locator("#candidates-table tbody tr").first).to_be_visible(timeout=30_000)
    assert page.locator("#candidates-skeleton").is_hidden()
    assert page.locator("#candidates-wrap").get_attribute("aria-busy") == "false"


def test_ranking_runs_once_for_a_page_load_not_once_per_download(page: Page, base_url: str):
    page.add_init_script("""
      window.__rankCalls = 0;
      document.addEventListener('DOMContentLoaded', () => {
        const orig = SiteScreens.rank;
        SiteScreens.rank = function () { window.__rankCalls++; return orig.apply(this, arguments); };
      });
    """)
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    expect(page.locator("#candidates-table tbody tr").first).to_be_visible(timeout=30_000)
    calls = page.evaluate("window.__rankCalls")
    assert 1 <= calls <= 3, f"ranked {calls} times during load (it was once per lazy download before)"


def test_lens_button_is_lit_before_the_ranking_finishes(page: Page, base_url: str):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    expect(page.locator("#candidates-table tbody tr").first).to_be_visible(timeout=30_000)
    state = page.evaluate("""() => new Promise(resolve => {
      const btn = document.querySelector('[data-cand-lens="solar"]');
      btn.click();
      // Synchronously after the click: pressed state is painted-ready, the ranking has not run yet.
      resolve({active: btn.classList.contains('active'), busy: document.getElementById('candidates-wrap').getAttribute('aria-busy')});
    })""")
    assert state == {"active": True, "busy": "true"}
    page.wait_for_function("document.getElementById('candidates-wrap').getAttribute('aria-busy') === 'false'", timeout=30_000)
    expect(page.locator("#candidates-table tbody tr").first).to_be_visible()
