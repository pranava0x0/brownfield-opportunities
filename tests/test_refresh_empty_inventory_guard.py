"""An upstream 200/empty response must not erase a program inventory."""
from __future__ import annotations

import argparse
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
