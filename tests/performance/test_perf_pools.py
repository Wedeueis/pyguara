"""What the self-contained object pools cost per frame.

`ParticleSystem`, `Sparks` and `ProjectileSystem` each pre-allocate a pool
and hand out slots from it, so they allocate nothing per frame -- the thing
an audit usually flags about per-particle Python objects does not apply.

They do iterate their **whole capacity** every frame, live slots and dead
ones alike (`particles.py:263`/`:312`, `sparks.py:131`/`:154`,
`projectiles/system.py:124`/`:192`), and that reads like the thing to fix.
Measured, it is not: an idle 1000-slot pool costs **0.024 ms**, because a
dead slot is one boolean test. A *full* one costs **2.2 ms**, and 4000 live
particles cost **9.0 ms** -- over half a frame. Per slot that is 0.024 us
dead against 2.2 us live, ninety times the difference.

So the cost is the live integration, not the scan, and compacting the pool
to skip dead slots would buy back 0.024 ms. Worth knowing before anyone
spends a day on it.

Nothing measured any of this before. These exist for RFC-0003: its Marco 3
replaces all three pools with Rust SoA, and a milestone claiming 45x needs
a baseline it can be held to. These numbers say where that 45x would have
to come from -- the per-element arithmetic, which is exactly what SoA plus
SIMD addresses, rather than the bookkeeping.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Color, Vector2
from pyguara.graphics.components.particles import ParticleSystem
from pyguara.graphics.vfx.sparks import Sparks
from tests.performance.conftest import (
    assert_scales_no_worse_than,
    measure,
)

CAPACITY = 1000


class _FakeTexture:
    """A texture the pools can hold without a GL context."""

    @property
    def width(self) -> int:
        """Width in pixels."""
        return 8

    @property
    def height(self) -> int:
        """Height in pixels."""
        return 8

    @property
    def native_handle(self) -> object:
        """Whatever a renderer would bind; never bound here."""
        return self


def _particles(capacity: int, live: int) -> ParticleSystem:
    """A particle system with `live` of `capacity` slots occupied."""
    system = ParticleSystem(capacity=capacity)
    if live:
        system.emit(
            _FakeTexture(),  # type: ignore[arg-type]
            Vector2(0.0, 0.0),
            count=live,
            life=1e6,  # outlive the measurement
        )
    return system


def _sparks(capacity: int, live: int) -> Sparks:
    """A spark pool with `live` of `capacity` slots occupied."""
    pool = Sparks(capacity=capacity)
    if live:
        pool.burst(
            Vector2(0.0, 0.0),
            count=live,
            life=1e6,
            color=Color(255, 255, 255),
        )
    return pool


@pytest.mark.performance
@pytest.mark.parametrize("make", [_particles, _sparks], ids=["particles", "sparks"])
def test_the_cost_is_the_live_elements_not_the_dead_slots(make) -> None:
    """Where the time actually goes, which is not where it looks.

    Walking the whole capacity every frame is real and is cheap: a dead
    slot is one boolean test. The integration of a live element is ~90x
    that. This pins the ratio so that "compact the pool" is recognisable
    as the wrong optimisation without re-deriving it.

    A ratio rather than a budget, so it is safe on a shared runner.
    """
    empty = make(CAPACITY, 0)
    full = make(CAPACITY, CAPACITY)

    idle = measure(lambda: empty.update(1.0 / 60.0))
    busy = measure(lambda: full.update(1.0 / 60.0))

    assert idle < busy * 0.2, (
        f"an idle pool cost {idle / max(busy, 1e-9):.1%} of a full one. If "
        f"dead slots have become expensive, skipping them is worth doing "
        f"after all -- which this asserts is not currently the case."
    )


@pytest.mark.performance
@pytest.mark.parametrize("make", [_particles, _sparks], ids=["particles", "sparks"])
def test_pool_update_scales_no_worse_than_linearly_with_capacity(make) -> None:
    """Capacity, not occupancy, is what the scan walks."""
    small = make(CAPACITY, CAPACITY)
    large = make(CAPACITY * 4, CAPACITY * 4)

    small_time = measure(lambda: small.update(1.0 / 60.0))
    large_time = measure(lambda: large.update(1.0 / 60.0))

    assert_scales_no_worse_than(
        small=small_time,
        large=large_time,
        factor=4,
        limit=8.0,
        what=f"{make.__name__.strip('_')} pool update at 4x the capacity",
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("live", [0, 10, 1000])
def test_sweep_particle_update(benchmark, live: int) -> None:
    """Sweep: the `docs/guides/performance.md` figures. Asserts nothing."""
    system = _particles(CAPACITY, live)

    benchmark(lambda: system.update(1.0 / 60.0))


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("live", [0, 10, 1000])
def test_sweep_spark_update(benchmark, live: int) -> None:
    """Sweep: the `docs/guides/performance.md` figures. Asserts nothing."""
    pool = _sparks(CAPACITY, live)

    benchmark(lambda: pool.update(1.0 / 60.0))
