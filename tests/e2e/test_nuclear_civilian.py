"""End-to-end tests for the civilian nuclear pipeline (2026-07-26).

`docs/data/nuclear-civilian-sites.json` (existing + planned civilian
nuclear sites, tiered by INL's Aug-2024 AP1000 deployment study) had been
on disk unrendered. It now ships as a map overlay (⚛ markers for the
promising tiers only) plus a table in the Nuclear Siting tab, with each
marker popup listing the nearest tracked Superfund sites from
`nuclear-brownfield-proximity.json`.

Every expected count is derived FROM the data file at test time — the
dataset grows (67 → 68 rows mid-development), so nothing is hardcoded.
"""
from __future__ import annotations

from playwright.sync_api import Page

# Mirrors NUCLEAR_MAPPED_CATEGORIES in app.js: the promising tiers that earn
# a marker. yellow / red stay data-only so the map stays readable.
MAPPED_CATEGORIES = ["dark_green", "light_green", "blue", "post_study"]


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30_000)


def _dataset(page: Page) -> dict:
    """Read the two data files in-page and derive the expected counts."""
    return page.evaluate(
        """async (mapped) => {
          const sitesR = await fetch('data/nuclear-civilian-sites.json');
          const proxR  = await fetch('data/nuclear-brownfield-proximity.json');
          const sites = (await sitesR.json()).sites || [];
          const prox  = (await proxR.json()).records || [];
          const promising = sites.filter((s) => mapped.includes(s.inl_category));
          const near = new Map(prox.map((r) => [r.nuclear_site_id, r.nearby_brownfields || []]));
          // A dark_green site that actually has neighbours, so the popup's
          // nearby-brownfield block is guaranteed non-empty.
          const withNeighbours = promising.find(
            (s) => s.inl_category === 'dark_green' && (near.get(s.id) || []).length > 0
          );
          return {
            total: sites.length,
            promising: promising.length,
            remainder: sites.length - promising.length,
            sample: withNeighbours ? {
              id: withNeighbours.id,
              name: withNeighbours.name,
              neighbour: (near.get(withNeighbours.id)[0] || {}).id,
            } : null,
          };
        }""",
        MAPPED_CATEGORIES,
    )


def test_nuclear_overlay_loads(page, base_url):
    """The ⚛ overlay lazy-loads exactly one marker per promising-tier site —
    the yellow / red tiers are tracked in the data but stay off the map."""
    _ready(page, base_url)
    data = _dataset(page)
    assert data["promising"] > 0 and data["remainder"] > 0, data
    page.wait_for_function(
        "() => document.querySelectorAll('.nuclear-site-icon').length > 0",
        timeout=15_000,
    )
    count = page.evaluate("() => document.querySelectorAll('.nuclear-site-icon').length")
    assert count == data["promising"], (
        f"expected {data['promising']} ⚛ markers (promising tiers of "
        f"{data['total']} sites), got {count}"
    )


def test_nuclear_legend_row_appears(page, base_url):
    """One legend row for the whole overlay — the readiness tier lives in the
    popup, not in three sub-rows."""
    _ready(page, base_url)
    page.wait_for_function(
        "() => document.querySelectorAll('.nuclear-site-icon').length > 0",
        timeout=15_000,
    )
    page.wait_for_function(
        "() => (document.querySelector('.legend')?.textContent || '')"
        ".includes('Nuclear pipeline site')",
        timeout=10_000,
    )
    legend = page.locator(".legend").text_content() or ""
    data = _dataset(page)
    assert "Nuclear pipeline site" in legend
    assert str(data["promising"]) in legend


def test_nuclear_siting_tab_lists_promising_sites(page, base_url):
    """The Nuclear Siting tab gains a civilian-pipeline table below the
    military screen: one row per promising site, tier-ordered, with a muted
    footnote counting the rows that stayed in the data file."""
    _ready(page, base_url)
    data = _dataset(page)
    page.locator("#tab-ap1000").click()
    page.wait_for_selector(".nuke-civ-table tbody tr")
    rows = page.locator(".nuke-civ-table tbody tr").count()
    assert rows == data["promising"], f"expected {data['promising']} rows, got {rows}"

    heading = page.locator("#nuclear-civilian h3").text_content() or ""
    assert "Civilian nuclear pipeline" in heading
    assert f"{data['total']:,} tracked sites" in heading

    foot = page.locator(".nuke-civ-foot").text_content() or ""
    assert f"{data['remainder']:,} further sites" in foot

    # Tier ordering: dark_green ("AP1000 ready") first.
    tiers = page.evaluate(
        "() => Array.from(document.querySelectorAll('.nuke-civ-table tbody tr "
        ".nuke-civ-cat')).map((c) => c.textContent.trim())"
    )
    assert tiers[0] == "AP1000 ready", tiers[:5]
    order = ["AP1000 ready", "AP1000 feasible", "Restart / SMR", "New entrant (post-2024 study)"]
    ranks = [order.index(t) for t in tiers]
    assert ranks == sorted(ranks), "rows must be grouped by readiness tier"


