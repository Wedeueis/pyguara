"""Tests for animation state machine."""

import pytest

from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.animation_system import AnimationSystem
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
    advance_state_machine,
    play_clip,
    set_default_state,
    transition_to,
)
from pyguara.graphics.components.sprite import Sprite
from pyguara.resources.types import Texture


class MockTexture(Texture):
    """Mock texture for testing."""

    def __init__(self, name: str = "mock"):
        super().__init__(f"{name}.png")

    @property
    def width(self) -> int:
        return 64

    @property
    def height(self) -> int:
        return 64

    @property
    def native_handle(self):
        return None


# ===== AnimationClip Tests =====


def test_animation_clip_rejects_empty_frames():
    """A clip with no frames cannot be played -- reject it at construction."""
    with pytest.raises(ValueError, match="has no frames"):
        AnimationClip("broken", [], frame_rate=10.0)


@pytest.mark.parametrize("rate", [0.0, -10.0])
def test_animation_clip_rejects_nonpositive_frame_rate(rate):
    """frame_rate <= 0 is a ZeroDivisionError / reversed playback waiting to happen."""
    with pytest.raises(ValueError, match="frame_rate must be positive"):
        AnimationClip("broken", [MockTexture()], frame_rate=rate)


# ===== Animator Tests =====


def test_animator_properties():
    """Animator should expose useful properties."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)

    # Create test clips
    idle_clip = AnimationClip("idle", [MockTexture(f"idle_{i}") for i in range(4)])
    add_clip(animator, idle_clip)

    # Initially not playing
    assert animator.is_playing is False
    assert animator.current_clip_name is None
    assert animator.is_finished is False

    # Start playing
    play_clip(animator, "idle")
    assert animator.is_playing is True
    assert animator.current_clip_name == "idle"
    assert animator.is_finished is False


def test_animator_catches_up_multiple_frames_in_one_update():
    """A dt larger than one frame period should advance every frame it covers."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"run_{i}") for i in range(8)]
    add_clip(animator, AnimationClip("run", frames, frame_rate=10.0, loop=True))
    play_clip(animator, "run")

    # 10 FPS => 0.1s/frame. A 0.45s lag spike should land on frame 4, not 1.
    advance_animator(animator, 0.45)
    assert sprite.texture is frames[4]

    # A dt that wraps past the end of a looping clip lands correctly.
    advance_animator(animator, 0.6)  # +6 frames from 4 => 10 => wraps to 2
    assert sprite.texture is frames[2]


def test_animator_non_looping_clamps_on_a_large_dt():
    """A huge dt on a non-looping clip stops on the last frame, not past it."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"a_{i}") for i in range(3)]
    add_clip(animator, AnimationClip("attack", frames, frame_rate=10.0, loop=False))
    play_clip(animator, "attack")

    advance_animator(animator, 5.0)  # far past the 0.3s clip

    assert sprite.texture is frames[-1]
    assert animator.is_playing is False
    assert animator.is_finished is True


def test_animator_is_finished():
    """Animator should detect when non-looping animation finishes."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)

    # Non-looping clip with 3 frames at 10 FPS (0.3s duration)
    clip = AnimationClip(
        "attack",
        [MockTexture(f"attack_{i}") for i in range(3)],
        frame_rate=10.0,
        loop=False,
    )
    add_clip(animator, clip)

    play_clip(animator, "attack")
    assert animator.is_finished is False

    # Update through the animation (3 frames / 10 FPS = 0.3 seconds)
    advance_animator(animator, 0.1)  # Frame 1
    assert animator.is_finished is False

    advance_animator(animator, 0.1)  # Frame 2
    assert animator.is_finished is False

    advance_animator(animator, 0.1)  # Animation finishes
    assert animator.is_finished is True
    assert animator.is_playing is False


# ===== AnimationState Tests =====


