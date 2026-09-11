"""#28's procgen kit: BSP, Wave Function Collapse, graph, and Poisson-disc generation.

`bsp.py` is genre-agnostic (plain `Rect` regions, no "room"/"dungeon"
vocabulary); `dungeon.py`'s room-carving and critical-path corridor
connection is the roguelike recipe #28 names as the flagship example --
"RTS map-gen and TD path-gen are others on the same algos" built the same
way, on `bsp.py` directly, not through `dungeon.py`. `wfc.py`, `graph.py`,
and `poisson.py` are three more independent generation strategies over
the same kind of primitives -- caller-defined states/rules, plain
points/edges, or a spacing constraint -- no tile or room-type vocabulary
baked into any of them.

`poisson.py` is the "constraint-placement" family scoped to its
well-defined piece, minimum-spacing sampling; a generic
frequency/dependency/exclusion rule-checking engine is a separate,
heavier concern, deliberately deferred rather than built here.
"""

from pyguara.kits.procgen.bsp import BspNode, split_bsp
from pyguara.kits.procgen.dungeon import DungeonLayout, carve_room, generate_dungeon
from pyguara.kits.procgen.graph import Edge, build_graph, scatter_points
from pyguara.kits.procgen.poisson import poisson_disc_sample
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
    "poisson_disc_sample",
    "scatter_points",
    "split_bsp",
]
