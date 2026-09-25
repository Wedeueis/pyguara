"""The Cerrado, drawn from primitives.

The **world** here is rects, circles and lines -- sky, mounds, trees,
platforms, fruit -- and its look comes from layering, palette and light
rather than from art. That is how `tamandua_murundus` and
`protocolo_bandeira` are drawn too, so it is the house style rather than
a shortcut taken here.

The **characters** are not. The guará and the falcão used to be drawn
here as well, swinging their legs off a sine wave, and they are now
sprites played by the engine's own `Animator` and
`AnimationStateMachine` -- see `animation.py`, and
`tools/slice_spritesheet.py` for where the frames come from. That is the
whole point of the change: those two components had no reference usage
anywhere in the repository, which is a poor advertisement for an engine
that ships them. Nothing else moved: a demo that was primitives all the
way down would still have had nothing to show for them.

Two rules everything in this module obeys.

**Colours come from the brand palette** (`pyguara.ui.design_system.tokens`),
so the world and the menus in front of it are the same Cerrado. Nothing
here invents a colour.

**`end_frame()` is a depth boundary, not just a text boundary.** The
ModernGL backend buckets shape instances *by type* and draws one instanced
call per bucket -- every rect, then every circle, then every line. Within a
single flush that means **circles always land on top of rectangles, whatever
order they were submitted in**: a tree canopy drawn before a platform still
covers it, and a fruit drawn before the player still hides them.

So a caller draws one depth layer, calls `end_frame()`, and draws the next.
Text is the same rule for the same reason -- `draw_text` uploads and draws
immediately, so text queued before a flush ends up behind the shapes in it.
Callers own the flush; this module only queues shapes.
"""

from __future__ import annotations

import math

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import IRenderer
from pyguara.ui.design_system.skin import bevel_edges
from pyguara.ui.design_system.tokens import (
    Guara,
    Rock,
    Roxo,
    Sand,
    Verdant,
    Water,
    Wood,
)

# ---- palette ------------------------------------------------------------

# The sky, horizon first. Bands rather than a gradient: a gradient needs a
# shader, and banding reads as stylised at this scale rather than cheap.
# Deliberately none of them near-white: the sky sits *below* the bloom
# threshold so that the sun disc is the only thing that blooms. A cream
# sky at #fff6dd crossed it, and the whole right half of the frame went
# to white haze.
SKY_BANDS: tuple[Color, ...] = (
    Color.from_hex("#f0b968"),
    Color.from_hex("#f8cd85"),
    Sand.C200,
    Color.from_hex("#ffe3ab"),
)

SUN = Color.from_hex("#fff2cc")
FAR_MOUND = Color.from_hex("#c98a63")
MID_MOUND = Rock.C600
TRUNK = Wood.C500
TRUNK_DARK = Wood.C700
CANOPY_FAR = Color.from_hex("#93a86d")
CANOPY_NEAR = Verdant.SAGE_500
GRASS = Color.from_hex("#a89a52")
PLANK = Wood.C400
WATER = Water.C300

FRUIT = Color.from_hex("#a8cf3f")
FRUIT_RIPE = Sand.C300
HEALTH_PICKUP = Guara.C400
POWER_PICKUP = Water.C400

COAT = Guara.C500
COAT_DARK = Guara.C700
MANE = Color.from_hex("#331a1e")
CREAM = Guara.CREAM
EYE = Wood.INK_900

FALCAO_BODY = Color.from_hex("#6d5b4a")
FALCAO_WING = Roxo.C700
FALCAO_CHEST = Sand.C100

CHECKPOINT = Water.C400
CHECKPOINT_LIT = Color.from_hex("#b6f0c0")
GOAL = Verdant.COLONIAL_500
HAZARD = Color.from_hex("#7b2f2f")

# ---- backdrop -----------------------------------------------------------

# Where the parallax furniture stands, in world x. Fixed rather than
# random: a backdrop that reshuffles every run is a backdrop nobody can
# tune, and these were placed against the level the builder makes.
FAR_MOUNDS: tuple[tuple[float, float], ...] = (
    (120.0, 150.0),
    (430.0, 210.0),
    (760.0, 130.0),
    (1080.0, 185.0),
    (1420.0, 160.0),
)
MID_TREES: tuple[tuple[float, float], ...] = (
    (80.0, 190.0),
    (360.0, 230.0),
    (690.0, 200.0),
    (960.0, 245.0),
    (1260.0, 210.0),
)

FAR_FACTOR = 0.12
MID_FACTOR = 0.35
NEAR_FACTOR = 0.7
"""How much of the camera each depth layer takes. 0 is painted on the sky."""


def draw_sky(renderer: IRenderer, width: int, height: int) -> None:
    """Fill the frame with the amber hour.

    Args:
        renderer: The world renderer.
        width: Viewport width.
        height: Viewport height.
    """
    band_height = height // len(SKY_BANDS) + 1
    for index, color in enumerate(SKY_BANDS):
        renderer.draw_rect(Rect(0, index * band_height, width, band_height), color)


