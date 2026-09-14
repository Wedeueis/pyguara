"""Tests for the run clock, the phase table and the glow it drives.

The demo cannot boot headlessly -- it is ModernGL, and SDL's dummy driver
has no OpenGL -- so the night's whole shape is tested here instead, as
data: a cycle, a phase table read off it, and a glow read off the light
that cycle writes.
"""

from __future__ import annotations

import pytest

from games.tamandua_murundus.phases import (
    BRIGHTEST,
    CYCLE_KEYFRAMES,
    DARKEST,
    DAWN_HOLD_PHASE,
    PHASES,
    RUN_SECONDS,
    glow_for_intensity,
    phase_at,
)
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.lighting.components import AmbientLight
from pyguara.graphics.lighting.cycle import (
    AmbientCycle,
    AmbientCycleSystem,
    sample_cycle,
)


def run_to(seconds: float) -> tuple[float, float]:
    """Tick a real cycle to `seconds` and return its intensity and glow."""
    entity_manager = EntityManager()
    entity = entity_manager.create_entity("ambient")
    entity.add_component(AmbientLight())
    entity.add_component(AmbientCycle(keyframes=CYCLE_KEYFRAMES, duration=RUN_SECONDS))
    system = AmbientCycleSystem(entity_manager)

    elapsed = 0.0
    while elapsed < seconds:
        system.update(1.0)
        elapsed += 1.0

    intensity = entity.get_component(AmbientLight).intensity
    return intensity, glow_for_intensity(intensity)


class TestGlowCurve:
    def test_the_brightest_ambient_means_no_glow(self) -> None:
        assert glow_for_intensity(BRIGHTEST) == pytest.approx(0.0)

    def test_the_darkest_ambient_means_full_glow(self) -> None:
        assert glow_for_intensity(DARKEST) == pytest.approx(1.0)

    def test_the_glow_is_clamped_outside_the_curve(self) -> None:
        """The cycle interpolates, so a keyframe pair can put the ambient
        a hair outside the range these constants describe."""
        assert glow_for_intensity(BRIGHTEST + 1.0) == pytest.approx(0.0)
        assert glow_for_intensity(DARKEST - 1.0) == pytest.approx(1.0)

    def test_the_glow_rises_as_the_light_falls(self) -> None:
        """The claim the demo makes: one curve, read from both ends."""
        bright = glow_for_intensity(0.6)
        dim = glow_for_intensity(0.3)
        dark = glow_for_intensity(0.12)

        assert bright < dim < dark


class TestPhaseTable:
    def test_a_run_starts_at_dusk(self) -> None:
        assert phase_at(0.0).name == "ANOITECER"

    def test_the_last_phase_that_has_started_is_the_current_one(self) -> None:
        assert phase_at(0.34).name == "NOITE"
        assert phase_at(0.60).name == "NOITE FECHADA"

    def test_a_run_ends_at_dawn(self) -> None:
        assert phase_at(0.99).name == "AMANHECER"

    def test_the_phase_wraps_like_the_cycle_does(self) -> None:
        """The table is read with the cycle's own phase, which wraps."""
        assert phase_at(1.25).name == phase_at(0.25).name

    def test_pressure_rises_monotonically_until_dawn(self) -> None:
        """A difficulty curve that dips mid-run reads as a bug."""
        before_dawn = [phase.release_per_feed for phase in PHASES[:-1]]

        assert before_dawn == sorted(before_dawn)

    def test_dawn_stops_the_spawns(self) -> None:
        """Which is what ends the run's pressure, with no separate flag."""
        assert PHASES[-1].release_per_feed == 0

    def test_every_phase_is_reachable(self) -> None:
        """A phase whose window is closed by the next one starting at the
        same point would never show, and nothing else would say so."""
        seen = {phase_at(step / 500.0).name for step in range(500)}

        assert seen == {phase.name for phase in PHASES}


