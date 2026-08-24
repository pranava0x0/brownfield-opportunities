"""E2E guards for the DOE Sites dossier tab (2026-08-24 restructure).

What these pin:
  - the tab mounts lazily from <template id="hanford-template"> exactly once
    and renders the answers-first layout: site pills, at-a-glance header,
    the open facility-fit matrix, the land-unit card grid, and the cited
    infrastructure section — with methodology collapsed at the bottom
  - the best-fit ranking regression: an all-precluded unit says
    "None — off the table", never a list of all four types
  - fit-matrix cells are real buttons whose click reveals the rationale,
    binding constraint, and citations (never tooltip-only)
  - the unit drawer renders ONE unit at a time with its environmental
    screen, corpus join, prior federal decision documents, and citations
  - the site switcher lazy-loads a sibling site (Paducah) and the ?doe=
    deep link works
  - the ▣ markers + legend row exist at APP_READY (Hanford loads eagerly
    because its generated_at drives the displayed refresh date)
  - the AI-narrative disclosure renders (every AI-drafted surface says so)
"""


def _goto_ready(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)


def _open_doe(page, base_url):
    _goto_ready(page, base_url)
    page.click("#tab-hanford")
    page.wait_for_selector("#view-hanford .doe-parcel-card", timeout=15000)


def _open_drawer(page, parcel_id):
    page.click(f'.doe-parcel-card[data-parcel="{parcel_id}"]')
    page.wait_for_selector("#doe-drawer:not([hidden])", timeout=10000)


def test_doe_tab_renders_answers_first_layout(page, base_url):
    _open_doe(page, base_url)
    state = page.evaluate(
        """(() => {
          const view = document.getElementById('view-hanford');
          const content = document.getElementById('hanford-content');
          const order = [...content.children].map(c => (c.className || '').toString().split(' ')[0]);
          return {
            pills: view.querySelectorAll('.doe-pill').length,
            glance: !!view.querySelector('.doe-glance'),
            stats: view.querySelectorAll('.doe-stat').length,
            matrixRows: view.querySelectorAll('.doe-fit-row').length,
            fitCellButtons: view.querySelectorAll('.doe-fit-cell-btn').length,
            cards: view.querySelectorAll('.doe-parcel-card').length,
            infra: !!view.querySelector('#doe-infra'),
            infraRows: view.querySelectorAll('.doe-infra-row').length,
            managers: view.querySelectorAll('.hanford-mgr').length,
            sourceRows: view.querySelectorAll('.hanford-sources .hanford-pathway-table tbody tr').length,
            sourcesOpen: view.querySelector('.hanford-sources').open,
            firstSection: order[1],
            drawerHidden: document.getElementById('doe-drawer').hidden,
          };
        })()"""
    )
    assert state["pills"] == 5
    assert state["glance"] is True
    assert state["stats"] >= 4
    assert state["matrixRows"] == 9
    assert state["fitCellButtons"] == 36
    assert state["cards"] == 9
    assert state["infra"] is True
    assert state["infraRows"] >= 6  # all seven categories, 8 rows for Hanford
    assert state["managers"] == 5
    assert state["sourceRows"] == 11
    # Methodology is reference material now — collapsed, at the bottom.
    assert state["sourcesOpen"] is False
    # The first content section after the pills is the at-a-glance header.
    assert state["firstSection"] == "doe-glance"
    assert state["drawerHidden"] is True


def test_facility_fit_best_fit_ranking(page, base_url):
    """2026-08-24 regression: the old tie-listing rendered an all-precluded
    unit's best fit as "Data center / Large reactor / SMR / Microreactor" —
    fit-for-everything, the exact opposite of the data. All-precluded must
    read "None — off the table"."""
    _open_doe(page, base_url)
    result = page.evaluate(
        """() => {
          const rowBest = (pid) => {
            const row = document.querySelector(`tr.doe-fit-row[data-parcel="${pid}"]`);
            return row ? row.querySelector('.hanford-best-fit').textContent.trim() : null;
          };
          return {
            energyNorthwest: rowBest('hanford-energy-northwest'),
            area300: rowBest('hanford-300-area'),
            area200: rowBest('hanford-200-area'),
            monument: rowBest('hanford-reach-monument'),
          };
        }"""
    )
    assert result["energyNorthwest"] == "Large reactor / SMR"
    assert result["area300"] == "Microreactor"
    assert result["area200"] == "None — off the table"
    assert result["monument"] == "None — off the table"


