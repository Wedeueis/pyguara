"""Tests for A* pathfinding system."""

import pytest

from pyguara.ai.pathfinding import (
    AStar,
    GridMap,
    Heuristic,
    diagonal_distance,
    euclidean_distance,
    manhattan_distance,
    octile_distance,
    path_to_world_coords,
    smooth_path,
    world_to_grid_coords,
)
from pyguara.common.types import Vector2


class TestHeuristicFunctions:
    """Test heuristic distance functions."""

    def test_manhattan_distance(self):
        """Manhattan distance should be sum of absolute differences."""
        assert manhattan_distance((0, 0), (3, 4)) == 7
        assert manhattan_distance((5, 5), (5, 5)) == 0
        assert manhattan_distance((0, 0), (10, 0)) == 10

    def test_euclidean_distance(self):
        """Euclidean distance should be straight-line distance."""
        assert euclidean_distance((0, 0), (3, 4)) == pytest.approx(5.0)
        assert euclidean_distance((0, 0), (0, 0)) == 0.0
        assert euclidean_distance((0, 0), (1, 1)) == pytest.approx(1.414, rel=0.01)

    def test_diagonal_distance(self):
        """Diagonal distance should be max of dx, dy."""
        assert diagonal_distance((0, 0), (3, 4)) == 4
        assert diagonal_distance((0, 0), (5, 3)) == 5
        assert diagonal_distance((0, 0), (0, 0)) == 0

    def test_octile_distance(self):
        """Octile distance should account for diagonal cost."""
        # Straight line
        assert octile_distance((0, 0), (5, 0)) == pytest.approx(5.0)
        # Pure diagonal
        assert octile_distance((0, 0), (5, 5)) == pytest.approx(5 * 1.414, rel=0.01)
        # Mixed
        dist = octile_distance((0, 0), (3, 5))
        assert dist > 0


class TestGridMap:
    """Test GridMap functionality."""

    def test_grid_creation(self):
        """GridMap should initialize with correct dimensions."""
        grid = GridMap(width=10, height=20)

        assert grid.width == 10
        assert grid.height == 20

    def test_all_cells_walkable_initially(self):
        """All cells should be walkable by default."""
        grid = GridMap(width=5, height=5)

        for x in range(5):
            for y in range(5):
                assert grid.is_walkable(x, y)

    def test_add_obstacle(self):
        """Should be able to add obstacles."""
        grid = GridMap(width=5, height=5)
        grid.add_obstacle(2, 3)

        assert not grid.is_walkable(2, 3)
        assert grid.is_walkable(2, 2)
        assert grid.is_walkable(3, 3)

    def test_remove_obstacle(self):
        """Should be able to remove obstacles."""
        grid = GridMap(width=5, height=5)
        grid.add_obstacle(2, 3)
        grid.remove_obstacle(2, 3)

        assert grid.is_walkable(2, 3)

    def test_out_of_bounds_not_walkable(self):
        """Out of bounds cells should not be walkable."""
        grid = GridMap(width=5, height=5)

        assert not grid.is_walkable(-1, 0)
        assert not grid.is_walkable(0, -1)
        assert not grid.is_walkable(5, 0)
        assert not grid.is_walkable(0, 5)

    def test_get_neighbors_cardinal(self):
        """Should get cardinal neighbors when diagonal disabled."""
        grid = GridMap(width=5, height=5)
        neighbors = grid.get_neighbors(2, 2, allow_diagonal=False)

        assert len(neighbors) == 4
        assert (2, 1) in neighbors  # North
        assert (3, 2) in neighbors  # East
        assert (2, 3) in neighbors  # South
        assert (1, 2) in neighbors  # West

    def test_get_neighbors_diagonal(self):
        """Should get all 8 neighbors when diagonal enabled."""
        grid = GridMap(width=5, height=5)
        neighbors = grid.get_neighbors(2, 2, allow_diagonal=True)

        assert len(neighbors) == 8

    def test_get_neighbors_corner(self):
        """Corner cells should have fewer neighbors."""
        grid = GridMap(width=5, height=5)
        neighbors = grid.get_neighbors(0, 0, allow_diagonal=True)

        assert len(neighbors) == 3  # Only SE, S, E

    def test_get_neighbors_with_obstacles(self):
        """Obstacles should block neighbors."""
        grid = GridMap(width=5, height=5)
        grid.add_obstacle(2, 1)  # North
        grid.add_obstacle(3, 2)  # East

        neighbors = grid.get_neighbors(2, 2, allow_diagonal=False)

        assert len(neighbors) == 2
        assert (2, 1) not in neighbors
        assert (3, 2) not in neighbors

    def test_diagonal_corner_cutting_prevention(self):
        """Diagonal movement should not cut corners."""
        grid = GridMap(width=5, height=5)
        grid.add_obstacle(3, 2)  # Block east
        grid.add_obstacle(2, 1)  # Block north

        neighbors = grid.get_neighbors(2, 2, allow_diagonal=True)

        # Should not include NE diagonal (3, 1) because path is blocked
        assert (3, 1) not in neighbors

    def test_clear_obstacles(self):
        """Should clear all obstacles."""
        grid = GridMap(width=5, height=5)
        grid.add_obstacle(1, 1)
        grid.add_obstacle(2, 2)
        grid.add_obstacle(3, 3)

        grid.clear_obstacles()

        assert grid.is_walkable(1, 1)
        assert grid.is_walkable(2, 2)
        assert grid.is_walkable(3, 3)


