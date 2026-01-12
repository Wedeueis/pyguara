"""A* pathfinding implementation for grid-based navigation.

Provides efficient pathfinding with multiple heuristic options.
"""

import heapq
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

from pyguara.common.types import Vector2


class Heuristic(Enum):
    """Available heuristic functions for pathfinding."""

    MANHATTAN = auto()  # |dx| + |dy| - for 4-directional movement
    EUCLIDEAN = auto()  # sqrt(dx^2 + dy^2) - for any movement
    DIAGONAL = auto()  # max(|dx|, |dy|) - for 8-directional movement
    OCTILE = auto()  # Diagonal distance with sqrt(2) cost


def manhattan_distance(start: tuple[int, int], goal: tuple[int, int]) -> float:
    """Manhattan distance heuristic (4-directional).

    Args:
        start: Starting position (x, y)
        goal: Goal position (x, y)

    Returns:
        Manhattan distance
    """
    return abs(start[0] - goal[0]) + abs(start[1] - goal[1])


def euclidean_distance(start: tuple[int, int], goal: tuple[int, int]) -> float:
    """Euclidean distance heuristic (any direction).

    Args:
        start: Starting position (x, y)
        goal: Goal position (x, y)

    Returns:
        Euclidean distance
    """
    dx = start[0] - goal[0]
    dy = start[1] - goal[1]
    return (dx * dx + dy * dy) ** 0.5


def diagonal_distance(start: tuple[int, int], goal: tuple[int, int]) -> float:
    """Diagonal distance heuristic (8-directional).

    Args:
        start: Starting position (x, y)
        goal: Goal position (x, y)

    Returns:
        Diagonal distance (Chebyshev distance)
    """
    dx = abs(start[0] - goal[0])
    dy = abs(start[1] - goal[1])
    return max(dx, dy)


def octile_distance(start: tuple[int, int], goal: tuple[int, int]) -> float:
    """Octile distance heuristic (8-directional with diagonal cost).

    Uses sqrt(2) for diagonal movement cost.

    Args:
        start: Starting position (x, y)
        goal: Goal position (x, y)

    Returns:
        Octile distance
    """
    dx = abs(start[0] - goal[0])
    dy = abs(start[1] - goal[1])
    return (dx + dy) + (1.414 - 2) * min(dx, dy)


# Map enum to function
HEURISTIC_FUNCTIONS: dict[
    Heuristic, Callable[[tuple[int, int], tuple[int, int]], float]
] = {
    Heuristic.MANHATTAN: manhattan_distance,
    Heuristic.EUCLIDEAN: euclidean_distance,
    Heuristic.DIAGONAL: diagonal_distance,
    Heuristic.OCTILE: octile_distance,
}


@dataclass(order=True)
class PathNode:
    """Node in the A* search.

    Uses f_cost for priority queue ordering.
    """

    f_cost: float
    position: tuple[int, int] = field(compare=False)
    g_cost: float = field(default=0.0, compare=False)
    h_cost: float = field(default=0.0, compare=False)
    parent: Optional["PathNode"] = field(default=None, compare=False, repr=False)


