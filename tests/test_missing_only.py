"""Unit tests for `--missing-only` mode.

Covers:
  * Base-class helpers (`merge_records_by_id`, `existing_records`, `existing_ids`)
  * Per-connector integration: the filter is applied BEFORE skip/take, the
    merge happens BEFORE return, and covered sites are not re-fetched.

No network calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from connectors.ai_summary import AiSummary
from connectors.base import Connector
from connectors.epa_echo import EpaEcho
from connectors.epa_superfund_docs import EpaSuperfundDocs
from connectors.infra_proximity import InfraProximity


# ----- base-class helpers ---------------------------------------------------

def test_merge_records_by_id_new_wins_on_collision():
    existing = [{"id": "A", "v": 1}, {"id": "B", "v": 2}]
    new = [{"id": "A", "v": 99}, {"id": "C", "v": 3}]
    merged = Connector.merge_records_by_id(new, existing)
    by_id = {r["id"]: r for r in merged}
    assert by_id["A"]["v"] == 99  # new overrides
    assert by_id["B"]["v"] == 2   # existing preserved
    assert by_id["C"]["v"] == 3   # new added
    assert len(merged) == 3


def test_merge_records_by_id_drops_records_without_id():
    existing = [{"id": "A", "v": 1}, {"v": 2}]
    new = [{"v": 99}, {"id": "B", "v": 3}]
    merged = Connector.merge_records_by_id(new, existing)
    assert {r["id"] for r in merged} == {"A", "B"}


def test_merge_records_by_id_preserves_existing_when_new_is_empty():
    existing = [{"id": "A", "v": 1}]
    merged = Connector.merge_records_by_id([], existing)
    assert merged == existing


def test_existing_records_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)

    class _C(Connector):
        slug = "test-missing-conn"
        source_label = "x"
        source_url = "x"
        def fetch_records(self, args, use_cache):
            return []

    inst = _C(cache_dir=tmp_path / "cache")
    assert inst.existing_records() == []
    assert inst.existing_ids() == set()


def test_existing_records_handles_malformed_json(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)

    class _C(Connector):
        slug = "test-malformed"
        source_label = "x"
        source_url = "x"
        def fetch_records(self, args, use_cache):
            return []

    (tmp_path / "test-malformed.json").write_text("{not valid json")
    inst = _C(cache_dir=tmp_path / "cache")
    assert inst.existing_records() == []
    assert inst.existing_ids() == set()


def test_existing_records_reads_sites_list(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)

    class _C(Connector):
        slug = "test-read"
        source_label = "x"
        source_url = "x"
        def fetch_records(self, args, use_cache):
            return []

    payload = {
        "generated_at": "2026-05-17T00:00:00Z",
        "source": "x",
        "source_url": "x",
        "count": 2,
        "sites": [{"id": "A", "x": 1}, {"id": "B", "x": 2}],
    }
    (tmp_path / "test-read.json").write_text(json.dumps(payload))
    inst = _C(cache_dir=tmp_path / "cache")
    assert inst.existing_records() == payload["sites"]
    assert inst.existing_ids() == {"A", "B"}


# ----- epa-superfund-docs ---------------------------------------------------

def _docs_args(**overrides) -> argparse.Namespace:
    ns = argparse.Namespace(
        docs_skip=0, docs_limit=0, docs_per_site=5, docs_status="F,D",
        missing_only=False, limit=None,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def test_superfund_docs_missing_only_skips_covered_sites(tmp_path, monkeypatch):
    """Sites already in epa-superfund-docs.json must NOT be re-fetched."""
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    existing_payload = {
        "generated_at": "2026-05-01T00:00:00Z", "source": "x", "source_url": "x",
        "count": 1, "sites": [{"id": "EPAID-COVERED", "program": "superfund",
                               "epa_id": "EPAID-COVERED",
                               "documents": [{"doc_id": "old"}]}],
    }
    (tmp_path / "epa-superfund-docs.json").write_text(json.dumps(existing_payload))

    monkeypatch.setattr(
        EpaSuperfundDocs, "_load_superfund_sites",
        lambda self: [
            {"id": "EPAID-COVERED", "epa_id": "EPAID-COVERED",
             "npl_status_code": "F", "acreage": 100, "name": "Covered",
             "profile_url": "https://www.epa.gov/superfund/covered"},
            {"id": "EPAID-NEW", "epa_id": "EPAID-NEW",
             "npl_status_code": "F", "acreage": 50, "name": "New",
             "profile_url": "https://www.epa.gov/superfund/new"},
        ],
    )

    fetched: list[str] = []

    def _no_resolve(self, url, use_cache):  # noqa: ANN001
        fetched.append(url)
        return None  # Force "no SF_SITE_ID" path so we don't hit the doc fetcher

    monkeypatch.setattr(EpaSuperfundDocs, "_resolve_sf_site_id", _no_resolve)

    inst = EpaSuperfundDocs(cache_dir=tmp_path / "cache")
    out = inst.fetch_records(_docs_args(missing_only=True), use_cache=False)

    assert fetched == ["https://www.epa.gov/superfund/new"], \
        "covered site's profile URL must not be fetched"
    out_ids = {r["id"] for r in out}
    assert "EPAID-COVERED" in out_ids, \
        "existing covered record must be preserved in merge"


def test_superfund_docs_missing_only_disabled_runs_full_set(tmp_path, monkeypatch):
    """Without --missing-only, the connector must process every site."""
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    (tmp_path / "epa-superfund-docs.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x", "count": 1,
        "sites": [{"id": "EPAID-COVERED", "program": "superfund",
                   "epa_id": "EPAID-COVERED", "documents": []}],
    }))
    monkeypatch.setattr(
        EpaSuperfundDocs, "_load_superfund_sites",
        lambda self: [
            {"id": "EPAID-COVERED", "epa_id": "EPAID-COVERED",
             "npl_status_code": "F", "acreage": 100, "name": "Covered",
             "profile_url": "https://www.epa.gov/superfund/covered"},
        ],
    )
    fetched: list[str] = []
    monkeypatch.setattr(
        EpaSuperfundDocs, "_resolve_sf_site_id",
        lambda self, url, use_cache: fetched.append(url) or None,
    )

    inst = EpaSuperfundDocs(cache_dir=tmp_path / "cache")
    inst.fetch_records(_docs_args(missing_only=False), use_cache=False)
    assert fetched == ["https://www.epa.gov/superfund/covered"], \
        "with missing_only off, even covered sites must be re-fetched"


# ----- epa-echo -------------------------------------------------------------

def _echo_args(**overrides) -> argparse.Namespace:
    ns = argparse.Namespace(
        echo_skip=0, echo_limit=0, echo_status="F,D",
        missing_only=False, limit=None,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def test_echo_missing_only_skips_covered_sites(tmp_path, monkeypatch):
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    (tmp_path / "epa-echo.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x", "count": 1,
        "sites": [{"id": "EPAID-COVERED", "program": "superfund",
                   "epa_id": "EPAID-COVERED",
                   "enforcement": {"registry_id": "RR1"}}],
    }))
    monkeypatch.setattr(
        EpaEcho, "_load_superfund_sites",
        lambda self: [
            {"id": "EPAID-COVERED", "epa_id": "EPAID-COVERED",
             "npl_status_code": "F", "acreage": 100, "name": "Covered"},
            {"id": "EPAID-NEW", "epa_id": "EPAID-NEW",
             "npl_status_code": "F", "acreage": 50, "name": "New"},
        ],
    )
    looked_up: list[str] = []
    monkeypatch.setattr(
        EpaEcho, "_lookup_facility",
        lambda self, epa_id, use_cache: looked_up.append(epa_id) or None,
    )

    inst = EpaEcho(cache_dir=tmp_path / "cache")
    out = inst.fetch_records(_echo_args(missing_only=True), use_cache=False)
    assert looked_up == ["EPAID-NEW"], \
        "covered site's ECHO lookup must not be re-issued"
    assert "EPAID-COVERED" in {r["id"] for r in out}


# ----- infra-proximity ------------------------------------------------------

def _infra_args(**overrides) -> argparse.Namespace:
    ns = argparse.Namespace(
        missing_only=False, limit=None,
        infra_skip_transmission=False, infra_skip_highway=False,
        infra_skip_rail=False, infra_skip_gas_pipeline=False,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def test_infra_proximity_missing_only_short_circuits_when_all_covered(
    tmp_path, monkeypatch,
):
    """When every loaded site is already in the existing output, the
    connector must skip the ~6-minute index build and return existing as-is."""
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    existing_sites = [
        {"id": "A", "program": "superfund", "transmission_mi": 0.5},
        {"id": "B", "program": "epa-acres", "highway_mi": 2.1},
    ]
    (tmp_path / "infra-proximity.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x",
        "count": 2, "sites": existing_sites,
    }))
    monkeypatch.setattr(
        InfraProximity, "_load_sites",
        lambda self: (
            setattr(self, "_loaded_program_count", 1)
            or iter([
                {"id": "A", "program": "superfund", "lat": 1, "lon": 1},
                {"id": "B", "program": "epa-acres", "lat": 2, "lon": 2},
            ])
        ),
    )

    built_layers: list[str] = []
    monkeypatch.setattr(
        InfraProximity, "_build_index",
        lambda self, layer, cfg, use_cache: built_layers.append(layer),
    )

    inst = InfraProximity(cache_dir=tmp_path / "cache")
    out = inst.fetch_records(_infra_args(missing_only=True), use_cache=False)
    assert built_layers == [], "no index should be built when every site is covered"
    out_ids = {r["id"] for r in out}
    assert out_ids == {"A", "B"}, "existing records must be returned unchanged"


# ----- ai-summary -----------------------------------------------------------

def _ai_args(**overrides) -> argparse.Namespace:
    ns = argparse.Namespace(
        ai_skip=0, ai_limit=0, ai_status="F,D",
        ai_static=True, ai_model="x", ai_max_tokens=100,
        missing_only=False, limit=None,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def test_ai_summary_static_missing_only_skips_covered(tmp_path, monkeypatch):
    """Static-mode summaries are cheap, but `--missing-only` should still
    skip already-summarized sites so users can fill gaps without bouncing
    the whole 1,787-record file."""
    monkeypatch.setattr(Connector, "OUTPUT_DIR", tmp_path)
    (tmp_path / "ai-summary.json").write_text(json.dumps({
        "generated_at": "x", "source": "x", "source_url": "x", "count": 1,
        "sites": [{"id": "A", "program": "superfund",
                   "summary": "old summary",
                   "summary_meta": {"model": "static", "hash": "h",
                                    "generated_at": "x"}}],
    }))
    monkeypatch.setattr(
        AiSummary, "_load_enriched_sites",
        lambda self: [
            {"id": "A", "name": "Covered", "program": "superfund",
             "npl_status_code": "F", "acreage": 100},
            {"id": "B", "name": "New", "program": "superfund",
             "npl_status_code": "F", "acreage": 50},
        ],
    )

    inst = AiSummary(cache_dir=tmp_path / "cache")
    out = inst.fetch_records(_ai_args(missing_only=True), use_cache=False)
    by_id = {r["id"]: r for r in out}
    # A keeps its prior summary (existing wasn't overwritten because A was filtered out);
    # B got a fresh static summary.
    assert by_id["A"]["summary"] == "old summary"
    assert by_id["B"]["summary"] != "old summary"
    assert "B" in by_id


# ----- refresh.py CLI -------------------------------------------------------

def test_refresh_parser_accepts_missing_only_flag():
    """The parser must accept --missing-only globally so any connector can opt in."""
    from refresh import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--source", "epa-superfund-docs", "--missing-only"])
    assert args.missing_only is True


def test_refresh_parser_missing_only_default_false():
    from refresh import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--source", "epa-superfund-docs"])
    assert args.missing_only is False
