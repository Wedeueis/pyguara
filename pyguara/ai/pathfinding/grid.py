"""Grid-based graph implementation."""

import math
from typing import Iterator, Set, Tuple

from pyguara.ai.pathfinding.core import Graph, Heuristic

# GridNode is just an (x, y) tuple for efficiency
GridNode = Tuple[int, int]


class GridGraph(Graph[GridNode]):
    """A 2D grid graph supporting 4 or 8 directional movement."""

    def __init__(self, width: int, height: int, allow_diagonal: bool = True):
        """Initialize the grid graph."""
        self.width = width
        self.height = height
        self.allow_diagonal = allow_diagonal
        self.walls: Set[GridNode] = set()
        self.weights: dict[GridNode, float] = {}  # For terrain costs

    def in_bounds(self, node: GridNode) -> bool:
        """Check if node is within grid limits."""
        x, y = node
        return 0 <= x < self.width and 0 <= y < self.height

    def is_passable(self, node: GridNode) -> bool:
        """Check if node is not a wall."""
        return node not in self.walls

    def get_neighbors(self, node: GridNode) -> Iterator[GridNode]:
        """Yield valid neighbors."""
        x, y = node
        # Standard 4 directions
        dirs = [(1, 0), (0, 1), (-1, 0), (0, -1)]

        if self.allow_diagonal:
            # Add diagonals
            dirs.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])

        for dx, dy in dirs:
            next_node = (x + dx, y + dy)
            if self.in_bounds(next_node) and self.is_passable(next_node):
                yield next_node

    def cost(self, from_node: GridNode, to_node: GridNode) -> float:
        """Calculate movement cost, 1.0 orthogonal, 1.414 diagonal."""
        base_cost = self.weights.get(to_node, 1.0)

        # Heuristic check for diagonal movement
        dx = abs(from_node[0] - to_node[0])
        dy = abs(from_node[1] - to_node[1])

        multiplier = 1.414 if (dx + dy) == 2 else 1.0
        return base_cost * multiplier


class ManhattanDistance(Heuristic[GridNode]):
    """Manhattan distance heuristic (better for 4-way movement)."""

    def estimate(self, current: GridNode, goal: GridNode) -> float:
        """Estimate the Manhattan distance."""
        return abs(current[0] - goal[0]) + abs(current[1] - goal[1])


class EuclideanDistance(Heuristic[GridNode]):
    """Euclidean distance heuristic (better for 8-way/any angle)."""

    def estimate(self, current: GridNode, goal: GridNode) -> float:
        """Estimate the Euclidean distance."""
        return math.hypot(goal[0] - current[0], goal[1] - current[1])
