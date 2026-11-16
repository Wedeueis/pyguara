"""The two drawing tricks the Cerrado look needs, over `UIRenderer`.

A bevel is two extra edges and a stamp shadow is a rectangle behind
the element. They are functions any component can call.

The highlights are opaque colours, mixed into the base colour with
`Color.lerp`, not translucent overlays, so they come out the same on
every renderer.
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
    """Return the top and bottom edge colours for a bevel over `base`.

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
