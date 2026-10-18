#!/usr/bin/env python3
"""Deterministic steps of the daily research routine.

  sync                 fetch, make sure the routine worktree exists, and bring
                       routine/site-research up to date (never discards
                       unmerged research). Prints JSON: pr, age_days, action.
  comments             list review comments on the open PR that have no reply
                       starting "Fixed in" or "Not changed:".
  reply ID TEXT        reply to review comment ID.
  checks               run the four local checks the routine needs before a commit.
  closeout [--merge]   exit 0 only when the PR is >= 3 days old, every comment is
                       answered, CI is green and local checks pass; --merge then
                       merges with a merge commit.
  clock start|status   start the 25-minute clock / print elapsed minutes and phase.

Run from anywhere; paths come from this file's location.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

MAIN = Path(__file__).resolve().parent.parent
WT = MAIN / ".claude" / "worktrees" / "routine-site-research"
BRANCH = "routine/site-research"
REPO = "pranava0x0/brownfield-opportunities"
GIT = "/Library/Developer/CommandLineTools/usr/bin/git"
GH = str(Path.home() / ".local" / "bin" / "gh")
PY = str(MAIN / ".venv" / "bin" / "python")
CLOSEOUT_DAYS = 3
CLOCK = WT / ".routine-clock"
PHASES = [(14, "research ok"), (18, "no new research: finish checks"), (25, "wrap up now"), (999, "over budget: stop")]


def run(*cmd: str, cwd: Path = MAIN, check: bool = True) -> str:
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and out.returncode:
        raise SystemExit(f"$ {' '.join(cmd)}\n{out.stderr.strip()}")
    return out.stdout.strip()


def git(*args: str, cwd: Path = WT, check: bool = True) -> str:
    return run(GIT, "-C", str(cwd), *args, check=check)


def open_pr() -> dict | None:
    prs = json.loads(run(GH, "pr", "list", "--repo", REPO, "--head", BRANCH, "--state", "open",
                         "--json", "number,createdAt"))
    return prs[0] if prs else None


def age_days(pr: dict) -> float:
    created = dt.datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 86400


def sync() -> dict:
    git("fetch", "origin", "--prune", cwd=MAIN)
    if not WT.exists():
        has_branch = git("branch", "--list", BRANCH, cwd=MAIN)
        args = ["worktree", "add", str(WT), BRANCH] if has_branch else ["worktree", "add", "-b", BRANCH, str(WT), "origin/main"]
        git(*args, cwd=MAIN)
    pr = open_pr()
    git("checkout", BRANCH)
    if pr:
        if subprocess.run([GIT, "-C", str(WT), "merge", "--no-edit", "origin/main"], capture_output=True).returncode:
            git("merge", "--abort", check=False)
            action = "merge conflict with origin/main: aborted, continuing on the current base"
        else:
            action = "merged origin/main into the PR branch"
    elif subprocess.run([GIT, "-C", str(WT), "merge", "--ff-only", "origin/main"], capture_output=True).returncode == 0:
        action = "fast-forwarded to origin/main"
    elif not git("log", "--oneline", "origin/main..HEAD"):
        git("reset", "--hard", "origin/main")
        action = "reset to origin/main (branch had no unmerged commits)"
    else:
        raise SystemExit("branch has commits not in main and no open PR: stop and report, never discard research")
    return {"pr": pr and pr["number"], "age_days": pr and round(age_days(pr), 2), "action": action}


def unanswered(pr_number: int) -> list[dict]:
    comments = json.loads(run(GH, "api", "--paginate", f"repos/{REPO}/pulls/{pr_number}/comments"))
    replied = {c["in_reply_to_id"] for c in comments
               if c.get("in_reply_to_id") and c["body"].startswith(("Fixed in", "Not changed:"))}
    return [{"id": c["id"], "path": c["path"], "line": c.get("line"), "body": c["body"][:700]}
            for c in comments if not c.get("in_reply_to_id") and c["id"] not in replied]


def local_checks() -> list[str]:
    cmds = [
        [PY, "scripts/site_research.py", "validate"],
        [PY, "-m", "pytest", "tests/test_site_research.py", "-q", "-p", "no:cacheprovider"],
        [PY, "scripts/validate_data.py", "--only", "site-research-contract"],
        [PY, "scripts/research_queue.py", "check"],
    ]
    failed = []
    for c in cmds:
        if subprocess.run(c, cwd=WT, capture_output=True).returncode:
            failed.append(" ".join(c[1:]))
    return failed


def closeout(merge: bool) -> int:
    pr = open_pr()
    if not pr:
        print("no open PR")
        return 1
    reasons = []
    if age_days(pr) < CLOSEOUT_DAYS:
        reasons.append(f"PR is {age_days(pr):.1f} days old (needs {CLOSEOUT_DAYS})")
    if (left := unanswered(pr["number"])):
        reasons.append(f"{len(left)} unanswered review comments")
    checks = json.loads(run(GH, "pr", "checks", str(pr["number"]), "--repo", REPO, "--json", "name,bucket", check=False) or "[]")
    if not checks or any(c["bucket"] != "pass" for c in checks):
        reasons.append("CI not all green: " + ", ".join(f"{c['name']}={c['bucket']}" for c in checks))
    if (failed := local_checks()):
        reasons.append("local checks failed: " + "; ".join(failed))
    if reasons:
        print("not ready:\n- " + "\n- ".join(reasons))
        return 1
    if merge:
        run(GH, "pr", "merge", str(pr["number"]), "--repo", REPO, "--merge")
        print(f"merged PR #{pr['number']}")
    else:
        print(f"PR #{pr['number']} ready to merge")
    return 0


def clock(action: str) -> None:
    if action == "start":
        CLOCK.write_text(str(int(time.time())))
        print("clock started")
        return
    minutes = (time.time() - int(CLOCK.read_text())) / 60
    phase = next(p for limit, p in PHASES if minutes < limit)
    print(f"{minutes:.1f} min · {phase}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "sync":
        print(json.dumps(sync()))
    elif cmd == "comments":
        pr = open_pr()
        print(json.dumps(unanswered(pr["number"]) if pr else [], indent=1))
    elif cmd == "reply":
        pr = open_pr()
        run(GH, "api", f"repos/{REPO}/pulls/{pr['number']}/comments/{argv[1]}/replies", "-f", f"body={' '.join(argv[2:])}")
    elif cmd == "checks":
        failed = local_checks()
        print("\n".join(failed) or "all local checks pass")
        return 1 if failed else 0
    elif cmd == "closeout":
        return closeout("--merge" in argv)
    elif cmd == "clock":
        clock(argv[1] if len(argv) > 1 else "status")
    else:
        raise SystemExit(f"unknown command {cmd!r}; see --help")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
