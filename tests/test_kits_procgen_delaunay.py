"""Delaunay triangulation, and the graph strategy built on it."""

import math

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2
from pyguara.kits.procgen import (
    build_graph,
    build_graph_delaunay,
    delaunay_edges,
    delaunay_triangles,
    scatter_points,
)


def _square() -> list[Vector2]:
    return [Vector2(0, 0), Vector2(100, 0), Vector2(100, 100), Vector2(0, 100)]


def _cloud(count: int = 25, seed: int = 42) -> list[Vector2]:
    return scatter_points(Rect(0, 0, 500, 500), count, RandomStream(seed))


def _is_connected(points, edges) -> bool:
    """Report whether every point is reachable from point 0."""
    if len(points) < 2:
        return True
    neighbours: dict[int, set[int]] = {index: set() for index in range(len(points))}
    for i, j in edges:
        neighbours[i].add(j)
        neighbours[j].add(i)
    seen = {0}
    stack = [0]
    while stack:
        for neighbour in neighbours[stack.pop()]:
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    return len(seen) == len(points)


# -- The triangulation --


def test_three_points_make_one_triangle():
    points = [Vector2(0, 0), Vector2(100, 0), Vector2(50, 80)]

    triangles = delaunay_triangles(points)

    assert len(triangles) == 1
    assert set(triangles[0]) == {0, 1, 2}


def test_a_square_triangulates_into_two():
    triangles = delaunay_triangles(_square())

    assert len(triangles) == 2


def test_every_triangle_is_wound_counter_clockwise():
    """Normalising the winding once is what lets the circumcircle test read
    the determinant's sign directly."""
    points = _cloud()

    for a, b, c in delaunay_triangles(points):
        cross = (points[b].x - points[a].x) * (points[c].y - points[a].y) - (
            points[c].x - points[a].x
        ) * (points[b].y - points[a].y)
        assert cross > 0


def test_no_point_lies_inside_any_circumcircle():
    """The defining property of a Delaunay triangulation. If this holds,
    the algorithm is right; if it does not, nothing else matters."""
    points = _cloud(20)
    triangles = delaunay_triangles(points)
    assert triangles

    for triangle in triangles:
        centre, radius = _circumcircle(*(points[index] for index in triangle))
        for index, point in enumerate(points):
            if index in triangle:
                continue
            assert point.distance_to(centre) >= radius - 1e-6


def _circumcircle(a: Vector2, b: Vector2, c: Vector2) -> tuple[Vector2, float]:
    """Return a triangle's circumcentre and circumradius."""
    d = 2.0 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
    ux = (
        (a.x**2 + a.y**2) * (b.y - c.y)
        + (b.x**2 + b.y**2) * (c.y - a.y)
        + (c.x**2 + c.y**2) * (a.y - b.y)
    ) / d
    uy = (
        (a.x**2 + a.y**2) * (c.x - b.x)
        + (b.x**2 + b.y**2) * (a.x - c.x)
        + (c.x**2 + c.y**2) * (b.x - a.x)
    ) / d
    centre = Vector2(ux, uy)
    return centre, centre.distance_to(a)


def test_the_triangle_count_matches_eulers_formula():
    """A triangulation of n points with h on the convex hull has exactly
    2n - 2 - h triangles. A mesh with a hole in it would not."""
    points = _cloud(30, seed=11)
    triangles = delaunay_triangles(points)
    hull = _convex_hull_size(points)

    assert len(triangles) == 2 * len(points) - 2 - hull


def _convex_hull_size(points: list[Vector2]) -> int:
    """Return how many points sit on the convex hull, collinear ones included.

    Andrew's monotone chain, popping only on a *strict* turn the wrong way
    so a point lying on a hull edge is kept. That convention is the one
    Euler's formula wants: a 4x4 grid has 12 points on its hull, not 4,
    and counting 4 makes the triangle count look wrong when it is right.
    """
    ordered = sorted(points, key=lambda p: (p.x, p.y))

    def half(sequence):
        chain: list[Vector2] = []
        for point in sequence:
            while len(chain) >= 2:
                a, b = chain[-2], chain[-1]
                cross = (b.x - a.x) * (point.y - a.y) - (point.x - a.x) * (b.y - a.y)
                if cross >= 0:
                    break
                chain.pop()
            chain.append(point)
        return chain

    return len(half(ordered)) + len(half(ordered[::-1])) - 2


