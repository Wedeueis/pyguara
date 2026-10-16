"""Tests for the feedback layer: `Sparks` and `Shaker`.

Both were demo code before they were engine code, and both have one
property worth pinning: they are bounded. A pool that quietly grew, or a
shake list that never retired an entry, would be a leak in exactly the
situation they exist for -- a busy frame.

Every `Sparks` test runs against both stores, the Python pool and the
native one, because a contributor without a Rust toolchain only ever sees
the first and the engine ships both. The native cases skip when the
extension is not built. `tests/test_native_spark_parity.py` is the other
half of that: this file asks whether each store behaves, that one asks
whether they agree.
"""

from __future__ import annotations

import math

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.vfx.shake import Shaker
from pyguara.graphics.vfx.sparks import Sparks

RED = Color(255, 0, 0)

# `False` is the Python pool, `True` the native one; see `_pool`.
STORES = [
    pytest.param(False, id="python"),
    pytest.param(True, id="native"),
]


def _pool(accelerate: bool, capacity: int, seed: int = 1) -> Sparks:
    """A spark pool on the requested store, skipping an absent extension."""
    if accelerate and not Sparks(capacity=1).accelerated:
        pytest.skip("native extension not built; `cargo build --release`")
    return Sparks(capacity=capacity, rng=RandomStream(seed), accelerate=accelerate)


def velocities(sparks: Sparks) -> list[tuple[float, float]]:
    """Every live spark's velocity, from whichever store holds it."""
    if sparks._native is not None:
        return [
            sparks._native.slot(i)[2:4]
            for i in range(sparks._capacity)
            if sparks._native.slot(i)[6]
        ]
    return [(s.velocity.x, s.velocity.y) for s in sparks._pool if s.active]


def positions(sparks: Sparks) -> list[tuple[float, float]]:
    """Every live spark's position, from whichever store holds it."""
    if sparks._native is not None:
        return [
            sparks._native.slot(i)[0:2]
            for i in range(sparks._capacity)
            if sparks._native.slot(i)[6]
        ]
    return [(s.position.x, s.position.y) for s in sparks._pool if s.active]


class _Recorder:
    """A renderer that records primitives and cannot take a batch.

    Deliberately not a `MagicMock`, which these tests used before there
    were two stores: a mock satisfies every `runtime_checkable` protocol,
    `ShapeBatchRenderer` included, so the native store would quietly take
    its batched route and the per-primitive assertions below would be
    asserting about a path no longer taken.
    """

    def __init__(self) -> None:
        self.circles: list[tuple[Vector2, float, Color]] = []
        self.lines: list[tuple[Vector2, Vector2, Color, int]] = []

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Record a circle."""
        self.circles.append((center, radius, color))

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Record a line."""
        self.lines.append((start, end, color, width))


@pytest.mark.parametrize("accelerate", STORES)
class TestSparkPool:
    def test_a_burst_emits_the_requested_count(self, accelerate: bool) -> None:
        sparks = _pool(accelerate, 64)
        sparks.burst(Vector2(10, 10), RED, count=12)

        assert sparks.live_count == 12

    def test_a_full_pool_drops_the_excess_rather_than_growing(
        self, accelerate: bool
    ) -> None:
        """The same contract `ParticleSystem` has: bounded, never resized."""
        sparks = _pool(accelerate, 8)
        sparks.burst(Vector2.zero(), RED, count=40)

        assert sparks.live_count == 8
        assert sparks._capacity == 8

    def test_particles_retire_when_their_life_runs_out(self, accelerate: bool) -> None:
        sparks = _pool(accelerate, 16)
        sparks.burst(Vector2.zero(), RED, count=6, life=0.2)

        sparks.update(1.0)

        assert sparks.live_count == 0

    def test_a_retired_slot_is_reused(self, accelerate: bool) -> None:
        sparks = _pool(accelerate, 4)
        sparks.burst(Vector2.zero(), RED, count=4, life=0.1)
        sparks.update(1.0)

        sparks.burst(Vector2.zero(), RED, count=4)

        assert sparks.live_count == 4

    def test_gravity_and_drag_move_a_particle(self, accelerate: bool) -> None:
        sparks = _pool(accelerate, 4)
        sparks.burst(
            Vector2.zero(),
            RED,
            count=1,
            speed=0.0,
            speed_jitter=0.0,
            life=5.0,
            gravity=100.0,
            drag=1.0,
        )

        sparks.update(0.5)

        # One step of Euler integration: velocity picks up gravity * dt,
        # then position picks up that velocity * dt.
        assert velocities(sparks)[0][1] == 50.0
        assert positions(sparks)[0][1] == 25.0

    def test_a_directed_burst_stays_inside_its_cone(self, accelerate: bool) -> None:
        sparks = _pool(accelerate, 64, seed=7)
        sparks.burst(
            Vector2.zero(),
            RED,
            count=32,
            direction=0.0,
            spread=0.4,
            speed=100.0,
            speed_jitter=0.0,
        )

        for x, y in velocities(sparks):
            assert abs(math.atan2(y, x)) <= 0.2 + 1e-6


