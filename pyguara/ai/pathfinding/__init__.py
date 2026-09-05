"""Generic, Protocol-based pathfinding.

Provides a graph-agnostic A* solver (`AStarPathfinder`) plus a concrete grid
graph (`GridGraph`) with heuristics, path smoothing, and grid<->world
coordinate conversion.
"""

from pyguara.ai.pathfinding.astar import AStarPathfinder
from pyguara.ai.pathfinding.core import Graph, Heuristic, Node
from pyguara.ai.pathfinding.grid import (
    DiagonalDistance,
    EuclideanDistance,
    GridGraph,
    GridNode,
    ManhattanDistance,
    OctileDistance,
    path_to_world_coords,
    smooth_path,
    world_to_grid_coords,
)

__all__ = [
    "Graph",
    "Heuristic",
    "Node",
    "AStarPathfinder",
    "GridGraph",
    "GridNode",
    "ManhattanDistance",
    "EuclideanDistance",
    "DiagonalDistance",
    "OctileDistance",
    "smooth_path",
    "path_to_world_coords",
    "world_to_grid_coords",
]
