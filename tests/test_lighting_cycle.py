"""Tests for the ambient day/night cycle.

Two halves, matching the module's own split: `sample_cycle` is a pure
function over keyframes and needs no ECS at all, and `AmbientCycleSystem`
is about who writes `AmbientLight` and when.

The wrap is the part worth pinning down. A cycle is a *ring* -- the last
keyframe interpolates back round to the first through 1.0/0.0 -- so the
segment covering "late night into dawn" is the one with no keyframe at
its left edge in a naive forward scan, and is exactly the one a cycle
spends a quarter of its time in.
"""

import pytest

from pyguara.common.types import Color
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.lighting.components import AmbientLight
from pyguara.graphics.lighting.cycle import (
    AmbientCycle,
    AmbientCycleSystem,
    LightKeyframe,
    sample_cycle,
)

BLACK = Color(0, 0, 0)
WHITE = Color(255, 255, 255)

# Midnight black, noon white. Deliberately only two keyframes and neither
# at phase 1.0, so every test of the back half is a test of the wrap.
DAY = [
    LightKeyframe(0.0, BLACK, 0.0),
    LightKeyframe(0.5, WHITE, 1.0),
]


class TestSampleCycle:
    def test_a_keyframes_phase_samples_exactly_it(self) -> None:
        assert sample_cycle(DAY, 0.0) == (BLACK, 0.0)
        assert sample_cycle(DAY, 0.5) == (WHITE, 1.0)

    def test_midway_through_a_segment_is_the_midpoint(self) -> None:
        color, intensity = sample_cycle(DAY, 0.25)

        assert color == Color(128, 128, 128)
        assert intensity == pytest.approx(0.5)

    def test_the_back_half_wraps_from_the_last_keyframe_to_the_first(self) -> None:
        """0.75 sits between noon and the *next* midnight, which is the
        first keyframe reached the long way round -- there is no keyframe
        at 1.0 and there should not need to be."""
        color, intensity = sample_cycle(DAY, 0.75)

        assert color == Color(128, 128, 128)
        assert intensity == pytest.approx(0.5)

    def test_the_ramp_runs_the_right_way_round_the_wrap(self) -> None:
        """Just past noon is still bright; just before midnight is nearly
        dark. Reversing the wrap segment would swap these."""
        _, just_after_noon = sample_cycle(DAY, 0.55)  # type: ignore[misc]
        _, just_before_midnight = sample_cycle(DAY, 0.95)  # type: ignore[misc]

        assert just_after_noon > 0.8
        assert just_before_midnight < 0.2

    def test_a_phase_past_one_wraps_rather_than_clamping(self) -> None:
        """A caller advancing a phase never has to normalise it first."""
        assert sample_cycle(DAY, 1.25) == sample_cycle(DAY, 0.25)

    def test_a_negative_phase_wraps_too(self) -> None:
        assert sample_cycle(DAY, -0.25) == sample_cycle(DAY, 0.75)

    def test_keyframes_need_not_be_given_in_order(self) -> None:
        shuffled = [DAY[1], DAY[0]]

        assert sample_cycle(shuffled, 0.25) == sample_cycle(DAY, 0.25)

    def test_one_keyframe_is_a_constant(self) -> None:
        single = [LightKeyframe(0.3, WHITE, 0.7)]

        assert sample_cycle(single, 0.0) == (WHITE, 0.7)
        assert sample_cycle(single, 0.9) == (WHITE, 0.7)

    def test_no_keyframes_samples_nothing(self) -> None:
        """Distinct from black: the system leaves the light alone rather
        than driving it to zero."""
        assert sample_cycle([], 0.4) is None

    def test_keyframes_stacked_on_one_phase_do_not_divide_by_zero(self) -> None:
        stacked = [LightKeyframe(0.2, BLACK, 0.0), LightKeyframe(0.2, WHITE, 1.0)]

        assert sample_cycle(stacked, 0.7) is not None


def make_scene(
    cycle: AmbientCycle | None = None,
    ambient: AmbientLight | None = None,
) -> tuple[AmbientCycleSystem, AmbientLight | None, AmbientCycle | None]:
    """One entity carrying whichever of the two components was asked for."""
    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    if cycle is not None:
        entity.add_component(cycle)
    if ambient is not None:
        entity.add_component(ambient)
    return AmbientCycleSystem(entity_manager), ambient, cycle


