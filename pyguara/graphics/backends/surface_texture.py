"""Blitting a texture, or one region of it, onto a pygame surface.

The shared implementation of `UIRenderer.draw_texture` for a renderer
that draws onto a `pygame.Surface`: cut the source region if one is
named, scale it to the destination, tint a copy if asked, blit.
"""

from __future__ import annotations

from typing import Any

import pygame

from pyguara.common.types import Rect
from pyguara.log import get_logger

logger = get_logger(__name__)

RGB = tuple[int, int, int]

_warned_out_of_bounds = False
_warned_unusable: set[str] = set()


def as_surface(texture: Any) -> pygame.Surface | None:
    """Return the surface a UI renderer can blit for `texture`.

    A bare surface passes straight through. A `resources.Texture`, which
    is what `ResourceManager.load` returns, is unwrapped: `PygameTexture`
    holds a surface, and a texture with `read_surface()` reads its pixels
    back from the GPU the first time and keeps them.

    Anything else draws nothing, and is logged once.

    Args:
        texture: A surface, a `resources.Texture`, or something unusable.

    Returns:
        The surface, or None if `texture` cannot provide one.
    """
    if isinstance(texture, pygame.Surface):
        return texture

    handle = getattr(texture, "native_handle", None)
    if isinstance(handle, pygame.Surface):
        return handle

    read_surface = getattr(texture, "read_surface", None)
    if callable(read_surface):
        surface: pygame.Surface = read_surface()
        return surface

    kind = type(texture).__name__
    if kind not in _warned_unusable:
        _warned_unusable.add(kind)
        logger.warning(
            "A UI renderer cannot draw a %s: it needs a pygame.Surface or a "
            "resources.Texture. Drawing nothing.",
            kind,
        )
    return None


def blit_texture(
    surface: pygame.Surface,
    texture: pygame.Surface,
    rect: Rect,
    tint: RGB | None = None,
    source_rect: Rect | None = None,
) -> bool:
    """Draw `texture`, or the `source_rect` region of it, scaled into `rect`.

    A source region is cut out before any scaling or tinting, so an atlas
    entry scales as a standalone texture would.

    A source region that leaves the texture is clipped to the overlap and
    logged once per process, naming the region and the texture. An empty
    overlap draws nothing.

    Args:
        surface: Destination.
        texture: The source surface.
        rect: Where to draw, in destination coordinates. A non-positive
            extent draws nothing, as in the shape helpers in
            `surface_blending`.
        tint: An `(r, g, b)` multiply, or None for none. RGB and not
            RGBA: a UI tint recolours and does not fade.
        source_rect: The region of `texture` to draw, or None for all of it.

    Returns:
        Whether anything was drawn.
    """
    if rect.width <= 0 or rect.height <= 0:
        return False

    whole = texture.get_rect()
    if source_rect is None:
        region = whole
    else:
        region = _clip_region(source_rect, whole)
        if region.width <= 0 or region.height <= 0:
            return False

    source = texture if region == whole else texture.subsurface(region)

    if region.width != rect.width or region.height != rect.height:
        source = pygame.transform.scale(source, (rect.width, rect.height))

    if tint is not None:
        # Copy first: with no scale above, `source` may still be the
        # caller's own texture (or a subsurface sharing its pixels), and
        # `fill` mutates in place -- tinting it directly would discolour
        # every later draw of that texture.
        tinted = source.copy()
        tinted.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
        source = tinted

    surface.blit(source, pygame.Rect(rect.x, rect.y, rect.width, rect.height))
    return True


def _clip_region(source_rect: Rect, whole: pygame.Rect) -> pygame.Rect:
    """Intersect a requested source region with the texture it names.

    Args:
        source_rect: The region the caller asked for.
        whole: The texture's own rect.

    Returns:
        The overlap, which may be empty.
    """
    global _warned_out_of_bounds

    asked = pygame.Rect(
        source_rect.x,
        source_rect.y,
        max(0, source_rect.width),
        max(0, source_rect.height),
    )
    clipped = asked.clip(whole)
    if clipped != asked and not _warned_out_of_bounds:
        _warned_out_of_bounds = True
        logger.warning(
            f"A UI texture draw asked for the region {tuple(asked)} of a "
            f"{whole.width}x{whole.height} texture, which does not contain it; "
            f"drew the {tuple(clipped)} overlap instead. The atlas metadata and "
            f"the atlas disagree. Reported once per process."
        )
    return clipped
