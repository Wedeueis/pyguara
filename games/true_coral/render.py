"""True Coral - every draw call the game makes.

The GDD's art direction is "Luminous Leaf Litter": a near-black forest
floor of dry leaves, with the things that matter -- the snake, its prey,
the fungi -- as the only sources of light. Nothing here is a sprite; it is
all circles, capsules and lines, which is what the ModernGL shape shader
draws in one instanced call per shape type.

Two engine features do most of the work and are worth knowing about before
changing anything here:

*Bloom* makes the glow. Rather than stacking translucent haloes by hand,
this module draws small, genuinely bright cores and lets the bloom pass
bleed them. That is why some colours look over-bright in isolation: they
are input to a threshold, not a final pixel.

*The light map* makes the dark. Everything is multiplied by the lighting
pass's output, so the leaf litter is only visible where something glows on
it -- and a lightning strike, which lifts the ambient term for a few
frames, reveals the whole floor at once. Drawing a leaf brighter here does
not brighten it on screen; adding a light near it does.

Draw order is the one thing to be careful about here, because it is not
the order of these calls. The ModernGL backend queues shape primitives
into one bucket per *shape type* and flushes them at `end_frame()` as one
instanced draw call each, rects then circles then lines. Submission order
holds within a bucket and not at all between them: every line in a frame
lands on top of every circle in it, whenever it was submitted. A snake's
head, drawn last as a circle, came out underneath the capsule of the body
segment behind it.

So each function here ends by calling `end_frame()` -- a flush is what
separates one layer from the next -- and a couple of them flush in the
middle, where a line has to go under a circle drawn after it. Text is the
other half of the same rule: `draw_text` draws immediately, so the HUD's
text is written after the scene's last flush. Flushes are cheap (three
draw calls), and layering is not otherwise expressible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import IRenderer

# ---- Palette -------------------------------------------------------
# The GDD's three snake colours, plus the litter they sit on. The neon
# variants are deliberately past the bloom threshold; the base ones are not.

VOID = Color(6, 7, 9)
SOIL = Color(11, 13, 12)
FLOOR = Color(24, 30, 27)

CORAL_RED = Color(255, 96, 26)  # PyGuara brand orange, pushed to neon
CORAL_RED_CORE = Color(255, 180, 120)
CREAM = Color(240, 234, 214)
# Not actually black: the floor is near-black too, so a true black band
# reads as a gap in the snake rather than as a band on it.
BAND_BLACK = Color(44, 40, 48)
HEAD_GOLD = Color(255, 206, 74)
HEAD_DARK = Color(34, 30, 34)

TEAL = Color(90, 226, 214)
TEAL_DIM = Color(52, 120, 118)
AMBER = Color(255, 190, 92)
EYE_GOLD = Color(255, 226, 120)

LEAF_COLORS = (
    Color(46, 38, 27),
    Color(38, 42, 31),
    Color(30, 28, 24),
    Color(52, 43, 30),
)

FOOD_COLORS = {
    "larva": CREAM,
    "beetle": Color(236, 46, 32),
    "star": Color(255, 236, 150),
}

CELL_SIZE = 32


@dataclass(slots=True)
class Leaf:
    """One piece of dry litter: a capsule with a rotation and a shade."""

    position: Vector2
    length: float
    width: float
    angle: float
    color: Color


@dataclass(slots=True)
class Mushroom:
    """A glowing fungus. Also a light source -- see `Backdrop.lights`."""

    position: Vector2
    radius: float
    phase: float
    color: Color


@dataclass(slots=True)
class Root:
    """A thick tree root crossing the frame behind everything."""

    start: Vector2
    end: Vector2
    width: int


class Backdrop:
    """The static forest floor: litter, roots, fungi, and the owl.

    Generated once from a seeded stream, so the floor is the same every
    run. That is worth more than variety here: a capture from
    `tools/agent_view.py` is comparable with the last one, and a change to
    the litter is visible as a change rather than as noise.
    """

    def __init__(
        self,
        width: int,
        height: int,
        arena: Rect,
        *,
        seed: int = 20260912,
    ) -> None:
        """Scatter the floor.

        Args:
            width: Window width in pixels.
            height: Window height in pixels.
            arena: The play area, in screen space. Litter falls inside it
                too -- it is the floor the snake crawls over -- but fungi
                and roots keep to the margins, where they cannot be
                mistaken for food.
            seed: Seed for the scatter.
        """
        self._width = width
        self._height = height
        self._arena = arena
        rng = RandomStream(seed)

        self.leaves = self._scatter_leaves(rng)
        self.roots = self._lay_roots(rng)
        self.mushrooms = self._grow_mushrooms(rng)
        self.owl_position = Vector2(width - 86.0, 88.0)

    def _scatter_leaves(self, rng: RandomStream) -> list[Leaf]:
        leaves = []
        for _ in range(340):
            x = rng.uniform(-10.0, self._width + 10.0)
            y = rng.uniform(-10.0, self._height + 10.0)
            inside = self._arena.contains_point(Vector2(x, y))
            leaves.append(
                Leaf(
                    position=Vector2(x, y),
                    # Litter on the playfield is smaller and darker, so it
                    # reads as texture rather than competing with food.
                    length=rng.uniform(7.0, 14.0) if inside else rng.uniform(9.0, 22.0),
                    width=rng.uniform(3.0, 5.0) if inside else rng.uniform(4.0, 8.0),
                    angle=rng.uniform(0.0, math.pi),
                    color=rng.choice(LEAF_COLORS),
                )
            )
        return leaves

    def _lay_roots(self, rng: RandomStream) -> list[Root]:
        roots = []
        for _ in range(7):
            edge = rng.randint(0, 3)
            if edge in (0, 1):
                x = rng.uniform(0.0, self._width)
                start = Vector2(x, -20.0 if edge == 0 else self._height + 20.0)
            else:
                y = rng.uniform(0.0, self._height)
                start = Vector2(-20.0 if edge == 2 else self._width + 20.0, y)
            end = start + Vector2(
                rng.uniform(-220.0, 220.0), rng.uniform(-220.0, 220.0)
            )
            roots.append(Root(start=start, end=end, width=rng.randint(9, 18)))
        return roots

    def _grow_mushrooms(self, rng: RandomStream) -> list[Mushroom]:
        mushrooms = []
        margin = self._arena.inflate(72, 72)
        attempts = 0
        while len(mushrooms) < 18 and attempts < 400:
            attempts += 1
            position = Vector2(
                rng.uniform(16.0, self._width - 16.0),
                rng.uniform(16.0, self._height - 16.0),
            )
            # Outside the play area, but hugging it: the fungi are what
            # light the arena's edges.
            if self._arena.contains_point(position):
                continue
            if not margin.contains_point(position):
                continue
            mushrooms.append(
                Mushroom(
                    position=position,
                    radius=rng.uniform(5.0, 10.0),
                    phase=rng.uniform(0.0, math.tau),
                    color=AMBER if rng.random() > 0.35 else TEAL,
                )
            )
        return mushrooms

    def lights(self) -> list[tuple[Vector2, Color, float]]:
        """Return the fungi as (position, colour, radius) light sources.

        The scene turns these into light entities. Kept here because the
        positions are generated here, and a light that does not sit on its
        mushroom is worse than no light at all.
        """
        return [(m.position, m.color, 26.0 + m.radius * 5.0) for m in self.mushrooms]


def draw_ground(
    renderer: IRenderer,
    backdrop: Backdrop,
    *,
    offset: Vector2,
    width: int,
    height: int,
) -> None:
    """Draw the bare soil and the roots under everything else.

    Split from `draw_litter` so the arena floor can be laid between them:
    the litter belongs *on* the playfield, not under it, and drawing the
    floor last buried every leaf inside the arena.

    Args:
        renderer: Target renderer.
        backdrop: The generated floor.
        offset: Screen shake offset.
        width: Window width.
        height: Window height.
    """
    renderer.draw_rect(Rect(0, 0, width, height), SOIL)

    for root in backdrop.roots:
        renderer.draw_line(
            root.start + offset, root.end + offset, Color(24, 20, 16), root.width
        )

    renderer.end_frame()


def draw_litter(
    renderer: IRenderer, backdrop: Backdrop, *, time: float, offset: Vector2
) -> None:
    """Draw the dry leaves and the fungi, over the soil and the arena floor.

    Args:
        renderer: Target renderer.
        backdrop: The generated floor.
        time: Seconds since the scene started, for the fungi's pulse.
        offset: Screen shake offset.
    """
    for leaf in backdrop.leaves:
        half = Vector2(math.cos(leaf.angle), math.sin(leaf.angle)) * (leaf.length / 2)
        centre = leaf.position + offset
        renderer.draw_line(centre - half, centre + half, leaf.color, int(leaf.width))

    # The leaves are lines and the caps are circles, so without a flush
    # here every leaf in the frame would lie on top of every cap.
    renderer.end_frame()

    for mushroom in backdrop.mushrooms:
        pulse = 0.75 + 0.25 * math.sin(time * 1.7 + mushroom.phase)
        centre = mushroom.position + offset
        stem_width = max(2, int(mushroom.radius * 0.5))
        # A rect, not a line, so it stays under its own cap: rects flush
        # before circles, lines after them.
        renderer.draw_rect(
            Rect(
                int(centre.x - stem_width / 2),
                int(centre.y),
                stem_width,
                int(mushroom.radius * 2.2),
            ),
            Color(40, 36, 30),
        )
        renderer.draw_circle(
            centre,
            mushroom.radius * (0.9 + 0.1 * pulse),
            _scaled(mushroom.color, pulse),
        )


def draw_owl(
    renderer: IRenderer, backdrop: Backdrop, *, time: float, offset: Vector2
) -> None:
    """Draw the owl watching from the canopy.

    The GDD's predator, present here only as a witness: it does not hunt
    in this build, so it is drawn as the reference art has it -- a neon
    outline in the dark, blinking now and then.

    Args:
        renderer: Target renderer.
        backdrop: Supplies the owl's position.
        time: Seconds since the scene started, driving the blink.
        offset: Screen shake offset.
    """
    centre = backdrop.owl_position + offset
    outline = Color(120, 180, 190, 210)

    renderer.draw_circle(centre + Vector2(0, 14), 26.0, outline, width=2)
    renderer.draw_circle(centre + Vector2(0, -12), 19.0, outline, width=2)
    for side in (-1.0, 1.0):
        tuft = centre + Vector2(13.0 * side, -26.0)
        renderer.draw_line(tuft, tuft + Vector2(5.0 * side, -9.0), outline, 2)
        renderer.draw_line(
            centre + Vector2(12.0 * side, 36.0),
            centre + Vector2(16.0 * side, 42.0),
            outline,
            2,
        )

    # Two blinks a cycle, a long way apart: a steady blink reads as a
    # pulsing light rather than as something alive.
    cycle = math.fmod(time, 5.2)
    blinking = cycle < 0.12 or 0.30 < cycle < 0.40
    for side in (-1.0, 1.0):
        eye = centre + Vector2(7.5 * side, -13.0)
        if blinking:
            renderer.draw_line(eye - Vector2(4, 0), eye + Vector2(4, 0), outline, 2)
        else:
            renderer.draw_circle(eye, 5.0, EYE_GOLD)
            renderer.draw_circle(eye, 2.0, VOID)

    renderer.end_frame()


def draw_arena(
    renderer: IRenderer,
    arena: Rect,
    *,
    time: float,
    offset: Vector2,
    storm: float,
) -> None:
    """Draw the play area's floor and its frame.

    Args:
        renderer: Target renderer.
        arena: The play area in screen space.
        time: Seconds since the scene started, for the frame's shimmer.
        offset: Screen shake offset.
        storm: 0..1 storm intensity; the frame runs hotter in a downpour.
    """
    shifted = Rect(
        int(arena.x + offset.x), int(arena.y + offset.y), arena.width, arena.height
    )
    renderer.draw_rect(shifted, FLOOR)

    # A faint dot at each cell corner. Almost subliminal, but it is the
    # difference between guessing a turn and knowing it.
    grid = Color(TEAL_DIM.r, TEAL_DIM.g, TEAL_DIM.b, 26)
    for gx in range(0, arena.width + 1, CELL_SIZE):
        for gy in range(0, arena.height + 1, CELL_SIZE):
            renderer.draw_circle(Vector2(shifted.x + gx, shifted.y + gy), 1.0, grid)

    shimmer = 0.72 + 0.28 * math.sin(time * 2.0)
    frame = _scaled(TEAL, (0.55 + 0.45 * storm) * shimmer)
    renderer.draw_rect(shifted.inflate(6, 6), frame, width=2)

    # Corner brackets, as in the reference art's HUD frame.
    length = 26
    for cx, sx in ((shifted.left - 3, 1), (shifted.right + 3, -1)):
        for cy, sy in ((shifted.top - 3, 1), (shifted.bottom + 3, -1)):
            corner = Vector2(cx, cy)
            renderer.draw_line(corner, corner + Vector2(length * sx, 0), TEAL, 3)
            renderer.draw_line(corner, corner + Vector2(0, length * sy), TEAL, 3)

    renderer.end_frame()


def draw_food(
    renderer: IRenderer,
    foods: list[tuple[str, Vector2, float]],
    *,
    time: float,
    offset: Vector2,
) -> None:
    """Draw every piece of prey on the board.

    Args:
        renderer: Target renderer.
        foods: `(food_type, screen centre, phase)` per item. The phase
            staggers the idle bob so a board full of prey does not
            breathe in unison.
        time: Seconds since the scene started.
        offset: Screen shake offset.
    """
    placed = []
    for food_type, centre, phase in foods:
        bob = math.sin(time * 3.1 + phase) * 2.0
        placed.append(
            (
                food_type,
                centre + offset + Vector2(0, bob),
                0.82 + 0.18 * math.sin(time * 5.0 + phase),
                time + phase,
            )
        )

    # Limbs before bodies, with a flush between: legs and star arms are
    # lines, bodies are circles, and unflushed the lines would be drawn
    # over the shells they are supposed to emerge from.
    for food_type, position, pulse, clock in placed:
        if food_type == "beetle":
            _draw_beetle_legs(renderer, position, clock)
        elif food_type == "star":
            _draw_star_arms(renderer, position, pulse, clock)
    renderer.end_frame()

    for food_type, position, pulse, clock in placed:
        if food_type == "beetle":
            _draw_beetle_body(renderer, position, pulse)
        elif food_type == "larva":
            _draw_grub(renderer, position, pulse, clock)
        else:
            _draw_star_core(renderer, position, pulse)
    renderer.end_frame()


def _draw_beetle_legs(renderer: IRenderer, position: Vector2, clock: float) -> None:
    """Six twitching legs, drawn under the shell."""
    radius = CELL_SIZE * 0.38
    for index in range(3):
        y = position.y + (index - 1) * radius * 0.55
        twitch = math.sin(clock * 9.0 + index) * 1.5
        for side in (-1.0, 1.0):
            renderer.draw_line(
                Vector2(position.x + radius * 0.6 * side, y),
                Vector2(position.x + (radius * 1.5) * side, y + twitch),
                Color(120, 22, 16),
                2,
            )


def _draw_beetle_body(renderer: IRenderer, position: Vector2, pulse: float) -> None:
    """A red beetle: shell, wing split, head, antennae."""
    color = FOOD_COLORS["beetle"]
    radius = CELL_SIZE * 0.38

    renderer.draw_circle(position, radius * 1.05, Color(90, 14, 10))
    renderer.draw_circle(position, radius, _scaled(color, pulse))
    renderer.draw_line(
        position - Vector2(0, radius * 0.8),
        position + Vector2(0, radius * 0.9),
        Color(70, 10, 8),
        2,
    )
    renderer.draw_circle(position - Vector2(0, radius * 0.85), radius * 0.42, VOID)
    for side in (-1.0, 1.0):
        antenna = position + Vector2(radius * 0.3 * side, -radius * 1.1)
        renderer.draw_line(
            antenna, antenna + Vector2(radius * 0.5 * side, -radius * 0.6), color, 2
        )


def _draw_grub(
    renderer: IRenderer, position: Vector2, pulse: float, clock: float
) -> None:
    """A cream grub: three tapering body balls, curled into a comma."""
    curl = math.sin(clock * 2.4) * 0.5
    for index, scale in enumerate((0.40, 0.33, 0.24)):
        angle = 2.2 + curl + index * 0.75
        centre = position + Vector2(math.cos(angle), math.sin(angle)) * (index * 6.0)
        renderer.draw_circle(
            centre, CELL_SIZE * scale, _scaled(CREAM, pulse - index * 0.08)
        )
    renderer.draw_circle(position - Vector2(2.0, 2.0), 2.0, Color(60, 56, 48))


def _draw_star_arms(
    renderer: IRenderer, position: Vector2, pulse: float, clock: float
) -> None:
    """The star's four arms, turning slowly under its core."""
    color = FOOD_COLORS["star"]
    arm = CELL_SIZE * (0.52 + 0.08 * pulse)
    for index in range(4):
        angle = clock * 1.3 + index * (math.pi / 2)
        reach = Vector2(math.cos(angle), math.sin(angle)) * arm
        renderer.draw_line(position - reach, position + reach, _scaled(color, 0.7), 2)


