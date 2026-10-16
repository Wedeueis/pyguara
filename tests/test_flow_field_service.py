"""Tests for `pyguara/ai/pathfinding/flow_field_service.py`."""

from __future__ import annotations

import math

from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.ai.pathfinding.grid import GridGraph
from pyguara.common.types import Vector2

CELL_SIZE = 32.0


def _service() -> tuple[GridGraph, FlowFieldService]:
    """An empty 5x5 graph and a service over it."""
    graph = GridGraph(5, 5, allow_diagonal=True)
    return graph, FlowFieldService(graph)


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


class TestRecomputeSkipsIdenticalWork:
    """A recompute that would produce the field already held is skipped.

    `FlowFieldService`'s first line calls itself a cache, and until now it
    was not one: `recompute()` always ran a full multi-source Dijkstra plus
    a full descent pass. That invited exactly one bug, and
    `games/vinagre_matilha` has it -- `FlankerAssignmentSystem.update`
    recomputes every fixed tick toward the jaguar's cell, which is 5.0 ms
    on its 30x20 grid, 30% of a frame budget sixty times a second, while
    the goal cell changes once per twelve ticks at a dead sprint.

    The skip is keyed on a **fingerprint of the graph**, not on the goals
    alone, and that distinction is the whole safety argument. The graph is
    mutable and really does change at runtime -- `PressurePlateSystem`
    removes a log's cells from `GridGraph.walls` mid-level, and a cache
    keyed on goals would then steer the pack through a wall that is no
    longer there, or into one that still is. Hashing the walls and weights
    costs 0.03-0.06% of a recompute (measured; see
    `docs/guides/performance.md`), which buys soundness for free and means
    there is no invalidation contract for a caller to forget.
    """

    def test_a_repeat_recompute_is_skipped(self) -> None:
        graph, service = _service()

        assert service.recompute(goals=[(0, 0)]) is True
        assert service.recompute(goals=[(0, 0)]) is False

    def test_goal_order_does_not_count_as_a_change(self) -> None:
        """The field depends on the goal *set*, so the key is a set."""
        graph, service = _service()

        service.recompute(goals=[(0, 0), (4, 4)])

        assert service.recompute(goals=[(4, 4), (0, 0)]) is False

    def test_new_goals_recompute(self) -> None:
        graph, service = _service()
        service.recompute(goals=[(0, 0)])

        assert service.recompute(goals=[(4, 4)]) is True

    def test_a_different_max_cost_recomputes(self) -> None:
        graph, service = _service()
        service.recompute(goals=[(0, 0)])

        assert service.recompute(goals=[(0, 0)], max_cost=2.0) is True

    def test_a_wall_appearing_recomputes_and_changes_the_field(self) -> None:
        """The one that matters: a stale field here steers into a wall."""
        graph, service = _service()
        service.recompute(goals=[(0, 0)])
        before = service.vector_at(Vector2(2.5 * CELL_SIZE, 0.5 * CELL_SIZE), CELL_SIZE)

        for y in range(5):
            graph.walls.add((1, y))  # a full wall between (2, 0) and the goal

        assert service.recompute(goals=[(0, 0)]) is True
        assert (
            service.vector_at(Vector2(2.5 * CELL_SIZE, 0.5 * CELL_SIZE), CELL_SIZE)
            != before
        )

    def test_a_wall_disappearing_recomputes(self) -> None:
        """`PressurePlateSystem`'s case, in the engine rather than the demo."""
        graph, service = _service()
        for y in range(5):
            graph.walls.add((1, y))
        service.recompute(goals=[(0, 0)])

        graph.walls.difference_update({(1, 2)})  # the log opens

        assert service.recompute(goals=[(0, 0)]) is True

    def test_a_terrain_weight_changing_recomputes(self) -> None:
        graph, service = _service()
        service.recompute(goals=[(0, 0)])

        graph.weights[(2, 2)] = 9.0

        assert service.recompute(goals=[(0, 0)]) is True

    def test_toggling_diagonals_recomputes(self) -> None:
        graph, service = _service()
        service.recompute(goals=[(0, 0)])

        graph.allow_diagonal = not graph.allow_diagonal

        assert service.recompute(goals=[(0, 0)]) is True