class TestTheNightsShape:
    """The curve and the table have to agree. They are separate data, and
    nothing but a test stops them drifting apart."""

    def test_the_peak_phase_lands_in_the_dark(self) -> None:
        """An earlier table put REVOADA past the darkest point, so the HUD
        announced the climax over a frame that looked like dusk."""
        revoada = next(phase for phase in PHASES if phase.name == "REVOADA")
        sampled = sample_cycle(CYCLE_KEYFRAMES, revoada.starts_at)

        assert sampled is not None
        assert glow_for_intensity(sampled[1]) > 0.85

    def test_dawn_lands_where_the_light_returns(self) -> None:
        dawn = next(phase for phase in PHASES if phase.name == "AMANHECER")
        at_dawn = sample_cycle(CYCLE_KEYFRAMES, dawn.starts_at)
        later = sample_cycle(CYCLE_KEYFRAMES, 0.97)

        assert at_dawn is not None and later is not None
        assert later[1] > at_dawn[1]

    def test_the_clearing_darkens_through_the_middle_of_the_run(self) -> None:
        _, early = run_to(30.0)
        _, middle = run_to(120.0)
        _, late = run_to(190.0)

        assert early < middle < late

    def test_the_clearing_is_bright_again_by_the_end(self) -> None:
        """A run that ended in the dark would have no resolution."""
        _, deep_night = run_to(190.0)
        _, dawn = run_to(RUN_SECONDS)

        assert dawn < deep_night
        assert dawn < 0.2

    def test_one_loop_of_the_cycle_is_one_run(self) -> None:
        """The time of day *is* the run clock -- one number driving the
        light, the tint and the spawn rate, with no way to drift."""
        entity_manager = EntityManager()
        entity = entity_manager.create_entity("ambient")
        entity.add_component(AmbientLight())
        cycle = AmbientCycle(keyframes=CYCLE_KEYFRAMES, duration=RUN_SECONDS)
        entity.add_component(cycle)
        system = AmbientCycleSystem(entity_manager)

        for _ in range(int(RUN_SECONDS) // 2):
            system.update(1.0)

        assert cycle.phase == pytest.approx(0.5, abs=0.01)


class TestTheEndOfTheRun:
    def test_the_hold_point_is_still_first_light_not_dusk(self) -> None:
        """The bug this constant exists for: a cycle is a ring, so a run
        allowed to tick to 1.0 is back at phase 0 -- dusk. Holding a hair
        short of the wrap keeps the clearing at dawn."""
        held = sample_cycle(CYCLE_KEYFRAMES, DAWN_HOLD_PHASE)
        wrapped = sample_cycle(CYCLE_KEYFRAMES, 1.0)

        assert held is not None and wrapped is not None
        assert glow_for_intensity(held[1]) < 0.25
        # And the thing it is *not*: phase 1.0 samples the first keyframe.
        assert wrapped == sample_cycle(CYCLE_KEYFRAMES, 0.0)

    def test_the_hold_point_falls_inside_the_dawn_phase(self) -> None:
        """Otherwise the run stops with the HUD still announcing night."""
        assert phase_at(DAWN_HOLD_PHASE).name == "AMANHECER"

    def test_the_hold_point_is_reached_before_the_wrap(self) -> None:
        """A phase step is `dt / duration`; the margin has to be larger
        than one step or a slow frame could tick straight past it."""
        step = (1.0 / 30.0) / RUN_SECONDS

        assert step < 1.0 - DAWN_HOLD_PHASE


class TestTheDifficultyCurve:
    """The phase table and `Murundu.feed_interval` are separate numbers
    that together decide the run's shape. Nothing but this stops them
    drifting into a curve that peaks in the wrong place."""

    def simulate_idle_run(self) -> list[tuple[float, str, int]]:
        """Run the whole night with nobody killing anything.

        Returns:
            `(seconds, phase name, swarm size)` sampled each second.
        """
        from games.tamandua_murundus.components import Murundu
        from games.tamandua_murundus.swarm import SWARM_CAP, Swarm
        from games.tamandua_murundus.systems import MurunduSystem
        from pyguara.common.components import Transform
        from pyguara.common.random import RandomStream
        from pyguara.common.types import Rect, Vector2
        from pyguara.events.dispatcher import EventDispatcher

        arena = Rect(40, 96, 880, 568)
        entity_manager = EntityManager()
        swarm = Swarm(
            entity_manager,
            arena,
            RandomStream(seed=3),
            cap=SWARM_CAP,
            decorative=0,
        )
        for index in range(5):
            mound = entity_manager.create_entity()
            mound.add_component(Transform(position=Vector2(150 + index * 160, 200)))
            mound.add_component(Murundu())

        ambient = entity_manager.create_entity("ambient")
        ambient.add_component(AmbientLight())
        cycle = AmbientCycle(keyframes=CYCLE_KEYFRAMES, duration=RUN_SECONDS)
        ambient.add_component(cycle)
        cycle_system = AmbientCycleSystem(entity_manager)
        mounds = MurunduSystem(entity_manager, EventDispatcher(), swarm)

        samples: list[tuple[float, str, int]] = []
        dt, elapsed, next_sample = 1.0 / 60.0, 0.0, 1.0
        while elapsed < RUN_SECONDS:
            cycle_system.update(dt)
            phase = phase_at(cycle.phase)
            mounds.release_per_feed = phase.release_per_feed
            mounds.update(dt)
            elapsed += dt
            if elapsed >= next_sample:
                samples.append((elapsed, phase.name, swarm.active_count))
                next_sample += 1.0
        return samples

    def test_an_idle_run_reaches_the_ceiling(self) -> None:
        """A density climax that never arrives is not a climax."""
        from games.tamandua_murundus.swarm import SWARM_CAP

        samples = self.simulate_idle_run()

        assert samples[-1][2] == SWARM_CAP

    def test_the_ceiling_is_not_reached_before_the_peak_phase(self) -> None:
        """An earlier pairing filled the swarm by the halfway mark, which
        left the last two phases adding no pressure at all -- the
        difficulty curve went flat exactly where it should peak."""
        from games.tamandua_murundus.swarm import SWARM_CAP

        samples = self.simulate_idle_run()
        first_full = next(
            (sample for sample in samples if sample[2] >= SWARM_CAP), None
        )

        assert first_full is not None
        assert first_full[1] == "REVOADA"

    def test_the_swarm_grows_through_every_phase_before_dawn(self) -> None:
        samples = self.simulate_idle_run()
        by_phase: dict[str, list[int]] = {}
        for _, name, count in samples:
            by_phase.setdefault(name, []).append(count)

        for name in ("ANOITECER", "NOITE", "NOITE FECHADA"):
            counts = by_phase[name]
            assert counts[-1] > counts[0], name
