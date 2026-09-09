"""Frame-timing abstraction for the main loop.

`Application` used `pygame.time.Clock` directly, so the loop -- and therefore
every backend, ModernGL included -- depended on pygame for its frame pacing
and could not be driven deterministically in a test. `Clock` is the seam:
the pygame implementation lives under `graphics/backends/pygame/`, and
`FixedClock` gives headless runs and tests a wall-clock-free tick.

Part of issue #9 (decouple pygame from the backend-agnostic core).
"""

from __future__ import annotations

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
