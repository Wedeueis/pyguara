"""Tests for `SpatialHash` (pyguara/common/spatial.py)."""

from __future__ import annotations

from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Rect, Vector2


def test_query_radius_finds_keys_within_range() -> None:
    grid = SpatialHash[str](cell_size=16.0)
    grid.insert("near", Vector2(10, 10))
    grid.insert("far", Vector2(1000, 1000))

    result = grid.query_radius(Vector2(0, 0), radius=50.0)

    assert result == ["near"]


def test_query_radius_excludes_keys_in_range_cell_but_outside_exact_radius() -> None:
    """Candidate cells are a superset of the exact answer -- confirms the
    exact-distance check actually filters, not just the cell lookup."""
    grid = SpatialHash[str](cell_size=64.0)
    # Same cell as the origin, but outside a tight radius.
    grid.insert("corner", Vector2(60, 60))

    result = grid.query_radius(Vector2(0, 0), radius=10.0)

    assert result == []


def test_query_point_finds_only_keys_sharing_the_cell() -> None:
    grid = SpatialHash[str](cell_size=10.0)
    grid.insert("same_cell", Vector2(1, 1))
    grid.insert("other_cell", Vector2(50, 50))

    result = grid.query_point(Vector2(2, 2))

    assert result == ["same_cell"]


def test_query_rect_finds_keys_inside_bounds() -> None:
    grid = SpatialHash[str](cell_size=16.0)
    grid.insert("inside", Vector2(5, 5))
    grid.insert("outside", Vector2(500, 500))

    result = grid.query_rect(Rect(0, 0, 20, 20))

    assert result == ["inside"]


def test_reinserting_at_a_new_position_moves_the_key() -> None:
    grid = SpatialHash[str](cell_size=16.0)
    grid.insert("key", Vector2(0, 0))

    grid.insert("key", Vector2(1000, 1000))

    assert grid.query_radius(Vector2(0, 0), radius=10.0) == []
    assert grid.query_radius(Vector2(1000, 1000), radius=10.0) == ["key"]


def test_reinserting_within_the_same_cell_does_not_duplicate_the_key() -> None:
    grid = SpatialHash[str](cell_size=64.0)
    grid.insert("key", Vector2(0, 0))

    grid.insert("key", Vector2(1, 1))

    assert grid.query_radius(Vector2(0, 0), radius=10.0) == ["key"]


def test_remove_drops_the_key_from_future_queries() -> None:
    grid = SpatialHash[str](cell_size=16.0)
    grid.insert("key", Vector2(0, 0))

    grid.remove("key")

    assert grid.query_radius(Vector2(0, 0), radius=100.0) == []


def test_remove_of_untracked_key_is_a_noop() -> None:
    grid = SpatialHash[str](cell_size=16.0)

    grid.remove("never inserted")  # must not raise


def test_query_respects_mask_filter() -> None:
    grid = SpatialHash[str](cell_size=16.0)
    grid.insert("enemy", Vector2(0, 0), mask=0b01)
    grid.insert("pickup", Vector2(1, 1), mask=0b10)

    enemies_only = grid.query_radius(Vector2(0, 0), radius=10.0, mask=0b01)

    assert enemies_only == ["enemy"]
