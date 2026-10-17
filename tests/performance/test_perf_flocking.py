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

from pyguara.ai.flocking_system import FlockingSystem
from pyguara.ecs.manager import EntityManager
from tests.performance.conftest import (
    assert_scales_no_worse_than,
    build_flock,
    measure,
    uniform_spread_for,
)

DT = 1 / 60

STORES = [
    pytest.param(False, id="python"),
    pytest.param(True, id="native"),
]


def _flock(count: int, *, spread: float, accelerate: bool):
    """`build_flock`, skipping the native store when it is not built."""
    if accelerate and not FlockingSystem(EntityManager()).accelerated:
        pytest.skip("native extension not built; `cargo build --release`")
    return build_flock(count, spread=spread, accelerate=accelerate)


@pytest.mark.performance
def test_flocking_is_linear_at_constant_density() -> None:
    """4x the agents at the same density should not cost 16x the time."""
    small_n, large_n = 250, 1000

    # Explicitly the Python store: this guard is about the complexity
    # class of `SpatialHash` plus `flock_force`, which is what it was
    # written against. The native store has its own guards below.
    _, small_system = build_flock(
        small_n, spread=uniform_spread_for(small_n), accelerate=False
    )
    _, large_system = build_flock(
        large_n, spread=uniform_spread_for(large_n), accelerate=False
    )

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
    _, spread_system = build_flock(
        count, spread=uniform_spread_for(count), accelerate=False
    )
    _, clumped_system = build_flock(count, spread=400.0, accelerate=False)

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
def test_the_native_store_is_wired_up_and_materially_faster() -> None:
    """1000 agents is where this stopped fitting in a frame.

    A Python tick at 1000 agents is 16 ms, which is 96% of a 16.7 ms
    frame: not a system that needs tuning, a crowd size the engine could
    not carry. Natively it is 1.9 ms.

    The guard is a ratio rather than a wall-clock budget so it means the
    same thing on a slower machine, and it is loose -- measured at 11%,
    asserted under 35% -- because its job is to notice that the native
    path stopped being taken at all. That has happened before: a loader
    that finds no library falls back to Python exactly as designed and
    every parity test *skips*, so this is one of the few places a
    silently absent extension becomes a failure.
    """
    count = 1000
    spread = uniform_spread_for(count)
    _, python = _flock(count, spread=spread, accelerate=False)
    _, native = _flock(count, spread=spread, accelerate=True)

    python_time = measure(lambda: python.update(DT))
    native_time = measure(lambda: native.update(DT))

    assert native_time < python_time * 0.35, (
        f"native flocking took {native_time * 1e3:.2f}ms against Python's "
        f"{python_time * 1e3:.2f}ms ({python_time / native_time:.1f}x). "
        "Expected around 9x."
    )


@pytest.mark.performance
def test_the_native_store_is_the_one_that_survives_a_horde() -> None:
    """Clumping is the case the port is really for.

    A flock converging on the player makes k proportional to n, so the
    tick goes quadratic -- `test_clumping_degrades_flocking_but_within_bounds`
    bounds how badly in Python and accepts 25x. The native store's
    advantage *grows* in exactly that regime, because what clumping
    multiplies is the per-neighbour arithmetic rather than the crossing.

    Measured at 2000 agents: Python 34ms uniform against 74ms clumped,
    2.2x; native 3.9ms against 4.6ms, 1.26x -- a ratio of 0.56. So this
    asserts the native degradation is under 0.7 of the Python one: the
    thing a horde actually needs, and not something the uniform-density
    ratio above would ever show. The bound is a ratio of ratios from
    four timings, so it is left loose on purpose.
    """
    count = 2000
    uniform = uniform_spread_for(count)

    _, python_uniform = _flock(count, spread=uniform, accelerate=False)
    _, python_clumped = _flock(count, spread=1200.0, accelerate=False)
    _, native_uniform = _flock(count, spread=uniform, accelerate=True)
    _, native_clumped = _flock(count, spread=1200.0, accelerate=True)

    python_penalty = measure(lambda: python_clumped.update(DT)) / measure(
        lambda: python_uniform.update(DT)
    )
    native_penalty = measure(lambda: native_clumped.update(DT)) / measure(
        lambda: native_uniform.update(DT)
    )

    assert native_penalty < python_penalty * 0.7, (
        f"clumping cost the native store {native_penalty:.2f}x against "
        f"Python's {python_penalty:.2f}x. The native store is supposed to "
        "degrade more gracefully with density, not less."
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("accelerate", STORES)
@pytest.mark.parametrize("count", [250, 500, 1000, 2000, 3000])
def test_sweep_flocking_uniform(benchmark, count: int, accelerate: bool) -> None:
    """Report ms/tick at uniform density. Asserts nothing; feeds the docs."""
    _, system = _flock(count, spread=uniform_spread_for(count), accelerate=accelerate)
    benchmark.pedantic(lambda: system.update(DT), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("accelerate", STORES)
@pytest.mark.parametrize("count", [500, 1000, 2000, 3000])
def test_sweep_flocking_clumped(benchmark, count: int, accelerate: bool) -> None:
    """Report ms/tick with the whole flock inside one small area."""
    _, system = _flock(count, spread=1200.0, accelerate=accelerate)
    benchmark.pedantic(lambda: system.update(DT), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("accelerate", STORES)
@pytest.mark.parametrize("groups", [1, 2, 3, 4])
def test_sweep_flocking_staggered(benchmark, groups: int, accelerate: bool) -> None:
    """Report ms/tick at 3000 agents with steering spread across `groups` ticks.

    Every agent still integrates its position every tick; only the
    steering decision is round-robined. This is the knob that decides
    whether a crowd of this size fits in a frame at all, so its cost
    curve is worth publishing next to the un-staggered one.
    """
    count = 3000
    _, system = _flock(count, spread=uniform_spread_for(count), accelerate=accelerate)
    system._groups = groups  # noqa: SLF001 - the ctor arg, set post-build
    benchmark.pedantic(lambda: system.update(DT), rounds=5, iterations=1)
