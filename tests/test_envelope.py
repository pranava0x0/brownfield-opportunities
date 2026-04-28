"""Unit tests for SuperfundNPL.envelope_center()."""
from __future__ import annotations

import pytest

from connectors.superfund_npl import SuperfundNPL


def test_simple_square():
    rings = [[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]]
    assert SuperfundNPL.envelope_center(rings) == (5.0, 5.0)


def test_negative_coordinates():
    rings = [[[-100.0, 30.0], [-90.0, 30.0], [-90.0, 40.0], [-100.0, 40.0], [-100.0, 30.0]]]
    assert SuperfundNPL.envelope_center(rings) == (-95.0, 35.0)


def test_multi_ring_polygon():
    rings = [
        [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]],
        [[10.0, 10.0], [12.0, 10.0], [12.0, 12.0], [10.0, 12.0], [10.0, 10.0]],
    ]
    assert SuperfundNPL.envelope_center(rings) == (6.0, 6.0)


def test_degenerate_single_point():
    rings = [[[5.0, 5.0], [5.0, 5.0], [5.0, 5.0]]]
    assert SuperfundNPL.envelope_center(rings) == (5.0, 5.0)


def test_empty_rings_raises():
    with pytest.raises(ValueError, match="empty geometry"):
        SuperfundNPL.envelope_center([])


def test_empty_inner_ring_raises():
    with pytest.raises(ValueError, match="empty geometry"):
        SuperfundNPL.envelope_center([[]])
