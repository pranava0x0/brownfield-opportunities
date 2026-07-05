"""Unit tests for the parcel-owner enrichment connector.

Mocks the three I/O points of fetch_records (_load_sites, existing_records,
http_get_json) — no network. Covers: owner hit, no-parcel tombstone, the
--parcel-limit budget cap, state filtering, and resume-skip of already-resolved
sites.
"""
from __future__ import annotations

import argparse

import pytest

from connectors.parcel_owner import ParcelOwner, STATE_PARCEL_SOURCES


def _args(state=None, limit=200):
    return argparse.Namespace(parcel_state=state, parcel_limit=limit)


def _conn(tmp_path, sites, existing=None, response_for=None):
    c = ParcelOwner(tmp_path)
    c._load_sites = lambda: sites  # type: ignore
    c.existing_records = lambda: (existing or [])  # type: ignore
    # response_for: dict keyed by rounded (lat,lon) → ArcGIS query response
    def fake_get(url, params, use_cache=True, cache_key=None):
        return (response_for or {}).get((cache_key["lat"], cache_key["lon"]), {"features": []})
    c.http_get_json = fake_get  # type: ignore
    return c


_OWNER_RESP = {"features": [{"attributes": {"ownname": "DOMTAR PAPER COMPANY LLC", "gisacres": 200.0, "parno": "123"}}]}


def test_owner_hit_emits_name_and_source(tmp_path):
    sites = [{"id": "NCD1", "program": "superfund", "state": "NC", "lat": 35.5, "lon": -80.5}]
    c = _conn(tmp_path, sites, response_for={(35.5, -80.5): _OWNER_RESP})
    out = c.fetch_records(_args(), use_cache=False)
    assert len(out) == 1
    assert out[0]["current_owner"] == "DOMTAR PAPER COMPANY LLC"
    assert out[0]["current_owner_source"] == STATE_PARCEL_SOURCES["NC"]["source"]


def test_owner_hit_also_emits_parcel_acreage_and_id(tmp_path):
    """The parcel's GIS acreage answers 'how many acres are actually available
    for development' and is the only land-size signal for ACRES sites."""
    sites = [{"id": "NCD1", "program": "superfund", "state": "NC", "lat": 35.5, "lon": -80.5}]
    c = _conn(tmp_path, sites, response_for={(35.5, -80.5): _OWNER_RESP})
    out = c.fetch_records(_args(), use_cache=False)
    assert out[0]["parcel_acreage"] == 200.0
    assert out[0]["parcel_id"] == "123"


def test_parcel_acreage_without_owner_still_emitted(tmp_path):
    """A parcel with acreage but a blank owner name is still a real land-size
    signal — emit parcel_acreage (owner stays null, not a tombstone)."""
    sites = [{"id": "NCD7", "program": "brownfield", "state": "NC", "lat": 35.7, "lon": -80.7}]
    resp = {"features": [{"attributes": {"ownname": "  ", "gisacres": 42.0, "parno": "P7"}}]}
    c = _conn(tmp_path, sites, response_for={(35.7, -80.7): resp})
    out = c.fetch_records(_args(), use_cache=False)
    assert len(out) == 1
    assert out[0].get("current_owner") is None
    assert out[0]["parcel_acreage"] == 42.0
    assert out[0]["parcel_id"] == "P7"


def test_zero_acreage_is_dropped_not_emitted(tmp_path):
    """A 0 / negative gisacres is a bad geometry, not a real parcel size — a
    parcel with 0 acreage and no owner is no signal at all (tombstone)."""
    sites = [{"id": "NCD8", "program": "brownfield", "state": "NC", "lat": 35.8, "lon": -80.8}]
    resp = {"features": [{"attributes": {"ownname": None, "gisacres": 0, "parno": None}}]}
    c = _conn(tmp_path, sites, response_for={(35.8, -80.8): resp})
    out = c.fetch_records(_args(), use_cache=False)
    assert len(out) == 1
    assert out[0].get("parcel_acreage") is None
    assert out[0].get("current_owner") is None


def test_no_parcel_emits_null_tombstone(tmp_path):
    sites = [{"id": "NCD2", "program": "superfund", "state": "NC", "lat": 34.0, "lon": -77.0}]
    c = _conn(tmp_path, sites)  # default response = no features
    out = c.fetch_records(_args(), use_cache=False)
    assert len(out) == 1
    assert out[0]["id"] == "NCD2"
    assert out[0]["current_owner"] is None  # tombstone so we don't re-query forever


def test_uncovered_state_is_skipped(tmp_path):
    sites = [{"id": "WY1", "program": "superfund", "state": "WY", "lat": 43.0, "lon": -108.0}]
    c = _conn(tmp_path, sites)
    out = c.fetch_records(_args(), use_cache=False)
    assert out == []  # WY not in the registry → nothing queried