def test_fit_cell_click_reveals_cited_reasoning(page, base_url):
    """The old matrix trapped rationales in title attributes — invisible on
    touch and to assistive tech, with no citation. Cells are now buttons
    whose click opens a reasoning row with the rationale, the binding
    constraint, and source links."""
    _open_doe(page, base_url)
    page.click('.doe-fit-cell-btn[data-parcel="hanford-300-area"][data-type="microreactor"]')
    state = page.evaluate(
        """(() => {
          const detail = document.querySelector('tr.doe-fit-detail[data-parcel="hanford-300-area"]');
          const hot = detail.querySelector('.doe-fit-reason.doe-reason-hot');
          return {
            open: !detail.hidden,
            hotType: hot ? hot.dataset.type : null,
            hasConstraint: !!hot.querySelector('.hp-constraint'),
            rationaleLen: hot.querySelector('p').textContent.length,
            citeLinks: hot.querySelectorAll('.doe-fit-cites a').length,
            ariaExpanded: document.querySelector(
              '.doe-fit-cell-btn[data-parcel="hanford-300-area"][data-type="microreactor"]'
            ).getAttribute('aria-expanded'),
          };
        })()"""
    )
    assert state["open"] is True
    assert state["hotType"] == "microreactor"
    assert state["hasConstraint"] is True
    assert state["rationaleLen"] > 50
    assert state["citeLinks"] >= 1
    assert state["ariaExpanded"] == "true"


def test_parcel_drawer_opens_one_unit_at_a_time(page, base_url):
    _open_doe(page, base_url)
    _open_drawer(page, "hanford-energy-northwest")
    first = page.evaluate(
        """(() => {
          const d = document.getElementById('doe-drawer');
          return {
            title: d.querySelector('h3').textContent,
            screenRows: d.querySelectorAll('.hanford-screen-table tbody tr').length,
            inlineCites: d.querySelectorAll('.doe-inline-cite').length,
            close: !!document.getElementById('doe-drawer-close'),
          };
        })()"""
    )
    assert "Energy Northwest" in first["title"]
    assert first["screenRows"] == 10  # Hanford runs the full ten-source screen
    assert first["inlineCites"] >= 2  # status + availability each carry a cite
    # Opening a second unit replaces the drawer content (one at a time).
    _open_drawer(page, "hanford-100-area")
    second = page.evaluate(
        "document.getElementById('doe-drawer').querySelector('h3').textContent"
    )
    assert "100 Area" in second
    # Close hides the drawer.
    page.click("#doe-drawer-close")
    page.wait_for_selector("#doe-drawer[hidden]", state="attached", timeout=10000)


def test_drawer_shows_corpus_join_and_decision_docs(page, base_url):
    """The 300-Area drawer must show the dashboard's own infra-proximity
    values joined onto the unit AND the prior federal decision documents
    (CERCLA RODs / Five-Year Reviews) from the epa-superfund-docs join —
    the 2026-08-24 backlog quick win."""
    _open_doe(page, base_url)
    _open_drawer(page, "hanford-300-area")
    state = page.evaluate(
        """(() => {
          const d = document.getElementById('doe-drawer');
          const corpus = d.querySelector('.hanford-corpus');
          return {
            corpusText: corpus ? corpus.textContent : '',
            docs: d.querySelectorAll('.doe-docs li').length,
          };
        })()"""
    )
    assert "Transmission" in state["corpusText"]
    assert "NPL status" in state["corpusText"]
    assert state["docs"] >= 1


