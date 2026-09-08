"""Grid-based graph implementation."""

import math
from collections.abc import Iterator

from pyguara.common.types import Vector2

# GridNode is just an (x, y) tuple for efficiency
GridNode = tuple[int, int]


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
        x, y = node
        # Standard 4 directions
        dirs = [(1, 0), (0, 1), (-1, 0), (0, -1)]

        if self.allow_diagonal:
            # Add diagonals
            dirs.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])

        for dx, dy in dirs:
            next_node = (x + dx, y + dy)
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
        return abs(current[0] - goal[0]) + abs(current[1] - goal[1])


class EuclideanDistance:
    """Euclidean distance heuristic (better for 8-way/any angle)."""

    def estimate(self, current: GridNode, goal: GridNode) -> float:
        """Estimate the Euclidean distance."""
        return math.hypot(goal[0] - current[0], goal[1] - current[1])


class DiagonalDistance:
    """Diagonal (Chebyshev) distance heuristic (for 8-way movement)."""

    def estimate(self, current: GridNode, goal: GridNode) -> float:
        """Estimate the Chebyshev distance."""
        dx = abs(current[0] - goal[0])
        dy = abs(current[1] - goal[1])
        return max(dx, dy)


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
    x0, y0 = start
    x1, y1 = end

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)

    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1

    err = dx - dy

    while True:
        if not graph.is_passable((x0, y0)):
            return False

        if (x0, y0) == (x1, y1):
            return True

        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


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
    world_path = []
    for x, y in path:
        # Center of cell
        world_x = x * cell_size + cell_size / 2 + offset.x
        world_y = y * cell_size + cell_size / 2 + offset.y
        world_path.append(Vector2(world_x, world_y))
    return world_path


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
    # floor, not int(): int() truncates toward zero, so a world point left of
    # or above the grid origin (negative local coordinate -- common with a
    # non-zero offset) would land one cell too high and, for -cell_size < d < 0,
    # collapse onto cell 0 instead of -1.
    grid_x = math.floor((position.x - offset.x) / cell_size)
    grid_y = math.floor((position.y - offset.y) / cell_size)
    return (grid_x, grid_y)
