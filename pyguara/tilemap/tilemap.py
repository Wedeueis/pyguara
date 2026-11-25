"""A named collection of `TileLayer`s sharing one or more `Tileset`s."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pyguara.common.types import Rect
from pyguara.tilemap.layer import TileLayer
from pyguara.tilemap.objects import MapObject, ObjectLayer
from pyguara.tilemap.tileset import Tileset


class Tilemap:
    """A map's layers and tilesets, and the glue between them.

    A `TileLayer` stores only global tile ids; resolving a gid to the
    custom properties a game gave it (walkable, damage, whatever) means
    knowing which `Tileset` owns that gid's range, which is what this
    class is for.
    """

    def __init__(
        self,
        tile_size: int | tuple[int, int],
        tilesets: list[Tileset] | None = None,
    ) -> None:
        """Create an empty map.

        Args:
            tile_size: A tile's `(width, height)` in pixels, or one number
                for a square tile.
            tilesets: The tilesets this map draws tile ids from. Their
                `first_gid` ranges should not overlap; on an overlap, the
                last matching tileset in this list wins.

        Raises:
            ValueError: If the size is not one or two positive whole numbers.
        """
        self.tile_width, self.tile_height = _tile_size(tile_size)
        self.tilesets = list(tilesets) if tilesets is not None else []
        self.layers: dict[str, TileLayer] = {}
        self.object_layers: dict[str, ObjectLayer] = {}

    @property
    def tile_size(self) -> int:
        """A square tile's edge length in pixels.

        Raises:
            ValueError: If the tiles are not square; read `tile_width` and
                `tile_height` instead.
        """
        if self.tile_width != self.tile_height:
            raise ValueError(
                f"this map's tiles are {self.tile_width}x{self.tile_height}, "
                f"not square; read tile_width and tile_height"
            )
        return self.tile_width

    def add_layer(self, name: str, layer: TileLayer) -> None:
        """Add a layer under `name`, replacing any existing layer there."""
        self.layers[name] = layer

    def add_object_layer(self, layer: ObjectLayer) -> None:
        """Add an object layer, replacing any existing one of that name.

        Kept separate from `layers` rather than sharing one dict: a tile
        layer and an object layer have nothing in common but a name, and
        every consumer of `layers` iterates it expecting a grid.

        Args:
            layer: The layer to add; its own `name` is the key.
        """
        self.object_layers[layer.name] = layer

    def objects(self, type_name: str | None = None) -> list[MapObject]:
        """Return every map object, optionally filtered by Tiled type.

        Across all object layers, in layer-then-file order. Most callers
        want "every spawn point in this map" and should not have to know
        which layer the author filed them under.

        Args:
            type_name: A Tiled type/class to match exactly, or None for
                everything.

        Returns:
            The matching objects.
        """
        found: list[MapObject] = []
        for layer in self.object_layers.values():
            found.extend(
                obj
                for obj in layer.objects
                if type_name is None or obj.type == type_name
            )
        return found

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
            self.properties_for, (self.tile_width, self.tile_height)
        )


def _tile_size(value: object) -> tuple[int, int]:
    """Read a tile size as `(width, height)`.

    Raises:
        ValueError: If it is not one or two positive whole numbers.
    """
    pair = (value, value) if not isinstance(value, tuple) else value
    if len(pair) != 2 or not all(
        isinstance(side, int) and not isinstance(side, bool) and side > 0
        for side in pair
    ):
        raise ValueError(
            f"a tile size is a positive whole number of pixels, or a "
            f"(width, height) pair of them, not {value!r}"
        )
    return pair[0], pair[1]
