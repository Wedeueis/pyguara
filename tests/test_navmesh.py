"""Tests for navigation mesh system."""

import pytest

from pyguara.ai.navmesh import (
    NavMesh,
    NavMeshEdge,
    NavMeshPathfinder,
    NavMeshPolygon,
    create_rectangle_polygon,
)
from pyguara.common.types import Vector2


class TestNavMeshPolygon:
    """Test NavMeshPolygon functionality."""

    def test_create_triangle(self):
        """Should create triangle polygon."""
        vertices = [Vector2(0, 0), Vector2(10, 0), Vector2(5, 10)]
        polygon = NavMeshPolygon(id=0, vertices=vertices)

        assert polygon.id == 0
        assert len(polygon.vertices) == 3

    def test_create_square(self):
        """Should create square polygon."""
        vertices = [
            Vector2(0, 0),
            Vector2(10, 0),
            Vector2(10, 10),
            Vector2(0, 10),
        ]
        polygon = NavMeshPolygon(id=0, vertices=vertices)

        assert len(polygon.vertices) == 4

    def test_too_few_vertices_raises_error(self):
        """Polygon must have at least 3 vertices."""
        with pytest.raises(ValueError, match="at least 3 vertices"):
            NavMeshPolygon(id=0, vertices=[Vector2(0, 0), Vector2(10, 0)])

    def test_center_calculation(self):
        """Center should be calculated as centroid."""
        vertices = [
            Vector2(0, 0),
            Vector2(10, 0),
            Vector2(10, 10),
            Vector2(0, 10),
        ]
        polygon = NavMeshPolygon(id=0, vertices=vertices)

        assert polygon.center == Vector2(5, 5)

    def test_contains_point_inside(self):
        """Should detect point inside polygon."""
        vertices = [
            Vector2(0, 0),
            Vector2(10, 0),
            Vector2(10, 10),
            Vector2(0, 10),
        ]
        polygon = NavMeshPolygon(id=0, vertices=vertices)

        assert polygon.contains_point(Vector2(5, 5))
        assert polygon.contains_point(Vector2(1, 1))
        assert polygon.contains_point(Vector2(9, 9))

    def test_contains_point_outside(self):
        """Should detect point outside polygon."""
        vertices = [
            Vector2(0, 0),
            Vector2(10, 0),
            Vector2(10, 10),
            Vector2(0, 10),
        ]
        polygon = NavMeshPolygon(id=0, vertices=vertices)

        assert not polygon.contains_point(Vector2(-1, 5))
        assert not polygon.contains_point(Vector2(11, 5))
        assert not polygon.contains_point(Vector2(5, -1))
        assert not polygon.contains_point(Vector2(5, 11))

    def test_contains_point_on_edge(self):
        """Point on edge behavior (implementation-dependent)."""
        vertices = [
            Vector2(0, 0),
            Vector2(10, 0),
            Vector2(10, 10),
            Vector2(0, 10),
        ]
        polygon = NavMeshPolygon(id=0, vertices=vertices)

        # Points very close to inside are clearly inside
        assert polygon.contains_point(Vector2(0.1, 5))
        assert polygon.contains_point(Vector2(5, 0.1))

    def test_get_shared_edge_adjacent(self):
        """Should find shared edge between adjacent polygons."""
        # Two squares sharing an edge
        poly1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        poly2 = NavMeshPolygon(
            id=1,
            vertices=[
                Vector2(10, 0),
                Vector2(20, 0),
                Vector2(20, 10),
                Vector2(10, 10),
            ],
        )

        edge = poly1.get_shared_edge(poly2)

        assert edge is not None
        start, end = edge
        # Shared edge is from (10, 0) to (10, 10) or vice versa
        assert (start == Vector2(10, 0) and end == Vector2(10, 10)) or (
            start == Vector2(10, 10) and end == Vector2(10, 0)
        )

    def test_get_shared_edge_not_adjacent(self):
        """Should return None for non-adjacent polygons."""
        poly1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        poly2 = NavMeshPolygon(
            id=1,
            vertices=[
                Vector2(20, 0),
                Vector2(30, 0),
                Vector2(30, 10),
                Vector2(20, 10),
            ],
        )

        edge = poly1.get_shared_edge(poly2)

        assert edge is None


class TestNavMeshEdge:
    """Test NavMeshEdge functionality."""

    def test_create_edge(self):
        """Should create edge between polygons."""
        edge = NavMeshEdge(
            poly1_id=0,
            poly2_id=1,
            start=Vector2(10, 0),
            end=Vector2(10, 10),
        )

        assert edge.poly1_id == 0
        assert edge.poly2_id == 1

    def test_midpoint_calculation(self):
        """Midpoint should be calculated correctly."""
        edge = NavMeshEdge(
            poly1_id=0,
            poly2_id=1,
            start=Vector2(0, 0),
            end=Vector2(10, 0),
        )

        assert edge.midpoint == Vector2(5, 0)

    def test_length_calculation(self):
        """Length should be calculated correctly."""
        edge = NavMeshEdge(
            poly1_id=0,
            poly2_id=1,
            start=Vector2(0, 0),
            end=Vector2(10, 0),
        )

        assert edge.length == pytest.approx(10.0)

    def test_length_diagonal(self):
        """Should calculate diagonal length correctly."""
        edge = NavMeshEdge(
            poly1_id=0,
            poly2_id=1,
            start=Vector2(0, 0),
            end=Vector2(3, 4),
        )

        assert edge.length == pytest.approx(5.0)


