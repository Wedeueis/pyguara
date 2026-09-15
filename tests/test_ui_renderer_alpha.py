"""A translucent UI fill has to blend, not replace.

`pygame.draw` writes the destination pixel including its alpha rather than
compositing into it. On the ModernGL backend that is harmless -- the UI
surface is `SRCALPHA` and the overlay is composited with blending, so an
alpha fill works by construction. On the pygame backend the target is the
opaque display surface, so a 74% scrim landed solid black and hid the frozen
scene it was meant to dim.

Which matters because a scrim is how every modal in the design system sits
over the screen behind it.
"""

from __future__ import annotations

import pygame
import pytest

from pyguara.common.types import Color, Rect
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer


def draw_scrim_over_white(alpha: int) -> tuple[int, int, int]:
    """Fill a white surface with black at `alpha` and read the centre back.

    Args:
        alpha: The fill's alpha, 0-255.

    Returns:
        The centre pixel as an `(r, g, b)` triple.
    """
    if not pygame.get_init():
        pygame.init()
    surface = pygame.Surface((32, 32))
    surface.fill((255, 255, 255))

    PygameUIRenderer(surface).draw_rect(Rect(0, 0, 32, 32), Color(0, 0, 0, alpha))

    return tuple(surface.get_at((16, 16)))[:3]  # type: ignore[return-value]


def test_a_half_alpha_fill_dims_rather_than_covers() -> None:
    assert draw_scrim_over_white(128) == pytest.approx((127, 127, 127), abs=2)


def test_an_opaque_fill_still_covers() -> None:
    assert draw_scrim_over_white(255) == (0, 0, 0)


def test_a_fully_transparent_fill_changes_nothing() -> None:
    assert draw_scrim_over_white(0) == (255, 255, 255)


def test_an_outline_blends_too() -> None:
    """The blended path must honour `width`, not silently fill."""
    if not pygame.get_init():
        pygame.init()
    surface = pygame.Surface((32, 32))
    surface.fill((255, 255, 255))

    PygameUIRenderer(surface).draw_rect(
        Rect(0, 0, 32, 32), Color(0, 0, 0, 128), width=2
    )

    assert surface.get_at((16, 16))[:3] == (255, 255, 255)
    assert surface.get_at((0, 16))[:3] == pytest.approx((127, 127, 127), abs=2)
