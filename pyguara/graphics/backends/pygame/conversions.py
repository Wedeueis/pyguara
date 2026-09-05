"""Conversion helpers from engine value types to pygame's native types.

Only this backend ever constructs `pygame.Color`/`pygame.Rect` -- `Color`
and `Rect` (`pyguara.common.types`) are plain, backend-agnostic dataclasses,
so ModernGL never needs these. Shared between `pygame_renderer.py` and
`pygame_window.py`, both of which pass engine `Color`/`Rect` values straight
into pygame drawing calls.
"""

import pygame

from pyguara.common.types import Color, Rect


def to_pygame_color(color: Color) -> pygame.Color:
    """Convert an engine Color to a real pygame.Color."""
    return pygame.Color(color.r, color.g, color.b, color.a)


def to_pygame_rect(rect: Rect) -> pygame.Rect:
    """Convert an engine Rect to a real pygame.Rect."""
    return pygame.Rect(rect.x, rect.y, rect.width, rect.height)
