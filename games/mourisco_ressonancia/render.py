"""Mourisco: Ressonância - Presentation.

Drawing here works differently from every other demo in the repo, because
the compositor multiplies the world by the light map: **anything the pulse
has not lit is black no matter what colour it was drawn in.** So the cave
is drawn at full albedo and the lighting decides what the player sees --
the reveal is not a drawing trick layered on top, it is the renderer.

What is drawn per tile is still modulated by remembered brightness, so a
surface the pulse swept a moment ago reads as a fading after-image rather
than snapping off the instant the wavefront passes.
"""

from __future__ import annotations

import math

from games.mourisco_ressonancia.cave import TILE, CaveLayout, Formation
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import IRenderer

# The palette is cold and narrow on purpose: the cave's only real colour
# comes from the pulse lighting it, so the albedo underneath needs to be
# neutral enough to take that tint.
ROCK = Color(120, 138, 158)
ROCK_EDGE = Color(178, 208, 232)
ROCK_DEEP = Color(58, 70, 88)
FORMATION = Color(140, 160, 182)
FLOOR_WET = Color(96, 126, 150)
ROCK_CORE = Color(74, 92, 114)
ROCK_SCREAM = Color(150, 118, 190)
EDGE_SCREAM = Color(206, 176, 244)
MOTE = Color(186, 228, 246)

PLAYER_BODY = Color(46, 42, 52)
PLAYER_RIM = Color(150, 214, 236)
PLAYER_EYE = Color(226, 246, 255)
PLAYER_HURT = Color(255, 120, 110)

SPIDER_BODY = Color(92, 62, 58)
SPIDER_MARK = Color(214, 136, 92)
BAT_BODY = Color(118, 96, 124)

EXIT_GLOW = Color(150, 240, 196)

_EDGE_THICKNESS = 3


def _shift(rect: Rect, offset: Vector2) -> Rect:
    return Rect(
        int(rect.x - offset.x),
        int(rect.y - offset.y),
        int(rect.width),
        int(rect.height),
    )


def _tile_tint(cell: tuple[int, int]) -> float:
    """A stable per-tile brightness jitter, in roughly 0.82..1.12.

    Hashed from the coordinate rather than drawn from a stream, so it is
    the same every frame for a given tile without storing anything: rock
    that shimmers as it is re-lit would look like noise, not stone.
    """
    h = (cell[0] * 73_856_093) ^ (cell[1] * 19_349_663)
    return 0.82 + ((h >> 8) & 0xFF) / 255.0 * 0.30


