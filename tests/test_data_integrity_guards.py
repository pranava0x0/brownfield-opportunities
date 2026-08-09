"""Regression guards for the defects found by the 2026-08-09 corpus validation.

Each test here corresponds to a row in `issues.md` dated 2026-08-09. They are
grouped in one file because they share a theme: the pipeline validated every
record in isolation but never the properties that only exist across records,
or that distinguish "unknown" from "zero".
"""
from __future__ import annotations

import argparse
import socket

import pytest

from connectors.base import prefer_ipv4
from connectors.superfund_npl import SuperfundNPL
from refresh import assert_unique_ids


# --------------------------------------------------------------------------
# Duplicate ids
# --------------------------------------------------------------------------

class TestUniqueIdGuard:
    """`refresh.py` must refuse to write a record set with a repeated id."""

    def test_accepts_unique_ids(self):
        assert_unique_ids("t", [{"id": "A"}, {"id": "B"}, {"id": "C"}])

    def test_accepts_empty(self):
        assert_unique_ids("t", [])

    def test_rejects_duplicate(self):
        with pytest.raises(ValueError, match="duplicate ids"):
            assert_unique_ids("t", [{"id": "A"}, {"id": "B"}, {"id": "A"}])

    def test_error_names_the_offender_and_the_counts(self):
        """The message has to be actionable without re-running the validator."""
        with pytest.raises(ValueError) as exc:
            assert_unique_ids("dod-fuds", [{"id": "FUDS-H09PT0002"}] * 2 + [{"id": "X"}])
        msg = str(exc.value)
        assert "dod-fuds" in msg
        assert "FUDS-H09PT0002 x2" in msg
        assert "3 records, 2 unique" in msg

    def test_reports_every_distinct_duplicate(self):
        with pytest.raises(ValueError) as exc:
            assert_unique_ids("t", [{"id": "A"}, {"id": "A"}, {"id": "B"}, {"id": "B"}])
        assert "A x2" in str(exc.value)
        assert "B x2" in str(exc.value)

    def test_triple_occurrence_counted_correctly(self):
        with pytest.raises(ValueError, match=r"A x3"):
            assert_unique_ids("t", [{"id": "A"}] * 3)


class TestFudsDeduplication:
    """dod-fuds drops a repeated layer-1 property instead of emitting it twice."""

    def _feature(self, prop_id: str):
        return {
            "attributes": {
                "DODFUDSPROPERTYIDPK": prop_id,
                "FEATURENAME": "U.S. NAVAL REPAIR FAC",
                "STATE": "pw",
                "ELIGIBILITY": "Eligible",
                "EPAREGION": "Region 9",
                "LATITUDE": 6.988333,
                "LONGITUDE": 134.221667,
            },
            "geometry": {"x": 134.221667, "y": 6.988333},
        }

    def test_repeated_property_id_yields_one_record(self, monkeypatch, tmp_path):
        from connectors import dod_fuds

        conn = dod_fuds.DodFuds(cache_dir=tmp_path)
        feats = [self._feature("H09PT0002"), self._feature("H09PT0002"),
                 self._feature("H09PT0003")]
        monkeypatch.setattr(conn, "_fetch_points", lambda *a, **k: feats)
        monkeypatch.setattr(conn, "_fetch_polygon_join", lambda *a, **k: ({}, {}))

        args = argparse.Namespace(fuds_state=None, fuds_eligible_only=False,
                                  fuds_polygons=False, limit=None)
        records = conn.fetch_records(args, use_cache=False)

        ids = [r["id"] for r in records]
        assert ids.count("FUDS-H09PT0002") == 1
        assert len(ids) == len(set(ids))
        # And the output must survive the driver's own guard.
        assert_unique_ids("dod-fuds", records)


# --------------------------------------------------------------------------
# Zero acreage means unknown, not zero
# --------------------------------------------------------------------------

class TestZeroAcreageBecomesNull:
    """A collapsed polygon must yield None, never 0.0.

    0.0 is a claim of no land: it sorts as the smallest site and feeds 0 into
    the acreage component of all three scoring lenses, whereas None correctly
    leaves the site unscored on land.
    """

    def _feature(self, rings, units=None, area=None):
        return {
            "attributes": {
                "EPA_ID": "NJD980528996",
                "SITE_NAME": "TEST SITE",
                "STATE_CODE": "NJ",
                "GIS_AREA": area,
                "GIS_AREA_UNITS": units,
                "NPL_STATUS_CODE": "D",
            },
            "geometry": {"rings": rings},
        }

    # A ring with zero enclosed area — three collinear points.
    DEGENERATE = [[[-74.0, 40.0], [-74.0, 40.0], [-74.0, 40.0], [-74.0, 40.0]]]
    REAL = [[[-74.0, 40.0], [-74.0, 40.1], [-73.9, 40.1], [-73.9, 40.0],
             [-74.0, 40.0]]]

    def test_degenerate_polygon_yields_none_not_zero(self, tmp_path):
        rec = SuperfundNPL(cache_dir=tmp_path).normalize(self._feature(self.DEGENERATE))
        assert rec is not None
        assert rec["acreage"] is None

    def test_explicit_zero_acres_from_source_yields_none(self, tmp_path):
        rec = SuperfundNPL(cache_dir=tmp_path).normalize(
            self._feature(self.REAL, units="Acres", area=0)
        )
        assert rec["acreage"] is None

    def test_real_polygon_still_produces_positive_acreage(self, tmp_path):
        rec = SuperfundNPL(cache_dir=tmp_path).normalize(self._feature(self.REAL))
        assert rec["acreage"] is not None and rec["acreage"] > 0

    def test_reported_acreage_is_untouched(self, tmp_path):
        rec = SuperfundNPL(cache_dir=tmp_path).normalize(
            self._feature(self.REAL, units="Acres", area=137.5)
        )
        assert rec["acreage"] == 137.5


