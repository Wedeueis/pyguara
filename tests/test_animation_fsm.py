"""Tests for animation state machine."""

import pytest
from pyguara.graphics.components.animation import (
    AnimationClip,
    Animator,
    AnimationState,
    AnimationTransition,
    AnimationStateMachine,
    TransitionCondition,
)
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.animation_system import AnimationSystem
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

    clip = AnimationClip(
        "idle", [MockTexture(f"idle_{i}") for i in range(4)], frame_rate=10.0
    )
    animator.add_clip(clip)
    animator.play("idle")

    assert animator._current_frame_index == 0

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(animator)

    system = AnimationSystem(entity_manager)
    system.update(0.1)

    # Animator should have advanced to the next frame
    assert animator._current_frame_index == 1


def test_animation_system_updates_state_machine():
    """AnimationSystem should update AnimationStateMachine components."""
    from pyguara.ecs.manager import EntityManager

    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    clip = AnimationClip(
        "idle", [MockTexture(f"idle_{i}") for i in range(4)], frame_rate=10.0
    )
    state = AnimationState("idle", clip)
    fsm.add_state(state)
    fsm.set_default_state("idle")

    assert animator._current_frame_index == 0

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(fsm)

    system = AnimationSystem(entity_manager)
    system.update(0.1)

    # State machine should have been updated (which updates the animator)
    assert animator._current_frame_index == 1


def test_animation_system_prioritizes_state_machine():
    """AnimationSystem should prioritize FSM over standalone Animator."""
    from pyguara.ecs.manager import EntityManager

    sprite = Sprite(MockTexture())
    animator = Animator(sprite)
    fsm = AnimationStateMachine(sprite, animator)

    clip = AnimationClip(
        "idle", [MockTexture(f"idle_{i}") for i in range(4)], frame_rate=10.0
    )
    state = AnimationState("idle", clip)
    fsm.add_state(state)
    fsm.set_default_state("idle")

    assert animator._current_frame_index == 0

    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(animator)
    entity.add_component(fsm)

    system = AnimationSystem(entity_manager)

    # Should only update FSM (which updates animator internally)
    # This prevents double-updating the animator
    system.update(0.1)

    # Verify it was updated once (should be on frame 1)
    assert animator._current_frame_index == 1
