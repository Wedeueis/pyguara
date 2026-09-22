"""Blending a translucent shape onto a pygame surface.

Both UI renderers draw through `pygame.draw`, which **replaces** the
destination pixel including its alpha rather than compositing into it. The
consequence differs per backend and neither is what anyone wants:

- on an opaque surface (the pygame backend's display) a 74% scrim lands
  solid black and hides the frame it was meant to dim;
- on an `SRCALPHA` surface (the ModernGL backend's UI overlay) the same
  call punches a **hole** -- a ghost button with a transparent fill erased
  the panel it was sitting on and showed the world through it.

Blitting composites instead, so both backends share this one path. Every
primitive goes through it -- rects, circles, lines and polygons -- not
rects alone: a translucent glow ring or a faded icon is exactly as much a
hole-puncher as a scrim is.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

RGBA = tuple[int, int, int, int]


def blit_blended(
    surface: pygame.Surface,
    bounds: pygame.Rect,
    draw: Callable[[pygame.Surface, tuple[int, int]], None],
) -> None:
    """Run `draw` on a scratch surface covering `bounds`, then blit it.

    Args:
        surface: Destination.
        bounds: The region the shape can touch, in surface coordinates.
            Clipped to `surface`, so an off-screen shape costs nothing.
        draw: Draws the shape onto the scratch surface. It receives the
            scratch surface and the `(dx, dy)` to add to every
            destination-space coordinate it draws at.
    """
    clipped = bounds.clip(surface.get_rect())
    if clipped.width <= 0 or clipped.height <= 0:
        return
    scratch = pygame.Surface(clipped.size, pygame.SRCALPHA)
    draw(scratch, (-clipped.x, -clipped.y))
    surface.blit(scratch, clipped.topleft)


def blit_blended_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    rgba: RGBA,
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


def blit_blended_circle(
    surface: pygame.Surface,
    center: tuple[int, int],
    radius: int,
    rgba: RGBA,
    width: int,
) -> None:
    """Draw a translucent circle, blended rather than written.

    Args:
        surface: Destination.
        center: Centre, in surface coordinates.
        radius: Radius in pixels.
        rgba: The colour, with an alpha below 255.
        width: Outline width; 0 fills.
    """
    if radius <= 0:
        return
    cx, cy = center
    bounds = pygame.Rect(cx - radius, cy - radius, 2 * radius + 1, 2 * radius + 1)

    def draw(scratch: pygame.Surface, offset: tuple[int, int]) -> None:
        pygame.draw.circle(
            scratch, rgba, (cx + offset[0], cy + offset[1]), radius, width
        )

    blit_blended(surface, bounds, draw)


def blit_blended_line(
    surface: pygame.Surface,
    start: tuple[int, int],
    end: tuple[int, int],
    rgba: RGBA,
    width: int,
) -> None:
    """Draw a translucent line, blended rather than written.

    Args:
        surface: Destination.
        start: One end, in surface coordinates.
        end: The other end.
        rgba: The colour, with an alpha below 255.
        width: Line width in pixels.
    """
    pad = max(1, width)
    bounds = pygame.Rect(
        min(start[0], end[0]) - pad,
        min(start[1], end[1]) - pad,
        abs(end[0] - start[0]) + 2 * pad + 1,
        abs(end[1] - start[1]) + 2 * pad + 1,
    )

    def draw(scratch: pygame.Surface, offset: tuple[int, int]) -> None:
        dx, dy = offset
        pygame.draw.line(
            scratch,
            rgba,
            (start[0] + dx, start[1] + dy),
            (end[0] + dx, end[1] + dy),
            width,
        )

    blit_blended(surface, bounds, draw)


def blit_blended_polygon(
    surface: pygame.Surface,
    points: list[tuple[int, int]],
    rgba: RGBA,
    width: int,
) -> None:
    """Draw a translucent polygon, blended rather than written.

    Args:
        surface: Destination.
        points: The vertices, in surface coordinates.
        rgba: The colour, with an alpha below 255.
        width: Outline width; 0 fills.
    """
    if len(points) < 3:
        return
    pad = max(1, width)
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    bounds = pygame.Rect(
        min(xs) - pad,
        min(ys) - pad,
        max(xs) - min(xs) + 2 * pad + 1,
        max(ys) - min(ys) + 2 * pad + 1,
    )

    def draw(scratch: pygame.Surface, offset: tuple[int, int]) -> None:
        dx, dy = offset
        pygame.draw.polygon(scratch, rgba, [(x + dx, y + dy) for x, y in points], width)

    blit_blended(surface, bounds, draw)
