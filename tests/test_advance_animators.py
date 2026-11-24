"""`advance_animators` moves every animator exactly as `advance_animator` would.

The batch path does the common case, a tick that changes no frame, inline.
It must agree bit for bit, in every playback mode, at any speed, and with
clips that time each frame, so these drive two identical sets of animators
side by side and compare every cursor after every tick.
"""

from __future__ import annotations

import random

import pytest

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.animation_system import AnimationSystem
from pyguara.graphics.components.animation import (
    AnimationClip,
    AnimationState,
    AnimationStateMachine,
    Animator,
    PlaybackMode,
    add_clip,
    add_state,
    advance_animator,
    advance_animators,
    play_clip,
    set_default_state,
)
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.events import AnimationFrameEvent
from pyguara.resources.types import Texture


class _Texture(Texture):
    @property
    def width(self) -> int:
        return 8

    @property
    def height(self) -> int:
        return 8

    @property
    def native_handle(self) -> object:
        return None


FRAMES = [_Texture(f"f{index}") for index in range(4)]


def _clip(rng: random.Random, index: int) -> AnimationClip:
    mode = list(PlaybackMode)[index % len(PlaybackMode)]
    timed = index % 3 == 0
    # Every fifth clip runs at a rate whose frame a tick length divides
    # exactly, so the cursor lands on the boundary itself.
    rate = (4.0, 8.0, 2.0)[index % 3] if index % 5 == 0 else rng.uniform(4.0, 24.0)
    return AnimationClip(
        name="clip",
        frames=FRAMES[: 1 + index % 4],
        frame_rate=rate,
        mode=mode,
        loop_count=2,
        frame_events={1: ["step"], 0: ["start"]},
        frame_durations=(
            tuple(rng.uniform(0.02, 0.2) for _ in FRAMES[: 1 + index % 4])
            if timed
            else None
        ),
    )


def _animators(seed: int) -> list[Animator]:
    rng = random.Random(seed)
    animators = []
    for index in range(60):
        animator = Animator(Sprite(texture=FRAMES[0]))
        add_clip(animator, _clip(rng, index))
        play_clip(animator, "clip")
        animator.playback_speed = rng.choice((1.0, 0.5, 2.0, 0.0, 1.3))
        animators.append(animator)
    return animators


def _cursor(animator: Animator) -> tuple[object, ...]:
    return (
        animator._current_time,
        animator._current_frame_index,
        animator._playing,
        animator._reverse,
        animator._loops_done,
        animator._sprite.texture,
    )


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_batch_agrees_with_one_at_a_time_exactly(seed: int) -> None:
    one_by_one, batched = _animators(seed), _animators(seed)
    rng = random.Random(seed + 100)

    for tick in range(400):
        dt = rng.choice((1 / 60, 1 / 30, 0.0, 0.25))
        if tick == 200:  # a hit-stop and a haste, partway through
            for group in (one_by_one, batched):
                group[0].playback_speed = 0.0
                group[1].playback_speed = 3.0
        expected = [(a, advance_animator(a, dt)) for a in one_by_one]
        fired = advance_animators(batched, dt)

        assert [_cursor(a) for a in batched] == [_cursor(a) for a in one_by_one]
        positions = {id(a): index for index, a in enumerate(batched)}
        assert [(positions[id(a)], names) for a, names in fired] == [
            (index, names) for index, (_, names) in enumerate(expected) if names
        ]


def test_the_system_names_the_entity_a_frame_event_came_from() -> None:
    manager, dispatcher = EntityManager(), EventDispatcher()
    seen: list[AnimationFrameEvent] = []
    dispatcher.subscribe(AnimationFrameEvent, seen.append)
    entity = manager.create_entity("walker")
    sprite = Sprite(texture=FRAMES[0])
    animator = Animator(sprite)
    add_clip(
        animator,
        AnimationClip(
            name="walk", frames=FRAMES[:2], frame_rate=10.0, frame_events={1: ["step"]}
        ),
    )
    play_clip(animator, "walk")
    entity.add_component(sprite)
    entity.add_component(animator)
    system = AnimationSystem(manager, dispatcher)

    for _ in range(7):
        system.update(1 / 60)

    assert [(e.entity_id, e.clip_name, e.name) for e in seen] == [
        ("walker", "walk", "step")
    ]


def test_an_animator_a_state_machine_drives_is_advanced_once() -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    sprite = Sprite(texture=FRAMES[0])
    animator = Animator(sprite)
    machine = AnimationStateMachine(sprite, animator)
    add_state(
        machine,
        AnimationState(
            name="run", clip=AnimationClip(name="run", frames=FRAMES, frame_rate=10.0)
        ),
    )
    set_default_state(machine, "run")
    entity.add_component(sprite)
    entity.add_component(animator)
    entity.add_component(machine)
    system = AnimationSystem(manager, EventDispatcher())

    for _ in range(6):  # 0.1 s: one frame at 10 fps, two if advanced twice
        system.update(1 / 60 + 1e-9)

    assert animator._current_frame_index == 1