@pytest.mark.parametrize("accelerate", STORES)
class TestSparkRendering:
    def test_only_live_particles_are_drawn(self, accelerate: bool) -> None:
        sparks = _pool(accelerate, 16)
        sparks.burst(Vector2.zero(), RED, count=5, life=1.0)
        renderer = _Recorder()

        sparks.render(renderer)

        assert len(renderer.circles) == 5

    def test_streaks_are_drawn_as_lines_rather_than_dots(
        self, accelerate: bool
    ) -> None:
        sparks = _pool(accelerate, 16)
        sparks.burst(Vector2.zero(), RED, count=5, life=1.0, streak=True)
        renderer = _Recorder()

        sparks.render(renderer)

        assert len(renderer.lines) == 5
        assert renderer.circles == []

    def test_the_offset_shifts_every_particle(self, accelerate: bool) -> None:
        sparks = _pool(accelerate, 4)
        sparks.burst(Vector2(100, 100), RED, count=1, speed=0.0, speed_jitter=0.0)
        renderer = _Recorder()

        sparks.render(renderer, Vector2(10, -5))

        centre = renderer.circles[0][0]
        assert (centre.x, centre.y) == (110, 95)

    def test_a_particle_fades_as_it_ages(self, accelerate: bool) -> None:
        sparks = _pool(accelerate, 4)
        sparks.burst(Vector2.zero(), RED, count=1, life=1.0, speed=0.0)
        renderer = _Recorder()

        sparks.render(renderer)
        full = renderer.circles[0][2].a
        sparks.update(0.5)
        sparks.render(renderer)
        half = renderer.circles[-1][2].a

        assert half < full


class TestShaker:
    def test_it_starts_still(self) -> None:
        assert Shaker(RandomStream(1)).offset == Vector2.zero()

    def test_a_shake_moves_the_offset(self) -> None:
        shaker = Shaker(RandomStream(1))
        shaker.add(10.0, duration=1.0)

        shaker.update(0.1)

        assert shaker.offset.magnitude > 0.0

    def test_a_shake_retires_once_its_duration_is_up(self) -> None:
        shaker = Shaker(RandomStream(1))
        shaker.add(10.0, duration=0.2)

        shaker.update(0.5)

        assert shaker.offset == Vector2.zero()
        assert shaker._shakes == []

    def test_overlapping_shakes_sum_rather_than_replace(self) -> None:
        """A second impact while the first is settling should add to it,
        not cut it short."""
        shaker = Shaker(RandomStream(1))
        shaker.add(6.0, duration=1.0)
        shaker.add(6.0, duration=1.0)

        shaker.update(0.05)

        assert len(shaker._shakes) == 2

    def test_a_zero_magnitude_shake_is_ignored(self) -> None:
        shaker = Shaker(RandomStream(1))
        shaker.add(0.0)

        assert shaker._shakes == []

    def test_update_returns_the_same_offset_it_stores(self) -> None:
        shaker = Shaker(RandomStream(1))
        shaker.add(8.0, duration=1.0)

        returned = shaker.update(0.1)

        assert returned == shaker.offset
