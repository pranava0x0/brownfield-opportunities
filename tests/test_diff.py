"""Tests for diff.diff_payloads() + render_markdown()."""
from __future__ import annotations

from diff import diff_payloads, render_markdown, short_summary


def _site(epa_id: str, **kw) -> dict:
    base = {
        "epa_id": epa_id,
        "name": f"Site {epa_id}",
        "acreage": 100.0,
        "npl_status_code": "F",
        "npl_status": "Currently on the Final NPL",
        "state": "IL",
    }
    base.update(kw)
    return base


def test_no_prior_treats_all_as_added():
    current = {"sites": [_site("A"), _site("B")]}
    diff = diff_payloads(None, current)
    assert len(diff["added"]) == 2
    assert diff["removed"] == []
    assert diff["changed"] == []


def test_added_and_removed():
    prior = {"sites": [_site("A"), _site("B")]}
    current = {"sites": [_site("B"), _site("C")]}
    diff = diff_payloads(prior, current)
    assert [s["epa_id"] for s in diff["added"]] == ["C"]
    assert [s["epa_id"] for s in diff["removed"]] == ["A"]
    assert diff["changed"] == []


def test_acreage_change_detected():
    prior = {"sites": [_site("A", acreage=100.0)]}
    current = {"sites": [_site("A", acreage=150.0)]}
    diff = diff_payloads(prior, current)
    assert len(diff["changed"]) == 1
    assert diff["changed"][0]["deltas"]["acreage"] == (100.0, 150.0)


def test_status_change_detected():
    prior = {"sites": [_site("A", npl_status_code="F", npl_status="Final NPL")]}
    current = {"sites": [_site("A", npl_status_code="D", npl_status="Deleted")]}
    diff = diff_payloads(prior, current)
    assert "npl_status_code" in diff["changed"][0]["deltas"]
    assert "npl_status" in diff["changed"][0]["deltas"]


def test_unchanged_site_not_in_changed():
    prior = {"sites": [_site("A")]}
    current = {"sites": [_site("A")]}
    diff = diff_payloads(prior, current)
    assert diff["changed"] == []


def test_short_summary_format():
    diff = {"added": [1, 2], "removed": [3], "changed": []}
    assert short_summary(diff) == "+2 −1 ~0 sites"


def test_render_markdown_no_changes():
    diff = diff_payloads({"sites": [_site("A")]}, {"sites": [_site("A")]})
    md = render_markdown(diff, "2026-04-27T12:00:00Z")
    assert "_No changes._" in md


def test_render_markdown_includes_added_sites():
    diff = diff_payloads(None, {"sites": [_site("A", acreage=42.5)]})
    md = render_markdown(diff, "2026-04-27T12:00:00Z")
    assert "Added (1)" in md
    assert "42.5 ac" in md
    assert "`A`" in md
