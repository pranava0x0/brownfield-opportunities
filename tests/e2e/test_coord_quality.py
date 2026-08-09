"""E2E tests for the coordinate-confidence note in the detail panel.

The dashboard draws ~47k markers that all look equally authoritative. The
2026-08-09 audit found 118 plotted outside their own state, 17 on typed-in
whole degrees, and 3,728 stacked on shared centroids. These tests assert the
UI now says so.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    # The flags arrive on a lazy enrichment that waits on the program loads.
    page.wait_for_function(
        "(window.__sites || []).some(s => s.coord_flags)", timeout=60_000
    )


def _pick(page: Page, flag: str, exclude: list[str] | None = None) -> str | None:
    return page.evaluate(
        """([flag, exclude]) => {
            const s = (window.__sites || []).find(x =>
                x.coord_flags && x.coord_flags.includes(flag)
                && !(exclude || []).some(e => x.coord_flags.includes(e)));
            return s ? s.id : null;
        }""",
        [flag, exclude or []],
    )


def test_coord_flags_join_across_every_program(page: Page, base_url: str):
    """The load-order race: this file is ~390 KB and resolves long before
    epa-acres.json (~10.9 MB). Without awaiting the program loads, every
    ACRES / FUDS / BRAC flag would be silently dropped — and ACRES is where
    the bad coordinates concentrate, so the bug would hide most of the data.
    """
    _ready(page, base_url)
    by_program = page.evaluate(
        """() => {
            const out = {};
            for (const s of window.__sites || []) {
                if (!s.coord_flags) continue;
                out[s.program] = (out[s.program] || 0) + 1;
            }
            return out;
        }"""
    )
    assert by_program.get("brownfield", 0) > 100, by_program
    assert by_program.get("fuds", 0) > 10, by_program


def test_state_mismatch_note_names_both_states(page: Page, base_url: str):
    _ready(page, base_url)
    sid = _pick(page, "state_mismatch")
    assert sid, "corpus should contain at least one state mismatch"
    page.evaluate("(id) => window.__selectSite(id)", sid)
    note = page.locator("#d-coord-note")
    expect(note).to_be_visible()
    text = note.inner_text()
    rec = page.evaluate("(id) => window.__sites.find(s => s.id === id)", sid)
    assert rec["coord_actual_state"] in text
    assert rec["state"] in text


def test_placeholder_note_renders(page: Page, base_url: str):
    _ready(page, base_url)
    sid = _pick(page, "placeholder", exclude=["state_mismatch", "outside_us"])
    if not sid:
        pytest.skip("no placeholder-only record in the current corpus")
    page.evaluate("(id) => window.__selectSite(id)", sid)
    expect(page.locator("#d-coord-note")).to_contain_text("placeholder")


def test_shared_point_note_counts_the_neighbours(page: Page, base_url: str):
    _ready(page, base_url)
    sid = _pick(page, "shared_point",
                exclude=["state_mismatch", "outside_us", "placeholder"])
    assert sid, "corpus should contain shared-coordinate clusters"
    page.evaluate("(id) => window.__selectSite(id)", sid)
    expect(page.locator("#d-coord-note")).to_contain_text("centroid")


def test_clean_site_shows_no_note(page: Page, base_url: str):
    """Most sites have no known problem and must stay uncluttered."""
    _ready(page, base_url)
    sid = page.evaluate(
        """() => {
            const s = (window.__sites || []).find(
                x => !x.coord_flags && x.lat != null);
            return s ? s.id : null;
        }"""
    )
    assert sid
    page.evaluate("(id) => window.__selectSite(id)", sid)
    expect(page.locator("#d-coord-note")).to_be_hidden()


def test_note_survives_repeated_selection(page: Page, base_url: str):
    """`#d-coord-note` is a sibling inside the coordinate <dd>.

    Writing `textContent` on that <dd> would delete the span — the exact trap
    the FUDS acreage note documents. selectSite() must rewrite only the
    leading text node.
    """
    _ready(page, base_url)
    flagged = _pick(page, "state_mismatch")
    clean = page.evaluate(
        "() => (window.__sites || []).find(x => !x.coord_flags && x.lat != null).id"
    )
    for _ in range(3):
        page.evaluate("(id) => window.__selectSite(id)", flagged)
        expect(page.locator("#d-coord-note")).to_be_visible()
        page.evaluate("(id) => window.__selectSite(id)", clean)
        expect(page.locator("#d-coord-note")).to_be_hidden()
    assert page.locator("#d-coord-note").count() == 1


def test_coordinates_are_never_rewritten_by_the_flag(page: Page, base_url: str):
    """The note is a caveat, not a correction — the displayed value must
    still be the source's own coordinate."""
    _ready(page, base_url)
    sid = _pick(page, "state_mismatch")
    page.evaluate("(id) => window.__selectSite(id)", sid)
    shown = page.evaluate(
        "() => document.getElementById('d-coord').firstChild.nodeValue"
    )
    rec = page.evaluate("(id) => window.__sites.find(s => s.id === id)", sid)
    lat = rec.get("lat_real", rec["lat"])
    lon = rec.get("lon_real", rec["lon"])
    assert shown.strip() == f"{lat:.4f}, {lon:.4f}"
