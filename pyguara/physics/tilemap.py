"""Build collision geometry from a tile grid.

Contiguous solid tiles are merged into as few rectangles as possible.
One collider per tile would leave interior faces where tiles meet, and
a character moving along a floor or a wall catches on them. Sprites
stay per-tile; only the collision shape is merged.
"""

from __future__ import annotations

from collections.abc import Sequence

from pyguara.common.types import Rect


def merge_tile_rects(solid: Sequence[Sequence[bool]], tile_size: int) -> list[Rect]:
    """Cover the solid tiles with as few rectangles as the greedy pass finds.

    Runs of solid tiles are joined along a row, then rows whose runs line up
    exactly are stacked. For a rectangular floor this collapses to a single
    box; for the general case it leaves far fewer interior faces than one
    collider per tile.

    Args:
        solid: Row-major grid, `solid[y][x]` true where a tile blocks.
        tile_size: Edge length of one tile in pixels.

    Returns:
        World-space rectangles covering exactly the solid tiles, in
        row order. Empty when nothing is solid.
    """
    if not solid or not solid[0]:
        return []

    height = len(solid)
    width = len(solid[0])
    claimed = [[False] * width for _ in range(height)]
    rects: list[Rect] = []

    for y in range(height):
        x = 0
        while x < width:
            if not solid[y][x] or claimed[y][x]:
                x += 1
                continue

            # Extend right while the row stays solid and unclaimed.
            run_end = x
            while (
                run_end + 1 < width
                and solid[y][run_end + 1]
                and not claimed[y][run_end + 1]
            ):
                run_end += 1

            # Extend down while the whole run repeats exactly.
            bottom = y
            while bottom + 1 < height and all(
                solid[bottom + 1][cx] and not claimed[bottom + 1][cx]
                for cx in range(x, run_end + 1)
            ):
                bottom += 1

            for cy in range(y, bottom + 1):
                for cx in range(x, run_end + 1):
                    claimed[cy][cx] = True

            rects.append(
                Rect(
                    x * tile_size,
                    y * tile_size,
                    (run_end - x + 1) * tile_size,
                    (bottom - y + 1) * tile_size,
                )
            )
            x = run_end + 1

    return rects
