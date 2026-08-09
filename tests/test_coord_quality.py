"""Tests for the coord-quality enrichment connector.

The connector's job is to say how much a coordinate can be trusted without
ever changing it. These tests cover the four flag predicates, the
state-boundary tolerance that separates real errors from generalized-polygon
noise, and the end-to-end contract that clean records produce no output.
"""
from __future__ import annotations

import argparse
import json

import pytest

from connectors.coord_quality import (
    SHARED_POINT_MIN,
    STATE_TOLERANCE_MI,
    CoordQuality,
    _decimals,
    _inside_any_region,
    _is_placeholder,
)


# -- Pure predicates --------------------------------------------------------

class TestPlaceholderDetection:
    @pytest.mark.parametrize("lat,lon", [
        (33.0, -112.0),      # whole degrees — the AZ cluster
        (38.0, -90.0),
        (33.5, -112.5),      # half degrees
        (45.0, -45.0),       # lat == |lon|
    ])
    def test_flags_typed_coordinates(self, lat, lon):
        assert _is_placeholder(lat, lon)

    @pytest.mark.parametrize("lat,lon", [
        (33.775324, -118.154456),
        (41.895217, -73.308184),
        (33.01, -112.0),     # only one component whole
        (33.25, -112.75),    # quarter degrees are plausible survey output
    ])
    def test_accepts_real_coordinates(self, lat, lon):
        assert not _is_placeholder(lat, lon)


class TestRegionBoxes:
    @pytest.mark.parametrize("lat,lon,why", [
        (40.0, -100.0, "CONUS"),
        (64.8, -147.7, "Fairbanks AK"),
        (52.9, 173.2, "Attu — western Aleutians, positive longitude"),
        (21.3, -157.8, "Honolulu"),
        (28.39, -178.3, "Kure Atoll — Northwestern Hawaiian Islands"),
        (18.2, -66.5, "Puerto Rico"),
        (-11.06, -171.07, "Swains Island, American Samoa"),
        (13.45, 144.75, "Guam"),
    ])
    def test_real_us_locations_are_inside(self, lat, lon, why):
        assert _inside_any_region(lat, lon), why

    @pytest.mark.parametrize("lat,lon,why", [
        (30.73, 76.77, "Chandigarh, India — ACRES-36324"),
        (43.2, 75.43, "flipped longitude sign — ACRES-125953"),
        (51.5, -0.12, "London"),
        (-33.9, 151.2, "Sydney"),
    ])
    def test_non_us_locations_are_outside(self, lat, lon, why):
        assert not _inside_any_region(lat, lon), why


class TestDecimals:
    @pytest.mark.parametrize("v,expected", [
        (33.0, 0), (33.5, 1), (33.25, 2), (33.775324, 6), (-118.154456, 6),
    ])
    def test_counts_significant_decimals(self, v, expected):
        assert _decimals(v) == expected


# -- End-to-end over a synthetic data directory -----------------------------

@pytest.fixture
def data_dir(tmp_path):
    """A minimal docs/data with a one-state basemap and program files."""
    d = tmp_path / "data"
    d.mkdir()
    # A square "Kansas" from -100..-98 lon, 38..40 lat.
    (d / "us-states.json").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "Kansas"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [-100.0, 38.0], [-98.0, 38.0], [-98.0, 40.0],
                [-100.0, 40.0], [-100.0, 38.0],
            ]]},
        }, {
            "type": "Feature",
            "properties": {"name": "Missouri"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [-98.0, 38.0], [-96.0, 38.0], [-96.0, 40.0],
                [-98.0, 40.0], [-98.0, 38.0],
            ]]},
        }],
    }))
    return d


def _write_sites(d, sites):
    (d / "superfund-npl.json").write_text(json.dumps({
        "generated_at": "2026-08-09T00:00:00Z", "source": "t",
        "source_url": "https://example.test", "count": len(sites),
        "sites": sites,
    }))
    for name in ("epa-acres.json", "dod-fuds.json", "dod-brac.json"):
        (d / name).write_text(json.dumps({
            "generated_at": "2026-08-09T00:00:00Z", "source": "t",
            "source_url": "https://example.test", "count": 0, "sites": [],
        }))


def _run(tmp_path, data_dir, monkeypatch):
    monkeypatch.setattr(CoordQuality, "DATA_DIR", data_dir)
    conn = CoordQuality(cache_dir=tmp_path / "cache")
    return {r["id"]: r for r in
            conn.fetch_records(argparse.Namespace(), use_cache=False)}


def _site(sid, lat, lon, state="KS"):
    return {"id": sid, "program": "superfund", "lat": lat, "lon": lon,
            "state": state, "name": sid}


