"""Coroutine-based scripting system.

Allows writing sequential game logic that can be paused and resumed,
similar to Unity's coroutines.

Example:
    >>> def my_sequence():
    ...     print("Start")
    ...     yield wait_for_seconds(1.0)
    ...     print("After 1 second")
    ...     yield wait_for_seconds(2.0)
    ...     print("After 3 seconds total")
    >>>
    >>> manager = CoroutineManager()
    >>> manager.start_coroutine(my_sequence())
    >>> # In game loop:
    >>> manager.update(dt)
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from pyguara.errors import ErrorHandlingStrategy
from pyguara.log import get_logger

logger = get_logger(__name__)


class WaitInstruction:
    """Base class for yield instructions."""

    def is_complete(self, dt: float) -> bool:
        """Check if wait condition is satisfied.

        Args:
            dt: Delta time since last frame

        Returns:
            True if waiting is done
        """
        return True


class FixedStepTicker:
    """A count of fixed-timestep steps, so a sequence can wait on one.

    The coroutine manager is ticked from the variable-rate update, so a
    sequence has no inherent notion of the fixed step. This is the shared
    counter that bridges them: the engine advances it from
    `Application._fixed_update`, and `WaitForFixedUpdate` watches it.

    A counter rather than a flag, so two instructions created in the same
    frame both see the next step rather than racing to consume one signal.
    """

    __slots__ = ("count",)

    def __init__(self) -> None:
        """Start at zero."""
        self.count = 0

    def advance(self) -> None:
        """Record one fixed step."""
        self.count += 1


_DEFAULT_FIXED_TICKER = FixedStepTicker()
"""The ticker used unless one is injected.

