"""What the particle and spark pools cost per frame.

`ParticleSystem` and `Sparks` each pre-allocate a pool and walk its
whole capacity every frame. Both are held in Rust; their Python
baselines are the pools in `tests.reference`. One test checks Rust is
materially faster, and one that the walk stays linear in capacity.
The figures are in `docs/guides/performance.md`.
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
from tests.reference.particles import ReferenceParticles
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
    return _emit_into(ParticleSystem(capacity=capacity), live)


def _python_particles(capacity: int, live: int) -> ReferenceParticles:
    """The Python reference pool with `live` of `capacity` slots occupied."""
    return _emit_into(ReferenceParticles(capacity=capacity), live)


def _emit_into(system, live: int):
    """Occupy `live` slots of a particle pool, Rust or reference."""
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
    ("python", "rust"),
    [(_python_particles, _particles), (_python_sparks, _sparks)],
    ids=["particles", "sparks"],
)
def test_the_rust_pool_is_materially_faster_than_the_python_it_replaced(
    python, rust
) -> None:
    """The reason the pools are in Rust, kept as a measurement.

    Asserted at a quarter of the Python cost, loosely, for a shared
    runner; the exact figure is in `docs/guides/performance.md`.
    """
    python_pool = python(CAPACITY, CAPACITY)
    rust_pool = rust(CAPACITY, CAPACITY)

    python_time = measure(lambda: python_pool.update(1.0 / 60.0))
    rust_time = measure(lambda: rust_pool.update(1.0 / 60.0))

    assert rust_time < python_time * 0.25, (
        f"the Rust pool took {rust_time / max(python_time, 1e-9):.0%} of the "
        f"Python reference. The arithmetic has regressed to within noise of "
        f"interpreted Python."
    )
