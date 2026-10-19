"""Navigation mesh (navmesh) system for polygon-based pathfinding.

Provides navigation meshes for complex 2D environments with irregular geometry.
Suitable for platformers, top-down games with obstacles, etc.
"""

from dataclasses import dataclass, field

from pyguara.common.types import Vector2


@dataclass
class NavMeshPolygon:
    """A convex polygon representing a walkable area.

    Polygons are connected via shared edges (portals).
    """

    id: int
    vertices: list[Vector2]
    center: Vector2 = field(init=False)
    neighbors: list[int] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        """Calculate polygon center."""
        if len(self.vertices) < 3:
            raise ValueError("Polygon must have at least 3 vertices")

        # Calculate centroid
        x_sum = sum(v.x for v in self.vertices)
        y_sum = sum(v.y for v in self.vertices)
        count = len(self.vertices)
        self.center = Vector2(x_sum / count, y_sum / count)

    def contains_point(self, point: Vector2) -> bool:
        """Check if point is inside polygon using ray casting.

        Args:
            point: Point to test

        Returns:
            True if point is inside polygon
        """
        x, y = point.x, point.y
        n = len(self.vertices)
        inside = False

        p1 = self.vertices[0]
        for i in range(1, n + 1):
            p2 = self.vertices[i % n]

            if y > min(p1.y, p2.y):
                if y <= max(p1.y, p2.y):
                    if x <= max(p1.x, p2.x):
                        if p1.y != p2.y:
                            xinters = (y - p1.y) * (p2.x - p1.x) / (p2.y - p1.y) + p1.x
                        if p1.x == p2.x or x <= xinters:
                            inside = not inside
            p1 = p2

        return inside

    def get_shared_edge(
        self, other: "NavMeshPolygon"
    ) -> tuple[Vector2, Vector2] | None:
        """Find shared edge with another polygon.

        Args:
            other: Other polygon to check

        Returns:
            Tuple of (start, end) vertices of shared edge, or None
        """
        # Check each edge of this polygon
        for i in range(len(self.vertices)):
            v1 = self.vertices[i]
            v2 = self.vertices[(i + 1) % len(self.vertices)]

            # Check if this edge matches any edge in other polygon
            for j in range(len(other.vertices)):
                ov1 = other.vertices[j]
                ov2 = other.vertices[(j + 1) % len(other.vertices)]

                # Check if edges are the same (either direction)
                if (
                    _points_equal(v1, ov1)
                    and _points_equal(v2, ov2)
                    or _points_equal(v1, ov2)
                    and _points_equal(v2, ov1)
                ):
                    return (v1, v2)

        return None


@dataclass
class NavMeshEdge:
    """Connection between two navigation polygons.

    Represents a portal between adjacent walkable areas.
    """

    poly1_id: int
    poly2_id: int
    start: Vector2
    end: Vector2

    @property
    def midpoint(self) -> Vector2:
        """Get midpoint of the edge."""
        return Vector2((self.start.x + self.end.x) / 2, (self.start.y + self.end.y) / 2)

    @property
    def length(self) -> float:
        """Get length of the edge."""
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return float((dx * dx + dy * dy) ** 0.5)


