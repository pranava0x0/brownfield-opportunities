"""E2E guards for the Hanford E2E dossier tab (the ninth tab).

What these pin:
  - the tab mounts lazily from <template id="hanford-template"> exactly once
    and renders all nine parcel cards with the full ten-source screen
  - the honesty rails render: the limitations strip, "precluded"
    opportunities, and Unavailable-is-not-no-hit handling
  - the ▣ markers + legend row exist at APP_READY (the dossier loads
    eagerly because its generated_at drives the displayed refresh date)
  - the "Show features on map" button loads the parcel's GeoJSON package,
    switches to the Map tab, and actually zooms in (the hidden-Browser-pane
    session could not verify fitBounds; this headless run has a real
    viewport, so this is the canonical check)
  - #hanford deep-links work
  - the corpus join renders the dashboard's own enrichment values inside a
    parcel card (byproduct reuse, not re-derivation)
"""


def _goto_ready(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=30000)


def _open_hanford(page, base_url):
    _goto_ready(page, base_url)
    page.click("#tab-hanford")
    page.wait_for_selector("#view-hanford details.hanford-parcel", timeout=15000)


def test_hanford_tab_renders_nine_parcels_with_full_screen(page, base_url):
    _open_hanford(page, base_url)
    state = page.evaluate(
        """(() => {
          const view = document.getElementById('view-hanford');
          const cards = view.querySelectorAll('details.hanford-parcel');
          const first = cards[0];
          return {
            cards: cards.length,
            managers: view.querySelectorAll('.hanford-mgr').length,
            pathwayRows: view.querySelectorAll('.hanford-pathway-table tbody tr').length,
            screenRows: first.querySelectorAll('.hanford-screen-table tbody tr').length,
            limitStrip: !!view.querySelector('.janus-limit'),
          };
        })()"""
    )
    assert state["cards"] == 9
    assert state["managers"] == 5
    assert state["pathwayRows"] == 8
    assert state["screenRows"] == 10
    assert state["limitStrip"] is True


def test_hanford_template_mounts_exactly_once(page, base_url):
    """Re-activating the tab must not stamp the template twice (the About/
    Coal/Retired lazy-mount rule)."""
    _open_hanford(page, base_url)
    page.click("#tab-map")
    page.click("#tab-hanford")
    count = page.evaluate(
        "document.querySelectorAll('#view-hanford .hanford-wrap').length"
    )
    assert count == 1, "template stamped more than once"


def test_hanford_precluded_opportunities_render(page, base_url):
    """An honest siting dossier says 'off the table' out loud — the
    precluded badges must actually render, not just live in the data."""
    _open_hanford(page, base_url)
    state = page.evaluate(
        """(() => {
          const view = document.getElementById('view-hanford');
          return {
            precluded: view.querySelectorAll('.hp-fit-precluded').length,
            anchored: view.querySelectorAll('.hp-fit-anchored').length,
            conditional: view.querySelectorAll('.hp-fit-conditional').length,
          };
        })()"""
    )
    assert state["precluded"] >= 2
    assert state["anchored"] >= 4
    assert state["conditional"] >= 3


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
    page.wait_for_selector("#view-hanford details.hanford-parcel", timeout=15000)
    active = page.evaluate(
        "document.getElementById('view-hanford').classList.contains('active')"
    )
    assert active is True


def test_hanford_corpus_join_renders_enrichment_values(page, base_url):
    """The 100-Area card must show the dashboard's own infra-proximity
    values (transmission distance + NPL status) joined onto the parcel."""
    _open_hanford(page, base_url)
    text = page.evaluate(
        """(() => {
          const card = document.getElementById('hp-hanford-100-area');
          card.open = true;
          return card.querySelector('.hanford-corpus') ?
            card.querySelector('.hanford-corpus').textContent : '';
        })()"""
    )
    assert "Transmission" in text
    assert "NPL status" in text
    assert "230" in text  # the 100-Area record's 230 kV join


def test_hanford_map_button_loads_layers_and_zooms(page, base_url):
    """The canonical fitBounds check (a hidden Browser pane cannot verify
    viewport-dependent zoom — this headless run has a real viewport)."""
    _open_hanford(page, base_url)
    page.evaluate(
        """(() => {
          const card = document.getElementById('hp-hanford-energy-northwest');
          card.open = true;
          card.querySelector('.hanford-map-btn').click();
        })()"""
    )
    page.wait_for_function(
        "document.getElementById('view-map').classList.contains('active')",
        timeout=15000,
    )
    page.wait_for_function("window.__leafletMap.getZoom() >= 8", timeout=15000)
    center = page.evaluate(
        "(() => { const c = window.__leafletMap.getCenter(); return [c.lat, c.lng]; })()"
    )
    # Centered on the Hanford area, not the CONUS default.
    assert 45.5 < center[0] < 47.5
    assert -121.0 < center[1] < -118.0


def test_hanford_screen_shows_nmfs_lens_separately(page, base_url):
    """The dossier's research point: NOAA/NMFS critical habitat is a
    separate consulting-agency lens from USFWS IPaC. Both rows must render
    with distinct labels."""
    _open_hanford(page, base_url)
    labels = page.evaluate(
        """(() => {
          const card = document.getElementById('hp-hanford-energy-northwest');
          card.open = true;
          return Array.from(card.querySelectorAll('.hanford-screen-table th[scope=row]'))
            .map(th => th.textContent);
        })()"""
    )
    assert "USFWS IPaC" in labels
    assert "NOAA critical habitat" in labels
    assert "Salmon EFH" in labels


def test_partial_map_package_renders_warning_not_pure_success(page, base_url):
    """A package with failed layers must say so on the card, the button
    title, AND the post-click toast — an omitted layer is coverage, not
    clearance (Codex PR #22 round 2). Shipped data has 0 failed layers, so
    the test injects a partial summary and rebuilds the view."""
    _open_hanford(page, base_url)
    state = page.evaluate(
        """(() => {
          const p = window.__hanford.parcels.find(x => x.id === 'hanford-energy-northwest');
          p.map_summary = { feature_count: 40, layers_ok: 11, layers_partial: 0, layers_failed: 3 };
          window.__setView('map');
          window.__setView('hanford');  // re-activation rebuilds the view
          const card = document.getElementById('hp-hanford-energy-northwest');
          card.open = true;
          const warn = card.querySelector('.hanford-map-warn');
          return {
            warn: warn ? warn.textContent : null,
            btnTitle: card.querySelector('.hanford-map-btn').title,
          };
        })()"""
    )
    assert state["warn"] and "3 of 14" in state["warn"]
    assert "coverage, not clearance" in state["btnTitle"]
    page.evaluate(
        """(() => {
          document.getElementById('hp-hanford-energy-northwest')
            .querySelector('.hanford-map-btn').click();
        })()"""
    )
    page.wait_for_function(
        "document.getElementById('toast') && "
        "document.getElementById('toast').textContent.includes('3 layers unavailable')",
        timeout=15000,
    )