def _draw_star_core(renderer: IRenderer, position: Vector2, pulse: float) -> None:
    """The star's hot centre."""
    renderer.draw_circle(position, CELL_SIZE * 0.30 * pulse, FOOD_COLORS["star"])
    renderer.draw_circle(position, CELL_SIZE * 0.16 * pulse, Color(255, 255, 255))


def draw_snake(
    renderer: IRenderer,
    segments: list[Vector2],
    *,
    time: float,
    offset: Vector2,
    flashing: bool,
    star: float,
    tongue: bool,
) -> None:
    """Draw the snake from tail to head.

    Args:
        renderer: Target renderer.
        segments: Screen-space centres, head first. Already interpolated
            between grid cells by the caller -- the grid tick is four
            steps a second, and drawing it raw is the single biggest
            reason the snake used to look like a spreadsheet.
        time: Seconds since the scene started, driving the body's wave.
        offset: Screen shake offset.
        flashing: Whether the snake is in its post-hit invincibility
            blink.
        star: 0..1 star-effect strength; adds a halo and heat.
        tongue: Whether the tongue is flicking this frame.
    """
    if not segments:
        return

    count = len(segments)
    spine = _spine(segments, offset, time, star)
    radii = [
        CELL_SIZE * 0.44 * (1.0 - 0.36 * (index / max(count - 1, 1)))
        for index in range(count)
    ]

    # The body is a tube, not a row of beads: consecutive centres are a
    # whole cell apart, so the segments are joined with capsules and the
    # circles only round off the joints. Drawn in two passes -- every
    # outline first, then every band -- because one segment's outline
    # would otherwise cut into the band of the segment before it.
    for widen in (3.0, 0.0):
        outline = widen > 0.0
        for index in range(count - 1, 0, -1):
            radius = radii[index] + widen
            band = VOID if outline else _band_color(index, flashing)
            renderer.draw_line(spine[index], spine[index - 1], band, int(radius * 2))
            renderer.draw_circle(spine[index], radius, band)
        # The outline is wider than the band it surrounds, and it is a
        # line: unflushed it would be drawn over every band circle.
        renderer.end_frame()

    for index in range(count - 1, 0, -1):
        if _band_color(index, flashing) is CORAL_RED:
            # A hot centre inside the red bands only: it is what the bloom
            # threshold catches, and it is why the snake glows and the
            # litter does not.
            renderer.draw_line(
                spine[index],
                spine[index - 1],
                CORAL_RED_CORE,
                int(radii[index] * 0.9),
            )
        if star > 0.0:
            renderer.draw_circle(
                spine[index],
                radii[index] + 4.0,
                _scaled(HEAD_GOLD, 0.4 * star),
                width=2,
            )

    renderer.end_frame()
    _draw_head(
        renderer,
        spine[0],
        _direction(spine[1] if count > 1 else spine[0], spine[0]),
        flashing=flashing,
        star=star,
        tongue=tongue,
        time=time,
    )


