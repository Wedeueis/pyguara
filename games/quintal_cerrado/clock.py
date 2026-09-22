"""The garden's clock: day count, a mm:ss readout, and how dark it is.

A session is fifteen minutes (the PRD's playable loop) split into three
five-minute days. Time only advances while the garden is actually being
played -- `scenes.GardenScene.fixed_update` adds to it, and the engine
pauses that while an overlay is up -- and it is part of the save, so
Continue resumes the same day rather than restarting the light.
"""

from __future__ import annotations

import math

DAY_LENGTH = 300.0
"""Seconds in one day."""

EVALUATION_TIME = 900.0
"""Seconds of play after which the evaluation offers itself: the PRD's 15:00."""

MAX_DARKNESS = 0.8
"""Ceiling on `darkness()`. The canvas scales it into a translucent wash, so
this is "as dark as the night gets", not an opacity."""


def day_number(elapsed: float) -> int:
    """The 1-based day `elapsed` seconds into a session falls on."""
    return int(elapsed // DAY_LENGTH) + 1


def format_clock(elapsed: float) -> str:
    """`"Day 2  07:05/15:00"` for `elapsed` seconds of play."""
    minutes, seconds = divmod(int(elapsed), 60)
    total_minutes = int(EVALUATION_TIME // 60)
    return f"Day {day_number(elapsed)}  {minutes:02d}:{seconds:02d}/{total_minutes}:00"


def darkness(elapsed: float) -> float:
    """How dark it is, 0.0 in full day and up to `MAX_DARKNESS` at midnight.

    The first half of each day is light, the second half dusk to night and
    back -- a smooth sine, so the light eases rather than snaps.

    Args:
        elapsed: Seconds of play.

    Returns:
        A value in `[0, MAX_DARKNESS]`.
    """
    phase = (elapsed % DAY_LENGTH) / DAY_LENGTH
    return MAX_DARKNESS * max(0.0, -math.sin(2 * math.pi * phase))
