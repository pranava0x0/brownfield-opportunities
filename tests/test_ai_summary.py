"""Unit tests for the AI-summary (Claude Haiku) enrichment connector.

Covers the input fingerprint, the user-prompt assembly, the status filter,
and the cache round-trip. No network calls — the API call itself is
exercised via dependency-injection-friendly seams.
"""
from __future__ import annotations

from pathlib import Path

from connectors.ai_summary import (
    AiSummary,
    _fingerprint,
    _fmt_distance,
    _pretty_text,
    build_static_summary,
    build_user_prompt,
)


# ---- fingerprint ----

def test_fingerprint_is_deterministic():
    site = {"id": "X", "program": "superfund", "name": "Acme", "acreage": 10}
    assert _fingerprint(site) == _fingerprint(site)


def test_fingerprint_changes_when_relevant_field_changes():
    a = {"id": "X", "program": "superfund", "name": "Acme", "acreage": 10}
    b = dict(a, acreage=20)
    assert _fingerprint(a) != _fingerprint(b)


def test_fingerprint_ignores_cosmetic_only_fields():
    """`lat_real`, `_inset`, `city_raw` etc. are display-time scaffolding
    and shouldn't trigger a re-bill of the model."""
    a = {"id": "X", "program": "superfund", "name": "Acme"}
    b = dict(a, lat_real=39.5, _inset="AK", city_raw="GREEN BAY")
    assert _fingerprint(a) == _fingerprint(b)


def test_fingerprint_includes_enforcement_headline():
    a = {"id": "X", "program": "superfund", "name": "Acme"}
    b = dict(a, enforcement={"formal_actions_5yr": 3, "current_compliance": "OK"})
    assert _fingerprint(a) != _fingerprint(b)


def test_fingerprint_includes_document_count_and_categories():
    a = {"id": "X", "program": "superfund", "name": "Acme", "documents": []}
    b = dict(a, documents=[{"category": "Key Documents", "title": "ROD"}])
    assert _fingerprint(a) != _fingerprint(b)


def test_fingerprint_stable_across_doc_order():
    """Document order shouldn't trip the cache — we hash counts + categories."""
    a = {
        "id": "X", "program": "superfund", "name": "Acme",
        "documents": [
            {"category": "Key Documents", "title": "A"},
            {"category": "SPP Decision Documents", "title": "B"},
        ],
    }
    b = dict(a, documents=list(reversed(a["documents"])))
    assert _fingerprint(a) == _fingerprint(b)


# ---- user prompt assembly ----

def test_user_prompt_includes_program_label():
    site = {"id": "X", "program": "superfund", "name": "Acme"}
    prompt = build_user_prompt(site)
    assert "EPA Superfund (NPL)" in prompt
    assert "Acme" in prompt


def test_user_prompt_omits_absent_fields():
    """Empty/None fields must not appear as `Field: ` lines — that primes
    the model to invent."""
    site = {"id": "X", "program": "superfund", "name": "Acme"}
    prompt = build_user_prompt(site)
    assert "Acreage:" not in prompt
    assert "NPL status:" not in prompt
    assert "Current owner:" not in prompt


def test_user_prompt_renders_infra_distances():
    site = {
        "id": "X", "program": "superfund", "name": "Acme",
        "transmission_mi": 0.4, "rail_mi": 1.2, "highway_mi": 5.0,
    }
    prompt = build_user_prompt(site)
    assert "transmission 0.4 mi" in prompt
    assert "rail 1.2 mi" in prompt
    assert "highway 5.0 mi" in prompt


def test_user_prompt_renders_enforcement():
    site = {
        "id": "X", "program": "superfund", "name": "Acme",
        "enforcement": {
            "inspections_5yr": 3,
            "formal_actions_5yr": 1,
            "penalties_5yr_usd": 50000.0,
            "current_compliance": "Significant Violation",
        },
    }
    prompt = build_user_prompt(site)
    assert "EPA ECHO" in prompt
    assert "1 formal actions" in prompt
    assert "$50,000" in prompt
    assert "Significant Violation" in prompt