def test_nuclear_popup_shows_category_and_nearby_brownfields(page, base_url):
    """The per-site "map →" jump switches to the Map tab and opens that
    site's popup, which carries its tier label and links the nearest tracked
    brownfields through the normal ?site=<id> selection path."""
    _ready(page, base_url)
    data = _dataset(page)
    assert data["sample"], "expected a dark_green site with nearby brownfields"
    page.locator("#tab-ap1000").click()
    page.wait_for_selector(".nuke-civ-table tbody tr")
    page.locator(f"[data-nuke-map='{data['sample']['id']}']").click()

    page.wait_for_selector("#view-map.active")
    page.wait_for_selector(".leaflet-popup", timeout=10_000)
    popup = page.locator(".leaflet-popup").text_content() or ""
    assert data["sample"]["name"] in popup
    assert "AP1000 ready" in popup, popup
    assert "Nearby tracked brownfields" in popup, popup

    hrefs = page.evaluate(
        "() => Array.from(document.querySelectorAll('.leaflet-popup .nuke-pop-near a'))"
        ".map((a) => a.getAttribute('href'))"
    )
    assert hrefs, "expected at least one nearby-brownfield link"
    assert all(h.startswith("?site=") for h in hrefs), hrefs
    assert any(data["sample"]["neighbour"] in h for h in hrefs), hrefs


def test_load_failure_shows_error_state_with_working_retry(page: Page, base_url: str) -> None:
    """A failed nuclear-civilian-sites.json fetch must NOT leave the tab
    section on "Loading…" forever (Codex review, PR #20): the section shows an
    explicit error + Retry, and Retry refetches successfully once the source
    recovers (the loader resets its promise on failure)."""
    fail = {"on": True}

    def route_nuclear(route):
        if fail["on"]:
            route.abort()
        else:
            route.fallback()

    page.route("**/nuclear-civilian-sites.json", route_nuclear)
    _ready(page, base_url)  # allSettled tolerates the abort; app still readies

    page.click("#tab-ap1000")
    err = page.locator("#nuclear-civilian p.muted")
    err.wait_for(state="visible", timeout=10_000)
    assert "Couldn’t load" in err.text_content()
    retry = page.locator("#nuke-civ-retry")
    assert retry.count() == 1

    fail["on"] = False  # source recovers
    retry.click()
    page.wait_for_selector("#nuclear-civilian table tbody tr", timeout=15_000)
    rows = page.locator("#nuclear-civilian tbody tr").count()
    assert rows > 0, "retry did not rebuild the civilian table"


def test_missing_primary_dataset_404_shows_error_not_forever_loading(page: Page, base_url: str) -> None:
    """A 404 on the PRIMARY dataset (partial static-site deployment) must hit
    the same error + Retry state as a network failure — not silently succeed
    as an empty list and strand the section on "Loading…" (Codex review #2,
    PR #20). The secondary proximity file keeps its 404 tolerance."""
    page.route(
        "**/nuclear-civilian-sites.json",
        lambda route: route.fulfill(status=404, body="not found"),
    )
    _ready(page, base_url)
    page.click("#tab-ap1000")
    err = page.locator("#nuclear-civilian p.muted")
    err.wait_for(state="visible", timeout=10_000)
    assert "Couldn’t load" in err.text_content()
    assert page.locator("#nuke-civ-retry").count() == 1


def test_proximity_failure_shows_unavailable_not_false_negative(page: Page, base_url: str) -> None:
    """A failed proximity fetch must render 'unavailable' in popups — never
    the definitive 'No tracked Superfund site within 50 mi' claim (Codex
    review #4, PR #20: a fetch failure must not become a false negative)."""
    page.route("**/nuclear-brownfield-proximity.json", lambda route: route.abort())
    _ready(page, base_url)
    # _dataset() would also hit the aborted route — fetch just the sites file.
    target = page.evaluate(
        """async () => {
          const sites = (await (await fetch('data/nuclear-civilian-sites.json')).json()).sites;
          return sites.find((s) => s.inl_category === 'dark_green').id;
        }"""
    )
    page.locator("#tab-ap1000").click()
    page.wait_for_selector(".nuke-civ-table tbody tr")
    page.locator(f"[data-nuke-map='{target}']").click()
    page.wait_for_selector(".leaflet-popup", timeout=10_000)
    popup = page.locator(".leaflet-popup").text_content() or ""
    assert "Nearby-brownfield data unavailable" in popup, popup
    assert "No tracked Superfund site" not in popup, popup


def test_empty_primary_dataset_shows_empty_state_not_loading(page: Page, base_url: str) -> None:
    """A successfully-loaded but EMPTY primary dataset (broken regeneration)
    renders an explicit empty state — not eternal 'Loading…' and not the
    error/Retry path, since a successful empty isn't retryable (Codex review
    #3, PR #20)."""
    page.route(
        "**/nuclear-civilian-sites.json",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"generated_at": "2026-01-01", "sites": []}',
        ),
    )
    _ready(page, base_url)
    page.click("#tab-ap1000")
    msg = page.locator("#nuclear-civilian p.muted")
    msg.wait_for(state="visible", timeout=10_000)
    assert "No civilian nuclear pipeline data available" in msg.text_content()
    assert page.locator("#nuke-civ-retry").count() == 0
