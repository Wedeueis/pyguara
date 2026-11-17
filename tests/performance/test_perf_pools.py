"""What the self-contained object pools cost per frame.

`ParticleSystem`, `Sparks` and `ProjectileSystem` each pre-allocate a
pool and iterate its whole capacity every frame. A dead slot costs one
boolean test; the cost is integrating the live ones.

`ParticleSystem` is pinned to its Python store with `accelerate=False`,
the baseline its native figures in `docs/guides/performance.md` are
quoted against. `Sparks` has only a Rust pool; its Python baseline is
`tests.reference.sparks`. One test checks Rust is materially faster.
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
from tests.reference.sparks import ReferenceSparks

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
    system = ParticleSystem(capacity=capacity, accelerate=False)
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
    return _burst_into(Sparks(capacity=capacity), live)


def _python_sparks(capacity: int, live: int) -> ReferenceSparks:
    """The Python reference pool with `live` of `capacity` slots occupied."""
    return _burst_into(ReferenceSparks(capacity=capacity), live)


def _burst_into(pool, live: int):
    """Occupy `live` slots of a spark pool, Rust or reference."""
    if live:
        pool.burst(
            Vector2(0.0, 0.0),
            count=live,
            life=1e6,
            color=Color(255, 255, 255),
        )
    return pool


@pytest.mark.performance
@pytest.mark.parametrize("make", [_particles], ids=["particles"])
def test_the_cost_is_the_live_elements_not_the_dead_slots(make) -> None:
    """Where the time actually goes, which is not where it looks.

    Particles only: in the Rust spark pool a live spark is nearly as
    cheap as a dead slot, so the ratio says nothing there.

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


@pytest.mark.performance
@pytest.mark.parametrize(
    ("make", "native"),
    [
        (_particles, lambda n: ParticleSystem(capacity=n)),
        (_python_sparks, lambda n: Sparks(capacity=n)),
    ],
    ids=["particles", "sparks"],
)
def test_the_native_store_is_wired_up_and_materially_faster(make, native) -> None:
    """That the accelerator is reached at all, which is easy to lose.

    The loader falls back silently when the extension is missing or stale,
    so a broken build would show only as the Python pool.

    Asserted at a quarter of the Python cost, loosely, for a shared
    runner; the exact figure is in `docs/guides/performance.md`.
    """
    accelerated = native(CAPACITY)
    if isinstance(accelerated, ParticleSystem) and not accelerated.accelerated:
        pytest.skip("native extension not built; `cargo build --release`")

    python_pool = make(CAPACITY, CAPACITY)
    _fill(accelerated, CAPACITY)

    python_time = measure(lambda: python_pool.update(1.0 / 60.0))
    native_time = measure(lambda: accelerated.update(1.0 / 60.0))

    assert native_time < python_time * 0.25, (
        f"the native store took {native_time / max(python_time, 1e-9):.0%} of "
        f"the Python one. Either it is not actually being used, or the "
        f"arithmetic has regressed to within noise of interpreted Python."
    )


def _fill(pool, live: int) -> None:
    """Occupy `live` slots, whichever pool kind this is."""
    if isinstance(pool, Sparks):
        pool.burst(Vector2(0.0, 0.0), Color(255, 255, 255), count=live, life=1e6)
    else:
        pool.emit(_FakeTexture(), Vector2(0.0, 0.0), count=live, life=1e6)
