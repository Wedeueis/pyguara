"""Tests for navigation mesh system."""

import math

import pytest

from pyguara.ai.navmesh import (
    NavMesh,
    NavMeshEdge,
    NavMeshPathfinder,
    NavMeshPolygon,
    _drop_collinear,
    _orient_portal,
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

    def test_remove_polygon_prunes_dangling_neighbor_ids(self):
        """A removed polygon's id must not linger in its ex-neighbors' lists.

        ``get_neighbors`` is public; a stale id there is one nobody can
        resolve back to a polygon.
        """
        navmesh = NavMesh()
        for i, x in enumerate((0.0, 100.0, 200.0)):
            navmesh.add_polygon(create_rectangle_polygon(i, x, 0.0, 100.0, 100.0))
        navmesh.build_connections()
        assert navmesh.get_neighbors(1) == [0, 2]

        navmesh.remove_polygon(2)

        assert navmesh.get_neighbors(1) == [0]
        assert navmesh.get_neighbors(0) == [1]
        # And every listed neighbor still resolves.
        for poly_id in (0, 1):
            for neighbor_id in navmesh.get_neighbors(poly_id):
                assert navmesh.get_polygon(neighbor_id) is not None

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


def _grid_mesh(cells: list[tuple[int, int]], cell: float = 10.0) -> NavMesh:
    """A mesh of unit square cells at the given grid coordinates."""
    mesh = NavMesh()
    for index, (column, row) in enumerate(cells):
        mesh.add_polygon(
            create_rectangle_polygon(index, column * cell, row * cell, cell, cell)
        )
    mesh.build_connections()
    return mesh


def _length(path: list[Vector2]) -> float:
    return sum(
        math.hypot(b.x - a.x, b.y - a.y) for a, b in zip(path, path[1:], strict=False)
    )


_ON_MESH_TOLERANCE = 0.05
"""How far off a polygon a sampled path point may be and still count.

`NavMeshPolygon.contains_point` is a ray cast, and it excludes part of
its own boundary -- so a point exactly on a wall reports as outside every
polygon that meets there. A string-pulled path runs **along** walls by
construction: that is what pulling it tight does. Without a tolerance,
the correct answer for a U-shaped corridor fails, because one whole leg
of it lies on the line x = 30.

0.05 against cells ten units across is three orders of magnitude smaller
than the corridor, so it admits wall-hugging and still catches a cut
through solid space -- the one this suite actually saw was several units
deep.
"""


def _on_mesh(mesh: NavMesh, point: Vector2) -> bool:
    """Whether `point` is on the mesh, counting its boundary.

    Probes the point itself and four neighbours a hair away, because a
    point on a shared edge is inside neither polygon as far as
    `contains_point` is concerned, but a hair to either side of it is
    inside one of them.
    """
    offsets = (
        (0.0, 0.0),
        (_ON_MESH_TOLERANCE, 0.0),
        (-_ON_MESH_TOLERANCE, 0.0),
        (0.0, _ON_MESH_TOLERANCE),
        (0.0, -_ON_MESH_TOLERANCE),
    )
    return any(
        mesh.get_polygon_at(Vector2(point.x + dx, point.y + dy)) is not None
        for dx, dy in offsets
    )


def _samples_off_mesh(mesh: NavMesh, path: list[Vector2], per_leg: int = 50) -> int:
    """Count points *strictly inside* each leg that are off the mesh.

    The endpoints are skipped on purpose. A funnel waypoint is a mesh
    **vertex** -- the corner the corridor bends around -- so it sits on
    the boundary of every polygon meeting there, and `contains_point`
    excludes it. That is a property of the point test, not of the path;
    what matters to something walking the route is that the segments
    stay inside.
    """
    outside = 0
    for a, b in zip(path, path[1:], strict=False):
        for step in range(1, per_leg):
            t = step / per_leg
            point = Vector2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
            if not _on_mesh(mesh, point):
                outside += 1
    return outside


class TestTheFunnelPullsThePathStraight:
    """A* says which polygons to cross; it does not say where to walk.

    Walking their centres is a route and a poor one: it detours to the
    middle of every cell and emits a waypoint per cell. Measured before
    this changed, an L-shaped corridor of five square cells came out 22%
    longer than the shortest path through its inner corner, and a
    straight ten-cell corridor produced ten waypoints for a straight
    line.
    """

    @pytest.mark.parametrize("cells", [3, 5, 10, 20])
    def test_a_straight_corridor_is_two_waypoints(self, cells: int) -> None:
        mesh = _grid_mesh([(i, 0) for i in range(cells)])
        start, goal = Vector2(1, 5), Vector2(cells * 10 - 1, 5)

        path = NavMeshPathfinder(mesh).find_path(start, goal)

        assert path == [start, goal]

    @pytest.mark.parametrize("cells", [3, 5, 10])
    def test_a_straight_corridor_is_the_straight_line_length(self, cells: int) -> None:
        """Not merely fewer waypoints -- the shortest ones."""
        mesh = _grid_mesh([(i, 0) for i in range(cells)])
        start, goal = Vector2(1, 2), Vector2(cells * 10 - 1, 8)

        path = NavMeshPathfinder(mesh).find_path(start, goal)

        assert _length(path) == pytest.approx(
            math.hypot(goal.x - start.x, goal.y - start.y)
        )

    def test_an_l_corridor_bends_once_at_the_inner_corner(self) -> None:
        """Three cells east, then two south. The corner is (20, 10)."""
        mesh = _grid_mesh([(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)])
        start, goal = Vector2(1, 5), Vector2(25, 29)

        path = NavMeshPathfinder(mesh).find_path(start, goal)

        assert len(path) == 3
        assert path[1].x == pytest.approx(20.0)
        assert path[1].y == pytest.approx(10.0)

    def test_the_l_corridor_path_is_optimal(self) -> None:
        mesh = _grid_mesh([(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)])
        start, goal = Vector2(1, 5), Vector2(25, 29)
        corner = Vector2(20, 10)
        ideal = math.hypot(corner.x - start.x, corner.y - start.y) + math.hypot(
            goal.x - corner.x, goal.y - corner.y
        )

        path = NavMeshPathfinder(mesh).find_path(start, goal)

        assert _length(path) == pytest.approx(ideal)

    def test_a_corner_the_other_way_round_works_too(self) -> None:
        """The mirror image, which is what catches a portal orientation
        that happens to be right for one handedness only.

        `NavMeshEdge` stores its endpoints in whichever order the two
        polygons were compared in, so it carries no orientation at all.
        A funnel handed a portal the wrong way round turns the wrong way,
        and it would do so on exactly half the corners in a mesh.
        """
        mesh = _grid_mesh([(0, 2), (1, 2), (2, 2), (2, 1), (2, 0)])
        start, goal = Vector2(1, 25), Vector2(25, 1)
        corner = Vector2(20, 20)
        ideal = math.hypot(corner.x - start.x, corner.y - start.y) + math.hypot(
            goal.x - corner.x, goal.y - corner.y
        )

        path = NavMeshPathfinder(mesh).find_path(start, goal)

        assert len(path) == 3
        assert path[1].x == pytest.approx(20.0)
        assert path[1].y == pytest.approx(20.0)
        assert _length(path) == pytest.approx(ideal)

    def test_an_open_room_is_a_straight_diagonal(self) -> None:
        """Sixteen cells with nothing in the way; the answer is one line.

        A vertex lying exactly *on* that line still makes the funnel's
        bounds cross, so it was emitted as a corner -- three points
        describing one straight segment.
        """
        mesh = _grid_mesh([(x, y) for y in range(4) for x in range(4)])
        start, goal = Vector2(1, 1), Vector2(39, 39)

        path = NavMeshPathfinder(mesh).find_path(start, goal)

        assert path == [start, goal]

    def test_a_zigzag_still_reaches_the_goal(self) -> None:
        mesh = _grid_mesh([(0, 0), (1, 0), (1, 1), (2, 1), (2, 2), (3, 2)])
        start, goal = Vector2(1, 5), Vector2(35, 25)

        path = NavMeshPathfinder(mesh).find_path(start, goal)

        assert path[0] == start
        assert path[-1] == goal


class TestTheFunnelStaysInsideTheMesh:
    """The property that makes string-pulling safe rather than merely short.

    A shortcut that leaves the corridor is worse than a detour: it walks
    an agent through a wall.
    """

    @pytest.mark.parametrize(
        "cells,start,goal",
        [
            ([(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)], (1, 5), (25, 29)),
            ([(0, 2), (1, 2), (2, 2), (2, 1), (2, 0)], (1, 25), (25, 1)),
            ([(0, 0), (1, 0), (1, 1), (2, 1), (2, 2), (3, 2)], (1, 5), (35, 25)),
            ([(i, 0) for i in range(6)], (1, 1), (59, 9)),
            (
                [(0, 0), (1, 0), (1, 1), (2, 1), (2, 2), (3, 2), (3, 3)],
                (1, 5),
                (31, 35),
            ),
            (
                [(0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (2, 2), (1, 2)],
                (1, 1),
                (11, 21),
            ),
        ],
        ids=["l-south", "l-north", "zigzag", "long-corridor", "staircase", "comb"],
    )
    def test_every_leg_runs_inside_the_mesh(
        self,
        cells: list[tuple[int, int]],
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> None:
        mesh = _grid_mesh(cells)
        path = NavMeshPathfinder(mesh).find_path(Vector2(*start), Vector2(*goal))

        assert path is not None
        assert _samples_off_mesh(mesh, path) == 0

    def test_a_path_is_never_longer_than_the_centre_path_it_replaced(self) -> None:
        """The funnel can only tighten; it must never add distance."""
        cells = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
        mesh = _grid_mesh(cells)
        finder = NavMeshPathfinder(mesh)
        start, goal = Vector2(1, 5), Vector2(25, 29)

        pulled = finder.find_path(start, goal)
        polygon_path = finder._find_polygon_path(0, 4)
        centres = finder._centre_path(start, goal, polygon_path)

        assert _length(pulled) <= _length(centres)


class TestTheFunnelFallsBackRatherThanReturningAGap:
    """A mesh whose neighbour lists and edge list disagree."""

    def test_a_missing_portal_falls_back_to_the_polygon_centres(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mesh = _grid_mesh([(0, 0), (1, 0), (2, 0)])
        finder = NavMeshPathfinder(mesh)
        monkeypatch.setattr(mesh, "get_edge_between", lambda a, b: None)

        path = finder.find_path(Vector2(1, 5), Vector2(25, 5))

        # The middle polygon's centre, as before the funnel existed.
        assert path is not None
        assert len(path) == 3
        assert path[1].x == pytest.approx(15.0)

    def test_the_fallback_still_starts_and_ends_in_the_right_places(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mesh = _grid_mesh([(0, 0), (1, 0), (2, 0)])
        finder = NavMeshPathfinder(mesh)
        start, goal = Vector2(1, 5), Vector2(25, 5)
        monkeypatch.setattr(mesh, "get_edge_between", lambda a, b: None)

        path = finder.find_path(start, goal)

        assert path[0] == start
        assert path[-1] == goal


class TestThePortalOrientationHelper:
    """`NavMeshEdge` carries no orientation, so one has to be derived."""

    def test_it_puts_the_endpoints_in_a_consistent_order(self) -> None:
        edge = NavMeshEdge(0, 1, Vector2(10, 0), Vector2(10, 10))

        forward = _orient_portal(edge, Vector2(5, 5), Vector2(15, 5))
        backward = _orient_portal(edge, Vector2(15, 5), Vector2(5, 5))

        assert forward == (backward[1], backward[0])

    def test_the_stored_endpoint_order_does_not_matter(self) -> None:
        """Which is the point: it is an accident of how the mesh was built."""
        one_way = NavMeshEdge(0, 1, Vector2(10, 0), Vector2(10, 10))
        other_way = NavMeshEdge(0, 1, Vector2(10, 10), Vector2(10, 0))

        assert _orient_portal(one_way, Vector2(5, 5), Vector2(15, 5)) == (
            _orient_portal(other_way, Vector2(5, 5), Vector2(15, 5))
        )


class TestTheCollinearPrune:
    """Only exactly-collinear points go; a near-miss is load-bearing."""

    def test_an_exactly_collinear_point_is_dropped(self) -> None:
        path = [Vector2(0, 0), Vector2(5, 5), Vector2(10, 10)]

        assert _drop_collinear(path) == [Vector2(0, 0), Vector2(10, 10)]

    def test_a_point_off_the_line_is_kept(self) -> None:
        path = [Vector2(0, 0), Vector2(5, 6), Vector2(10, 10)]

        assert _drop_collinear(path) == path

    def test_a_point_barely_off_the_line_is_kept(self) -> None:
        """The segment replacing it might leave the corridor, and not
        leaving the corridor is the whole value of the funnel."""
        path = [Vector2(0, 0), Vector2(5, 5.0001), Vector2(10, 10)]

        assert _drop_collinear(path) == path

    def test_two_points_are_left_alone(self) -> None:
        path = [Vector2(0, 0), Vector2(10, 10)]

        assert _drop_collinear(path) == path


class TestTheFunnelRestartsFromEachNewApex:
    """The subtle line, and the one a reader is most likely to simplify.

    When the funnel's bounds cross, the vertex they crossed over becomes
    the new apex and the scan **restarts from that vertex's index** --
    `index = apex_index + 1`, not `index += 1`. Portals already passed
    can still constrain the path from the new apex, and skipping them is
    not a missed optimisation: it produces a path that leaves the mesh.

    Found by sabotage. Replacing the restart with a plain advance passed
    every other test in this file, because none of the shapes they use
    ever needs to look backwards.
    """

    STAIRCASE = [(0, 0), (1, 0), (1, 1), (2, 1), (2, 2), (3, 2), (3, 3)]
    COMB = [(0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (2, 2), (1, 2)]

    def test_a_staircase_path_does_not_cut_through_a_wall(self) -> None:
        """Without the restart this took a *shorter* route -- through the
        corner at roughly (18.5, 20), which is solid. A shortcut that
        leaves the corridor is worse than any detour."""
        mesh = _grid_mesh(self.STAIRCASE)

        path = NavMeshPathfinder(mesh).find_path(Vector2(1, 5), Vector2(31, 35))

        assert path is not None
        assert _samples_off_mesh(mesh, path, per_leg=200) == 0

    def test_a_staircase_keeps_the_corner_that_makes_it_legal(self) -> None:
        mesh = _grid_mesh(self.STAIRCASE)

        path = NavMeshPathfinder(mesh).find_path(Vector2(1, 5), Vector2(31, 35))

        assert [(p.x, p.y) for p in path] == [
            (1, 5),
            (10.0, 10.0),
            (30.0, 30.0),
            (31, 35),
        ]

    def test_a_u_turn_keeps_both_of_its_corners(self) -> None:
        """A comb: east along the top, south down the right, back west.

        The funnel emits the corner at (30, 20) **twice** here -- the
        bounds cross again at a portal sharing the apex's own vertex --
        and a duplicate has zero area against anything, so the collinear
        prune read `A, A` as collinear and dropped the real corner. The
        route then went straight from (30, 10) to the goal, across the
        gap in the comb. Repeated points are collapsed before the prune
        for exactly this reason.
        """
        mesh = _grid_mesh(self.COMB)

        path = NavMeshPathfinder(mesh).find_path(Vector2(1, 1), Vector2(11, 21))

        assert [(p.x, p.y) for p in path] == [
            (1, 1),
            (30.0, 10.0),
            (30.0, 20.0),
            (11, 21),
        ]

    def test_the_u_turn_path_stays_on_the_mesh(self) -> None:
        mesh = _grid_mesh(self.COMB)

        path = NavMeshPathfinder(mesh).find_path(Vector2(1, 1), Vector2(11, 21))

        assert _samples_off_mesh(mesh, path, per_leg=200) == 0

    def test_a_pulled_path_never_repeats_a_waypoint(self) -> None:
        """Which is what made the prune dangerous in the first place."""
        mesh = _grid_mesh(self.COMB)

        path = NavMeshPathfinder(mesh).find_path(Vector2(1, 1), Vector2(11, 21))

        for first, second in zip(path, path[1:], strict=False):
            assert (first.x, first.y) != (second.x, second.y)
