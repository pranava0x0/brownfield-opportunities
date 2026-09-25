"""`--output` must redirect ALL writes of a canonical run, including the diff log.

Observed 2026-09-25: `refresh.py --source superfund-npl --no-cache --output
<scratch>.json` (a dry comparison pull) still treated the run as the canonical
solo refresh, diffed the new records against the empty scratch path, and
overwrote the tracked data/changes.md with a bogus "+1908 −0 ~0 sites" entry.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import refresh


class _OneRecord:
    slug = "superfund-npl"
    source_label = "Test NPL"
    source_url = "https://example.invalid/npl"
    authoritative_inventory = True

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir

    def fetch_records(self, args: argparse.Namespace, use_cache: bool) -> list[dict]:
        return [{"id": "XX0000000001", "name": "Test Site", "program": "superfund",
                 "state": "XX", "lat": 40.0, "lon": -80.0}]


def test_output_override_does_not_touch_the_tracked_diff_log(tmp_path, monkeypatch):
    changes = tmp_path / "changes.md"
    changes.write_text("sentinel — must survive a redirected run\n")
    scratch = tmp_path / "scratch" / "npl-new.json"
    monkeypatch.setattr(refresh.connectors, "get", lambda _slug: _OneRecord)
    monkeypatch.setattr(refresh, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(refresh, "CHANGES_PATH", changes)
    args = argparse.Namespace(fetch_only=False, pretty=False, limit=None, output=scratch)

    rc, _records, _src = refresh._run_one(refresh.CANONICAL_SLUG, args, use_cache=False)

    assert rc == 0
    assert scratch.exists()
    assert changes.read_text() == "sentinel — must survive a redirected run\n"
