"""The impacted-test selector must narrow safely, and fail open when unsure.

A selector that guesses narrow hides regressions, so the interesting cases
here are the ones where it must REFUSE to narrow.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "select_tests", str(ROOT / "scripts" / "select_tests.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sel():
    return _load()


def test_a_single_score_module_runs_only_its_own_tests(sel):
    targets, _ = sel.select(["docs/nickel-score.js"])
    assert "tests/e2e/test_nickel_score.py" in targets
    assert "tests/" not in targets, "must not escalate to the full suite"
    assert "tests/e2e/test_dc_score.py" not in targets


def test_css_only_changes_run_the_geometry_guards_and_nothing_else(sel):
    """CSS cannot change behaviour, only geometry — so the scrolling and DOM
    guards are exactly the right coverage, and the logic suites are not."""
    targets, _ = sel.select(["docs/style.css"])
    assert "tests/e2e/test_tab_scrolling.py" in targets
    assert "tests/e2e/test_nickel_score.py" not in targets
    assert "tests/" not in targets


def test_prose_only_changes_still_run_the_cheap_guards(sel):
    targets, _ = sel.select(["README.md", "research/foo.md"])
    assert targets == sorted(sel.ALWAYS)


@pytest.mark.parametrize("path", [
    "schema.py", "refresh.py", "connectors/base.py", "connectors/spatial.py",
    "connectors/__init__.py", "tests/e2e/conftest.py", "requirements.txt",
])
def test_shared_foundations_force_the_full_suite(sel, path):
    """These reach everything downstream. Narrowing here is how a selector
    starts hiding regressions."""
    targets, reasons = sel.select([path])
    assert targets == ["tests/"], f"{path} narrowed to {targets}"
    assert any("full suite" in r for r in reasons)


def test_an_unrecognised_path_fails_open(sel):
    """Unknown means everything. A new top-level file must not silently map to
    no coverage."""
    targets, reasons = sel.select(["some/brand/new/thing.py"])
    assert targets == ["tests/"]
    assert any("unrecognised" in r for r in reasons)


def test_the_cross_cutting_guards_are_always_included(sel):
    """They are cheap, and they are the ones that catch bugs in files that
    look unrelated to them — the tab-scrolling and DOM-budget regressions both
    arrived that way."""
    for change in (["docs/nickel-score.js"], ["connectors/water_proximity.py"],
                   ["docs/style.css"], ["README.md"]):
        targets, _ = sel.select(change)
        for guard in sel.ALWAYS:
            assert guard in targets, f"{guard} missing for {change}"


def test_a_directory_target_subsumes_its_files(sel):
    """app.js drives every view, so it selects tests/e2e/ — and the individual
    e2e files must not also be listed or pytest would run them twice."""
    targets, _ = sel.select(["docs/app.js"])
    assert "tests/e2e/" in targets
    assert not any(t.startswith("tests/e2e/test_") for t in targets)


def test_every_rule_points_at_a_test_path_that_exists(sel):
    """A rule naming a deleted test file silently selects nothing."""
    missing = []
    for _pattern, tests in sel.RULES:
        for t in tests:
            base = t.split("::")[0]
            if not (ROOT / base).exists():
                missing.append(t)
    for t in sel.ALWAYS:
        if not (ROOT / t.split("::")[0]).exists():
            missing.append(t)
    assert not missing, f"rules point at missing paths: {missing}"