def test_site_switcher_loads_lazy_site(page, base_url):
    """Clicking the Paducah pill lazy-loads paducah-e2e.json and renders its
    dossier through the same code path; its markers join the map layer."""
    _open_doe(page, base_url)
    page.click('.doe-pill[data-doe-site="paducah"]')
    page.wait_for_function(
        "window.__doeSites && !!window.__doeSites.paducah", timeout=15000
    )
    page.wait_for_selector('.doe-parcel-card[data-parcel="paducah-ai-campus"]', timeout=10000)
    state = page.evaluate(
        """(() => ({
          glanceName: document.querySelector('.doe-glance h3').textContent,
          cards: document.querySelectorAll('.doe-parcel-card').length,
          matrixRows: document.querySelectorAll('.doe-fit-row').length,
          markers: document.querySelectorAll('.hanford-parcel-icon').length,
          url: location.search,
        }))()"""
    )
    assert "Paducah" in state["glanceName"]
    assert state["cards"] == 5
    assert state["matrixRows"] == 5
    assert state["markers"] == 14  # 9 Hanford + 5 Paducah
    # Drawer works on the lazy site; screening may be pending (which must
    # render as an explicit pending note, never a silent no-hit).
    _open_drawer(page, "paducah-ai-campus")
    drawer = page.evaluate(
        """(() => {
          const d = document.getElementById('doe-drawer');
          return {
            title: d.querySelector('h3').textContent,
            screenRows: d.querySelectorAll('.hanford-screen-table tbody tr').length,
            pendingNote: d.textContent.includes('not yet run'),
          };
        })()"""
    )
    assert "Brookfield" in drawer["title"] or "AI/HPC" in drawer["title"]
    assert drawer["screenRows"] in (0, 8) or drawer["pendingNote"]
    if drawer["screenRows"] == 0:
        assert drawer["pendingNote"] is True


def test_doe_deep_link_selects_site(page, base_url):
    page.goto(f"{base_url}/index.html?doe=wipp#hanford")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.wait_for_selector('.doe-parcel-card[data-parcel="wipp-lwa-balance"]', timeout=15000)
    active = page.evaluate(
        "document.querySelector('.doe-pill-active').dataset.doeSite"
    )
    assert active == "wipp"


def test_infrastructure_section_covers_gas_and_td_with_citations(page, base_url):
    """The seven-category infrastructure vocabulary (power_td + natural_gas
    added 2026-08-24 by user direction) — every rendered row carries its own
    source link, and Hanford's gas row states the honest no-pipeline fact."""
    _open_doe(page, base_url)
    state = page.evaluate(
        """(() => {
          const rows = [...document.querySelectorAll('.doe-infra-row')];
          const byHead = {};
          for (const r of rows) byHead[r.querySelector('h4').textContent] = r;
          const gas = byHead['Natural gas'];
          const td = byHead['Power — transmission & distribution'];
          return {
            heads: Object.keys(byHead),
            gasText: gas ? gas.textContent : '',
            gasCites: gas ? gas.querySelectorAll('a').length : 0,
            tdCites: td ? td.querySelectorAll('a').length : 0,
            allRowsCited: rows.every(r => r.querySelectorAll('a').length >= 1),
          };
        })()"""
    )
    assert "Natural gas" in state["heads"]
    assert "Power — transmission & distribution" in state["heads"]
    assert "NO dedicated natural-gas pipeline" in state["gasText"]
    assert state["gasCites"] >= 1
    assert state["tdCites"] >= 1
    assert state["allRowsCited"] is True


def test_ai_disclosure_renders(page, base_url):
    _open_doe(page, base_url)
    note = page.evaluate(
        "document.querySelector('.doe-ai-note') ? document.querySelector('.doe-ai-note').textContent : ''"
    )
    assert "AI-drafted" in note
    assert "human-verified" in note


def test_hanford_view_scrolls(page, base_url):
    """`main` is `overflow: hidden` app-shell-wide; the view opts back into
    scrolling with its own `overflow-y: auto` (2026-08-24 regression)."""
    _open_doe(page, base_url)
    state = page.evaluate(
        """(() => {
          const view = document.getElementById('view-hanford');
          const style = getComputedStyle(view);
          return {
            overflowY: style.overflowY,
            scrollHeight: view.scrollHeight,
            clientHeight: view.clientHeight,
          };
        })()"""
    )
    assert state["overflowY"] == "auto"
    assert state["scrollHeight"] > state["clientHeight"]


def test_hanford_template_mounts_exactly_once(page, base_url):
    _open_doe(page, base_url)
    page.click("#tab-map")
    page.click("#tab-hanford")
    count = page.evaluate(
        "document.querySelectorAll('#view-hanford .hanford-wrap').length"
    )
    assert count == 1, "template stamped more than once"


