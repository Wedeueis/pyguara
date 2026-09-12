"""Tests for the feedback layer: `Sparks` and `Shaker`.

Both were demo code before they were engine code, and both have one
property worth pinning: they are bounded. A pool that quietly grew, or a
shake list that never retired an entry, would be a leak in exactly the
situation they exist for -- a busy frame.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.vfx.shake import Shaker
from pyguara.graphics.vfx.sparks import Sparks

RED = Color(255, 0, 0)


def live(sparks: Sparks) -> int:
    """Count the particles currently alive in the pool."""
    return sum(1 for spark in sparks._pool if spark.active)


class TestSparkPool:
    def test_a_burst_emits_the_requested_count(self) -> None:
        sparks = Sparks(capacity=64, rng=RandomStream(1))
        sparks.burst(Vector2(10, 10), RED, count=12)

        assert live(sparks) == 12

    def test_a_full_pool_drops_the_excess_rather_than_growing(self) -> None:
        """The same contract `ParticleSystem` has: bounded, never resized."""
        sparks = Sparks(capacity=8, rng=RandomStream(1))
        sparks.burst(Vector2.zero(), RED, count=40)

        assert live(sparks) == 8
        assert len(sparks._pool) == 8

    def test_particles_retire_when_their_life_runs_out(self) -> None:
        sparks = Sparks(capacity=16, rng=RandomStream(1))
        sparks.burst(Vector2.zero(), RED, count=6, life=0.2)

        sparks.update(1.0)

        assert live(sparks) == 0

    def test_a_retired_slot_is_reused(self) -> None:
        sparks = Sparks(capacity=4, rng=RandomStream(1))
        sparks.burst(Vector2.zero(), RED, count=4, life=0.1)
        sparks.update(1.0)

        sparks.burst(Vector2.zero(), RED, count=4)

        assert live(sparks) == 4

    def test_gravity_and_drag_move_a_particle(self) -> None:
        sparks = Sparks(capacity=4, rng=RandomStream(1))
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

        spark = next(s for s in sparks._pool if s.active)
        # One step of Euler integration: velocity picks up gravity * dt,
        # then position picks up that velocity * dt.
        assert spark.velocity.y == 50.0
        assert spark.position.y == 25.0

    def test_a_directed_burst_stays_inside_its_cone(self) -> None:
        sparks = Sparks(capacity=64, rng=RandomStream(7))
        sparks.burst(
            Vector2.zero(),
            RED,
            count=32,
            direction=0.0,
            spread=0.4,
            speed=100.0,
            speed_jitter=0.0,
        )

        for spark in sparks._pool:
            if spark.active:
                angle = math.atan2(spark.velocity.y, spark.velocity.x)
                assert abs(angle) <= 0.2 + 1e-6


class TestSparkRendering:
    def test_only_live_particles_are_drawn(self) -> None:
        sparks = Sparks(capacity=16, rng=RandomStream(1))
        sparks.burst(Vector2.zero(), RED, count=5, life=1.0)
        renderer = MagicMock()

        sparks.render(renderer)

        assert renderer.draw_circle.call_count == 5

    def test_streaks_are_drawn_as_lines_rather_than_dots(self) -> None:
        sparks = Sparks(capacity=16, rng=RandomStream(1))
        sparks.burst(Vector2.zero(), RED, count=5, life=1.0, streak=True)
        renderer = MagicMock()

        sparks.render(renderer)

        assert renderer.draw_line.call_count == 5
        renderer.draw_circle.assert_not_called()

    def test_the_offset_shifts_every_particle(self) -> None:
        sparks = Sparks(capacity=4, rng=RandomStream(1))
        sparks.burst(Vector2(100, 100), RED, count=1, speed=0.0, speed_jitter=0.0)
        renderer = MagicMock()

        sparks.render(renderer, Vector2(10, -5))

        centre = renderer.draw_circle.call_args[0][0]
        assert (centre.x, centre.y) == (110, 95)

    def test_a_particle_fades_as_it_ages(self) -> None:
        sparks = Sparks(capacity=4, rng=RandomStream(1))
        sparks.burst(Vector2.zero(), RED, count=1, life=1.0, speed=0.0)
        renderer = MagicMock()

        sparks.render(renderer)
        full = renderer.draw_circle.call_args[0][2].a
        sparks.update(0.5)
        sparks.render(renderer)
        half = renderer.draw_circle.call_args[0][2].a

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
