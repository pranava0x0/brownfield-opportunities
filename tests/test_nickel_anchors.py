"""Unit tests for the curated nickel supply-chain anchor catalog.

The catalog is small and hand-written, so the guards here are about the two
things that go wrong with curated data: a coordinate that came from nowhere,
and a row that drifts out of the vocabulary its consumers iterate.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "nickel-anchors.json"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_nickel_anchors", str(ROOT / "scripts" / "build_nickel_anchors.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return json.loads(OUT.read_text())["sites"]


def test_every_row_declares_exactly_one_coordinate_source():
    """A row carries either an explicit lat/lon from a source that located the
    facility, or a locality resolved from the Census Gazetteer. Never both,
    and never neither — the alternative was typing town coordinates from
    memory, which is fabrication that looks like a plausible number."""
    mod = _load_builder()
    for raw in mod.ANCHORS:
        has_site = "lat" in raw and "lon" in raw
        has_locality = "locality" in raw
        assert has_site != has_locality, (
            f"{raw['id']} must declare exactly one of lat/lon or locality")


def test_site_precision_is_never_claimed_for_a_locality_row(rows):
    """coord_precision is load-bearing and must not be quietly upgraded: a
    locality row is a Census place internal point, good to a few miles, and no
    surface may render it as a facility coordinate."""
    for r in rows:
        if r.get("locality"):
            assert r["coord_precision"] == "locality", r["id"]
        else:
            assert r["coord_precision"] == "site", r["id"]
            assert r.get("locality") is None


def test_every_row_carries_a_resolving_citation_and_an_audit_stamp(rows):
    """The coal-conversions curated-provenance contract, applied here."""
    for r in rows:
        assert r["source_url"].startswith("https://"), r["id"]
        assert len(r["verified_at"]) == 10, r["id"]
        assert r["note"].strip(), r["id"]


def test_every_kind_is_routed_to_a_scored_distance_or_deliberately_not():
    """The connector rolls anchor kinds up into three scored distances. A new
    kind that lands in neither KIND_GROUPS nor the refinery set contributes to
    nothing and would be silently invisible — the UAT-007 drift-safe-iteration
    rule, applied to a vocabulary instead of a legend."""
    from connectors.nickel_anchor_proximity import KIND_GROUPS
    import schema

    declared = set(schema.NickelAnchor.model_fields["kind"].annotation.__args__)
    grouped = {k for kinds in KIND_GROUPS.values() for k in kinds}
    # The two refinery kinds are deliberately ungrouped: they are map context
    # and precedent, not an input a site's score should move on.
    ungrouped_by_design = {"refinery_planned", "refinery_historic"}
    assert grouped | ungrouped_by_design == declared, (
        f"unrouted anchor kinds: {declared - grouped - ungrouped_by_design}")


def test_the_only_former_us_nickel_refinery_is_in_the_catalog(rows):
    """Port Nickel at Braithwaite, Louisiana operated as a nickel-cobalt
    refinery from 1958 to 2000 and its 387-acre core tract is currently for
    sale. It is the single most literal reuse candidate the research found, so
    its absence would be a real gap rather than a stylistic one."""
    hit = [r for r in rows if r["kind"] == "refinery_historic"]
    assert hit, "no historic refinery row"
    assert any("Port Nickel" in r["name"] for r in hit)
    assert all(r["coord_precision"] == "site" for r in hit)


def test_ids_are_unique(rows):
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
