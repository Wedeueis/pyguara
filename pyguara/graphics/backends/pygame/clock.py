"""Pygame implementation of the `Clock` frame-pacing protocol."""

from __future__ import annotations

import pygame


class PygameClock:
    """`Clock` backed by `pygame.time.Clock`.

    `tick()` blocks as needed to hold the requested frame rate and returns
    the milliseconds the previous frame took -- exactly `pygame.time.Clock`'s
    contract, which is what this abstraction was modelled on.
    """

    def __init__(self) -> None:
        """Create the wrapped `pygame.time.Clock`."""
        self._clock = pygame.time.Clock()

    def tick(self, target_fps: int = 0) -> float:
        """Cap at ``target_fps`` (0 = uncapped) and return elapsed milliseconds."""
        return float(self._clock.tick(target_fps))