class NavMesh:
    """Navigation mesh for polygon-based pathfinding.

    Manages a collection of convex polygons representing walkable areas
    and their connections.

    Example:
        >>> navmesh = NavMesh()
        >>> # Add walkable polygons
        >>> poly1 = NavMeshPolygon(
        ...     id=0,
        ...     vertices=[Vector2(0, 0), Vector2(10, 0), Vector2(10, 10), Vector2(0, 10)]
        ... )
        >>> navmesh.add_polygon(poly1)
        >>> # Build connectivity
        >>> navmesh.build_connections()
    """

    def __init__(self) -> None:
        """Initialize empty navmesh."""
        self._polygons: dict[int, NavMeshPolygon] = {}
        self._edges: list[NavMeshEdge] = []

    def add_polygon(self, polygon: NavMeshPolygon) -> None:
        """Add a polygon to the navmesh.

        Args:
            polygon: Polygon to add
        """
        if polygon.id in self._polygons:
            raise ValueError(f"Polygon with id {polygon.id} already exists")

        self._polygons[polygon.id] = polygon

    def remove_polygon(self, polygon_id: int) -> None:
        """Remove a polygon from the navmesh.

        Args:
            polygon_id: ID of polygon to remove
        """
        if polygon_id in self._polygons:
            del self._polygons[polygon_id]
            # Remove edges involving this polygon
            self._edges = [
                e
                for e in self._edges
                if e.poly1_id != polygon_id and e.poly2_id != polygon_id
            ]
            # Drop the now-dangling id from every remaining neighbor list, so
            # get_neighbors() never hands back an id get_polygon() can't resolve.
            for polygon in self._polygons.values():
                if polygon_id in polygon.neighbors:
                    polygon.neighbors.remove(polygon_id)

    def get_polygon(self, polygon_id: int) -> NavMeshPolygon | None:
        """Get polygon by ID.

        Args:
            polygon_id: Polygon ID

        Returns:
            Polygon or None if not found
        """
        return self._polygons.get(polygon_id)

    def get_polygon_at(self, point: Vector2) -> NavMeshPolygon | None:
        """Find which polygon contains a point.

        Args:
            point: Point to query

        Returns:
            Polygon containing the point, or None
        """
        for polygon in self._polygons.values():
            if polygon.contains_point(point):
                return polygon
        return None

    def build_connections(self) -> None:
        """Build connectivity between adjacent polygons.

        Finds shared edges and creates connections.
        Should be called after all polygons are added.
        """
        self._edges.clear()

        # Clear existing neighbor lists
        for polygon in self._polygons.values():
            polygon.neighbors.clear()

        # Check all pairs of polygons
        polygon_ids = list(self._polygons.keys())
        for i, id1 in enumerate(polygon_ids):
            poly1 = self._polygons[id1]

            for id2 in polygon_ids[i + 1 :]:
                poly2 = self._polygons[id2]

                # Check for shared edge
                shared_edge = poly1.get_shared_edge(poly2)
                if shared_edge:
                    # Add edge
                    edge = NavMeshEdge(
                        poly1_id=id1,
                        poly2_id=id2,
                        start=shared_edge[0],
                        end=shared_edge[1],
                    )
                    self._edges.append(edge)

                    # Add to neighbor lists
                    poly1.neighbors.append(id2)
                    poly2.neighbors.append(id1)

    def get_neighbors(self, polygon_id: int) -> list[int]:
        """Get IDs of neighboring polygons.

        Args:
            polygon_id: Polygon ID

        Returns:
            List of neighbor polygon IDs
        """
        polygon = self._polygons.get(polygon_id)
        return polygon.neighbors if polygon else []

    def get_edge_between(self, poly1_id: int, poly2_id: int) -> NavMeshEdge | None:
        """Get edge connecting two polygons.

        Args:
            poly1_id: First polygon ID
            poly2_id: Second polygon ID

        Returns:
            Edge connecting the polygons, or None
        """
        for edge in self._edges:
            if (edge.poly1_id == poly1_id and edge.poly2_id == poly2_id) or (
                edge.poly1_id == poly2_id and edge.poly2_id == poly1_id
            ):
                return edge
        return None

    @property
    def polygon_count(self) -> int:
        """Get number of polygons in navmesh."""
        return len(self._polygons)

    @property
    def edge_count(self) -> int:
        """Get number of edges in navmesh."""
        return len(self._edges)

    def clear(self) -> None:
        """Remove all polygons and edges."""
        self._polygons.clear()
        self._edges.clear()


