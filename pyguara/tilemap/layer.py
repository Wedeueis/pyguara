"""One layer of a `Tilemap`: a dense grid of global tile ids."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pyguara.common.grid import Cell
from pyguara.common.types import Rect
from pyguara.physics.tilemap import merge_tile_rects

EMPTY_GID = 0


class TileLayer:
    """A dense `width` x `height` grid of global tile ids.

    Knows nothing of tilesets or `Tilemap` -- `collision_rects()` takes a
    property lookup as a parameter rather than reaching for one, so this
    stays a plain grid a `Tilemap` composes rather than a piece that
    depends on it.
    """

    def __init__(
        self,
        width: int,
        height: int,
        tiles: list[list[int]] | None = None,
    ) -> None:
        """Create a layer, optionally seeded with existing tile data.

        Args:
            width: Columns.
            height: Rows.
            tiles: Row-major initial tile ids (`tiles[y][x]`), `EMPTY_GID`
                (0) meaning no tile. Defaults to an all-empty grid the given
                size, deep-copied if given so the caller's list is never
                aliased and mutated underneath them.

        Raises:
            ValueError: If `tiles` is given and does not match `width` x
                `height`.
        """
        self.width = width
        self.height = height
        if tiles is None:
            self._tiles = [[EMPTY_GID] * width for _ in range(height)]
        else:
            if len(tiles) != height or any(len(row) != width for row in tiles):
                raise ValueError(f"tiles must be {height} rows of {width} columns each")
            self._tiles = [list(row) for row in tiles]
        self._collision_rects: list[Rect] | None = None

    def get_tile(self, cell: Cell) -> int:
        """Return the global tile id at `cell`, or `EMPTY_GID` if none."""
        x, y = cell
        return self._tiles[y][x]

    def set_tile(self, cell: Cell, gid: int) -> None:
        """Set the global tile id at `cell`.

        Invalidates the cached `collision_rects()` result -- the next call
        re-merges, since a changed tile can change which rectangles cover
        the solid area.
        """
        x, y = cell
        self._tiles[y][x] = gid
        self._collision_rects = None

    def collision_rects(
        self,
        properties_for: Callable[[int], Mapping[str, Any]],
        tile_size: int,
    ) -> list[Rect]:
        """Return merged collision rectangles for every tile marked solid.

        Cached until the next `set_tile()` call -- recomputing on every
        query would re-run the merge for a layer that hasn't changed.

        Args:
            properties_for: Resolves a gid to its tile's custom properties;
                a tile is solid iff `properties_for(gid)["solid"]` is
                truthy. Normally `Tilemap.properties_for`.
            tile_size: Edge length of one tile in pixels.
        """
        if self._collision_rects is None:
            solid = [
                [bool(properties_for(gid).get("solid", False)) for gid in row]
                for row in self._tiles
            ]
            self._collision_rects = merge_tile_rects(solid, tile_size)
        return self._collision_rects
