"""The plot, drawn from primitives.

No textures -- soil tiles and seedlings are rects and circles, the same
house style `guara_falcao`/`tamandua_murundus`/`protocolo_bandeira` use.
Colours come from the brand palette (`pyguara.ui.design_system.tokens`),
so the grid sits in the same Cerrado as the rest of the design system.

Draws through the world `IRenderer`, not `UIRenderer`, since the
fun-improvement roadmap's Phase 5: `garden_widget.GardenGridCanvas` still
turns a click into a cell as a `Canvas`-derived UI widget, but its own
*rendering* now happens through `render_world()`, called directly from
`scenes.GardenScene.render()`, so the plot draws into the pipeline's
world pass and picks up its post-process shaders (`bootstrap.py`) --
`UIRenderer`'s draw calls, and everything else still built from them
(the tool bar, the HUD), do not. `IRenderer`'s primitives take the exact
same screen-pixel coordinates `UIRenderer`'s always did (see its own
protocol docstring), so nothing here needed to change beyond the type.
"""

from __future__ import annotations

import math

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import IRenderer
from pyguara.ui.design_system.tokens import Rock, Roxo, Sand, Verdant, Water, Wood

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


DEGRADED_TINT = Color(206, 132, 96)
DEGRADED_TINT_STRENGTH = 0.4
"""How far chemically degraded soil shifts towards `DEGRADED_TINT` -- the
PRD's "soil turns dusty red"."""

PEST = Roxo.C700
PEST_TINT = Roxo.C500
DYING_TINT = Color(112, 102, 92)


def draw_soil_tile(
    renderer: IRenderer,
    rect: Rect,
    kind: str,
    *,
    moisture: float = 0.0,
    degraded: bool = False,
) -> None:
    """Fill one cell with its soil kind's colour, plus a grid line.

    Args:
        renderer: The world renderer to draw through.
        rect: The cell's screen rectangle.
        kind: A `Tilemap.properties_for(gid)["kind"]` value; unknown kinds
            fall back to raw dirt rather than raising, so a gid a future
            phase has not taught this module about yet still draws
            something instead of crashing the whole grid.
        moisture: `SoilCell.moisture`, 0.0-1.0. Tints the tile towards
            `MOISTURE_TINT` so watering (and its `systems/soil_system.py`
            decay) is something a player can actually see, not just a
            number that quietly gates growth.
        degraded: `SoilCell.is_chemically_degraded`. Tints the tile dusty
            red, so the cost of a chemical spray stays visible in the
            ground long after the pests are gone.
    """
    base = _SOIL_COLORS.get(kind, RAW_DIRT)
    if degraded:
        base = base.lerp(DEGRADED_TINT, DEGRADED_TINT_STRENGTH)
    color = base.lerp(MOISTURE_TINT, moisture * MOISTURE_TINT_STRENGTH)
    renderer.draw_rect(rect, color)
    renderer.draw_rect(rect, GRID_LINE, width=1)


def draw_pest_marks(
    renderer: IRenderer, rect: Rect, pressure: float, elapsed: float
) -> None:
    """Scatter small crawling dots over a cell, more of them the worse it is.

    Args:
        renderer: The world renderer to draw through.
        rect: The cell's screen rectangle.
        pressure: `SoilCell.pest_pressure`, 0.0-1.0.
        elapsed: Seconds since the scene entered, so the dots crawl.
    """
    count = math.ceil(pressure * 5)
    for index in range(count):
        angle = index * 2.4 + elapsed * (0.8 + 0.15 * index)
        radius = rect.width * (0.18 + 0.05 * (index % 3))
        renderer.draw_circle(
            Vector2(
                rect.centerx + math.cos(angle) * radius,
                rect.centery + math.sin(angle * 1.3) * radius,
            ),
            2.0,
            PEST,
        )


STAGE_SCALE: dict[str, float] = {
    "seedling": 0.55,
    "growing": 0.8,
    "mature": 1.0,
    "harvestable": 1.0,
    "infested": 0.9,
    "dying": 0.7,
}

HARVEST_RING = Sand.C200
HARVEST_FRUIT = Sand.C300


def draw_plant(
    renderer: IRenderer,
    center: Vector2,
    color: Color,
    stage: str,
    *,
    pop_scale: float = 1.0,
    sway: float = 0.0,
    elapsed: float = 0.0,
) -> None:
    """Draw a plant at its growth stage, with a pop-in bounce and idle sway.

    Args:
        renderer: The world renderer to draw through.
        center: The cell's centre, in screen space.
        color: The species' colour.
        stage: `PlantComponent.growth_stage` -- picks the silhouette size.
            An unrecognised stage falls back to full size rather than
            raising, the same tolerance `draw_soil_tile` gives an unknown
            tile kind.
        pop_scale: A multiplier on top of the stage's own size, 1.0 at
            rest. Right after planting or a stage change the caller drives
            this from a tween that overshoots above 1.0 before settling
            back on it, so the transition reads as an event, not just a
            fact discovered a frame later.
        sway: A per-plant horizontal offset in pixels, so a full plot
            doesn't read as a field of static stickers.
        elapsed: Seconds since the scene entered, driving the harvestable
            stage's pulsing ring -- the same role `phase` plays in
            `guara_falcao.art.draw_guara`'s run cycle.
    """
    scale = STAGE_SCALE.get(stage, 1.0) * pop_scale
    if stage == "infested":
        color = color.lerp(PEST_TINT, 0.5)
    elif stage == "dying":
        color = color.lerp(DYING_TINT, 0.8)
        sway = 0.0
    base = Vector2(center.x + sway, center.y)

    stem_height = 10 * scale
    renderer.draw_line(
        Vector2(base.x, base.y + stem_height),
        Vector2(base.x, base.y - 2 * scale),
        TILLED_DIRT,
        width=max(1, round(3 * scale)),
    )

    leaf_center = Vector2(base.x, base.y - 6 * scale)
    if stage == "dying":
        # A wilted plant sags: the leaf droops down and to one side.
        leaf_center = Vector2(base.x + 4 * scale, base.y - 1 * scale)
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