class NavMeshPathfinder:
    """A* pathfinding on navigation meshes, with string-pulling.

    Two stages. A* over the polygon adjacency graph finds *which*
    polygons to cross; the funnel algorithm then pulls a string through
    their shared edges to find the shortest route inside that corridor.

    The second stage used to be walking the polygon centres, which is a
    route and a poor one -- it detours to the middle of every cell it
    passes through and emits a waypoint per cell. Measured with this
    module's own helpers: an L-shaped corridor of five square cells came
    out 22% longer than the shortest path through its inner corner, and a
    straight ten-cell corridor produced ten waypoints for a straight
    line. Both are two or three waypoints now, at the optimal length.
    """

    def __init__(self, navmesh: NavMesh):
        """Initialize pathfinder.

        Args:
            navmesh: Navigation mesh to search
        """
        self.navmesh = navmesh

    def find_path(self, start: Vector2, goal: Vector2) -> list[Vector2] | None:
        """Find path from start to goal.

        Args:
            start: Starting position
            goal: Goal position

        Returns:
            Waypoints from start to goal, or None if either end is off
            the mesh. Interior waypoints are mesh **vertices** -- the
            corners the corridor bends around -- so `get_polygon_at()`
            may report one as outside: `NavMeshPolygon.contains_point`
            excludes part of its own boundary, and a corner is on the
            boundary of every polygon meeting there. The *segments*
            between waypoints run inside the mesh, which is the property
            that matters to something following the path.
        """
        # Find starting and goal polygons
        start_poly = self.navmesh.get_polygon_at(start)
        goal_poly = self.navmesh.get_polygon_at(goal)

        if not start_poly or not goal_poly:
            return None

        # If same polygon, straight line
        if start_poly.id == goal_poly.id:
            return [start, goal]

        # Find polygon path using A*
        polygon_path = self._find_polygon_path(start_poly.id, goal_poly.id)
        if not polygon_path:
            return None

        # Convert polygon path to waypoint path
        return self._create_waypoint_path(start, goal, polygon_path)

    def _find_polygon_path(self, start_id: int, goal_id: int) -> list[int] | None:
        """Find path through polygons using A*.

        Args:
            start_id: Starting polygon ID
            goal_id: Goal polygon ID

        Returns:
            List of polygon IDs forming path, or None
        """
        import heapq
        from itertools import count

        # A* on polygon graph. The counter breaks priority ties without ever
        # comparing polygon ids, keeping the pop order stable and independent
        # of id values.
        counter = count()
        open_set: list[tuple[float, int, int]] = [(0.0, next(counter), start_id)]
        came_from: dict[int, int] = {}
        g_score: dict[int, float] = {start_id: 0.0}

        start_poly = self.navmesh.get_polygon(start_id)
        goal_poly = self.navmesh.get_polygon(goal_id)

        if not start_poly or not goal_poly:
            return None

        while open_set:
            _, _, current_id = heapq.heappop(open_set)

            if current_id == goal_id:
                # Reconstruct path
                path = [current_id]
                while current_id in came_from:
                    current_id = came_from[current_id]
                    path.append(current_id)
                path.reverse()
                return path

            current_poly = self.navmesh.get_polygon(current_id)
            if not current_poly:
                continue

            current_g = g_score[current_id]

            for neighbor_id in current_poly.neighbors:
                neighbor_poly = self.navmesh.get_polygon(neighbor_id)
                if not neighbor_poly:
                    continue

                # Calculate tentative g_score (distance between centers)
                dx = neighbor_poly.center.x - current_poly.center.x
                dy = neighbor_poly.center.y - current_poly.center.y
                distance = (dx * dx + dy * dy) ** 0.5

                tentative_g = current_g + distance

                if neighbor_id not in g_score or tentative_g < g_score[neighbor_id]:
                    came_from[neighbor_id] = current_id
                    g_score[neighbor_id] = tentative_g

                    # Heuristic: distance to goal
                    dx = goal_poly.center.x - neighbor_poly.center.x
                    dy = goal_poly.center.y - neighbor_poly.center.y
                    h = (dx * dx + dy * dy) ** 0.5

                    f = tentative_g + h
                    heapq.heappush(open_set, (f, next(counter), neighbor_id))

        return None

    def _create_waypoint_path(
        self, start: Vector2, goal: Vector2, polygon_path: list[int]
    ) -> list[Vector2]:
        """Pull the polygon path straight with the funnel algorithm.

        A* returns the *polygons* to cross, not a route. Walking their
        centres is a route, and a poor one: it takes a detour to the
        middle of every cell it passes through and emits a waypoint per
        cell. Measured on this module's own helpers, an L-shaped corridor
        of five square cells came out **22% longer** than the shortest
        two-leg path through the inner corner, and a straight ten-cell
        corridor produced ten waypoints for what is a straight line.

        The funnel ("simple stupid funnel", Mononen) walks the sequence of
        portals -- the shared edges between consecutive polygons -- keeping
        a left and a right bound from the current apex. While a new portal
        endpoint narrows the funnel it is adopted; when the two bounds
        cross, the vertex they crossed over is a genuine corner, it becomes
        the next apex, and the scan restarts from there. What comes out is
        the shortest path inside the polygon corridor, bending only at
        actual corners.

        The portal data this needs already existed -- `get_edge_between`
        and `NavMeshEdge` -- which is why this is a change to one method
        rather than to the mesh.

        Args:
            start: Starting position.
            goal: Goal position.
            polygon_path: Polygon IDs from A*, start to goal.

        Returns:
            Waypoints from `start` to `goal`, bending only where the
            corridor forces it. Falls back to the polygon centres if any
            portal is missing, which would mean a mesh whose adjacency and
            whose edges disagree.
        """
        portals = self._portals(start, goal, polygon_path)
        if portals is None:
            return self._centre_path(start, goal, polygon_path)
        return _pull_string(portals)

    def _portals(
        self, start: Vector2, goal: Vector2, polygon_path: list[int]
    ) -> list[tuple[Vector2, Vector2]] | None:
        """Build the left/right portal sequence the funnel walks.

        Each portal is the edge shared by two consecutive polygons, with
        its endpoints ordered left-then-right **relative to the direction
        of travel**. `NavMeshEdge` stores its endpoints in whatever order
        the two polygons happened to be compared in, which carries no
        orientation at all, so the ordering is decided here from the sign
        of the cross product with the step direction.

        Args:
            start: Starting position; becomes a degenerate first portal.
            goal: Goal position; becomes a degenerate last portal.
            polygon_path: Polygon IDs from A*.

        Returns:
            The portals, or None if the mesh could not supply one -- the
            caller falls back rather than returning a path with a gap in
            it.
        """
        portals: list[tuple[Vector2, Vector2]] = [(start, start)]
        previous = start
        for first_id, second_id in zip(polygon_path, polygon_path[1:], strict=False):
            edge = self.navmesh.get_edge_between(first_id, second_id)
            second = self.navmesh.get_polygon(second_id)
            if edge is None or second is None:
                return None
            portals.append(_orient_portal(edge, previous, second.center))
            previous = second.center
        portals.append((goal, goal))
        return portals

    def _centre_path(
        self, start: Vector2, goal: Vector2, polygon_path: list[int]
    ) -> list[Vector2]:
        """Return the old centre-walking path, as a fallback.

        Reached only when `get_edge_between` cannot find a portal for a
        pair of polygons A* says are adjacent, which means the mesh's
        neighbour lists and its edge list disagree. A worse path is a
        better answer there than no path.

        Args:
            start: Starting position.
            goal: Goal position.
            polygon_path: Polygon IDs from A*.

        Returns:
            Start, each intermediate polygon's centre, goal.
        """
        waypoints = [start]
        for poly_id in polygon_path[1:-1]:
            polygon = self.navmesh.get_polygon(poly_id)
            if polygon:
                waypoints.append(polygon.center)
        waypoints.append(goal)
        return waypoints


