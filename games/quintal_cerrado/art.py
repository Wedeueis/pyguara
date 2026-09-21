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

import math

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


MOISTURE_TINT = Water.C300
MOISTURE_TINT_STRENGTH = 0.35
"""How far a fully-saturated (moisture=1.0) cell shifts towards
`MOISTURE_TINT` -- a legible "this is wet" cue without washing out the
till/tilled colour contrast a glance needs first."""


def draw_soil_tile(
    renderer: UIRenderer, rect: Rect, kind: str, *, moisture: float = 0.0
) -> None:
    """Fill one cell with its soil kind's colour, plus a grid line.

    Args:
        renderer: The UI renderer to draw through.
        rect: The cell's screen rectangle.
        kind: A `Tilemap.properties_for(gid)["kind"]` value; unknown kinds
            fall back to raw dirt rather than raising, so a gid a future
            phase has not taught this module about yet still draws
            something instead of crashing the whole grid.
        moisture: `SoilCell.moisture`, 0.0-1.0. Tints the tile towards
            `MOISTURE_TINT` so watering (and its `systems/soil_system.py`
            decay) is something a player can actually see, not just a
            number that quietly gates growth.
    """
    base = _SOIL_COLORS.get(kind, RAW_DIRT)
    color = base.lerp(MOISTURE_TINT, moisture * MOISTURE_TINT_STRENGTH)
    renderer.draw_rect(rect, color)
    renderer.draw_rect(rect, GRID_LINE, width=1)


STAGE_SCALE: dict[str, float] = {
    "seedling": 0.55,
    "growing": 0.8,
    "mature": 1.0,
    "harvestable": 1.0,
}

HARVEST_RING = Sand.C200
HARVEST_FRUIT = Sand.C300


def draw_plant(
    renderer: UIRenderer,
    center: Vector2,
    color: Color,
    stage: str,
    *,
    pop: float = 0.0,
    sway: float = 0.0,
    elapsed: float = 0.0,
) -> None:
    """Draw a plant at its growth stage, with a pop-in bounce and idle sway.

    Args:
        renderer: The UI renderer to draw through.
        center: The cell's centre, in screen space.
        color: The species' colour.
        stage: `PlantComponent.growth_stage` -- picks the silhouette size.
            An unrecognised stage falls back to full size rather than
            raising, the same tolerance `draw_soil_tile` gives an unknown
            tile kind.
        pop: 1.0 right after planting or a stage change, easing to 0.0 --
            a brief overshoot scale so a transition reads as an event, not
            just a fact discovered a frame later.
        sway: A per-plant horizontal offset in pixels, so a full plot
            doesn't read as a field of static stickers.
        elapsed: Seconds since the scene entered, driving the harvestable
            stage's pulsing ring -- the same role `phase` plays in
            `guara_falcao.art.draw_guara`'s run cycle.
    """
    scale = STAGE_SCALE.get(stage, 1.0) * (1.0 + 0.4 * pop)
    base = Vector2(center.x + sway, center.y)

    stem_height = 10 * scale
    renderer.draw_line(
        Vector2(base.x, base.y + stem_height),
        Vector2(base.x, base.y - 2 * scale),
        TILLED_DIRT,
        width=max(1, round(3 * scale)),
    )

    leaf_center = Vector2(base.x, base.y - 6 * scale)
    leaf_radius = 7 * scale
    renderer.draw_circle(leaf_center, leaf_radius, color)

    if stage == "harvestable":
        pulse = 0.5 + 0.5 * math.sin(elapsed * 3.0)
        ring_color = Color(
            HARVEST_RING.r, HARVEST_RING.g, HARVEST_RING.b, int(110 + 90 * pulse)
        )
        renderer.draw_circle(
            leaf_center, leaf_radius + 3 + 2 * pulse, ring_color, width=2
        )
        renderer.draw_circle(
            Vector2(
                leaf_center.x + leaf_radius * 0.5, leaf_center.y - leaf_radius * 0.3
            ),
            2.5,
            HARVEST_FRUIT,
        )
