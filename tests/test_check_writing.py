"""Unit tests for the AI-slop writing linter (scripts/check_writing.py).

Two jobs here, and the second matters more than the first:

  1. The rules fire on the phrases they claim to catch — every case below is
     a real string this repo actually shipped (see the 2026-08-25 writing
     pass), not an invented example.

  2. The rules do NOT fire on prose that is doing real work. A linter people
     learn to ignore is worse than no linter, so the suppression paths —
     ALLOW_PHRASES, comment/code stripping, and the slogan heuristic — get
     more coverage than the matching paths.

`test_repo_copy_has_no_banned_language` is the ongoing regression guard: it
keeps the shipped copy clean once it has been cleaned.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "check_writing.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_writing", MODULE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


cw = _load()


def _scan(text: str, rules=None):
    """Scan raw prose lines, as --stdin does."""
    units = enumerate(text.splitlines(), 1)
    return list(cw.scan_text("<t>", units, rules or cw.RULES))


def _ids(text: str) -> set:
    return {h.rule.id for h in _scan(text)}


# --- the rules catch what they claim ---------------------------------------

# Every string here shipped in this repo before the 2026-08-25 writing pass.
@pytest.mark.parametrize("phrase,rule_id", [
    ("a unit precluded across the board says None — off the table.", "off-the-table"),
    ("DOE sites, end to end — every reuse outcome, cited", "end-to-end"),
    ("That spread makes it the ideal end-to-end example.", "end-to-end"),
    ("facts are hand-curated and cited per row.", "hand-curated"),
    ("facts are hand-curated and cited per row.", "citation-boast"),
    ("Every claim links its source; screening evidence follows.", "citation-boast"),
    ("with an honest facility-fit call for each.", "self-praise"),
    ("a category with no verifiable public source is omitted rather than invented.",
     "self-praise"),
    ("it is never silently counted as a no-hit.", "self-praise"),
    ("an honest siting tool must render this with the same confidence.", "self-praise"),
    ("the Reach's fall Chinook are the textbook case.", "self-praise"),
    ("Unavailable is never a no-hit.", "negation-slogan"),
    ("It's not just a map, it's a siting tool.", "negation-slogan"),
    ("This platform is a testament to open data.", "puffery"),
    ("Let's dive in to the data.", "ai-opener"),
    ("It's important to note that coverage varies.", "ai-opener"),
])
def test_banned_phrase_is_flagged(phrase, rule_id):
    assert rule_id in _ids(phrase), f"{rule_id} missed: {phrase!r}"


def test_every_banned_rule_is_fail_level():
    for rule in cw.BANNED:
        assert rule.level == "FAIL", f"{rule.id} is in BANNED but not FAIL"
    for rule in cw.REVIEW:
        assert rule.level == "WARN", f"{rule.id} is in REVIEW but not WARN"


def test_rule_ids_are_unique():
    ids = [r.id for r in cw.RULES]
    assert len(ids) == len(set(ids))


# --- suppression: the parts that keep the linter usable --------------------

def test_allowlisted_legal_caveats_are_not_flagged():
    """A NEPA disclaimer has to say what a result is NOT."""
    text = ("Screening evidence, not a determination. "
            "Agencies make the actual determinations.")
    assert "negative-parallelism" not in _ids(text)


def test_allowlisted_program_names_keep_their_wording():
    assert _ids("Clean Energy on Mine Lands (CEML) is a DOE program.") == set()


def test_every_allow_phrase_carries_a_reason():
    for phrase, reason in cw.ALLOW_PHRASES:
        assert phrase.strip(), "empty allow phrase"
        assert reason.strip(), f"allow phrase {phrase!r} has no reason"


def test_literal_groundbreaking_ceremony_is_not_puffery():
    """Portsmouth held an actual groundbreaking — a noun, not a boast."""
    assert "puffery" not in _ids("groundbreaking held March 20, 2026")
    assert "puffery" not in _ids("a groundbreaking already held")
    # The adjectival boast still trips.
    assert "puffery" in _ids("a groundbreaking approach to siting")


# --- the slogan heuristic ---------------------------------------------------

def test_short_trailing_negation_reads_as_a_slogan():
    text = "Screening evidence, never an agency finding."
    assert "negative-parallelism" in _ids(text)


def test_long_explanatory_negation_is_left_alone():
    """This sentence is the CLAUDE.md lesson about naming the specific
    constraint — good writing that the rule must not punish."""
    text = ("The footprint is occupied by an active DOE conversion mission "
            "with no announced end date — a mission constraint, not a "
            "permanent legal bar.")
    assert "negative-parallelism" not in _ids(text)


# --- prose extraction: identifiers and code must never trip a rule ---------

def test_html_comments_are_not_scanned():
    html = "<!-- End-to-end dossiers for five DOE sites -->\n<p>Clean copy.</p>"
    assert list(cw.scan_text("f", cw.prose_lines_html(html), cw.RULES)) == []


def test_html_attributes_and_urls_are_not_scanned():
    """A link to hanford-e2e.json is a filename, not the phrase."""
    html = '<a href="/data/hanford-e2e.json" title="end-to-end">Dossier</a>'
    assert list(cw.scan_text("f", cw.prose_lines_html(html), cw.RULES)) == []


def test_js_line_comments_are_not_scanned():
    js = '// this renders the end-to-end dossier, off the table\nconst x = 1;'
    assert list(cw.scan_text("f", cw.prose_lines_js(js), cw.RULES)) == []


def test_js_visible_strings_are_scanned():
    js = 'return `<p>Every claim links its source.</p>`;'
    hits = list(cw.scan_text("f", cw.prose_lines_js(js), cw.RULES))
    assert {h.rule.id for h in hits} == {"citation-boast"}


def test_markdown_code_is_not_scanned():
    md = "Run `build_doe_sites_e2e.py` first.\n\n```\nend-to-end\n```\n"
    assert list(cw.scan_text("f", cw.prose_lines_md(md), cw.RULES)) == []


def test_json_skips_urls_and_scans_prose():
    payload = ('{"source_url": "https://x.test/end-to-end", '
               '"summary": "The dossier is hand-curated and complete."}')
    hits = list(cw.scan_text("f", cw.prose_lines_json(payload), cw.RULES))
    assert {h.rule.id for h in hits} == {"hand-curated"}


def test_line_numbers_survive_comment_stripping():
    html = "<!--\nmulti\nline\n-->\n<p>off the table</p>"
    hits = list(cw.scan_text("f", cw.prose_lines_html(html), cw.RULES))
    assert [h.line_no for h in hits] == [5]


# --- the ongoing guard ------------------------------------------------------

def test_repo_copy_has_no_banned_language():
    """The shipped copy stays clean. If this goes red, either fix the copy
    or — if the phrase is genuinely required — add it to ALLOW_PHRASES with
    a reason."""
    banned = []
    for path in cw.collect_copy_files():
        for hit in cw.scan_file(path, cw.BANNED):
            banned.append(f"{hit.source}:{hit.line_no} {hit.matched!r} "
                          f"({hit.rule.id})")
    assert not banned, "banned language in user-visible copy:\n" + "\n".join(banned)


def test_copy_globs_all_resolve():
    """A glob that matches nothing silently stops guarding its files."""
    for pattern in cw.COPY_GLOBS:
        assert list(ROOT.glob(pattern)), f"COPY_GLOBS pattern matches nothing: {pattern}"


# --- scoping: commit/PR prose is a different register than product copy ----

def test_citation_meta_is_scoped_to_copy_only():
    """"extended the citation-liveness check" is normal engineering
    vocabulary in a commit message; "every fact is cited" in product copy is
    the tell. Same word, different register."""
    rule = next(r for r in cw.RULES if r.id == "citation-meta")
    assert rule.scopes == ("copy",)


def test_banned_rules_apply_to_commits_and_prs():
    for rule in cw.BANNED:
        assert "text" in rule.scopes, f"{rule.id} would not catch a bad commit message"
        assert "copy" in rule.scopes, f"{rule.id} would not catch bad copy"


def test_every_rule_declares_at_least_one_scope():
    for rule in cw.RULES:
        assert rule.scopes, f"{rule.id} has no scope and can never fire"
        assert set(rule.scopes) <= {"copy", "text"}, f"{rule.id} has an unknown scope"