def create_rectangle_polygon(
    polygon_id: int, x: float, y: float, width: float, height: float
) -> NavMeshPolygon:
    """Create a rectangular polygon.

    Helper function for common case.

    Args:
        polygon_id: Unique polygon ID
        x: Left edge X coordinate
        y: Top edge Y coordinate
        width: Rectangle width
        height: Rectangle height

    Returns:
        NavMeshPolygon representing the rectangle
    """
    vertices = [
        Vector2(x, y),
        Vector2(x + width, y),
        Vector2(x + width, y + height),
        Vector2(x, y + height),
    ]
    return NavMeshPolygon(id=polygon_id, vertices=vertices)


def _triangle_area_2(a: Vector2, b: Vector2, c: Vector2) -> float:
    """Twice the signed area of triangle `abc`.

    The sign is all the funnel uses: it says which side of the ray `a->b`
    the point `c` falls on, and comparing two of them says whether the
    funnel narrowed or crossed over. Twice the area rather than the area
    because the halving would be divided out of every comparison.

    Args:
        a: The apex.
        b: One bound.
        c: The point being tested.

    Returns:
        A signed value; zero when the three are collinear.
    """
    return (c.x - a.x) * (b.y - a.y) - (b.x - a.x) * (c.y - a.y)


def _orient_portal(
    edge: "NavMeshEdge", from_point: Vector2, to_point: Vector2
) -> tuple[Vector2, Vector2]:
    """Order a portal's endpoints left-then-right for the direction crossed.

    `NavMeshEdge` records its endpoints in whichever order the two
    polygons were compared in, so it carries no orientation. The funnel
    needs one: its whole method is comparing "has the left bound crossed
    the right", and a portal handed over the wrong way round turns a
    corner the wrong way.

    Args:
        edge: The shared edge.
        from_point: Where the step is coming from.
        to_point: Where it is going.

    Returns:
        `(left, right)` for that direction of travel. A portal exactly
        collinear with the step is returned unchanged -- it has no left
        and right, and the funnel treats a zero area as "on the bound",
        which is correct for one.
    """
    step_x = to_point.x - from_point.x
    step_y = to_point.y - from_point.y
    side = step_x * (edge.start.y - from_point.y) - step_y * (
        edge.start.x - from_point.x
    )
    if side > 0:
        return (edge.start, edge.end)
    return (edge.end, edge.start)