def draw_sun(renderer: IRenderer, width: int, height: int) -> None:
    """Draw the low sun, sized to bloom.

    It is drawn near-white on a bright sky so the bloom threshold catches
    it; the light that actually falls on the world is a `LightSource`, not
    this disc.

    Args:
        renderer: The world renderer.
        width: Viewport width.
        height: Viewport height.
    """
    center = Vector2(width * 0.74, height * 0.22)
    renderer.draw_circle(center, 78.0, Color(SUN.r, SUN.g, SUN.b, 90))
    renderer.draw_circle(center, 46.0, SUN)


def draw_parallax(
    renderer: IRenderer, camera_x: float, width: int, height: int
) -> None:
    """Draw the three depth layers behind the level.

    Args:
        renderer: The world renderer.
        camera_x: The camera's world x, which each layer takes a share of.
        width: Viewport width.
        height: Viewport height.
    """
    horizon = int(height * 0.72)

    for world_x, size in FAR_MOUNDS:
        x = world_x - camera_x * FAR_FACTOR
        _draw_mound(renderer, x, horizon + 30, size, FAR_MOUND)

    for world_x, size in MID_TREES:
        x = world_x - camera_x * MID_FACTOR
        _draw_tree(renderer, x, horizon + 10, size)

    # The near band: a strip of ground with grass tufts standing off it.
    renderer.draw_rect(Rect(0, horizon + 40, width, height - horizon), GRASS)
    for index in range(-2, width // 46 + 3):
        x = index * 46 - (camera_x * NEAR_FACTOR) % 46
        height_of = 10 + (index * 7) % 9
        renderer.draw_rect(Rect(int(x), horizon + 40 - height_of, 4, height_of), GRASS)


def _draw_mound(
    renderer: IRenderer, x: float, base_y: int, size: float, color: Color
) -> None:
    """Draw one termite mound as a stepped cone.

    Args:
        renderer: The world renderer.
        x: Screen x of the mound's centre.
        base_y: Screen y of its base.
        size: Height in pixels.
        color: Fill colour.
    """
    steps = 6
    for step in range(steps):
        fraction = step / steps
        width = size * (0.62 - fraction * 0.5)
        step_height = size / steps
        renderer.draw_rect(
            Rect(
                int(x - width / 2),
                int(base_y - size * fraction - step_height),
                int(max(2.0, width)),
                int(step_height) + 1,
            ),
            color,
        )


def _draw_tree(renderer: IRenderer, x: float, base_y: int, size: float) -> None:
    """Draw one Cerrado tree: a crooked trunk under stacked canopy blobs.

    Args:
        renderer: The world renderer.
        x: Screen x of the trunk.
        base_y: Screen y of its base.
        size: Overall height in pixels.
    """
    trunk_height = size * 0.6
    renderer.draw_rect(
        Rect(int(x - 5), int(base_y - trunk_height), 10, int(trunk_height)), TRUNK
    )
    renderer.draw_rect(
        Rect(int(x + 1), int(base_y - trunk_height), 4, int(trunk_height)), TRUNK_DARK
    )

    crown_y = base_y - trunk_height
    for offset_x, offset_y, radius, color in (
        (-26.0, 6.0, 26.0, CANOPY_FAR),
        (24.0, 2.0, 24.0, CANOPY_FAR),
        (0.0, -14.0, 32.0, CANOPY_NEAR),
        (-12.0, -2.0, 22.0, CANOPY_NEAR),
    ):
        renderer.draw_circle(Vector2(x + offset_x, crown_y + offset_y), radius, color)


# ---- level furniture ----------------------------------------------------


def draw_plank(renderer: IRenderer, rect: Rect) -> None:
    """Draw a platform as a lit wooden plank.

    The lit top and shaded underside come from `bevel_edges()`, the same
    function the design system's buttons use -- one definition of "which
    way the light is coming from", shared by the world and the UI over it.

    Args:
        renderer: The world renderer.
        rect: The platform's screen rectangle.
    """
    renderer.draw_rect(rect, PLANK)

    top, bottom = bevel_edges(PLANK)
    edge = max(2, rect.height // 8)
    renderer.draw_rect(Rect(rect.x, rect.y, rect.width, edge), top)
    renderer.draw_rect(
        Rect(rect.x, rect.y + rect.height - edge, rect.width, edge), bottom
    )

    # Grain: a few darker lines along the plank, skipped on short ones
    # where they would read as noise rather than wood.
    if rect.width >= 48 and rect.height >= 12:
        for index in range(1, rect.width // 34):
            grain_x = rect.x + index * 34
            renderer.draw_line(
                Vector2(grain_x, rect.y + edge + 2),
                Vector2(grain_x, rect.y + rect.height - edge - 2),
                bottom,
                width=1,
            )


# Two earth tones, picked per tile from its world position. A single flat
# colour over a whole level reads as a painted wall; a per-tile lit edge
# reads as stacked bricks, because every tile draws one whether or not the
# tile above it is solid. Varying the fill is the middle ground.
EARTH = (Color.from_hex("#9d4c3c"), Color.from_hex("#8f4535"))


def draw_ground_tile(renderer: IRenderer, rect: Rect, world_x: float) -> None:
    """Draw one solid tile of the level's earth.

    Args:
        renderer: The world renderer.
        rect: The tile's screen rectangle.
        world_x: Its world x, so the shade is stable as the camera moves.
    """
    renderer.draw_rect(rect, EARTH[int(world_x // 32) % len(EARTH)])


def draw_fruit(renderer: IRenderer, center: Vector2, radius: float) -> None:
    """Draw a hanging lime with a specular dot.

    Draws where it is told and nowhere else. The float used to be a sine
    added here, which meant the fruit drifted while the light attached to
    its entity stayed put -- a glow hanging beside the thing glowing. The
    motion belongs to the transform, so the drawing, the light and the
    pickup radius all agree on where the fruit is.

    Args:
        renderer: The world renderer.
        center: Screen position.
        radius: Fruit radius in pixels.
    """
    renderer.draw_circle(center, radius, FRUIT)
    renderer.draw_circle(
        Vector2(center.x, center.y + radius * 0.25), radius * 0.7, FRUIT_RIPE
    )
    renderer.draw_circle(
        Vector2(center.x - radius * 0.3, center.y - radius * 0.35),
        radius * 0.22,
        Color.WHITE,
    )


def draw_pickup(renderer: IRenderer, center: Vector2, radius: float, kind: str) -> None:
    """Draw a collectible, by kind.

    Args:
        renderer: The world renderer.
        center: Screen position.
        radius: Radius in pixels.
        kind: `"coin"`, `"health"` or `"power"`.
    """
    if kind == "coin":
        draw_fruit(renderer, center, radius)
        return

    color = HEALTH_PICKUP if kind == "health" else POWER_PICKUP
    renderer.draw_circle(center, radius, color)
    renderer.draw_circle(center, radius * 0.55, Color.WHITE)


def draw_checkpoint(renderer: IRenderer, rect: Rect, lit: bool) -> None:
    """Draw a checkpoint post, lit once reached.

    Args:
        renderer: The world renderer.
        rect: Its screen rectangle.
        lit: Whether the player has already passed it.
    """
    color = CHECKPOINT_LIT if lit else CHECKPOINT
    renderer.draw_rect(
        Rect(rect.x + rect.width // 2 - 3, rect.y, 6, rect.height), TRUNK
    )
    renderer.draw_rect(Rect(rect.x, rect.y, rect.width, rect.height // 3), color)


def draw_goal(renderer: IRenderer, rect: Rect, phase: float) -> None:
    """Draw the level's end: a standing beam of light.

    Args:
        renderer: The world renderer.
        rect: Its screen rectangle.
        phase: Seconds, for the pulse.
    """
    pulse = 0.5 + 0.5 * math.sin(phase * 3.0)
    renderer.draw_rect(rect, GOAL)
    inner = Rect(
        rect.x + 4, rect.y + 4, max(2, rect.width - 8), max(2, rect.height - 8)
    )
    renderer.draw_rect(
        inner,
        Color(
            CHECKPOINT_LIT.r, CHECKPOINT_LIT.g, CHECKPOINT_LIT.b, int(120 + 100 * pulse)
        ),
    )


def draw_hazard(renderer: IRenderer, rect: Rect) -> None:
    """Draw a hazard as a row of spines.

    Args:
        renderer: The world renderer.
        rect: Its screen rectangle.
    """
    renderer.draw_rect(rect, HAZARD)
    spine_width = 6
    for index in range(max(1, rect.width // (spine_width * 2))):
        x = rect.x + index * spine_width * 2
        renderer.draw_rect(Rect(x, rect.y - 6, spine_width, 6), HAZARD)


def draw_crate(renderer: IRenderer, rect: Rect) -> None:
    """Draw a pushable crate.

    Args:
        renderer: The world renderer.
        rect: Its screen rectangle.
    """
    renderer.draw_rect(rect, Wood.C400)
    top, bottom = bevel_edges(Wood.C400)
    renderer.draw_rect(Rect(rect.x, rect.y, rect.width, 3), top)
    renderer.draw_rect(Rect(rect.x, rect.y + rect.height - 3, rect.width, 3), bottom)
    renderer.draw_line(
        Vector2(rect.x, rect.y),
        Vector2(rect.x + rect.width, rect.y + rect.height),
        bottom,
        width=2,
    )


# ---- the characters -----------------------------------------------------
