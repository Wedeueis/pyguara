"""Tests for `pyguara/common/grid.py`."""

from __future__ import annotations

import math

from pyguara.common.grid import (
    cell_to_world,
    cells_in_rect,
    chebyshev_distance,
    line,
    manhattan_distance,
    neighbors4,
    neighbors8,
    world_to_cell,
)
from pyguara.common.types import Rect, Vector2

# ========== world_to_cell / cell_to_world ==========


def test_world_to_cell_uses_floor_not_truncation_left_of_origin() -> None:
    """A negative coordinate must floor toward -1, not truncate toward 0 --
    the exact bug #64 flagged in the pre-migration ai/pathfinding copy."""
    assert world_to_cell(Vector2(-1, -1), cell_size=10.0) == (-1, -1)


def test_world_to_cell_respects_offset() -> None:
    assert world_to_cell(Vector2(25, 5), cell_size=10.0, offset=Vector2(20, 0)) == (
        0,
        0,
    )


def test_cell_to_world_returns_the_cell_centre() -> None:
    assert cell_to_world((0, 0), cell_size=10.0) == Vector2(5, 5)
    assert cell_to_world((2, 3), cell_size=10.0) == Vector2(25, 35)


def test_cell_to_world_round_trips_through_world_to_cell() -> None:
    cell = (4, -3)
    center = cell_to_world(cell, cell_size=16.0, offset=Vector2(1, 2))
    assert world_to_cell(center, cell_size=16.0, offset=Vector2(1, 2)) == cell


# ========== distances ==========


def test_manhattan_distance_is_axis_sum() -> None:
    assert manhattan_distance((0, 0), (3, 4)) == 7


def test_chebyshev_distance_is_the_larger_axis_delta() -> None:
    assert chebyshev_distance((0, 0), (3, 4)) == 4
    assert chebyshev_distance((0, 0), (5, 1)) == 5


# ========== neighbours ==========


def test_neighbors4_returns_the_four_orthogonal_cells() -> None:
    result = set(neighbors4((5, 5)))
    assert result == {(6, 5), (4, 5), (5, 6), (5, 4)}


def test_neighbors8_includes_diagonals() -> None:
    result = set(neighbors8((0, 0)))
    assert result == {
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    }
    assert len(result) == 8


# ========== line ==========


def test_line_is_inclusive_of_both_endpoints() -> None:
    result = line((0, 0), (3, 0))
    assert result[0] == (0, 0)
    assert result[-1] == (3, 0)


def test_line_on_a_single_cell_returns_just_that_cell() -> None:
    assert line((2, 2), (2, 2)) == [(2, 2)]


def test_line_is_axis_exact_for_horizontal_and_vertical_walks() -> None:
    assert line((0, 0), (4, 0)) == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
    assert line((0, 0), (0, 3)) == [(0, 0), (0, 1), (0, 2), (0, 3)]


def test_line_step_count_matches_the_longer_axis() -> None:
    """Bresenham never takes more steps than the dominant axis needs."""
    result = line((0, 0), (10, 3))
    assert len(result) == 11  # 10 steps + the start


# ========== cells_in_rect ==========


def test_cells_in_rect_covers_every_cell_touching_the_rect() -> None:
    result = set(cells_in_rect(Rect(0, 0, 20, 20), cell_size=10.0))
    # A 20x20 rect at the origin spans cells (0,0) and (1,1) on each edge;
    # the far edge lands exactly on a cell boundary, included as a
    # candidate the same way SpatialHash's own cell lookup includes it.
    assert (0, 0) in result
    assert (1, 1) in result


def test_cells_in_rect_respects_offset() -> None:
    result = set(
        cells_in_rect(Rect(10, 10, 5, 5), cell_size=10.0, offset=Vector2(10, 10))
    )
    assert result == {(0, 0)}


def test_manhattan_matches_chebyshev_on_pure_diagonals() -> None:
    """Sanity cross-check: on a pure 45-degree line the two metrics diverge
    by exactly the smaller axis, not some other relationship entirely."""
    a, b = (0, 0), (5, 5)
    assert manhattan_distance(a, b) == 2 * chebyshev_distance(a, b)
    assert chebyshev_distance(a, b) == math.dist(a, b) / math.sqrt(2)
