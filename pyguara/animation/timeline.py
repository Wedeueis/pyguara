"""Composing tweens in sequence and in parallel.

Chaining through nested `on_complete` callbacks stops being readable past
two steps, and there is no way to say "these two at once, then that one"
at all. Combat juice is naturally a timeline -- anticipation, strike,
hitstop, knockback, recovery -- and so is a card dealing, a chest opening,
a UI screen sliding in.

    (Timeline()
        .then(wind_up)
        .wait(0.05)
        .call(spawn_hitbox)
        .parallel(knockback, screen_shake)
        .then(recover)
        .start())

A `Timeline` ticks with the same `update(dt) -> bool` contract a `Tween`
has, so `TweenManager` holds either without knowing which, and a timeline
can be a step inside another timeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class Animatable(Protocol):
    """Something a `TweenManager` can tick.

    Satisfied by `Tween` and `Timeline` alike, which is what lets a manager
    hold both and a timeline hold a timeline. Deliberately the contract
    `Tween` already had rather than a new one: `update` returning False to
    mean "done, drop me" is how the manager already decides what to remove.
    """

    def start(self) -> None:
        """Begin, or begin again from the top."""
        ...

    def stop(self) -> None:
        """Halt and reset, without firing completion callbacks."""
        ...

    def update(self, dt: float) -> bool:
        """Advance by `dt`.

        Args:
            dt: Seconds since the last call.

        Returns:
            True while still running; False once finished.
        """
        ...

    @property
    def is_complete(self) -> bool:
        """Whether this has finished."""
        ...


class _Step(ABC):
    """One entry in a timeline."""

    @abstractmethod
    def begin(self) -> None:
        """Prepare to run. Called when the timeline reaches this step."""

    @abstractmethod
    def advance(self, dt: float) -> float:
        """Run for up to `dt` seconds.

        Returns:
            The unused remainder of `dt`, in seconds, once this step has
            finished -- so a long frame can carry the leftover into the
            next step instead of throwing it away. A step still running
            returns a negative number, which is how `Timeline` tells "done
            with time to spare" from "not done".
        """

    @abstractmethod
    def halt(self) -> None:
        """Stop, because the timeline was stopped."""


_RUNNING = -1.0
"""`_Step.advance`'s "still running" return. A real remainder is >= 0."""


class _TweenStep(_Step):
    """Runs one `Animatable` to completion."""

    def __init__(self, animatable: Animatable) -> None:
        """Wrap an animatable as a step.

        Args:
            animatable: The tween or nested timeline to run.
        """
        self._animatable = animatable

    def begin(self) -> None:
        """Start the animatable from the top."""
        self._animatable.start()

    def advance(self, dt: float) -> float:
        """Tick the animatable.

        Args:
            dt: Seconds to advance by.

        Returns:
            0.0 when it finished this tick, `_RUNNING` otherwise. The
            remainder is not recovered from a tween, which does not report
            how much of the last `dt` it needed -- so a timeline's steps
            can drift by up to one frame each. Accepted deliberately: the
            alternative is making every `Tween` report its overshoot, for a
            correction smaller than the frame it would be measured in.
        """
        return 0.0 if not self._animatable.update(dt) else _RUNNING

    def halt(self) -> None:
        """Stop the animatable."""
        self._animatable.stop()


class _WaitStep(_Step):
    """Does nothing for a fixed number of seconds."""

    def __init__(self, seconds: float) -> None:
        """Create the wait.

        Args:
            seconds: How long to wait.
        """
        self._seconds = seconds
        self._elapsed = 0.0

    def begin(self) -> None:
        """Reset the clock."""
        self._elapsed = 0.0

    def advance(self, dt: float) -> float:
        """Count down.

        Args:
            dt: Seconds to advance by.

        Returns:
            The leftover time once the wait elapses, so the step after it
            starts at the right moment rather than at the next frame
            boundary. This is where carrying the remainder actually
            matters: a 0.05 s hitstop between two tweens is shorter than a
            frame at 60 Hz.
        """
        self._elapsed += dt
        overshoot = self._elapsed - self._seconds
        return overshoot if overshoot >= 0 else _RUNNING

    def halt(self) -> None:
        """Nothing to release."""
        self._elapsed = 0.0