Module-level because the fixed step is a genuinely global property of the
frame loop, in the same spirit as `get_theme()` -- and injectable at both
ends so a test does not have to reach for it.
"""


class WaitForFrames(WaitInstruction):
    """Wait a fixed number of update ticks.

    The frame-count primitive that was missing: only time and predicate
    waits existed, so "skip a frame so the thing I just spawned has been
    laid out" had to be spelled as a `WaitForSeconds` guess.

    Counts the ticks on which the instruction is *examined*, so
    `WaitForFrames(1)` resumes on the next update rather than the current
    one.
    """

    def __init__(self, frames: int) -> None:
        """Initialize the wait.

        Args:
            frames: How many updates to wait. Zero or negative completes on
                the first check, which is what "wait no frames" should mean
                rather than an error.
        """
        self.frames = frames
        self._remaining = frames

    def is_complete(self, dt: float) -> bool:
        """Count down one update.

        Args:
            dt: Unused; this instruction is frame-counted, not timed.

        Returns:
            True once the requested number of updates has passed.
        """
        self._remaining -= 1
        return self._remaining <= 0


class WaitForFixedUpdate(WaitInstruction):
    """Wait until the next fixed-timestep step.

    What a sequence needs to line up with physics: the coroutine manager
    runs on the variable-rate update, so before this there was no way to
    synchronise a scripted sequence with the fixed step at all.

    Requires the engine to be advancing the ticker --
    `Application._fixed_update` does. In a bare harness that never calls
    `CoroutineManager.notify_fixed_update()`, this never completes, which
    is the honest behaviour: the step it waits for is not happening.
    """

    def __init__(self, ticker: FixedStepTicker | None = None) -> None:
        """Initialize the wait.

        Args:
            ticker: The counter to watch. Defaults to the engine-wide one.
        """
        self._ticker = ticker or _DEFAULT_FIXED_TICKER
        self._start = self._ticker.count

    def is_complete(self, dt: float) -> bool:
        """Whether a fixed step has elapsed since this instruction began.

        Args:
            dt: Unused; this instruction is step-counted, not timed.

        Returns:
            True once the ticker has advanced.
        """
        return self._ticker.count > self._start


class WaitForSeconds(WaitInstruction):
    """Wait for a specified duration.

    Example:
        >>> yield WaitForSeconds(2.5)  # Wait 2.5 seconds
    """

    def __init__(self, duration: float):
        """Initialize wait instruction.

        Args:
            duration: Time to wait in seconds
        """
        self.duration = duration
        self._elapsed = 0.0

    def is_complete(self, dt: float) -> bool:
        """Check if duration has elapsed."""
        self._elapsed += dt
        return self._elapsed >= self.duration


class WaitUntil(WaitInstruction):
    """Wait until a condition becomes true.

    Example:
        >>> yield WaitUntil(lambda: player.health < 50)
    """

    def __init__(self, condition: Callable[[], bool]):
        """Initialize wait instruction.

        Args:
            condition: Callable that returns True when done waiting
        """
        self.condition = condition

    def is_complete(self, dt: float) -> bool:
        """Check if condition is true."""
        return self.condition()


class WaitWhile(WaitInstruction):
    """Wait while a condition remains true.

    Example:
        >>> yield WaitWhile(lambda: enemy.is_alive)
    """

    def __init__(self, condition: Callable[[], bool]):
        """Initialize wait instruction.

        Args:
            condition: Callable that returns True to keep waiting
        """
        self.condition = condition

    def is_complete(self, dt: float) -> bool:
        """Check if condition is false."""
        return not self.condition()


class Coroutine:
    """Wrapper for a coroutine generator.

    Manages the execution state of a generator-based coroutine.
    """

    def __init__(
        self,
        generator: Generator[Any, None, None],
        owner: Any = None,
    ):
        """Initialize coroutine.

        Args:
            generator: Generator function to execute
            owner: Arbitrary tag identifying what this sequence belongs to
                -- an entity id, a scene, a system. `CoroutineManager.stop_by`
                takes the same value. Compared by equality, so anything
                hashable or comparable works.
        """
        self._generator = generator
        self._current_instruction: WaitInstruction | None = None
        self._is_complete = False
        self._nested_coroutine: Coroutine | None = None
        self.owner = owner
        self._result: Any = None
        self._on_complete: list[Callable[[Coroutine], None]] = []

    @property
    def done(self) -> bool:
        """Whether this sequence has finished, by completion or by `stop()`."""
        return self._is_complete

    @property
    def result(self) -> Any:
        """What the generator returned, once it has finished.

        A generator's `return value` reaches its caller as
        `StopIteration.value`, which this used to catch and discard -- so a
        fire-and-forget sequence had no way to report anything back. None
        until `done`, and None for a sequence that was stopped rather than
        allowed to finish.
        """
        return self._result

    def on_complete(self, callback: Callable[[Coroutine], None]) -> None:
        """Register a callback for when this sequence finishes.

        Called once, with this coroutine, whether it ran to completion or
        was stopped -- a caller waiting on a sequence needs to hear about
        either. Read `result` to tell them apart.

        Args:
            callback: Called with this coroutine when it finishes.
        """
        if self._is_complete:
            # Already finished; a late subscriber still gets told rather
            # than waiting for an event that cannot come.
            callback(self)
            return
        self._on_complete.append(callback)

    def _finish(self, result: Any = None) -> None:
        """Mark finished and notify subscribers exactly once.

        Args:
            result: The generator's return value, if it returned one.
        """
        if self._is_complete:
            return
        self._is_complete = True
        self._result = result
        callbacks, self._on_complete = self._on_complete, []
        for callback in callbacks:
            callback(self)

    def update(self, dt: float) -> bool:
        """Update the coroutine.

        Args:
            dt: Delta time since last frame

        Returns:
            True if coroutine is still running, False if complete
        """
        if self._is_complete:
            return False

        # Update nested coroutine if active
        if self._nested_coroutine:
            still_running = self._nested_coroutine.update(dt)
            if still_running:
                return True
            # Nested coroutine finished, continue parent in same update
            self._nested_coroutine = None
            # Fall through to continue executing

        # Check current wait instruction
        if self._current_instruction:
            if not self._current_instruction.is_complete(dt):
                return True
            # Wait is done, clear it and continue
            self._current_instruction = None
            # Don't return yet - continue executing

        # Resume generator (may execute multiple times in one frame)
        while True:
            try:
                yielded = next(self._generator)

                # Handle what was yielded
                if isinstance(yielded, WaitInstruction):
                    self._current_instruction = yielded
                    return True
                elif isinstance(yielded, Coroutine):
                    self._nested_coroutine = yielded
                    # Start nested coroutine immediately
                    still_running = self._nested_coroutine.update(dt)
                    if still_running:
                        return True
                    # Nested completed immediately, continue loop
                    self._nested_coroutine = None
                elif isinstance(yielded, Generator):
                    # Auto-wrap generator in Coroutine
                    self._nested_coroutine = Coroutine(yielded)
                    # Start nested coroutine immediately
                    still_running = self._nested_coroutine.update(dt)
                    if still_running:
                        return True
                    # Nested completed immediately, continue loop
                    self._nested_coroutine = None
                else:
                    # None or other values: pause until next frame
                    return True

            except StopIteration as stop:
                # `.value` is the generator's `return`, which this used to
                # throw away -- the reason a sequence could not report a
                # result (#55).
                self._finish(stop.value)
                return False

    def stop(self) -> None:
        """Stop the coroutine immediately.

        Closes the underlying generator, so any ``finally`` blocks or
        context managers open inside the scripted sequence run their
        cleanup now rather than whenever the generator is garbage
        collected. Idempotent, and never raises: a generator that swallows
        the injected ``GeneratorExit`` (by yielding again) is reported and
        left for the garbage collector.
        """
        # Marked finished first, so `done` is true for any `on_complete`
        # subscriber this notifies and a stopped sequence cannot be
        # mistaken for a running one mid-teardown. `result` stays None,
        # which is how a caller tells "stopped" from "returned".
        self._finish(None)
        if self._nested_coroutine:
            self._nested_coroutine.stop()
            self._nested_coroutine = None
        self._current_instruction = None
        closer = getattr(self._generator, "close", None)
        if closer is None:
            return
        if getattr(self._generator, "gi_running", False):
            # stop() called from inside this coroutine's own body: the frame
            # is live on our stack and cannot be closed now. It is flagged
            # complete and dropped next frame; its finally-blocks run at GC.
            return
        try:
            closer()
        except RuntimeError as exc:
            # generator ignored GeneratorExit and yielded again
            logger.exception(exc, "Coroutine generator refused to close on stop()")

    @property
    def is_complete(self) -> bool:
        """Check if coroutine has finished."""
        return self._is_complete


class CoroutineManager:
    """Manages multiple coroutines.

    Handles starting, updating, and stopping coroutines.

    A scripted sequence that raises is contained: it is stopped and reported
    according to ``error_strategy``, and the other coroutines still run this
    frame. Coroutines may safely start or stop coroutines (including
    themselves) from inside their own body during ``update()``.

    Example:
        >>> manager = CoroutineManager()
        >>> coro = manager.start_coroutine(my_sequence())
        >>> # In game loop:
        >>> manager.update(dt)
    """

    def __init__(
        self,
        error_strategy: ErrorHandlingStrategy = ErrorHandlingStrategy.RAISE,
    ) -> None:
        """Initialize coroutine manager.

        Args:
            error_strategy: What to do when a coroutine body raises. ``RAISE``
                (the default, matching ``EventDispatcher`` and ``DIContainer``)
                logs the traceback and re-raises after stopping the offender;
                ``LOG`` logs and carries on; ``IGNORE`` drops it silently.
        """
        self._coroutines: list[Coroutine] = []
        self._error_strategy = error_strategy
        self._fixed_ticker = _DEFAULT_FIXED_TICKER

    def start_coroutine(
        self,
        generator: Generator[Any, None, None],
        owner: Any = None,
    ) -> Coroutine:
        """Start a new coroutine.

        Args:
            generator: Generator function to run as coroutine
            owner: Tag identifying what this sequence belongs to -- an
                entity id, a scene, a system. `stop_by(owner)` then stops
                the whole group, which is what a despawning enemy or an
                exiting scene needs. Untagged coroutines are never caught
                by `stop_by`.

        Returns:
            Coroutine object that can be used to stop it
        """
        coroutine = Coroutine(generator, owner=owner)
        self._coroutines.append(coroutine)
        return coroutine

    def stop_by(self, owner: Any) -> int:
        """Stop every coroutine tagged with `owner`.

        The answer to both of #55's P1 rows with one mechanism. A killed
        enemy's scripted attack pattern used to keep running against a
        despawned entity, and a sequence started in one scene kept ticking
        in the next -- because nothing could name a group to tear down.

        `owner=None` stops nothing, deliberately: that is the untagged
        default, and treating it as "stop everything anonymous" would make
        a missing argument quietly destructive. Use `stop_all()` to mean
        all.

        Args:
            owner: The tag to match, by equality.

        Returns:
            How many coroutines were stopped.
        """
        if owner is None:
            return 0

        matched = [c for c in self._coroutines if c.owner == owner]
        for coroutine in matched:
            coroutine.stop()
        # Rebuilt rather than removed in a loop, so this is safe to call
        # from inside a coroutine body during `update()` -- the same reason
        # `update()` iterates a snapshot.
        self._coroutines = [c for c in self._coroutines if c.owner != owner]
        return len(matched)

    def notify_fixed_update(self) -> None:
        """Record that a fixed-timestep step has elapsed.

        Called from the engine's fixed update. The coroutine manager is
        ticked from the *variable*-rate update, so without this there is no
        way for a sequence to sync to the fixed step at all -- which is
        what `WaitForFixedUpdate` needs, and why physics-adjacent scripting
        had no primitive to wait on.
        """
        self._fixed_ticker.advance()

    @property
    def fixed_ticker(self) -> FixedStepTicker:
        """The ticker `WaitForFixedUpdate` instructions should watch."""
        return self._fixed_ticker

    def stop_coroutine(self, coroutine: Coroutine) -> bool:
        """Stop a specific coroutine.

        Args:
            coroutine: Coroutine to stop

        Returns:
            True if coroutine was found and stopped
        """
        if coroutine in self._coroutines:
            coroutine.stop()
            self._coroutines.remove(coroutine)
            return True
        return False

    def stop_all(self) -> None:
        """Stop all active coroutines."""
        for coroutine in self._coroutines:
            coroutine.stop()
        self._coroutines.clear()

    def update(self, dt: float) -> None:
        """Update all active coroutines, dropping the ones that finish.

        Iterates a snapshot taken at frame start, so a coroutine that starts
        or stops coroutines from inside its own body does not corrupt the
        pass: a coroutine stopped mid-frame is skipped, and one started
        mid-frame is carried forward untouched (it first runs next frame).

        Args:
            dt: Delta time since last frame
        """
        snapshot = list(self._coroutines)
        survivors: list[Coroutine] = []
        visited = 0
        try:
            for coro in snapshot:
                visited += 1
                if coro not in self._coroutines:
                    continue  # stopped mid-frame by an earlier coroutine
                try:
                    still_running = coro.update(dt)
                except Exception:  # noqa: BLE001 - user script; strategy decides
                    coro.stop()
                    if self._reraise_coroutine_error(coro):
                        raise
                    still_running = False
                if still_running and coro in self._coroutines:
                    survivors.append(coro)
        finally:
            # Rebuild the live list so it survives a mid-frame re-raise: the
            # coroutines already kept, then snapshot entries the loop never
            # reached (RAISE aborted it) that are still live, then any started
            # during this pass (absent from the snapshot).
            unvisited = [c for c in snapshot[visited:] if c in self._coroutines]
            started_this_pass = [c for c in self._coroutines if c not in snapshot]
            # A late stop_all()/stop_coroutine() from inside a coroutine body
            # can have flagged an already-kept coroutine complete; drop those.
            self._coroutines = [
                c
                for c in (*survivors, *unvisited, *started_this_pass)
                if not c.is_complete
            ]

    def _reraise_coroutine_error(self, coroutine: Coroutine) -> bool:
        """Report a coroutine that raised; return True if it must propagate.

        Args:
            coroutine: The coroutine whose body raised (already stopped).

        Returns:
            True when ``error_strategy`` is ``RAISE`` and the caller should
            re-raise the active exception, False when it was handled here.
        """
        if self._error_strategy is ErrorHandlingStrategy.IGNORE:
            return False
        logger.error(
            "Coroutine raised and was stopped",
            exc_info=True,
            active_coroutines=len(self._coroutines),
        )
        return self._error_strategy is ErrorHandlingStrategy.RAISE

    @property
    def active_count(self) -> int:
        """Get number of active coroutines."""
        return len(self._coroutines)

    @property
    def active_coroutines(self) -> list[Coroutine]:
        """Get list of active coroutines (copy)."""
        return self._coroutines.copy()


# Convenience functions


def wait_for_seconds(duration: float) -> WaitForSeconds:
    """Create a WaitForSeconds instruction.

    Args:
        duration: Time to wait in seconds

    Returns:
        WaitForSeconds instruction

    Example:
        >>> yield wait_for_seconds(2.0)
    """
    return WaitForSeconds(duration)


def wait_for_frames(frames: int) -> WaitForFrames:
    """Wait a number of update ticks.

    Args:
        frames: How many updates to wait.

    Returns:
        The instruction to yield.
    """
    return WaitForFrames(frames)


def wait_for_fixed_update(
    ticker: FixedStepTicker | None = None,
) -> WaitForFixedUpdate:
    """Wait until the next fixed-timestep step.

    Args:
        ticker: The counter to watch; defaults to the engine-wide one.

    Returns:
        The instruction to yield.
    """
    return WaitForFixedUpdate(ticker)


def wait_until(condition: Callable[[], bool]) -> WaitUntil:
    """Create a WaitUntil instruction.

    Args:
        condition: Callable that returns True when done waiting

    Returns:
        WaitUntil instruction

    Example:
        >>> yield wait_until(lambda: player.position.x > 100)
    """
    return WaitUntil(condition)


def wait_while(condition: Callable[[], bool]) -> WaitWhile:
    """Create a WaitWhile instruction.

    Args:
        condition: Callable that returns True to keep waiting

    Returns:
        WaitWhile instruction

    Example:
        >>> yield wait_while(lambda: enemy.is_alive)
    """
    return WaitWhile(condition)
