"""Animation Logic Component."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto

from pyguara.ecs.component import BaseComponent
from pyguara.graphics.components.sprite import Sprite
from pyguara.log import get_logger
from pyguara.resources.types import Texture

logger = get_logger(__name__)


@dataclass
class AnimationClip:
    """Data for a single animation state (e.g., 'walk_down').

    Attributes:
        frame_events: 0-based frame index -> event name(s) fired when
            `Animator.update()` lands on (or catches up through) that
            frame. Consumed by `AnimationSystem`, which turns each fired
            name into an `AnimationFrameEvent` -- the mechanism
            `kits/action_combat`'s `ActiveFrameWindow` uses to toggle a
            Hitbox's active frames without its own timer. Not fired for
            frame 0 by `play()`'s initial-frame application; only by
            `update()`-driven frame transitions.
    """

    name: str
    frames: list[Texture]
    frame_rate: float = 10.0  # Frames per second
    loop: bool = True
    frame_events: dict[int, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject clips that cannot be played (empty, or non-positive rate)."""
        if not self.frames:
            raise ValueError(f"AnimationClip '{self.name}' has no frames")
        if self.frame_rate <= 0:
            raise ValueError(
                f"AnimationClip '{self.name}' frame_rate must be positive, "
                f"got {self.frame_rate}"
            )


class Animator(BaseComponent):
    """Component that manages playback of AnimationClips.

    It 'drives' a Sprite component. Every frame, it calculates which texture
    frame should be visible and assigns it to the Sprite.

    Note:
        This is a legacy component with playback logic. Ideally, animation
        logic would be in an AnimationSystem.
    """

    # Tracked debt, not an answer: this component's behaviour belongs in
    # a system, and moving it is #37's job. The escape keeps it
    # compiling until then.
    _allow_methods = True

    def __init__(self, sprite: Sprite) -> None:
        """Initialize the animator with a target sprite.

        Args:
            sprite: The sprite component that this animator will update.
        """
        super().__init__()
        self._sprite = sprite
        self._clips: dict[str, AnimationClip] = {}

        self._current_clip: AnimationClip | None = None
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
            logger.warning("Animation clip '%s' not found", name)
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

    def update(self, dt: float) -> list[str]:
        """Advance the animation timer.

        Catches up all whole frames owed for ``dt`` in one call, so a lag
        spike or a host running slower than the clip's ``frame_rate`` does not
        silently drop frames or fall permanently behind.

        Returns:
            Every `AnimationClip.frame_events` name attached to a frame
            crossed this call, oldest first -- every frame in between on a
            multi-frame catch-up, not just the one landed on, so a hit
            window can't be skipped by a lag spike.
        """
        if not self._playing or not self._current_clip:
            return []

        self._current_time += dt

        # Duration of a single frame; frame_rate is > 0 (AnimationClip validates).
        seconds_per_frame = 1.0 / self._current_clip.frame_rate
        if self._current_time < seconds_per_frame:
            return []

        frames_advanced = int(self._current_time / seconds_per_frame)
        self._current_time -= frames_advanced * seconds_per_frame

        total_frames = len(self._current_clip.frames)
        previous_index = self._current_frame_index
        raw_index = previous_index + frames_advanced

        if raw_index < total_frames:
            self._current_frame_index = raw_index
            crossed = range(previous_index + 1, raw_index + 1)
        elif self._current_clip.loop:
            self._current_frame_index = raw_index % total_frames
            crossed = range(previous_index + 1, raw_index + 1)
        else:
            self._current_frame_index = total_frames - 1
            self._current_time = 0.0
            self._playing = False  # Stop at end
            crossed = range(previous_index + 1, total_frames)

        frame_events = self._current_clip.frame_events
        fired = [
            name
            for index in crossed
            for name in frame_events.get(index % total_frames, ())
        ]

        self._apply_frame()
        return fired

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
    def current_clip_name(self) -> str | None:
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
    transitions: list[AnimationTransition] = field(default_factory=list)
    on_enter: Callable[[], None] | None = None
    on_exit: Callable[[], None] | None = None
    on_complete: Callable[[], None] | None = None


class AnimationStateMachine(BaseComponent):
    """Hierarchical Finite State Machine for animation control.

    Manages states, transitions, and callbacks for complex animation behavior.
    Built on top of the Animator component.

    Note:
        This is a legacy component with state machine logic. Ideally, FSM
        logic would be in an AnimationStateMachineSystem.
    """

    # Tracked debt, not an answer: this component's behaviour belongs in
    # a system, and moving it is #37's job. The escape keeps it
    # compiling until then.
    _allow_methods = True

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
        self._states: dict[str, AnimationState] = {}
        self._current_state: AnimationState | None = None
        self._default_state: str | None = None
        # Latch so on_complete / ANIMATION_END fire once per clip completion,
        # not every frame the finished clip sits on its last frame.
        self._completion_handled: bool = False

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
            logger.warning("Animation state '%s' not found", state_name)
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
        self._completion_handled = False

        # Call on_enter callback
        if target_state.on_enter:
            target_state.on_enter()

        # Start playing the animation
        self._animator.play(target_state.clip.name, force_reset=True)

        return True

    def update(self, dt: float) -> list[str]:
        """
        Update the state machine and check for transitions.

        Args:
            dt (float): Delta time in seconds.

        Returns:
            Frame-event names fired by the animator this call -- see
            `Animator.update()`.
        """
        # Update the animator
        fired = self._animator.update(dt)

        if not self._current_state:
            return fired

        # Fire the completion callback once, on the frame the clip finishes.
        if self._animator.is_finished and not self._completion_handled:
            self._completion_handled = True
            if self._current_state.on_complete:
                self._current_state.on_complete()

        # Check for automatic transitions every frame (IMMEDIATE fires as soon
        # as the state is entered; ANIMATION_END only once the clip finishes).
        self._check_transitions()

        return fired

    def _check_transitions(self) -> None:
        """Check if any transitions should trigger based on current conditions."""
        if not self._current_state:
            return

        # Sort transitions by priority (highest first)
        sorted_transitions = sorted(
            self._current_state.transitions, key=lambda t: t.priority, reverse=True
        )

        for transition in sorted_transitions:
            should_transition = (
                transition.condition == TransitionCondition.IMMEDIATE
                or (
                    transition.condition == TransitionCondition.ANIMATION_END
                    and self._animator.is_finished
                )
            )

            if should_transition:
                self.transition_to(transition.to_state)
                break  # Only execute one transition per update

    @property
    def current_state_name(self) -> str | None:
        """Get the name of the current state."""
        return self._current_state.name if self._current_state else None
