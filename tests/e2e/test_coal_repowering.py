"""E2E guards for the Coal Repowering tab (Spec 04) + the lazy About
architecture section that shipped alongside it.

These pin the regressions found in the 2026-08-23 review of the
feat/coal-repowering-and-arch-pipelines PR:
  - filter <option>s hardcoded to values the data never contains
    ("retiring", "SERC") — options must derive from the dataset
  - status badge falling through to "Retired" for planned_retirement rows
  - the About arch section being always-rendered (~250 nodes) and tripping
    the 5,000-node first-paint budget — it must mount from <template> on
    first About activation only
  - the eighth tab overflowing the mobile tab strip into a page-level
    horizontal scroll (the CLAUDE.md "don't add an eighth tab without
    re-checking" rule, now a test instead of a console one-liner)
"""


def _goto_ready(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)


def test_coal_tab_builds_table_with_derived_filters(page, base_url):
    """Activating the tab builds the table; every filter <option> value
    (beyond 'all') exists in the loaded dataset, and every dataset value has
    an option — the drift-safe-iteration rule (UAT-007) applied to selects."""
    _goto_ready(page, base_url)
    page.click("#tab-coal")
    page.wait_for_selector("#coal-table-container table.coal-table", timeout=15000)
    state = page.evaluate(
        """(() => {
          const rows = document.querySelectorAll('#coal-table-container tbody tr').length;
          const opts = (id) => [...document.querySelectorAll(`#${id} option`)]
            .map(o => o.value).filter(v => v !== 'all');
          return {
            rows,
            statusOpts: opts('coal-status-filter'),
            isoOpts: opts('coal-iso-filter'),
            suitOpts: opts('coal-suitability-filter'),
            dataStatuses: [...new Set((window.__coalAssets || []).map(a => a.status))],
            dataIsos: [...new Set((window.__coalAssets || []).map(a => a.iso_rto))],
          };
        })()"""
    )
    assert state["rows"] >= 15, f"coal table rows: {state['rows']}"
    assert sorted(state["statusOpts"]) == sorted(state["dataStatuses"]), state
    assert sorted(state["isoOpts"]) == sorted(state["dataIsos"]), state
    assert len(state["suitOpts"]) >= 2


def test_coal_status_filter_planned_retirement_matches_rows(page, base_url):
    """The v1 bug: an option value 'retiring' that no record carried, so the
    filter returned zero rows and every planned_retirement badge fell through
    to 'Retired'. Selecting planned_retirement must yield rows whose badge
    reads 'Retiring soon'."""
    _goto_ready(page, base_url)
    page.click("#tab-coal")
    page.wait_for_selector("#coal-table-container table.coal-table", timeout=15000)
    page.select_option("#coal-status-filter", "planned_retirement")
    page.wait_for_function(
        "document.querySelectorAll('#coal-table-container tbody tr').length > 0",
        timeout=5000,
    )
    badges = page.evaluate(
        "[...document.querySelectorAll('#coal-table-container .coal-status-pill')]"
        ".map(e => e.textContent.trim())"
    )
    assert badges and all(b == "Retiring soon" for b in badges), badges


def test_coal_drawer_opens_with_modeled_label_and_citation(page, base_url):
    """The drawer labels the dollar figure as modeled and surfaces the
    per-row source_url + verified_at (the provenance contract, spec 04)."""
    _goto_ready(page, base_url)
    page.click("#tab-coal")
    page.wait_for_selector("#coal-table-container table.coal-table", timeout=15000)
    page.click("#coal-table-container .coal-btn.inspect-btn")
    page.wait_for_selector("#coal-site-drawer:not([hidden])", timeout=5000)
    state = page.evaluate(
        """(() => {
          const body = document.getElementById('coal-drawer-body');
          const cite = body.querySelector('.coal-plant-cite a');
          return {
            text: body.textContent,
            citeHref: cite ? cite.href : null,
          };
        })()"""
    )
    assert "Modeled" in state["text"], "valuation must be labeled as modeled"
    assert state["citeHref"] and state["citeHref"].startswith("https://"), state["citeHref"]
    # Close button hides it again ([hidden] + belt-and-suspenders CSS).
    page.click("#coal-drawer-close")
    page.wait_for_selector("#coal-site-drawer[hidden]", state="attached", timeout=5000)