class TestAStar:
    """Test A* pathfinding algorithm."""

    def test_straight_line_path(self):
        """Should find straight line path when no obstacles."""
        grid = GridMap(width=10, height=10)
        pathfinder = AStar(grid)

        path = pathfinder.find_path(
            start=(0, 0), goal=(5, 0), heuristic=Heuristic.MANHATTAN
        )

        assert path is not None
        assert path[0] == (0, 0)
        assert path[-1] == (5, 0)
        assert len(path) == 6  # 0,1,2,3,4,5

    def test_diagonal_path(self):
        """Should find diagonal path when allowed."""
        grid = GridMap(width=10, height=10)
        pathfinder = AStar(grid)

        path = pathfinder.find_path(
            start=(0, 0),
            goal=(5, 5),
            heuristic=Heuristic.EUCLIDEAN,
            allow_diagonal=True,
        )

        assert path is not None
        assert path[0] == (0, 0)
        assert path[-1] == (5, 5)
        # Diagonal path should be shorter than cardinal-only
        assert len(path) <= 11

    def test_path_around_obstacle(self):
        """Should find path around obstacles."""
        grid = GridMap(width=10, height=10)
        # Create wall
        for y in range(1, 9):
            grid.add_obstacle(5, y)

        pathfinder = AStar(grid)
        path = pathfinder.find_path(start=(0, 5), goal=(9, 5))

        assert path is not None
        assert path[0] == (0, 5)
        assert path[-1] == (9, 5)
        # Path should go around the wall
        assert (5, 5) not in path

    def test_no_path_available(self):
        """Should return None when no path exists."""
        grid = GridMap(width=10, height=10)
        # Create complete wall
        for y in range(10):
            grid.add_obstacle(5, y)

        pathfinder = AStar(grid)
        path = pathfinder.find_path(start=(0, 5), goal=(9, 5))

        assert path is None

    def test_start_equals_goal(self):
        """Should return single-point path when start equals goal."""
        grid = GridMap(width=10, height=10)
        pathfinder = AStar(grid)

        path = pathfinder.find_path(start=(5, 5), goal=(5, 5))

        assert path == [(5, 5)]

    def test_start_blocked(self):
        """Should return None when start is blocked."""
        grid = GridMap(width=10, height=10)
        grid.add_obstacle(0, 0)

        pathfinder = AStar(grid)
        path = pathfinder.find_path(start=(0, 0), goal=(5, 5))

        assert path is None

    def test_goal_blocked(self):
        """Should return None when goal is blocked."""
        grid = GridMap(width=10, height=10)
        grid.add_obstacle(5, 5)

        pathfinder = AStar(grid)
        path = pathfinder.find_path(start=(0, 0), goal=(5, 5))

        assert path is None

    def test_different_heuristics(self):
        """Should work with different heuristics."""
        grid = GridMap(width=10, height=10)
        pathfinder = AStar(grid)

        for heuristic in [
            Heuristic.MANHATTAN,
            Heuristic.EUCLIDEAN,
            Heuristic.DIAGONAL,
            Heuristic.OCTILE,
        ]:
            path = pathfinder.find_path(start=(0, 0), goal=(5, 5), heuristic=heuristic)
            assert path is not None
            assert path[0] == (0, 0)
            assert path[-1] == (5, 5)

    def test_cardinal_only_movement(self):
        """Should only use cardinal directions when diagonal disabled."""
        grid = GridMap(width=10, height=10)
        pathfinder = AStar(grid)

        path = pathfinder.find_path(
            start=(0, 0),
            goal=(2, 2),
            heuristic=Heuristic.MANHATTAN,
            allow_diagonal=False,
        )

        assert path is not None
        # Check each step is cardinal (only one coord changes at a time)
        for i in range(len(path) - 1):
            curr = path[i]
            next_pos = path[i + 1]
            dx = abs(next_pos[0] - curr[0])
            dy = abs(next_pos[1] - curr[1])
            assert dx + dy == 1  # Exactly one step in one direction

    def test_statistics_tracking(self):
        """Should track pathfinding statistics."""
        grid = GridMap(width=10, height=10)
        pathfinder = AStar(grid)

        path = pathfinder.find_path(start=(0, 0), goal=(5, 5))

        assert pathfinder.last_iterations > 0
        assert pathfinder.last_path_length > 0
        assert pathfinder.last_path_length == len(path)

    def test_statistics_on_no_path(self):
        """Statistics should be valid even when no path found."""
        grid = GridMap(width=10, height=10)
        # Block completely
        for y in range(10):
            grid.add_obstacle(5, y)

        pathfinder = AStar(grid)
        path = pathfinder.find_path(start=(0, 0), goal=(9, 9))

        assert path is None
        assert pathfinder.last_iterations > 0
        assert pathfinder.last_path_length == 0

    def test_complex_maze(self):
        """Should find path through complex maze."""
        grid = GridMap(width=20, height=20)

        # Create maze-like structure
        for x in range(5, 15):
            grid.add_obstacle(x, 5)
        for y in range(5, 15):
            grid.add_obstacle(5, y)
        for x in range(5, 15):
            grid.add_obstacle(x, 14)
        # Leave openings
        grid.remove_obstacle(10, 5)
        grid.remove_obstacle(5, 10)

        pathfinder = AStar(grid)
        path = pathfinder.find_path(start=(0, 0), goal=(10, 10))

        assert path is not None
        assert path[0] == (0, 0)
        assert path[-1] == (10, 10)


