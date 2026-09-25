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