def test_fewer_than_three_points_has_no_triangulation():
    assert delaunay_triangles([]) == []
    assert delaunay_triangles([Vector2(0, 0)]) == []
    assert delaunay_triangles([Vector2(0, 0), Vector2(1, 1)]) == []


def test_collinear_points_have_no_triangulation():
    """A fact about the input, not a failure."""
    points = [Vector2(x, 0) for x in range(5)]

    assert delaunay_triangles(points) == []


def test_edges_are_unique_sorted_pairs():
    edges = delaunay_edges(_square())

    assert all(i < j for i, j in edges)
    assert len(edges) == len(set(edges))
    assert edges == sorted(edges)


def test_a_squares_edges_are_its_sides_plus_one_diagonal():
    edges = delaunay_edges(_square())

    assert len(edges) == 5


# -- The graph strategy --


def test_the_graph_connects_every_point():
    points = _cloud()

    edges = build_graph_delaunay(points, RandomStream(7))

    assert _is_connected(points, edges)


def test_no_edge_joins_two_points_that_are_not_neighbours():
    """The whole reason to triangulate first: an edge exists only where the
    two points share a Voronoi boundary."""
    points = _cloud()
    allowed = set(delaunay_edges(points))

    edges = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.5)

    assert set(edges) <= allowed


def test_it_avoids_the_long_edge_the_euclidean_mst_takes():
    """Two tight clusters far apart. The Euclidean MST joins them by
    whichever pair happens to be closest, and the triangulation offers the
    same bridge -- but the Delaunay graph takes no *other* long edge,
    where the Euclidean one is free to."""
    points = [Vector2(x * 5, y * 5) for x in range(4) for y in range(4)]
    points += [Vector2(400 + x * 5, 400 + y * 5) for x in range(4) for y in range(4)]

    euclidean = build_graph(points, RandomStream(3), extra_edge_chance=0.4)
    delaunay = build_graph_delaunay(points, RandomStream(3), extra_edge_chance=0.4)

    def long_edges(edges):
        return sum(1 for i, j in edges if points[i].distance_to(points[j]) > 200)

    assert long_edges(delaunay) < long_edges(euclidean)


def test_a_pure_spanning_tree_has_exactly_n_minus_one_edges():
    points = _cloud()

    edges = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.0)

    assert len(edges) == len(points) - 1
    assert _is_connected(points, edges)


def test_a_higher_chance_adds_more_loops():
    points = _cloud()

    few = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.05)
    many = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.9)

    assert len(many) > len(few)


def test_a_distance_cap_keeps_loops_local():
    points = _cloud()

    edges = build_graph_delaunay(
        points,
        RandomStream(7),
        extra_edge_chance=1.0,
        extra_edge_max_distance=60.0,
    )
    tree = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.0)

    extras = set(edges) - set(tree)
    assert extras
    assert all(points[i].distance_to(points[j]) <= 60.0 for i, j in extras)


def test_the_spanning_tree_is_deterministic_regardless_of_the_stream():
    """Same promise `build_graph()` makes: the tree depends on the points'
    order alone."""
    points = _cloud()

    first = build_graph_delaunay(points, RandomStream(1), extra_edge_chance=0.0)
    second = build_graph_delaunay(points, RandomStream(999), extra_edge_chance=0.0)

    assert first == second


def test_the_same_seed_gives_the_same_graph():
    points = _cloud()

    first = build_graph_delaunay(points, RandomStream(5))
    second = build_graph_delaunay(points, RandomStream(5))

    assert first == second


