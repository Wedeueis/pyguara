"""Tween system for animating values over time."""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union
from enum import Enum, auto

from pyguara.animation.easing import EasingType, ease


class TweenState(Enum):
    """State of a tween animation."""

    IDLE = auto()
    PLAYING = auto()
    PAUSED = auto()
    COMPLETE = auto()


@dataclass
class Tween:
    """Animates a value from start to end over a duration.

    Supports different easing functions, delays, loops, and callbacks.

    Example:
        >>> # Animate position from (0, 0) to (100, 50) over 1 second
        >>> tween = Tween(
        ...     start_value=(0.0, 0.0),
        ...     end_value=(100.0, 50.0),
        ...     duration=1.0,
        ...     easing=EasingType.EASE_OUT_QUAD
        ... )
        >>> tween.start()
        >>> # In update loop:
        >>> tween.update(dt)
        >>> position = tween.current_value
    """

    start_value: Union[float, tuple[float, ...]]
    end_value: Union[float, tuple[float, ...]]
    duration: float
    easing: EasingType = EasingType.LINEAR
    delay: float = 0.0
    loops: int = 0  # 0 = no loop, -1 = infinite, N = loop N times
    yoyo: bool = False  # If True, alternate between start/end on loops
    on_update: Optional[Callable[[Any], None]] = None
    on_complete: Optional[Callable[[], None]] = None

    # Runtime state (not part of init)
    state: TweenState = field(default=TweenState.IDLE, init=False)
    elapsed: float = field(default=0.0, init=False)
    current_loop: int = field(default=0, init=False)
    is_reverse: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.duration <= 0:
            raise ValueError("Duration must be positive")

        # Ensure start and end have same structure
        if isinstance(self.start_value, tuple) != isinstance(self.end_value, tuple):
            raise ValueError(
                "start_value and end_value must both be float or both be tuple"
            )

        if isinstance(self.start_value, tuple) and isinstance(self.end_value, tuple):
            if len(self.start_value) != len(self.end_value):
                raise ValueError(
                    "start_value and end_value tuples must have same length"
                )

    def start(self) -> None:
        """Start or restart the tween."""
        self.state = TweenState.PLAYING
        self.elapsed = 0.0
        self.current_loop = 0
        self.is_reverse = False

    def pause(self) -> None:
        """Pause the tween."""
        if self.state == TweenState.PLAYING:
            self.state = TweenState.PAUSED

    def resume(self) -> None:
        """Resume a paused tween."""
        if self.state == TweenState.PAUSED:
            self.state = TweenState.PLAYING

    def stop(self) -> None:
        """Stop and reset the tween."""
        self.state = TweenState.IDLE
        self.elapsed = 0.0
        self.current_loop = 0
        self.is_reverse = False

    def update(self, dt: float) -> bool:
        """Update the tween.

        Args:
            dt: Delta time in seconds

        Returns:
            True if tween is still playing, False if complete
        """
        if self.state != TweenState.PLAYING:
            return self.state != TweenState.COMPLETE

        self.elapsed += dt

        # Handle delay
        if self.elapsed < self.delay:
            return True

        # Calculate progress
        time_in_tween = self.elapsed - self.delay
        progress = min(time_in_tween / self.duration, 1.0)

        # Apply easing
        eased = ease(progress, self.easing)

        # Calculate current value
        if self.is_reverse:
            # Interpolate from end to start
            self._interpolate(1.0 - eased)
        else:
            # Interpolate from start to end
            self._interpolate(eased)

        # Call update callback
        if self.on_update:
            self.on_update(self.current_value)

        # Check for completion
        if progress >= 1.0:
            self._handle_completion()

        return self.state == TweenState.PLAYING

    def _interpolate(self, t: float) -> None:
        """Interpolate between start and end values."""
        if isinstance(self.start_value, tuple) and isinstance(self.end_value, tuple):
            # Tuple interpolation
            self.current_value = tuple(
                self.start_value[i] + (self.end_value[i] - self.start_value[i]) * t
                for i in range(len(self.start_value))
            )
        else:
            # Scalar interpolation
            # At this point both must be floats due to validation in __post_init__
            assert isinstance(self.start_value, float)
            assert isinstance(self.end_value, float)
            self.current_value = (
                self.start_value + (self.end_value - self.start_value) * t
            )

    def _handle_completion(self) -> None:
        """Handle tween completion and looping."""
        # Check if we should loop
        if self.loops == -1 or self.current_loop < self.loops:
            self.current_loop += 1

            if self.yoyo:
                # Reverse direction
                self.is_reverse = not self.is_reverse
            else:
                # Reset to start
                self.is_reverse = False

            # Reset elapsed time (keep any overshoot)
            overshoot = self.elapsed - (self.delay + self.duration)
            self.elapsed = self.delay + overshoot

        else:
            # Complete
            self.state = TweenState.COMPLETE
            if self.on_complete:
                self.on_complete()

    @property
    def current_value(self) -> Union[float, tuple[float, ...]]:
        """Get the current interpolated value."""
        if not hasattr(self, "_current_value"):
            self._current_value = self.start_value
        return self._current_value

    @current_value.setter
    def current_value(self, value: Union[float, tuple[float, ...]]) -> None:
        """Set the current interpolated value."""
        self._current_value = value

    @property
    def progress(self) -> float:
        """Get normalized progress [0, 1]."""
        if self.state == TweenState.IDLE:
            return 0.0
        if self.state == TweenState.COMPLETE:
            return 1.0

        if self.elapsed < self.delay:
            return 0.0

        return min((self.elapsed - self.delay) / self.duration, 1.0)

    @property
    def is_complete(self) -> bool:
        """Check if tween is complete."""
        return self.state == TweenState.COMPLETE

    @property
    def is_playing(self) -> bool:
        """Check if tween is playing."""
        return self.state == TweenState.PLAYING


