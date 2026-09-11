"""Tests for `pyguara/ai/pathfinding/flow_field.py`."""

from __future__ import annotations

from pyguara.ai.pathfinding.flow_field import dijkstra_map, flow_field
from pyguara.ai.pathfinding.grid import GridGraph

# ========== dijkstra_map ==========


def test_dijkstra_map_gives_the_goal_zero_cost() -> None:
    graph = GridGraph(width=5, height=5, allow_diagonal=False)

    result = dijkstra_map(graph, goals=[(2, 2)])

    assert result[(2, 2)] == 0.0


def test_dijkstra_map_cost_grows_with_orthogonal_distance() -> None:
    graph = GridGraph(width=5, height=5, allow_diagonal=False)

    result = dijkstra_map(graph, goals=[(0, 0)])

    assert result[(1, 0)] == 1.0
    assert result[(2, 0)] == 2.0
    assert result[(1, 1)] == 2.0


def test_dijkstra_map_covers_every_reachable_node() -> None:
    graph = GridGraph(width=3, height=3, allow_diagonal=False)

    result = dijkstra_map(graph, goals=[(0, 0)])

    assert set(result.keys()) == {(x, y) for x in range(3) for y in range(3)}


def test_dijkstra_map_excludes_nodes_past_max_cost() -> None:
    graph = GridGraph(width=10, height=1, allow_diagonal=False)

    result = dijkstra_map(graph, goals=[(0, 0)], max_cost=2.0)

    assert set(result.keys()) == {(0, 0), (1, 0), (2, 0)}
    assert (3, 0) not in result


def test_dijkstra_map_multi_source_takes_the_nearer_goal() -> None:
    graph = GridGraph(width=10, height=1, allow_diagonal=False)

    result = dijkstra_map(graph, goals=[(0, 0), (9, 0)])

    # Cell 4 is 4 away from goal 0 and 5 away from goal 9 -- nearer to 0.
    assert result[(4, 0)] == 4.0
    # Cell 5 is equidistant either way, but never more than the closer one.
    assert result[(5, 0)] == 4.0


def test_dijkstra_map_walls_are_unreachable() -> None:
    graph = GridGraph(width=3, height=1, allow_diagonal=False)
    graph.walls.add((1, 0))

    result = dijkstra_map(graph, goals=[(0, 0)])

    assert (2, 0) not in result


def test_dijkstra_map_respects_terrain_weights() -> None:
    graph = GridGraph(width=3, height=1, allow_diagonal=False)
    graph.weights[(1, 0)] = 5.0

    result = dijkstra_map(graph, goals=[(0, 0)])

    assert result[(1, 0)] == 5.0
    assert result[(2, 0)] == 6.0


# ========== flow_field ==========


def test_flow_field_goal_has_no_next_step() -> None:
    graph = GridGraph(width=3, height=3, allow_diagonal=False)
    costs = dijkstra_map(graph, goals=[(1, 1)])

    field = flow_field(graph, costs)

    assert field[(1, 1)] is None


def test_flow_field_points_toward_lower_cost() -> None:
    graph = GridGraph(width=5, height=1, allow_diagonal=False)
    costs = dijkstra_map(graph, goals=[(0, 0)])

    field = flow_field(graph, costs)

    assert field[(3, 0)] == (2, 0)
    assert field[(1, 0)] == (0, 0)


def test_following_the_flow_field_reaches_the_goal() -> None:
    graph = GridGraph(width=6, height=6, allow_diagonal=True)
    goal = (5, 5)
    costs = dijkstra_map(graph, goals=[goal])
    field = flow_field(graph, costs)

    current = (0, 0)
    steps = 0
    while current != goal:
        current = field[current]
        steps += 1
        assert steps <= 36  # generous bound; a real loop is the actual bug

    assert current == goal


def test_flow_field_only_covers_nodes_the_cost_map_reached() -> None:
    graph = GridGraph(width=10, height=1, allow_diagonal=False)
    costs = dijkstra_map(graph, goals=[(0, 0)], max_cost=2.0)

    field = flow_field(graph, costs)

    assert set(field.keys()) == {(0, 0), (1, 0), (2, 0)}
    assert (3, 0) not in field
