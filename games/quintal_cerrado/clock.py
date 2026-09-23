"""The garden's calendar: which day it is, and how far through the session.

The garden is turn-based, so there is no clock left to keep -- a day does
not pass, it *ends*, when the player sleeps (`turn.py`, and
`systems/day_resolver.py` for what a night does). What used to be a
seconds-to-day conversion is now just formatting.

Day count and stamina are part of the save, so Continue resumes the same
morning.
"""

from __future__ import annotations

from games.quintal_cerrado.turn import SESSION_DAYS


def format_day(day: int) -> str:
    """`"Dia 3 / 12"` for the given day.

    Args:
        day: The current day, 1-based.

    Returns:
        The label the weather card shows.
    """
    return f"Dia {day} / {SESSION_DAYS}"


def days_left(day: int) -> int:
    """How many days remain after this one, never below zero.

    Args:
        day: The current day, 1-based.

    Returns:
        Days left in the session.
    """
    return max(0, SESSION_DAYS - day)
