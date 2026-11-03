"""Manufacturing screens: each ranks the corpus, lists its cited plants, and matches the shell CLI."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((ROOT / "docs" / "data" / "manufacturing-facilities.json").read_text())
LENSES = ["robotics", "turbine", "transformer", "minerals"]


def _pick(page: Page, base_url: str, lens: str) -> None:
    page.goto(f"{base_url}/index.html?lens={lens}")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.wait_for_function("document.querySelectorAll('#candidates-table tbody tr').length >= 10", timeout=60_000)


@pytest.mark.parametrize("lens", LENSES)
def test_screen_ranks_and_lists_its_plants_and_requirements(page: Page, base_url: str, lens: str):
    _pick(page, base_url, lens)
    assert page.locator(f'[data-cand-lens="{lens}"].active').count() == 1
    summary = page.locator("#screen-method .mfg-evidence > summary").text_content()
    rows = [s for s in CATALOG["sites"] if s["sector"] == lens]
    active = sum(1 for s in rows if s["status"] not in ("cancelled", "paused"))
    assert summary.startswith(f"{active} US plant")
    if active < len(rows):
        assert f"({len(rows) - active} cancelled or paused)" in summary
    page.locator("#screen-method .mfg-evidence > summary").click()
    assert page.locator("#screen-method .mfg-plants li a[href^='https://']").count() == len(rows)


@pytest.mark.parametrize("lens", LENSES)
def test_browser_rank_matches_the_shell_cli(page: Page, base_url: str, lens: str):
    _pick(page, base_url, lens)
    page_ids = page.evaluate("()=>Array.from(document.querySelectorAll('#candidates-table tbody tr')).slice(0,10).map(r=>r.dataset.id)")
    out = subprocess.run(["node", "scripts/screen.js", "top", lens, "10"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert page_ids == [line.split()[3] for line in out.strip().splitlines()]


def test_top_robot_site_shows_a_measured_plant_distance(page: Page, base_url: str):
    import re
    _pick(page, base_url, "robotics")
    cell = page.locator('#candidates-table tbody tr').first.locator('td[data-label="Robot or AI-hardware plant within 100 mi"]')
    assert cell.get_attribute("data-status") == "pass"
    assert re.search(r"\d+ mi · \S", cell.text_content()), cell.text_content()
    # No coordinates, no distance: unknown, never a pass.
    ev = page.evaluate("()=>{const s={id:'x'};window.SiteScreens.stampManufacturing([s],[{sector:'robotics',status:'operating',name:'p',lat:30,lon:-95}]);"
                       "return window.SiteScreens.evaluate(s,'robotics').results.find(r=>r.id==='cluster').status}")
    assert ev == "unknown"


def test_a_failed_catalog_is_reported_and_a_retry_updates_the_open_site(page: Page, base_url: str):
    page.route("**/data/manufacturing-facilities.json", lambda route: route.abort())
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.wait_for_function("document.querySelectorAll('#candidates-table tbody tr').length >= 1", timeout=60_000)
    page.locator("#candidates-table tbody tr .site-evidence-open").first.click()
    chip = page.locator("#d-suit-dc .screen-chip", has_text="Robot or AI-hardware plant")
    page.wait_for_function("document.querySelector('#d-suit-dc .screen-summary')", timeout=30_000)
    assert chip.first.get_attribute("data-status") == "unknown"
    page.locator('[data-cand-lens="robotics"]').click()
    page.wait_for_function("(document.getElementById('candidates-stats')?.textContent || '').includes('plant catalog')", timeout=30_000)
    page.unroute("**/data/manufacturing-facilities.json")
    page.locator("#screen-retry").click()
    page.wait_for_function("document.querySelectorAll('#candidates-table tbody tr').length >= 10", timeout=60_000)
    # The drawer that was open when the catalog arrived is re-rendered with the distance.
    page.wait_for_function("[...document.querySelectorAll('#d-suit-dc .screen-chip')].some(c => c.textContent.includes('Robot or AI-hardware plant') && c.dataset.status !== 'unknown')", timeout=30_000)


def test_plant_markers_load_with_a_source_link(page: Page, base_url: str):
    page.goto(f"{base_url}/index.html#map")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.wait_for_function(f"document.querySelectorAll('.mfg-icon').length === {len(CATALOG['sites'])}", timeout=60_000)
    # A marker can sit under another overlay or outside the view; dispatch the click Leaflet listens for.
    page.locator(".mfg-icon").first.dispatch_event("click")
    page.wait_for_selector(".leaflet-popup .ref-campus-link[href^='https://']", timeout=10_000)
    assert "not the plant" in page.locator(".leaflet-popup").text_content()