class TweenManager:
    """Manages multiple tweens.

    Automatically updates all active tweens and removes completed ones.

    Example:
        >>> manager = TweenManager()
        >>> tween = Tween(start_value=0.0, end_value=100.0, duration=1.0)
        >>> manager.add(tween)
        >>> tween.start()
        >>>
        >>> # In game loop:
        >>> manager.update(dt)
    """

    def __init__(self) -> None:
        """Initialize tween manager."""
        self._tweens: list[Tween] = []

    def add(self, tween: Tween) -> Tween:
        """Add a tween to the manager.

        Args:
            tween: Tween to manage

        Returns:
            The tween (for chaining)
        """
        self._tweens.append(tween)
        return tween

    def remove(self, tween: Tween) -> bool:
        """Remove a tween from the manager.

        Args:
            tween: Tween to remove

        Returns:
            True if tween was removed, False if not found
        """
        try:
            self._tweens.remove(tween)
            return True
        except ValueError:
            return False

    def update(self, dt: float) -> None:
        """Update all active tweens.

        Args:
            dt: Delta time in seconds
        """
        # Update all tweens
        for tween in self._tweens[:]:  # Copy list to allow removal during iteration
            if not tween.update(dt):
                # Tween is complete, remove it
                self._tweens.remove(tween)

    def clear(self) -> None:
        """Remove all tweens."""
        self._tweens.clear()

    def pause_all(self) -> None:
        """Pause all playing tweens."""
        for tween in self._tweens:
            tween.pause()

    def resume_all(self) -> None:
        """Resume all paused tweens."""
        for tween in self._tweens:
            tween.resume()

    def stop_all(self) -> None:
        """Stop all tweens."""
        for tween in self._tweens:
            tween.stop()
        self.clear()

    @property
    def tween_count(self) -> int:
        """Get number of active tweens."""
        return len(self._tweens)

    @property
    def active_tweens(self) -> list[Tween]:
        """Get list of all active tweens."""
        return self._tweens.copy()
