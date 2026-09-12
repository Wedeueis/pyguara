"""How many boids can `FlockingSystem` steer in a frame?

This is the measurement the crowd-scale question turns on, so it is worth
being precise about what is being measured.

A flocking tick is O(n . k): n agents, each visiting the k neighbours the
spatial hash hands back. That means **density is a second independent
variable**, and a suite that varies only n is measuring half the story.
Two regimes are covered here:

*Uniform* holds agents-per-cell constant while n grows, which isolates the
n term and is the one the linearity guard is about.

*Clumped* packs every agent into a fixed area regardless of n, so k grows
with n and the tick goes quadratic by construction. This is not a
pathological case: it is a horde converging on a player, which is exactly
what the demo this suite exists for will do every run. The guard here
bounds how badly that degrades, rather than pretending it does not.
"""

from __future__ import annotations

import pytest

from tests.performance.conftest import (
    assert_scales_no_worse_than,
    build_flock,
    measure,
    uniform_spread_for,
)

DT = 1 / 60


@pytest.mark.performance
def test_flocking_is_linear_at_constant_density() -> None:
    """4x the agents at the same density should not cost 16x the time."""
    small_n, large_n = 250, 1000

    _, small_system = build_flock(small_n, spread=uniform_spread_for(small_n))
    _, large_system = build_flock(large_n, spread=uniform_spread_for(large_n))

    small = measure(lambda: small_system.update(DT))
    large = measure(lambda: large_system.update(DT))

    assert_scales_no_worse_than(
        small=small,
        large=large,
        factor=4,
        limit=8.0,
        what="FlockingSystem.update at constant density",
    )


@pytest.mark.performance
def test_clumping_degrades_flocking_but_within_bounds() -> None:
    """A flock converging on one point costs more, boundedly.

    Every agent inside a single neighbourhood makes k proportional to n,
    so this is quadratic on purpose. The guard's job is to notice if it
    gets *worse* than that -- or if someone removes the spatial hash and
    it becomes quadratic at every density.
    """
    count = 500
    _, spread_system = build_flock(count, spread=uniform_spread_for(count))
    _, clumped_system = build_flock(count, spread=400.0)

    spread = measure(lambda: spread_system.update(DT))
    clumped = measure(lambda: clumped_system.update(DT))

    assert_scales_no_worse_than(
        small=spread,
        large=clumped,
        factor=1,
        limit=25.0,
        what="FlockingSystem.update clumped vs uniform",
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [250, 500, 1000, 2000, 3000])
def test_sweep_flocking_uniform(benchmark, count: int) -> None:
    """Report ms/tick at uniform density. Asserts nothing; feeds the docs."""
    _, system = build_flock(count, spread=uniform_spread_for(count))
    benchmark.pedantic(lambda: system.update(DT), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [500, 1000, 2000, 3000])
def test_sweep_flocking_clumped(benchmark, count: int) -> None:
    """Report ms/tick with the whole flock inside one small area."""
    _, system = build_flock(count, spread=1200.0)
    benchmark.pedantic(lambda: system.update(DT), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("groups", [1, 2, 3, 4])
def test_sweep_flocking_staggered(benchmark, groups: int) -> None:
    """Report ms/tick at 3000 agents with steering spread across `groups` ticks.

    Every agent still integrates its position every tick; only the
    steering decision is round-robined. This is the knob that decides
    whether a crowd of this size fits in a frame at all, so its cost
    curve is worth publishing next to the un-staggered one.
    """
    count = 3000
    _, system = build_flock(count, spread=uniform_spread_for(count))
    system._groups = groups  # noqa: SLF001 - the ctor arg, set post-build
    benchmark.pedantic(lambda: system.update(DT), rounds=5, iterations=1)
