"""Tests for `pyguara/ai/pathfinding/flow_field_service.py`."""

from __future__ import annotations

import math

from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.ai.pathfinding.grid import GridGraph
from pyguara.common.types import Vector2

CELL_SIZE = 32.0


def test_vector_at_is_zero_before_any_recompute() -> None:
    graph = GridGraph(width=5, height=5, allow_diagonal=False)
    service = FlowFieldService(graph)

    assert service.vector_at(Vector2(0, 0), CELL_SIZE) == Vector2(0, 0)
    assert not service.is_computed


def test_recompute_marks_the_service_computed() -> None:
    graph = GridGraph(width=5, height=5, allow_diagonal=False)
    service = FlowFieldService(graph)

    service.recompute(goals=[(4, 4)])

    assert service.is_computed


def test_vector_at_points_toward_the_goal_on_a_straight_line() -> None:
    graph = GridGraph(width=10, height=1, allow_diagonal=False)
    service = FlowFieldService(graph)
    service.recompute(goals=[(0, 0)])

    # Standing in cell (5, 0), the field should point back toward (0, 0):
    # negative x, no y component.
    direction = service.vector_at(Vector2(5 * CELL_SIZE + 1, 0), CELL_SIZE)
    assert direction.x < 0
    assert abs(direction.y) < 0.001


def test_vector_at_is_zero_at_the_goal_cell() -> None:
    graph = GridGraph(width=5, height=5, allow_diagonal=False)
    service = FlowFieldService(graph)
    service.recompute(goals=[(2, 2)])

    goal_world = Vector2(2 * CELL_SIZE + 1, 2 * CELL_SIZE + 1)
    assert service.vector_at(goal_world, CELL_SIZE) == Vector2(0, 0)


def test_vector_at_is_zero_outside_max_cost() -> None:
    graph = GridGraph(width=10, height=1, allow_diagonal=False)
    service = FlowFieldService(graph)
    service.recompute(goals=[(0, 0)], max_cost=2.0)

    # Cell (9, 0) was never reached by the capped sweep.
    direction = service.vector_at(Vector2(9 * CELL_SIZE + 1, 0), CELL_SIZE)
    assert direction == Vector2(0, 0)


def test_water_weighted_cell_biases_the_field_around_it() -> None:
    graph = GridGraph(width=3, height=1, allow_diagonal=False)
    graph.weights[(1, 0)] = 10.0  # water: expensive to cross
    service = FlowFieldService(graph)
    service.recompute(goals=[(0, 0)])

    assert service.cost_at((1, 0)) == 10.0
    # Cost accrues on *entering* a cell: crossing (1, 0) costs 10 once, then
    # (2, 0) itself is unweighted (+1.0) -- not a second 10.0 charge.
    assert service.cost_at((2, 0)) == 11.0


def test_cost_at_is_infinite_for_an_unreached_cell() -> None:
    graph = GridGraph(width=5, height=5, allow_diagonal=False)
    # Wall off a fully enclosed 1x1 pocket at (4, 4), unreachable from (0, 0).
    graph.walls.add((3, 4))
    graph.walls.add((4, 3))
    service = FlowFieldService(graph)
    service.recompute(goals=[(0, 0)])

    assert service.cost_at((2, 2)) != math.inf  # sanity: rest of grid reached
    assert service.cost_at((4, 4)) == math.inf