def _spine(
    segments: list[Vector2], offset: Vector2, time: float, star: float
) -> list[Vector2]:
    """Return the drawn centreline: shaken, and slithering.

    The wave runs *along* the body -- each segment displaced perpendicular
    to its own direction of travel, one phase step behind the segment
    ahead -- which is what makes a snake look like it is pushing itself
    forward rather than vibrating.
    """
    count = len(segments)
    spine = []
    for index, centre in enumerate(segments):
        ahead = segments[max(index - 1, 0)]
        behind = segments[min(index + 1, count - 1)]
        along = _direction(behind, ahead)
        perp = Vector2(-along.y, along.x)
        # The head leads; the tail has the least freedom to wander.
        reach = (1.6 + 1.4 * star) * min(1.0, index / 2.0)
        spine.append(
            centre + offset + perp * (math.sin(time * 7.0 - index * 0.8) * reach)
        )
    return spine


def _draw_head(
    renderer: IRenderer,
    centre: Vector2,
    facing: Vector2,
    *,
    flashing: bool,
    star: float,
    tongue: bool,
    time: float,
) -> None:
    """Draw the head: skull, cocar, eyes, and the flicking tongue."""
    perp = Vector2(-facing.y, facing.x)
    radius = CELL_SIZE * 0.52

    # The cocar the window title promises, and the reference art wears:
    # three feathers fanned back from the crown.
    # Fanned wide, because a feather laid along the body is a feather
    # hidden under the body; the middle one is longer so it clears the
    # first segment instead of disappearing into it.
    feathers = ((-0.95, CREAM, 1.9), (0.0, CORAL_RED, 2.5), (0.95, TEAL, 1.9))
    for angle, color, reach in feathers:
        direction = _rotate(-facing, angle)
        base = centre + direction * (radius * 0.5)
        tip = centre + direction * (radius * reach)
        renderer.draw_line(base, tip, color, 3)
        renderer.draw_circle(tip, 2.5, _scaled(color, 1.0))

    renderer.draw_circle(centre, radius + 3.5, VOID)
    # Dark, like the reference art's head, rather than another warm band:
    # a gold head sat directly in front of a red band and the two merged
    # into one orange lozenge with no face on it. What reads as the head
    # is the crown stripe and the eyes.
    renderer.draw_circle(
        centre, radius, Color(255, 255, 255) if flashing else HEAD_DARK
    )
    if star > 0.0:
        renderer.draw_circle(centre, radius + 6.0, _scaled(TEAL, 0.5 * star), width=2)

    crown = centre - facing * (radius * 0.45)
    renderer.draw_line(
        crown - perp * (radius * 0.8), crown + perp * (radius * 0.8), CREAM, 5
    )

    # Snout: a smaller ball pushed forward, which is all it takes to read
    # as a head with a direction rather than as a ball.
    snout = centre + facing * (radius * 0.62)
    renderer.draw_circle(snout, radius * 0.5, HEAD_GOLD)

    for side in (-1.0, 1.0):
        eye = centre + facing * (radius * 0.1) + perp * (radius * 0.48 * side)
        renderer.draw_circle(eye, radius * 0.3, EYE_GOLD)
        renderer.draw_circle(eye + facing * (radius * 0.09), radius * 0.14, VOID)

    if tongue:
        root = snout + facing * (radius * 0.45)
        fork = root + facing * (radius * 0.55)
        renderer.draw_line(root, fork, Color(255, 60, 70), 2)
        for side in (-1.0, 1.0):
            renderer.draw_line(
                fork,
                fork + _rotate(facing, 0.5 * side) * (radius * 0.4),
                Color(255, 60, 70),
                2,
            )

    renderer.end_frame()
    _ = time


