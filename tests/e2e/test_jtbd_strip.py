"""End-to-end tests for the JTBD quick-start strip (2026-07-26).

A slim header strip that answers "what are you siting?" in one click:
each job chip routes to the view + scoring lens that answers it, by
CLICKING the real tab / lens buttons (so lens state, active classes, the
rebuild, and the ?lens= URL sync stay on one code path). The strip stays
visible after a pick — users try several jobs — and only the × dismisses
it, persisted in localStorage and applied before first paint.
"""
from __future__ import annotations

from playwright.sync_api import Page


def _ready(page: Page, base_url: str, query: str = "") -> None:
    page.goto(f"{base_url}/index.html{query}")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)


def test_strip_renders_four_job_chips(page, base_url):
    """The strip is visible on a first visit with one chip per job."""
    _ready(page, base_url)
    strip = page.locator("#jtbd-strip")
    assert strip.is_visible()
    jobs = page.evaluate(
        "() => Array.from(document.querySelectorAll('#jtbd-strip [data-jtbd]'))"
        ".map((b) => b.dataset.jtbd)"
    )
    assert jobs == ["dc", "gen", "reactor", "mfg"], jobs
    # Every chip carries a readable label, and the dismiss control exists.
    labels = page.evaluate(
        "() => Array.from(document.querySelectorAll('#jtbd-strip [data-jtbd]'))"
        ".map((b) => b.textContent.trim())"
    )
    assert all(len(t) > 3 for t in labels), labels
    assert page.locator("#jtbd-dismiss").is_visible()


def test_generation_chip_routes_to_rankings_with_gen_lens(page, base_url):
    """"Power generation" activates the Rankings tab on the Generation lens,
    with the lens button lit and ?lens=gen round-tripped through the URL —
    i.e. it reuses the real lens-click path rather than a parallel one."""
    _ready(page, base_url)
    assert "lens=" not in page.evaluate("location.search")
    page.locator("[data-jtbd='gen']").click()
    page.wait_for_selector("#view-candidates.active")
    page.wait_for_function("location.search.includes('lens=gen')")
    page.wait_for_function(
        "() => document.getElementById('candidates-stats').textContent"
        ".includes('generation score')"
    )
    active = page.evaluate(
        "document.querySelector('[data-cand-lens].active')?.dataset.candLens"
    )
    assert active == "gen"
    assert page.locator("#candidates-table tbody tr").count() > 0


def test_factory_chip_routes_to_manufacturing_lens(page, base_url):
    """The Factory job maps to the Manufacturing lens (?lens=mfg)."""
    _ready(page, base_url)
    page.locator("[data-jtbd='mfg']").click()
    page.wait_for_selector("#view-candidates.active")
    page.wait_for_function("location.search.includes('lens=mfg')")
    page.wait_for_function(
        "() => document.getElementById('candidates-stats').textContent"
        ".includes('manufacturing score')"
    )


def test_reactor_chip_activates_nuclear_siting_view(page, base_url):
    """The Nuclear reactor job opens the Nuclear Siting tab."""
    _ready(page, base_url)
    page.locator("[data-jtbd='reactor']").click()
    page.wait_for_selector("#view-ap1000.active")
    assert page.locator("#tab-ap1000").get_attribute("aria-selected") == "true"
    assert page.locator("#view-map").is_hidden()


def test_job_chip_does_not_dismiss_the_strip(page, base_url):
    """Picking a job keeps the strip up — users compare several jobs. Only
    the × hides it."""
    _ready(page, base_url)
    page.locator("[data-jtbd='dc']").click()
    page.wait_for_selector("#view-candidates.active")
    assert page.locator("#jtbd-strip").is_visible()
    page.locator("[data-jtbd='reactor']").click()
    page.wait_for_selector("#view-ap1000.active")
    assert page.locator("#jtbd-strip").is_visible()


def test_dismiss_hides_strip_and_persists_across_reload(page, base_url):
    """× hides the strip (via the `hidden` attribute, which must actually
    remove it from layout — the [hidden] trap) and it stays hidden on the
    next visit. The hide runs at app.js top level, so on reload the strip is
    already hidden by the time the document has loaded — no flash."""
    _ready(page, base_url)
    page.locator("#jtbd-dismiss").click()
    assert page.locator("#jtbd-strip").is_hidden()
    assert page.evaluate(
        "getComputedStyle(document.getElementById('jtbd-strip')).display"
    ) == "none", "the `hidden` attribute must beat the strip's display:flex"
    assert page.evaluate("localStorage.getItem('jtbdDismissed')") == "1"

    page.goto(f"{base_url}/index.html")
    page.wait_for_selector("#jtbd-strip", state="attached")
    assert page.evaluate("document.getElementById('jtbd-strip').hidden") is True
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)
    assert page.locator("#jtbd-strip").is_hidden()


def test_strip_stays_within_dom_budget(page, base_url):
    """First-paint DOM budget: the strip is ~20 nodes at most and the page
    stays under the 5,000-node cap enforced by test_dom_size_under_5k_nodes."""
    _ready(page, base_url)
    counts = page.evaluate(
        "() => ({"
        "  strip: document.getElementById('jtbd-strip').querySelectorAll('*').length + 1,"
        "  total: document.querySelectorAll('*').length,"
        "})"
    )
    assert counts["strip"] <= 20, counts
    assert counts["total"] < 5000, counts
