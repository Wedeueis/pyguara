"""Screen shake: several overlapping impulses summed into one offset.

`CameraShake` is a single decaying impulse. Real feedback overlaps -- a
kill lands while the previous explosion is still settling -- and running
one shake at a time means the second impact either cuts the first short or
is swallowed by it. `Shaker` keeps every live impulse and sums them.

The result is a plain pixel offset, which is deliberate: a scene drawing
in world space adds it to the camera position, and one drawing in screen
space adds it to what it draws. Neither has to own a camera to shake.
"""

from __future__ import annotations

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import CameraShake


class Shaker:
    """Several overlapping camera shakes, summed into one offset."""

    def __init__(self, rng: RandomStream | None = None) -> None:
        """Start still.

        Args:
            rng: Random stream driving shake direction, shared by every
                shake this adds.
        """
        self._shakes: list[CameraShake] = []
        self._rng = rng if rng is not None else RandomStream()
        self._offset = Vector2.zero()

    @property
    def offset(self) -> Vector2:
        """The current shake offset, in pixels."""
        return self._offset

    def add(self, magnitude: float, duration: float = 0.25) -> None:
        """Start another shake on top of whatever is already running.

        Args:
            magnitude: Peak offset in pixels; decays linearly to zero.
            duration: Seconds the shake lasts.
        """
        if magnitude <= 0.0:
            return
        self._shakes.append(
            CameraShake(duration=duration, magnitude=magnitude, rng=self._rng)
        )

    def update(self, dt: float) -> Vector2:
        """Advance every live shake and return their combined offset.

        Args:
            dt: Seconds since the last frame.

        Returns:
            The offset to add to everything drawn this frame.
        """
        total = Vector2.zero()
        still_running = []
        for shake in self._shakes:
            offset = shake.update(dt)
            if shake.elapsed < shake.duration:
                still_running.append(shake)
                total = total + offset
        self._shakes = still_running
        self._offset = total
        return total