def test_animation_state_creation():
    """AnimationState should store state data."""
    clip = AnimationClip("idle", [MockTexture()])

    state = AnimationState(
        name="idle_state",
        clip=clip,
    )

    assert state.name == "idle_state"
    assert state.clip == clip
    assert len(state.transitions) == 0
    assert state.on_enter is None
    assert state.on_exit is None
    assert state.on_complete is None


def test_animation_state_with_callbacks():
    """AnimationState should support callbacks."""
    clip = AnimationClip("idle", [MockTexture()])

    entered = []
    exited = []
    completed = []

    state = AnimationState(
        name="test",
        clip=clip,
        on_enter=lambda: entered.append(True),
        on_exit=lambda: exited.append(True),
        on_complete=lambda: completed.append(True),
    )

    # Callbacks should be stored
    assert state.on_enter is not None
    assert state.on_exit is not None
    assert state.on_complete is not None

    # Call callbacks
    state.on_enter()
    state.on_exit()
    state.on_complete()

    assert len(entered) == 1
    assert len(exited) == 1
    assert len(completed) == 1


# ===== AnimationStateMachine Tests =====


def test_state_machine_creation():
    """AnimationStateMachine should initialize correctly."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    assert fsm.current_state_name is None


def test_state_machine_add_state():
    """State machine should register states."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    clip = AnimationClip("idle", [MockTexture()])
    state = AnimationState("idle", clip)

    add_state(fsm, state)

    # State should be registered internally
    assert "idle" in fsm._states


def test_state_machine_set_default_state():
    """State machine should enter default state."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    clip = AnimationClip("idle", [MockTexture()])
    state = AnimationState("idle", clip)
    add_state(fsm, state)

    set_default_state(fsm, "idle")

    assert fsm.current_state_name == "idle"
    assert animator.is_playing is True
    assert animator.current_clip_name == "idle"


def test_state_machine_set_invalid_default_state():
    """State machine should raise error for invalid default state."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    with pytest.raises(ValueError, match="does not exist"):
        set_default_state(fsm, "nonexistent")


def test_state_machine_manual_transition():
    """State machine should support manual transitions."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    # Create two states
    idle_clip = AnimationClip("idle", [MockTexture("idle")])
    walk_clip = AnimationClip("walk", [MockTexture("walk")])

    idle_state = AnimationState("idle", idle_clip)
    walk_state = AnimationState("walk", walk_clip)

    add_state(fsm, idle_state)
    add_state(fsm, walk_state)

    set_default_state(fsm, "idle")
    assert fsm.current_state_name == "idle"

    # Manual transition
    result = transition_to(fsm, "walk")
    assert result is True
    assert fsm.current_state_name == "walk"
    assert animator.current_clip_name == "walk"


def test_state_machine_transition_callbacks():
    """State machine should call on_enter and on_exit callbacks."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    events = []

    idle_clip = AnimationClip("idle", [MockTexture()])
    walk_clip = AnimationClip("walk", [MockTexture()])

    idle_state = AnimationState(
        "idle",
        idle_clip,
        on_enter=lambda: events.append("idle_enter"),
        on_exit=lambda: events.append("idle_exit"),
    )
    walk_state = AnimationState(
        "walk",
        walk_clip,
        on_enter=lambda: events.append("walk_enter"),
        on_exit=lambda: events.append("walk_exit"),
    )

    add_state(fsm, idle_state)
    add_state(fsm, walk_state)

    set_default_state(fsm, "idle")
    assert events == ["idle_enter"]

    events.clear()

    transition_to(fsm, "walk")
    assert events == ["idle_exit", "walk_enter"]