def draw_cave(
    renderer: IRenderer,
    layout: CaveLayout,
    faces: list[tuple[tuple[int, int], Rect]],
    formations: list[Formation],
    brightness_of,
    scream_of,
    offset: Vector2,
) -> None:
    """Draw the rock surfaces the pulse currently remembers.

    Only exposed faces are considered (a tile buried in rock can never be
    seen), and each is skipped entirely below a brightness threshold --
    both because it would composite to black anyway and because skipping
    keeps the draw count proportional to what is actually visible.

    Each face is built from a dark body, an inset darker core, and a bright
    rim on whichever sides meet open air. The rim is what does the work:
    it is the edge between rock and void that makes a cave read as carved
    space rather than as a grid of squares.
    """
    for cell, rect in faces:
        lit = brightness_of(cell)
        if lit <= 0.02:
            continue
        lit = min(1.0, lit) * _tile_tint(cell)
        # A surface found by a scream keeps that call's violet, so the two
        # calls leave visibly different marks on the cave.
        violet = min(1.0, scream_of(cell))
        body_hue = ROCK.lerp(ROCK_SCREAM, violet)
        edge_hue = ROCK_EDGE.lerp(EDGE_SCREAM, violet)

        renderer.draw_rect(_shift(rect, offset), ROCK_DEEP.lerp(body_hue, lit))
        # A gently lighter core rather than a hard inset: too much
        # contrast here turned every surface into a tiled brick wall
        # instead of continuous rock.
        core = Rect(rect.x + 3, rect.y + 3, rect.width - 6, rect.height - 6)
        if core.width > 0 and core.height > 0:
            renderer.draw_rect(
                _shift(core, offset),
                ROCK_DEEP.lerp(body_hue.lerp(ROCK_CORE, 0.35), lit * 0.95),
            )

        x, y = cell
        edge = ROCK_DEEP.lerp(edge_hue, lit)
        if not layout.is_solid((x, y - 1)):
            renderer.draw_rect(
                _shift(Rect(rect.x, rect.y, rect.width, _EDGE_THICKNESS), offset), edge
            )
        if not layout.is_solid((x, y + 1)):
            renderer.draw_rect(
                _shift(
                    Rect(
                        rect.x,
                        rect.bottom - _EDGE_THICKNESS,
                        rect.width,
                        _EDGE_THICKNESS,
                    ),
                    offset,
                ),
                FLOOR_WET.lerp(ROCK_EDGE, lit),
            )
        if not layout.is_solid((x - 1, y)):
            renderer.draw_rect(
                _shift(Rect(rect.x, rect.y, _EDGE_THICKNESS, rect.height), offset), edge
            )
        if not layout.is_solid((x + 1, y)):
            renderer.draw_rect(
                _shift(
                    Rect(
                        rect.right - _EDGE_THICKNESS,
                        rect.y,
                        _EDGE_THICKNESS,
                        rect.height,
                    ),
                    offset,
                ),
                edge,
            )

    for formation in formations:
        cell = (int(formation.base.x // TILE), int(formation.base.y // TILE))
        lit = max(brightness_of(cell), brightness_of((cell[0], cell[1] - 1)))
        if lit <= 0.04:
            continue
        lit = min(1.0, lit)
        base = formation.base - offset
        tip = formation.tip - offset
        span = tip - base
        steps = 5
        for i in range(steps):
            t = i / steps
            # Taper toward the tip, and brighten: the point of a
            # stalactite catching the light is the readable part.
            width = max(1.0, formation.width * (1.0 - t * 0.85))
            colour = ROCK_DEEP.lerp(FORMATION, lit * (0.55 + 0.45 * t))
            centre = base.lerp(tip, t)
            renderer.draw_rect(
                Rect(
                    int(centre.x - width / 2),
                    int(centre.y),
                    max(1, int(width)),
                    max(1, int(abs(span.y) / steps) + 1),
                ),
                colour,
            )


def draw_atmosphere(
    renderer: IRenderer,
    motes: list[tuple[Vector2, float, float]],
    brightness_of,
    offset: Vector2,
    elapsed: float,
) -> None:
    """Drift dust motes through the lit air.

    Only drawn where the cave is currently remembered: a mote hanging in
    provably unlit air would be the one thing on screen the pulse had not
    revealed, which breaks the rule the whole game rests on.
    """
    for home, radius, phase in motes:
        drift = Vector2(
            math.sin(elapsed * 0.4 + phase) * 9.0,
            math.cos(elapsed * 0.29 + phase * 1.7) * 7.0
            - (elapsed * 6.0 + phase * 40) % 60.0,
        )
        point = home + drift
        cell = (int(point.x // TILE), int(point.y // TILE))
        lit = brightness_of(cell)
        if lit <= 0.12:
            continue
        shimmer = 0.55 + 0.45 * math.sin(elapsed * 2.2 + phase * 3.0)
        renderer.draw_circle(
            point - offset,
            radius,
            MOTE.lerp(ROCK_DEEP, 1.0 - min(1.0, lit) * shimmer),
        )


def draw_player(
    renderer: IRenderer,
    position: Vector2,
    facing: float,
    offset: Vector2,
    elapsed: float,
    calling: float,
    hurt: float = 0.0,
) -> None:
    """Draw the jaguarundi: a low, long silhouette with lit eyes.

    Drawn with a rim rather than a fill because the player is the one
    thing that must stay findable in a black cave -- the eyes are the
    anchor the player tracks, so they are always at least faintly lit.
    """
    screen = position - offset
    lean = 1.0 + 0.12 * calling
    body_w, body_h = 30.0 * lean, 15.0

    renderer.draw_circle(Vector2(screen.x, screen.y + 9), 12.0, Color(0, 0, 0, 90))

    renderer.draw_rect(
        Rect(
            int(screen.x - body_w / 2),
            int(screen.y - body_h / 2),
            int(body_w),
            int(body_h),
        ),
        PLAYER_BODY,
    )
    renderer.draw_circle(
        Vector2(screen.x + facing * body_w * 0.42, screen.y - 3), 8.5, PLAYER_BODY
    )
    # Tail, curling opposite the heading.
    tail_root = Vector2(screen.x - facing * body_w * 0.5, screen.y - 2)
    renderer.draw_line(
        tail_root,
        Vector2(tail_root.x - facing * 16, tail_root.y - 8 - 2 * math.sin(elapsed * 6)),
        PLAYER_BODY,
        width=4,
    )

    rim = PLAYER_RIM.lerp(Color(255, 255, 255), min(1.0, calling))
    if hurt > 0.0:
        rim = rim.lerp(PLAYER_HURT, min(1.0, hurt))
    renderer.draw_rect(
        Rect(
            int(screen.x - body_w / 2),
            int(screen.y - body_h / 2),
            int(body_w),
            2,
        ),
        rim,
    )
    eye = Vector2(screen.x + facing * body_w * 0.55, screen.y - 4)
    renderer.draw_circle(eye, 2.6 + 1.4 * calling, PLAYER_EYE)


def draw_spider(
    renderer: IRenderer,
    position: Vector2,
    lit: float,
    offset: Vector2,
    agitated: bool,
) -> None:
    """Draw a cave spider, visible only as far as it has been revealed."""
    if lit <= 0.05:
        return
    screen = position - offset
    body = SPIDER_BODY.lerp(SPIDER_MARK if agitated else ROCK_EDGE, min(1.0, lit))
    for i in range(4):
        angle = math.pi * (0.18 + 0.21 * i)
        for side in (-1.0, 1.0):
            leg = Vector2(
                screen.x + math.cos(angle) * 16.0 * side,
                screen.y - math.sin(angle) * 12.0,
            )
            renderer.draw_line(screen, leg, body, width=2)
    renderer.draw_circle(screen, 8.0, body)
    renderer.draw_circle(Vector2(screen.x, screen.y - 2), 3.0, SPIDER_MARK)


def draw_bat(
    renderer: IRenderer, position: Vector2, lit: float, offset: Vector2, phase: float
) -> None:
    """Draw a bat, wings beating on `phase`."""
    if lit <= 0.05:
        return
    screen = position - offset
    color = BAT_BODY.lerp(ROCK_EDGE, min(1.0, lit))
    flap = math.sin(phase) * 7.0
    renderer.draw_circle(screen, 4.0, color)
    renderer.draw_line(screen, Vector2(screen.x - 11, screen.y - flap), color, width=2)
    renderer.draw_line(screen, Vector2(screen.x + 11, screen.y - flap), color, width=2)


def draw_exit(
    renderer: IRenderer, position: Vector2, offset: Vector2, elapsed: float
) -> None:
    """Draw the way out.

    Always faintly visible, unlike everything else: a goal the player
    cannot find until they happen to ping it is not a goal, it is a maze.
    """
    screen = position - offset
    pulse = 0.6 + 0.4 * math.sin(elapsed * 2.4)
    renderer.draw_circle(screen, 16.0 + 3.0 * pulse, EXIT_GLOW.lerp(ROCK_DEEP, 0.45))
    renderer.draw_circle(screen, 8.0, EXIT_GLOW)