def test_about_arch_section_mounts_lazily_from_template(page, base_url):
    """At first paint the arch flow-card grid lives in <template> (0 rendered
    nodes); activating About stamps it exactly once."""
    _goto_ready(page, base_url)
    before = page.evaluate(
        "document.querySelectorAll('#about-arch-mount .flow-card').length"
    )
    assert before == 0, "arch cards must not render before About activation"
    page.click("#tab-about")
    page.wait_for_selector("#about-arch-mount .flow-card", timeout=5000)
    counts = page.evaluate(
        """(() => ({
          cards: document.querySelectorAll('#about-arch-mount .flow-card').length,
          master: document.querySelectorAll('#about-arch-mount .master-card').length,
        }))()"""
    )
    assert counts["cards"] >= 7, counts
    assert counts["master"] == 1, counts
    # Re-activating About must not double-mount.
    page.click("#tab-map")
    page.click("#tab-about")
    again = page.evaluate(
        "document.querySelectorAll('#about-arch-mount .master-card').length"
    )
    assert again == 1, "template stamped more than once"


def test_arch_section_contains_no_raw_latex(page, base_url):
    """The v1 draft shipped $\\text{...}$ LaTeX into plain HTML where it
    renders as literal dollar-sign soup — no MathJax exists on this page."""
    _goto_ready(page, base_url)
    page.click("#tab-about")
    page.wait_for_selector("#about-arch-mount .flow-card", timeout=5000)
    text = page.evaluate("document.getElementById('about-arch-mount').textContent")
    for marker in ("\\text", "\\le", "\\times", "$O(", "$V ="):
        assert marker not in text, f"raw LaTeX marker {marker!r} in About arch copy"


def test_tab_strip_no_horizontal_page_scroll_mobile(page, base_url):
    """CANONICAL eighth-tab guard: at 375px the tab strip must scroll
    internally — the document itself must have zero horizontal overflow.
    (CLAUDE.md: 'Don't add an eighth tab without re-checking that number' —
    this makes the check permanent.)"""
    page.set_viewport_size({"width": 375, "height": 812})
    _goto_ready(page, base_url)
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow == 0, f"page-level horizontal overflow: {overflow}px"


def test_coal_csv_export_serves_the_filtered_catalog(page, base_url):
    """Codex round 2: the GLOBAL topbar export serves the brownfield corpus,
    so the Coal tab ships its own Export CSV. The CSV must contain exactly
    the filtered catalog rows (header + N), carry the citation columns, and
    shrink when a filter narrows the table."""
    _goto_ready(page, base_url)
    page.click("#tab-coal")
    page.wait_for_selector("#coal-table-container table.coal-table", timeout=15000)
    state = page.evaluate(
        """(() => {
          const all = window.__buildCoalCsv().split('\\n');
          document.getElementById('coal-status-filter').value = 'planned_retirement';
          document.getElementById('coal-status-filter').dispatchEvent(new Event('change'));
          const filtered = window.__buildCoalCsv().split('\\n');
          return {
            btn: !!document.getElementById('coal-export-csv'),
            header: all[0],
            allRows: all.length - 1,
            filteredRows: filtered.length - 1,
            assets: (window.__coalAssets || []).length,
            planned: (window.__coalAssets || []).filter(a => a.status === 'planned_retirement').length,
          };
        })()"""
    )
    assert state["btn"], "coal Export CSV button missing"
    assert state["allRows"] == state["assets"], state
    assert state["filteredRows"] == state["planned"] > 0, state
    for col in ("plant_name", "source_url", "verified_at", "modeled_stranded_value_usd", "poi_occupied"):
        assert col in state["header"], state["header"]


def test_coal_load_failure_shows_retry_not_forever_loading(page, base_url):
    """Codex review P2: a failed catalog fetch must render a retryable error,
    never an indefinite 'Loading…'. The retry button re-fetches (the loader
    nulls its promise on failure) and builds the table."""
    blocked = {"on": True}

    def route_coal(route):
        if blocked["on"]:
            route.abort()
        else:
            route.fallback()

    page.route("**/data/coal-conversions.json", route_coal)
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__sitesLoaded === true", timeout=20000)
    page.click("#tab-coal")
    page.wait_for_selector("#coal-table-container button.coal-btn", timeout=10000)
    text = page.evaluate("document.getElementById('coal-table-container').textContent")
    assert "failed to load" in text, text
    # Unblock and retry — the table must build.
    blocked["on"] = False
    page.click("#coal-table-container button.coal-btn")
    page.wait_for_selector("#coal-table-container table.coal-table", timeout=15000)


