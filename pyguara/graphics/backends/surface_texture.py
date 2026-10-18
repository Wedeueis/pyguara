"""Blitting a texture, or one region of it, onto a pygame surface.

Both UI renderers draw onto a `pygame.Surface` -- the pygame backend's
display directly, the ModernGL backend's offscreen overlay before it is
uploaded -- and their `draw_texture` bodies were byte-identical: scale the
whole surface to the destination, tint a copy if asked, blit. Identical by
coincidence, not by construction, which is how the pygame stubs drifted
from the GL ones before (see `test_graphics_protocol_conformance.py`).

`source_rect` is the reason it matters now. A UI texture draw could not
name a region of its texture, so a widget showing one frame of an atlas
had to be handed a pre-cut surface -- while the *world* renderer has
carried `RenderCommand.source_rect` and `RenderBatch.source_rects` all
along, and the pygame backend blits regions straight out of a sheet. The
asymmetry was the defect; one shared implementation is what keeps the two
halves answering the same way.
"""

from __future__ import annotations

import pygame

from pyguara.common.types import Rect
from pyguara.log import get_logger

logger = get_logger(__name__)

RGB = tuple[int, int, int]

_warned_out_of_bounds = False


def blit_texture(
    surface: pygame.Surface,
    texture: pygame.Surface,
    rect: Rect,
    tint: RGB | None = None,
    source_rect: Rect | None = None,
) -> bool:
    """Draw `texture`, or the `source_rect` region of it, scaled into `rect`.

    A source region is cut out before any scaling or tinting runs, so the
    destination holds that region stretched to fill it -- the same order
    the pygame world renderer's per-instance path uses, and the only order
    that makes an atlas entry scale the way a standalone texture would.

    **An out-of-bounds source region is clipped, not refused.** The caller
    asked for pixels that do not exist, which is always a bug in its atlas
    metadata, but the alternative to drawing the overlap is drawing
    nothing: one wrong entry would then blank a whole HUD rather than show
    one wrong sprite. The clip is logged once per process, naming the
    region and the texture, so the bug is findable from the log instead of
    from the frame. An empty overlap draws nothing at all.

    Args:
        surface: Destination.
        texture: The source surface.
        rect: Where to draw, in destination coordinates. A non-positive
            extent draws nothing, matching the shape helpers in
            `surface_blending` -- a nine-patch with one zero-width edge
            asks for three of those per frame, so they have to be free
            rather than an error.
        tint: An `(r, g, b)` multiply, or None for none. Deliberately RGB
            and not RGBA: a UI tint recolours, where a sprite or particle
            tint also fades, and the world renderer's batch path uses the
            full tuple for exactly that reason.
        source_rect: The region of `texture` to draw, or None for all of it.

    Returns:
        Whether anything was drawn. The ModernGL backend only has to
        re-upload its overlay when something was.
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
