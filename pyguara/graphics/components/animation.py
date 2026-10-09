"""Animation Logic Component."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto

from pyguara.ecs.component import StrictComponent
from pyguara.graphics.components.sprite import Sprite
from pyguara.log import get_logger
from pyguara.resources.types import Texture

logger = get_logger(__name__)


class PlaybackMode(Enum):
    """How a clip behaves when it reaches its last frame.

    A single `loop` bool could only say "start over" or "stop", which
    leaves out the two things an idle animation and a one-shot both want:
    breathing back down rather than snapping to frame 0, and finishing
    N times rather than once or forever.

    Attributes:
        ONCE: Stop on the last frame.
        LOOP: Jump back to frame 0 and keep going.
        PING_PONG: Play forwards, then backwards, then forwards -- an idle
            bob or a breathing loop, where a hard cut back to frame 0 is
            visible as a hitch.
        LOOP_TIMES: Loop `loop_count` times, then stop on the last frame.
    """

    ONCE = auto()
    LOOP = auto()
    PING_PONG = auto()
    LOOP_TIMES = auto()


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
        mode: What happens at the last frame. Defaults to None, which
            means "whatever `loop` says" -- `loop` predates this and
            plenty of clips (and every prefab file) still set it.
        loop_count: How many loops `LOOP_TIMES` runs. Ignored otherwise.
    """

    name: str
    frames: list[Texture]
    frame_rate: float = 10.0  # Frames per second
    loop: bool = True
    frame_events: dict[int, tuple[str, ...]] = field(default_factory=dict)
    mode: PlaybackMode | None = None
    loop_count: int = 1

    def __post_init__(self) -> None:
        """Reject clips that cannot be played, and settle the mode.

        `loop` is kept as the serialized form and `mode` derived from it
        when nothing set one, so an existing clip or prefab keeps working
        and a clip that sets `mode` gets the richer behaviour. Setting
        both inconsistently resolves in `mode`'s favour, since it is the
        more specific statement.

        Raises:
            ValueError: If there are no frames, the frame rate is not
                positive, or `LOOP_TIMES` was asked for without a positive
                count -- which would stop on the first frame and look like
                a missing animation.
        """
        if not self.frames:
            raise ValueError(f"AnimationClip '{self.name}' has no frames")
        if self.frame_rate <= 0:
            raise ValueError(
                f"AnimationClip '{self.name}' frame_rate must be positive, "
                f"got {self.frame_rate}"
            )

        if self.mode is None:
            self.mode = PlaybackMode.LOOP if self.loop else PlaybackMode.ONCE
        else:
            self.loop = self.mode in (
                PlaybackMode.LOOP,
                PlaybackMode.PING_PONG,
                PlaybackMode.LOOP_TIMES,
            )

        if self.mode is PlaybackMode.LOOP_TIMES and self.loop_count < 1:
            raise ValueError(
                f"AnimationClip '{self.name}' uses LOOP_TIMES with "
                f"loop_count={self.loop_count}; it must be at least 1."
            )

    @property
    def playback_mode(self) -> PlaybackMode:
        """The settled playback mode. Never None after `__post_init__`."""
        assert self.mode is not None
        return self.mode


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

        # Multiplier over the clip's own `frame_rate`. A haste or slow buff
        # should not need every clip swapped for a faster copy. 0 freezes
        # the cursor without clearing `is_playing`, which is what a
        # hitstop wants -- the animation resumes rather than restarting.
        self.playback_speed: float = 1.0

        # PING_PONG direction, and completed-loop count for LOOP_TIMES.
        self._reverse: bool = False
        self._loops_done: int = 0

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
    animator._reverse = False
    animator._loops_done = 0
    animator._playing = True

    # Apply the first frame immediately, so the sprite does not show the
    # previous clip's texture for one frame.
    animator._apply_frame()


