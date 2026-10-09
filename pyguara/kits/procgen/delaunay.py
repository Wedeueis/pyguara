"""Delaunay triangulation, and a graph built from it.

`build_graph()` grows a minimum spanning tree straight over the scattered
points, which has no notion of spatial locality beyond "nearest point not
yet in the tree". The result can carry a long edge clear across the map:
MST is free to join two distant clusters by whichever pair happens to be
closest, and nothing stops that pair being on opposite sides of open
space.

Triangulating first bounds the candidate edges to ones between genuine
neighbours -- a Delaunay edge exists only where the two points share a
Voronoi boundary -- so the MST drawn from them cannot take a shortcut
across the map, and the extra loop edges land between adjacent regions
rather than between whatever two points a dice roll picked.

#119 deliberately shipped the simpler version to avoid a geometry
dependency. Bowyer-Watson is about seventy lines, so this adds the
strategy without adding scipy.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.kits.procgen.graph import Edge, build_graph

Triangle = tuple[int, int, int]

# Circumcircle tests are determinants of *squared* distances, so they are
# degree 4 in the coordinates and lose precision fast. The tolerance is
# therefore scaled by the coordinate magnitude to the fourth, not fixed:
# an absolute epsilon is enormous for a cloud of unit-sized points and
# negligible for one spanning a million.
_RELATIVE_EPSILON = 1e-12

# Flipping to a fixpoint provably terminates -- each flip increases the
# triangulation's sorted angle vector -- but a precision tie could in
# principle make two flips undo each other forever. The cap turns that
# into a slightly non-Delaunay mesh rather than a hung frame, and is far
# above the O(n^2) flips the algorithm actually needs.
_MAX_FLIP_PASSES = 1000


def delaunay_triangles(points: Sequence[Vector2]) -> list[Triangle]:
    """Triangulate `points`, by hull fan then split-insert then flips.

    Not Bowyer-Watson, which needs a "super-triangle" enclosing the cloud
    and then discards the triangles touching it. That step is where the
    holes come from: a super vertex falling inside the circumcircle of a
    triangle of *real* points produces an edge from a real point to a
    super vertex through the middle of the cloud, and dropping it takes a
    genuine region along with it. Pushing the enclosure further out to
    avoid that destroys the precision of a determinant that is degree 4
    in the coordinates. Sweeping the margin from 3x to 1000x the bounding
    box, every value left some cloud with a hole -- the two failure modes
    trade against each other and neither disappears.

    So instead:

    1. Fan-triangulate the convex hull. Covers exactly the hull, with no
       phantom vertices to remove afterwards.
    2. Insert each remaining point by splitting the triangle (or the two
       triangles, for a point on a shared edge) that contains it.
    3. Flip every edge that is not locally Delaunay, to a fixpoint.

    Steps 2 and 3 both preserve the covered region *exactly*, so the mesh
    cannot develop a hole however the arithmetic goes, and Lawson's
    theorem says flipping to a fixpoint from any triangulation reaches
    the Delaunay one.

    Args:
        points: Node positions. Order fixes each point's index.

    Returns:
        Triangles as `(i, j, k)` index triples into `points`, each wound
        counter-clockwise. Empty when there are fewer than three points,
        or when every point is collinear -- a degenerate cloud has no
        triangulation, which is a fact about the input rather than a
        failure.
    """
    count = len(points)
    if count < 3:
        return []

    hull = _convex_hull(points)
    if len(hull) < 3:
        return []

    triangles = [
        _wind(points, (hull[0], hull[index], hull[index + 1]))
        for index in range(1, len(hull) - 1)
    ]

    placed: dict[tuple[float, float], int] = {
        (points[index].x, points[index].y): index for index in hull
    }
    for index in range(count):
        key = (points[index].x, points[index].y)
        if key in placed:
            # Already a vertex, or a duplicate of one. Inserting it would
            # fan zero-area triangles off an existing vertex and corrupt
            # every later circumcircle test. `build_graph_delaunay`'s
            # component fix-up is what keeps a duplicate reachable.
            continue
        placed[key] = index
        triangles = _split_insert(points, triangles, index)

    return _legalise(points, triangles)


def delaunay_edges(points: Sequence[Vector2]) -> list[Edge]:
    """Return the unique edges of `points`' Delaunay triangulation.

    Args:
        points: Node positions. Order fixes each point's index.

    Returns:
        Edges as `(i, j)` index pairs, `i < j`, sorted. Empty for a
        degenerate cloud.
    """
    edges: set[Edge] = set()
    for a, b, c in delaunay_triangles(points):
        edges.add((min(a, b), max(a, b)))
        edges.add((min(b, c), max(b, c)))
        edges.add((min(a, c), max(a, c)))
    return sorted(edges)


def build_graph_delaunay(
    points: Sequence[Vector2],
    rng: RandomStream,
    extra_edge_chance: float = 0.15,
    extra_edge_max_distance: float | None = None,
) -> list[Edge]:
    """Connect `points` into a graph over their Delaunay triangulation.

    The same shape `build_graph()` returns, and the same guarantee: every
    point is reachable from every other. The difference is which edges
    were ever candidates. Here they are triangulation edges only, so no
    edge joins two points that are not neighbours -- which is what keeps
    long skinny edges from cutting across open space.

    Falls back to `build_graph()` for a cloud with no triangulation at all
    (fewer than three points, or every point collinear). That is not a
    failure mode worth reporting: three points in a row have exactly one
    sensible graph and the Euclidean MST finds it.

    Args:
        points: Node positions. Order fixes each point's index.
        rng: Seeded stream driving the loop-edge rolls. The spanning tree
            is deterministic given `points`' order alone.
        extra_edge_chance: Probability of keeping each non-tree
            triangulation edge as a loop. 0.0 returns a pure spanning
            tree.
        extra_edge_max_distance: Only triangulation edges at or under this
            length are loop candidates. `None` considers all of them.

    Returns:
        Edges as `(i, j)` index pairs, `i < j`, spanning tree edges first,
        then extras sorted by length. Empty if `points` has fewer than 2
        entries.
    """
    count = len(points)
    if count < 2:
        return []

    candidates = delaunay_edges(points)
    if not candidates:
        return build_graph(points, rng, extra_edge_chance, extra_edge_max_distance)

    lengths = {
        edge: points[edge[0]].distance_to(points[edge[1]]) for edge in candidates
    }
    tree_edges = _minimum_spanning_forest(candidates, lengths, count)
    tree_edges.extend(_bridge_components(points, tree_edges, count))

    tree_edge_set = set(tree_edges)
    extras = sorted(
        (
            edge
            for edge in candidates
            if edge not in tree_edge_set
            and (
                extra_edge_max_distance is None
                or lengths[edge] <= extra_edge_max_distance
            )
        ),
        key=lambda edge: (lengths[edge], edge),
    )

    return tree_edges + [edge for edge in extras if rng.random() < extra_edge_chance]


# -- Internals --


def _convex_hull(points: Sequence[Vector2]) -> list[int]:
    """Return the convex hull's point indices, counter-clockwise.

    Andrew's monotone chain, popping on a non-left turn so a point lying
    *on* a hull edge is excluded. Those points are then inserted as
    ordinary interior points, where `_split_insert` already handles a
    point on an edge -- which is simpler than fanning a hull that
    contains collinear runs and then discarding the zero-area triangles.

    Args:
        points: The cloud.

    Returns:
        Hull indices in counter-clockwise order, or fewer than three
        entries when every point is collinear.
    """
    order = sorted(range(len(points)), key=lambda i: (points[i].x, points[i].y))

    def chain(sequence: list[int]) -> list[int]:
        built: list[int] = []
        for index in sequence:
            while len(built) >= 2 and (
                _cross(points[built[-2]], points[built[-1]], points[index]) <= 0
            ):
                built.pop()
            built.append(index)
        return built

    lower = chain(order)
    upper = chain(order[::-1])
    hull = lower[:-1] + upper[:-1]
    return hull if len(hull) >= 3 else []


def _contains(vertices: Sequence[Vector2], triangle: Triangle, point: Vector2) -> bool:
    """Report whether `point` is inside `triangle`, edges included.

    Edges included on purpose: a point on a shared edge is then found in
    *both* adjacent triangles, and `_split_insert` splits both, which is
    exactly the right answer for that case.

    Args:
        vertices: Coordinates, indexed by the triangle's entries.
        triangle: A counter-clockwise triangle.
        point: The point to test.

    Returns:
        True if inside or on the boundary.
    """
    a, b, c = (vertices[index] for index in triangle)
    scale = max(abs(a.x), abs(a.y), abs(b.x), abs(b.y), abs(c.x), abs(c.y), 1.0)
    tolerance = _RELATIVE_EPSILON * scale * scale
    return (
        _cross(a, b, point) >= -tolerance
        and _cross(b, c, point) >= -tolerance
        and _cross(c, a, point) >= -tolerance
    )


def _split_insert(
    vertices: Sequence[Vector2], triangles: list[Triangle], index: int
) -> list[Triangle]:
    """Add a point by splitting whatever triangles contain it.

    One triangle for an interior point (into three), two for a point on a
    shared edge (into four), one for a point on a hull edge (into two, the
    third fan triangle being degenerate and skipped).

    All three cases are the same operation: delete the containing
    triangles and fan the new point to the outline of the hole they
    leave. That outline is exactly their union's boundary, so the covered
    region does not change -- which is the property that makes a hole
    impossible regardless of how the arithmetic goes.

    Args:
        vertices: Coordinates.
        triangles: The current triangulation.
        index: The point to insert.

    Returns:
        The new triangulation. Unchanged if no triangle contains the
        point, which only happens for a point outside the hull -- and
        every point is inside its own cloud's hull.
    """
    point = vertices[index]
    containing = [
        triangle for triangle in triangles if _contains(vertices, triangle, point)
    ]
    if not containing:
        return triangles

    remaining = [triangle for triangle in triangles if triangle not in containing]
    for a, b in _boundary_edges(containing):
        if _cross(vertices[a], vertices[b], point) == 0:
            # The point lies on this boundary edge, so the fan triangle
            # would have no area. Skipping it is what keeps a degenerate
            # triangle -- whose circumcircle is undefined -- out of the
            # mesh.
            continue
        remaining.append(_wind(vertices, (a, b, index)))
    return remaining


def _legalise(vertices: Sequence[Vector2], triangles: list[Triangle]) -> list[Triangle]:
    """Flip every edge that is not locally Delaunay, until none is left.

    Lawson's algorithm: from *any* triangulation of a point set, flipping
    illegal edges terminates at the Delaunay triangulation. That is what
    lets step 1 be a plain hull fan, which is a valid triangulation but
    nothing like a Delaunay one.

    A flip swaps the diagonal of the quadrilateral two triangles form, so
    it preserves the covered region exactly. Only a *convex*
    quadrilateral can be flipped; a reflex one's diagonal is already
    locally Delaunay, so refusing to flip it is correct rather than a
    compromise.

    Args:
        vertices: Coordinates.
        triangles: A valid triangulation to legalise, modified in place.

    Returns:
        The legalised triangulation.
    """
    for _ in range(_MAX_FLIP_PASSES):
        if not _flip_one(vertices, triangles):
            return triangles
    return triangles


def _flip_one(vertices: Sequence[Vector2], triangles: list[Triangle]) -> bool:
    """Flip the first illegal, flippable edge found.

    One flip per pass, rebuilding the edge map each time. That is O(n)
    work per flip rather than maintaining adjacency through every
    change -- a worthwhile trade at the point counts a level graph uses,
    and the structure that would make it faster is also the structure
    that makes this kind of code wrong.

    Args:
        vertices: Coordinates.
        triangles: The triangulation, modified in place.

    Returns:
        True if an edge was flipped.
    """
    shared: dict[Edge, list[int]] = {}
    for position, (a, b, c) in enumerate(triangles):
        for first, second in ((a, b), (b, c), (c, a)):
            shared.setdefault((min(first, second), max(first, second)), []).append(
                position
            )

    for (a, b), owners in shared.items():
        if len(owners) != 2:
            continue
        left, right = owners
        apex = _opposite(triangles[left], (a, b))
        other = _opposite(triangles[right], (a, b))
        if apex is None or other is None:
            continue

        if not _in_circumcircle(vertices, triangles[left], vertices[other]):
            continue
        # The flipped diagonal is (apex, other); it only exists if the
        # quadrilateral is convex, which is exactly the condition that
        # both new triangles come out wound the same way round.
        if (
            _cross(vertices[apex], vertices[other], vertices[a])
            * _cross(vertices[apex], vertices[other], vertices[b])
            >= 0
        ):
            continue

        triangles[left] = _wind(vertices, (apex, other, a))
        triangles[right] = _wind(vertices, (apex, other, b))
        return True

    return False


def _opposite(triangle: Triangle, edge: Edge) -> int | None:
    """Return the triangle's vertex that is not on `edge`.

    Args:
        triangle: The triangle.
        edge: One of its edges.

    Returns:
        The third vertex, or None if the edge is not the triangle's.
    """
    rest = [vertex for vertex in triangle if vertex not in edge]
    return rest[0] if len(rest) == 1 else None


def _wind(vertices: Sequence[Vector2], triangle: Triangle) -> Triangle:
    """Return `triangle` wound counter-clockwise.

    Normalising the winding once is what lets `_in_circumcircle` read the
    determinant's sign directly instead of recomputing the orientation on
    every test.

    Args:
        vertices: Coordinates, indexed by the triangle's entries.
        triangle: The triple to orient.

    Returns:
        The same three indices, possibly reordered.
    """
    a, b, c = triangle
    if _cross(vertices[a], vertices[b], vertices[c]) < 0:
        return (a, c, b)
    return triangle


def _cross(a: Vector2, b: Vector2, c: Vector2) -> float:
    """Return twice the signed area of the triangle `a`, `b`, `c`.

    Args:
        a: First corner.
        b: Second corner.
        c: Third corner.

    Returns:
        Positive when the three turn counter-clockwise.
    """
    return (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)


def _in_circumcircle(
    vertices: Sequence[Vector2], triangle: Triangle, point: Vector2
) -> bool:
    """Report whether `point` lies inside `triangle`'s circumcircle.

    The standard determinant of squared distances, taken relative to
    `point` so the 4x4 form collapses to a 3x3 one. `triangle` is wound
    counter-clockwise by `_wind`, so a positive determinant means inside.

    Args:
        vertices: Coordinates, indexed by the triangle's entries.
        triangle: The triangle to test against.
        point: The point to test.

    A point *on* the circumcircle counts as **outside**, within tolerance.
    That sense matters because the only caller is the flip test: four
    cocircular points -- a regular grid, which level generators produce
    constantly -- give a determinant of zero, and calling that "inside"
    makes the edge illegal, flips it, finds the flipped diagonal equally
    on-circle, and flips it back. The pass cap turned that into a
    thousand wasted flips and a mesh full of violations until this went
    strict. On-circle means either diagonal is a correct Delaunay answer,
    so leaving the one already there is right.

    Args:
        vertices: Coordinates, indexed by the triangle's entries.
        triangle: The triangle to test against.
        point: The point to test.

    Returns:
        True only if strictly inside, by more than the tolerance.
    """
    a, b, c = (vertices[index] for index in triangle)
    ax, ay = a.x - point.x, a.y - point.y
    bx, by = b.x - point.x, b.y - point.y
    cx, cy = c.x - point.x, c.y - point.y

    determinant = (
        (ax * ax + ay * ay) * (bx * cy - cx * by)
        - (bx * bx + by * by) * (ax * cy - cx * ay)
        + (cx * cx + cy * cy) * (ax * by - bx * ay)
    )
    scale = max(abs(ax), abs(ay), abs(bx), abs(by), abs(cx), abs(cy), 1.0)
    return determinant > _RELATIVE_EPSILON * scale**4


def _boundary_edges(triangles: Sequence[Triangle]) -> list[Edge]:
    """Return the edges on the outline of a group of triangles.

    An edge shared by two of them is interior and vanishes when the group
    is removed; one belonging to a single triangle is on the boundary and
    becomes a wall of the cavity the new point fans out to.

    Args:
        triangles: The triangles being removed.

    Returns:
        The boundary edges, each as an index pair.
    """
    counts: dict[Edge, int] = {}
    for a, b, c in triangles:
        for first, second in ((a, b), (b, c), (c, a)):
            edge = (min(first, second), max(first, second))
            counts[edge] = counts.get(edge, 0) + 1
    return [edge for edge, count in counts.items() if count == 1]


def _minimum_spanning_forest(
    candidates: Sequence[Edge], lengths: dict[Edge, float], count: int
) -> list[Edge]:
    """Run Kruskal's algorithm over a sparse candidate edge set.

    Kruskal rather than Prim's, unlike `build_graph()`: a triangulation
    has O(n) edges, so sorting them and walking once beats rescanning
    every remaining point on each step.

    Args:
        candidates: The edges to choose from.
        lengths: Each candidate's length.
        count: How many points there are.

    Returns:
        The forest's edges. A spanning *tree* when the candidates connect
        every point, which a real triangulation does.
    """
    parent = list(range(count))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    chosen: list[Edge] = []
    for edge in sorted(candidates, key=lambda e: (lengths[e], e)):
        root_a, root_b = find(edge[0]), find(edge[1])
        if root_a == root_b:
            continue
        parent[root_a] = root_b
        chosen.append(edge)
    return chosen


def _bridge_components(
    points: Sequence[Vector2], edges: Sequence[Edge], count: int
) -> list[Edge]:
    """Join anything the triangulation left unreachable.

    A real Delaunay triangulation is connected, so this normally finds
    nothing. It exists for the inputs that are not real triangulations:
    duplicate points, which land on an existing vertex and get skipped, and
    precision ties near-collinear clouds can produce. `build_graph()`
    promises every point is reachable from every other, and this strategy
    has to promise the same thing or it is not a drop-in alternative.

    Args:
        points: Node positions.
        edges: The edges chosen so far.
        count: How many points there are.

    Returns:
        The extra edges needed, shortest first.
    """
    parent = list(range(count))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for edge in edges:
        parent[find(edge[0])] = find(edge[1])

    bridges: list[Edge] = []
    while True:
        roots = {find(index) for index in range(count)}
        if len(roots) < 2:
            return bridges

        best: Edge | None = None
        best_length = math.inf
        for i in range(count):
            for j in range(i + 1, count):
                if find(i) == find(j):
                    continue
                length = points[i].distance_to(points[j])
                if length < best_length:
                    best_length = length
                    best = (i, j)

        assert best is not None  # two components means a crossing pair exists
        parent[find(best[0])] = find(best[1])
        bridges.append(best)