def draw_hud_panels(
    renderer: IRenderer,
    *,
    arena: Rect,
    lives: int,
    star_fraction: float,
    width: int,
) -> None:
    """Draw the HUD's shapes: life pips and the star meter.

    Split from the text because of the flush order described in this
    module's docstring -- shapes have to be queued before the scene's
    `end_frame()`, text drawn after it.

    Args:
        renderer: Target renderer.
        arena: The play area, which the HUD aligns to.
        lives: Remaining lives, drawn as coiled-snake pips.
        star_fraction: 0..1 of the star effect remaining; 0 hides the meter.
        width: Window width.
    """
    for index in range(lives):
        pip = Vector2(arena.left + 92 + index * 22, 58)
        renderer.draw_circle(pip, 8.0, VOID)
        renderer.draw_circle(pip, 6.5, CORAL_RED)
        renderer.draw_circle(pip, 3.0, HEAD_GOLD)

    if star_fraction > 0.0:
        meter = Rect(width - 250, 50, 180, 8)
        renderer.draw_rect(meter, Color(30, 46, 48))
        renderer.draw_rect(
            Rect(meter.x, meter.y, int(meter.width * star_fraction), meter.height),
            TEAL,
        )

    renderer.end_frame()


def draw_hud_text(
    renderer: IRenderer,
    *,
    arena: Rect,
    score: int,
    lives: int,
    star_fraction: float,
    storming: bool,
    width: int,
    height: int,
) -> None:
    """Draw the HUD's text, after the scene has flushed its shapes.

    Args:
        renderer: Target renderer.
        arena: The play area, which the HUD aligns to.
        score: Current score.
        lives: Remaining lives, labelled beside the pips.
        star_fraction: 0..1 of the star effect remaining.
        storming: Whether the downpour is running, for the weather line.
        width: Window width.
        height: Window height.
    """
    renderer.draw_text("SCORE", Vector2(arena.left, 30), TEAL_DIM, size=13)
    renderer.draw_text(f"{score:06d}", Vector2(arena.left, 46), CREAM, size=24)
    renderer.draw_text("VIDAS", Vector2(arena.left + 92, 30), TEAL_DIM, size=13)
    _ = lives

    renderer.draw_text(
        "TEMPESTADE" if storming else "GAROA",
        Vector2(width - 250, 28),
        AMBER if storming else TEAL_DIM,
        size=14,
    )
    if star_fraction > 0.0:
        renderer.draw_text("IMORTAL", Vector2(width - 250, 64), HEAD_GOLD, size=16)

    renderer.draw_text(
        "SETAS mover    ESC menu",
        Vector2(arena.left, height - 42),
        TEAL_DIM,
        size=14,
    )


