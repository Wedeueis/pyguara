"""Frame-timing abstraction for the main loop.

`Clock` is the protocol `Application` paces its loop with. `WallClock`
and the pygame implementation under `graphics/backends/pygame/` follow
real time; `FixedClock` gives headless runs and tests a tick that does
not depend on it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """A frame-pacing clock.

    Modelled on `pygame.time.Clock` so the real implementation is a thin
    wrapper: `tick()` both throttles the caller and reports elapsed time.
    """

    def tick(self, target_fps: int = 0) -> float:
        """Advance one frame and return the time the previous frame took.

        Args:
            target_fps: Frames per second to cap at. ``0`` means no cap --
                return immediately. A real clock sleeps as needed to hold
                the rate; a deterministic one never sleeps.

        Returns:
            Milliseconds elapsed since the previous ``tick()`` call. The
            caller divides by 1000 for seconds.
        """
        ...


class FixedClock:
    """A `Clock` that never sleeps and always reports the same frame time.

    For headless runs and tests: the loop advances by a fixed, reproducible
    delta regardless of how long the frame actually took.
    """

    def __init__(self, frame_time_ms: float = 1000.0 / 60.0) -> None:
        """Create a clock whose every `tick()` reports ``frame_time_ms``."""
        self._frame_time_ms = frame_time_ms

    def tick(self, target_fps: int = 0) -> float:
        """Return the fixed frame time. ``target_fps`` is ignored."""
        return self._frame_time_ms


class WallClock:
    """A `Clock` on the system's monotonic timer, with no pygame in it.

    `tick()` sleeps out whatever is left of the frame and reports the
    whole of it, sleep included, as `pygame.time.Clock` does. It sleeps
    rather than spinning, so a frame may run a millisecond long.

    The time is not rounded to whole milliseconds.
    """

    def __init__(
        self,
        now: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Start timing from now.

        Args:
            now: Seconds on a monotonic timer. Replaceable for tests.
            sleep: Blocks for a number of seconds. Replaceable for tests.
        """
        self._now = now
        self._sleep = sleep
        self._last = now()

    def tick(self, target_fps: int = 0) -> float:
        """Cap at ``target_fps`` (0 = uncapped) and return elapsed milliseconds."""
        if target_fps > 0:
            remaining = 1.0 / target_fps - (self._now() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        current = self._now()
        elapsed = current - self._last
        self._last = current
        return elapsed * 1000.0
