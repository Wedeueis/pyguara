"""Merging a tile grid into as few colliders as possible.

A floor built as one collider per tile has interior faces between the tiles.
They are invisible in the level and real to the solver, and a character
resting `collision_slop` deep in the floor catches its leading bottom corner
on them. Merging removes the faces; these tests pin the merge itself, and
`tests/integration/test_platformer_feel.py` pins the behaviour it buys.
"""

from __future__ import annotations

import pytest

from pyguara.physics.tilemap import merge_tile_rects

pytestmark = pytest.mark.unit

TILE = 32


def grid(rows: list[str]) -> list[list[bool]]:
    """Build a solidity grid from `#` and `.` rows."""
    return [[char == "#" for char in row] for row in rows]


def test_a_solid_rectangle_becomes_one_collider() -> None:
    """The case that matters: a flat floor is one box, not forty."""
    rects = merge_tile_rects(grid(["#" * 40] * 5), TILE)

    assert len(rects) == 1
    assert (rects[0].x, rects[0].y) == (0, 0)
    assert (rects[0].width, rects[0].height) == (40 * TILE, 5 * TILE)


def test_a_gap_splits_the_run() -> None:
    """A pit in the floor must remain a pit."""
    rects = merge_tile_rects(grid(["##..###"]), TILE)

    assert [(r.x, r.width) for r in rects] == [(0, 2 * TILE), (4 * TILE, 3 * TILE)]


def test_rows_that_do_not_line_up_are_not_stacked() -> None:
    """A row is only stacked onto the one above when their runs match.

    Runs extend rightwards first, so the wider row stays whole and the
    narrower one becomes its own rectangle rather than the pair being
    squared off into a shape the level does not have.
    """
    rects = merge_tile_rects(grid(["###", "##."]), TILE)

    assert sorted((r.x, r.y, r.width, r.height) for r in rects) == [
        (0, 0, 3 * TILE, TILE),
        (0, TILE, 2 * TILE, TILE),
    ]


def test_every_solid_tile_is_covered_exactly_once() -> None:
    """The property that makes merging safe: same area, no overlap.

    A merge that dropped a tile would open a hole to fall through; one that
    double-covered a tile would leave overlapping colliders fighting.
    """
    rows = [
        "#####...####",
        "#..##...#..#",
        "#..#######.#",
        "############",
    ]
    solid = grid(rows)
    rects = merge_tile_rects(solid, TILE)

    covered: dict[tuple[int, int], int] = {}
    for rect in rects:
        for gy in range(rect.y // TILE, (rect.y + rect.height) // TILE):
            for gx in range(rect.x // TILE, (rect.x + rect.width) // TILE):
                covered[(gx, gy)] = covered.get((gx, gy), 0) + 1

    expected = {
        (x, y)
        for y, row in enumerate(solid)
        for x, is_solid in enumerate(row)
        if is_solid
    }
    assert set(covered) == expected
    assert all(count == 1 for count in covered.values())


def test_merging_actually_reduces_the_collider_count() -> None:
    """Otherwise the whole exercise buys nothing."""
    rows = ["#" * 40] * 5 + ["#" + "." * 38 + "#"] * 10
    solid = grid(rows)
    per_tile = sum(row.count(True) for row in solid)

    assert len(merge_tile_rects(solid, TILE)) < per_tile / 10


def test_an_empty_grid_yields_nothing() -> None:
    """No tiles, no colliders -- and no crash on the empty case."""
    assert merge_tile_rects([], TILE) == []
    assert merge_tile_rects(grid(["...", "..."]), TILE) == []