def test_it_falls_back_for_a_cloud_with_no_triangulation():
    """Three points in a row have exactly one sensible graph, and the
    Euclidean MST finds it."""
    points = [Vector2(0, 0), Vector2(10, 0), Vector2(20, 0)]

    edges = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.0)

    assert _is_connected(points, edges)
    assert len(edges) == 2


def test_two_points_make_one_edge():
    points = [Vector2(0, 0), Vector2(10, 10)]

    assert build_graph_delaunay(points, RandomStream(7)) == [(0, 1)]


def test_fewer_than_two_points_makes_no_edges():
    assert build_graph_delaunay([], RandomStream(7)) == []
    assert build_graph_delaunay([Vector2(0, 0)], RandomStream(7)) == []


def test_duplicate_points_are_still_reachable():
    """A coincident point lands on an existing vertex and the triangulation
    skips it; the component fix-up is what keeps the connectivity promise."""
    points = [Vector2(0, 0), Vector2(100, 0), Vector2(50, 80), Vector2(100, 0)]

    edges = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.0)

    assert _is_connected(points, edges)


def test_a_point_cloud_at_a_large_offset_still_triangulates():
    """The super-triangle margin is proportional to the cloud, so it holds
    at any scale -- a fixed margin would not."""
    points = [
        Vector2(1_000_000 + x * 10, 1_000_000 + y * 10)
        for x in range(4)
        for y in range(4)
    ]

    triangles = delaunay_triangles(points)

    assert len(triangles) == 2 * len(points) - 2 - _convex_hull_size(points)


def test_the_tree_edges_come_first_and_extras_are_sorted_by_length():
    points = _cloud()
    tree = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.0)

    edges = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=1.0)

    assert edges[: len(tree)] == tree
    extras = edges[len(tree) :]
    lengths = [points[i].distance_to(points[j]) for i, j in extras]
    assert lengths == sorted(lengths)


def test_the_tree_is_a_minimum_spanning_tree_of_the_triangulation():
    """Kruskal over the triangulation edges; no cheaper spanning subset of
    those edges exists."""
    points = _cloud(15, seed=3)
    candidates = delaunay_edges(points)
    tree = build_graph_delaunay(points, RandomStream(7), extra_edge_chance=0.0)

    weight = sum(points[i].distance_to(points[j]) for i, j in tree)
    best = _brute_force_mst_weight(points, candidates)

    assert weight == pytest.approx(best)


def _brute_force_mst_weight(points, candidates) -> float:
    """MST weight by an independent Kruskal, written differently on purpose."""
    parent = {index: index for index in range(len(points))}

    def find(node):
        while parent[node] != node:
            node = parent[node]
        return node

    total = 0.0
    for length, (i, j) in sorted(
        (points[i].distance_to(points[j]), (i, j)) for i, j in candidates
    ):
        if find(i) != find(j):
            parent[find(i)] = find(j)
            total += length
    return total


def test_the_graph_has_the_same_shape_as_build_graphs():
    """A drop-in alternative: same argument order, same return shape."""
    points = _cloud()

    one = build_graph(points, RandomStream(7))
    other = build_graph_delaunay(points, RandomStream(7))

    assert all(isinstance(edge, tuple) and len(edge) == 2 for edge in other)
    assert all(i < j for i, j in other)
    assert _is_connected(points, one) and _is_connected(points, other)


def _triangulated_area(points, triangles) -> float:
    """Total area of a triangulation."""
    return sum(
        abs(
            (points[b].x - points[a].x) * (points[c].y - points[a].y)
            - (points[c].x - points[a].x) * (points[b].y - points[a].y)
        )
        / 2.0
        for a, b, c in triangles
    )


