"""A genre-agnostic tilemap data structure: layers, tilesets, and Tiled import.

`physics/tilemap.py`'s `merge_tile_rects` is the collision-geometry half of
this; `TileLayer.collision_rects()` calls it directly rather than
duplicating tile merging here.
"""

from pyguara.tilemap.layer import EMPTY_GID, TileLayer
from pyguara.tilemap.ldtk_loader import load_ldtk, load_ldtk_level
from pyguara.tilemap.objects import MapObject, ObjectLayer, ObjectShape
from pyguara.tilemap.tiled_loader import load_tmx
from pyguara.tilemap.tilemap import Tilemap
from pyguara.tilemap.tileset import Tileset

__all__ = [
    "EMPTY_GID",
    "MapObject",
    "ObjectLayer",
    "ObjectShape",
    "TileLayer",
    "Tilemap",
    "Tileset",
    "load_ldtk",
    "load_ldtk_level",
    "load_tmx",
]
