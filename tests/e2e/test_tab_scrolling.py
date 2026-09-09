"""Every tab must be able to reach its own content.

This guard exists because the bug has now shipped twice. `.view` is
`position: absolute; inset: 0`, so a tab view fills its container and CANNOT
scroll the document — each scrolling view has to declare its own
`overflow: auto`, and forgetting it is invisible in review and in every
functional test. The Maritime tab shipped in PR #26 with 14,475px of content
inside a 649px box and no way to reach the second row; the Nickel tab
reproduced it exactly one PR later.

Nothing about a tab's own tests catches this: the rows are in the DOM, the
scores are right, the table is "visible". Only the geometry is wrong. So the
check lives here, once, across every tab and every breakpoint, rather than
being re-remembered per feature.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

TABS = ["map", "table", "candidates", "retired", "coal", "ap1000",
        "micro", "hanford", "maritime", "nickel", "about"]

# Phone, tablet, laptop. The band between the 640px mobile breakpoint and the
# desktop layout is where the tab-strip overflow regression lived, so it is
# represented here too.
VIEWPORTS = [("mobile", 390, 844), ("tablet", 820, 1180), ("laptop", 1280, 800)]

_PROBE = """(t) => {
  const v = document.getElementById('view-' + t);
  if (!v) return null;
  const cs = getComputedStyle(v);
  const scrolls = (el) => {
    const c = getComputedStyle(el);
    return (c.overflowY === 'auto' || c.overflowY === 'scroll')
      && el.scrollHeight > el.clientHeight + 2;
  };
  let childScrolls = false;
  for (const el of v.querySelectorAll('*')) {
    if (scrolls(el)) { childScrolls = true; break; }
  }
  return {
    needsScroll: v.scrollHeight > v.clientHeight + 2,
    viewScrolls: cs.overflowY === 'auto' || cs.overflowY === 'scroll',
    childScrolls,
    clientH: v.clientHeight,
    scrollH: v.scrollHeight,
    hOverflow: document.documentElement.scrollWidth
               - document.documentElement.clientWidth,
  };
}"""


@pytest.mark.parametrize("label,width,height", VIEWPORTS)
def test_every_tab_can_reach_its_own_content(
        page: Page, base_url: str, label: str, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)

    unreachable = []
    for tab in TABS:
        # At narrow widths the tab strip scrolls horizontally, so a tab can sit
        # outside the visible band. Scroll it in first — that is what a user
        # does, and a bare click can time out waiting for stability.
        btn = page.locator(f"#tab-{tab}")
        btn.scroll_into_view_if_needed(timeout=10_000)
        btn.click(timeout=10_000)
        page.wait_for_timeout(300)
        r = page.evaluate(_PROBE, tab)
        assert r is not None, f"#view-{tab} missing"
        if r["needsScroll"] and not r["viewScrolls"] and not r["childScrolls"]:
            unreachable.append(
                f"{tab}: {r['scrollH']}px of content in a {r['clientH']}px box, "
                "no scroll container")
    assert not unreachable, (
        f"tabs whose content cannot be reached at {label} ({width}x{height}): "
        + "; ".join(unreachable))


@pytest.mark.parametrize("label,width,height", VIEWPORTS)
def test_no_tab_scrolls_the_page_sideways(
        page: Page, base_url: str, label: str, width: int, height: int) -> None:
    """Horizontal overflow escapes onto the document and scrolls the whole
    page, which looks like a broken layout on every tab rather than the one
    that caused it."""
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)

    offenders = []
    for tab in TABS:
        btn = page.locator(f"#tab-{tab}")
        btn.scroll_into_view_if_needed(timeout=10_000)
        btn.click(timeout=10_000)
        page.wait_for_timeout(300)
        over = page.evaluate(
            "document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth")
        if over > 0:
            offenders.append(f"{tab}: {over}px")
    assert not offenders, (
        f"tabs scrolling the page sideways at {label} ({width}x{height}): "
        + "; ".join(offenders))
