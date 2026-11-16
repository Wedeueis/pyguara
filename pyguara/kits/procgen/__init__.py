"""The procgen kit: BSP, WFC, graph, Delaunay, Poisson-disc and placement.

None of the algorithms has room or tile vocabulary:

- `bsp.py` partitions plain `Rect` regions. `dungeon.py` is the
  roguelike recipe on top of it.
- `wfc.py` collapses caller-defined states under adjacency rules.
- `graph.py` and `delaunay.py` connect scattered points; the second
  only joins neighbours, so no edge crosses open space.
- `poisson.py` picks spots with a minimum spacing, and `placement.py`
  decides what goes in each slot under the caller's rules.
"""

from pyguara.kits.procgen.bsp import BspNode, split_bsp
from pyguara.kits.procgen.delaunay import (
    Triangle,
    build_graph_delaunay,
    delaunay_edges,
    delaunay_triangles,
)
from pyguara.kits.procgen.dungeon import DungeonLayout, carve_room, generate_dungeon
from pyguara.kits.procgen.graph import Edge, build_graph, scatter_points
from pyguara.kits.procgen.placement import (
    DependencyCycleError,
    Excludes,
    ForbidsTag,
    MaxCount,
    MaxPerGroup,
    MinSpacing,
    PlacementRequest,
    PlacementResult,
    PlacementRule,
    PlacementState,
    Requires,
    RequiresTag,
    Slot,
    place_items,
)
from pyguara.kits.procgen.poisson import poisson_disc_sample
from pyguara.kits.procgen.wfc import AdjacencyRule, WfcContradictionError, generate_wfc

__all__ = [
    "AdjacencyRule",
    "BspNode",
    "DependencyCycleError",
    "DungeonLayout",
    "Edge",
    "Excludes",
    "ForbidsTag",
    "MaxCount",
    "MaxPerGroup",
    "MinSpacing",
    "PlacementRequest",
    "PlacementResult",
    "PlacementRule",
    "PlacementState",
    "Requires",
    "RequiresTag",
    "Slot",
    "Triangle",
    "WfcContradictionError",
    "build_graph",
    "build_graph_delaunay",
    "carve_room",
    "delaunay_edges",
    "delaunay_triangles",
    "generate_dungeon",
    "generate_wfc",
    "place_items",
    "poisson_disc_sample",
    "scatter_points",
    "split_bsp",
]