class TestPathSmoothing:
    """Test path smoothing functionality."""

    def test_smooth_straight_path(self):
        """Straight path should remain unchanged."""
        grid = GridMap(width=10, height=10)
        path = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0)]

        smoothed = smooth_path(path, grid)

        assert smoothed == [(0, 0), (5, 0)]

    def test_smooth_empty_path(self):
        """Empty path should remain empty."""
        grid = GridMap(width=10, height=10)
        path = []

        smoothed = smooth_path(path, grid)

        assert smoothed == []

    def test_smooth_single_point(self):
        """Single point path should remain unchanged."""
        grid = GridMap(width=10, height=10)
        path = [(0, 0)]

        smoothed = smooth_path(path, grid)

        assert smoothed == [(0, 0)]

    def test_smooth_two_points(self):
        """Two point path should remain unchanged."""
        grid = GridMap(width=10, height=10)
        path = [(0, 0), (5, 5)]

        smoothed = smooth_path(path, grid)

        assert smoothed == [(0, 0), (5, 5)]

    def test_smooth_removes_unnecessary_waypoints(self):
        """Should remove waypoints with clear line of sight."""
        grid = GridMap(width=10, height=10)
        # L-shaped path that could be diagonal
        path = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]

        smoothed = smooth_path(path, grid)

        # Should skip intermediate points
        assert len(smoothed) < len(path)
        assert smoothed[0] == (0, 0)
        assert smoothed[-1] == (2, 2)

    def test_smooth_respects_obstacles(self):
        """Should not cut through obstacles."""
        grid = GridMap(width=10, height=10)
        grid.add_obstacle(1, 1)  # Block diagonal

        # Path goes around obstacle
        path = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]

        smoothed = smooth_path(path, grid)

        # Should keep waypoints that can't be skipped
        assert smoothed[0] == (0, 0)
        assert smoothed[-1] == (2, 2)
        # Can't go directly due to obstacle
        assert (1, 1) not in smoothed


