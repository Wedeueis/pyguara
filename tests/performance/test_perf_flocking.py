"""How many boids can `FlockingSystem` steer in a frame?

A flocking tick is O(n * k): n agents, each visiting the k neighbours
the spatial hash returns, so density is a second variable.

Uniform holds agents-per-cell constant while n grows, which isolates
the n term; the linearity guard uses it. Clumped packs every agent
into a fixed area, so k grows with n and the tick goes quadratic, as a
horde converging on a player does. Its guard bounds how badly.
"""

from __future__ import annotations

import time

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


def _fastest_interleaved(*systems: FlockingSystem, rounds: int = 15) -> list[float]:
    """Each system's fastest tick, taking turns so they share the same load."""
    best = [float("inf")] * len(systems)
    for _ in range(rounds):
        for index, system in enumerate(systems):
            start = time.perf_counter()
            system.update(DT)
            best[index] = min(best[index], time.perf_counter() - start)
    return best


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
    """The native tick is a small fraction of the Python one at 1000 agents.

    A ratio, not a wall-clock budget, and a loose one: its job is to
    notice that the native path stopped being taken. A loader that finds
    no library falls back to Python and every parity test skips, so this
    is one of the few places a missing extension fails.
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
    """Clumping degrades the native store less than the Python one.

    A flock converging on the player makes k proportional to n. Clumping
    multiplies the per-neighbour arithmetic, which is where the native
    store gains. Asserted: native degradation under 0.8 of Python's.

    The four timings are interleaved because this is a ratio of ratios;
    measured one after another, the result spreads too widely on a busy
    machine.
    """
    count = 2000
    uniform = uniform_spread_for(count)

    _, python_uniform = _flock(count, spread=uniform, accelerate=False)
    _, python_clumped = _flock(count, spread=1200.0, accelerate=False)
    _, native_uniform = _flock(count, spread=uniform, accelerate=True)
    _, native_clumped = _flock(count, spread=1200.0, accelerate=True)

    py_uniform, py_clumped, nat_uniform, nat_clumped = _fastest_interleaved(
        python_uniform, python_clumped, native_uniform, native_clumped
    )
    python_penalty = py_clumped / py_uniform
    native_penalty = nat_clumped / nat_uniform

    assert native_penalty < python_penalty * 0.8, (
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