class TestFlagging:
    def test_clean_site_is_omitted_entirely(self, tmp_path, data_dir, monkeypatch):
        """Absence must mean 'no known problem' so the file stays small."""
        _write_sites(data_dir, [_site("CLEAN", 39.123456, -99.123456)])
        assert _run(tmp_path, data_dir, monkeypatch) == {}

    def test_state_mismatch_carries_actual_state_and_gap(
        self, tmp_path, data_dir, monkeypatch
    ):
        # Well inside "Missouri" while claiming KS.
        _write_sites(data_dir, [_site("WRONG", 39.123456, -96.987654)])
        out = _run(tmp_path, data_dir, monkeypatch)
        rec = out["WRONG"]
        assert "state_mismatch" in rec["coord_flags"]
        assert rec["coord_actual_state"] == "MO"
        assert rec["coord_state_gap_mi"] > STATE_TOLERANCE_MI

    def test_point_just_over_the_border_is_not_flagged(
        self, tmp_path, data_dir, monkeypatch
    ):
        """213 real corpus sites sit on a state line — don't cry wolf."""
        # ~0.3 mi east of the KS/MO line at -98.0.
        _write_sites(data_dir, [_site("BORDER", 39.123456, -97.994321)])
        out = _run(tmp_path, data_dir, monkeypatch)
        assert "state_mismatch" not in out.get("BORDER", {}).get("coord_flags", [])

    def test_outside_us_is_flagged(self, tmp_path, data_dir, monkeypatch):
        _write_sites(data_dir, [_site("INDIA", 30.730421, 76.765596)])
        assert "outside_us" in _run(tmp_path, data_dir, monkeypatch)["INDIA"]["coord_flags"]

    def test_shared_point_needs_at_least_three(self, tmp_path, data_dir, monkeypatch):
        pair = [_site("A", 39.111111, -99.111111), _site("B", 39.111111, -99.111111)]
        _write_sites(data_dir, pair)
        out = _run(tmp_path, data_dir, monkeypatch)
        assert "shared_point" not in out.get("A", {}).get("coord_flags", [])

        trio = pair + [_site("C", 39.111111, -99.111111)]
        _write_sites(data_dir, trio)
        out = _run(tmp_path, data_dir, monkeypatch)
        assert "shared_point" in out["A"]["coord_flags"]
        assert out["A"]["coord_shared_count"] == SHARED_POINT_MIN

    def test_placeholder_and_low_precision_stack(
        self, tmp_path, data_dir, monkeypatch
    ):
        """A whole-degree coordinate is both typed AND coarse — report both."""
        _write_sites(data_dir, [_site("PH", 39.0, -99.0)])
        flags = _run(tmp_path, data_dir, monkeypatch)["PH"]["coord_flags"]
        assert "placeholder" in flags
        assert "low_precision" in flags

    def test_missing_coordinates_are_skipped_not_flagged(
        self, tmp_path, data_dir, monkeypatch
    ):
        """No coordinate is a different problem, tracked by coord-present."""
        rec = _site("NOCOORD", None, None)
        _write_sites(data_dir, [rec])
        assert _run(tmp_path, data_dir, monkeypatch) == {}

    def test_never_mutates_the_coordinate(self, tmp_path, data_dir, monkeypatch):
        """The connector reports; it must never 'correct' a location."""
        _write_sites(data_dir, [_site("WRONG", 39.123456, -96.987654)])
        out = _run(tmp_path, data_dir, monkeypatch)
        assert "lat" not in out["WRONG"] and "lon" not in out["WRONG"]

    def test_emitted_records_validate_against_schema(
        self, tmp_path, data_dir, monkeypatch
    ):
        from schema import SiteRecord
        _write_sites(data_dir, [
            _site("WRONG", 39.123456, -96.987654),
            _site("PH", 39.0, -99.0),
        ])
        for rec in _run(tmp_path, data_dir, monkeypatch).values():
            SiteRecord.model_validate(rec)


class TestShippedOutput:
    """The committed docs/data/coord-quality.json must stay coherent."""

    @pytest.fixture
    def shipped(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        return json.loads(
            (root / "docs" / "data" / "coord-quality.json").read_text()
        )

    def test_every_record_has_at_least_one_flag(self, shipped):
        assert all(r.get("coord_flags") for r in shipped["sites"])

    def test_flags_are_from_the_known_vocabulary(self, shipped):
        known = {"state_mismatch", "outside_us", "placeholder",
                 "shared_point", "low_precision"}
        seen = {f for r in shipped["sites"] for f in r["coord_flags"]}
        assert seen <= known, seen - known

    def test_state_mismatch_records_carry_their_evidence(self, shipped):
        for r in shipped["sites"]:
            if "state_mismatch" in r["coord_flags"]:
                assert r.get("coord_actual_state"), r["id"]