def test_user_prompt_renders_dc_candidate_yes_and_no():
    yes = build_user_prompt({
        "id": "X", "program": "superfund", "name": "Acme",
        "data_center_reuse_candidate": True,
    })
    no = build_user_prompt({
        "id": "X", "program": "superfund", "name": "Acme",
        "data_center_reuse_candidate": False,
    })
    assert "YES" in yes
    assert "Data-center reuse candidate: NO" in no


def test_user_prompt_renders_owner_with_source():
    site = {
        "id": "X", "program": "fuds", "name": "Acme Field",
        "current_owner": "USACE", "current_owner_source": "USACE FUDS",
    }
    prompt = build_user_prompt(site)
    assert "Current owner: USACE (per USACE FUDS)" in prompt


# ---- status filter ----

def test_status_filter_parses_csv():
    assert AiSummary._parse_status_filter("F,D") == {"F", "D"}


def test_status_filter_all_returns_none():
    assert AiSummary._parse_status_filter("all") is None


def test_status_filter_empty_returns_none():
    assert AiSummary._parse_status_filter("") is None
    assert AiSummary._parse_status_filter(None) is None


# ---- cache round-trip ----

def test_summary_cache_roundtrip(tmp_path: Path):
    inst = AiSummary(cache_dir=tmp_path)
    inst._write_cached_summary(
        "EPA-1",
        "deadbeef",
        "Paragraph one.\n\nParagraph two.\n\nParagraph three.",
        {"model": "claude-haiku-4-5-20251001", "hash": "deadbeef", "generated_at": "2026-05-04T00:00:00Z"},
    )
    loaded = inst._read_cached_summary("EPA-1", "deadbeef")
    assert loaded is not None
    assert loaded["summary"].startswith("Paragraph one.")
    assert loaded["summary_meta"]["model"] == "claude-haiku-4-5-20251001"


def test_summary_cache_miss_returns_none(tmp_path: Path):
    inst = AiSummary(cache_dir=tmp_path)
    assert inst._read_cached_summary("EPA-NEVER", "0") is None


def test_summary_cache_path_isolates_by_fingerprint(tmp_path: Path):
    """Same site id with different fingerprint = different cache file —
    so a real input change forces a new generation rather than serving stale."""
    inst = AiSummary(cache_dir=tmp_path)
    p1 = inst._summary_cache_path("EPA-1", "abc")
    p2 = inst._summary_cache_path("EPA-1", "def")
    assert p1 != p2


def test_summary_cache_isolated_from_http_cache(tmp_path: Path):
    """`_summary_cache_path` must not collide with `cache_path()` from
    the base class — they share `self.cache_dir`."""
    inst = AiSummary(cache_dir=tmp_path)
    summary_path = inst._summary_cache_path("EPA-1", "abc")
    http_path = inst.cache_path({"url": "https://example.com", "params": {}})
    assert summary_path.name != http_path.name
    assert "summary" in summary_path.name


# ---- _fmt_distance: "adjacent" replaces "on-site" / "0.0 miles" ----

def test_fmt_distance_renders_adjacent_for_zero():
    """Connector emits `round(d, 1)`, so values < 0.05 mi land as 0.0.
    The formatter should treat that as the "passes through / borders the
    boundary" case and read as a feature, not a `0.0 mi` display bug."""
    assert _fmt_distance(0.0) == "adjacent"
    assert _fmt_distance(0.04) == "adjacent"
    assert _fmt_distance(0.049) == "adjacent"


def test_fmt_distance_renders_miles_above_threshold():
    """At and above 0.05 mi the value is meaningful — render as
    "N.N miles away" so the prose stays uniform with the longer-distance
    cases."""
    assert _fmt_distance(0.05) == "0.1 miles away"  # rounds up to 0.1
    assert _fmt_distance(0.4) == "0.4 miles away"
    assert _fmt_distance(7.0) == "7.0 miles away"
    assert _fmt_distance(31.85) == "31.9 miles away"


# ---- build_static_summary: adjacent + DC parenthetical trim ----

def _base_site(**overrides):
    """Minimal Superfund site for static-summary tests."""
    site = {
        "id": "EPA-X",
        "program": "superfund",
        "name": "Acme Industrial",
        "city": "Springfield",
        "state": "OH",
        "acreage": 120,
        "npl_status": "Final",
    }
    site.update(overrides)
    return site


