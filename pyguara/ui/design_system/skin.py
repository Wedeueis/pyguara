"""The two drawing tricks the Cerrado look needs, over `UIRenderer`.

Everything else in this design system is theme values. These two are not
expressible that way -- a bevel is two extra edges and a stamp shadow is a
rectangle behind the element -- so they live here as functions any
component can call, rather than as a second widget hierarchy.

**Why the highlights are opaque rather than alpha overlays.** The obvious
bevel is white at ~18% alpha over the top edge and black over the bottom.
It does not work here: both UI backends draw through `pygame.draw`, which
*replaces* the destination pixel including its alpha rather than blending
into it. On the pygame backend the surface is opaque, so a 45/255 white
lands as solid white; on the ModernGL backend the overlay is `SRCALPHA`,
so the same call punches a nearly transparent hole in the element instead
of lightening it. Mixing the highlight into the base colour on the CPU --
which `Color.lerp` already does -- gives the same result on both, and is
deterministic enough to assert on in a test.
"""

from __future__ import annotations

from pyguara.common.types import Color, Rect
from pyguara.graphics.protocols import UIRenderer

HIGHLIGHT_MIX = 0.25
"""How far the lit edge moves towards white."""

SHADOW_MIX = 0.35
"""How far the shaded edge moves towards black. Heavier than the
highlight: the eye reads a dark edge as less pronounced than a light one
of the same magnitude."""


def bevel_edges(base: Color, *, pressed: bool = False) -> tuple[Color, Color]:
    """The top and bottom edge colours for a bevel over `base`.

    Args:
        base: The element's fill colour, which the edges are mixed from.
        pressed: Swap the pair, so the element reads as pushed in rather
            than standing proud.

    Returns:
        `(top, bottom)` -- lit then shaded, or the reverse when pressed.
    """
    lit = base.lerp(Color.WHITE, HIGHLIGHT_MIX)
    shaded = base.lerp(Color.BLACK, SHADOW_MIX)
    return (shaded, lit) if pressed else (lit, shaded)


def draw_bevel(
    renderer: UIRenderer,
    rect: Rect,
    base: Color,
    *,
    pressed: bool = False,
    thickness: int = 2,
) -> None:
    """Draw a lit top edge and a shaded bottom edge inside `rect`.

    Call it after the element's fill and before its text, so the edges sit
    on the fill but never across a glyph.

    Args:
        renderer: The UI renderer to draw through.
        rect: The element's bounds. The edges are drawn inside it, so the
            element does not grow.
        base: The element's fill colour.
        pressed: Invert the bevel for a pressed element.
        thickness: Edge thickness in pixels; clamped so the two edges
            cannot overlap in a short element.
    """
    edge = max(1, min(thickness, rect.height // 2))
    top, bottom = bevel_edges(base, pressed=pressed)

    renderer.draw_rect(Rect(rect.x, rect.y, rect.width, edge), top)
    renderer.draw_rect(
        Rect(rect.x, rect.y + rect.height - edge, rect.width, edge), bottom
    )


def draw_stamp_shadow(
    renderer: UIRenderer,
    rect: Rect,
    color: Color,
    *,
    offset: int = 2,
) -> None:
    """Draw `rect` offset down-right as a hard shadow.

    Hard-edged and opaque on purpose: this is a print-stamp shadow, not a
    soft drop shadow, and a blurred one is not reachable through the UI
    renderer's primitives anyway (see the module docstring on alpha).

    Call it *before* the element it sits under.

    Args:
        renderer: The UI renderer to draw through.
        rect: The element's bounds.
        color: The shadow colour -- usually `theme.shadows.color`.
        offset: Pixels right and down.
    """
    renderer.draw_rect(
        Rect(rect.x + offset, rect.y + offset, rect.width, rect.height), color
    )
