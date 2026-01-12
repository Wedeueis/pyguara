"""Navigation mesh (navmesh) system for polygon-based pathfinding.

Provides navigation meshes for complex 2D environments with irregular geometry.
Suitable for platformers, top-down games with obstacles, etc.
"""

from dataclasses import dataclass, field
from typing import Optional

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
    ) -> Optional[tuple[Vector2, Vector2]]:
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

    def get_polygon(self, polygon_id: int) -> Optional[NavMeshPolygon]:
        """Get polygon by ID.

        Args:
            polygon_id: Polygon ID

        Returns:
            Polygon or None if not found
        """
        return self._polygons.get(polygon_id)

    def get_polygon_at(self, point: Vector2) -> Optional[NavMeshPolygon]:
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

    def get_edge_between(self, poly1_id: int, poly2_id: int) -> Optional[NavMeshEdge]:
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
    """A* pathfinding on navigation meshes.

    Finds paths through connected polygons and smooths them
    using the funnel algorithm.
    """

    def __init__(self, navmesh: NavMesh):
        """Initialize pathfinder.

        Args:
            navmesh: Navigation mesh to search
        """
        self.navmesh = navmesh

    def find_path(self, start: Vector2, goal: Vector2) -> Optional[list[Vector2]]:
        """Find path from start to goal.

        Args:
            start: Starting position
            goal: Goal position

        Returns:
            List of waypoints from start to goal, or None if no path
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

    def _find_polygon_path(self, start_id: int, goal_id: int) -> Optional[list[int]]:
        """Find path through polygons using A*.

        Args:
            start_id: Starting polygon ID
            goal_id: Goal polygon ID

        Returns:
            List of polygon IDs forming path, or None
        """
        import heapq

        # A* on polygon graph
        open_set = [(0.0, start_id)]
        came_from: dict[int, int] = {}
        g_score: dict[int, float] = {start_id: 0.0}

        start_poly = self.navmesh.get_polygon(start_id)
        goal_poly = self.navmesh.get_polygon(goal_id)

        if not start_poly or not goal_poly:
            return None

        while open_set:
            _, current_id = heapq.heappop(open_set)

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
                    heapq.heappush(open_set, (f, neighbor_id))

        return None

    def _create_waypoint_path(
        self, start: Vector2, goal: Vector2, polygon_path: list[int]
    ) -> list[Vector2]:
        """Convert polygon path to waypoint path.

        Uses a simple approach: use polygon centers as waypoints.
        For production, consider implementing the funnel algorithm.

        Args:
            start: Starting position
            goal: Goal position
            polygon_path: List of polygon IDs

        Returns:
            List of waypoint positions
        """
        waypoints = [start]

        # Add polygon centers (skip first and last)
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
