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
