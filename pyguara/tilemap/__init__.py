"""A genre-agnostic tilemap data structure: layers, tilesets, and Tiled import.

`physics/tilemap.py`'s `merge_tile_rects` is the collision-geometry half of
this; `TileLayer.collision_rects()` calls it directly rather than
duplicating tile merging here.
"""

from pyguara.tilemap.layer import EMPTY_GID, TileLayer
from pyguara.tilemap.tiled_loader import load_tmx
from pyguara.tilemap.tilemap import Tilemap
from pyguara.tilemap.tileset import Tileset

__all__ = ["EMPTY_GID", "TileLayer", "Tileset", "Tilemap", "load_tmx"]
