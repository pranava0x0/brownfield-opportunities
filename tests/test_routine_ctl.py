"""routine_ctl.sync rebuilds a missing worktree from the right base."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("routine_ctl", ROOT / "scripts" / "routine_ctl.py")
routine_ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routine_ctl)


def _worktree_add_args(monkeypatch, tmp_path, local: str, remote: str) -> list:
    calls = []

    def fake_git(*args, cwd=None, check=True):
        calls.append(args)
        if args[:2] == ("branch", "--list"):
            return local
        if args[:3] == ("branch", "-r", "--list"):
            return remote
        return ""

    monkeypatch.setattr(routine_ctl, "git", fake_git)
    monkeypatch.setattr(routine_ctl, "WT", tmp_path / "missing-worktree")
    monkeypatch.setattr(routine_ctl, "open_pr", lambda: None)
    monkeypatch.setattr(routine_ctl.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    routine_ctl.sync()
    return next(a for a in calls if a[:2] == ("worktree", "add"))


def test_pushed_branch_is_used_when_no_local_branch(monkeypatch, tmp_path):
    # The open PR's commits live on origin/<branch>; starting from main would drop them.
    args = _worktree_add_args(monkeypatch, tmp_path, local="", remote="origin/routine/site-research")
    assert args[-1] == "origin/routine/site-research" and "--track" in args


def test_local_branch_wins(monkeypatch, tmp_path):
    args = _worktree_add_args(monkeypatch, tmp_path, local="routine/site-research", remote="origin/routine/site-research")
    assert args[-1] == "routine/site-research" and "-b" not in args


def test_main_when_branch_exists_nowhere(monkeypatch, tmp_path):
    args = _worktree_add_args(monkeypatch, tmp_path, local="", remote="")
    assert args[-1] == "origin/main"


def test_dossier_conflict_is_resolved_by_union(tmp_path, monkeypatch):
    """Two edits to the one-line dossier file conflict in git even for different
    sites (PR #44); sync must keep both sets of dossiers."""
    import json
    import subprocess
    git = lambda *a, cwd: subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True).stdout.strip()
    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.email", "t@t", cwd=repo)
    git("config", "user.name", "t", cwd=repo)
    (repo / "docs" / "data").mkdir(parents=True)
    f = repo / "docs" / "data" / "site-research.json"
    write = lambda ids: f.write_text(json.dumps({"sites": [{"id": i} for i in ids]}))
    write(["A"])
    git("add", ".", cwd=repo)
    git("commit", "-q", "-m", "base", cwd=repo)
    git("checkout", "-q", "-b", "branch", cwd=repo)
    write(["A", "B"])
    git("commit", "-qam", "branch", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    write(["A", "C"])
    git("commit", "-qam", "main", cwd=repo)
    git("checkout", "-q", "branch", cwd=repo)
    monkeypatch.setattr(routine_ctl, "WT", repo)
    monkeypatch.setattr(routine_ctl, "GIT", "git")
    added = []
    real_run = routine_ctl.run
    monkeypatch.setattr(routine_ctl, "run", lambda *c, **k: real_run(*c, **k) if c[0] == "git" else (added.append(c) or ""))
    base = git("merge-base", "HEAD", "main", cwd=repo)
    assert subprocess.run(["git", "-C", str(repo), "merge", "--no-edit", "main"], capture_output=True).returncode
    msg = routine_ctl.resolve_merge_conflict(base)
    assert "re-added 1 dossiers" in msg
    assert added and added[0][2] == "add" and added[0][3].endswith("B.json")
    assert git("status", "--porcelain", cwd=repo) == ""


def test_same_site_changed_on_both_sides_is_not_silently_overwritten(tmp_path, monkeypatch):
    """PR #44 review: the branch copy must not revert a same-day correction on main."""
    import json
    import subprocess
    git = lambda *a, cwd: subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True).stdout.strip()
    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.email", "t@t", cwd=repo)
    git("config", "user.name", "t", cwd=repo)
    (repo / "docs" / "data").mkdir(parents=True)
    f = repo / "docs" / "data" / "site-research.json"
    write = lambda note: f.write_text(json.dumps({"sites": [{"id": "A", "note": note}]}))
    write("base")
    git("add", ".", cwd=repo)
    git("commit", "-q", "-m", "base", cwd=repo)
    git("checkout", "-q", "-b", "branch", cwd=repo)
    write("branch")
    git("commit", "-qam", "branch", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    write("main correction")
    git("commit", "-qam", "main", cwd=repo)
    git("checkout", "-q", "branch", cwd=repo)
    monkeypatch.setattr(routine_ctl, "WT", repo)
    monkeypatch.setattr(routine_ctl, "GIT", "git")
    base = git("merge-base", "HEAD", "main", cwd=repo)
    assert subprocess.run(["git", "-C", str(repo), "merge", "--no-edit", "main"], capture_output=True).returncode
    msg = routine_ctl.resolve_merge_conflict(base)
    assert "MERGE CONFLICT" in msg and "['A']" in msg
    assert json.loads(f.read_text())["sites"][0]["note"] == "branch"
    assert git("status", "--porcelain", cwd=repo) == ""