NO_POWER = Color(206, 84, 70)
SOLAR_CELL = Color(44, 74, 128)
SOLAR_FRAME = Color(150, 170, 200)
PIPE = Color(120, 138, 150)
DRONE_BODY = Sand.C300
SENSOR_TRACK = Color(24, 20, 20, 150)


def draw_structure(
    renderer: IRenderer,
    rect: Rect,
    kind: str,
    *,
    powered: bool = True,
    elapsed: float = 0.0,
) -> None:
    """Draw one placed structure inside its cell.

    Args:
        renderer: The world renderer to draw through.
        rect: The cell's screen rectangle.
        kind: A key of `structures.STRUCTURE_TABLE`. An unknown kind draws
            nothing, the same tolerance `draw_soil_tile` gives an unknown
            tile.
        powered: Whether it has power. An unpowered device draws a red
            warning dot, so a plot that has outgrown its panels says so.
        elapsed: Seconds since the scene entered, animating the glint, the
            droplets, the blink and the drone's hover.
    """
    cx, cy = rect.centerx, rect.centery
    if kind == "solar_panel":
        panel = Rect(rect.x + 6, rect.y + 9, rect.width - 12, rect.height - 18)
        renderer.draw_rect(panel, SOLAR_CELL)
        renderer.draw_rect(panel, SOLAR_FRAME, width=2)
        renderer.draw_line(
            Vector2(cx, panel.top), Vector2(cx, panel.bottom), SOLAR_FRAME, width=1
        )
        renderer.draw_line(
            Vector2(panel.left, cy), Vector2(panel.right, cy), SOLAR_FRAME, width=1
        )
        glint = 0.5 + 0.5 * math.sin(elapsed * 2.2)
        renderer.draw_circle(
            Vector2(panel.left + 8, panel.top + 7),
            2.0 + glint,
            Color(255, 244, 200, int(120 + 120 * glint)),
        )
    elif kind == "drip_irrigation":
        renderer.draw_line(
            Vector2(rect.x + 6, cy), Vector2(rect.right - 6, cy), PIPE, width=4
        )
        renderer.draw_line(
            Vector2(cx, rect.y + 6), Vector2(cx, rect.bottom - 6), PIPE, width=4
        )
        renderer.draw_circle(Vector2(cx, cy), 6, PIPE)
        if powered:
            for index in range(4):
                phase = (elapsed * 1.6 + index * 0.25) % 1.0
                angle = index * math.pi / 2 + math.pi / 4
                distance = 8 + phase * 12
                renderer.draw_circle(
                    Vector2(
                        cx + math.cos(angle) * distance, cy + math.sin(angle) * distance
                    ),
                    2.0,
                    Color(
                        Water.C300.r, Water.C300.g, Water.C300.b, int(255 * (1 - phase))
                    ),
                )
    elif kind == "soil_sensor":
        renderer.draw_line(
            Vector2(cx, cy + 12), Vector2(cx, rect.bottom - 6), PIPE, width=3
        )
        renderer.draw_rect(Rect(cx - 7, cy - 10, 14, 20), PIPE)
        blink = 1.0 if math.sin(elapsed * 4.0) > 0.0 else 0.35
        renderer.draw_circle(
            Vector2(cx, cy - 3), 3.0, Color(120, 230, 150, int(255 * blink))
        )
    elif kind == "auto_harvester":
        hover = math.sin(elapsed * 3.0) * 2.0
        body = Vector2(cx, cy + hover)
        renderer.draw_circle(Vector2(cx + 2, rect.bottom - 8), 6, Color(0, 0, 0, 60))
        renderer.draw_circle(body, 8, DRONE_BODY if powered else PIPE)
        spin = elapsed * (14.0 if powered else 0.0)
        for arm in (0.0, math.pi / 2):
            dx, dy = math.cos(spin + arm) * 14, math.sin(spin + arm) * 4
            renderer.draw_line(
                Vector2(body.x - dx, body.y - 8 - dy),
                Vector2(body.x + dx, body.y - 8 + dy),
                SOLAR_FRAME,
                width=2,
            )
    else:
        return

    if not powered:
        renderer.draw_circle(Vector2(rect.right - 7, rect.y + 7), 4.0, NO_POWER)


def draw_sensor_readout(
    renderer: IRenderer, rect: Rect, moisture: float, organic: float, pest: float
) -> None:
    """Draw three thin bars along the bottom of a cell a soil sensor covers.

    Args:
        renderer: The world renderer to draw through.
        rect: The cell's screen rectangle.
        moisture: `SoilCell.moisture`, 0.0-1.0 (blue).
        organic: `SoilCell.organic_matter`, 0.0-1.0 (green).
        pest: `SoilCell.pest_pressure`, 0.0-1.0 (magenta) -- the one that
            earns the sensor its place: it reads pests before a plant does.
    """
    width = rect.width - 10
    for row, (value, color) in enumerate(
        (
            (moisture, Water.C300),
            (organic, Verdant.SAGE_100),
            (pest, Color(210, 90, 200)),
        )
    ):
        y = rect.bottom - 14 + row * 4
        renderer.draw_rect(Rect(rect.x + 5, y, width, 3), SENSOR_TRACK)
        filled = int(width * max(0.0, min(1.0, value)))
        if filled > 0:
            renderer.draw_rect(Rect(rect.x + 5, y, filled, 3), color)
