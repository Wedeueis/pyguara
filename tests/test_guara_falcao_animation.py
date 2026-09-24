"""The guará is a sprite now, played by the engine's own animation components.

Every demo in this repository used to animate by drawing primitives on a
sine wave, which left `Animator` and `AnimationStateMachine` with no
reference usage anywhere (#201). These pin the wiring: a clip per
movement state, a recoil that a movement state cannot interrupt and that
gets out of the way on its own, and a companion on the plain animator
path with no state machine over it.

No textures are loaded here. `AnimationClip` needs frames but never looks
at them, so the clips are built from stand-ins -- what is under test is
the state logic, not the art.
"""

from __future__ import annotations

from typing import Any

import pytest

from games.guara_falcao import animation
from games.guara_falcao.components import PlayerAnimState
from pyguara.graphics.components.animation import (
    AnimationClip,
    AnimationStateMachine,
    Animator,
    advance_state_machine,
)
from pyguara.graphics.components.sprite import Sprite


class _Frame:
    """The least a `Texture` has to be for a clip to hold it."""

    def __init__(self, name: str) -> None:
        self.path = name
        self.width = 1
        self.height = 1


def _clips() -> dict[str, AnimationClip]:
    """A clip per name in `animation.CLIPS`, with stand-in frames."""
    return {
        name: AnimationClip(
            name=name,
            frames=[_Frame(f"{name}_{i}") for i in range(spec.frames)],
            frame_rate=spec.frame_rate,
            loop=spec.loop,
        )
        for name, spec in animation.CLIPS.items()
    }


class _Entity:
    """Just enough entity for `attach` to hang components on."""

    def __init__(self) -> None:
        self.components: dict[type, Any] = {}

    def add_component(self, component: Any) -> None:
        self.components[type(component)] = component


@pytest.fixture
def machine() -> AnimationStateMachine:
    return animation.attach(_Entity(), _clips())


class TestTheClipTable:
    """What the slicer wrote and what the game plays must agree."""

    def test_every_movement_state_has_a_clip(self) -> None:
        for state in PlayerAnimState:
            assert state in animation.STATE_CLIPS, state

    def test_every_mapped_clip_exists(self) -> None:
        for clip in animation.STATE_CLIPS.values():
            assert clip in animation.CLIPS, clip

    def test_the_recoil_and_the_landing_do_not_loop(self) -> None:
        """Both resolve and hand the sprite back; a looping recoil would
        never let go of it."""
        assert not animation.CLIPS[animation.HIT].loop
        assert not animation.CLIPS[animation.LAND].loop

    def test_running_and_idling_do_loop(self) -> None:
        assert animation.CLIPS[animation.RUN].loop
        assert animation.CLIPS[animation.IDLE].loop

    def test_the_wall_slide_borrows_the_fall(self) -> None:
        """There is no wall-slide art and the controller ships with wall
        sliding off; falling is the honest stand-in."""
        assert animation.STATE_CLIPS[PlayerAnimState.WALL_SLIDE] == animation.FALL


class TestAttaching:
    """What the player entity ends up carrying."""

    def test_it_adds_the_three_components(self) -> None:
        entity = _Entity()

        animation.attach(entity, _clips())

        assert Sprite in entity.components
        assert Animator in entity.components
        assert AnimationStateMachine in entity.components

    def test_it_starts_idle(self, machine: AnimationStateMachine) -> None:
        assert machine.current_state_name == animation.IDLE

    def test_the_companions_clip_is_not_a_state_of_the_guara(
        self, machine: AnimationStateMachine
    ) -> None:
        """The falcão has its own animator; a state for it here would be
        a pose the guará could be asked to strike."""
        assert animation.FALCAO not in machine._states


class TestDriving:
    """A clip per movement state, asked for every frame."""

    @pytest.mark.parametrize("state", list(PlayerAnimState))
    def test_each_state_plays_its_own_clip(
        self, machine: AnimationStateMachine, state: PlayerAnimState
    ) -> None:
        animation.drive(machine, state)

        assert machine.current_state_name == animation.STATE_CLIPS[state]

    def test_asking_twice_does_not_restart_the_clip(
        self, machine: AnimationStateMachine
    ) -> None:
        """`drive` is called every frame, so a re-request must be free."""
        animation.drive(machine, PlayerAnimState.RUN)
        advance_state_machine(machine, 0.5)
        mid = machine._animator._current_frame_index

        animation.drive(machine, PlayerAnimState.RUN)

        assert machine._animator._current_frame_index == mid


class TestTheRecoil:
    """Being hit is an event; being invincible is a state."""

    def test_it_takes_over_from_the_movement_state(
        self, machine: AnimationStateMachine
    ) -> None:
        animation.drive(machine, PlayerAnimState.RUN)

        animation.recoil(machine)

        assert machine.current_state_name == animation.HIT

    def test_a_movement_state_cannot_interrupt_it(
        self, machine: AnimationStateMachine
    ) -> None:
        animation.recoil(machine)

        animation.drive(machine, PlayerAnimState.RUN)

        assert machine.current_state_name == animation.HIT

    def test_it_gets_out_of_the_way_on_its_own(
        self, machine: AnimationStateMachine
    ) -> None:
        """The clip's own ANIMATION_END transition, so nothing has to time
        it by hand."""
        animation.recoil(machine)

        advance_state_machine(machine, 1.0)

        assert machine.current_state_name == animation.IDLE

    def test_and_then_movement_takes_over_again(
        self, machine: AnimationStateMachine
    ) -> None:
        animation.recoil(machine)
        advance_state_machine(machine, 1.0)

        animation.drive(machine, PlayerAnimState.RUN)

        assert machine.current_state_name == animation.RUN

    def test_a_second_hit_restarts_it(self, machine: AnimationStateMachine) -> None:
        animation.recoil(machine)
        advance_state_machine(machine, 0.1)

        animation.recoil(machine)

        assert machine._animator._current_frame_index == 0