def _hull_area(points) -> float:
    """Area of the cloud's convex hull, by the shoelace formula."""
    ordered = sorted(points, key=lambda p: (p.x, p.y))

    def chain(sequence):
        built = []
        for point in sequence:
            while len(built) >= 2:
                a, b = built[-2], built[-1]
                if (b.x - a.x) * (point.y - a.y) - (point.x - a.x) * (b.y - a.y) > 0:
                    break
                built.pop()
            built.append(point)
        return built

    hull = chain(ordered)[:-1] + chain(ordered[::-1])[:-1]
    return (
        abs(
            sum(
                hull[i].x * hull[(i + 1) % len(hull)].y
                - hull[(i + 1) % len(hull)].x * hull[i].y
                for i in range(len(hull))
            )
        )
        / 2.0
    )


# The property that matters most, and the one the first implementation
# failed: the triangles must tile the convex hull exactly. A Bowyer-Watson
# version with a super-triangle left holes of up to 6% of the hull on
# ordinary random clouds -- and the Delaunay-property check above passes
# happily on a mesh with a hole in it, because it only ever looks at the
# triangles that *are* there.
_WATERTIGHT_CASES = {
    "random 25": _cloud(25, seed=1),
    "random 60": scatter_points(Rect(0, 0, 1000, 1000), 60, RandomStream(9)),
    "square grid": [Vector2(x * 10, y * 10) for x in range(6) for y in range(6)],
    "grid far from the origin": [
        Vector2(1_000_000 + x * 10, 1_000_000 + y * 10)
        for x in range(4)
        for y in range(4)
    ],
    "tiny grid": [Vector2(x * 0.001, y * 0.001) for x in range(4) for y in range(4)],
    "wide flat sine": [Vector2(x * 50, math.sin(x) * 2) for x in range(12)],
    "thin zigzag strip": [Vector2(x * 100, (x % 2) * 0.5) for x in range(15)],
    "points on a circle": [
        Vector2(100 * math.cos(i * math.tau / 12), 100 * math.sin(i * math.tau / 12))
        for i in range(12)
    ],
    "collinear hull points": [
        Vector2(0, 0),
        Vector2(50, 0),
        Vector2(100, 0),
        Vector2(50, 50),
    ],
}


@pytest.mark.parametrize("label", sorted(_WATERTIGHT_CASES))
def test_the_triangles_tile_the_convex_hull_exactly(label):
    points = _WATERTIGHT_CASES[label]
    triangles = delaunay_triangles(points)
    assert triangles

    hull = _hull_area(points)

    assert _triangulated_area(points, triangles) == pytest.approx(hull, rel=1e-9)


@pytest.mark.parametrize("seed", range(1, 26))
def test_no_random_cloud_develops_a_hole(seed):
    """A sweep, because the failure was input-dependent: the first version
    was fine on most clouds and short two triangles on others."""
    points = _cloud(25, seed=seed)
    triangles = delaunay_triangles(points)

    assert _triangulated_area(points, triangles) == pytest.approx(
        _hull_area(points), rel=1e-9
    )


@pytest.mark.parametrize("seed", range(1, 11))
def test_no_random_cloud_violates_the_delaunay_property(seed):
    points = _cloud(20, seed=seed)

    for triangle in delaunay_triangles(points):
        centre, radius = _circumcircle(*(points[index] for index in triangle))
        for index, point in enumerate(points):
            if index in triangle:
                continue
            assert point.distance_to(centre) >= radius - 1e-6 * max(radius, 1.0)


def test_a_cocircular_grid_settles_instead_of_flipping_forever():
    """Four points on a circle make either diagonal a correct Delaunay
    answer. An inclusive flip test called both illegal, flipped one, found
    the other equally illegal, and burned the whole pass budget."""
    points = [Vector2(x * 10, y * 10) for x in range(5) for y in range(5)]

    triangles = delaunay_triangles(points)

    assert _triangulated_area(points, triangles) == pytest.approx(
        _hull_area(points), rel=1e-9
    )
    for triangle in triangles:
        centre, radius = _circumcircle(*(points[index] for index in triangle))
        for index, point in enumerate(points):
            if index in triangle:
                continue
            assert point.distance_to(centre) >= radius - 1e-6 * radius
