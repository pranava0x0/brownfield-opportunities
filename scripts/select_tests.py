#!/usr/bin/env python3
"""Pick the tests a change actually needs, instead of running everything.

Why
---
The full suite is ~730 unit tests plus ~380 browser tests, and the browser
half dominates: a serial e2e pass over this project runs 15-25 minutes, which
is long enough that it stops being run. A gate people skip is worse than a
smaller gate they keep.

This maps changed files to the tests that can actually observe them, so a
typical single-connector or single-tab change runs in seconds rather than
minutes. It is a SELECTOR, not a replacement for CI: the full suite still runs
on the PR, and anything this cannot classify escalates to everything rather
than quietly narrowing.

Design rules
------------
1. **Unknown means everything.** A changed path matching no rule returns the
   full suite. Guessing narrow on an unrecognised file is how a selector
   starts hiding regressions.
2. **Shared foundations are not selective.** `schema.py`, `conftest.py`,
   `refresh.py`, `connectors/base.py`, `connectors/spatial.py` and the CI
   config touch everything downstream, so they force the full suite.
3. **Cross-cutting guards always run.** The DOM budget, refresh-date drift,
   tab scrolling and provenance drift checks exist precisely because the bugs
   they catch appear in files that look unrelated. They are cheap and they are
   the ones that have actually caught things.

Usage
-----
    python3 scripts/select_tests.py                 # vs origin/main
    python3 scripts/select_tests.py --range HEAD~1  # explicit base
    python3 scripts/select_tests.py --explain       # show the mapping
    bash scripts/pr_gate.sh --impacted              # use it in the gate
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Always run these: cheap, cross-cutting, and historically the ones that catch
# regressions in files that look unrelated to them.
ALWAYS = [
    "tests/test_provenance_registry.py",
    "tests/e2e/test_tab_scrolling.py",
    "tests/e2e/test_smoke.py::test_dom_size_under_5k_nodes",
    "tests/e2e/test_smoke.py::test_refresh_date_reflects_freshest_data_file",
]

# A change to any of these can break anything downstream — no narrowing.
FULL_SUITE_TRIGGERS = [
    "schema.py",
    "refresh.py",
    "conftest.py",
    "tests/conftest.py",
    "tests/e2e/conftest.py",
    "connectors/base.py",
    "connectors/spatial.py",
    "connectors/__init__.py",
    "connectors/geom.py",
    "requirements.txt",
    ".github/workflows/*",
    "scripts/select_tests.py",
]

# glob -> tests that can observe a change to it.
RULES: list[tuple[str, list[str]]] = [
    # Score modules: their own logic tests, plus the collision guard — a bare
    # top-level name in one of these silently overwrites another's global.
    ("docs/nickel-score.js", ["tests/e2e/test_nickel_score.py", "tests/e2e/test_nickel_tab.py"]),
    ("docs/dc-score.js", ["tests/e2e/test_dc_score.py", "tests/e2e/test_candidates_view.py"]),
    ("docs/maritime-score.js", ["tests/e2e/test_maritime_score.py"]),
    ("docs/microreactor-score.js", ["tests/e2e/test_microreactor.py"]),
    ("docs/ap1000-score.js", ["tests/e2e/test_ap1000_score.py"]),
    ("docs/provenance.js", ["tests/test_provenance_registry.py", "tests/e2e/test_evidence_panel.py"]),
    # app.js and the page shell drive every view.
    ("docs/app.js", ["tests/e2e/"]),
    ("docs/index.html", ["tests/e2e/"]),
    # CSS cannot change behaviour, only geometry — the scrolling/overflow and
    # DOM guards in ALWAYS are the ones that can see it.
    ("docs/style.css", []),
    # Connectors and their builders.
    ("connectors/water_proximity.py", ["tests/test_water_proximity.py"]),
    ("connectors/nickel_anchor_proximity.py", ["tests/test_nickel_anchors.py"]),
    ("connectors/port_proximity.py", ["tests/test_port_proximity.py"]),
    ("scripts/build_streamgages_overlay.py", ["tests/test_water_proximity.py"]),
    ("scripts/build_nickel_anchors.py", ["tests/test_nickel_anchors.py"]),
    ("connectors/*.py", ["tests/"]),
    ("scripts/build_*.py", ["tests/"]),
    ("scripts/validate_data.py", ["tests/"]),
    ("scripts/check_writing.py", ["tests/test_check_writing.py"]),
    # Data files: the offline validators cover these, and pr_gate runs those
    # separately, so no pytest target is implied.
    ("docs/data/*", []),
    # Docs and research prose.
    ("*.md", []),
    ("research/*", []),
    ("docs/llms.txt", []),
]


def changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    files = [f for f in out.stdout.splitlines() if f.strip()]
    # Uncommitted work counts too — the gate runs before a commit as often as
    # after one.
    for extra in ("--cached", ""):
        cmd = ["git", "diff", "--name-only"] + ([extra] if extra else [])
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        files += [f for f in r.stdout.splitlines() if f.strip()]
    return sorted(set(files))


def select(files: list[str]) -> tuple[list[str], list[str]]:
    """(pytest targets, reasons). Empty targets means nothing to run."""
    reasons: list[str] = []
    if not files:
        return [], ["no changed files"]

    for f in files:
        for trig in FULL_SUITE_TRIGGERS:
            if fnmatch.fnmatch(f, trig):
                return ["tests/"], [f"{f} is a shared foundation — full suite"]

    targets: set[str] = set(ALWAYS)
    unmatched: list[str] = []
    for f in files:
        for pattern, tests in RULES:
            if fnmatch.fnmatch(f, pattern):
                if tests:
                    targets.update(tests)
                    reasons.append(f"{f} -> {', '.join(tests)}")
                else:
                    reasons.append(f"{f} -> (guards only)")
                break
        else:
            unmatched.append(f)

    if unmatched:
        return ["tests/"], [f"unrecognised path {u} — full suite" for u in unmatched]

    # A directory target subsumes the individual files under it.
    if "tests/e2e/" in targets:
        targets = {t for t in targets if not t.startswith("tests/e2e/test_")}
    return sorted(targets), reasons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--range", default="origin/main",
                    help="Base to diff against (default: origin/main).")
    ap.add_argument("--explain", action="store_true",
                    help="Print the mapping to stderr.")
    args = ap.parse_args()

    files = changed_files(args.range)
    targets, reasons = select(files)
    if args.explain:
        print(f"# {len(files)} changed file(s)", file=sys.stderr)
        for r in reasons:
            print(f"#   {r}", file=sys.stderr)
        print(f"# -> {len(targets)} pytest target(s)", file=sys.stderr)
    print(" ".join(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