class TestTheBlink:
    """The invincibility flash, which `draw_texture` cannot tint."""

    def test_an_unhurt_guara_is_always_drawn(self) -> None:
        assert animation.blink_visible(0.0)

    def test_a_hurt_one_flickers(self) -> None:
        seen = {
            animation.blink_visible(animation.BLINK_PERIOD * step)
            for step in range(1, 7)
        }

        assert seen == {True, False}


class TestTheCompanion:
    """The plain-animator path: one clip and nothing to decide."""

    def test_it_gets_a_sprite_and_an_animator(self) -> None:
        entity = _Entity()

        animation.attach_falcao(entity, _clips())

        assert Sprite in entity.components
        assert Animator in entity.components

    def test_but_no_state_machine(self) -> None:
        entity = _Entity()

        animation.attach_falcao(entity, _clips())

        assert AnimationStateMachine not in entity.components

    def test_its_clip_is_playing(self) -> None:
        entity = _Entity()

        animation.attach_falcao(entity, _clips())

        assert entity.components[Animator].current_clip_name == animation.FALCAO

    def test_it_rides_while_the_guara_stands(self) -> None:
        """The idle frames already have it perched on the guará's back, so
        drawing the flying one over them would be two birds."""
        assert not animation.falcao_visible(PlayerAnimState.IDLE)

    def test_and_flies_once_it_moves(self) -> None:
        assert animation.falcao_visible(PlayerAnimState.RUN)
        assert animation.falcao_visible(PlayerAnimState.JUMP)

    def test_it_stays_behind_whichever_way_the_guara_faces(self) -> None:
        right = animation.falcao_offset(True, 0.0)
        left = animation.falcao_offset(False, 0.0)

        assert right.x < 0 < left.x

    def test_it_bobs(self) -> None:
        heights = {round(animation.falcao_offset(True, t / 10).y, 3) for t in range(20)}

        assert len(heights) > 1


class TestStandingOnTheGround:
    """The slicer stands every frame on its canvas; the draw must too."""

    def test_the_sprite_is_lifted_above_the_transform(self) -> None:
        """Drawn at the transform, half the canvas hangs below the
        collider and the guará sinks into the platform."""
        assert animation.draw_offset(40.0) < 0

    def test_a_taller_collider_needs_less_lifting(self) -> None:
        assert animation.draw_offset(40.0) < animation.draw_offset(60.0)

    def test_the_lift_puts_the_canvas_bottom_on_the_colliders(self) -> None:
        collider = 40.0
        centre = animation.draw_offset(collider)

        canvas_bottom = centre + animation.DRAW_HEIGHT / 2
        assert canvas_bottom == pytest.approx(collider / 2)


class TestTheMenuFilmstrip:
    """The same `Animator`, outside the ECS."""

    def test_it_starts_on_the_first_frame(self) -> None:
        clips = _clips()

        strip = animation.Filmstrip(clips[animation.RUN])

        assert strip.sprite.texture is clips[animation.RUN].frames[0]

    def test_advancing_moves_the_playhead(self) -> None:
        clips = _clips()
        strip = animation.Filmstrip(clips[animation.RUN])

        strip.advance(1.0 / animation.CLIPS[animation.RUN].frame_rate)

        assert strip.sprite.texture is clips[animation.RUN].frames[1]

    def test_it_loops(self) -> None:
        clips = _clips()
        strip = animation.Filmstrip(clips[animation.RUN])

        strip.advance(10.0)

        assert strip.sprite.texture in clips[animation.RUN].frames


class TestTheFramesAreOnDisk:
    """A clip table that names a file the slicer never wrote is a crash on
    the first frame of the demo, not a test failure."""

    def test_every_clip_has_all_of_its_frames(self) -> None:
        import pathlib

        directory = pathlib.Path(animation.TEXTURE_DIR)
        for name, spec in animation.CLIPS.items():
            stem = name if name.startswith("falcao") else f"guara_{name}"
            for index in range(spec.frames):
                path = directory / f"{stem}_{index}.png"
                assert path.exists(), path

    def test_every_frame_of_a_clip_is_the_same_size(self) -> None:
        """A clip whose frames differ in size makes the character jump
        about as it plays."""
        import pathlib

        from PIL import Image

        directory = pathlib.Path(animation.TEXTURE_DIR)
        for name, spec in animation.CLIPS.items():
            stem = name if name.startswith("falcao") else f"guara_{name}"
            sizes = {
                Image.open(directory / f"{stem}_{index}.png").size
                for index in range(spec.frames)
            }
            assert len(sizes) == 1, (name, sizes)

    def test_the_guara_frame_height_matches_what_the_draw_scale_assumes(
        self,
    ) -> None:
        import pathlib

        from PIL import Image

        path = pathlib.Path(animation.TEXTURE_DIR) / "guara_idle_0.png"
        assert Image.open(path).size[1] == animation.FRAME_HEIGHT

    def test_the_falcao_frame_height_does_too(self) -> None:
        import pathlib

        from PIL import Image

        path = pathlib.Path(animation.TEXTURE_DIR) / "falcao_fly_0.png"
        assert Image.open(path).size[1] == animation.FALCAO_FRAME_HEIGHT
