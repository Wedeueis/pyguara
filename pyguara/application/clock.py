"""Frame-timing abstraction for the main loop.

`Application` used `pygame.time.Clock` directly, so the loop -- and therefore
every backend, ModernGL included -- depended on pygame for its frame pacing
and could not be driven deterministically in a test. `Clock` is the seam:
the pygame implementation lives under `graphics/backends/pygame/`, and
`FixedClock` gives headless runs and tests a wall-clock-free tick.

Part of issue #9 (decouple pygame from the backend-agnostic core).
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

    `pygame.time.Clock`'s contract, which `PygameClock` wraps, kept for the
    wgpu backend: `tick()` sleeps out whatever is left of the frame and
    reports the whole of it, sleep included. It sleeps rather than spinning,
    as pygame's `tick` does -- a frame may run a millisecond long, which a
    game cannot see and a laptop battery can.

    Unlike pygame's, the time is not rounded to whole milliseconds: a 60 Hz
    frame is 16.67 ms, and reporting 16 or 17 alternately is jitter the
    game's interpolation then has to absorb.
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