class _CallStep(_Step):
    """Calls a function once, then finishes immediately."""

    def __init__(self, callback: Callable[[], None]) -> None:
        """Create the call step.

        Args:
            callback: Takes nothing, returns nothing.
        """
        self._callback = callback

    def begin(self) -> None:
        """Nothing: the call happens in `advance`, inside the tick."""

    def advance(self, dt: float) -> float:
        """Call the callback and pass the whole `dt` on.

        Called from `advance` rather than `begin` so the callback runs
        inside the timeline's own tick, in order with the steps around it,
        rather than at whatever moment the previous step happened to end.

        Args:
            dt: Seconds available; all of it is passed on.

        Returns:
            `dt` unchanged -- a callback takes no time.
        """
        self._callback()
        return dt

    def halt(self) -> None:
        """Nothing to release."""


class _ParallelStep(_Step):
    """Runs several animatables at once, finishing with the slowest."""

    def __init__(self, animatables: tuple[Animatable, ...]) -> None:
        """Create the parallel step.

        Args:
            animatables: The members to run together.
        """
        self._animatables = animatables
        self._running: list[Animatable] = []

    def begin(self) -> None:
        """Start every member."""
        self._running = list(self._animatables)
        for animatable in self._running:
            animatable.start()

    def advance(self, dt: float) -> float:
        """Tick every member that is still running.

        Every member gets the full `dt`, and the step finishes when the
        last one does -- "and then" after a parallel step means after all
        of it, which is the only reading that makes `parallel(a, b)`
        composable with `then(c)`.

        Args:
            dt: Seconds to advance by.

        Returns:
            0.0 when every member has finished, `_RUNNING` otherwise.
        """
        self._running = [
            animatable for animatable in self._running if animatable.update(dt)
        ]
        return _RUNNING if self._running else 0.0

    def halt(self) -> None:
        """Stop every member."""
        for animatable in self._animatables:
            animatable.stop()
        self._running = []


