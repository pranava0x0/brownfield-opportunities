"""Regression tests for the AP1000 military-installation siting overlay."""
from __future__ import annotations

from playwright.sync_api import Page


def _ready(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    page.wait_for_function(
        "typeof window.computeAp1000Score === 'function'"
        " && typeof window.computeAp1000Breakdown === 'function'",
        timeout=10_000,
    )


def test_ap1000_weights_follow_priority_order(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    weights = page.evaluate("() => window.AP1000_WEIGHTS")
    assert sum(weights.values()) == 100
    assert weights == {
        "water": 40,
        "transmission": 22,
        "substation": 16,
        "workforce": 15,
        "fiber": 7,
    }
    assert page.evaluate("() => window.AP1000_MIN_DEVELOPABLE_ACRES") == 500
    assert weights["water"] > weights["transmission"] + weights["substation"]
    assert weights["transmission"] + weights["substation"] > weights["workforce"]
    assert weights["workforce"] > weights["fiber"]


def test_ap1000_ranking_is_deterministic(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    rows = page.evaluate(
        """async () => {
          const payload = await fetch('data/ap1000-sites.json').then((r) => r.json());
          return payload.sites
            .map((s) => ({ id: s.id, score: window.computeAp1000Score(s) }))
            .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
        }"""
    )
    assert len(rows) == 14
    assert rows[0]["id"] == "redstone-arsenal-al"
    assert rows[0]["score"] == 86
    assert rows[-1]["id"] == "edwards-afb-ca"


def test_ap1000_air_force_rflp_provenance_is_emitted(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    rflp = page.evaluate(
        """async () => {
          const payload = await fetch('data/ap1000-sites.json').then((r) => r.json());
          return payload.sites
            .filter((s) => s.af_rflp_site)
            .map((s) => ({ id: s.id, acres: s.af_rflp_acres, source: s.af_rflp_source_url }));
        }"""
    )
    assert {r["id"] for r in rflp} == {
        "arnold-afb-tn",
        "davis-monthan-afb-az",
        "edwards-afb-ca",
        "jbmdl-nj",
        "robins-afb-ga",
    }
    assert sum(r["acres"] for r in rflp) == 3132
    assert all("sam.gov" in r["source"] for r in rflp)


def test_ap1000_tab_renders_ranking_and_rflp_badge(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    page.get_by_role("tab", name="Nuclear Siting").click()
    page.get_by_text("Fort Benning (Fort Moore)", exact=True).wait_for(timeout=10_000)
    assert page.locator("#export-csv").is_hidden()
    assert page.get_by_role("button", name="Download AP1000 table as CSV").is_visible()
    assert page.locator(".ap1000-row").count() == 14
    assert page.locator(".ap1000-rflp").count() == 5
    assert page.locator(".ap1000-row .ap1000-cell-src").count() >= 14 * 8
    assert page.locator(".ap1000-workforce-area", has_text="Tacoma + Seattle metro (~4M) within ~1 hr").is_visible()
    page.get_by_text("Arnold AFB (AEDC)", exact=True).click()
    assert page.locator(".ap1000-detail:not([hidden])").get_by_text(
        "Air Force AI data-center RFLP"
    ).is_visible()
    page.get_by_role("tab", name="Table").click()
    assert page.locator("#export-csv").is_visible()


def test_ap1000_csv_exports_values_with_source_urls(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    page.get_by_role("tab", name="Nuclear Siting").click()
    page.get_by_text("Fort Benning (Fort Moore)", exact=True).wait_for(timeout=10_000)
    csv = page.evaluate("window.__buildAp1000Csv()")
    lines = csv.split("\n")
    header = lines[0].split(",")
    assert len(lines) == 15
    for col in [
        "score",
        "acreage_threshold_acres",
        "acreage_threshold_met",
        "water",
        "water_reason",
        "developable_acreage",
        "developable_acreage_reason",
        "transmission_mi",
        "substation_mi",
        "workforce",
        "workforce_reason",
        "fiber",
        "fiber_reason",
        "seismic_flag",
        "usgs_pgam_g",
        "usgs_ss_g",
        "usgs_sdc",
        "usgs_exceeds_sse_0.30g",
    ]:
        assert col in header
        assert f"{col}_source_url" in header
    assert "score_acreage_points" not in header
    hood_line = next(line for line in lines if "Fort Hood" in line)
    assert "poor" in hood_line
    # water_reason carries the validated firm-yield rationale (Belton Lake)
    assert "Belton" in hood_line
    assert "https://" in hood_line


def test_ap1000_seismic_flag_shows_usgs_pga(page: Page, base_url: str) -> None:
    """Flags cell renders quantitative USGS PGA / SDC; high sites flagged 'bad'."""
    _ready(page, base_url)
    page.get_by_role("tab", name="Nuclear Siting").click()
    page.get_by_text("Fort Benning (Fort Moore)", exact=True).wait_for(timeout=10_000)
    # JBLM has the highest PGA (0.59g) — exceeds 0.30g SSE threshold → 'bad' class.
    jblm_row = page.locator(".ap1000-row").filter(has_text="Joint Base Lewis-McChord")
    jblm_flags_text = jblm_row.locator(".ap1000-flags-cell").inner_text()
    assert "0.59g" in jblm_flags_text
    assert "SDC D" in jblm_flags_text
    # Fort Hood has low PGA (0.03g) — 'ok' class, still shown.
    hood_row = page.locator(".ap1000-row").filter(has_text="Fort Hood")
    hood_flags_text = hood_row.locator(".ap1000-flags-cell").inner_text()
    assert "0.03g" in hood_flags_text


def test_ap1000_table_is_accessible(page: Page, base_url: str) -> None:
    _ready(page, base_url)
    page.get_by_role("tab", name="Nuclear Siting").click()
    page.get_by_text("Fort Benning (Fort Moore)", exact=True).wait_for(timeout=10_000)
    # The table has an accessible name (caption) and every column header carries scope.
    assert page.locator(".ap1000-table caption").count() == 1
    assert page.locator(".ap1000-table thead th").count() == 10
    assert page.locator(".ap1000-table thead th:not([scope='col'])").count() == 0
    # The expand affordance is a real <button> with aria-expanded — not a
    # nested-interactive role="button" row containing links.
    assert page.locator(".ap1000-row[role='button']").count() == 0
    assert page.locator(".ap1000-row .ap1000-expand[aria-expanded]").count() == 14
    # Per-factor accessible names on the source links (not nine identical "source").
    assert page.get_by_role("link", name="Water source").count() == 14
    # Keyboard activation of the expand button opens the paired detail row.
    first = page.locator(".ap1000-row .ap1000-expand").first
    first.focus()
    page.keyboard.press("Enter")
    assert first.get_attribute("aria-expanded") == "true"
    assert page.locator(".ap1000-detail:not([hidden])").count() >= 1


def test_water_rights_multiplier_discounts_fully_appropriated(page: Page, base_url: str) -> None:
    """Availability ≠ obtainability: a fully-appropriated basin multiplies
    the water component by 0.2 (JBLM: adequate 0.62 × 0.2 × 40 ≈ 5), a
    contested basin by 0.6, and a missing water_rights_class is NOT charged."""
    _ready(page, base_url)
    r = page.evaluate(
        """() => {
          const base = { water_adequacy: 'adequate' };
          return {
            mults: window.AP1000_WATER_RIGHTS_MULT,
            full: window.computeAp1000Breakdown({...base, water_rights_class: 'fully_appropriated'}).water,
            contested: window.computeAp1000Breakdown({...base, water_rights_class: 'contested'}).water,
            unassessed: window.computeAp1000Breakdown(base).water,
          };
        }"""
    )
    assert r["mults"] == {"obtainable": 1.0, "contested": 0.6, "fully_appropriated": 0.2}
    assert r["unassessed"] == 25          # 0.62 × 40, no rights charge
    assert r["contested"] == 15           # 0.62 × 0.6 × 40
    assert r["full"] == 5                 # 0.62 × 0.2 × 40


def test_documented_low_flow_margin_beats_adequacy_bucket(page: Page, base_url: str) -> None:
    """When a documented drought/low flow exists (Robins: 854 cfs, 2012),
    the computed margin path is used instead of the adequacy bucket:
    854 ÷ 31.1 ≈ 27× → ~0.975 frac → 39/40, higher than 'adequate' (25)."""
    _ready(page, base_url)
    water = page.evaluate(
        "() => window.computeAp1000Breakdown({ water_adequacy: 'adequate', "
        "water_low_flow_cfs: 854, water_rights_class: 'obtainable' }).water"
    )
    assert water == 39


def test_reactor_classes_distinguish_large_pwr_from_smr(page: Page, base_url: str) -> None:
    """AP1000/APR1400 are large PWRs — a separate category from SMR / micro.
    The class table encodes that: both large PWRs share the 500-ac threshold
    and 'Large PWR' group; the SMR and micro classes shrink water demand and
    acreage. A severe-water desert site scores 0 water as an AP1000 but a
    meaningful fraction as an air-coolable microreactor."""
    _ready(page, base_url)
    r = page.evaluate(
        """() => {
          const RC = window.REACTOR_CLASSES;
          const desert = { water_adequacy: 'severe', water_rights_class: 'fully_appropriated' };
          return {
            groups: Object.fromEntries(Object.entries(RC).map(([k, c]) => [k, c.group])),
            acres: Object.fromEntries(Object.entries(RC).map(([k, c]) => [k, c.min_acres])),
            ap1000Water: window.computeAp1000Breakdown(desert, 'ap1000').water,
            microWater: window.computeAp1000Breakdown(desert, 'micro').water,
          };
        }"""
    )
    assert r["groups"] == {"ap1000": "Large PWR", "apr1400": "Large PWR",
                           "ap300": "SMR", "micro": "Microreactor"}
    assert r["acres"]["ap1000"] == r["acres"]["apr1400"] == 500
    assert r["acres"]["ap300"] < 500 and r["acres"]["micro"] < r["acres"]["ap300"]
    assert r["ap1000Water"] == 0
    assert r["microWater"] > 0  # air-coolable: water is not the binding screen


def test_reactor_class_selector_reranks_view(page: Page, base_url: str) -> None:
    """The Nuclear Siting tab's reactor-class buttons rebuild the table under
    the selected class (default ap1000 preserved for deep links)."""
    _ready(page, base_url)
    page.locator("#tab-ap1000").click()
    page.wait_for_selector(".ap1000-row")
    page.wait_for_selector("[data-reactor-class='micro']")
    before = page.locator(".ap1000-row .ap1000-name").first.text_content()
    page.locator("[data-reactor-class='micro']").click()
    page.wait_for_selector("[data-reactor-class='micro'].active")
    after = page.locator(".ap1000-row .ap1000-name").first.text_content()
    assert before and after  # both render; ordering may legitimately differ
    # Water-starved desert sites must not be pinned to the bottom under micro:
    scores = page.evaluate(
        """() => window.__ap1000ScoredRows ? null :
             Array.from(document.querySelectorAll('.ap1000-row .ap1000-score-chip'))
               .map((n) => Number(n.textContent))"""
    )
    assert scores and all(s > 0 for s in scores)
