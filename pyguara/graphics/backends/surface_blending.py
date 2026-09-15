"""Blending a translucent shape onto a pygame surface.

Both UI renderers draw through `pygame.draw`, which **replaces** the
destination pixel including its alpha rather than compositing into it. The
consequence differs per backend and neither is what anyone wants:

- on an opaque surface (the pygame backend's display) a 74% scrim lands
  solid black and hides the frame it was meant to dim;
- on an `SRCALPHA` surface (the ModernGL backend's UI overlay) the same
  call punches a **hole** -- a ghost button with a transparent fill erased
  the panel it was sitting on and showed the world through it.

Blitting composites instead, so both backends share this one path.
"""

from __future__ import annotations

import pygame


def blit_blended_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    rgba: tuple[int, int, int, int],
    width: int,
    border_radius: int,
) -> None:
    """Draw `rgba` into a scratch surface and blit it, so the alpha blends.

    Args:
        surface: Destination.
        rect: Destination rectangle, in surface coordinates.
        rgba: The colour, with an alpha below 255.
        width: Outline width; 0 fills.
        border_radius: Corner radius.
    """
    if rect.width <= 0 or rect.height <= 0:
        return

    scratch = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(
        scratch,
        rgba,
        pygame.Rect(0, 0, rect.width, rect.height),
        width,
        border_radius=border_radius,
    )
    surface.blit(scratch, rect.topleft)
