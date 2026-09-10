"""Integer grid-cell math: coordinates, distances, neighbours, line walks.

`Cell` is a plain `tuple[int, int]`, matching how grid code already treats
cell coordinates throughout the engine (`ai.pathfinding.grid.GridNode`, a
`SpatialHash` bucket key) -- a wrapper class would fight every call site
that already unpacks `x, y = cell` or uses a cell as a dict key.

This exists so pixel<->cell conversion, distance, neighbourhoods, and a
line-of-sight walk are written and tested once, not once per subsystem.
`ai/pathfinding/grid.py` carried its own copy of all of this (with a real
bug in its `int()`-truncating coordinate conversion, since fixed locally)
before being migrated to call here instead.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

from pyguara.common.types import Rect, Vector2

Cell = tuple[int, int]

_NEIGHBORS_4: tuple[Cell, ...] = ((1, 0), (0, 1), (-1, 0), (0, -1))
_NEIGHBORS_8: tuple[Cell, ...] = _NEIGHBORS_4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def world_to_cell(
    position: Vector2, cell_size: float, offset: Vector2 = Vector2(0, 0)
) -> Cell:
    """Return the cell containing `position`.

    Args:
        position: World-space position.
        cell_size: Width and height of one grid cell, in world units.
        offset: World-space position of the grid's origin -- cell (0, 0)'s
            top-left corner. Defaults to no offset.

    Returns:
        The (x, y) cell containing `position`.
    """
    # floor, not int(): int() truncates toward zero, so a point left of or
    # above the grid origin (a negative local coordinate, common with a
    # non-zero offset) would land one cell too high, collapsing everything
    # in -cell_size < d < 0 onto cell 0 instead of -1.
    return (
        math.floor((position.x - offset.x) / cell_size),
        math.floor((position.y - offset.y) / cell_size),
    )


def cell_to_world(
    cell: Cell, cell_size: float, offset: Vector2 = Vector2(0, 0)
) -> Vector2:
    """Return the world-space centre of `cell`.

    Args:
        cell: The (x, y) cell.
        cell_size: Width and height of one grid cell, in world units.
        offset: World-space position of the grid's origin. Defaults to no
            offset.

    Returns:
        The cell's centre in world space -- a walking target lands in the
        middle of a tile, not its corner.
    """
    x, y = cell
    return Vector2(
        x * cell_size + cell_size / 2 + offset.x,
        y * cell_size + cell_size / 2 + offset.y,
    )


def manhattan_distance(a: Cell, b: Cell) -> int:
    """Return the 4-directional (orthogonal-only) distance between two cells."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def chebyshev_distance(a: Cell, b: Cell) -> int:
    """Return the 8-directional distance, where a diagonal step counts as one."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def neighbors4(cell: Cell) -> list[Cell]:
    """Return the 4 orthogonally adjacent cells.

    Unfiltered by bounds or walls -- that policy belongs to whatever grid
    graph or tilemap is asking, not to this primitive.
    """
    x, y = cell
    return [(x + dx, y + dy) for dx, dy in _NEIGHBORS_4]


def neighbors8(cell: Cell) -> list[Cell]:
    """Return the 8 adjacent cells (orthogonal and diagonal), unfiltered."""
    x, y = cell
    return [(x + dx, y + dy) for dx, dy in _NEIGHBORS_8]


def line(start: Cell, end: Cell) -> list[Cell]:
    """Walk every cell Bresenham's line algorithm visits from `start` to `end`.

    Inclusive of both endpoints. This knows nothing of walls or bounds,
    only geometry -- a caller checking line-of-sight stops at the first
    cell that fails its own passability test instead.

    Args:
        start: The first cell.
        end: The last cell.

    Returns:
        Every cell on the line, in order from `start` to `end`.
    """
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    cells = [(x0, y0)]
    while (x0, y0) != (x1, y1):
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
        cells.append((x0, y0))
    return cells


def cells_in_rect(
    bounds: Rect, cell_size: float, offset: Vector2 = Vector2(0, 0)
) -> Iterator[Cell]:
    """Yield every cell whose bucket could overlap `bounds`.

    A broad-phase walk, the same trade `SpatialHash` makes for its own
    lookups: a cell exactly touching `bounds`'s far edge is included even
    though `Rect.contains_point` treats that edge as exclusive, so this is
    a candidate set to confirm against, not an exact answer.

    Args:
        bounds: The world-space rectangle to walk.
        cell_size: Width and height of one grid cell, in world units.
        offset: World-space position of the grid's origin. Defaults to no
            offset.

    Returns:
        Every cell in the range spanning `bounds`, row by row.
    """
    min_cell = world_to_cell(Vector2(bounds.left, bounds.top), cell_size, offset)
    max_cell = world_to_cell(Vector2(bounds.right, bounds.bottom), cell_size, offset)
    for x in range(min_cell[0], max_cell[0] + 1):
        for y in range(min_cell[1], max_cell[1] + 1):
            yield (x, y)
