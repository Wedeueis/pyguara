"""#28's procgen kit, scoped to BSP partitioning + the dungeon recipe.

`bsp.py` is genre-agnostic (plain `Rect` regions, no "room"/"dungeon"
vocabulary); `dungeon.py`'s room-carving and critical-path corridor
connection is the roguelike recipe #28 names as the flagship example --
"RTS map-gen and TD path-gen are others on the same algos" built the same
way, on `bsp.py` directly, not through `dungeon.py`.

Wave Function Collapse, general graph-based generation, and
constraint-placement are real, separately-sized algorithm families #28
also names -- deliberately deferred to their own passes, not built here.
"""

from pyguara.kits.procgen.bsp import BspNode, split_bsp
from pyguara.kits.procgen.dungeon import DungeonLayout, carve_room, generate_dungeon

__all__ = [
    "BspNode",
    "DungeonLayout",
    "carve_room",
    "generate_dungeon",
    "split_bsp",
]