def _pull_string(portals: list[tuple[Vector2, Vector2]]) -> list[Vector2]:
    """Run the funnel over an oriented portal sequence.

    Mononen's "simple stupid funnel". The apex starts at the first
    portal, which is the degenerate `(start, start)`; both bounds start
    there too. Each portal either narrows a bound or crosses the other
    one, and a crossing means the vertex crossed over is a real corner:
    it is emitted, becomes the new apex, and the scan **restarts from its
    index** -- which is why this is a `while` rather than a `for`, and
    why the algorithm is linear despite appearing to backtrack.

    **Why the restart cannot spin.** A crossing is only possible once the
    bound being crossed has been tightened since the last restart, and a
    bound can only be tightened at a portal *after* the apex -- so
    `left_index`/`right_index` is always strictly greater than
    `apex_index` when a crossing fires, and the apex therefore advances
    every time. Remove either tightening branch and that stops holding:
    the apex sticks, `index` resets to the same place forever, and the
    function never returns. Both are sabotage-tested, and both show up
    as the suite timing out rather than as an assertion.

    Args:
        portals: `(left, right)` pairs, starting with `(start, start)`
            and ending with `(goal, goal)`.

    Returns:
        The pulled path, always beginning at the start and ending at the
        goal, with no two consecutive points equal.
    """
    apex = portals[0][0]
    left, right = apex, apex
    apex_index = left_index = right_index = 0
    path = [apex]

    index = 1
    while index < len(portals):
        new_left, new_right = portals[index]

        # Tighten the right bound, unless doing so would cross the left.
        if _triangle_area_2(apex, right, new_right) <= 0.0:
            if _points_equal(apex, right) or (
                _triangle_area_2(apex, left, new_right) > 0.0
            ):
                right, right_index = new_right, index
            else:
                # Crossed: the left bound is a corner.
                path.append(left)
                apex = left
                apex_index = left_index
                left = right = apex
                left_index = right_index = apex_index
                index = apex_index + 1
                continue

        # And the left bound, unless doing so would cross the right.
        if _triangle_area_2(apex, left, new_left) >= 0.0:
            if _points_equal(apex, left) or (
                _triangle_area_2(apex, right, new_left) < 0.0
            ):
                left, left_index = new_left, index
            else:
                path.append(right)
                apex = right
                apex_index = right_index
                left = right = apex
                left_index = right_index = apex_index
                index = apex_index + 1
                continue

        index += 1

    goal = portals[-1][0]
    if not _points_equal(path[-1], goal):
        path.append(goal)
    return _drop_collinear(path)


def _drop_collinear(path: list[Vector2], epsilon: float = 1e-9) -> list[Vector2]:
    """Remove waypoints that lie exactly on the line through their neighbours.

    The funnel emits a corner whenever its bounds cross, and they can
    cross over a vertex that happens to sit *on* the straight line it was
    already following -- a 4x4 open room gave `(1, 1) -> (30, 30) ->
    (39, 39)`, three points describing one straight segment. Dropping the
    middle changes the route by nothing and saves an agent a steering
    decision.

    The tolerance is deliberately tiny. A point merely *near* the line
    cannot be dropped: the segment that would replace it may leave the
    polygon corridor, and the whole value of the funnel is that its
    output provably does not.

    **Repeated points are collapsed first, and must be.** The funnel can
    emit the same corner twice -- it does, on a U-shaped corridor, when
    the bounds cross again at a portal that shares the apex's vertex --
    and a duplicate has zero area against *anything*. So the collinear
    test would see `A, A` as collinear with whatever came before, drop
    the real corner, and return a path straight through the wall the
    corner existed to go around. Measured on a comb-shaped mesh: the
    corner at (30, 20) vanished and the route cut across the gap.

    Args:
        path: The pulled path.
        epsilon: How close to collinear counts, as twice a triangle's
            area. Not a distance, so it scales with the triangle -- which
            is why it is set far below any coordinate the mesh will hold
            rather than tuned.

    Returns:
        The path with repeated and exactly-collinear interior points
        removed.
    """
    unique = [path[0]]
    for point in path[1:]:
        if not _points_equal(unique[-1], point):
            unique.append(point)
    if len(unique) < 3:
        return unique
    kept = [unique[0]]
    for previous, point, following in zip(unique, unique[1:], unique[2:], strict=False):
        if abs(_triangle_area_2(previous, point, following)) > epsilon:
            kept.append(point)
    kept.append(unique[-1])
    return kept


def _points_equal(p1: Vector2, p2: Vector2, epsilon: float = 0.001) -> bool:
    """Check if two points are equal within tolerance.

    Args:
        p1: First point
        p2: Second point
        epsilon: Tolerance for equality

    Returns:
        True if points are equal within epsilon
    """
    return abs(p1.x - p2.x) < epsilon and abs(p1.y - p2.y) < epsilon