class Timeline:
    """A sequence of tweens, waits, callbacks and parallel groups.

    Built by chaining -- each method returns the timeline -- and run by
    `start()` plus `update(dt)` each frame, or by handing it to a
    `TweenManager`.

    Steps are composed before `start()`. Appending to a running timeline is
    allowed and the new step simply runs when reached; appending to a
    *finished* one does nothing until it is started again, which is the
    same rule a `Tween` follows.
    """

    def __init__(
        self,
        loops: int = 0,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        """Create an empty timeline.

        Args:
            loops: 0 runs once, -1 repeats forever, N repeats N extra
                times -- the same convention `Tween.loops` uses, so the two
                do not disagree about what `1` means.
            on_complete: Called once, after the last loop.
        """
        self._steps: list[_Step] = []
        self.loops = loops
        self.on_complete = on_complete
        self._index = 0
        self._loop = 0
        self._running = False
        self._complete = False

    # -- Composition --

    def then(self, animatable: Animatable) -> Timeline:
        """Append a tween (or nested timeline) to run after everything so far.

        Args:
            animatable: What to run.

        Returns:
            This timeline, for chaining.
        """
        self._steps.append(_TweenStep(animatable))
        return self

    def wait(self, seconds: float) -> Timeline:
        """Append a pause.

        Args:
            seconds: How long to wait. Must not be negative.

        Returns:
            This timeline, for chaining.

        Raises:
            ValueError: If `seconds` is negative, which would make the step
                finish before it began and silently swallow the one after
                it in the same frame.
        """
        if seconds < 0:
            raise ValueError(f"wait() needs a non-negative duration, got {seconds}.")
        self._steps.append(_WaitStep(seconds))
        return self

    def call(self, callback: Callable[[], None]) -> Timeline:
        """Append a callback, run in order with the steps around it.

        Args:
            callback: Takes nothing, returns nothing.

        Returns:
            This timeline, for chaining.
        """
        self._steps.append(_CallStep(callback))
        return self

    def parallel(self, *animatables: Animatable) -> Timeline:
        """Append a group that runs together and finishes with the slowest.

        Args:
            *animatables: The members. One is legal and equivalent to
                `then()`; none is a no-op step.

        Returns:
            This timeline, for chaining.
        """
        self._steps.append(_ParallelStep(animatables))
        return self

    # -- Playback --

    @property
    def step_count(self) -> int:
        """How many steps have been appended."""
        return len(self._steps)

    @property
    def current_step(self) -> int:
        """Index of the step now running, or `step_count` once finished."""
        return self._index

    @property
    def is_complete(self) -> bool:
        """Whether the timeline has finished every loop."""
        return self._complete

    @property
    def is_playing(self) -> bool:
        """Whether the timeline is running."""
        return self._running

    def start(self) -> Timeline:
        """Start, or restart from the first step.

        Returns:
            This timeline, so `Timeline().then(t).start()` reads as one
            expression.
        """
        self._index = 0
        self._loop = 0
        self._complete = False
        self._running = bool(self._steps)
        if self._running:
            self._steps[0].begin()
        else:
            # An empty timeline is complete, not stuck: a game building one
            # from a filtered list of effects should not hang when the
            # filter happens to match nothing.
            self._complete = True
        return self

    def stop(self) -> None:
        """Halt immediately, without firing `on_complete`.

        Every step is halted, not only the current one, so a parallel group
        that was interrupted does not leave its members running.
        """
        for step in self._steps:
            step.halt()
        self._running = False
        self._complete = False
        self._index = 0
        self._loop = 0

    def update(self, dt: float) -> bool:
        """Advance the timeline by `dt`.

        A step that finishes with time left over hands the remainder to the
        next one in the *same* call, so a chain of short waits does not
        take one frame each -- five 1 ms callbacks in a timeline would
        otherwise take 83 ms at 60 Hz.

        A step that takes *no* time -- a callback, an empty parallel group,
        a zero wait -- also runs in the same call, even with nothing left
        over. Otherwise `then(tween).call(spawn_hitbox)` fires the callback
        one frame after the tween it belongs to, which is exactly the kind
        of off-by-one-frame that makes a combat timeline feel loose.

        At most one full pass over the steps happens per call. Without that
        bound, a looping timeline of nothing but instant steps would spin
        here forever instead of merely misbehaving.

        Args:
            dt: Seconds since the last call.

        Returns:
            True while still running, False once finished -- the contract
            `TweenManager` uses to decide what to drop.
        """
        if not self._running:
            return False

        remaining = dt
        budget = len(self._steps) + 1
        while budget > 0:
            budget -= 1
            leftover = self._steps[self._index].advance(remaining)
            if leftover < 0:
                return True

            remaining = leftover
            if not self._advance_index():
                return False

        return True

    def _advance_index(self) -> bool:
        """Move to the next step, looping or completing at the end.

        Reports back rather than letting the caller re-read
        `self._running`: an attribute a method just changed is exactly what
        a type checker cannot follow, and the answer is this method's to
        give.

        Returns:
            True if a step is now current, False if the timeline finished.
        """
        self._index += 1
        if self._index < len(self._steps):
            self._steps[self._index].begin()
            return True

        if self.loops == -1 or self._loop < self.loops:
            self._loop += 1
            self._index = 0
            self._steps[0].begin()
            return True

        self._running = False
        self._complete = True
        if self.on_complete:
            self.on_complete()
        return False
