#!/usr/bin/env python3
"""One-page project status: replaces the "sync and take stock" agent sessions.

Prints, in order: local vs origin/main, worktrees, open PRs (checks and
unanswered review comments), data files past their refresh cadence, overdue
research dossiers, the offline data-validation summary, and stray local web
servers. Read-only except `git fetch`.

  python3 scripts/project_status.py [--no-fetch] [--freshness]

--freshness also runs scripts/check_upstream_freshness.py (network, ~1 min).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = "/Library/Developer/CommandLineTools/usr/bin/git"
GH = str(Path.home() / ".local" / "bin" / "gh")
PY = str(ROOT / ".venv" / "bin" / "python")
REPO = "pranava0x0/brownfield-opportunities"
# Days after which a generated data file counts as due for a refresh.
CADENCE_DAYS = {
    "superfund-npl.json": 14, "dod-fuds.json": 30, "epa-redev.json": 30, "eia-retired-plants.json": 45,
    "planned-retirements.json": 45, "epa-echo.json": 120, "epa-superfund-docs.json": 120,
    "coal-conversions.json": 120, "nuclear-civilian-sites.json": 120, "microreactor-fleet.json": 120,
    "hanford-e2e.json": 120, "srs-e2e.json": 120, "portsmouth-e2e.json": 120, "paducah-e2e.json": 120,
    "wipp-e2e.json": 120, "ap1000-sites.json": 120, "federal-clean-energy.json": 120,
}


def sh(*cmd: str, check: bool = False) -> str:
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 or not check else ""


def section(title: str) -> None:
    print(f"\n== {title}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--freshness", action="store_true")
    args = ap.parse_args()
    if not args.no_fetch:
        sh(GIT, "fetch", "origin", "--prune")

    section("Git")
    print("branch:", sh(GIT, "branch", "--show-current"))
    print("ahead/behind origin/main:", sh(GIT, "rev-list", "--left-right", "--count", "HEAD...origin/main").replace("\t", "/"))
    print("uncommitted files:", len(sh(GIT, "status", "--porcelain").splitlines()))
    for line in sh(GIT, "worktree", "list").splitlines()[1:]:
        print("worktree:", line)

    section("Open PRs")
    prs = json.loads(sh(GH, "pr", "list", "--repo", REPO, "--state", "open", "--json", "number,title,createdAt") or "[]")
    for pr in prs:
        checks = json.loads(sh(GH, "pr", "checks", str(pr["number"]), "--repo", REPO, "--json", "bucket") or "[]")
        buckets = {c["bucket"] for c in checks} or {"none"}
        comments = json.loads(sh(GH, "api", f"repos/{REPO}/pulls/{pr['number']}/comments") or "[]")
        answered = {c["in_reply_to_id"] for c in comments if c.get("in_reply_to_id")}
        open_comments = sum(1 for c in comments if not c.get("in_reply_to_id") and c["id"] not in answered)
        print(f"#{pr['number']} {pr['title'][:60]} · opened {pr['createdAt'][:10]} · checks {','.join(sorted(buckets))} · {open_comments} unanswered comments")
    if not prs:
        print("none")

    section("Data files past cadence")
    today = dt.date.today()
    late = 0
    for name, days in CADENCE_DAYS.items():
        path = ROOT / "docs" / "data" / name
        if not path.exists():
            continue
        stamp = json.loads(path.read_text()).get("generated_at", "")[:10]
        if stamp and (today - dt.date.fromisoformat(stamp)).days > days:
            late += 1
            print(f"{name:<32} generated {stamp} (cadence {days} d)")
    if not late:
        print("none")

    section("Research dossiers past next_review")
    print(sh(PY, "scripts/site_research.py", "due") or "none")
    print(sh(PY, "scripts/research_queue.py", "check"))

    section("Offline data validation")
    print(sh(PY, "scripts/validate_data.py", "--fail-on", "NEVER").splitlines()[-1:][0] if True else "")

    section("Stray local web servers")
    print(sh("pgrep", "-fl", "http.server|serve.py") or "none")

    if args.freshness:
        section("Upstream freshness")
        print(sh(PY, "scripts/check_upstream_freshness.py"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