def test_static_summary_renders_adjacent_for_zero_distance():
    """All three infra clauses should use the shared "adjacent" wording when
    the rounded distance is 0.0 — never "0.0 miles" or "on-site"."""
    site = _base_site(transmission_mi=0.0, rail_mi=0.0, highway_mi=0.0)
    out = build_static_summary(site)
    assert "0.0 miles" not in out
    assert "0.0 mi" not in out
    assert "on-site" not in out
    assert "transmission lines adjacent" in out
    assert "rail adjacent" in out
    assert "highway adjacent" in out


def test_static_summary_renders_miles_for_real_distance():
    site = _base_site(transmission_mi=0.4, rail_mi=7.0, highway_mi=31.9)
    out = build_static_summary(site)
    assert "transmission lines 0.4 miles away" in out
    assert "rail 7.0 miles away" in out
    assert "highway 31.9 miles away" in out


def test_static_summary_mixes_adjacent_and_miles():
    site = _base_site(transmission_mi=0.0, rail_mi=7.0, highway_mi=0.04)
    out = build_static_summary(site)
    assert "transmission lines adjacent" in out
    assert "rail 7.0 miles away" in out
    assert "highway adjacent" in out


def test_static_summary_trims_dc_parenthetical():
    """The "(≥50 acres with electric transmission and water service access)"
    parenthetical was repeated verbatim on 776 sites — read as boilerplate at
    scale. The criteria still appear in the KPI subtext, the legend pill, and
    the detail panel — but not in every per-site narrative."""
    site = _base_site(data_center_reuse_candidate=True)
    out = build_static_summary(site)
    assert "Flagged as a data-center reuse candidate." in out
    # Boilerplate must be gone:
    assert "(≥50 acres" not in out
    assert "EPA RE-Powering criteria" not in out
    assert "with electric transmission and water service access" not in out


def test_static_summary_omits_dc_clause_when_false():
    site = _base_site(data_center_reuse_candidate=False)
    out = build_static_summary(site)
    assert "data-center reuse candidate" not in out


# ---- _pretty_text: title-case regressions (backlog 440-448, v1.11.3) ----

def test_pretty_text_apostrophe_possessive_not_uppercased():
    """str.title() produced "Beck'S Lake" — the 's after the apostrophe must
    stay lowercase (regex lookbehind excludes apostrophe)."""
    assert _pretty_text("BECK'S LAKE") == "Beck's Lake"
    assert _pretty_text("SIGMON'S SEPTIC TANK SERVICE") == "Sigmon's Septic Tank Service"


def test_pretty_text_prepositions_lowercased():
    """The old <=2-char keep-upper rule preserved OF/IN mid-string; stop words
    must be lowercased so we get "University of Minnesota", not "OF"."""
    assert _pretty_text("UNIVERSITY OF MINNESOTA") == "University of Minnesota"
    assert _pretty_text("TOWN OF BEDFORD") == "Town of Bedford"


def test_pretty_text_company_abbrev_not_state_code():
    """"CO." (Company) must title-case to "Co.", not stay uppercase like the
    Colorado postal code — the trailing period is the disambiguator."""
    assert _pretty_text("SMITH CO. DUMP") == "Smith Co. Dump"


def test_static_summary_lead_uses_an_for_vowel_program_label():
    """Grammar: "is a EPA Superfund" → "is an EPA Superfund" when no acreage
    fronts the label and the program starts with a vowel sound."""
    site = _base_site(acreage=None)
    out = build_static_summary(site)
    assert "is an EPA Superfund" in out
    assert "is a EPA" not in out


def test_static_summary_suppresses_clean_compliance_noise():
    """A clean ECHO record (no formal actions, no penalties, no violation date)
    must not surface an enforcement sentence — "No Violation Identified" is not
    a risk signal and read as noise on 80 sites."""
    site = _base_site(
        enforcement={
            "formal_actions_5yr": 0,
            "penalties_5yr_usd": 0,
            "last_violation_date": None,
            "current_compliance": "No Violation Identified",
        }
    )
    out = build_static_summary(site)
    assert "No Violation" not in out
    assert "compliance" not in out.lower()
    assert "EPA ECHO records show" not in out
