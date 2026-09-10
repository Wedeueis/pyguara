"""A named collection of `TileLayer`s sharing one or more `Tileset`s."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pyguara.common.types import Rect
from pyguara.tilemap.layer import TileLayer
from pyguara.tilemap.tileset import Tileset


class Tilemap:
    """A map's layers and tilesets, and the glue between them.

    A `TileLayer` stores only global tile ids; resolving a gid to the
    custom properties a game gave it (walkable, damage, whatever) means
    knowing which `Tileset` owns that gid's range, which is what this
    class is for.
    """

    def __init__(self, tile_size: int, tilesets: list[Tileset] | None = None) -> None:
        """Create an empty map.

        Args:
            tile_size: Edge length of one tile in pixels. Tiles are square
                -- `merge_tile_rects` underneath `TileLayer.collision_rects`
                takes one size, not a width/height pair.
            tilesets: The tilesets this map draws tile ids from. Their
                `first_gid` ranges should not overlap; on an overlap, the
                last matching tileset in this list wins.
        """
        self.tile_size = tile_size
        self.tilesets = list(tilesets) if tilesets is not None else []
        self.layers: dict[str, TileLayer] = {}

    def add_layer(self, name: str, layer: TileLayer) -> None:
        """Add a layer under `name`, replacing any existing layer there."""
        self.layers[name] = layer

    def properties_for(self, gid: int) -> Mapping[str, Any]:
        """Return `gid`'s custom properties from whichever tileset owns it.

        Returns `{}` for `EMPTY_GID` (0) or a gid no tileset's range covers.
        """
        for tileset in reversed(self.tilesets):
            if tileset.contains(gid):
                return tileset.properties_for(gid)
        return {}

    def collision_rects(self, layer_name: str) -> list[Rect]:
        """Return merged collision rectangles for the named layer's solid tiles.

        Args:
            layer_name: A key in `self.layers`.

        Raises:
            KeyError: If no layer is registered under `layer_name`.
        """
        return self.layers[layer_name].collision_rects(
            self.properties_for, self.tile_size
        )
