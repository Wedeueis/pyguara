"""What a flow-field recompute costs, and what computing it in Rust buys.

Two things are guarded. `FlowFieldService.recompute` skips a recompute
that would reproduce the field it holds. And the sweep itself is
native, which bounds the worst case when a goal really does move. See
ADR 0004, Decision 6.

The guards are ratios, never wall-clock budgets. "Python" here is
`tests.reference.flow_field`, the implementation the service replaced.
The absolute figures are in `docs/guides/performance.md`.
"""

from __future__ import annotations

import random

import pytest

from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.ai.pathfinding.grid import GridGraph
from pyguara.common.types import Vector2
from tests.performance.conftest import measure
from tests.reference.flow_field import ReferenceFlowField

SKIP_LIMIT = 0.1
"""The most a skipped recompute may cost, as a fraction of a real one.

Measured at 1.6% on a 64x64 grid: the fingerprint is Python and the
sweep is Rust, so this is far closer than when both were Python.
"""


def _graph(side: int, *, walls: float = 0.12, seed: int = 7) -> GridGraph:
    """A `side`x`side` grid with a scattered fraction of it walled.

    Scattered rather than maze-like on purpose: random walls leave many
    diagonals with one flanking cell solid, so the corner rule -- the most
    expensive part of a neighbour lookup -- actually runs.
    """
    rng = random.Random(seed)
    graph = GridGraph(side, side, allow_diagonal=True)
    for y in range(side):
        for x in range(side):
            if rng.random() < walls:
                graph.walls.add((x, y))
    graph.walls.discard((side // 2, side // 2))
    return graph


def _goal_of(graph: GridGraph) -> tuple[int, int]:
    """The centre cell, which `_graph` guarantees is not a wall."""
    return (graph.width // 2, graph.height // 2)


@pytest.mark.performance
def test_the_skip_costs_a_fraction_of_the_recompute_it_avoids() -> None:
    """The guard's whole premise: fingerprinting is cheaper than sweeping.

    Hashing every wall and every weight is O(cells), which is the same
    complexity class as the sweep it is deciding about -- so "it is cheap"
    needs to be a measurement rather than an intuition. It is cheap
    because the constant is a set hash against a priority queue.

    A ratio, so it holds on any machine, and generous enough that it is
    asserting the premise rather than the constant.
    """
    graph = _graph(64)
    service = FlowFieldService(graph)
    goal = _goal_of(graph)
    service.recompute([goal])

    skipped = measure(lambda: service.recompute([goal]))
    # A fresh service each round, or the second recompute would be skipped
    # too and this would measure the same thing twice.
    computed = measure(lambda: FlowFieldService(graph).recompute([goal]))

    assert skipped < computed * SKIP_LIMIT, (
        f"the skip cost {skipped / max(computed, 1e-9):.1%} of a recompute. "
        f"If fingerprinting the graph has become comparable to sweeping it, "
        f"the guard is no longer worth its soundness and an explicit "
        f"invalidation contract would be."
    )


@pytest.mark.performance
def test_a_recompute_scales_no_worse_than_the_cell_count() -> None:
    """Dijkstra over a grid is O(cells log cells), so 4x cells is ~4-6x.

    Pinned because the two halves of a recompute scale differently and it
    is easy to make one of them worse: the sweep is heap-driven, the
    descent pass is a flat walk over every reached cell. A change that
    made the descent pass consult the graph per neighbour rather than the
    cost map would show up here as a jump, not as a constant factor.
    """
    small = _graph(32)
    large = _graph(64)

    small_time = measure(lambda: FlowFieldService(small).recompute([_goal_of(small)]))
    large_time = measure(lambda: FlowFieldService(large).recompute([_goal_of(large)]))

    ratio = large_time / max(small_time, 1e-9)
    assert ratio <= 10.0, (
        f"4x the cells cost {ratio:.1f}x the time (limit 10x). "
        f"{small_time * 1e3:.2f}ms -> {large_time * 1e3:.2f}ms. That is a "
        f"change of complexity class, not a constant factor."
    )


@pytest.mark.performance
def test_the_sweep_is_materially_faster_than_the_python_it_replaced() -> None:
    """The reason the field is in Rust, kept as a measurement.

    Asserted at a fifth of the Python cost, loosely, for a shared runner;
    the exact figure is in `docs/guides/performance.md`.
    """
    graph = _graph(64)
    goal = _goal_of(graph)

    python_time = measure(lambda: ReferenceFlowField(graph).recompute([goal]))
    native_time = measure(lambda: FlowFieldService(graph).recompute([goal]))

    assert native_time < python_time * 0.2, (
        f"the service took {native_time / max(python_time, 1e-9):.0%} of the "
        f"Python reference. The sweep has regressed to within noise of "
        f"interpreted Python."
    )


@pytest.mark.performance
def test_a_query_is_cheaper_natively_than_in_python() -> None:
    """`vector_at` is the per-agent cost, and it also got faster.

    Worth its own guard because the obvious native boundary would have
    made it *slower*: a crossing per query that returned the descent
    neighbour, leaving Python to do four `Vector2` operations, costs more
    than the dict lookup it replaced. The crossing is 0.044 us and those
    operations are 3.1 us, so the direction is computed natively instead
    and the whole method is one crossing.
    """
    graph = _graph(64)
    goal = _goal_of(graph)
    native = FlowFieldService(graph)
    python = ReferenceFlowField(graph)
    native.recompute([goal])
    python.recompute([goal])

    rng = random.Random(3)
    positions = [
        Vector2(rng.uniform(0, 64 * 32), rng.uniform(0, 64 * 32)) for _ in range(500)
    ]

    python_time = measure(lambda: [python.vector_at(p, 32.0) for p in positions])
    native_time = measure(lambda: [native.vector_at(p, 32.0) for p in positions])

    assert native_time < python_time, (
        f"a native query cost {native_time / max(python_time, 1e-9):.0%} of a "
        f"Python one. The point of computing the direction natively is that "
        f"the crossing is cheaper than the `Vector2` arithmetic it replaces; "
        f"if that has stopped holding, `direction_at` should go back to "
        f"returning a neighbour."
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("side", [30, 64, 96])
@pytest.mark.parametrize("native", [False, True], ids=["python", "native"])
def test_sweep_recompute(benchmark, side: int, native: bool) -> None:
    """Sweep: the `docs/guides/performance.md` figures. Asserts nothing."""
    graph = _graph(side)
    goal = _goal_of(graph)
    build = FlowFieldService if native else ReferenceFlowField

    benchmark(lambda: build(graph).recompute([goal]))