def advance_animator(animator: Animator, dt: float) -> list[str]:
    """Advance the playback cursor by `dt`.

    Catches up every whole frame owed for `dt` in one call, so a lag spike
    or a host running slower than the clip's `frame_rate` does not
    silently drop frames or fall permanently behind.

    `dt` is scaled by `animator.playback_speed` first, so a haste buff is
    one field rather than a second copy of every clip. A speed of 0 holds
    the cursor without clearing `is_playing`, which is what a hitstop
    wants: the animation resumes where it was instead of restarting.

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

    scaled = dt * animator.playback_speed
    if scaled <= 0:
        return []

    animator._current_time += scaled

    # frame_rate is > 0; `AnimationClip` validates it.
    seconds_per_frame = 1.0 / clip.frame_rate
    if animator._current_time < seconds_per_frame:
        return []

    frames_advanced = int(animator._current_time / seconds_per_frame)
    animator._current_time -= frames_advanced * seconds_per_frame

    crossed = _step_cursor(animator, clip, frames_advanced)

    total_frames = len(clip.frames)
    frame_events = clip.frame_events
    fired = [
        name for index in crossed for name in frame_events.get(index % total_frames, ())
    ]

    animator._apply_frame()
    return fired


def _step_cursor(
    animator: Animator, clip: AnimationClip, frames_advanced: int
) -> list[int]:
    """Move the frame cursor by whole frames, per the clip's playback mode.

    Returns the indices crossed rather than only the one landed on, so a
    frame event in a hit window cannot be skipped by a lag spike -- which
    is why PING_PONG walks frame by frame instead of computing the final
    index with modular arithmetic. The walk is bounded by
    `frames_advanced`, which a long frame makes large but never unbounded.

    Args:
        animator: The animator whose cursor to move.
        clip: Its current clip.
        frames_advanced: How many whole frames are owed.

    Returns:
        The frame indices crossed, oldest first.
    """
    total_frames = len(clip.frames)
    mode = clip.playback_mode

    if total_frames == 1:
        # Nothing to advance through; a one-frame ONCE clip still has to
        # stop, or `is_finished` never becomes true.
        if mode is PlaybackMode.ONCE:
            animator._playing = False
            animator._current_time = 0.0
        return []

    previous_index = animator._current_frame_index

    if mode is PlaybackMode.LOOP:
        raw = previous_index + frames_advanced
        animator._current_frame_index = raw % total_frames
        return list(range(previous_index + 1, raw + 1))

    if mode is PlaybackMode.ONCE:
        raw = previous_index + frames_advanced
        if raw < total_frames:
            animator._current_frame_index = raw
            return list(range(previous_index + 1, raw + 1))
        animator._current_frame_index = total_frames - 1
        animator._current_time = 0.0
        animator._playing = False
        return list(range(previous_index + 1, total_frames))

    if mode is PlaybackMode.LOOP_TIMES:
        raw = previous_index + frames_advanced
        crossed = list(range(previous_index + 1, raw + 1))
        animator._loops_done += raw // total_frames
        if animator._loops_done >= clip.loop_count:
            animator._current_frame_index = total_frames - 1
            animator._current_time = 0.0
            animator._playing = False
            # Trim what never played: the clip stopped at the end of its
            # last loop, so anything past that was not crossed.
            allowed = clip.loop_count * total_frames - 1
            return [index for index in crossed if index <= allowed]
        animator._current_frame_index = raw % total_frames
        return crossed

    # PING_PONG: walk, because the direction flips mid-run and no closed
    # form gives the crossed indices as well as the destination.
    crossed = []
    index = previous_index
    for _ in range(frames_advanced):
        if animator._reverse:
            if index == 0:
                animator._reverse = False
                index = 1
            else:
                index -= 1
        else:
            if index == total_frames - 1:
                animator._reverse = True
                index = total_frames - 2
            else:
                index += 1
        crossed.append(index)
    animator._current_frame_index = index
    return crossed


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
