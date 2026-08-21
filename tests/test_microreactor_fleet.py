"""Unit tests for scripts/build_microreactor_fleet.py and its emitted file.

The fleet is a CURATED overlay, not a connector output, so `schema.py` never
sees it and `refresh.py` never validates it. These tests are the only thing
standing between a typo and a silently-wrong public dataset — they assert the
structural invariants the build script's own `validate()` enforces, plus the
two rules the source projects live by:

  * every row carries a source (a row without one must not have been written)
  * a megawatt sits in exactly one evidence band, and bands are never summed
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_microreactor_fleet.py"
OUT = ROOT / "docs" / "data" / "microreactor-fleet.json"
AP1000 = ROOT / "docs" / "data" / "ap1000-sites.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_microreactor_fleet", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


@pytest.fixture(scope="module")
def payload() -> dict:
    assert OUT.exists(), f"{OUT} missing — run python3 {SCRIPT.relative_to(ROOT)}"
    return json.loads(OUT.read_text())


# -- Structural invariants --------------------------------------------------

def test_ids_are_unique(payload):
    for key in ("vendors", "commitments"):
        ids = [r["id"] for r in payload[key]]
        assert len(ids) == len(set(ids)), f"duplicate id in {key}"


def test_every_row_carries_a_source(payload):
    """A row with no located source was never supposed to be written."""
    for key in ("vendors", "commitments"):
        for row in payload[key]:
            assert row.get("sources"), f"{key}/{row['id']} has no source"
            for src in row["sources"]:
                assert src["url"].startswith("https://"), f"{row['id']}: {src['url']}"
                assert src["label"], f"{row['id']}: source with no label"


def test_bands_come_from_the_declared_ladder(payload):
    known = {b["band"] for b in payload["evidence_bands"]}
    for key in ("vendors", "commitments"):
        for row in payload[key]:
            assert row["band"] in known, f"{key}/{row['id']}: unknown band {row['band']!r}"


def test_evidence_bands_are_ordered_strongest_first(payload):
    """Render order reads this list directly — a reshuffle would invert the
    whole visual ranking without any other symptom."""
    assert [b["band"] for b in payload["evidence_bands"]] == [
        "operational", "construction", "doe-authorized", "review",
        "contracted", "framework",
    ]


def test_every_commitment_vendor_id_resolves(payload):
    vendor_ids = {v["id"] for v in payload["vendors"]}
    for c in payload["commitments"]:
        vid = c.get("vendor_id")
        assert vid is None or vid in vendor_ids, f"{c['id']}: dangling vendor_id {vid!r}"


def test_coordinates_are_a_pair_or_absent(payload):
    """Half a coordinate would place a marker at the equator."""
    for c in payload["commitments"]:
        assert (c["lat"] is None) == (c["lon"] is None), f"{c['id']}: half a coordinate"
        if c["lat"] is not None:
            assert -90 <= c["lat"] <= 90 and -180 <= c["lon"] <= 180, c["id"]


# -- The Janus coordinate join ----------------------------------------------

def test_janus_sites_take_coordinates_from_ap1000_file(payload):
    """The nine Army installations must not carry hand-typed coordinates —
    they join from ap1000-sites.json so the two nuclear surfaces can never
    disagree about where Fort Wainwright is."""
    ap = {s["id"]: s for s in json.loads(AP1000.read_text())["sites"]}
    janus = [c for c in payload["commitments"] if c.get("janus")]
    assert len(janus) == 9, f"expected 9 Janus rows, got {len(janus)}"
    for c in janus:
        ref = c["ap1000_ref"]
        assert ref in ap, f"{c['id']}: unknown ap1000 ref {ref!r}"
        assert c["lat"] == ap[ref]["lat"]
        assert c["lon"] == ap[ref]["lon"]
        assert ap[ref]["janus_site"] is True, f"{ref} is not flagged janus_site upstream"


def test_join_fails_loud_on_an_unknown_installation(mod):
    """A silently-unmapped Janus site would just vanish from the overlay."""
    with pytest.raises(KeyError):
        mod.join_ap1000_coords([
            {"id": "janus-nowhere", "ap1000_site_id": "fort-nonexistent-zz",
             "lat": None, "lon": None},
        ])


# -- The band-summing rule --------------------------------------------------

def test_committed_mwe_is_reported_per_band_never_as_a_total(payload):
    """Summing an announced MOU with an executed contract is the exact error
    the band ladder exists to prevent, so the payload must expose a mapping
    and never a single scalar."""
    mwe = payload["committed_mwe_by_band"]
    assert isinstance(mwe, dict) and mwe
    assert "total" not in mwe and "committed_mwe" not in payload
    for band, v in mwe.items():
        assert band in {b["band"] for b in payload["evidence_bands"]}
        assert v > 0


def test_committed_mwe_matches_the_rows_it_claims_to_sum(payload):
    expected: dict[str, float] = {}
    for c in payload["commitments"]:
        if not c.get("microreactor") or c.get("mwe") is None:
            continue
        expected[c["band"]] = round(expected.get(c["band"], 0.0) + c["mwe"], 1)
    assert payload["committed_mwe_by_band"] == expected


def test_smr_scale_comparators_are_excluded_from_microreactor_counts(payload):
    """Doicești is a six-module NuScale plant kept as a market comparator. If
    it ever leaks into the microreactor counts the headline is wrong by an
    order of magnitude."""
    comparators = [c for c in payload["commitments"] if not c.get("microreactor")]
    assert comparators, "the comparator rows disappeared — check the flag"
    for c in comparators:
        assert c["mwe"] is None or c["id"] not in {
            x["id"] for x in payload["commitments"] if x.get("microreactor")
        }
    micro = [c for c in payload["commitments"] if c.get("microreactor")]
    assert payload["counts"]["commitments_microreactor"] == len(micro)
    assert payload["counts"]["commitments"] == len(payload["commitments"])


# -- Counts and the demand ladder -------------------------------------------

def test_counts_match_the_rows(payload):
    c = payload["counts"]
    assert c["vendors"] == len(payload["vendors"])
    assert c["commitments"] == len(payload["commitments"])
    assert c["commitments_mapped"] == sum(1 for x in payload["commitments"] if x["lat"] is not None)
    assert c["sectors"] == len(payload["sectors"])
    assert c["sector_loads"] == sum(len(s["loads"]) for s in payload["sectors"])
    assert c["vendors_microreactor_band"] == sum(
        1 for v in payload["vendors"] if not v.get("adjacent")
    )


def test_adjacency_is_labelled_not_hidden(payload):
    """Oklo's Aurora outgrew the microreactor band. Dropping it would lose the
    Eielson award; including it unlabelled would overstate the band."""
    adjacent = [v for v in payload["vendors"] if v.get("adjacent")]
    assert len(adjacent) == 1
    assert adjacent[0]["id"] == "oklo"
    assert adjacent[0]["adjacent_note"], "an adjacency with no explanation is just an error"


def test_load_fit_follows_the_band_edge(payload, mod):
    """`fit` is derived, not typed — a load is 'full' iff one unit covers its
    whole upper bound."""
    for sec in payload["sectors"]:
        for load in sec["loads"]:
            expected = "full" if load["mw_high"] <= mod.MICRO_BAND_MWE else "block"
            assert load["fit"] == expected, f"{load['label']}: {load['fit']}"
            assert load["mw_low"] <= load["mw_high"]


# -- Determinism ------------------------------------------------------------

def test_build_is_deterministic(mod, tmp_path, monkeypatch, payload):
    """Re-running must reproduce the shipped file byte-for-byte — otherwise a
    refresh produces a spurious diff and nobody can tell a real change from
    reformatting."""
    out = tmp_path / "microreactor-fleet.json"
    monkeypatch.setattr(mod, "OUT_PATH", out)
    mod.main()
    assert json.loads(out.read_text()) == payload
    assert out.read_text() == OUT.read_text()
