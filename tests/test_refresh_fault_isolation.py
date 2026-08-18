"""`refresh.py --all` must not let one connector's failure kill the rest.

The scheduled "Refresh site data" workflow failed 13 consecutive runs between
2026-05-25 and 2026-08-17. Three *different* triggers were confirmed across
those logs — an Overpass 504 in `infra_proximity`, an `echodata.epa.gov`
ReadTimeout in `epa_echo`, and an ArcGIS `ConnectionResetError` in
`infra_proximity._build_index` — which is what ruled out "one flaky host" and
pointed at the orchestration instead.

The `--all` loop already threaded a per-connector return code. The defect was
narrower: `_run_one` *raised* rather than returning nonzero, so the exception
sailed straight past the loop and out of `main()`, taking every connector still
queued behind it with it.

Fail-loud is preserved deliberately: the traceback is logged and the run still
exits nonzero. Isolation buys the remaining connectors their turn; it does not
quietly turn a broken run green.
"""
from __future__ import annotations

import logging

import pytest

import refresh


class _FakeConnector:
    """Minimal stand-in for a registered connector class."""

    source_label = "fake"
    source_url = "https://example.invalid/fake"
    run_order = 100


@pytest.fixture
def fake_registry(monkeypatch):
    """Replace the connector registry with three ordered no-op connectors."""
    slugs = ["alpha", "bravo", "charlie"]
    monkeypatch.setattr(refresh.connectors, "names", lambda: list(slugs))
    monkeypatch.setattr(refresh.connectors, "get", lambda _slug: _FakeConnector)
    return slugs


def _drive(monkeypatch, run_one, argv=("refresh.py", "--all", "--fetch-only")):
    """Run `main()` with `_run_one` stubbed. `--fetch-only` blocks disk writes."""
    monkeypatch.setattr("sys.argv", list(argv))
    monkeypatch.setattr(refresh, "_run_one", run_one)
    return refresh.main()


def test_one_connector_raising_does_not_stop_the_rest(fake_registry, monkeypatch):
    """The connector after the failure still gets its turn."""
    attempted: list[str] = []

    def run_one(slug, args, use_cache, output_override=None):
        attempted.append(slug)
        if slug == "bravo":
            raise ConnectionError("Connection reset by peer")
        return 0, [{"id": slug}], "fake"

    _drive(monkeypatch, run_one)

    # Before the fix this was ["alpha", "bravo"] — charlie never ran.
    assert attempted == ["alpha", "bravo", "charlie"]


def test_isolated_failure_still_returns_nonzero(fake_registry, monkeypatch):
    """Isolation must not disguise a broken run as a healthy one."""
    def run_one(slug, args, use_cache, output_override=None):
        if slug == "bravo":
            raise ConnectionError("Connection reset by peer")
        return 0, [{"id": slug}], "fake"

    assert _drive(monkeypatch, run_one) == 1


def test_all_succeeding_returns_zero(fake_registry, monkeypatch):
    """Control: the isolation path must not poison a clean run."""
    def run_one(slug, args, use_cache, output_override=None):
        return 0, [{"id": slug}], "fake"

    assert _drive(monkeypatch, run_one) == 0


def test_every_connector_failing_is_reported_not_swallowed(fake_registry, monkeypatch):
    """All three are attempted, and the run still fails."""
    attempted: list[str] = []

    def run_one(slug, args, use_cache, output_override=None):
        attempted.append(slug)
        raise TimeoutError("read timed out")

    assert _drive(monkeypatch, run_one) == 1
    assert attempted == ["alpha", "bravo", "charlie"]


def test_nonzero_return_code_is_preserved_alongside_isolation(fake_registry, monkeypatch):
    """A connector that *returns* 1 is still honoured when another raises."""
    def run_one(slug, args, use_cache, output_override=None):
        if slug == "alpha":
            return 1, None, "fake"        # graceful failure (e.g. empty canonical)
        if slug == "bravo":
            raise ConnectionError("boom")  # hard failure
        return 0, [{"id": slug}], "fake"

    assert _drive(monkeypatch, run_one) == 1


def test_failure_logs_the_slug_and_a_traceback(fake_registry, monkeypatch, caplog):
    """`log.exception` — the operator must be able to see which host broke."""
    def run_one(slug, args, use_cache, output_override=None):
        if slug == "bravo":
            raise ConnectionError("Connection reset by peer")
        return 0, [{"id": slug}], "fake"

    with caplog.at_level(logging.ERROR, logger="refresh"):
        _drive(monkeypatch, run_one)

    assert "bravo" in caplog.text
    assert "Connection reset by peer" in caplog.text   # traceback body, not just the slug
    assert "ConnectionError" in caplog.text


def test_keyboard_interrupt_still_aborts_the_run(fake_registry, monkeypatch):
    """`except Exception` must not trap operator cancellation."""
    attempted: list[str] = []

    def run_one(slug, args, use_cache, output_override=None):
        attempted.append(slug)
        if slug == "bravo":
            raise KeyboardInterrupt
        return 0, [{"id": slug}], "fake"

    with pytest.raises(KeyboardInterrupt):
        _drive(monkeypatch, run_one)

    assert attempted == ["alpha", "bravo"]  # charlie correctly never ran


def test_single_source_runs_are_unaffected(monkeypatch):
    """`--source X` keeps propagating — isolation is scoped to `--all`."""
    def run_one(slug, args, use_cache, output_override=None):
        raise ConnectionError("boom")

    with pytest.raises(ConnectionError):
        _drive(monkeypatch, run_one,
               argv=("refresh.py", "--source", "superfund-npl", "--fetch-only"))
