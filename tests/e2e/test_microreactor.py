"""End-to-end tests for the microreactor siting lens and the Microreactors tab.

The lens lives in `docs/microreactor-score.js` and exposes on `window`:
  computeMicroreactorScore / computeMicroreactorBreakdown
  microreactorScorable / microreactorIsOffGrid / microreactorGridAccessMi
  microreactorMeetsAcreageThreshold
  MICRO_WEIGHTS / MICRO_MIN_ACRES / MICRO_FLOOD_SFHA_PENALTY / MICRO_SCORE_TOOLTIP

It is the one lens in this app that INVERTS the grid signal — distance from
transmission scores higher — so several of these tests exist specifically to
pin behaviour that looks backwards next to test_dc_score.py and would
otherwise read as a bug and get "fixed".

Three tests here are regressions against defects the real data exposed during
the build, each called out in its own docstring: manufactured isolation from
HIFLD's sub-transmission gap, solar farms counting as an anchor load, and
deliverability behaving as a proxy for "urban".
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


# -- Helpers ----------------------------------------------------------------

def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function(
        "typeof window.computeMicroreactorScore === 'function'", timeout=10_000
    )


def _score(page: Page, record: dict):
    return page.evaluate("(r) => window.computeMicroreactorScore(r)", record)


def _bd(page: Page, record: dict):
    return page.evaluate("(r) => window.computeMicroreactorBreakdown(r)", record)


def _base(**over) -> dict:
    """A minimal scorable record: the `_infraChecked` marker is what tells the
    lens the enrichment join has run, so every synthetic record needs it."""
    rec = {"id": "T-1", "program": "brownfield", "_infraChecked": True}
    rec.update(over)
    return rec


# -- Weight table -----------------------------------------------------------

def test_micro_weights_sum_to_100(page: Page, base_url: str):
    _ready(page, base_url)
    w = page.evaluate("() => window.MICRO_WEIGHTS")
    assert sum(w.values()) == 100, w
    assert set(w) == {
        "licensing_path", "grid_isolation", "anchor_load",
        "deliverability", "readiness",
    }


def test_breakdown_keys_match_the_weight_table(page: Page, base_url: str):
    """A key that drifts renders a silent 0 chip instead of erroring — the
    same failure mode documented for _DC_SUIT_GROUPS."""
    _ready(page, base_url)
    w = page.evaluate("() => window.MICRO_WEIGHTS")
    bd = _bd(page, _base(transmission_mi=1.0))
    assert set(bd) == set(w)
    groups = page.evaluate("() => window._MICRO_SUIT_GROUPS")
    grouped = {k for g in groups for k in g["keys"]}
    assert grouped == set(w), "a component is missing from the chip groups"


def test_no_component_can_exceed_its_cap(page: Page, base_url: str):
    _ready(page, base_url)
    w = page.evaluate("() => window.MICRO_WEIGHTS")
    maxed = _base(
        program="brac", transmission_mi=None, substation_mi=None,
        highway_mi=0.1, rail_mi=0.1,
        power_plant_mi=0.5, power_plant_mw=8, power_plant_fuel="petroleum",
        npl_status_code="D", in_energy_community=True, in_reuse="Yes",
        current_owner="US Army", in_opportunity_zone=True,
    )
    bd = _bd(page, maxed)
    for k, cap in w.items():
        assert 0 <= bd[k] <= cap, f"{k}={bd[k]} exceeds cap {cap}"
    assert _score(page, maxed) <= 100


# -- The gate ---------------------------------------------------------------

def test_unscorable_until_the_infra_join_has_run(page: Page, base_url: str):
    """A null transmission distance means "off-grid" only AFTER the join has
    landed. Before it, every site in the corpus would look off-grid and score
    a perfect isolation term for the second or two until the lazy fetch
    resolves."""
    _ready(page, base_url)
    unchecked = {"id": "T-1", "program": "fuds"}
    assert page.evaluate("(r) => window.microreactorScorable(r)", unchecked) is False
    assert _score(page, unchecked) is None
    assert _bd(page, unchecked) is None


def test_a_site_carrying_a_distance_needs_no_marker(page: Page, base_url: str):
    """The value itself is the evidence that the join ran."""
    _ready(page, base_url)
    rec = {"id": "T-1", "program": "fuds", "transmission_mi": 3.0}
    assert page.evaluate("(r) => window.microreactorScorable(r)", rec) is True
    assert _score(page, rec) is not None


# -- Grid isolation: the inversion ------------------------------------------

@pytest.mark.parametrize("mi,expect_at_least", [(0.25, 0), (3, 6), (10, 14), (25, 20), (50, 22)])
def test_isolation_rises_with_distance(page: Page, base_url: str, mi, expect_at_least):
    """Backwards on purpose: this is the only lens in the app where far is
    better. Do not 'fix' it to match dc-score.js."""
    _ready(page, base_url)
    bd = _bd(page, _base(transmission_mi=mi, substation_mi=mi))
    assert bd["grid_isolation"] >= expect_at_least, (mi, bd)


def test_isolation_is_monotonic_in_distance(page: Page, base_url: str):
    _ready(page, base_url)
    vals = [
        _bd(page, _base(transmission_mi=d, substation_mi=d))["grid_isolation"]
        for d in (0.1, 1, 3, 10, 25, 60)
    ]
    assert vals == sorted(vals), vals


def test_a_near_substation_defeats_a_distant_line(page: Page, base_url: str):
    """REGRESSION. HIFLD's public feed is patchy on sub-transmission, so 13.5%
    of the corpus reports a substation closer than its "nearest" line. A
    60/40 blend of the two distances credited eight FUDS properties around
    Sault Ste Marie, Michigan with 41–44 miles of isolation while they sat a
    mile from a substation — and they took over the top of the ranking.

    A substation cannot exist without being connected, so grid access is the
    MINIMUM of the two, never a blend."""
    _ready(page, base_url)
    sault = _base(transmission_mi=44.2, substation_mi=1.0)
    truly_remote = _base(transmission_mi=44.2, substation_mi=44.0)
    assert page.evaluate("(r) => window.microreactorGridAccessMi(r)", sault) == 1.0
    assert _bd(page, sault)["grid_isolation"] < _bd(page, truly_remote)["grid_isolation"]
    # And it must score no better than a site whose line is genuinely 1 mi off.
    assert (_bd(page, sault)["grid_isolation"]
            == _bd(page, _base(transmission_mi=1.0, substation_mi=1.0))["grid_isolation"])


def test_off_grid_requires_both_to_be_absent(page: Page, base_url: str):
    _ready(page, base_url)
    both_null = _base(transmission_mi=None, substation_mi=None)
    line_only_null = _base(transmission_mi=None, substation_mi=2.0)
    assert page.evaluate("(r) => window.microreactorIsOffGrid(r)", both_null) is True
    assert page.evaluate("(r) => window.microreactorIsOffGrid(r)", line_only_null) is False
    w = page.evaluate("() => window.MICRO_WEIGHTS")
    assert _bd(page, both_null)["grid_isolation"] == w["grid_isolation"]


def test_off_grid_is_false_before_the_join_runs(page: Page, base_url: str):
    _ready(page, base_url)
    assert page.evaluate(
        "(r) => window.microreactorIsOffGrid(r)", {"id": "T-1", "program": "fuds"}
    ) is False


# -- Anchor load ------------------------------------------------------------

def test_solar_is_not_an_anchor_load(page: Page, base_url: str):
    """REGRESSION. Solar is the nearest plant for 14,722 of 46,759 sites — the
    single most common answer in the corpus — because solar farms are sited on
    cheap rural land precisely BECAUSE nothing is there. Treating that as
    evidence of a local load handed a third of the corpus a signal that does
    not exist, and put a Massachusetts air base with a 3.5 MW solar farm
    beside it at the top of the ranking."""
    _ready(page, base_url)
    common = dict(power_plant_mi=2.5, power_plant_mw=8)
    solar = _bd(page, _base(transmission_mi=5, power_plant_fuel="solar", **common))
    diesel = _bd(page, _base(transmission_mi=5, power_plant_fuel="petroleum", **common))
    assert solar["anchor_load"] < diesel["anchor_load"]
    # Fuel gates the evidence, so a non-dispatchable neighbour collapses to
    # exactly the same floor as having found no plant at all — never worse,
    # never better.
    none_found = _bd(page, _base(transmission_mi=5, power_plant_mi=None))
    assert solar["anchor_load"] == none_found["anchor_load"]
    for fuel in ("wind", "batteries", "pumped storage"):
        v = _bd(page, _base(transmission_mi=5, power_plant_fuel=fuel, **common))
        assert v["anchor_load"] == none_found["anchor_load"], fuel


@pytest.mark.parametrize("fuel,rank", [
    ("petroleum", 5), ("coal", 4), ("natural gas", 3), ("biomass", 2), ("nuclear", 1),
])
def test_displaced_fuel_orders_the_anchor(page: Page, base_url: str, fuel, rank):
    _ready(page, base_url)
    v = _bd(page, _base(transmission_mi=5, power_plant_mi=2,
                        power_plant_mw=10, power_plant_fuel=fuel))["anchor_load"]
    ref = _bd(page, _base(transmission_mi=5, power_plant_mi=2,
                          power_plant_mw=10, power_plant_fuel="nuclear"))["anchor_load"]
    assert v >= ref, (fuel, v, ref)


def test_a_utility_scale_plant_is_a_weaker_anchor_than_a_genset(page: Page, base_url: str):
    """A 2 GW combined-cycle plant next door means the grid is strong and a
    1 MWe unit adds nothing; an 8 MW petroleum plant is a like-for-like
    replacement."""
    _ready(page, base_url)
    small = _bd(page, _base(transmission_mi=8, power_plant_mi=2,
                            power_plant_mw=8, power_plant_fuel="petroleum"))
    huge = _bd(page, _base(transmission_mi=8, power_plant_mi=2,
                           power_plant_mw=2000, power_plant_fuel="petroleum"))
    assert small["anchor_load"] > huge["anchor_load"]


def test_no_plant_located_scores_a_floor_not_a_zero(page: Page, base_url: str):
    """Empty tundra is the failure mode at the top of an isolation-weighted
    ranking, so the floor is deliberately low — but a load may exist that we
    simply cannot see, so it is not zero."""
    _ready(page, base_url)
    bd = _bd(page, _base(transmission_mi=None, substation_mi=None, power_plant_mi=None))
    w = page.evaluate("() => window.MICRO_WEIGHTS")
    assert 0 < bd["anchor_load"] < w["anchor_load"] * 0.3


# -- Deliverability ---------------------------------------------------------

def test_deliverability_is_flat_within_reach(page: Page, base_url: str):
    """REGRESSION. A steep proximity curve made this a proxy for 'urban' and
    cancelled the isolation premium the whole lens exists to express. A site
    0.4 mi from an Interstate and one 12 mi from it are equally deliverable —
    a low-boy trailer covers the last twelve miles."""
    _ready(page, base_url)
    near = _bd(page, _base(transmission_mi=5, highway_mi=0.4, rail_mi=0.4))
    mid = _bd(page, _base(transmission_mi=5, highway_mi=12, rail_mi=12))
    assert near["deliverability"] == mid["deliverability"]


def test_deliverability_collapses_where_access_genuinely_fails(page: Page, base_url: str):
    """The deliberate brake on the isolation premium: you cannot truck a
    70-tonne reactor to a place with no primary road."""
    _ready(page, base_url)
    reachable = _bd(page, _base(transmission_mi=5, highway_mi=10, rail_mi=10))
    far = _bd(page, _base(transmission_mi=5, highway_mi=70, rail_mi=70))
    none = _bd(page, _base(transmission_mi=5, highway_mi=None, rail_mi=None))
    assert reachable["deliverability"] > far["deliverability"] > none["deliverability"]
    assert none["deliverability"] == 0


# -- Licensing path ---------------------------------------------------------

def test_federal_land_outranks_private_brownfield(page: Page, base_url: str):
    """Every U.S. microreactor to reach criticality did so under a DOE
    authorization on federal land, not an NRC operating licence."""
    _ready(page, base_url)
    def lic(program, **over):
        return _bd(page, _base(program=program, transmission_mi=5, **over))["licensing_path"]
    brac = lic("brac")
    fed_superfund = lic("superfund", federal_facility_code="Y")
    fuds = lic("fuds")
    superfund = lic("superfund", federal_facility_code="N")
    brownfield = lic("brownfield")
    assert brac >= fed_superfund > fuds > superfund > brownfield
    assert brownfield > 0, "the NRC path is slower, not impossible"


# -- Subtractive terms ------------------------------------------------------

def test_sfha_flood_subtracts_but_less_than_the_dc_lens(page: Page, base_url: str):
    """A 2–20 acre reactor pad can be sited out of the mapped floodplain
    inside a larger parcel; a 200-acre campus cannot."""
    _ready(page, base_url)
    dry = _base(transmission_mi=5, in_sfha=False)
    wet = _base(transmission_mi=5, in_sfha=True)
    penalty = page.evaluate("() => window.MICRO_FLOOD_SFHA_PENALTY")
    assert _score(page, dry) - _score(page, wet) == penalty
    assert penalty < page.evaluate("() => window.FLOOD_SFHA_PENALTY")


def test_unmapped_flood_is_not_penalised(page: Page, base_url: str):
    """Absence of evidence is not evidence of safety — but it is also not
    evidence of danger, and null must not be charged."""
    _ready(page, base_url)
    assert _score(page, _base(transmission_mi=5, in_sfha=None)) == \
           _score(page, _base(transmission_mi=5, in_sfha=False))


@pytest.mark.parametrize("rating,expected", [
    ("Very High", 8), ("Relatively High", 4), ("Relatively Low", 0),
    ("Very Low", 0), (None, 0), ("Insufficient Data", 0),
])
def test_wildfire_penalty(page: Page, base_url: str, rating, expected):
    _ready(page, base_url)
    clean = _score(page, _base(transmission_mi=5))
    got = _score(page, _base(transmission_mi=5, nri_wildfire_rating=rating))
    assert clean - got == expected, rating


def test_drought_is_not_penalised_unlike_the_dc_lens(page: Page, base_url: str):
    """Heat-pipe (eVinci, Antares R1) and helium HTGR (Kaleidos, KRONOS)
    designs are air-coolable, so cooling-water scarcity is not the binding
    constraint it is for a wet-cooled thermal plant."""
    _ready(page, base_url)
    assert _score(page, _base(transmission_mi=5, nri_drought_rating="Very High")) == \
           _score(page, _base(transmission_mi=5))


# -- Land threshold ---------------------------------------------------------

def test_acreage_threshold_is_tri_state(page: Page, base_url: str):
    """null means UNKNOWN, not too small. Every ACRES brownfield and two
    thirds of FUDS ship no acreage; a null-means-fail rule would silently
    delete most of the corpus from this lens."""
    _ready(page, base_url)
    thr = lambda r: page.evaluate("(r) => window.microreactorMeetsAcreageThreshold(r)", r)
    minimum = page.evaluate("() => window.MICRO_MIN_ACRES")
    assert thr(_base(acreage=minimum + 1)) is True
    assert thr(_base(acreage=minimum - 1)) is False
    assert thr(_base()) is None
    # The cadastral parcel is a conservative floor that only ever fills a null.
    assert thr(_base(parcel_acreage=minimum + 1)) is True
    assert thr(_base(acreage=1, parcel_acreage=9_999)) is False


def test_land_is_a_screen_not_a_ranked_factor(page: Page, base_url: str):
    """Westinghouse publishes 5 MWe on two acres, so a 40,000-acre range has
    no scoring advantage over a 12-acre parcel."""
    _ready(page, base_url)
    assert _score(page, _base(transmission_mi=5, acreage=12)) == \
           _score(page, _base(transmission_mi=5, acreage=40_000))


# -- The tab ----------------------------------------------------------------

def _open_tab(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    page.click("#tab-micro")
    page.wait_for_selector(".micro-rank-table tbody tr", timeout=30_000)


def test_tab_renders_fleet_commitments_and_ranking(page: Page, base_url: str):
    _open_tab(page, base_url)
    page.wait_for_selector(".janus-table tbody tr", timeout=15_000)
    tables = page.locator("#micro-content table.micro-table")
    assert tables.count() == 4
    assert tables.nth(0).locator("tbody tr").count() >= 11        # the fleet
    assert tables.nth(1).locator("tbody tr").count() >= 30        # commitments + track headers
    assert page.locator(".micro-rank-table tbody tr").count() > 0  # the siting screen
    # Every fleet and commitment row must expose at least one source link.
    assert page.locator("#micro-content .micro-src a").count() >= 40


def test_janus_screen_has_nine_traceable_installations(page: Page, base_url: str):
    _open_tab(page, base_url)
    page.wait_for_selector(".janus-table tbody tr", timeout=15_000)
    assert page.locator(".janus-table tbody tr").count() == 9
    page.locator("button.janus-site-button").first.click()
    page.wait_for_selector("#janus-detail")
    assert page.locator(".janus-source-card").count() == 6
    assert page.locator(".janus-source-card a").count() >= 6
    detail = page.locator("#janus-detail").inner_text()
    assert "Screening, not siting" in detail
    assert "Unavailable is not no-hit" in detail


def test_janus_deep_link_and_lazy_map_package(page: Page, base_url: str):
    _ready(page, base_url)
    page.goto(f"{base_url}/index.html?janus=fort-benning-ga#micro")
    page.wait_for_selector("#janus-detail", timeout=20_000)
    assert "Fort Benning" in page.locator("#janus-detail").inner_text()
    page.click("button.janus-map-button")
    page.wait_for_selector("#view-map:not([hidden])", timeout=20_000)
    page.wait_for_function("() => window.__janusMapFeatureCount() > 0", timeout=20_000)
    assert page.evaluate("() => window.__janusMapFeatureCount()") > 1_000


def test_tab_is_a_bookmarkable_hash_route(page: Page, base_url: str):
    _ready(page, base_url)
    page.goto(f"{base_url}/index.html#micro")
    page.wait_for_selector("#view-micro:not([hidden])", timeout=15_000)
    assert page.locator("#tab-micro").get_attribute("aria-selected") == "true"


def test_ranking_rows_are_sorted_by_score_descending(page: Page, base_url: str):
    _open_tab(page, base_url)
    scores = page.locator(".micro-rank-table tbody .suit-score").all_inner_texts()
    vals = [int(s) for s in scores]
    assert vals == sorted(vals, reverse=True), vals[:12]


def test_hard_islanded_toggle_filters_to_off_grid_sites(page: Page, base_url: str):
    _open_tab(page, base_url)
    before = page.locator(".micro-rank-table tbody tr").count()
    page.click("#micro-offgrid-toggle")
    page.wait_for_selector("#micro-offgrid-toggle.active", timeout=5_000)
    cells = page.locator(".micro-rank-table tbody tr td:nth-child(5)").all_inner_texts()
    assert cells, "the off-grid set is empty — the filter or the data broke"
    assert all("Off-grid" in c for c in cells)
    page.click("#micro-offgrid-toggle")
    page.wait_for_selector("#micro-offgrid-toggle:not(.active)", timeout=5_000)
    assert page.locator(".micro-rank-table tbody tr").count() == before


def test_ranking_reports_the_same_grid_distance_the_score_used(page: Page, base_url: str):
    """The table column and the score must read the same number, or a site
    credited with 1 mi of grid access displays 44 mi of isolation."""
    _open_tab(page, base_url)
    mismatches = page.evaluate("""() => {
      const bad = [];
      document.querySelectorAll(".micro-rank-table tbody tr").forEach(tr => {
        const s = window.__sites.find(x => x.id === tr.dataset.id);
        if (!s) { bad.push([tr.dataset.id, "site not found"]); return; }
        const shown = tr.cells[4].textContent.trim();
        const eff = window.microreactorGridAccessMi(s);
        const want = eff == null ? "Off-grid" : window.__fmtMiles(eff);
        if (shown !== want) bad.push([s.id, shown, want]);
      });
      return bad;
    }""")
    assert mismatches == []


def test_commitment_markers_and_legend_row(page: Page, base_url: str):
    _open_tab(page, base_url)
    page.click("#tab-map")
    page.wait_for_selector(".micro-commit-icon", timeout=15_000)
    count = page.locator(".micro-commit-icon").count()
    assert count >= 20, count
    legend = page.locator(".legend").inner_text()
    assert "Microreactor commitment" in legend
    assert str(count) in legend


def test_alaska_commitments_are_remapped_into_the_inset(page: Page, base_url: str):
    """Eielson AFB and the Fort Wainwright Janus installation are two of the
    highest-value rows in the set, and their real coordinates sit outside
    US_BOUNDS — a raw marker would be unreachable behind maxBoundsViscosity."""
    _open_tab(page, base_url)
    page.click("#tab-map")
    page.wait_for_selector(".micro-commit-icon", timeout=15_000)
    ak = page.evaluate("""() => (window.__microFleet().commitments || [])
        .filter(c => c.state === "AK" && c.lat_real != null)
        .map(c => ({ id: c.id, inset: c._inset, lat: c.lat, latReal: c.lat_real }))""")
    assert len(ak) == 2, ak
    for row in ak:
        assert row["inset"] == "AK", row
        assert row["latReal"] > 60, row          # the real Alaskan latitude survives
        assert 18 < row["lat"] < 30, row         # remapped into the inset box
    # And nothing renders outside the map's own box.
    offscreen = page.evaluate("""() => {
      const h = document.getElementById("map").clientHeight;
      let n = 0;
      document.querySelectorAll(".micro-commit-icon").forEach(el => {
        const m = el.style.transform.match(/translate3d\\(([-\\d.]+)px,\\s*([-\\d.]+)px/);
        if (m && (+m[2] < 0 || +m[2] > h)) n++;
      });
      return n;
    }""")
    assert offscreen == 0, f"{offscreen} commitment markers render outside the map"


def test_csv_export_covers_the_full_ranking_with_the_breakdown(page: Page, base_url: str):
    _open_tab(page, base_url)
    csv = page.evaluate("() => window.__buildMicroCsv()")
    lines = csv.split("\n")
    header = lines[0].split(",")
    for col in ("microreactor_score", "grid_access_mi", "off_grid",
                "score_grid_isolation", "score_licensing_path"):
        assert col in header, col
    assert len(lines) > 1_000, "the CSV should export the full ranking, not the visible page"
    assert len(lines[1].split(",")) == len(header)


def test_global_filters_carry_onto_the_siting_screen(page: Page, base_url: str):
    """Sources from tableState.filtered, the same set the map and table show —
    the unification the Rankings tab got in v1.21."""
    _open_tab(page, base_url)
    before = page.evaluate("() => window.__microRankedCount()")
    page.evaluate(
        "(st) => { const sel = document.getElementById('f-state');"
        " sel.value = st; sel.dispatchEvent(new Event('change')); }",
        "AK",
    )
    page.wait_for_function(
        "(n) => window.__microRankedCount() !== n", arg=before, timeout=15_000
    )
    after = page.evaluate("() => window.__microRankedCount()")
    assert after < before
    states = page.locator(".micro-rank-table tbody tr .micro-sub").all_inner_texts()
    assert states and all(s.strip().endswith("AK") for s in states), states[:5]


def test_fleet_load_failure_offers_a_retry_that_recovers(page: Page, base_url: str):
    """A failed fetch must NOT render "0 designs" — that would be a false
    negative about the industry rather than about the network, the same trap
    the civilian-nuclear overlay documents. It must say so and offer a retry,
    and the retry has to actually recover rather than re-render the error.

    The failure has to be made PERSISTENT to reach the error state at all: the
    fleet loads once eagerly at boot (for the map markers) and again on tab
    activation, and the boot attempt nulls its own promise on failure, so a
    single transient failure silently self-heals the moment the tab opens.
    That is good behaviour, and it is exactly why an intermittent 500 is the
    wrong thing to assert on here.
    """
    state = {"fail": True, "attempts": 0}

    def handler(route):
        state["attempts"] += 1
        if state["fail"]:
            route.fulfill(status=500, body="")
        else:
            route.continue_()

    page.route("**/data/microreactor-fleet.json", handler)
    _ready(page, base_url)
    page.click("#tab-micro")
    page.wait_for_selector("#micro-retry", timeout=20_000)
    text = page.locator("#micro-content").inner_text()
    assert "could not be loaded" in text
    assert "0 designs" not in text and "0 commitments" not in text
    assert page.locator(".micro-rank-table").count() == 0

    # Let the network recover, then confirm the button is wired to a real
    # refetch and not just a re-render of the same error.
    before = state["attempts"]
    state["fail"] = False
    page.click("#micro-retry")
    page.wait_for_selector(".micro-rank-table tbody tr", timeout=30_000)
    assert state["attempts"] > before, "the retry never re-fetched"
    page.wait_for_selector(".janus-table", timeout=15_000)
    assert page.locator("#micro-content table.micro-table").count() == 4
