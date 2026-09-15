"""Animation Logic Component."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto

from pyguara.ecs.component import StrictComponent
from pyguara.graphics.components.sprite import Sprite
from pyguara.log import get_logger
from pyguara.resources.types import Texture

logger = get_logger(__name__)


@dataclass
class AnimationClip:
    """Data for a single animation state (e.g., 'walk_down').

    Attributes:
        frame_events: 0-based frame index -> event name(s) fired when
            `advance_animator()` lands on (or catches up through) that
            frame. Consumed by `AnimationSystem`, which turns each fired
            name into an `AnimationFrameEvent` -- the mechanism
            `kits/action_combat`'s `ActiveFrameWindow` uses to toggle a
            Hitbox's active frames without its own timer. Not fired for
            frame 0 by `play_clip()`'s initial-frame application; only by
            `advance_animator()`-driven frame transitions.
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


class Animator(StrictComponent):
    """Component that manages playback of AnimationClips.

    It 'drives' a Sprite component. Every frame, it calculates which texture
    frame should be visible and assigns it to the Sprite.

    Holds the clip table and the playback cursor; the behaviour that moves
    that cursor lives beside this class as free functions, and
    `AnimationSystem` is what calls them each frame. See "Playback" below.
    """

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


class AnimationStateMachine(StrictComponent):
    """Hierarchical Finite State Machine for animation control.

    Manages states, transitions, and callbacks for complex animation behavior.
    Built on top of the Animator component.

    Holds the state table and the current state; the transition logic
    lives beside this class as free functions, driven by
    `AnimationSystem`. See "Playback" below.
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
        self._states: dict[str, AnimationState] = {}
        self._current_state: AnimationState | None = None
        self._default_state: str | None = None
        # Latch so on_complete / ANIMATION_END fire once per clip completion,
        # not every frame the finished clip sits on its last frame.
        self._completion_handled: bool = False

    @property
    def current_state_name(self) -> str | None:
        """Get the name of the current state."""
        return self._current_state.name if self._current_state else None


# --- Playback ------------------------------------------------------
#
# The behaviour that drives the two components above, as free functions
# beside the data they move -- the same split `Transform`/`set_parent`
# and `Health`/`apply_damage` use. `AnimationSystem` calls
# `advance_animator` / `advance_state_machine` once per frame; a game
# calls `play_clip` and `transition_to` directly.
#
# These read and write the components' private cursors. That is
# deliberate: they are those classes' own behaviour, living in their own
# module, not an outside caller reaching in.


def add_clip(animator: Animator, clip: AnimationClip) -> None:
    """Register `clip` under its own name, replacing any clip of that name.

    Args:
        animator: The animator to register with.
        clip: The clip to add.
    """
    animator._clips[clip.name] = clip


def play_clip(animator: Animator, name: str, force_reset: bool = False) -> None:
    """Start playing the clip called `name`.

    Re-requesting the clip already playing is ignored unless
    `force_reset` is set, so a caller can ask every frame -- which is what
    a state machine does -- without restarting the animation each time.

    Args:
        animator: The animator to drive.
        name: The clip's name, e.g. "run".
        force_reset: Restart even if this clip is already playing.
    """
    if name not in animator._clips:
        logger.warning("Animation clip '%s' not found", name)
        return

    current = animator._current_clip
    if current and current.name == name and not force_reset:
        return

    animator._current_clip = animator._clips[name]
    animator._current_time = 0.0
    animator._current_frame_index = 0
    animator._playing = True

    # Apply the first frame immediately, so the sprite does not show the
    # previous clip's texture for one frame.
    animator._apply_frame()


def advance_animator(animator: Animator, dt: float) -> list[str]:
    """Advance the playback cursor by `dt`.

    Catches up every whole frame owed for `dt` in one call, so a lag spike
    or a host running slower than the clip's `frame_rate` does not
    silently drop frames or fall permanently behind.

    Args:
        animator: The animator to advance.
        dt: Seconds since the last call.

    Returns:
        Every `AnimationClip.frame_events` name attached to a frame
        crossed this call, oldest first -- every frame in between on a
        multi-frame catch-up, not just the one landed on, so a hit window
        cannot be skipped by a lag spike.
    """
    clip = animator._current_clip
    if not animator._playing or not clip:
        return []

    animator._current_time += dt

    # frame_rate is > 0; `AnimationClip` validates it.
    seconds_per_frame = 1.0 / clip.frame_rate
    if animator._current_time < seconds_per_frame:
        return []

    frames_advanced = int(animator._current_time / seconds_per_frame)
    animator._current_time -= frames_advanced * seconds_per_frame

    total_frames = len(clip.frames)
    previous_index = animator._current_frame_index
    raw_index = previous_index + frames_advanced

    if raw_index < total_frames:
        animator._current_frame_index = raw_index
        crossed = range(previous_index + 1, raw_index + 1)
    elif clip.loop:
        animator._current_frame_index = raw_index % total_frames
        crossed = range(previous_index + 1, raw_index + 1)
    else:
        animator._current_frame_index = total_frames - 1
        animator._current_time = 0.0
        animator._playing = False  # Stop at end
        crossed = range(previous_index + 1, total_frames)

    frame_events = clip.frame_events
    fired = [
        name for index in crossed for name in frame_events.get(index % total_frames, ())
    ]

    animator._apply_frame()
    return fired


def add_state(machine: AnimationStateMachine, state: AnimationState) -> None:
    """Register `state`, and its clip with the machine's animator.

    Args:
        machine: The state machine to register with.
        state: The state to add.
    """
    machine._states[state.name] = state
    add_clip(machine._animator, state.clip)


def set_default_state(machine: AnimationStateMachine, state_name: str) -> None:
    """Set the machine's starting state and enter it immediately.

    Args:
        machine: The state machine to configure.
        state_name: Name of the default state.

    Raises:
        ValueError: If no state of that name has been added.
    """
    if state_name not in machine._states:
        raise ValueError(f"State '{state_name}' does not exist")
    machine._default_state = state_name
    transition_to(machine, state_name, force=True)


def transition_to(
    machine: AnimationStateMachine, state_name: str, force: bool = False
) -> bool:
    """Move the machine into `state_name`, running the state callbacks.

    Args:
        machine: The state machine to move.
        state_name: Name of the target state.
        force: Re-enter even if the machine is already in that state.

    Returns:
        Whether the transition happened.
    """
    if state_name not in machine._states:
        logger.warning("Animation state '%s' not found", state_name)
        return False

    target_state = machine._states[state_name]

    if not force and machine._current_state == target_state:
        return False

    if machine._current_state and machine._current_state.on_exit:
        machine._current_state.on_exit()

    machine._current_state = target_state
    machine._completion_handled = False

    if target_state.on_enter:
        target_state.on_enter()

    play_clip(machine._animator, target_state.clip.name, force_reset=True)
    return True


def advance_state_machine(machine: AnimationStateMachine, dt: float) -> list[str]:
    """Advance the machine's animator and take any transition now due.

    Args:
        machine: The state machine to advance.
        dt: Seconds since the last call.

    Returns:
        The frame-event names the animator fired -- see
        `advance_animator`.
    """
    fired = advance_animator(machine._animator, dt)

    if not machine._current_state:
        return fired

    # Once per completion, not every frame the finished clip sits on its
    # last frame.
    if machine._animator.is_finished and not machine._completion_handled:
        machine._completion_handled = True
        if machine._current_state.on_complete:
            machine._current_state.on_complete()

    _take_due_transition(machine)
    return fired


def _take_due_transition(machine: AnimationStateMachine) -> None:
    """Take the highest-priority transition whose condition now holds.

    At most one per advance: taking two in a frame would skip a state's
    `on_enter` work entirely.
    """
    state = machine._current_state
    if not state:
        return

    for transition in sorted(state.transitions, key=lambda t: t.priority, reverse=True):
        due = transition.condition == TransitionCondition.IMMEDIATE or (
            transition.condition == TransitionCondition.ANIMATION_END
            and machine._animator.is_finished
        )
        if due:
            transition_to(machine, transition.to_state)
            break
