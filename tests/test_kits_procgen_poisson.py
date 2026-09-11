"""Tests for `pyguara/kits/procgen/poisson.py` (Poisson-disc sampling)."""

from __future__ import annotations

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect
from pyguara.kits.procgen import poisson_disc_sample


def test_non_positive_min_distance_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        poisson_disc_sample(Rect(0, 0, 100, 100), 0, RandomStream(1))


def test_a_zero_area_region_returns_no_points() -> None:
    assert poisson_disc_sample(Rect(0, 0, 0, 50), 5.0, RandomStream(1)) == []


def test_every_point_is_within_bounds() -> None:
    bounds = Rect(10, 20, 100, 80)
    points = poisson_disc_sample(bounds, 8.0, RandomStream(1))

    assert len(points) > 1
    for point in points:
        assert bounds.left <= point.x <= bounds.right
        assert bounds.top <= point.y <= bounds.bottom


def test_every_pair_of_points_respects_min_distance() -> None:
    bounds = Rect(0, 0, 100, 100)
    min_distance = 6.0
    points = poisson_disc_sample(bounds, min_distance, RandomStream(1))

    assert len(points) > 1
    for i, a in enumerate(points):
        for b in points[i + 1 :]:
            assert a.distance_to(b) >= min_distance - 1e-9


def test_sampling_is_deterministic() -> None:
    bounds = Rect(0, 0, 60, 60)
    a = poisson_disc_sample(bounds, 5.0, RandomStream(42))
    b = poisson_disc_sample(bounds, 5.0, RandomStream(42))

    assert a == b


def test_a_smaller_min_distance_packs_more_points() -> None:
    bounds = Rect(0, 0, 100, 100)
    sparse = poisson_disc_sample(bounds, 15.0, RandomStream(1))
    dense = poisson_disc_sample(bounds, 4.0, RandomStream(1))

    assert len(dense) > len(sparse)
