"""Tests for `pyguara/kits/echolocation/`.

The sweep is tested against a fake ray caster rather than a physics world:
the kit takes a callable precisely so it does not depend on a backend, and
testing it that way keeps the occlusion rule (a ray stops at the first
surface) checkable without building a cave first.
"""

from __future__ import annotations

import math

from pyguara.common.types import Vector2
from pyguara.kits.echolocation import (
    ActivePulse,
    PulseEmitter,
    RevealMemory,
    start_pulse,
    sweep,
    tick_cooldown,
)

# ========== PulseEmitter / start_pulse ==========


class TestEmitter:
    def test_a_fresh_emitter_is_ready(self) -> None:
        assert PulseEmitter().is_ready

    def test_starting_a_pulse_puts_it_on_cooldown(self) -> None:
        emitter = PulseEmitter()
        start_pulse(emitter, Vector2(0, 0), scream=False)
        assert not emitter.is_ready

    def test_the_cooldown_ticks_back_to_ready(self) -> None:
        emitter = PulseEmitter(cooldown=0.2)
        start_pulse(emitter, Vector2(0, 0), scream=False)
        tick_cooldown(emitter, 0.25)
        assert emitter.is_ready

    def test_a_scream_reaches_further_and_lasts_longer_than_a_chirp(self) -> None:
        emitter = PulseEmitter()
        chirp = start_pulse(emitter, Vector2(0, 0), scream=False)
        scream = start_pulse(emitter, Vector2(0, 0), scream=True)
        assert scream.max_radius > chirp.max_radius
        assert scream.duration > chirp.duration
        assert scream.is_scream and not chirp.is_scream


class TestActivePulse:
    def test_radius_grows_from_zero_to_its_maximum(self) -> None:
        pulse = ActivePulse(origin=Vector2(0, 0), max_radius=100.0, duration=1.0)
        assert pulse.radius == 0.0
        pulse.elapsed = 1.0
        assert pulse.radius == 100.0

    def test_the_front_decelerates_rather_than_ramping_linearly(self) -> None:
        pulse = ActivePulse(origin=Vector2(0, 0), max_radius=100.0, duration=1.0)
        pulse.elapsed = 0.5
        # Eased out: half the time has carried it well past half the way.
        assert pulse.radius > 60.0

    def test_intensity_fades_as_it_expands(self) -> None:
        pulse = ActivePulse(origin=Vector2(0, 0), max_radius=100.0, duration=1.0)
        assert pulse.intensity == 1.0
        pulse.elapsed = 1.0
        assert pulse.intensity == 0.0

    def test_it_reports_itself_spent_at_the_end(self) -> None:
        pulse = ActivePulse(origin=Vector2(0, 0), max_radius=100.0, duration=0.5)
        assert not pulse.is_spent
        pulse.elapsed = 0.5
        assert pulse.is_spent

    def test_a_zero_duration_pulse_does_not_divide_by_zero(self) -> None:
        pulse = ActivePulse(origin=Vector2(0, 0), max_radius=10.0, duration=0.0)
        assert pulse.progress == 1.0


# ========== sweep ==========


class TestSweep:
    def test_it_casts_the_requested_number_of_rays(self) -> None:
        hits = sweep(lambda _s, _e: None, Vector2(0, 0), 50.0, ray_count=16)
        assert len(hits) == 16

    def test_a_clear_ray_reports_the_full_radius(self) -> None:
        hits = sweep(lambda _s, _e: None, Vector2(0, 0), 50.0, ray_count=4)
        assert all(hit.entity_id is None for hit in hits)
        assert all(abs(hit.distance - 50.0) < 0.001 for hit in hits)

    def test_a_blocked_ray_stops_at_the_surface(self) -> None:
        def raycast(start: Vector2, end: Vector2):
            del end
            return (start + Vector2(10, 0), "wall")

        hits = sweep(raycast, Vector2(0, 0), 100.0, ray_count=4)
        assert all(hit.entity_id == "wall" for hit in hits)
        assert all(abs(hit.distance - 10.0) < 0.001 for hit in hits)

    def test_rays_are_spread_around_the_full_circle(self) -> None:
        hits = sweep(lambda _s, _e: None, Vector2(0, 0), 10.0, ray_count=4)
        angles = sorted(
            round(math.degrees(math.atan2(h.point.y, h.point.x))) % 360 for h in hits
        )
        assert angles == [0, 90, 180, 270]

    def test_start_angle_rotates_the_whole_fan(self) -> None:
        straight = sweep(lambda _s, _e: None, Vector2(0, 0), 10.0, ray_count=4)
        rotated = sweep(
            lambda _s, _e: None,
            Vector2(0, 0),
            10.0,
            ray_count=4,
            start_angle=math.pi / 4,
        )
        assert straight[0].point.to_tuple() != rotated[0].point.to_tuple()

    def test_a_zero_radius_pulse_sweeps_nothing(self) -> None:
        assert sweep(lambda _s, _e: None, Vector2(0, 0), 0.0, ray_count=8) == []


# ========== RevealMemory ==========


class TestRevealMemory:
    def test_an_unrevealed_key_is_dark(self) -> None:
        assert RevealMemory().brightness("nowhere") == 0.0

    def test_revealing_lights_a_key_up(self) -> None:
        memory = RevealMemory()
        memory.reveal((1, 2), 0.8)
        assert memory.brightness((1, 2)) == 0.8

    def test_revealing_again_keeps_the_brighter_value(self) -> None:
        memory = RevealMemory()
        memory.reveal((1, 2), 0.8)
        memory.reveal((1, 2), 0.3)
        assert memory.brightness((1, 2)) == 0.8

    def test_decay_fades_toward_darkness(self) -> None:
        memory = RevealMemory(decay_per_second=0.5)
        memory.reveal((0, 0), 1.0)
        memory.decay(1.0)
        assert memory.brightness((0, 0)) == 0.5

    def test_a_fully_faded_key_is_dropped_entirely(self) -> None:
        """Kept small on purpose: the dict is what gets iterated to draw."""
        memory = RevealMemory(decay_per_second=1.0)
        memory.reveal((0, 0), 0.5)
        memory.decay(1.0)
        assert memory.items() == []

    def test_dim_scales_everything_down(self) -> None:
        memory = RevealMemory()
        memory.reveal((0, 0), 1.0)
        memory.dim(0.5)
        assert memory.brightness((0, 0)) == 0.5

    def test_dim_can_cap_before_scaling_so_fresh_reveals_lose_too(self) -> None:
        memory = RevealMemory()
        memory.reveal((0, 0), 1.0)
        memory.reveal((1, 0), 0.4)
        memory.dim(0.5, ceiling=0.4)
        assert memory.brightness((0, 0)) == 0.2
        assert memory.brightness((1, 0)) == 0.2

    def test_clear_forgets_everything(self) -> None:
        memory = RevealMemory()
        memory.reveal((0, 0), 1.0)
        memory.clear()
        assert memory.items() == []
