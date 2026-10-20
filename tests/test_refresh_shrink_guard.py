"""A connector that returns far fewer records than its file already holds
must not overwrite it without an explicit --allow-shrink.

The empty-write guard stops a zero-record write. It cannot stop a truncated
one: on 2026-09-25 an ECHO refresh was throttled after ~550 sites, skipped
the rest, and would have replaced 1,906 records with 557. The same shape
comes from `--limit N` runs, which write N records over the full file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import refresh


def _connector(n: int, authoritative: bool = False):
    class _C:
        slug = "shrinking"
        source_label = "Test source"
        source_url = "https://example.invalid/test"
        authoritative_inventory = authoritative

        def __init__(self, cache_dir: Path):
            self.cache_dir = cache_dir

        def fetch_records(self, args, use_cache):
            return [{"id": f"S{i}", "name": "Test site", "program": "brownfield",
                     "state": "XX", "lat": 40.0, "lon": -80.0} for i in range(n)]
    return _C


def _args(**over) -> argparse.Namespace:
    base = dict(fetch_only=False, pretty=False, limit=None, output=None, allow_shrink=False)
    base.update(over)
    return argparse.Namespace(**base)


def _prior(path: Path, n: int) -> str:
    text = json.dumps({"generated_at": "2026-06-19T00:00:00Z", "source": "prior", "source_url": "https://example.invalid/p",
                       "count": n, "sites": [{"id": f"S{i}"} for i in range(n)]})
    path.write_text(text)
    return text


def _run(tmp_path, monkeypatch, n_new: int, **args_over):
    monkeypatch.setattr(refresh.connectors, "get", lambda _slug: _connector(n_new))
    monkeypatch.setattr(refresh, "CACHE_DIR", tmp_path / "cache")
    return refresh._run_one("test-enrichment", _args(**args_over), use_cache=False,
                            output_override=tmp_path / "enrichment.json")


def test_large_shrink_is_refused_and_the_file_is_untouched(tmp_path, monkeypatch):
    before = _prior(tmp_path / "enrichment.json", 100)
    rc, records, _ = _run(tmp_path, monkeypatch, 30)
    assert rc == 1 and records is None
    assert (tmp_path / "enrichment.json").read_text() == before


def test_allow_shrink_permits_an_intended_smaller_write(tmp_path, monkeypatch):
    _prior(tmp_path / "enrichment.json", 100)
    rc, records, _ = _run(tmp_path, monkeypatch, 30, allow_shrink=True)
    assert rc == 0 and len(records) == 30
    assert json.loads((tmp_path / "enrichment.json").read_text())["count"] == 30


def test_ordinary_churn_below_the_threshold_is_allowed(tmp_path, monkeypatch):
    _prior(tmp_path / "enrichment.json", 100)
    rc, records, _ = _run(tmp_path, monkeypatch, 95)
    assert rc == 0 and len(records) == 95


def test_first_run_and_growth_are_unaffected(tmp_path, monkeypatch):
    rc, _, _ = _run(tmp_path, monkeypatch, 5)
    assert rc == 0
    rc, _, _ = _run(tmp_path, monkeypatch, 500)
    assert rc == 0


def test_nullout_guard_counts_only_fields_that_were_present():
    """EPA's 2026-10-17 NPL republish blanked STATE_CODE on 84 sites; a
    count-only guard could not see it."""
    import refresh
    prior = [{"id": "A", "state": "AK", "name": "x"}, {"id": "B", "state": None, "name": "y"}]
    now = [{"id": "A", "state": None, "name": "x"}, {"id": "B", "state": None, "name": " "}]
    assert refresh.count_nullouts(prior, now) == {"state": 1, "name": 1}
    assert refresh.count_nullouts(prior, prior) == {}


def test_nullout_limit_is_relative_to_the_fields_prior_coverage():
    """Blanking all 5 values of a field present on 5 of 1,000 records is a
    100% loss of that field, not 0.5% of the file (Codex review, PR #43)."""
    import refresh
    prior = [{"id": str(i), "city": "Lima" if i < 5 else None} for i in range(1000)]
    now = [{"id": str(i)} for i in range(1000)]
    assert refresh.excessive_nullouts(prior, now) == {"city": 5}
    prior = [{"id": str(i), "state": "OH"} for i in range(1000)]
    now = [{"id": str(i), "state": None if i < 5 else "OH"} for i in range(1000)]
    assert refresh.excessive_nullouts(prior, now) == {}  # 0.5% of a fully populated field
