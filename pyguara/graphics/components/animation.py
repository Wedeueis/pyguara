"""Animation Logic Component."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from enum import Enum, auto
from pyguara.resources.types import Texture
from pyguara.graphics.components.sprite import Sprite
from pyguara.ecs.component import BaseComponent


@dataclass
class AnimationClip:
    """Data for a single animation state (e.g., 'walk_down')."""

    name: str
    frames: List[Texture]
    frame_rate: float = 10.0  # Frames per second
    loop: bool = True


class Animator(BaseComponent):
    """
    Component that manages playback of AnimationClips.

    It 'drives' a Sprite component. Every frame, it calculates which texture
    frame should be visible and assigns it to the Sprite.
    """

    def __init__(self, sprite: Sprite) -> None:
        """Initialize the animator with a target sprite.

        Args:
            sprite: The sprite component that this animator will update.
        """
        super().__init__()
        self._sprite = sprite
        self._clips: Dict[str, AnimationClip] = {}

        self._current_clip: Optional[AnimationClip] = None
        self._current_time: float = 0.0
        self._current_frame_index: int = 0
        self._playing: bool = False

    def add_clip(self, clip: AnimationClip) -> None:
        """Register a new animation state."""
        self._clips[clip.name] = clip

    def play(self, name: str, force_reset: bool = False) -> None:
        """
        Start playing an animation.

        Args:
            name (str): The name of the clip (e.g., 'run').
            force_reset (bool): If True, restarts animation even if already playing it.
        """
        if name not in self._clips:
            print(f"[Animator] Warning: Clip '{name}' not found.")
            return

        # Optimization: Don't restart if we are already playing this clip
        if self._current_clip and self._current_clip.name == name and not force_reset:
            return

        self._current_clip = self._clips[name]
        self._current_time = 0.0
        self._current_frame_index = 0
        self._playing = True

        # Apply first frame immediately
        self._apply_frame()

    def update(self, dt: float) -> None:
        """Advance the animation timer."""
        if not self._playing or not self._current_clip:
            return

        self._current_time += dt

        # Calculate duration of a single frame
        seconds_per_frame = 1.0 / self._current_clip.frame_rate

        if self._current_time >= seconds_per_frame:
            # Move to next frame
            self._current_time -= seconds_per_frame
            self._current_frame_index += 1

            # Handle Looping
            total_frames = len(self._current_clip.frames)

            if self._current_frame_index >= total_frames:
                if self._current_clip.loop:
                    self._current_frame_index = 0
                else:
                    self._current_frame_index = total_frames - 1
                    self._playing = False  # Stop at end

            self._apply_frame()

    def _apply_frame(self) -> None:
        """Update the visual Sprite component with the current texture."""
        # FIX: Check for None to satisfy Mypy
        if self._current_clip is None:
            return

        frame = self._current_clip.frames[self._current_frame_index]
        self._sprite.texture = frame

    @property
    def is_playing(self) -> bool:
        """Check if an animation is currently playing."""
        return self._playing

    @property
    def current_clip_name(self) -> Optional[str]:
        """Get the name of the currently playing clip."""
        return self._current_clip.name if self._current_clip else None

    @property
    def is_finished(self) -> bool:
        """Check if the current non-looping animation has finished."""
        if not self._current_clip or self._current_clip.loop:
            return False
        return not self._playing


# ===== Animation State Machine =====


class TransitionCondition(Enum):
    """Conditions that can trigger state transitions."""

    ANIMATION_END = auto()  # Transition when current animation finishes
    IMMEDIATE = auto()  # Transition immediately (manual trigger)


@dataclass
class AnimationTransition:
    """
    Defines a transition from one animation state to another.

    Attributes:
        from_state (str): Source state name.
        to_state (str): Target state name.
        condition (TransitionCondition): When to trigger the transition.
        priority (int): Higher priority transitions are checked first.
    """

    from_state: str
    to_state: str
    condition: TransitionCondition
    priority: int = 0


@dataclass
class AnimationState:
    """
    Represents a single state in the animation state machine.

    Attributes:
        name (str): Unique identifier for this state.
        clip (AnimationClip): The animation clip to play in this state.
        transitions (List[AnimationTransition]): Possible transitions from this state.
        on_enter (Optional[Callable]): Callback when entering this state.
        on_exit (Optional[Callable]): Callback when exiting this state.
        on_complete (Optional[Callable]): Callback when animation completes.
    """

    name: str
    clip: AnimationClip
    transitions: List[AnimationTransition] = field(default_factory=list)
    on_enter: Optional[Callable[[], None]] = None
    on_exit: Optional[Callable[[], None]] = None
    on_complete: Optional[Callable[[], None]] = None


class AnimationStateMachine(BaseComponent):
    """
    Hierarchical Finite State Machine for animation control.

    Manages states, transitions, and callbacks for complex animation behavior.
    Built on top of the Animator component.
    """

    def __init__(self, sprite: Sprite, animator: Animator):
        """
        Initialize the state machine.

        Args:
            sprite (Sprite): The sprite to animate.
            animator (Animator): The animator that will play clips.
        """
        super().__init__()
        self._sprite = sprite
        self._animator = animator
        self._states: Dict[str, AnimationState] = {}
        self._current_state: Optional[AnimationState] = None
        self._default_state: Optional[str] = None

    def add_state(self, state: AnimationState) -> None:
        """
        Register a new animation state.

        Args:
            state (AnimationState): The state to add.
        """
        self._states[state.name] = state
        # Register the clip with the animator
        self._animator.add_clip(state.clip)

    def set_default_state(self, state_name: str) -> None:
        """
        Set the default state to enter when starting the state machine.

        Args:
            state_name (str): Name of the default state.

        Raises:
            ValueError: If the state doesn't exist.
        """
        if state_name not in self._states:
            raise ValueError(f"State '{state_name}' does not exist")
        self._default_state = state_name
        # Auto-enter default state
        self.transition_to(state_name, force=True)

    def transition_to(self, state_name: str, force: bool = False) -> bool:
        """
        Transition to a new state.

        Args:
            state_name (str): Name of the target state.
            force (bool): If True, transition even if already in this state.

        Returns:
            bool: True if transition succeeded, False otherwise.
        """
        if state_name not in self._states:
            print(f"[AnimationStateMachine] Warning: State '{state_name}' not found")
            return False

        target_state = self._states[state_name]

        # Skip if already in this state (unless forced)
        if not force and self._current_state == target_state:
            return False

        # Exit current state
        if self._current_state and self._current_state.on_exit:
            self._current_state.on_exit()

        # Enter new state
        self._current_state = target_state

        # Call on_enter callback
        if target_state.on_enter:
            target_state.on_enter()

        # Start playing the animation
        self._animator.play(target_state.clip.name, force_reset=True)

        return True

    def update(self, dt: float) -> None:
        """
        Update the state machine and check for transitions.

        Args:
            dt (float): Delta time in seconds.
        """
        # Update the animator
        self._animator.update(dt)

        if not self._current_state:
            return

        # Check if animation finished
        if self._animator.is_finished:
            # Call on_complete callback
            if self._current_state.on_complete:
                self._current_state.on_complete()

            # Check for automatic transitions
            self._check_transitions()

    def _check_transitions(self) -> None:
        """Check if any transitions should trigger based on current conditions."""
        if not self._current_state:
            return

        # Sort transitions by priority (highest first)
        sorted_transitions = sorted(
            self._current_state.transitions, key=lambda t: t.priority, reverse=True
        )

        for transition in sorted_transitions:
            # Check if condition is met
            should_transition = False

            if transition.condition == TransitionCondition.ANIMATION_END:
                # Transition when animation finishes
                if self._animator.is_finished:
                    should_transition = True

            # Execute transition if condition met
            if should_transition:
                self.transition_to(transition.to_state)
                break  # Only execute one transition per update

    @property
    def current_state_name(self) -> Optional[str]:
        """Get the name of the current state."""
        return self._current_state.name if self._current_state else None