# ---- helpers -------------------------------------------------------


def _band_color(index: int, flashing: bool) -> Color:
    """Return a body segment's band colour, cycling red -> black -> cream."""
    if flashing:
        return Color(255, 255, 255)
    # One cell per band. Two-cell bands are closer to the reference art,
    # but a five-segment snake then never shows a cream one, and the
    # three-colour pattern is the thing the game is named after.
    return (CORAL_RED, BAND_BLACK, CREAM)[(index - 1) % 3]


def _scaled(color: Color, factor: float) -> Color:
    """Return `color` with its channels scaled, clamped to 0..255."""
    clamp = lambda value: max(0, min(255, int(value)))  # noqa: E731
    return Color(
        clamp(color.r * factor),
        clamp(color.g * factor),
        clamp(color.b * factor),
        color.a,
    )


def _direction(start: Vector2, end: Vector2) -> Vector2:
    """Return the unit vector from `start` to `end`, or right if coincident."""
    delta = end - start
    if delta.x == 0.0 and delta.y == 0.0:
        return Vector2(1.0, 0.0)
    return delta.normalize()


def _rotate(vector: Vector2, radians: float) -> Vector2:
    """Rotate a vector by an angle."""
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    return Vector2(
        vector.x * cos_a - vector.y * sin_a, vector.x * sin_a + vector.y * cos_a
    )