class GridMap:
    """Grid-based map for pathfinding.

    Supports obstacles and different movement patterns.
    """

    def __init__(self, width: int, height: int):
        """Initialize grid map.

        Args:
            width: Grid width in cells
            height: Grid height in cells
        """
        self.width = width
        self.height = height
        self._obstacles: set[tuple[int, int]] = set()

    def add_obstacle(self, x: int, y: int) -> None:
        """Mark a cell as obstacle.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            self._obstacles.add((x, y))

    def remove_obstacle(self, x: int, y: int) -> None:
        """Remove obstacle from cell.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        self._obstacles.discard((x, y))

    def is_walkable(self, x: int, y: int) -> bool:
        """Check if a cell is walkable.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            True if cell is in bounds and not an obstacle
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        return (x, y) not in self._obstacles

    def get_neighbors(
        self, x: int, y: int, allow_diagonal: bool = True
    ) -> list[tuple[int, int]]:
        """Get walkable neighbors of a cell.

        Args:
            x: X coordinate
            y: Y coordinate
            allow_diagonal: If True, include diagonal neighbors

        Returns:
            List of walkable neighbor positions
        """
        neighbors = []

        # Cardinal directions (4-directional)
        directions = [
            (0, -1),  # North
            (1, 0),  # East
            (0, 1),  # South
            (-1, 0),  # West
        ]

        if allow_diagonal:
            # Add diagonal directions
            directions.extend(
                [
                    (1, -1),  # Northeast
                    (1, 1),  # Southeast
                    (-1, 1),  # Southwest
                    (-1, -1),  # Northwest
                ]
            )

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if self.is_walkable(nx, ny):
                # For diagonal movement, check if adjacent cells are walkable
                # to prevent cutting corners
                if allow_diagonal and abs(dx) == 1 and abs(dy) == 1:
                    if not self.is_walkable(x + dx, y) or not self.is_walkable(
                        x, y + dy
                    ):
                        continue
                neighbors.append((nx, ny))

        return neighbors

    def clear_obstacles(self) -> None:
        """Remove all obstacles from the map."""
        self._obstacles.clear()


class AStar:
    """A* pathfinding algorithm.

    Finds optimal path from start to goal on a grid map.

    Example:
        >>> grid = GridMap(width=10, height=10)
        >>> grid.add_obstacle(5, 5)
        >>> pathfinder = AStar(grid)
        >>> path = pathfinder.find_path(
        ...     start=(0, 0),
        ...     goal=(9, 9),
        ...     heuristic=Heuristic.EUCLIDEAN
        ... )
    """

    def __init__(self, grid_map: GridMap):
        """Initialize A* pathfinder.

        Args:
            grid_map: Grid map to search on
        """
        self.grid_map = grid_map
        self._last_iterations = 0
        self._last_path_length = 0

    def find_path(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
        heuristic: Heuristic = Heuristic.EUCLIDEAN,
        allow_diagonal: bool = True,
    ) -> Optional[list[tuple[int, int]]]:
        """Find path from start to goal using A*.

        Args:
            start: Starting position (x, y)
            goal: Goal position (x, y)
            heuristic: Heuristic function to use
            allow_diagonal: Allow diagonal movement

        Returns:
            List of positions from start to goal, or None if no path
        """
        # Validate inputs
        if not self.grid_map.is_walkable(*start):
            return None
        if not self.grid_map.is_walkable(*goal):
            return None

        if start == goal:
            return [start]

        # Get heuristic function
        heuristic_func = HEURISTIC_FUNCTIONS[heuristic]

        # Initialize
        open_set: list[PathNode] = []
        closed_set: set[tuple[int, int]] = set()
        g_costs: dict[tuple[int, int], float] = {start: 0.0}

        # Add start node
        h_cost = heuristic_func(start, goal)
        start_node = PathNode(f_cost=h_cost, position=start, g_cost=0.0, h_cost=h_cost)
        heapq.heappush(open_set, start_node)

        iterations = 0

        while open_set:
            iterations += 1

            # Get node with lowest f_cost
            current = heapq.heappop(open_set)

            # Skip if already processed
            if current.position in closed_set:
                continue

            # Found goal
            if current.position == goal:
                self._last_iterations = iterations
                path = self._reconstruct_path(current)
                self._last_path_length = len(path)
                return path

            # Mark as processed
            closed_set.add(current.position)

            # Check neighbors
            for neighbor_pos in self.grid_map.get_neighbors(
                *current.position, allow_diagonal=allow_diagonal
            ):
                if neighbor_pos in closed_set:
                    continue

                # Calculate movement cost
                dx = abs(neighbor_pos[0] - current.position[0])
                dy = abs(neighbor_pos[1] - current.position[1])
                move_cost = 1.414 if (dx + dy) == 2 else 1.0  # Diagonal cost

                # Calculate g_cost
                tentative_g = current.g_cost + move_cost

                # Check if this path is better
                if neighbor_pos not in g_costs or tentative_g < g_costs[neighbor_pos]:
                    g_costs[neighbor_pos] = tentative_g
                    h_cost = heuristic_func(neighbor_pos, goal)
                    f_cost = tentative_g + h_cost

                    neighbor_node = PathNode(
                        f_cost=f_cost,
                        position=neighbor_pos,
                        g_cost=tentative_g,
                        h_cost=h_cost,
                        parent=current,
                    )
                    heapq.heappush(open_set, neighbor_node)

        # No path found
        self._last_iterations = iterations
        self._last_path_length = 0
        return None

    def _reconstruct_path(self, node: PathNode) -> list[tuple[int, int]]:
        """Reconstruct path from goal to start.

        Args:
            node: Goal node

        Returns:
            List of positions from start to goal
        """
        path = []
        current = node

        while current is not None:
            path.append(current.position)
            current = current.parent

        path.reverse()
        return path

    @property
    def last_iterations(self) -> int:
        """Get number of iterations in last pathfinding call."""
        return self._last_iterations

    @property
    def last_path_length(self) -> int:
        """Get length of last found path."""
        return self._last_path_length


def smooth_path(
    path: list[tuple[int, int]], grid_map: GridMap
) -> list[tuple[int, int]]:
    """Smooth path by removing unnecessary waypoints.

    Uses line-of-sight checks to skip intermediate points.

    Args:
        path: Original path
        grid_map: Grid map for collision checking

    Returns:
        Smoothed path
    """
    if len(path) <= 2:
        return path

    smoothed = [path[0]]
    current_idx = 0

    while current_idx < len(path) - 1:
        # Try to skip as many points as possible
        farthest_idx = current_idx + 1

        for test_idx in range(current_idx + 2, len(path)):
            if _has_line_of_sight(path[current_idx], path[test_idx], grid_map):
                farthest_idx = test_idx
            else:
                break

        smoothed.append(path[farthest_idx])
        current_idx = farthest_idx

    return smoothed


def _has_line_of_sight(
    start: tuple[int, int], end: tuple[int, int], grid_map: GridMap
) -> bool:
    """Check if there's a clear line of sight between two points.

    Uses Bresenham's line algorithm.

    Args:
        start: Starting position
        end: Ending position
        grid_map: Grid map for collision checking

    Returns:
        True if line of sight is clear
    """
    x0, y0 = start
    x1, y1 = end

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)

    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1

    err = dx - dy

    while True:
        if not grid_map.is_walkable(x0, y0):
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
    path: list[tuple[int, int]], cell_size: float, offset: Vector2 = Vector2.zero()
) -> list[Vector2]:
    """Convert grid path to world coordinates.

    Args:
        path: Grid path (cell coordinates)
        cell_size: Size of each grid cell in world units
        offset: World offset (default: 0, 0)

    Returns:
        Path in world coordinates
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
) -> tuple[int, int]:
    """Convert world coordinates to grid position.

    Args:
        position: World position
        cell_size: Size of each grid cell in world units
        offset: World offset (default: 0, 0)

    Returns:
        Grid position (x, y)
    """
    grid_x = int((position.x - offset.x) / cell_size)
    grid_y = int((position.y - offset.y) / cell_size)
    return (grid_x, grid_y)
