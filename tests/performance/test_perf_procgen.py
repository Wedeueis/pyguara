"""What generation costs, and the complexity class that decides it.

`generate_wfc` was the last unmeasured item in RFC-0003's list of native
candidates -- ADR 0004's Track R item 1 says so explicitly, and says to
measure before claiming. Measured, the claim it would have supported was
about the wrong thing: **95% of a 48x48 generation was choosing which
cell to collapse next**, by listing every undecided cell and sorting it
once per collapse. That is Decision 6 -- the algorithmic question before
the boundary -- and it is the second row after the render batcher where
asking it first moved `T_py` out from under a port.

The guard here is the one that matters, and it is a ratio rather than a
budget so it holds on any machine: generation has to stay in its
complexity class. A scan-and-sort per collapse costs **16-19x for 4x the
cells**; the entropy heap costs **4.4x**, which is what a near-linear
algorithm looks like. A regression to the former is not a slow patch, it
is a 64x64 grid going from 27 ms to 3.5 seconds.

The absolute figures live in `docs/guides/performance.md`, produced by
the sweeps, which assert nothing.
"""

from __future__ import annotations

import pytest

from pyguara.ai.pathfinding import AStarPathfinder, GridGraph, OctileDistance
from pyguara.common.random import RandomStream
from pyguara.kits.procgen import AdjacencyRule, generate_wfc
from tests.performance.conftest import assert_scales_no_worse_than, measure

# A four-state terrain palette with a transition chain -- water touches
# sand, sand touches grass, grass touches rock. Chosen over a
# checkerboard because the chain leaves cells at genuinely different
# entropies, which is what the selection order is about; a two-state
# checkerboard decides the whole grid from one collapse and measures
# propagation instead.
_TERRAIN = ["water", "sand", "grass", "rock"]
_ADJACENT = {
    "water": ["water", "sand"],
    "sand": ["water", "sand", "grass"],
    "grass": ["sand", "grass", "rock"],
    "rock": ["grass", "rock"],
}
_DIRS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
_RULES = [
    AdjacencyRule(from_state=a, to_state=b, direction=d)
    for a, allowed in _ADJACENT.items()
    for b in allowed
    for d in _DIRS4
]


def _generate(side: int) -> None:
    """One whole `side`x`side` generation, from a fixed seed."""
    generate_wfc(side, side, _TERRAIN, _RULES, RandomStream(5))


def _walled_grid(side: int, *, walls: float = 0.12, seed: int = 7) -> GridGraph:
    """A `side`x`side` grid with a scattered fraction of it walled.

    Scattered rather than maze-like for the reason
    `test_perf_pathfinding` gives: random walls leave many diagonals with
    one flanking cell solid, so the corner rule -- the most expensive part
    of a neighbour lookup -- actually runs.
    """
    rng = RandomStream(seed)
    graph = GridGraph(side, side, allow_diagonal=True)
    for y in range(side):
        for x in range(side):
            if rng.random() < walls:
                graph.walls.add((x, y))
    graph.walls.discard((0, 0))
    graph.walls.discard((side - 1, side - 1))
    return graph


@pytest.mark.performance
def test_generation_does_not_go_quadratic_in_the_cell_count() -> None:
    """The guard the entropy heap exists to satisfy.

    16x16 to 32x32 is 4x the cells. Near-linear lands around 4.4x; the
    scan-and-sort it replaced landed at 18.8x, so the limit separates the
    two by a wide margin rather than pinning a constant.
    """
    small = measure(lambda: _generate(16), rounds=3)
    large = measure(lambda: _generate(32), rounds=3)

    assert_scales_no_worse_than(
        small=small,
        large=large,
        factor=4,
        limit=9.0,
        what="generate_wfc over 4x the cells",
    )


@pytest.mark.performance
def test_generation_stays_in_class_at_the_next_size_up() -> None:
    """The same claim one size further out, because a quadratic term is
    easiest to miss at the size where it is still small.

    32x32 to 64x64 is another 4x. The scan-and-sort landed at 16.4x here;
    a 64x64 grid is the size a roguelike floor actually is, which is why
    this one is worth its runtime.
    """
    small = measure(lambda: _generate(32), rounds=3)
    large = measure(lambda: _generate(64), rounds=3)

    assert_scales_no_worse_than(
        small=small,
        large=large,
        factor=4,
        limit=9.0,
        what="generate_wfc over 4x the cells, at 64x64",
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("side", [16, 32, 48, 64])
def test_sweep_generate_wfc(benchmark, side: int) -> None:  # type: ignore[no-untyped-def]
    """Sweep: the `docs/guides/performance.md` figures. Asserts nothing."""
    benchmark(lambda: _generate(side))


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("side", [32, 64, 96])
def test_sweep_astar_corner_to_corner(benchmark, side: int) -> None:  # type: ignore[no-untyped-def]
    """Sweep: one A* query across the whole grid. Asserts nothing.

    The worst single query a grid of this size affords, which is the
    figure that matters: corner to corner with a scattered-wall field is
    what a repath across a whole floor costs, and at 96x96 it is longer
    than a frame.
    """
    graph = _walled_grid(side)
    solver, heuristic = AStarPathfinder(), OctileDistance()
    goal = (side - 1, side - 1)

    benchmark(lambda: solver.find_path(graph, (0, 0), goal, heuristic))