def test_state_machine_automatic_transition():
    """State machine should transition automatically on ANIMATION_END."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    # Attack animation (non-looping, 2 frames at 10 FPS = 0.2s duration)
    attack_clip = AnimationClip(
        "attack",
        [MockTexture(f"attack_{i}") for i in range(2)],
        frame_rate=10.0,
        loop=False,
    )

    # Idle animation (looping)
    idle_clip = AnimationClip("idle", [MockTexture("idle")], loop=True)

    # Create transition from attack to idle when attack finishes
    attack_to_idle = AnimationTransition(
        from_state="attack",
        to_state="idle",
        condition=TransitionCondition.ANIMATION_END,
    )

    attack_state = AnimationState("attack", attack_clip, transitions=[attack_to_idle])
    idle_state = AnimationState("idle", idle_clip)

    add_state(fsm, attack_state)
    add_state(fsm, idle_state)

    set_default_state(fsm, "attack")
    assert fsm.current_state_name == "attack"

    # Update until animation finishes (2 frames at 10 FPS = 0.2s)
    advance_state_machine(fsm, 0.1)  # Frame 1
    assert fsm.current_state_name == "attack"

    # Animation finishes and transitions to idle
    advance_state_machine(fsm, 0.1)  # Frame 2, animation ends, transition triggers
    assert fsm.current_state_name == "idle"


def test_state_machine_on_complete_callback():
    """State machine should call on_complete when animation finishes."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    completed = []

    # Non-looping clip (2 frames at 10 FPS = 0.2s duration)
    clip = AnimationClip(
        "attack",
        [MockTexture(f"attack_{i}") for i in range(2)],
        frame_rate=10.0,
        loop=False,
    )

    state = AnimationState("attack", clip, on_complete=lambda: completed.append(True))
    add_state(fsm, state)
    set_default_state(fsm, "attack")

    # Update until animation finishes
    advance_state_machine(fsm, 0.1)  # Frame 1
    assert len(completed) == 0

    advance_state_machine(fsm, 0.1)  # Animation finishes, callback should fire
    assert len(completed) == 1


def test_state_machine_on_complete_fires_once_when_held_past_completion():
    """A terminal state must not re-fire on_complete every subsequent frame."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    completed = []
    clip = AnimationClip(
        "death",
        [MockTexture(f"death_{i}") for i in range(2)],
        frame_rate=10.0,
        loop=False,
    )
    # No ANIMATION_END transition: the FSM will sit on this finished clip.
    state = AnimationState("death", clip, on_complete=lambda: completed.append(True))
    add_state(fsm, state)
    set_default_state(fsm, "death")

    for _ in range(20):
        advance_state_machine(fsm, 0.1)

    assert completed == [True]  # exactly one, not one-per-frame


def test_state_machine_on_complete_refires_after_replaying_the_state():
    """Re-entering a terminal state arms its completion callback again."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    completed = []
    clip = AnimationClip(
        "hit", [MockTexture(f"hit_{i}") for i in range(2)], frame_rate=10.0, loop=False
    )
    add_state(fsm, AnimationState("hit", clip, on_complete=lambda: completed.append(1)))
    set_default_state(fsm, "hit")

    for _ in range(5):
        advance_state_machine(fsm, 0.1)
    assert len(completed) == 1

    transition_to(fsm, "hit", force=True)  # replay
    for _ in range(5):
        advance_state_machine(fsm, 0.1)
    assert len(completed) == 2


