"""Tests for SuperfundNPL._dedupe_status_a()."""
from __future__ import annotations

from connectors.superfund_npl import SuperfundNPL


def _r(epa_id: str, name: str, status: str) -> dict:
    return {"epa_id": epa_id, "name": name, "npl_status_code": status, "parent_epa_id": None}


def test_child_dropped_when_parent_present():
    parent = _r("AAA", "Big Refinery Site", "F")
    child = _r("AAA-OU1", "Big Refinery Site OU1", "A")
    out = SuperfundNPL._dedupe_status_a([parent, child])
    assert out == [parent]


def test_orphan_child_kept():
    """Status-A row with no parent in dataset is kept (no silent data loss)."""
    orphan = _r("XXX", "Orphan Sub-Site", "A")
    out = SuperfundNPL._dedupe_status_a([orphan])
    assert out == [orphan]
    assert orphan["parent_epa_id"] is None


def test_non_a_records_unaffected():
    a = _r("A", "Site A", "F")
    b = _r("B", "Site B", "D")
    c = _r("C", "Site C", "P")
    out = SuperfundNPL._dedupe_status_a([a, b, c])
    assert out == [a, b, c]


def test_self_named_status_a_not_treated_as_child_of_itself():
    """Status-A site with a unique name (no parent prefix-match) is kept."""
    rec = _r("XYZ", "Unique Sub-Site Name", "A")
    out = SuperfundNPL._dedupe_status_a([rec])
    assert out == [rec]


def test_child_records_parent_epa_id():
    parent = _r("PPP", "Parent Plant", "F")
    child = _r("PPP-OU2", "Parent Plant OU2", "A")
    SuperfundNPL._dedupe_status_a([parent, child])
    assert child["parent_epa_id"] == "PPP"
