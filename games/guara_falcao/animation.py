"""The guará, animated from a sprite sheet by the engine.

Every other demo in this repository animates by drawing primitives on a
sine wave -- `art.draw_guara` swung its legs off `math.sin(phase * 12)`.
That is the house style and it works, but it meant `Animator` and
`AnimationStateMachine` (`pyguara.graphics.components.animation`) had no
reference usage anywhere, which is what #201 flagged. This is that usage,
and the demo gets real art for it.

The frames come from `tools/slice_spritesheet.py`, which cuts them out of
the project's contact sheet once and writes keyed PNGs. Nothing here
knows the sheet exists; it loads files.

**The demo already had the hard half.** `systems.AnimationFSMSystem`
computes a `PlayerAnimState` every tick from the platformer controller --
idle, run, jump, fall, land -- and has done since long before there was
anything to play. All that was missing was a clip per state, so `drive()`
is three lines: look up the clip, and ask the machine for it.

Two clips are deliberately not looped. `land` is a squat that resolves
back to standing, and `hit` is a recoil -- both end, rather than repeat,
and each carries an `ANIMATION_END` transition back to `idle` so the
machine leaves them on its own. Everything else loops.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from games.guara_falcao.components import PlayerAnimState
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.graphics.components.animation import (
    AnimationClip,
    AnimationState,
    AnimationStateMachine,
    AnimationTransition,
    Animator,
    TransitionCondition,
    add_clip,
    add_state,
    advance_animator,
    play_clip,
    set_default_state,
    transition_to,
)
from pyguara.graphics.components.sprite import Sprite
from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import Texture

TEXTURE_DIR = "games/guara_falcao/assets/textures"

IDLE = "idle"
RUN = "run"
JUMP = "jump"
FALL = "fall"
LAND = "land"
HIT = "hit"

FRAME_HEIGHT = 176
"""Height of every sliced guará frame, in source pixels. The slicer puts
all of them on one canvas, so a state change never resizes the
character. Keep in step with what `tools/slice_spritesheet.py` prints."""

DRAW_HEIGHT = 78.0
"""How tall the guará is drawn, in world pixels. Bigger than the 40-pixel
collider, as the primitive version was: a character that exactly fills
its collision box reads as a crate, and the overhang is where the ears,
the mane and the tail live."""

DRAW_SCALE = DRAW_HEIGHT / FRAME_HEIGHT
"""What `IRenderer.draw_texture` is given. One number for every clip,
because every frame shares a canvas."""

FALCAO = "falcao_fly"

FALCAO_FRAME_HEIGHT = 83
FALCAO_DRAW_HEIGHT = 30.0
FALCAO_DRAW_SCALE = FALCAO_DRAW_HEIGHT / FALCAO_FRAME_HEIGHT

FALCAO_OFFSET = Vector2(-26.0, -58.0)
"""Where the falcão flies relative to the guará's transform, facing
right. Mirrored with the guará, so the companion stays behind it."""

FALCAO_BOB = 4.0
"""Pixels the falcão rises and falls as it flies, so it is not pinned to
the guará like a decal."""

FALCAO_BOB_RATE = 6.0
"""Radians a second of that bob."""

BLINK_PERIOD = 0.1
"""Seconds per on/off step of the invincibility blink. `draw_texture`
carries no tint, so a hurt guará flickers rather than flashing white --
which is what a platformer does anyway."""


@dataclass(frozen=True)
class _ClipSpec:
    """How to build one clip.

    Attributes:
        frames: How many `<name>_<index>.png` files it has.
        frame_rate: Frames a second.
        loop: Whether it repeats, or ends and hands over.
    """

    frames: int
    frame_rate: float
    loop: bool = True


CLIPS: dict[str, _ClipSpec] = {
    # Two frames, slowly: the guará breathing with the falcão on its back.
    IDLE: _ClipSpec(frames=2, frame_rate=3.0),
    RUN: _ClipSpec(frames=4, frame_rate=12.0),
    # The leap, played once and held -- the last frame is the airborne
    # pose, and holding it is what "still going up" looks like.
    JUMP: _ClipSpec(frames=3, frame_rate=10.0, loop=False),
    FALL: _ClipSpec(frames=2, frame_rate=8.0),
    LAND: _ClipSpec(frames=1, frame_rate=6.0, loop=False),
    HIT: _ClipSpec(frames=3, frame_rate=12.0, loop=False),
    FALCAO: _ClipSpec(frames=4, frame_rate=10.0),
}

STATE_CLIPS: dict[PlayerAnimState, str] = {
    PlayerAnimState.IDLE: IDLE,
    PlayerAnimState.RUN: RUN,
    PlayerAnimState.JUMP: JUMP,
    PlayerAnimState.FALL: FALL,
    PlayerAnimState.LAND: LAND,
    # There is no wall-slide art, and the controller ships with
    # `wall_slide_enabled=False`. Falling is the honest stand-in.
    PlayerAnimState.WALL_SLIDE: FALL,
}

_ENDS_IN_IDLE = (LAND, HIT)
"""Clips that resolve on their own rather than repeating. The transition
back to `idle` is what lets `drive()` take the sprite over again without
having to time the clip itself."""


def load_clips(resources: ResourceManager) -> dict[str, AnimationClip]:
    """Load every clip's frames off disk.

    Args:
        resources: The engine's resource manager, which caches textures
            so a second scene entering does not re-read the files.

    Returns:
        The clips, by name.
    """
    clips = {}
    for name, spec in CLIPS.items():
        stem = name if name.startswith("falcao") else f"guara_{name}"
        frames = [
            resources.load(f"{TEXTURE_DIR}/{stem}_{index}.png", Texture)  # type: ignore[type-abstract]
            for index in range(spec.frames)
        ]
        clips[name] = AnimationClip(
            name=name,
            frames=frames,
            frame_rate=spec.frame_rate,
            loop=spec.loop,
        )
    return clips


def attach(entity: Entity, clips: dict[str, AnimationClip]) -> AnimationStateMachine:
    """Give `entity` the sprite, animator and machine that drive it.

    Args:
        entity: The player.
        clips: What `load_clips` returned.

    Returns:
        The machine, already standing in `IDLE`.
    """
    sprite = Sprite(texture=clips[IDLE].frames[0])
    animator = Animator(sprite)
    machine = AnimationStateMachine(sprite, animator)

    for name, clip in clips.items():
        if name == FALCAO:
            continue  # the companion's own clip, not a state of the guará
        transitions = (
            [
                AnimationTransition(
                    from_state=name,
                    to_state=IDLE,
                    condition=TransitionCondition.ANIMATION_END,
                )
            ]
            if name in _ENDS_IN_IDLE
            else []
        )
        add_state(
            machine, AnimationState(name=name, clip=clip, transitions=transitions)
        )

    entity.add_component(sprite)
    entity.add_component(animator)
    entity.add_component(machine)
    set_default_state(machine, IDLE)
    return machine


def attach_falcao(entity: Entity, clips: dict[str, AnimationClip]) -> None:
    """Give `entity` a plain looping animator for the falcão's flight.

    A bare `Animator` with no state machine over it, which is the other
    half of what `AnimationSystem` drives -- the companion has one clip
    and nothing to decide. Where the guará shows the state-machine path,
    this shows the simple one.

    Args:
        entity: The falcão.
        clips: What `load_clips` returned.
    """
    sprite = Sprite(texture=clips[FALCAO].frames[0])
    animator = Animator(sprite)
    add_clip(animator, clips[FALCAO])
    entity.add_component(sprite)
    entity.add_component(animator)
    play_clip(animator, FALCAO)


def falcao_visible(state: PlayerAnimState) -> bool:
    """Whether the falcão is flying rather than riding.

    The guará's idle frames have the falcão perched on its back, so
    drawing the flying one over them would be two birds. It takes off
    when the guará moves, which is the companion's whole behaviour and
    comes free from the art.

    Args:
        state: What the platformer controller says the player is doing.

    Returns:
        Whether to draw the flying falcão this frame.
    """
    return state is not PlayerAnimState.IDLE


def falcao_offset(facing_right: bool, elapsed: float) -> Vector2:
    """Where to draw the falcão, relative to the guará's own centre.

    Args:
        facing_right: Which way the guará faces; the companion stays
            behind it.
        elapsed: Seconds, for the bob.

    Returns:
        The offset in world pixels.
    """
    return Vector2(
        FALCAO_OFFSET.x * (1.0 if facing_right else -1.0),
        FALCAO_OFFSET.y + math.sin(elapsed * FALCAO_BOB_RATE) * FALCAO_BOB,
    )


class Filmstrip:
    """One clip, playing, outside the ECS.

    The menu draws a guará walking across its backdrop and has no
    entities to hang components on. This is the same `Animator` the
    player uses, driven by hand with `advance_animator` -- the plainest
    use of the API there is, and what keeps the menu and the game looking
    like the same game.

    Attributes:
        sprite: What the animator writes into; `texture` is the frame to
            draw this instant.
    """

    def __init__(self, clip: AnimationClip) -> None:
        """Start `clip` playing.

        Args:
            clip: The clip to loop.
        """
        self.sprite = Sprite(texture=clip.frames[0])
        self._animator = Animator(self.sprite)
        add_clip(self._animator, clip)
        play_clip(self._animator, clip.name)

    def advance(self, dt: float) -> None:
        """Move the playhead on.

        Args:
            dt: Seconds since the last call.
        """
        advance_animator(self._animator, dt)


def draw_offset(collider_height: float) -> float:
    """How far above a transform the sprite's centre must sit.

    The slicer stands every frame on the bottom of its canvas, and
    `draw_texture` centres on the position it is given -- so drawn at the
    transform, the guará's feet land half a canvas below it and it sinks
    into the platform. This is the difference between the collider's
    bottom edge and the canvas's.

    Args:
        collider_height: The character collider's full height.

    Returns:
        A y offset, negative: the sprite's centre sits above the
        transform.
    """
    return collider_height / 2.0 - DRAW_HEIGHT / 2.0


def drive(machine: AnimationStateMachine, state: PlayerAnimState) -> None:
    """Put `machine` into the clip that matches how the player is moving.

    Called every frame with whatever `systems.AnimationFSMSystem` decided.
    `transition_to` ignores a request for the clip already playing, so
    asking every frame is free and does not restart the animation.

    A recoil in progress is left alone: `recoil()` is the more important
    thing to show and it is over in a quarter of a second, after which
    the clip's own `ANIMATION_END` transition hands the sprite back and
    the next call here picks the movement state up again.

    Args:
        machine: The player's machine.
        state: What the platformer controller says the player is doing.
    """
    if machine.current_state_name == HIT:
        return
    transition_to(machine, STATE_CLIPS.get(state, IDLE))


def recoil(machine: AnimationStateMachine) -> None:
    """Play the hit clip, from the top.

    Driven by `PlayerDamagedEvent` rather than by `Health.invincible_time`,
    because being hit is an event and being invincible is a state: the
    recoil is a quarter of a second and the invincibility is seconds, so
    a state-driven version would loop the recoil until it wore off.

    Args:
        machine: The player's machine.
    """
    transition_to(machine, HIT, force=True)


def blink_visible(invincible_time: float) -> bool:
    """Whether to draw the guará this frame while it is invincible.

    `IRenderer.draw_texture` has no tint, so the primitive version's
    white flash cannot survive the move to sprites. Flickering the
    sprite is what the genre does instead, and it reads the same: you
    have been hit, and you cannot be hit again yet.

    Args:
        invincible_time: `Health.invincible_time`, seconds remaining.

    Returns:
        Whether the sprite is drawn this frame.
    """
    if invincible_time <= 0:
        return True
    return int(invincible_time / BLINK_PERIOD) % 2 == 0