def test_state_machine_immediate_transition_fires_on_entry():
    """An IMMEDIATE transition in a state's list is taken on the next update."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    intro_to_loop = AnimationTransition(
        from_state="intro",
        to_state="loop",
        condition=TransitionCondition.IMMEDIATE,
    )
    add_state(
        fsm,
        AnimationState(
            "intro",
            AnimationClip("intro", [MockTexture("intro")], loop=True),
            transitions=[intro_to_loop],
        ),
    )
    add_state(
        fsm,
        AnimationState("loop", AnimationClip("loop", [MockTexture("loop")], loop=True)),
    )

    set_default_state(fsm, "intro")
    assert fsm.current_state_name == "intro"

    advance_state_machine(fsm, 0.016)
    assert fsm.current_state_name == "loop"


def test_state_machine_transition_priority():
    """State machine should respect transition priority."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    events = []

    clip = AnimationClip("test", [MockTexture()], loop=False)

    # Create transitions with different priorities
    high_priority_transition = AnimationTransition(
        from_state="test",
        to_state="high",
        condition=TransitionCondition.ANIMATION_END,
        priority=10,
    )

    low_priority_transition = AnimationTransition(
        from_state="test",
        to_state="low",
        condition=TransitionCondition.ANIMATION_END,
        priority=1,
    )

    test_state = AnimationState(
        "test",
        clip,
        transitions=[low_priority_transition, high_priority_transition],
    )
    high_state = AnimationState("high", clip, on_enter=lambda: events.append("high"))
    low_state = AnimationState("low", clip, on_enter=lambda: events.append("low"))

    add_state(fsm, test_state)
    add_state(fsm, high_state)
    add_state(fsm, low_state)

    set_default_state(fsm, "test")

    # Update until animation finishes
    advance_state_machine(fsm, 1.0)

    # Should transition to high priority state
    assert fsm.current_state_name == "high"
    assert events == ["high"]


# ===== AnimationSystem Tests =====


def test_animation_system_updates_animator():
    """AnimationSystem should update standalone Animator components."""
    from pyguara.ecs.manager import EntityManager

    sprite = Sprite(MockTexture())
    animator = Animator(sprite)

    frames = [MockTexture(f"idle_{i}") for i in range(4)]
    add_clip(animator, AnimationClip("idle", frames, frame_rate=10.0))
    play_clip(animator, "idle")
    assert sprite.texture is frames[0]

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(animator)

    AnimationSystem(entity_manager, EventDispatcher()).update(0.1)

    # One frame period elapsed -> the driven sprite shows the next frame.
    assert sprite.texture is frames[1]


def test_animation_system_updates_state_machine():
    """AnimationSystem should update AnimationStateMachine components."""
    from pyguara.ecs.manager import EntityManager

    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    frames = [MockTexture(f"idle_{i}") for i in range(4)]
    add_state(
        fsm, AnimationState("idle", AnimationClip("idle", frames, frame_rate=10.0))
    )
    set_default_state(fsm, "idle")
    assert sprite.texture is frames[0]

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(fsm)

    AnimationSystem(entity_manager, EventDispatcher()).update(0.1)

    assert sprite.texture is frames[1]


def test_animation_system_prioritizes_state_machine():
    """AnimationSystem should update an FSM-driven animator exactly once."""
    from pyguara.ecs.manager import EntityManager

    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    frames = [MockTexture(f"idle_{i}") for i in range(4)]
    add_state(
        fsm, AnimationState("idle", AnimationClip("idle", frames, frame_rate=10.0))
    )
    set_default_state(fsm, "idle")

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(animator)
    entity.add_component(fsm)

    AnimationSystem(entity_manager, EventDispatcher()).update(0.1)

    # Frame 1, not frame 2: the entity's Animator is not also updated directly.
    assert sprite.texture is frames[1]


# ===== Frame events =====


def test_landing_on_a_frame_fires_its_events():
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"f{i}") for i in range(4)]
    add_clip(
        animator,
        AnimationClip(
            "attack",
            frames,
            frame_rate=10.0,
            frame_events={2: ("swing_start",)},
        ),
    )
    play_clip(animator, "attack")

    assert advance_animator(animator, 0.1) == []  # frame 1, no event there
    assert advance_animator(animator, 0.1) == ["swing_start"]  # frame 2


def test_a_multi_frame_catch_up_fires_every_crossed_frames_events():
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"f{i}") for i in range(5)]
    add_clip(
        animator,
        AnimationClip(
            "attack",
            frames,
            frame_rate=10.0,
            frame_events={1: ("wind_up",), 2: ("swing_start",), 3: ("swing_end",)},
        ),
    )
    play_clip(animator, "attack")

    # One big dt jumps straight from frame 0 to frame 3 -- every frame
    # events in between still fire, in order, not just the landed-on frame.
    # (0.34, not 0.3: 0.3 / 0.1 rounds to 2.999...96 in binary floating
    # point and would truncate one frame short.)
    assert advance_animator(animator, 0.34) == ["wind_up", "swing_start", "swing_end"]


