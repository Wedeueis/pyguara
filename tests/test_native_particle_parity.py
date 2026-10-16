"""The two particle stores must agree, or the accelerator is a bug factory.

Keeping a native pool alongside the Python one buys an installable
pure-Python engine and costs two implementations that have to behave the
same. This is where that cost is paid: the same operations run against
both and the results are compared.

Skipped wholesale when the extension is not built, which is the normal
state for a contributor without a Rust toolchain -- `cargo build --release`
makes these run.

Floats are compared with a tolerance because the native pool stores f32
where Python uses f64. That is a deliberate trade for memory and SIMD, and
the drift it produces is the thing this file bounds: a particle is a
visual effect, not a simulation anyone replays, so sub-pixel disagreement
over a lifetime is acceptable. If these tolerances ever have to be
loosened, that is a finding rather than a maintenance chore.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.graphics.components.particles import ParticleSystem

CAPACITY = 64
DT = 1.0 / 60.0


def _available() -> bool:
    """Whether the native extension is present."""
    return ParticleSystem(capacity=1).accelerated


pytestmark = pytest.mark.skipif(
    not _available(), reason="native extension not built; `cargo build --release`"
)


def _pair(capacity: int = CAPACITY, seed: int = 99) -> tuple[ParticleSystem, ...]:
    """A Python pool and a native pool on identical seeded streams.

    The same seed matters: `emit` takes three draws per particle, so two
    pools on different streams spawn different particles and nothing can be
    compared.
    """
    return (
        ParticleSystem(capacity, RandomStream(seed), accelerate=False),
        ParticleSystem(capacity, RandomStream(seed), accelerate=True),
    )


def test_the_same_seed_spawns_the_same_count() -> None:
    python_pool, native_pool = _pair()
    texture = MagicMock()

    for pool in (python_pool, native_pool):
        pool.emit(texture, Vector2(10.0, 20.0), count=12, speed=100.0, life=2.0)

    assert python_pool.live_count == native_pool.live_count == 12


def test_a_burst_larger_than_the_pool_fills_it_and_stops() -> None:
    """Both drop the remainder rather than evicting a live particle."""
    python_pool, native_pool = _pair(capacity=8)
    texture = MagicMock()

    for pool in (python_pool, native_pool):
        pool.emit(texture, Vector2(0.0, 0.0), count=50, speed=50.0, life=5.0)

    assert python_pool.live_count == native_pool.live_count == 8


def test_an_overflowing_burst_leaves_both_streams_in_step() -> None:
    """The subtle one, and the reason `_emit_native` counts free slots.

    The Python loop asks for a slot before it draws, so an emission that
    overflows consumes nothing for the particles it drops. A native path
    that drew `count` sets regardless would come out of the emission with
    its stream further along -- and then *every later emission* would
    differ, while the one that caused it looked perfectly fine. This
    asserts on a later emission for exactly that reason.
    """
    python_pool, native_pool = _pair(capacity=8)
    texture = MagicMock()

    for pool in (python_pool, native_pool):
        pool.emit(texture, Vector2.zero(), count=40, speed=50.0, life=0.05)
        for _ in range(10):  # retire the lot, freeing the pool
            pool.update(DT)
        assert pool.live_count == 0
        pool.emit(texture, Vector2.zero(), count=4, speed=100.0, life=5.0)

    expected = sorted(
        (p.velocity.x, p.velocity.y) for p in python_pool._pool if p.active
    )
    got = sorted(
        native_pool._native.slot(i)[2:4]
        for i in range(8)
        if native_pool._native.slot(i)[6]
    )

    assert len(expected) == len(got) == 4
    for (ex, ey), (gx, gy) in zip(expected, got, strict=True):
        assert gx == pytest.approx(ex, abs=0.01)
        assert gy == pytest.approx(ey, abs=0.01)


def test_positions_agree_after_a_hundred_ticks() -> None:
    """The integration, compared where it has had time to diverge."""
    python_pool, native_pool = _pair()
    texture = MagicMock()
    for pool in (python_pool, native_pool):
        pool.emit(
            texture,
            Vector2(0.0, 0.0),
            count=8,
            speed=120.0,
            life=100.0,
            damping=0.99,
            acceleration=Vector2(0.0, 300.0),
        )

    for _ in range(100):
        python_pool.update(DT)
        native_pool.update(DT)

    expected = sorted(
        (p.position.x, p.position.y) for p in python_pool._pool if p.active
    )
    got = sorted(
        native_pool._native.slot(i)[:2]
        for i in range(native_pool._capacity)
        if native_pool._native.slot(i)[6]
    )

    assert len(got) == len(expected) == 8
    for (ex, ey), (gx, gy) in zip(expected, got, strict=True):
        assert gx == pytest.approx(ex, abs=0.05)
        assert gy == pytest.approx(ey, abs=0.05)


def test_particles_expire_on_the_same_tick() -> None:
    python_pool, native_pool = _pair()
    texture = MagicMock()
    for pool in (python_pool, native_pool):
        pool.emit(texture, Vector2(0.0, 0.0), count=5, speed=10.0, life=0.1)

    counts: list[tuple[int, int]] = []
    for _ in range(10):
        python_pool.update(DT)
        native_pool.update(DT)
        counts.append((python_pool.live_count, native_pool.live_count))

    assert all(python == native for python, native in counts), counts
    assert counts[-1] == (0, 0)


def test_render_produces_the_same_batches() -> None:
    """The packing path: one batch per texture, same positions, same tint
    decision."""
    python_pool, native_pool = _pair()
    first, second = MagicMock(name="first"), MagicMock(name="second")
    for pool in (python_pool, native_pool):
        pool.emit(first, Vector2(5.0, 5.0), count=4, speed=0.0, life=10.0)
        pool.emit(second, Vector2(50.0, 50.0), count=3, speed=0.0, life=10.0)

    python_backend, native_backend = _recording_backend(), _recording_backend()
    camera = _camera()
    python_pool.render(python_backend, camera)
    native_pool.render(native_backend, camera)

    python_batches = _summarise(python_backend)
    native_batches = _summarise(native_backend)

    assert {t for t, _, _ in python_batches} == {t for t, _, _ in native_batches}
    assert dict((t, n) for t, n, _ in python_batches) == dict(
        (t, n) for t, n, _ in native_batches
    )
    assert dict((t, c) for t, _, c in python_batches) == dict(
        (t, c) for t, _, c in native_batches
    )


def test_a_colour_animation_tints_both_the_same_way() -> None:
    """`colors_enabled` must agree, or one path silently skips tinting."""
    python_pool, native_pool = _pair()
    texture = MagicMock()
    for pool in (python_pool, native_pool):
        pool.emit(
            texture,
            Vector2(0.0, 0.0),
            count=4,
            speed=0.0,
            life=1.0,
            color_start=(255, 0, 0, 255),
            color_end=(0, 0, 255, 0),
        )
    # Deliberately NOT halfway. At t=0.5 the lerp is symmetric, so a
    # reversed one gives the same answer and this test passes while
    # proving nothing -- which is exactly what it did at 30 ticks.
    for _ in range(20):  # a third of the way through a 1.0s life
        python_pool.update(DT)
        native_pool.update(DT)

    python_backend, native_backend = _recording_backend(), _recording_backend()
    python_pool.render(python_backend, _camera())
    native_pool.render(native_backend, _camera())

    python_batch = python_backend.render_batch.call_args.args[0]
    native_batch = native_backend.render_batch.call_args.args[0]

    assert python_batch.colors_enabled is native_batch.colors_enabled is True
    for expected, got in zip(python_batch.colors, native_batch.colors, strict=True):
        for channel_expected, channel_got in zip(expected, got, strict=True):
            assert abs(channel_expected - channel_got) <= 1


def _recording_backend() -> MagicMock:
    """A renderer that records the batches handed to it."""
    backend = MagicMock()
    backend.width = 800
    backend.height = 600
    return backend


def _camera() -> MagicMock:
    """A camera with no zoom and no offset, so screen space is world space."""
    camera = MagicMock()
    camera.zoom = 1.0
    camera.screen_offset.return_value = Vector2(0.0, 0.0)
    return camera


def _summarise(backend: MagicMock) -> list[tuple[int, int, bool]]:
    """`(texture id, destination count, colours enabled)` per batch."""
    summary = []
    for call in backend.render_batch.call_args_list:
        batch = call.args[0]
        summary.append(
            (id(batch.texture), len(batch.destinations), batch.colors_enabled)
        )
    return summary
