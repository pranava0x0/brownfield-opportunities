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


def test_registry_states_are_well_formed():
    """Every registered state must carry the keys the query relies on so a new
    state can't be half-added. NC/MT/WI/NJ/VT/CT/MA are the 2026-06/07 set;
    FL/CO/IA/MN were verified 2026-07-26. acreage_field is optional ONLY for
    owner-only states (IA: the 2017 layer has no usable area field); everywhere
    else it must be present so acreage keeps flowing."""
    required = {"base", "owner_field", "parcel_id_field", "source"}
    assert {"NC", "MT", "WI", "NJ", "VT", "CT", "MA", "FL", "CO", "IA", "MN"} <= set(STATE_PARCEL_SOURCES)
    owner_only_ok = {"IA"}
    for st, src in STATE_PARCEL_SOURCES.items():
        assert required <= set(src), f"{st} missing keys: {required - set(src)}"
        if st not in owner_only_ok:
            assert "acreage_field" in src, f"{st} must carry acreage_field"
        if "acreage_multiplier" in src:
            assert "acreage_field" in src, f"{st}: multiplier without acreage_field"
            assert "acreage_units_field" not in src, \
                f"{st}: fixed multiplier and per-record units are mutually exclusive"
        assert src["base"].startswith("https://") and src["base"].rstrip("/")[-1].isdigit(), \
            f"{st} base must be an https layer URL ending in a layer index"


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


def test_mixed_unit_acreage_converts_sqft_to_acres(tmp_path):
    """MA reports LOT_SIZE in per-record LOT_UNITS ('Acres' | 'Sq. Ft.'). A
    square-feet value must be converted to acres; an 'Acres' value passes
    through; an UNKNOWN unit yields no acreage (never a wrong number)."""
    src = STATE_PARCEL_SOURCES["MA"]
    def feat(size, units):
        return {"features": [{"attributes": {"OWNER1": "ACME LLC", "LOT_SIZE": size,
                                             "LOT_UNITS": units, "LOC_ID": "M_1_2"}}]}
    # 43,560 sq ft == 1 acre
    sites = [{"id": "MA1", "program": "brownfield", "state": "MA", "lat": 42.3, "lon": -71.1}]
    c = _conn(tmp_path, sites, response_for={(42.3, -71.1): feat(43560, "Sq. Ft.")})
    out = c.fetch_records(_args(), use_cache=False)
    assert out[0]["parcel_acreage"] == 1.0
    # 'Acres' passes through
    c = _conn(tmp_path, sites, response_for={(42.3, -71.1): feat(5.5, "Acres")})
    assert c.fetch_records(_args(), use_cache=False)[0]["parcel_acreage"] == 5.5
    # unknown unit → no acreage, but owner still emitted
    c = _conn(tmp_path, sites, response_for={(42.3, -71.1): feat(100, "Hectares")})
    r = c.fetch_records(_args(), use_cache=False)[0]
    assert r.get("parcel_acreage") is None and r["current_owner"] == "ACME LLC"


def test_fixed_multiplier_converts_fl_sqft_to_acres(tmp_path):
    """FL's LND_SQFOOT is ALWAYS square feet (DOR NAL convention) with no
    per-record units column — the source-level acreage_multiplier must convert
    it. 43,560 sq ft == 1 acre."""
    def feat(sqft):
        return {"features": [{"attributes": {"OWN_NAME": "GSI OPA LOCKA OWNER LLC",
                                             "LND_SQFOOT": sqft, "PARCEL_ID": "0821280040031"}}]}
    sites = [{"id": "FL1", "program": "brownfield", "state": "FL", "lat": 25.89, "lon": -80.24}]
    c = _conn(tmp_path, sites, response_for={(25.89, -80.24): feat(43560)})
    out = c.fetch_records(_args(), use_cache=False)
    assert out[0]["parcel_acreage"] == 1.0
    assert out[0]["current_owner"] == "GSI OPA LOCKA OWNER LLC"
    assert out[0]["current_owner_source"] == STATE_PARCEL_SOURCES["FL"]["source"]
    # half an acre, rounded to 2dp
    c = _conn(tmp_path, sites, response_for={(25.89, -80.24): feat(21780)})
    assert c.fetch_records(_args(), use_cache=False)[0]["parcel_acreage"] == 0.5


def test_owner_only_state_emits_owner_without_acreage(tmp_path):
    """IA has no usable acreage field (Web-Mercator Shape__Area only) — the
    registry row omits acreage_field and the record must still emit the owner
    with the vintage-carrying source label, and no parcel_acreage."""
    resp = {"features": [{"attributes": {"DEEDHOLDER": "IOWA CONCRETE PRODS CO",
                                         "STATEPARID": "77-32000524002002"}}]}
    sites = [{"id": "IA1", "program": "superfund", "state": "IA", "lat": 41.56, "lon": -93.72}]
    c = _conn(tmp_path, sites, response_for={(41.56, -93.72): resp})
    out = c.fetch_records(_args(), use_cache=False)
    assert out[0]["current_owner"] == "IOWA CONCRETE PRODS CO"
    assert "parcel_acreage" not in out[0]
    assert "2017" in out[0]["current_owner_source"]


def test_api_error_skips_site_without_tombstone_or_crash(tmp_path):
    """An ArcGIS error payload (http_get_json raises RuntimeError) on one site
    must not crash the run OR tombstone the site (it stays retryable) — the
    2026-07-26 FL Davie Landfill crash. Later sites still process."""
    sites = [
        {"id": "FL_BAD", "program": "superfund", "state": "FL", "lat": 26.07, "lon": -80.34},
        {"id": "FL_OK", "program": "brownfield", "state": "FL", "lat": 25.89, "lon": -80.24},
    ]
    ok = {"features": [{"attributes": {"OWN_NAME": "ACME", "LND_SQFOOT": 43560,
                                       "PARCEL_ID": "P1"}}]}
    c = _conn(tmp_path, sites)
    def fake_get(url, params, use_cache=True, cache_key=None):
        if cache_key["lat"] == 26.07:
            raise RuntimeError("API error: code 400 Invalid query parameters")
        return ok
    c.http_get_json = fake_get  # type: ignore
    out = c.fetch_records(_args(), use_cache=False)
    ids = {r["id"] for r in out}
    assert "FL_OK" in ids          # the run continued past the error
    assert "FL_BAD" not in ids     # no tombstone — retryable next run


def test_consecutive_api_errors_drop_state_not_run(tmp_path):
    """15 consecutive API errors in one state drop THAT state for the run
    (systemically-broken config guard) while other states keep processing."""
    fl = [{"id": f"FL{i}", "program": "brownfield", "state": "FL",
           "lat": 26.0 + i / 1000, "lon": -80.3} for i in range(20)]
    co = [{"id": "CO_OK", "program": "superfund", "state": "CO", "lat": 39.82, "lon": -104.9}]
    ok = {"features": [{"attributes": {"owner": "CITY OF DENVER", "landAcres": 2.0,
                                       "parcel_id": "C1"}}]}
    calls = {"fl": 0}
    c = _conn(tmp_path, fl + co)
    def fake_get(url, params, use_cache=True, cache_key=None):
        if "Florida" in url:
            calls["fl"] += 1
            raise RuntimeError("API error: code 400")
        return ok
    c.http_get_json = fake_get  # type: ignore
    out = c.fetch_records(_args(), use_cache=False)
    assert calls["fl"] == 15                      # dropped at the streak limit
    assert {r["id"] for r in out} == {"CO_OK"}    # CO unaffected


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