def test_a_frame_with_no_events_fires_nothing():
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"f{i}") for i in range(3)]
    add_clip(animator, AnimationClip("idle", frames, frame_rate=10.0))
    play_clip(animator, "idle")

    assert advance_animator(animator, 0.1) == []


def test_looping_wraps_and_still_fires_the_wrapped_frames_events():
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"f{i}") for i in range(3)]
    add_clip(
        animator,
        AnimationClip(
            "loop",
            frames,
            frame_rate=10.0,
            loop=True,
            frame_events={0: ("cycle_start",)},
        ),
    )
    play_clip(animator, "loop")

    advance_animator(animator, 0.1)  # frame 1
    assert advance_animator(animator, 0.2) == ["cycle_start"]  # frame 2 then wraps to 0


def test_a_non_looping_clip_still_fires_its_final_frames_events():
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"f{i}") for i in range(3)]
    add_clip(
        animator,
        AnimationClip(
            "attack",
            frames,
            frame_rate=10.0,
            loop=False,
            frame_events={2: ("hit_confirm",)},
        ),
    )
    play_clip(animator, "attack")

    # A big dt would overshoot frame 2 without clamping -- the clip stops
    # at the last frame instead, and that frame's events still fire.
    assert advance_animator(animator, 1.0) == ["hit_confirm"]


def test_frame_events_flow_through_the_state_machine():
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)
    frames = [MockTexture(f"f{i}") for i in range(3)]
    add_state(
        fsm,
        AnimationState(
            "attack",
            AnimationClip(
                "attack", frames, frame_rate=10.0, frame_events={1: ("hit",)}
            ),
        ),
    )
    set_default_state(fsm, "attack")

    assert advance_state_machine(fsm, 0.1) == ["hit"]


def test_animation_system_dispatches_an_animation_frame_event():
    from pyguara.ecs.manager import EntityManager
    from pyguara.graphics.events import AnimationFrameEvent

    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"f{i}") for i in range(3)]
    add_clip(
        animator,
        AnimationClip(
            "attack", frames, frame_rate=10.0, frame_events={1: ("swing_start",)}
        ),
    )
    play_clip(animator, "attack")

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(animator)

    dispatcher = EventDispatcher()
    received: list[AnimationFrameEvent] = []
    dispatcher.subscribe(AnimationFrameEvent, received.append)

    AnimationSystem(entity_manager, dispatcher).update(0.1)

    assert len(received) == 1
    assert received[0].entity_id == entity.id
    assert received[0].name == "swing_start"
    assert received[0].clip_name == "attack"


# ===== Component purity =====


class TestComponentPurity:
    """The two animation components were the last `_allow_methods = True`
    escapes in `pyguara/graphics`. These pin the move down, so a method
    cannot drift back onto them unnoticed."""

    def test_both_components_are_strict(self) -> None:
        from pyguara.ecs.component import StrictComponent

        assert issubclass(Animator, StrictComponent)
        assert issubclass(AnimationStateMachine, StrictComponent)

    def test_neither_component_still_carries_its_behaviour(self) -> None:
        """A negative control for the test above: `issubclass` alone would
        pass just as happily with every method still attached."""
        for gone in ("add_clip", "play", "update"):
            assert not hasattr(Animator, gone)
        for gone in ("add_state", "set_default_state", "transition_to", "update"):
            assert not hasattr(AnimationStateMachine, gone)

    def test_adding_a_method_back_fails_at_class_definition(self) -> None:
        with pytest.raises(TypeError, match="Regression"):

            class Regression(Animator):
                def tick(self, dt: float) -> None:
                    pass