def test_map_overlays_render_markers_and_legend(page, base_url):
    """The map surfaces of BOTH overlays: 18 ⬢ coal + 10 🏛 federal markers
    exist with the glyph directly in the styled icon div (no orphaned inner
    span — the CSS targets the class itself), and the legend gains both rows.
    This is the path findings #1/#2 of the 2026-08-23 review shipped through
    untested."""
    _goto_ready(page, base_url)
    state = page.evaluate(
        """(() => {
          const coal = [...document.querySelectorAll('.coal-repowering-icon')];
          const fed = [...document.querySelectorAll('.federal-site-icon')];
          const legend = document.querySelector('.legend') || document.body;
          const firstCoal = coal[0];
          return {
            coal: coal.length,
            fed: fed.length,
            coalHasInnerSpan: firstCoal ? !!firstCoal.querySelector('span') : null,
            coalStyled: firstCoal ? getComputedStyle(firstCoal).fontSize : null,
            legendText: legend.textContent,
          };
        })()"""
    )
    assert state["coal"] == 18, state
    assert state["fed"] == 10, state
    assert state["coalHasInnerSpan"] is False, "glyph must live directly in the icon div"
    assert state["coalStyled"] == "17px", f"marker CSS not applied: {state['coalStyled']}"
    assert "Coal repowering asset" in state["legendText"]
    assert "Federal clean energy" in state["legendText"]


def test_drawer_nearby_shows_unavailable_not_negative_on_prox_failure(page, base_url):
    """Codex round 4: a failed proximity load must render 'unavailable' with a
    working Retry — never the negative claim 'no tracked sites within 10 mi'
    (absence means unknown). Retry re-fetches (promise nulled) and rebuilds."""
    blocked = {"on": True}

    def route_prox(route):
        if blocked["on"]:
            route.abort()
        else:
            route.fallback()

    page.route("**/data/coal-conversions-proximity.json", route_prox)
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.click("#tab-coal")
    page.wait_for_selector("#coal-table-container table.coal-table", timeout=15000)
    page.click("#coal-table-container .coal-btn.inspect-btn")
    page.wait_for_selector("#coal-site-drawer:not([hidden])", timeout=5000)
    text = page.evaluate("document.getElementById('coal-drawer-body').textContent")
    assert "failed to load" in text, text
    assert "No tracked brownfield sites" not in text, "negative claim rendered for a failed load"
    blocked["on"] = False
    page.click("#coal-drawer-body .coal-nearby-retry")
    page.wait_for_selector("#coal-drawer-body .coal-nearby-section, #coal-drawer-body .coal-nearby-item", timeout=15000)


def test_coal_join_reapplies_after_restricted_boot_then_reset(page, base_url):
    """Codex round 3: booting with ?program=superfund leaves the ACRES/FUDS/
    BRAC promises null, so the initial proximity apply only reaches Superfund.
    Pressing Reset later loads those programs — the cached join must re-apply
    so their matches carry the coal fields for the rest of the session."""
    page.goto(f"{base_url}/index.html?program=superfund")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    acres_id = page.evaluate(
        """(async () => {
          const j = await (await fetch('data/coal-conversions-proximity.json')).json();
          const m = (j.matches || []).find(x => x.id.startsWith('ACRES-'));
          return m ? m.id : null;
        })()"""
    )
    assert acres_id, "shipped proximity file has no ACRES match — test needs updating"
    # Not loaded yet under the restricted URL.
    assert page.evaluate(f"window.__sites.some(s => s.id === '{acres_id}')") is False
    # Reset lives inside the (closed) filters panel — dispatch the click
    # directly; the visibility of the button is covered by the Reset e2e
    # tests, this one exercises the join re-apply.
    page.evaluate("document.getElementById('filters-reset').click()")
    page.wait_for_function(
        f"""(() => {{
          const s = window.__sites.find(x => x.id === '{acres_id}');
          return !!(s && s.coal_conversion_plant_name);
        }})()""",
        timeout=30000,
    )


def test_coal_detail_cell_renders_for_joined_site(page, base_url):
    """A site inside the 10-mi join renders the 'Coal repowering' row with a
    clickable chip labeled as modeled; a site outside stays 'Not available'."""
    _goto_ready(page, base_url)
    result = page.evaluate(
        """(async () => {
          // Wait for the proximity join to land on some site.
          for (let i = 0; i < 100; i++) {
            const hit = window.__sites.find(s => s.coal_conversion_plant_mi != null);
            if (hit) { window.__selectSite(hit.id); break; }
            await new Promise(r => setTimeout(r, 200));
          }
          const cell = document.getElementById('d-coal-repower-mi');
          return cell ? cell.textContent : null;
        })()"""
    )
    assert result and "modeled" in result, result