class TestCoordinateConversion:
    """Test coordinate conversion utilities."""

    def test_world_to_grid_basic(self):
        """Should convert world coords to grid coords."""
        cell_size = 32.0
        world_pos = Vector2(64.0, 96.0)

        grid_pos = world_to_grid_coords(world_pos, cell_size)

        assert grid_pos == (2, 3)

    def test_world_to_grid_with_offset(self):
        """Should account for world offset."""
        cell_size = 32.0
        world_pos = Vector2(96.0, 128.0)
        offset = Vector2(32.0, 32.0)

        grid_pos = world_to_grid_coords(world_pos, cell_size, offset)

        assert grid_pos == (2, 3)

    def test_world_to_grid_origin(self):
        """Origin should map to (0, 0)."""
        cell_size = 32.0
        world_pos = Vector2(0.0, 0.0)

        grid_pos = world_to_grid_coords(world_pos, cell_size)

        assert grid_pos == (0, 0)

    def test_path_to_world_coords_basic(self):
        """Should convert grid path to world coords."""
        path = [(0, 0), (1, 0), (1, 1)]
        cell_size = 32.0

        world_path = path_to_world_coords(path, cell_size)

        assert len(world_path) == 3
        assert world_path[0] == Vector2(16.0, 16.0)  # Center of (0,0)
        assert world_path[1] == Vector2(48.0, 16.0)  # Center of (1,0)
        assert world_path[2] == Vector2(48.0, 48.0)  # Center of (1,1)

    def test_path_to_world_coords_with_offset(self):
        """Should account for world offset."""
        path = [(0, 0), (1, 1)]
        cell_size = 32.0
        offset = Vector2(100.0, 200.0)

        world_path = path_to_world_coords(path, cell_size, offset)

        assert world_path[0] == Vector2(116.0, 216.0)
        assert world_path[1] == Vector2(148.0, 248.0)

    def test_path_to_world_coords_empty(self):
        """Empty path should return empty list."""
        path = []
        cell_size = 32.0

        world_path = path_to_world_coords(path, cell_size)

        assert world_path == []

    def test_round_trip_conversion(self):
        """Converting world -> grid -> world should be consistent."""
        cell_size = 32.0
        original = Vector2(100.0, 150.0)

        # World -> Grid
        grid_pos = world_to_grid_coords(original, cell_size)

        # Grid -> World (center of cell)
        world_path = path_to_world_coords([grid_pos], cell_size)
        result = world_path[0]

        # Should be in same cell
        grid_result = world_to_grid_coords(result, cell_size)
        assert grid_result == grid_pos


class TestPathfindingIntegration:
    """Test complete pathfinding workflows."""

    def test_find_and_smooth_path(self):
        """Should find and smooth path."""
        grid = GridMap(width=20, height=20)
        pathfinder = AStar(grid)

        # Find path
        path = pathfinder.find_path(start=(0, 0), goal=(10, 10))
        assert path is not None

        # Smooth it
        smoothed = smooth_path(path, grid)
        assert len(smoothed) <= len(path)
        assert smoothed[0] == (0, 0)
        assert smoothed[-1] == (10, 10)

    def test_find_convert_and_smooth(self):
        """Complete workflow: find, convert, smooth."""
        grid = GridMap(width=20, height=20)
        pathfinder = AStar(grid)
        cell_size = 32.0

        # Add some obstacles
        for i in range(5, 15):
            grid.add_obstacle(10, i)
        grid.remove_obstacle(10, 10)  # Opening

        # Find path
        path = pathfinder.find_path(start=(0, 0), goal=(19, 19))
        assert path is not None

        # Smooth
        smoothed = smooth_path(path, grid)

        # Convert to world coords
        world_path = path_to_world_coords(smoothed, cell_size)

        assert len(world_path) > 0
        assert isinstance(world_path[0], Vector2)

    def test_pathfinding_with_moving_agent(self):
        """Simulate agent following path."""
        grid = GridMap(width=10, height=10)
        pathfinder = AStar(grid)

        # Find path
        path = pathfinder.find_path(start=(0, 0), goal=(9, 9))
        assert path is not None

        # Simulate movement along path
        current_pos = path[0]
        for waypoint in path[1:]:
            # Check distance to next waypoint
            dx = waypoint[0] - current_pos[0]
            dy = waypoint[1] - current_pos[1]
            dist = (dx * dx + dy * dy) ** 0.5

            # Should be reachable in one step
            assert dist <= 1.5  # Allow diagonal

            current_pos = waypoint

        # Should reach goal
        assert current_pos == (9, 9)

    def test_dynamic_obstacle_replanning(self):
        """Should handle dynamic obstacles by replanning."""
        grid = GridMap(width=10, height=10)
        pathfinder = AStar(grid)

        # Find initial path (straight line)
        path1 = pathfinder.find_path(start=(0, 0), goal=(9, 0), allow_diagonal=False)
        assert path1 is not None
        original_length = len(path1)

        # Add obstacle in the way
        grid.add_obstacle(5, 0)

        # Replan
        path2 = pathfinder.find_path(start=(0, 0), goal=(9, 0), allow_diagonal=False)
        assert path2 is not None
        assert (5, 0) not in path2
        # New path should be longer (goes around)
        assert len(path2) > original_length
