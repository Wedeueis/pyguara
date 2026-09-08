"""Tests for animation state machine."""

import pytest

from pyguara.graphics.animation_system import AnimationSystem
from pyguara.graphics.components.animation import (
    AnimationClip,
    AnimationState,
    AnimationStateMachine,
    AnimationTransition,
    Animator,
    TransitionCondition,
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
    animator.add_clip(idle_clip)

    # Initially not playing
    assert animator.is_playing is False
    assert animator.current_clip_name is None
    assert animator.is_finished is False

    # Start playing
    animator.play("idle")
    assert animator.is_playing is True
    assert animator.current_clip_name == "idle"
    assert animator.is_finished is False


def test_animator_catches_up_multiple_frames_in_one_update():
    """A dt larger than one frame period should advance every frame it covers."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"run_{i}") for i in range(8)]
    animator.add_clip(AnimationClip("run", frames, frame_rate=10.0, loop=True))
    animator.play("run")

    # 10 FPS => 0.1s/frame. A 0.45s lag spike should land on frame 4, not 1.
    animator.update(0.45)
    assert sprite.texture is frames[4]

    # A dt that wraps past the end of a looping clip lands correctly.
    animator.update(0.6)  # +6 frames from 4 => 10 => wraps to 2
    assert sprite.texture is frames[2]


def test_animator_non_looping_clamps_on_a_large_dt():
    """A huge dt on a non-looping clip stops on the last frame, not past it."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    frames = [MockTexture(f"a_{i}") for i in range(3)]
    animator.add_clip(AnimationClip("attack", frames, frame_rate=10.0, loop=False))
    animator.play("attack")

    animator.update(5.0)  # far past the 0.3s clip

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
    animator.add_clip(clip)

    animator.play("attack")
    assert animator.is_finished is False

    # Update through the animation (3 frames / 10 FPS = 0.3 seconds)
    animator.update(0.1)  # Frame 1
    assert animator.is_finished is False

    animator.update(0.1)  # Frame 2
    assert animator.is_finished is False

    animator.update(0.1)  # Animation finishes
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

    fsm.add_state(state)

    # State should be registered internally
    assert "idle" in fsm._states


def test_state_machine_set_default_state():
    """State machine should enter default state."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    clip = AnimationClip("idle", [MockTexture()])
    state = AnimationState("idle", clip)
    fsm.add_state(state)

    fsm.set_default_state("idle")

    assert fsm.current_state_name == "idle"
    assert animator.is_playing is True
    assert animator.current_clip_name == "idle"


def test_state_machine_set_invalid_default_state():
    """State machine should raise error for invalid default state."""
    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    with pytest.raises(ValueError, match="does not exist"):
        fsm.set_default_state("nonexistent")


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

    fsm.add_state(idle_state)
    fsm.add_state(walk_state)

    fsm.set_default_state("idle")
    assert fsm.current_state_name == "idle"

    # Manual transition
    result = fsm.transition_to("walk")
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

    fsm.add_state(idle_state)
    fsm.add_state(walk_state)

    fsm.set_default_state("idle")
    assert events == ["idle_enter"]

    events.clear()

    fsm.transition_to("walk")
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

    fsm.add_state(attack_state)
    fsm.add_state(idle_state)

    fsm.set_default_state("attack")
    assert fsm.current_state_name == "attack"

    # Update until animation finishes (2 frames at 10 FPS = 0.2s)
    fsm.update(0.1)  # Frame 1
    assert fsm.current_state_name == "attack"

    # Animation finishes and transitions to idle
    fsm.update(0.1)  # Frame 2, animation ends, transition triggers
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
    fsm.add_state(state)
    fsm.set_default_state("attack")

    # Update until animation finishes
    fsm.update(0.1)  # Frame 1
    assert len(completed) == 0

    fsm.update(0.1)  # Animation finishes, callback should fire
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
    fsm.add_state(state)
    fsm.set_default_state("death")

    for _ in range(20):
        fsm.update(0.1)

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
    fsm.add_state(AnimationState("hit", clip, on_complete=lambda: completed.append(1)))
    fsm.set_default_state("hit")

    for _ in range(5):
        fsm.update(0.1)
    assert len(completed) == 1

    fsm.transition_to("hit", force=True)  # replay
    for _ in range(5):
        fsm.update(0.1)
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
    fsm.add_state(
        AnimationState(
            "intro",
            AnimationClip("intro", [MockTexture("intro")], loop=True),
            transitions=[intro_to_loop],
        )
    )
    fsm.add_state(
        AnimationState("loop", AnimationClip("loop", [MockTexture("loop")], loop=True))
    )

    fsm.set_default_state("intro")
    assert fsm.current_state_name == "intro"

    fsm.update(0.016)
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

    fsm.add_state(test_state)
    fsm.add_state(high_state)
    fsm.add_state(low_state)

    fsm.set_default_state("test")

    # Update until animation finishes
    fsm.update(1.0)

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
    animator.add_clip(AnimationClip("idle", frames, frame_rate=10.0))
    animator.play("idle")
    assert sprite.texture is frames[0]

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(animator)

    AnimationSystem(entity_manager).update(0.1)

    # One frame period elapsed -> the driven sprite shows the next frame.
    assert sprite.texture is frames[1]


def test_animation_system_updates_state_machine():
    """AnimationSystem should update AnimationStateMachine components."""
    from pyguara.ecs.manager import EntityManager

    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    frames = [MockTexture(f"idle_{i}") for i in range(4)]
    fsm.add_state(
        AnimationState("idle", AnimationClip("idle", frames, frame_rate=10.0))
    )
    fsm.set_default_state("idle")
    assert sprite.texture is frames[0]

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(fsm)

    AnimationSystem(entity_manager).update(0.1)

    assert sprite.texture is frames[1]


def test_animation_system_prioritizes_state_machine():
    """AnimationSystem should update an FSM-driven animator exactly once."""
    from pyguara.ecs.manager import EntityManager

    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    frames = [MockTexture(f"idle_{i}") for i in range(4)]
    fsm.add_state(
        AnimationState("idle", AnimationClip("idle", frames, frame_rate=10.0))
    )
    fsm.set_default_state("idle")

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(animator)
    entity.add_component(fsm)

    AnimationSystem(entity_manager).update(0.1)

    # Frame 1, not frame 2: the entity's Animator is not also updated directly.
    assert sprite.texture is frames[1]