class TestAmbientCycleSystem:
    def test_the_phase_advances_by_dt_over_duration(self) -> None:
        cycle = AmbientCycle(keyframes=DAY, duration=10.0, phase=0.0)
        system, _, _ = make_scene(cycle, AmbientLight())

        system.update(2.5)

        assert cycle.phase == pytest.approx(0.25)

    def test_the_phase_wraps_at_the_end_of_a_loop(self) -> None:
        cycle = AmbientCycle(keyframes=DAY, duration=10.0, phase=0.9)
        system, _, _ = make_scene(cycle, AmbientLight())

        system.update(2.0)

        assert cycle.phase == pytest.approx(0.1)

    def test_the_sampled_value_is_written_to_the_ambient_light(self) -> None:
        cycle = AmbientCycle(keyframes=DAY, duration=10.0, phase=0.5)
        ambient = AmbientLight(color=Color(1, 2, 3), intensity=0.123)
        system, _, _ = make_scene(cycle, ambient)

        system.update(0.0)

        assert ambient.color == WHITE
        assert ambient.intensity == pytest.approx(1.0)

    def test_the_cycle_owns_the_light_and_overwrites_another_writer(self) -> None:
        """The ownership rule, made executable. Something else setting
        `intensity` between ticks does not survive the next tick -- which
        is why a transient flash is a `LightSource` or a `playing = False`,
        not a second writer."""
        cycle = AmbientCycle(keyframes=DAY, duration=10.0, phase=0.5)
        ambient = AmbientLight()
        system, _, _ = make_scene(cycle, ambient)

        ambient.intensity = 0.42
        system.update(0.0)

        assert ambient.intensity == pytest.approx(1.0)

    def test_a_paused_cycle_neither_advances_nor_writes(self) -> None:
        """The documented way to hand the light to another writer."""
        cycle = AmbientCycle(keyframes=DAY, duration=10.0, phase=0.5, playing=False)
        ambient = AmbientLight(color=Color(1, 2, 3), intensity=0.123)
        system, _, _ = make_scene(cycle, ambient)

        system.update(5.0)

        assert cycle.phase == pytest.approx(0.5)
        assert ambient.color == Color(1, 2, 3)
        assert ambient.intensity == pytest.approx(0.123)

    def test_an_entity_without_an_ambient_light_is_skipped(self) -> None:
        """The two components are required together; a cycle alone drives
        nothing rather than raising mid-frame."""
        cycle = AmbientCycle(keyframes=DAY, duration=10.0)
        system, _, _ = make_scene(cycle, None)

        system.update(1.0)

        assert cycle.phase == pytest.approx(0.0)

    def test_a_cycle_with_no_keyframes_leaves_the_light_alone(self) -> None:
        cycle = AmbientCycle(keyframes=[], duration=10.0)
        ambient = AmbientLight(color=Color(1, 2, 3), intensity=0.123)
        system, _, _ = make_scene(cycle, ambient)

        system.update(1.0)

        assert ambient.color == Color(1, 2, 3)
        assert ambient.intensity == pytest.approx(0.123)

    def test_a_zero_duration_freezes_the_phase_but_still_drives_the_light(
        self,
    ) -> None:
        """`duration = 0` means "hold here", not "silently stop driving the
        light" -- and must not divide by zero."""
        cycle = AmbientCycle(keyframes=DAY, duration=0.0, phase=0.5)
        ambient = AmbientLight()
        system, _, _ = make_scene(cycle, ambient)

        system.update(1.0)

        assert cycle.phase == pytest.approx(0.5)
        assert ambient.intensity == pytest.approx(1.0)

    def test_a_scene_with_no_cycle_is_untouched(self) -> None:
        """The whole point of opting in per entity: an existing scene that
        attaches no cycle behaves exactly as it did before."""
        ambient = AmbientLight(color=Color(1, 2, 3), intensity=0.123)
        system, _, _ = make_scene(None, ambient)

        system.update(1.0)

        assert ambient.color == Color(1, 2, 3)
        assert ambient.intensity == pytest.approx(0.123)


class TestComponentPurity:
    def test_the_cycle_component_is_strict(self) -> None:
        """`AmbientCycle` is a `StrictComponent`, so a logic method added
        to it later fails at class-definition time rather than review."""
        from pyguara.ecs.component import StrictComponent

        assert issubclass(AmbientCycle, StrictComponent)
