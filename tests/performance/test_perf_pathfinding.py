"""What a flow-field recompute costs, and what the accelerator buys.

The engine's largest measured margin, and the one that changed what a
port was *for*. Nothing here existed before ADR 0004: `tests/performance/`
covered ECS, flocking, spatial, GL, render-CPU and the pools, and a
recompute -- the single most expensive operation in the engine -- was
unmeasured.

Measured, a 96x96 Python recompute is **85 ms**, which is 516% of a 16.7 ms
frame. That is not a slow feature, it is a feature that cannot be used at
interactive rates: one goal crossing one cell boundary drops five frames.
Two things came out of knowing that, in this order, and the order is
Decision 6 of ADR 0004:

1. `FlowFieldService.recompute` learned to skip a recompute that would
   reproduce the field it already holds. 3114x on the unchanged path, and
   a shipped demo's 30% of a frame down to 0.01%.
2. The sweep itself went native: 85 ms -> 1.36 ms. The guard did not make
   this unnecessary, it corrected the reason for it -- from throughput to
   the worst case, which the guard cannot help with because a goal really
   does move.

The guards here are ratios, never wall-clock budgets, so they are safe on
a shared runner; the absolute figures live in
`docs/guides/performance.md`. The one exception is the native comparison,
which is a ratio between the two stores in the same process -- also
machine-independent.
"""

from __future__ import annotations

import random

import pytest

from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from pyguara.ai.pathfinding.grid import GridGraph
from pyguara.common.types import Vector2
from tests.performance.conftest import measure


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
    service = FlowFieldService(graph, accelerate=False)
    goal = _goal_of(graph)
    service.recompute([goal])

    skipped = measure(lambda: service.recompute([goal]))
    # A fresh service each round, or the second recompute would be skipped
    # too and this would measure the same thing twice.
    computed = measure(
        lambda: FlowFieldService(graph, accelerate=False).recompute([goal])
    )

    assert skipped < computed * 0.05, (
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

    small_time = measure(
        lambda: FlowFieldService(small, accelerate=False).recompute([_goal_of(small)])
    )
    large_time = measure(
        lambda: FlowFieldService(large, accelerate=False).recompute([_goal_of(large)])
    )

    ratio = large_time / max(small_time, 1e-9)
    assert ratio <= 10.0, (
        f"4x the cells cost {ratio:.1f}x the time (limit 10x). "
        f"{small_time * 1e3:.2f}ms -> {large_time * 1e3:.2f}ms. That is a "
        f"change of complexity class, not a constant factor."
    )


@pytest.mark.performance
def test_the_native_store_is_wired_up_and_materially_faster() -> None:
    """That the accelerator is reached at all, which is easy to lose.

    `pyguara/native.py` falls back silently when the extension is missing
    or stale -- that is the point of it -- so a broken build, a renamed
    class or a lookup that stopped finding `target/release/` all present
    as "the Python sweep, and nobody noticed".

    A fifth of the Python cost, where the measured margin is sixty-threefold
    at 96x96 and includes the per-recompute upload of the wall mask. The
    assertion is loose because a shared runner is noisy and because the
    exact figure belongs in `docs/guides/performance.md` rather than in a
    test that would then need retuning per machine.

    Note that this *skips* without the extension rather than failing, so it
    is not what catches a broken lookup on a machine that has one --
    `tests/test_flow_field_service.py::TestTheStoreIsOneEngineWideChoice`
    is, by asserting the service agrees with `native.in_use()`.
    """
    graph = _graph(64)
    goal = _goal_of(graph)
    accelerated = FlowFieldService(graph)
    if not accelerated.accelerated:
        pytest.skip("native extension not built; `cargo build --release`")

    python_time = measure(
        lambda: FlowFieldService(graph, accelerate=False).recompute([goal])
    )
    native_time = measure(lambda: FlowFieldService(graph).recompute([goal]))

    assert native_time < python_time * 0.2, (
        f"the native store took {native_time / max(python_time, 1e-9):.0%} of "
        f"the Python one. Either it is not actually being used, or the sweep "
        f"has regressed to within noise of interpreted Python."
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
    if not native.accelerated:
        pytest.skip("native extension not built; `cargo build --release`")
    python = FlowFieldService(graph, accelerate=False)
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
@pytest.mark.parametrize("accelerate", [False, True], ids=["python", "native"])
def test_sweep_recompute(benchmark, side: int, accelerate: bool) -> None:
    """Sweep: the `docs/guides/performance.md` figures. Asserts nothing."""
    graph = _graph(side)
    goal = _goal_of(graph)
    if accelerate and not FlowFieldService(graph).accelerated:
        pytest.skip("native extension not built; `cargo build --release`")

    benchmark(lambda: FlowFieldService(graph, accelerate=accelerate).recompute([goal]))
