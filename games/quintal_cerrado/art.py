"""The plot, drawn from primitives.

No textures -- soil tiles and seedlings are rects and circles, the same
house style `guara_falcao`/`tamandua_murundus`/`protocolo_bandeira` use.
Colours come from the brand palette (`pyguara.ui.design_system.tokens`),
so the grid sits in the same Cerrado as the rest of the design system.

Everything here draws through a `UIRenderer` rather than the world
`IRenderer`: the whole plot is one `Canvas`-derived UI widget
(`garden_widget.GardenGridCanvas`), not world-space geometry, so its
draw calls take the same renderer a `Panel` or `ProgressBar` would.
"""

from __future__ import annotations

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.design_system.tokens import Rock, Sand, Verdant, Water, Wood

WORLD_BACKDROP = Verdant.COLONIAL_700

RAW_DIRT = Wood.C500
TILLED_DIRT = Wood.C700
PATH = Sand.C300
WATER_PIPE = Water.C300
GRID_LINE = Rock.C600

_SOIL_COLORS: dict[str, Color] = {
    "raw_dirt": RAW_DIRT,
    "tilled_dirt": TILLED_DIRT,
    "path": PATH,
    "water_pipe": WATER_PIPE,
}


def draw_soil_tile(renderer: UIRenderer, rect: Rect, kind: str) -> None:
    """Fill one cell with its soil kind's colour, plus a grid line.

    Args:
        renderer: The UI renderer to draw through.
        rect: The cell's screen rectangle.
        kind: A `Tilemap.properties_for(gid)["kind"]` value; unknown kinds
            fall back to raw dirt rather than raising, so a gid a future
            phase has not taught this module about yet still draws
            something instead of crashing the whole grid.
    """
    renderer.draw_rect(rect, _SOIL_COLORS.get(kind, RAW_DIRT))
    renderer.draw_rect(rect, GRID_LINE, width=1)


def draw_seedling(renderer: UIRenderer, center: Vector2, color: Color) -> None:
    """Draw a planted seedling as a small stem and a leaf.

    Args:
        renderer: The UI renderer to draw through.
        center: The cell's centre, in screen space.
        color: The species' colour.
    """
    renderer.draw_line(
        Vector2(center.x, center.y + 10),
        Vector2(center.x, center.y - 2),
        TILLED_DIRT,
        width=3,
    )
    renderer.draw_circle(Vector2(center.x, center.y - 6), 7, color)