# --------------------------------------------------------------------------
# IPv4 pinning
# --------------------------------------------------------------------------

class TestPreferIpv4:
    @pytest.fixture(autouse=True)
    def _restore(self):
        original = socket.getaddrinfo
        yield
        socket.getaddrinfo = original

    def test_pins_resolution_to_ipv4(self):
        captured = {}
        real = socket.getaddrinfo

        def spy(host, port, family=0, type=0, proto=0, flags=0):
            captured["family"] = family
            return []

        socket.getaddrinfo = spy
        prefer_ipv4()
        socket.getaddrinfo("example.com", 443)
        assert captured["family"] == socket.AF_INET
        assert socket.getaddrinfo is not real

    def test_disabled_is_a_noop(self):
        before = socket.getaddrinfo
        prefer_ipv4(enabled=False)
        assert socket.getaddrinfo is before

    def test_is_idempotent(self):
        """Repeat calls must not nest wrappers — that would recurse per call."""
        prefer_ipv4()
        first = socket.getaddrinfo
        prefer_ipv4()
        prefer_ipv4()
        assert socket.getaddrinfo is first

    def test_still_resolves_a_real_hostname(self):
        """localhost has an A record; pinning must not break normal lookup."""
        prefer_ipv4()
        results = socket.getaddrinfo("localhost", 80)
        assert results
        assert all(r[0] == socket.AF_INET for r in results)


# --------------------------------------------------------------------------
# Source sentinel strings
# --------------------------------------------------------------------------

class TestCollapseSentinel:
    """Placeholder strings must become absent, not survive as values.

    `NO CITY` and `Unknown` were missing from the frontend's PLACE_SENTINELS,
    so they reached the detail panel and rendered as "No City". Collapsing at
    the connector fixes the browser AND every non-browser consumer.
    """

    @pytest.mark.parametrize("raw", [
        None, "", "   ", "NO CITY", "no city", "  No City  ",
        "-- Not Defined --", "-- NOT DEFINED --", "_NULL_", "_null_",
        "Unknown", "UNKNOWN", "unknown", "n/a", "N/A", "NA", "na",
        "None", "none", "NULL", "not defined", "TBD", "--", "-", ".",
    ])
    def test_sentinels_become_none(self, raw):
        from connectors.text import collapse_sentinel
        assert collapse_sentinel(raw) is None

    @pytest.mark.parametrize("raw,expected", [
        ("Hattiesburg", "Hattiesburg"),
        ("  Forrest  ", "Forrest"),
        ("St. Louis", "St. Louis"),
        ("0", "0"),                      # a street number, not a sentinel
        ("Nan", "Nan"),                  # Nan County exists; only "na" is a sentinel
        ("Unknown Valley", "Unknown Valley"),  # substring must not match
        ("None Such Road", "None Such Road"),
    ])
    def test_real_values_pass_through(self, raw, expected):
        from connectors.text import collapse_sentinel
        assert collapse_sentinel(raw) == expected

    def test_connectors_apply_it(self, tmp_path):
        """The three place-bearing connectors must actually call it."""
        from connectors.dod_fuds import DodFuds
        rec = DodFuds(cache_dir=tmp_path).normalize({
            "attributes": {
                "DODFUDSPROPERTYIDPK": "A04MS0001", "FEATURENAME": "X",
                "CLOSESTCITY": "NO CITY", "COUNTY": "-- Not Defined --",
                "STATE": "ms", "EPAREGION": "04",
                "LATITUDE": 31.2, "LONGITUDE": -89.2,
            },
            "geometry": {"x": -89.2, "y": 31.2},
        })
        assert rec["city"] is None
        assert rec["county"] is None


# --------------------------------------------------------------------------
# Infra attribute sentinels
# --------------------------------------------------------------------------

class TestInfraAttributeSentinels:
    """Zero MW and sub-1 kV are missing values, not measurements."""

    def test_min_substation_kv_is_documented(self):
        from connectors.infra_proximity import MIN_SUBSTATION_KV
        assert MIN_SUBSTATION_KV == 1.0

    def test_shipped_corpus_has_no_zero_mw_or_lv_substations(self):
        """End-to-end: the file on disk is clean."""
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        recs = json.loads(
            (root / "docs" / "data" / "infra-proximity.json").read_text()
        )["sites"]
        assert not [r for r in recs if r.get("power_plant_mw") == 0]
        assert not [r for r in recs
                    if r.get("substation_kv") is not None
                    and r["substation_kv"] < 1.0]

    def test_shipped_corpus_has_no_sentinel_place_strings(self):
        import json
        from pathlib import Path
        from connectors.text import collapse_sentinel
        root = Path(__file__).resolve().parent.parent
        offenders = []
        for name in ("superfund-npl.json", "epa-acres.json", "dod-fuds.json",
                     "dod-brac.json"):
            for rec in json.loads((root / "docs" / "data" / name).read_text())["sites"]:
                for field in ("city", "county", "address"):
                    if field in rec and collapse_sentinel(rec[field]) is None:
                        offenders.append(f"{name}:{rec['id']}:{field}={rec[field]!r}")
        assert not offenders, offenders[:10]
