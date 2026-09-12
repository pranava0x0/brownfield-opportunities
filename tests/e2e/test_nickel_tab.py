"""Browser contracts for category evidence; legacy numeric suitability is retired."""
from __future__ import annotations
import csv
import io
import pytest
from playwright.sync_api import Page, expect
pytestmark = pytest.mark.e2e

def _ready(page, base_url):
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.SiteEvidence && window.__APP_READY__ === true", timeout=45000)

def _assess(page, record, lens="dc"):
    return page.evaluate("([s,l]) => SiteEvidence.assessSite(s,l)", [record,lens])

def _open_tab(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.click("#tab-nickel")
    page.wait_for_selector("#nickel-table tbody tr", timeout=30_000)

def test_tab_mounts_lazily_from_its_template(page: Page, base_url: str) -> None:
    """Template content is excluded from document.querySelectorAll('*'), which
    is how this view stays out of the first-paint node budget. Before the tab
    is clicked the interior must not exist in the live DOM."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    assert page.locator("#nickel-table").count() == 0
    page.click("#tab-nickel")
    expect(page.locator("#nickel-table")).to_be_visible()

def test_lens_toggle_switches_the_ranking_and_the_url(
        page: Page, base_url: str) -> None:
    """`?nlens=` is only encoded off-default, and the two lenses genuinely
    rank different sites — the import lens lists port-served sites, the
    domestic lens rail-served ones."""
    _open_tab(page, base_url)
    assert "nlens=" not in page.url
    first_import = page.locator("#nickel-table tbody tr").first.get_attribute("data-id")

    page.click("[data-nickel-lens='domestic']")
    # syncUrl() writes through a 200ms debounce, so the URL must be WAITED on,
    # never read immediately after the click.
    #
    # It must be waited on with wait_for_function, NOT page.wait_for_url():
    # syncUrl uses history.replaceState, which is a same-document URL change
    # and not a navigation, so wait_for_url sits on a navigation event that
    # never fires ("waiting for navigation ... until 'load'") and times out.
    # It passed locally only because the URL already matched by the time the
    # call was made; on a slower runner it did not, and CI went red.
    page.wait_for_function(
        "location.search.includes('nlens=domestic')", timeout=15_000)
    first_domestic = page.locator("#nickel-table tbody tr").first.get_attribute("data-id")
    assert first_import != first_domestic

    page.click("[data-nickel-lens='import']")
    page.wait_for_function("!location.search.includes('nlens=')", timeout=15_000)

def test_import_lens_lists_only_port_served_sites(page: Page, base_url: str) -> None:
    """The score gate only asks whether the water join has run, which every
    site passes. The ranked list asks the stricter question the tab's own copy
    implies — the Maritime tab had to learn this distinction twice."""
    _open_tab(page, base_url)
    ids = page.eval_on_selector_all(
        "#nickel-table tbody tr", "els => els.slice(0, 40).map(e => e.dataset.id)")
    portless = page.evaluate(
        "(ids) => ids.filter(id => window.__sites.find(s => s.id === id)?.port_mi == null)",
        ids)
    assert portless == [], f"portless sites in the import ranking: {portless}"

def test_the_default_view_only_lists_land_confirmed_above_the_threshold(
        page: Page, base_url: str) -> None:
    """95% of otherwise-eligible sites have no published acreage, they are
    mostly small urban parcels, and because every scored component is a
    distance that is near zero downtown they dominated the ranking outright —
    0 of the top 150 had confirmed land. Defaulting to confirmed land is what
    makes this screen answer the question the tab actually asks.
    """
    _open_tab(page, base_url)
    statuses = page.eval_on_selector_all(
        "#nickel-table tbody tr",
        """els => els.map(e => window.nickelAcreageStatus(
             window.__sites.find(x => x.id === e.dataset.id)))""")
    assert statuses, "no rows"
    assert all(st is True for st in statuses), (
        f"default view leaked non-confirmed land: {set(map(str, statuses))}")
    assert "reported land" in page.locator("#nickel-stats").inner_text()

def test_sites_known_to_be_under_the_land_threshold_are_excluded(
        page: Page, base_url: str) -> None:
    """Land is stated as a threshold, so a site KNOWN to be smaller than it is
    not a candidate. The tie-break alone only reordered equal scores, which
    left under-threshold sites outranking buildable ones whenever the scores
    differed (Codex review). Unknown acreage still qualifies — EPA publishes
    none for its ~36k brownfields, and excluding unknowns would delete most of
    the corpus on a fact we do not have.
    """
    _open_tab(page, base_url)
    bad = page.eval_on_selector_all(
        "#nickel-table tbody tr",
        """els => els.map(e => {
             const s = window.__sites.find(x => x.id === e.dataset.id);
             return {id: e.dataset.id, status: window.nickelAcreageStatus(s)};
           }).filter(r => r.status === false)""")
    assert bad == [], f"under-threshold sites in the ranking: {bad[:5]}"
    # Under the inclusive basis, unknowns must appear but `false` must still
    # not — "we cannot check" and "too small" are different answers.
    page.click("[data-nickel-land='any']")
    page.wait_for_function(
        "document.getElementById('nickel-stats')"
        "?.textContent.includes('or unknown')", timeout=30_000)
    rows = page.eval_on_selector_all(
        "#nickel-table tbody tr",
        """els => els.map(e => window.nickelAcreageStatus(
             window.__sites.find(x => x.id === e.dataset.id)))""")
    assert any(st is None for st in rows), "unknown-acreage sites wrongly excluded"
    assert not any(st is False for st in rows), "under-threshold sites leaked in"

def test_a_failed_data_load_reports_an_error_not_a_false_empty(
        page: Page, base_url: str) -> None:
    """The loaders swallow their own rejections and a 404 becomes an empty
    payload, so the boot fan-out settles either way. Without tracking the
    failure the tab told the user their filters matched nothing, when in fact
    the data it ranks on never arrived (Codex round 2).

    Forced by aborting the request, which is the only way to reach the branch.
    """
    page.route("**/data/water-proximity.json", lambda route: route.abort())
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.click("#tab-nickel")
    stats = page.locator("#nickel-stats")
    stats.wait_for(timeout=30_000)
    page.wait_for_function(
        "document.getElementById('nickel-stats')"
        "?.textContent.includes('Some evidence unavailable')", timeout=30_000)
    txt = stats.inner_text()
    assert "water" in txt, txt
    assert "No sites match" not in txt

def test_the_nickel_tab_retries_a_failed_port_load(
        page: Page, base_url: str) -> None:
    """The import lens ranks on `port_mi`. A failed eager fetch clears its
    promise, so opening the tab has to retry it — otherwise the default
    ranking stays empty until a reload or a visit to Maritime (Codex round 2).
    """
    state = {"failed": False}

    def handler(route):
        if not state["failed"]:
            state["failed"] = True
            route.abort()
        else:
            route.continue_()

    page.route("**/data/port-proximity.json", handler)
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.click("#tab-nickel")
    page.wait_for_function("document.getElementById('nickel-stats').textContent.includes('unavailable')")
    page.click("#tab-candidates")
    page.click("#tab-nickel")
    # The retry fires on tab activation; the ranking must recover without a
    # reload.
    page.wait_for_selector("#nickel-table tbody tr", timeout=60_000)
    assert page.locator("#nickel-table tbody tr").count() > 0

def test_a_port_failure_does_not_blame_the_domestic_lens(
        page: Page, base_url: str) -> None:
    """The domestic lens deliberately has no port term, so a failed port fetch
    leaves it fully rankable. Reporting "could not load port data" there would
    blame missing data for what is a normal result (Codex round 3).
    """
    page.route("**/data/port-proximity.json", lambda route: route.abort())
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("window.__APP_READY__ === true", timeout=60_000)
    page.click("#tab-nickel")
    page.click("[data-nickel-lens='domestic']")
    page.wait_for_selector("#nickel-table tbody tr", timeout=60_000)
    stats = page.locator("#nickel-stats").inner_text()
    assert "Some evidence unavailable" not in stats, stats
    assert page.locator("#nickel-table tbody tr").count() > 0

def test_the_lead_block_does_not_swallow_the_table(page: Page, base_url: str) -> None:
    """A copy edit once ate `.nickel-lead`'s closing </div>, so the lead block
    wrapped the entire table. The browser auto-recovers from unbalanced tags,
    so nothing looked broken — it surfaced only because a UAT measurement
    reported the lead block as 13,164px tall.

    Asserting the table is NOT a descendant of the lead is the cheap
    structural check that would have caught it immediately.
    """
    _open_tab(page, base_url)
    swallowed = page.evaluate(
        """() => {
             const lead = document.querySelector('.nickel-lead');
             const table = document.getElementById('nickel-table');
             return !!(lead && table && lead.contains(table));
           }""")
    assert not swallowed, ".nickel-lead contains the results table — unbalanced markup"
    lead_h = page.evaluate(
        "document.querySelector('.nickel-lead').getBoundingClientRect().height")
    assert lead_h < 1200, f"lead block is {lead_h}px tall — it is wrapping more than copy"

def test_csv_columns_include_water_proximity(page: Page, base_url: str) -> None:
    """Universal CSV export must include the quantitative water proximity columns."""
    page.goto(f"{base_url}/index.html")
    page.wait_for_function("typeof window.__csvColumns !== 'undefined'", timeout=30_000)
    keys = page.evaluate("() => window.__csvColumns.map(c => c.key)")
    for expected in ["water_gage_mi", "water_flow_cfs", "water_gage_name", "water_gage_id"]:
        assert expected in keys, f"{expected} missing from CSV_COLUMNS"

def test_nickel_categories_are_alphabetical_without_hidden_score_order(page,base_url):
    _open_tab(page,base_url)
    names=page.locator('#nickel-table .site-evidence-open').all_inner_texts()
    assert len(names)>10
    assert page.evaluate("names=>names.every((n,i)=>!i || names[i-1].localeCompare(n)<=0)",names)
    assert page.locator('#nickel-table .cand-score').count()==0

def test_unknown_land_remains_explicit_in_inclusive_view(page,base_url):
    _open_tab(page,base_url);page.click('[data-nickel-land="any"]')
    expect(page.locator('#nickel-stats')).to_contain_text('or unknown')
    assert 'Unknown' in page.locator('#nickel-table [data-category="land"] .evidence-finding').all_inner_texts()

def test_recycling_threshold_filters_using_its_own_land_basis(page,base_url):
    _open_tab(page,base_url);page.click('[data-nickel-land="recycling"]')
    expect(page.locator('#nickel-stats')).to_contain_text('100+')
    assert page.evaluate("""()=>Array.from(document.querySelectorAll('#nickel-table tbody tr')).every(r=>nickelAcreageStatus(window.__sites.find(s=>s.id===r.dataset.id),100)===true)""")

def test_pending_port_load_never_claims_no_sites_match(page,base_url):
    def delay(route):
        import time
        time.sleep(0.8)
        route.continue_()
    page.route('**/data/port-proximity.json',delay)
    page.add_init_script("""window.__nickelStates=[];new MutationObserver(()=>{const n=document.getElementById('nickel-stats');if(n)window.__nickelStates.push(n.textContent)}).observe(document,{subtree:true,childList:true,characterData:true});""")
    page.goto(base_url+'/index.html#nickel');page.wait_for_selector('#nickel-table tbody tr',timeout=45000)
    states=page.evaluate('window.__nickelStates')
    assert not any('No sites match' in t for t in states)

def test_nickel_map_overlay_loads_when_map_is_requested(page,base_url):
    _open_tab(page,base_url);page.click('#tab-map');page.wait_for_selector('.nickel-anchor-icon')
    assert page.locator('.nickel-anchor-icon').count()>=10
    assert page.locator('.nickel-anchor-icon').first.evaluate('n=>getComputedStyle(n).fontSize')=='15px'
    expect(page.locator('.legend')).to_contain_text('Nickel supply chain')
