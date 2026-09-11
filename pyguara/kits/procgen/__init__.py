"""#28's procgen kit: BSP, Wave Function Collapse, and graph-based generation.

`bsp.py` is genre-agnostic (plain `Rect` regions, no "room"/"dungeon"
vocabulary); `dungeon.py`'s room-carving and critical-path corridor
connection is the roguelike recipe #28 names as the flagship example --
"RTS map-gen and TD path-gen are others on the same algos" built the same
way, on `bsp.py` directly, not through `dungeon.py`. `wfc.py` and
`graph.py` are two more independent generation strategies over the same
kind of primitives -- caller-defined states/rules and plain points/edges,
no tile or room-type vocabulary baked into either.

Constraint-placement is the remaining algorithm family #28 also names --
deliberately deferred to its own pass, not built here.
"""

from pyguara.kits.procgen.bsp import BspNode, split_bsp
from pyguara.kits.procgen.dungeon import DungeonLayout, carve_room, generate_dungeon
from pyguara.kits.procgen.graph import Edge, build_graph, scatter_points
from pyguara.kits.procgen.wfc import AdjacencyRule, WfcContradictionError, generate_wfc

__all__ = [
    "AdjacencyRule",
    "BspNode",
    "DungeonLayout",
    "Edge",
    "WfcContradictionError",
    "build_graph",
    "carve_room",
    "generate_dungeon",
    "generate_wfc",
    "scatter_points",
    "split_bsp",
]
