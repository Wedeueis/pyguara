"""A tileset's custom per-tile properties, addressed by global tile id."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Tileset:
    """One tileset's tiles, as a global-id range plus per-tile properties.

    `first_gid`/`tile_count` are what let several tilesets share one map's
    tile-id space -- Tiled's own scheme for it, not an artifact only Tiled
    files need: a game combining two spritesheets into one map wants the
    same stable, non-overlapping ranges.

    Attributes:
        name: The tileset's name, for lookup/debugging.
        first_gid: The lowest global tile id this tileset owns.
        tile_count: How many tile ids this tileset owns, starting at
            `first_gid`. A gid outside `[first_gid, first_gid + tile_count)`
            belongs to a different tileset.
        properties: Local tile id (0-based within this tileset, i.e.
            `gid - first_gid`) to that tile's custom properties. A tile
            with no entry has no custom properties -- most tiles in a
            tileset don't, only the ones a game gave meaning to (walls
            marked `solid`, hazards marked `damage`, and so on).
    """

    name: str
    first_gid: int
    tile_count: int
    properties: Mapping[int, Mapping[str, Any]] = field(default_factory=dict)

    def contains(self, gid: int) -> bool:
        """Report whether `gid` falls in this tileset's range."""
        return self.first_gid <= gid < self.first_gid + self.tile_count

    def properties_for(self, gid: int) -> Mapping[str, Any]:
        """Return `gid`'s custom properties, or `{}` if it has none.

        Args:
            gid: A global tile id already confirmed to be `contains()` this
                tileset -- this does not check the range itself.
        """
        return self.properties.get(gid - self.first_gid, {})
