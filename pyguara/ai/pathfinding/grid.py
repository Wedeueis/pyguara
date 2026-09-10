"""Grid-based graph implementation."""

import math
from collections.abc import Iterator

from pyguara.common.grid import Cell
from pyguara.common.grid import cell_to_world as _cell_to_world
from pyguara.common.grid import chebyshev_distance as _chebyshev_distance
from pyguara.common.grid import line as _line
from pyguara.common.grid import manhattan_distance as _manhattan_distance
from pyguara.common.grid import neighbors4 as _neighbors4
from pyguara.common.grid import neighbors8 as _neighbors8
from pyguara.common.grid import world_to_cell as _world_to_cell
from pyguara.common.types import Vector2

# GridNode is just an (x, y) tuple for efficiency
GridNode = Cell


class GridGraph:
    """A 2D grid graph supporting 4 or 8 directional movement."""

    def __init__(self, width: int, height: int, allow_diagonal: bool = True):
        """Initialize the grid graph."""
        self.width = width
        self.height = height
        self.allow_diagonal = allow_diagonal
        self.walls: set[GridNode] = set()
        self.weights: dict[GridNode, float] = {}  # For terrain costs

    def in_bounds(self, node: GridNode) -> bool:
        """Check if node is within grid limits."""
        x, y = node
        return 0 <= x < self.width and 0 <= y < self.height

    def is_passable(self, node: GridNode) -> bool:
        """Check if node is not a wall."""
        return node not in self.walls

    def _is_walkable(self, node: GridNode) -> bool:
        """Check if a node is both in bounds and not a wall."""
        return self.in_bounds(node) and self.is_passable(node)

    def get_neighbors(self, node: GridNode) -> Iterator[GridNode]:
        """Yield valid neighbors.

        Diagonal moves refuse to cut a solid corner: both orthogonal cells
        flanking the diagonal must be walkable (in bounds and not a wall),
        matching the deleted `GridMap`'s behavior -- an out-of-bounds
        flanking cell blocks the diagonal too, not just an actual wall.
        """
        candidates = _neighbors8(node) if self.allow_diagonal else _neighbors4(node)

        x, y = node
        for next_node in candidates:
            dx, dy = next_node[0] - x, next_node[1] - y
            if not (self.in_bounds(next_node) and self.is_passable(next_node)):
                continue

            if abs(dx) == 1 and abs(dy) == 1:
                if not self._is_walkable((x + dx, y)) or not self._is_walkable(
                    (x, y + dy)
                ):
                    continue

            yield next_node

    def cost(self, from_node: GridNode, to_node: GridNode) -> float:
        """Calculate movement cost, 1.0 orthogonal, 1.414 diagonal."""
        base_cost = self.weights.get(to_node, 1.0)

        # Heuristic check for diagonal movement
        dx = abs(from_node[0] - to_node[0])
        dy = abs(from_node[1] - to_node[1])

        multiplier = 1.414 if (dx + dy) == 2 else 1.0
        return base_cost * multiplier


class ManhattanDistance:
    """Manhattan distance heuristic (better for 4-way movement)."""

    def estimate(self, current: GridNode, goal: GridNode) -> float:
        """Estimate the Manhattan distance."""
        return _manhattan_distance(current, goal)


class EuclideanDistance:
    """Euclidean distance heuristic (better for 8-way/any angle)."""

    def estimate(self, current: GridNode, goal: GridNode) -> float:
        """Estimate the Euclidean distance."""
        return math.hypot(goal[0] - current[0], goal[1] - current[1])


class DiagonalDistance:
    """Diagonal (Chebyshev) distance heuristic (for 8-way movement)."""

    def estimate(self, current: GridNode, goal: GridNode) -> float:
        """Estimate the Chebyshev distance."""
        return _chebyshev_distance(current, goal)


class OctileDistance:
    """Octile distance heuristic (diagonal distance with sqrt(2) cost)."""

    def estimate(self, current: GridNode, goal: GridNode) -> float:
        """Estimate the octile distance."""
        dx = abs(current[0] - goal[0])
        dy = abs(current[1] - goal[1])
        return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)


def smooth_path(path: list[GridNode], graph: GridGraph) -> list[GridNode]:
    """Smooth a grid path by removing unnecessary waypoints.

    Uses line-of-sight checks to skip intermediate points.

    Args:
        path: Original path.
        graph: Grid graph for collision checking.

    Returns:
        Smoothed path.
    """
    if len(path) <= 2:
        return path

    smoothed = [path[0]]
    current_idx = 0

    while current_idx < len(path) - 1:
        # Try to skip as many points as possible
        farthest_idx = current_idx + 1

        for test_idx in range(current_idx + 2, len(path)):
            if _has_line_of_sight(path[current_idx], path[test_idx], graph):
                farthest_idx = test_idx
            else:
                break

        smoothed.append(path[farthest_idx])
        current_idx = farthest_idx

    return smoothed


def _has_line_of_sight(start: GridNode, end: GridNode, graph: GridGraph) -> bool:
    """Check if there's a clear line of sight between two grid nodes.

    Uses Bresenham's line algorithm.

    Args:
        start: Starting node.
        end: Ending node.
        graph: Grid graph for collision checking.

    Returns:
        True if line of sight is clear.
    """
    return all(graph.is_passable(cell) for cell in _line(start, end))


def path_to_world_coords(
    path: list[GridNode], cell_size: float, offset: Vector2 = Vector2.zero()
) -> list[Vector2]:
    """Convert grid path to world coordinates.

    Args:
        path: Grid path (cell coordinates).
        cell_size: Size of each grid cell in world units.
        offset: World offset (default: 0, 0).

    Returns:
        Path in world coordinates (cell centers).
    """
    return [_cell_to_world(cell, cell_size, offset) for cell in path]


def world_to_grid_coords(
    position: Vector2, cell_size: float, offset: Vector2 = Vector2.zero()
) -> GridNode:
    """Convert world coordinates to grid position.

    Args:
        position: World position.
        cell_size: Size of each grid cell in world units.
        offset: World offset (default: 0, 0).

    Returns:
        Grid position (x, y).
    """
    return _world_to_cell(position, cell_size, offset)