def test_precluded_fits_render_out_loud(page, base_url):
    """An honest siting dossier says 'off the table' out loud — precluded
    badges render in the matrix, not just in the data."""
    _open_doe(page, base_url)
    state = page.evaluate(
        """(() => {
          const view = document.getElementById('view-hanford');
          return {
            precluded: view.querySelectorAll('.hp-fit-precluded').length,
            anchored: view.querySelectorAll('.hp-fit-anchored').length,
            offTable: [...view.querySelectorAll('.hanford-best-fit')]
              .filter(td => td.textContent.includes('off the table')).length,
          };
        })()"""
    )
    assert state["precluded"] >= 10
    assert state["anchored"] >= 2
    assert state["offTable"] == 5  # 100/200/Monument/B Reactor/PNNL


def test_hanford_markers_and_legend_present_at_ready(page, base_url):
    _goto_ready(page, base_url)
    state = page.evaluate(
        """(() => ({
          markers: document.querySelectorAll('.hanford-parcel-icon').length,
          legend: !!document.querySelector('.legend-hanford'),
        }))()"""
    )
    assert state["markers"] == 9
    assert state["legend"] is True


def test_hanford_deep_link_activates_tab(page, base_url):
    page.goto(f"{base_url}/index.html#hanford")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)
    page.wait_for_selector("#view-hanford .doe-parcel-card", timeout=15000)
    active = page.evaluate(
        "document.getElementById('view-hanford').classList.contains('active')"
    )
    assert active is True


def test_hanford_screen_shows_nmfs_lens_separately(page, base_url):
    """The dossier's research point: NOAA/NMFS critical habitat is a
    separate consulting-agency lens from USFWS IPaC — Hanford's ten-source
    screen renders both rows with distinct labels."""
    _open_doe(page, base_url)
    _open_drawer(page, "hanford-energy-northwest")
    labels = page.evaluate(
        """(() => Array.from(document.querySelectorAll(
             '#doe-drawer .hanford-screen-table th[scope=row]'))
           .map(th => th.textContent))()"""
    )
    assert "USFWS IPaC" in labels
    assert "NOAA critical habitat" in labels
    assert "Salmon EFH" in labels


def test_hanford_map_button_loads_layers_and_zooms(page, base_url):
    """The canonical fitBounds check (a hidden Browser pane cannot verify
    viewport-dependent zoom — this headless run has a real viewport)."""
    _open_doe(page, base_url)
    _open_drawer(page, "hanford-energy-northwest")
    page.click("#doe-drawer .hanford-map-btn")
    page.wait_for_function(
        "document.getElementById('view-map').classList.contains('active')",
        timeout=15000,
    )
    page.wait_for_function("window.__leafletMap.getZoom() >= 8", timeout=15000)
    center = page.evaluate(
        "(() => { const c = window.__leafletMap.getCenter(); return [c.lat, c.lng]; })()"
    )
    assert 45.5 < center[0] < 47.5
    assert -121.0 < center[1] < -118.0


def test_partial_map_package_renders_warning_not_pure_success(page, base_url):
    """A package with failed layers must say so on the drawer, the button
    title, AND the post-click toast — an omitted layer is coverage, not
    clearance (Codex PR #22 round 2). Shipped data has 0 failed layers, so
    the test injects a partial summary and reopens the drawer."""
    _open_doe(page, base_url)
    page.evaluate(
        """(() => {
          const p = window.__hanford.parcels.find(x => x.id === 'hanford-energy-northwest');
          p.map_summary = { feature_count: 40, layers_ok: 11, layers_partial: 0, layers_failed: 3 };
        })()"""
    )
    _open_drawer(page, "hanford-energy-northwest")
    state = page.evaluate(
        """(() => {
          const d = document.getElementById('doe-drawer');
          const warn = d.querySelector('.hanford-map-warn');
          return {
            warn: warn ? warn.textContent : null,
            btnTitle: d.querySelector('.hanford-map-btn').title,
          };
        })()"""
    )
    assert state["warn"] and "3 of 14" in state["warn"]
    assert "coverage, not clearance" in state["btnTitle"]
    page.click("#doe-drawer .hanford-map-btn")
    page.wait_for_function(
        "document.getElementById('toast') && "
        "document.getElementById('toast').textContent.includes('3 layers unavailable')",
        timeout=15000,
    )
