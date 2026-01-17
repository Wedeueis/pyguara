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

from typing import Any, Callable, Generator, Optional


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

    def __init__(self, generator: Generator[Any, None, None]):
        """Initialize coroutine.

        Args:
            generator: Generator function to execute
        """
        self._generator = generator
        self._current_instruction: Optional[WaitInstruction] = None
        self._is_complete = False
        self._nested_coroutine: Optional["Coroutine"] = None

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

            except StopIteration:
                self._is_complete = True
                return False

    def stop(self) -> None:
        """Stop the coroutine immediately."""
        self._is_complete = True
        if self._nested_coroutine:
            self._nested_coroutine.stop()

    @property
    def is_complete(self) -> bool:
        """Check if coroutine has finished."""
        return self._is_complete


class CoroutineManager:
    """Manages multiple coroutines.

    Handles starting, updating, and stopping coroutines.

    Example:
        >>> manager = CoroutineManager()
        >>> coro = manager.start_coroutine(my_sequence())
        >>> # In game loop:
        >>> manager.update(dt)
    """

    def __init__(self) -> None:
        """Initialize coroutine manager."""
        self._coroutines: list[Coroutine] = []

    def start_coroutine(self, generator: Generator[Any, None, None]) -> Coroutine:
        """Start a new coroutine.

        Args:
            generator: Generator function to run as coroutine

        Returns:
            Coroutine object that can be used to stop it
        """
        coroutine = Coroutine(generator)
        self._coroutines.append(coroutine)
        return coroutine

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
        """Update all active coroutines.

        Args:
            dt: Delta time since last frame
        """
        # Update all coroutines and remove completed ones
        self._coroutines = [coro for coro in self._coroutines if coro.update(dt)]

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
