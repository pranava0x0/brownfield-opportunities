"""An upstream 200/empty response must not erase a program inventory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import refresh


class _EmptyConnector:
    slug = "empty"
    source_label = "Empty test source"
    source_url = "https://example.invalid/empty"
    authoritative_inventory = True

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir

    def fetch_records(self, args: argparse.Namespace, use_cache: bool) -> list[dict]:
        return []


class _EmptyEnrichment(_EmptyConnector):
    authoritative_inventory = False


def _args() -> argparse.Namespace:
    return argparse.Namespace(fetch_only=False, pretty=False, limit=None, output=None)


def test_empty_authoritative_inventory_aborts_before_write(tmp_path, monkeypatch):
    output = tmp_path / "inventory.json"
    output.write_text('{"sentinel":"keep"}')
    monkeypatch.setattr(refresh.connectors, "get", lambda _slug: _EmptyConnector)
    monkeypatch.setattr(refresh, "CACHE_DIR", tmp_path / "cache")

    rc, records, _source = refresh._run_one(
        "epa-acres", _args(), use_cache=False, output_override=output
    )

    assert rc == 1
    assert records is None
    assert output.read_text() == '{"sentinel":"keep"}'


def test_empty_enrichment_can_create_a_first_run_payload(tmp_path, monkeypatch):
    output = tmp_path / "enrichment.json"
    monkeypatch.setattr(refresh.connectors, "get", lambda _slug: _EmptyEnrichment)
    monkeypatch.setattr(refresh, "CACHE_DIR", tmp_path / "cache")

    rc, records, _source = refresh._run_one(
        "test-enrichment", _args(), use_cache=False, output_override=output
    )

    assert rc == 0
    assert records == []
    assert output.exists()


def test_empty_enrichment_does_not_blank_a_populated_file(tmp_path, monkeypatch):
    """An outage that yields zero records must not erase existing enrichment.

    Observed for real: the 2026-08-24 and 2026-09-07 `--all` cron runs both
    logged `[ai-summary] no records normalized; writing empty payload` because
    ANTHROPIC_API_KEY is unset in CI. Harmless only while the commit step is
    skipped — re-enabling auto-commit would publish the blanked file.
    """
    output = tmp_path / "enrichment.json"
    output.write_text(json.dumps({
        "generated_at": "2026-01-01T00:00:00Z",
        "source": "prior run",
        "source_url": "https://example.invalid/prior",
        "count": 2,
        "sites": [{"id": "A"}, {"id": "B"}],
    }))
    monkeypatch.setattr(refresh.connectors, "get", lambda _slug: _EmptyEnrichment)
    monkeypatch.setattr(refresh, "CACHE_DIR", tmp_path / "cache")

    rc, records, _source = refresh._run_one(
        "test-enrichment", _args(), use_cache=False, output_override=output
    )

    assert rc == 1
    assert records is None
    assert json.loads(output.read_text())["count"] == 2


def test_empty_enrichment_may_overwrite_an_already_empty_file(tmp_path, monkeypatch):
    """A zero-record file is not data worth protecting — the write stays legal."""
    output = tmp_path / "enrichment.json"
    output.write_text(json.dumps({
        "generated_at": "2026-01-01T00:00:00Z",
        "source": "prior run",
        "source_url": "https://example.invalid/prior",
        "count": 0,
        "sites": [],
    }))
    monkeypatch.setattr(refresh.connectors, "get", lambda _slug: _EmptyEnrichment)
    monkeypatch.setattr(refresh, "CACHE_DIR", tmp_path / "cache")

    rc, records, _source = refresh._run_one(
        "test-enrichment", _args(), use_cache=False, output_override=output
    )

    assert rc == 0
    assert records == []


def test_unreadable_prior_file_does_not_block_the_write(tmp_path, monkeypatch):
    """A corrupt prior payload must not wedge the connector — fail open, warn."""
    output = tmp_path / "enrichment.json"
    output.write_text("{ not json")
    monkeypatch.setattr(refresh.connectors, "get", lambda _slug: _EmptyEnrichment)
    monkeypatch.setattr(refresh, "CACHE_DIR", tmp_path / "cache")

    rc, records, _source = refresh._run_one(
        "test-enrichment", _args(), use_cache=False, output_override=output
    )

    assert rc == 0
    assert records == []
