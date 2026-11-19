"""Procedural construction of the plot's `Tilemap`.

No `.tmx` file, deliberately. `load_tmx` exists to import hand-authored
Tiled maps, and this grid is the opposite of level art: it starts uniform
(every cell raw dirt) and every cell mutates at runtime as the player
tills, plants and builds. That is simulation state, not something to
author in an editor -- so it is built in code, once, the same way
`guara_falcao/level_builder.py` builds its own tile grid procedurally.

Three layers, one job each:

- `terrain` is the authoritative render source for ground kind (raw dirt,
  tilled, path, water pipe) -- `GardenGridCanvas` reads it every frame.
- `flora`/`automation` are occupancy grids only: O(1) "is this cell
  planted/built on" checks and neighbour scans. The actual plant or
  automation sprite and state live on the ECS entity; the tile gid on
  these layers never duplicates that as a second source of truth.

`TileLayer.collision_rects()`/`merge_tile_rects` go unused here on
purpose -- no physics body collides with this grid, so there is nothing
for that half of the tilemap package to do in this demo.
"""

from __future__ import annotations

from pyguara.tilemap.layer import TileLayer
from pyguara.tilemap.tilemap import Tilemap
from pyguara.tilemap.tileset import Tileset

RAW_DIRT_GID = 1
TILLED_GID = 2
PATH_GID = 3
WATER_PIPE_GID = 4

_SOIL_TILESET = Tileset(
    name="cerrado_soil",
    first_gid=1,
    tile_count=4,
    properties={
        0: {"kind": "raw_dirt"},
        1: {"kind": "tilled_dirt"},
        2: {"kind": "path"},
        3: {"kind": "water_pipe"},
    },
)


def build_tilemap(width: int, height: int, tile_size: int) -> Tilemap:
    """Build a uniform, all-raw-dirt plot.

    Args:
        width: Columns.
        height: Rows.
        tile_size: Edge length of one tile in pixels.

    Returns:
        A `Tilemap` with `terrain`, `flora` and `automation` layers.
    """
    tilemap = Tilemap(tile_size=tile_size, tilesets=[_SOIL_TILESET])
    tilemap.add_layer(
        "terrain", TileLayer(width, height, tiles=_uniform(width, height, RAW_DIRT_GID))
    )
    tilemap.add_layer("flora", TileLayer(width, height))
    tilemap.add_layer("automation", TileLayer(width, height))
    return tilemap


def _uniform(width: int, height: int, gid: int) -> list[list[int]]:
    """A `height` x `width` grid filled with one gid."""
    return [[gid] * width for _ in range(height)]