def test_parcel_limit_caps_new_queries(tmp_path):
    sites = [{"id": f"NC{i}", "program": "superfund", "state": "NC", "lat": 35.0 + i / 100, "lon": -80.0}
             for i in range(5)]
    resp = {(round(35.0 + i / 100, 6), -80.0): _OWNER_RESP for i in range(5)}
    c = _conn(tmp_path, sites, response_for=resp)
    out = c.fetch_records(_args(limit=2), use_cache=False)
    # Only 2 new queries → at most 2 records emitted this run.
    assert len([r for r in out if r.get("current_owner")]) == 2


def test_seeded_owner_is_not_requeried(tmp_path):
    sites = [{"id": "NCD3", "program": "superfund", "state": "NC", "lat": 36.0, "lon": -81.0}]
    existing = [{"id": "NCD3", "program": "superfund",
                 "current_owner": "ALREADY KNOWN INC", "current_owner_source": "x"}]
    # No response registered — if it queried, it'd tombstone-null and overwrite.
    c = _conn(tmp_path, sites, existing=existing)
    out = c.fetch_records(_args(), use_cache=False)
    assert len(out) == 1
    assert out[0]["current_owner"] == "ALREADY KNOWN INC"


def test_seeded_null_owner_is_not_requeried(tmp_path):
    """A null-owner TOMBSTONE from a prior run (serialized as just {id, program}
    by exclude_none) must NOT be re-queried — the no-match is permanent and
    re-querying would re-consume the budget every run. Even though a winning
    response is registered, the skip keeps it a tombstone."""
    sites = [{"id": "NCD6", "program": "superfund", "state": "NC", "lat": 35.5, "lon": -80.5}]
    existing = [{"id": "NCD6", "program": "superfund"}]  # tombstone (current_owner dropped)
    c = _conn(tmp_path, sites, existing=existing, response_for={(35.5, -80.5): _OWNER_RESP})
    out = c.fetch_records(_args(), use_cache=False)
    assert len(out) == 1
    assert out[0].get("current_owner") is None  # stayed a tombstone — not re-queried


def test_seeded_owner_without_acreage_is_upgraded_from_cache(tmp_path):
    """Owner-resolved records from runs before parcel_acreage existed lack it,
    but their parcel response is already cached. The free cache-only upgrade
    pass backfills parcel_acreage without a new query (budget untouched)."""
    sites = [{"id": "NCD9", "program": "superfund", "state": "NC", "lat": 35.5, "lon": -80.5}]
    existing = [{"id": "NCD9", "program": "superfund",
                 "current_owner": "DOMTAR PAPER COMPANY LLC",
                 "current_owner_source": STATE_PARCEL_SOURCES["NC"]["source"]}]
    c = _conn(tmp_path, sites, existing=existing, response_for={(35.5, -80.5): _OWNER_RESP})
    c._cache_exists = lambda *a: True  # type: ignore  # pretend the response is on disk
    out = c.fetch_records(_args(limit=0), use_cache=False)
    assert len(out) == 1
    assert out[0]["current_owner"] == "DOMTAR PAPER COMPANY LLC"  # unchanged
    assert out[0]["parcel_acreage"] == 200.0  # backfilled from cache
    assert out[0]["parcel_id"] == "123"


def test_seeded_tombstone_is_not_upgraded(tmp_path):
    """A null-owner tombstone has no parcel — the acreage-upgrade pass must
    leave it untouched even if a winning response is registered/cached."""
    sites = [{"id": "NCDA", "program": "superfund", "state": "NC", "lat": 35.5, "lon": -80.5}]
    existing = [{"id": "NCDA", "program": "superfund"}]  # tombstone
    c = _conn(tmp_path, sites, existing=existing, response_for={(35.5, -80.5): _OWNER_RESP})
    c._cache_exists = lambda *a: True  # type: ignore
    out = c.fetch_records(_args(), use_cache=False)
    assert len(out) == 1
    assert out[0].get("parcel_acreage") is None
    assert out[0].get("current_owner") is None


def test_seeded_owner_not_upgraded_when_uncached(tmp_path):
    """The upgrade never hits the network — an owner record whose response is
    NOT cached stays acreage-less (no new query spent to fetch it)."""
    sites = [{"id": "NCDB", "program": "superfund", "state": "NC", "lat": 35.5, "lon": -80.5}]
    existing = [{"id": "NCDB", "program": "superfund",
                 "current_owner": "KNOWN INC", "current_owner_source": "x"}]
    c = _conn(tmp_path, sites, existing=existing, response_for={(35.5, -80.5): _OWNER_RESP})
    # _cache_exists defaults to the real check against tmp cache dir → False.
    out = c.fetch_records(_args(), use_cache=False)
    assert out[0].get("parcel_acreage") is None  # untouched, no network fetch


def test_state_filter_restricts_to_one_state(tmp_path):
    sites = [
        {"id": "NCD4", "program": "superfund", "state": "NC", "lat": 35.5, "lon": -80.5},
        {"id": "NCD5", "program": "superfund", "state": "NC", "lat": 35.6, "lon": -80.6},
    ]
    c = _conn(tmp_path, sites, response_for={(35.5, -80.5): _OWNER_RESP})
    out = c.fetch_records(_args(state="nc"), use_cache=False)  # lowercased → NC
    assert any(r.get("current_owner") for r in out)
