"""#28's procgen kit: BSP partitioning, the dungeon recipe, and Wave Function Collapse.

`bsp.py` is genre-agnostic (plain `Rect` regions, no "room"/"dungeon"
vocabulary); `dungeon.py`'s room-carving and critical-path corridor
connection is the roguelike recipe #28 names as the flagship example --
"RTS map-gen and TD path-gen are others on the same algos" built the same
way, on `bsp.py` directly, not through `dungeon.py`. `wfc.py` is a second,
independent generation strategy over the same kind of `Rect`/grid-cell
primitives -- caller-defined states and adjacency rules, no tile
vocabulary baked in.

General graph-based generation and constraint-placement are the remaining
algorithm families #28 also names -- deliberately deferred to their own
passes, not built here.
"""

from pyguara.kits.procgen.bsp import BspNode, split_bsp
from pyguara.kits.procgen.dungeon import DungeonLayout, carve_room, generate_dungeon
from pyguara.kits.procgen.wfc import AdjacencyRule, WfcContradictionError, generate_wfc

__all__ = [
    "AdjacencyRule",
    "BspNode",
    "DungeonLayout",
    "WfcContradictionError",
    "carve_room",
    "generate_dungeon",
    "generate_wfc",
    "split_bsp",
]
