"""Tests for `pyguara/kits/procgen/graph.py` (point scatter + graph connection)."""

from __future__ import annotations

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2
from pyguara.kits.procgen import build_graph, scatter_points

# ========== scatter_points ==========


def test_zero_count_returns_no_points() -> None:
    assert scatter_points(Rect(0, 0, 100, 100), 0, RandomStream(1)) == []


def test_every_scattered_point_is_within_bounds() -> None:
    bounds = Rect(10, 20, 100, 50)
    points = scatter_points(bounds, 200, RandomStream(1))

    assert len(points) == 200
    for point in points:
        assert bounds.left <= point.x <= bounds.right
        assert bounds.top <= point.y <= bounds.bottom


def test_scatter_is_deterministic() -> None:
    bounds = Rect(0, 0, 50, 50)
    a = scatter_points(bounds, 20, RandomStream(7))
    b = scatter_points(bounds, 20, RandomStream(7))

    assert a == b


# ========== build_graph ==========


def _connected_component(n: int, edges: list[tuple[int, int]]) -> set[int]:
    adjacency: dict[int, set[int]] = {i: set() for i in range(n)}
    for i, j in edges:
        adjacency[i].add(j)
        adjacency[j].add(i)

    seen = {0}
    stack = [0]
    while stack:
        node = stack.pop()
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return seen


def test_fewer_than_two_points_has_no_edges() -> None:
    assert build_graph([], RandomStream(1)) == []
    assert build_graph([Vector2(0, 0)], RandomStream(1)) == []


def test_two_points_connect_directly() -> None:
    points = [Vector2(0, 0), Vector2(5, 0)]

    edges = build_graph(points, RandomStream(1), extra_edge_chance=0.0)

    assert edges == [(0, 1)]


def test_zero_extra_edge_chance_produces_a_pure_spanning_tree() -> None:
    points = [Vector2(i * 3, (i % 3) * 7) for i in range(15)]

    edges = build_graph(points, RandomStream(1), extra_edge_chance=0.0)

    assert len(edges) == len(points) - 1


def test_every_point_is_reachable() -> None:
    points = [Vector2(i * 3, (i % 4) * 7) for i in range(25)]

    edges = build_graph(points, RandomStream(1), extra_edge_chance=0.1)

    assert _connected_component(len(points), edges) == set(range(len(points)))


def test_full_extra_edge_chance_with_no_distance_cap_is_a_complete_graph() -> None:
    points = [Vector2(i, 0) for i in range(6)]

    edges = build_graph(points, RandomStream(1), extra_edge_chance=1.0)

    assert len(edges) == len(points) * (len(points) - 1) // 2


def test_extra_edge_max_distance_excludes_far_pairs() -> None:
    # MST: (0,1), (1,2), (2,3) -- the cheapest way to reach the far point.
    # (0,2) is a close non-tree pair; (0,3)/(1,3) are far non-tree pairs.
    points = [Vector2(0, 0), Vector2(1, 0), Vector2(2, 0), Vector2(100, 0)]

    edges = build_graph(
        points,
        RandomStream(1),
        extra_edge_chance=1.0,
        extra_edge_max_distance=10.0,
    )

    assert (0, 3) not in edges
    assert (1, 3) not in edges
    assert (0, 2) in edges  # close enough, and extra_edge_chance=1.0


def test_build_graph_is_deterministic() -> None:
    points = [Vector2(i * 2, (i % 5) * 3) for i in range(30)]

    a = build_graph(points, RandomStream(99), extra_edge_chance=0.2)
    b = build_graph(points, RandomStream(99), extra_edge_chance=0.2)

    assert a == b