class TestNavMesh:
    """Test NavMesh functionality."""

    def test_create_empty_navmesh(self):
        """Should create empty navmesh."""
        navmesh = NavMesh()

        assert navmesh.polygon_count == 0
        assert navmesh.edge_count == 0

    def test_add_polygon(self):
        """Should add polygon to navmesh."""
        navmesh = NavMesh()
        polygon = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )

        navmesh.add_polygon(polygon)

        assert navmesh.polygon_count == 1

    def test_add_duplicate_id_raises_error(self):
        """Adding polygon with duplicate ID should raise error."""
        navmesh = NavMesh()
        polygon1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        polygon2 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(20, 0),
                Vector2(30, 0),
                Vector2(30, 10),
                Vector2(20, 10),
            ],
        )

        navmesh.add_polygon(polygon1)

        with pytest.raises(ValueError, match="already exists"):
            navmesh.add_polygon(polygon2)

    def test_remove_polygon(self):
        """Should remove polygon from navmesh."""
        navmesh = NavMesh()
        polygon = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        navmesh.add_polygon(polygon)

        navmesh.remove_polygon(0)

        assert navmesh.polygon_count == 0

    def test_get_polygon(self):
        """Should retrieve polygon by ID."""
        navmesh = NavMesh()
        polygon = NavMeshPolygon(
            id=5,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        navmesh.add_polygon(polygon)

        retrieved = navmesh.get_polygon(5)

        assert retrieved is not None
        assert retrieved.id == 5

    def test_get_nonexistent_polygon(self):
        """Getting nonexistent polygon should return None."""
        navmesh = NavMesh()

        retrieved = navmesh.get_polygon(999)

        assert retrieved is None

    def test_get_polygon_at(self):
        """Should find polygon containing a point."""
        navmesh = NavMesh()
        polygon = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        navmesh.add_polygon(polygon)

        found = navmesh.get_polygon_at(Vector2(5, 5))

        assert found is not None
        assert found.id == 0

    def test_get_polygon_at_outside(self):
        """Should return None when point is outside all polygons."""
        navmesh = NavMesh()
        polygon = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        navmesh.add_polygon(polygon)

        found = navmesh.get_polygon_at(Vector2(50, 50))

        assert found is None

    def test_build_connections(self):
        """Should build connections between adjacent polygons."""
        navmesh = NavMesh()

        # Two adjacent squares
        poly1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        poly2 = NavMeshPolygon(
            id=1,
            vertices=[
                Vector2(10, 0),
                Vector2(20, 0),
                Vector2(20, 10),
                Vector2(10, 10),
            ],
        )

        navmesh.add_polygon(poly1)
        navmesh.add_polygon(poly2)
        navmesh.build_connections()

        assert navmesh.edge_count == 1
        assert 1 in poly1.neighbors
        assert 0 in poly2.neighbors

    def test_build_connections_no_adjacency(self):
        """Should not create edges for non-adjacent polygons."""
        navmesh = NavMesh()

        # Two separate squares
        poly1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        poly2 = NavMeshPolygon(
            id=1,
            vertices=[
                Vector2(20, 0),
                Vector2(30, 0),
                Vector2(30, 10),
                Vector2(20, 10),
            ],
        )

        navmesh.add_polygon(poly1)
        navmesh.add_polygon(poly2)
        navmesh.build_connections()

        assert navmesh.edge_count == 0
        assert len(poly1.neighbors) == 0
        assert len(poly2.neighbors) == 0

    def test_get_neighbors(self):
        """Should get neighbors of a polygon."""
        navmesh = NavMesh()

        poly1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        poly2 = NavMeshPolygon(
            id=1,
            vertices=[
                Vector2(10, 0),
                Vector2(20, 0),
                Vector2(20, 10),
                Vector2(10, 10),
            ],
        )

        navmesh.add_polygon(poly1)
        navmesh.add_polygon(poly2)
        navmesh.build_connections()

        neighbors = navmesh.get_neighbors(0)

        assert len(neighbors) == 1
        assert 1 in neighbors

    def test_get_edge_between(self):
        """Should get edge between two polygons."""
        navmesh = NavMesh()

        poly1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        poly2 = NavMeshPolygon(
            id=1,
            vertices=[
                Vector2(10, 0),
                Vector2(20, 0),
                Vector2(20, 10),
                Vector2(10, 10),
            ],
        )

        navmesh.add_polygon(poly1)
        navmesh.add_polygon(poly2)
        navmesh.build_connections()

        edge = navmesh.get_edge_between(0, 1)

        assert edge is not None
        assert edge.poly1_id == 0
        assert edge.poly2_id == 1

    def test_clear(self):
        """Should clear all polygons and edges."""
        navmesh = NavMesh()

        poly = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        navmesh.add_polygon(poly)

        navmesh.clear()

        assert navmesh.polygon_count == 0
        assert navmesh.edge_count == 0


class TestNavMeshPathfinder:
    """Test NavMeshPathfinder functionality."""

    def test_pathfinding_same_polygon(self):
        """Path within same polygon should be straight line."""
        navmesh = NavMesh()
        poly = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(20, 0),
                Vector2(20, 20),
                Vector2(0, 20),
            ],
        )
        navmesh.add_polygon(poly)
        navmesh.build_connections()

        pathfinder = NavMeshPathfinder(navmesh)
        path = pathfinder.find_path(Vector2(5, 5), Vector2(15, 15))

        assert path is not None
        assert len(path) == 2
        assert path[0] == Vector2(5, 5)
        assert path[1] == Vector2(15, 15)

    def test_pathfinding_two_polygons(self):
        """Path through two adjacent polygons."""
        navmesh = NavMesh()

        poly1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        poly2 = NavMeshPolygon(
            id=1,
            vertices=[
                Vector2(10, 0),
                Vector2(20, 0),
                Vector2(20, 10),
                Vector2(10, 10),
            ],
        )

        navmesh.add_polygon(poly1)
        navmesh.add_polygon(poly2)
        navmesh.build_connections()

        pathfinder = NavMeshPathfinder(navmesh)
        path = pathfinder.find_path(Vector2(5, 5), Vector2(15, 5))

        assert path is not None
        assert len(path) >= 2
        assert path[0] == Vector2(5, 5)
        assert path[-1] == Vector2(15, 5)

    def test_pathfinding_start_outside(self):
        """Should return None when start is outside navmesh."""
        navmesh = NavMesh()
        poly = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        navmesh.add_polygon(poly)
        navmesh.build_connections()

        pathfinder = NavMeshPathfinder(navmesh)
        path = pathfinder.find_path(Vector2(50, 50), Vector2(5, 5))

        assert path is None

    def test_pathfinding_goal_outside(self):
        """Should return None when goal is outside navmesh."""
        navmesh = NavMesh()
        poly = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        navmesh.add_polygon(poly)
        navmesh.build_connections()

        pathfinder = NavMeshPathfinder(navmesh)
        path = pathfinder.find_path(Vector2(5, 5), Vector2(50, 50))

        assert path is None

    def test_pathfinding_no_connection(self):
        """Should return None when polygons are not connected."""
        navmesh = NavMesh()

        # Two separate polygons
        poly1 = NavMeshPolygon(
            id=0,
            vertices=[
                Vector2(0, 0),
                Vector2(10, 0),
                Vector2(10, 10),
                Vector2(0, 10),
            ],
        )
        poly2 = NavMeshPolygon(
            id=1,
            vertices=[
                Vector2(20, 0),
                Vector2(30, 0),
                Vector2(30, 10),
                Vector2(20, 10),
            ],
        )

        navmesh.add_polygon(poly1)
        navmesh.add_polygon(poly2)
        navmesh.build_connections()

        pathfinder = NavMeshPathfinder(navmesh)
        path = pathfinder.find_path(Vector2(5, 5), Vector2(25, 5))

        assert path is None

    def test_pathfinding_complex_mesh(self):
        """Path through multiple connected polygons."""
        navmesh = NavMesh()

        # Create a row of connected squares
        for i in range(5):
            poly = NavMeshPolygon(
                id=i,
                vertices=[
                    Vector2(i * 10, 0),
                    Vector2((i + 1) * 10, 0),
                    Vector2((i + 1) * 10, 10),
                    Vector2(i * 10, 10),
                ],
            )
            navmesh.add_polygon(poly)

        navmesh.build_connections()

        pathfinder = NavMeshPathfinder(navmesh)
        path = pathfinder.find_path(Vector2(5, 5), Vector2(45, 5))

        assert path is not None
        assert path[0] == Vector2(5, 5)
        assert path[-1] == Vector2(45, 5)


class TestHelperFunctions:
    """Test helper functions."""

    def test_create_rectangle_polygon(self):
        """Should create rectangular polygon."""
        polygon = create_rectangle_polygon(0, 10.0, 20.0, 30.0, 40.0)

        assert polygon.id == 0
        assert len(polygon.vertices) == 4
        assert polygon.vertices[0] == Vector2(10, 20)
        assert polygon.vertices[1] == Vector2(40, 20)
        assert polygon.vertices[2] == Vector2(40, 60)
        assert polygon.vertices[3] == Vector2(10, 60)

    def test_create_rectangle_at_origin(self):
        """Should create rectangle at origin."""
        polygon = create_rectangle_polygon(0, 0.0, 0.0, 10.0, 10.0)

        assert polygon.vertices[0] == Vector2(0, 0)
        assert polygon.center == Vector2(5, 5)
