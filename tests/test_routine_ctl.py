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
