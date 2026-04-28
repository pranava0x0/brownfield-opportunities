"""Tests for SuperfundNPL._merge_by_epa_id() — collapses multi-polygon sites."""
from __future__ import annotations

from connectors.superfund_npl import SuperfundNPL


def _feat(epa_id, area, units="Acres", name=None, rings=None, **attrs):
    base = {
        "EPA_ID": epa_id,
        "SITE_NAME": name or f"Site {epa_id}",
        "GIS_AREA": area,
        "GIS_AREA_UNITS": units,
    }
    base.update(attrs)
    return {
        "attributes": base,
        "geometry": {"rings": rings or [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]},
    }


def test_distinct_ids_unchanged():
    feats = [_feat("A", 100), _feat("B", 200)]
    out = SuperfundNPL._merge_by_epa_id(feats)
    assert len(out) == 2


def test_duplicate_id_acreage_summed():
    feats = [_feat("X", 100), _feat("X", 50), _feat("X", 25)]
    out = SuperfundNPL._merge_by_epa_id(feats)
    assert len(out) == 1
    assert out[0]["attributes"]["GIS_AREA"] == 175.0


def test_rings_concatenated():
    r1 = [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]
    r2 = [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 10.0]]]
    feats = [_feat("X", 1, rings=r1), _feat("X", 1, rings=r2)]
    out = SuperfundNPL._merge_by_epa_id(feats)
    assert len(out[0]["geometry"]["rings"]) == 2


def test_first_non_null_attribute_wins():
    feats = [
        _feat("X", 100, name="Real Name", CITY_NAME=None),
        _feat("X", 50, name="Fragment", CITY_NAME="Springfield"),
    ]
    out = SuperfundNPL._merge_by_epa_id(feats)
    attrs = out[0]["attributes"]
    assert attrs["SITE_NAME"] == "Real Name"
    assert attrs["CITY_NAME"] == "Springfield"


def test_mixed_units_drops_acreage_summing():
    """Units must match to sum — otherwise keep first non-null."""
    feats = [
        _feat("X", 100, units="Acres"),
        _feat("X", 5, units="Square Miles"),
    ]
    out = SuperfundNPL._merge_by_epa_id(feats)
    # First wins; second is not summed.
    assert out[0]["attributes"]["GIS_AREA"] == 100.0
    assert out[0]["attributes"]["GIS_AREA_UNITS"] == "Acres"


def test_features_without_epa_id_passthrough():
    feats = [_feat(None, 100), _feat("A", 50), _feat("A", 25)]
    out = SuperfundNPL._merge_by_epa_id(feats)
    assert len(out) == 2  # one merged "A" + one null-id passthrough
