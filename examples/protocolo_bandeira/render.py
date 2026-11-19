"""Protocolo Bandeira - every draw call the game makes.

The art direction is a cerrado clearing at dusk: red laterite baked all
day, cracked, littered with quartz and dry tussock, with a termite mound
the anteater is defending. Nothing here is a sprite; it is all circles,
capsules and lines, which is what the ModernGL shape shader draws in one
instanced call per shape type.

Three engine features do the work, and are worth knowing about before
changing anything here:

*Bloom* makes the heat. Rather than stacking translucent haloes by hand,
this module draws small, genuinely bright cores -- tracer heads, a
bomber's fuse, the muzzle flash -- and lets the bloom pass bleed them.
That is why a few colours look over-bright in isolation: they are input
to a threshold, not a final pixel. The earth deliberately sits under it.

*The light map* makes the dusk. Everything is multiplied by the lighting
pass's output, so the clearing is lit by a low sun plus whatever the fight
is throwing off. Drawing the soil brighter here does not brighten it on
screen; adding a light near it does.

*The heat haze* refracts the finished frame. It is a post-process, so
nothing in this module has to account for it -- but it is why the ground
detail is drawn at a scale coarse enough to survive a few pixels of
displacement.

Draw order is the one thing to be careful about, because it is not the
order of these calls. The ModernGL backend queues shape primitives into
one bucket per *shape type* and flushes them at `end_frame()` as one
instanced draw call each, rects then circles then lines. Submission order
holds within a bucket and not at all between them: every line in a frame
lands on top of every circle in it, whenever it was submitted. So each
function here ends by flushing, and the ones drawing a crowd do it in
layers -- every enemy's legs, flush, every enemy's body -- rather than one
creature at a time, which would cost a flush per enemy. Text is the other
half of the same rule: `draw_text` draws immediately, so the HUD's text is
written after the scene's last flush.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import IRenderer

# ---- Palette -------------------------------------------------------
# Sunset over red earth. Everything on the ground sits under the bloom
# threshold; everything the fight produces sits over it.

SKY_HIGH = Color(48, 28, 54)
SKY_MID = Color(96, 42, 52)
SKY_LOW = Color(148, 68, 44)

EARTH_DEEP = Color(44, 20, 15)
EARTH = Color(88, 38, 26)
CRACK = Color(58, 25, 18)
DUST_PALE = Color(158, 122, 86)

ROCK = Color(74, 58, 52)
ROCK_LIT = Color(108, 88, 74)
GRASS = Color(104, 88, 46)
GRASS_DRY = Color(142, 118, 60)
MOUND = Color(104, 50, 30)
MOUND_LIT = Color(138, 70, 40)

# The anteater. Grey fur, and the wedge across the shoulder that gives the
# tamanduá-bandeira its name -- the "flag" it carries.
FUR_DARK = Color(52, 50, 58)
FUR = Color(116, 112, 120)
FUR_LIGHT = Color(158, 154, 162)
BAND_WHITE = Color(198, 196, 202)
BAND_BLACK = Color(28, 26, 32)
CLAW = Color(226, 222, 210)

ANT_BODY = Color(172, 38, 30)
ANT_DARK = Color(108, 22, 18)
ANT_LEG = Color(72, 18, 14)

BEETLE = Color(56, 62, 98)
BEETLE_LIT = Color(94, 104, 152)
BEETLE_EYE = Color(150, 255, 110)

BOMBER_SHELL = Color(128, 62, 26)
BOMBER_HOT = Color(255, 126, 38)
BOMBER_CORE = Color(255, 228, 160)

PLAYER_SHOT = Color(255, 206, 92)
PLAYER_SHOT_CORE = Color(255, 248, 214)
ENEMY_SHOT = Color(140, 240, 96)
ENEMY_SHOT_CORE = Color(228, 255, 200)

HIT_WHITE = Color(255, 252, 244)
# What the player washes to while invincible after a hit. Not HIT_WHITE:
# a pure white wash over the whole animal erases it, and with bloom on top
# the player becomes a glowing blob exactly when they most need to see
# where they are. A hot tint keeps the silhouette.
HURT_TINT = Color(255, 176, 150)
BLOOD = Color(198, 62, 40)

PANEL = Color(22, 13, 14)
PANEL_EDGE = Color(128, 66, 40)
PANEL_EDGE_HOT = Color(206, 112, 54)
TEXT = Color(244, 230, 204)
TEXT_DIM = Color(146, 118, 98)
GOLD = Color(255, 198, 78)
HEALTH_FULL = Color(224, 62, 44)
HEALTH_LOW = Color(255, 176, 60)
COMBO_COLOR = Color(255, 232, 140)


@dataclass(slots=True)
class Rock:
    """A quartz pebble: a lit cap over a shadowed base."""

    position: Vector2
    radius: float


@dataclass(slots=True)
class Tuft:
    """A clump of dry grass, stored as the blades' shared base."""

    position: Vector2
    blades: tuple[tuple[float, float], ...]  # (angle, length) per blade
    color: Color


@dataclass(slots=True)
class Crack:
    """One fissure in the baked earth, as a run of joined points."""

    points: tuple[Vector2, ...]
    width: int


@dataclass(slots=True)
class Mound:
    """A termite mound -- the thing worth defending, and cover to run past."""

    position: Vector2
    radius: float


class Backdrop:
    """The generated clearing: cracks, pebbles, tussock and mounds.

    Scattered once at construction and never regenerated, so the ground is
    a fixed place the fight happens in rather than a field that churns
    under it.
    """

    def __init__(
        self,
        width: int,
        height: int,
        arena: Rect,
        rng: RandomStream | None = None,
    ) -> None:
        """Scatter the clearing.

        Args:
            width: Window width in pixels.
            height: Window height in pixels.
            arena: The play area; mounds keep clear of its centre so the
                player never starts inside one.
            rng: Stream driving the scatter. None for an unseeded run.
        """
        self._width = width
        self._height = height
        self._arena = arena
        rng = rng if rng is not None else RandomStream()

        self.cracks = self._split_earth(rng)
        self.rocks = self._scatter_rocks(rng)
        self.tufts = self._scatter_tufts(rng)
        self.mounds = self._raise_mounds(rng)

    def _split_earth(self, rng: RandomStream) -> list[Crack]:
        """Run fissures across the floor, each a drunkard's walk."""
        cracks = []
        for _ in range(16):
            x = rng.uniform(self._arena.left, self._arena.right)
            y = rng.uniform(self._arena.top, self._arena.bottom)
            angle = rng.uniform(0.0, math.tau)
            points = [Vector2(x, y)]

            # Long, gently-turning runs: a short walk with sharp turns
            # reads as scattered debris rather than as a split in the ground.
            for _ in range(rng.randint(6, 11)):
                angle += rng.uniform(-0.5, 0.5)
                step = rng.uniform(18.0, 46.0)
                last = points[-1]
                points.append(
                    Vector2(
                        last.x + math.cos(angle) * step,
                        last.y + math.sin(angle) * step,
                    )
                )

            cracks.append(Crack(points=tuple(points), width=rng.randint(1, 2)))
        return cracks

    def _scatter_rocks(self, rng: RandomStream) -> list[Rock]:
        """Drop quartz pebbles over the whole frame, arena included."""
        return [
            Rock(
                position=Vector2(
                    rng.uniform(0.0, self._width), rng.uniform(0.0, self._height)
                ),
                radius=rng.uniform(2.0, 6.5),
            )
            for _ in range(70)
        ]

    def _scatter_tufts(self, rng: RandomStream) -> list[Tuft]:
        """Grow dry tussock, thickest around the edges of the clearing."""
        tufts = []
        for _ in range(54):
            # Biased outward: a squared roll pushes most tufts away from
            # the middle, so the arena floor stays readable.
            edge = rng.random() ** 0.5
            if rng.random() < 0.5:
                x = rng.uniform(0.0, self._width)
                y = (
                    self._arena.top * (1.0 - edge)
                    if rng.random() < 0.5
                    else self._height
                    - (self._height - self._arena.bottom) * (1.0 - edge)
                )
            else:
                x = (
                    self._arena.left * (1.0 - edge)
                    if rng.random() < 0.5
                    else self._width - (self._width - self._arena.right) * (1.0 - edge)
                )
                y = rng.uniform(0.0, self._height)

            blades = tuple(
                (
                    rng.uniform(-1.5, -1.64) + rng.uniform(-0.6, 0.6),
                    rng.uniform(9.0, 20.0),
                )
                for _ in range(rng.randint(3, 6))
            )
            tufts.append(
                Tuft(
                    position=Vector2(x, y),
                    blades=blades,
                    color=GRASS if rng.random() < 0.6 else GRASS_DRY,
                )
            )
        return tufts

    def _raise_mounds(self, rng: RandomStream) -> list[Mound]:
        """Raise termite mounds in the corners of the arena, clear of the middle."""
        # Placed on a jittered ring around the middle rather than by
        # rejection sampling: sampling the whole rectangle and rejecting
        # anything too close kept giving up against its attempt cap and
        # returning whatever it had, which read as a row along one edge.
        # A ring spreads them by construction, and the jitter keeps it
        # from reading as a ring.
        mounds = []
        centre = Vector2(
            self._arena.x + self._arena.width / 2,
            self._arena.y + self._arena.height / 2,
        )
        count = 5
        for index in range(count):
            angle = (index / count) * math.tau + rng.uniform(-0.35, 0.35)
            reach = rng.uniform(0.55, 0.88)
            position = Vector2(
                centre.x + math.cos(angle) * (self._arena.width / 2 - 70) * reach,
                centre.y + math.sin(angle) * (self._arena.height / 2 - 70) * reach,
            )
            mounds.append(Mound(position=position, radius=rng.uniform(17.0, 28.0)))
        return mounds


# ---- Ground --------------------------------------------------------


def draw_ground(
    renderer: IRenderer,
    backdrop: Backdrop,
    *,
    offset: Vector2,
    width: int,
    height: int,
    arena: Rect,
) -> None:
    """Lay the sky band, the earth, and the fissures across it.

    Args:
        renderer: Target renderer.
        backdrop: The generated clearing.
        offset: Screen shake offset.
        width: Window width.
        height: Window height.
        arena: The play area, drawn a shade lighter than its surroundings
            so the boundary reads without a drawn border.
    """
    renderer.draw_rect(Rect(0, 0, width, height), EARTH_DEEP)

    # A sunset behind the top HUD band: four stacked bands rather than a
    # gradient, because the shape shader has no interpolation across a
    # rect and four is enough to read as sky at this size.
    band = arena.top / 4.0
    for index, color in enumerate((SKY_HIGH, SKY_MID, SKY_LOW, EARTH_DEEP)):
        renderer.draw_rect(Rect(0, index * band, width, band + 1), color)

    renderer.draw_rect(
        Rect(arena.x + offset.x, arena.y + offset.y, arena.width, arena.height), EARTH
    )

    for crack in backdrop.cracks:
        for start, end in zip(crack.points, crack.points[1:], strict=False):
            renderer.draw_line(start + offset, end + offset, CRACK, crack.width)

    # One flush for both layers: the backend drains rects before lines,
    # which is exactly soil then fissures.
    renderer.end_frame()


def draw_scatter(renderer: IRenderer, backdrop: Backdrop, *, offset: Vector2) -> None:
    """Draw the pebbles, the tussock and the termite mounds.

    Args:
        renderer: Target renderer.
        backdrop: The generated clearing.
        offset: Screen shake offset.
    """
    for mound in backdrop.mounds:
        base = mound.position + offset
        renderer.draw_circle(base, mound.radius, EARTH_DEEP)
        renderer.draw_circle(base + Vector2(0, -3), mound.radius * 0.82, MOUND)
        renderer.draw_circle(base + Vector2(-2, -7), mound.radius * 0.55, MOUND_LIT)

    for rock in backdrop.rocks:
        centre = rock.position + offset
        renderer.draw_circle(centre, rock.radius, ROCK)
        renderer.draw_circle(centre + Vector2(-0.6, -0.9), rock.radius * 0.6, ROCK_LIT)

    renderer.end_frame()

    for tuft in backdrop.tufts:
        base = tuft.position + offset
        for angle, length in tuft.blades:
            tip = base + Vector2(math.cos(angle) * length, math.sin(angle) * length)
            renderer.draw_line(base, tip, tuft.color, 2)

    renderer.end_frame()


def draw_arena_edge(renderer: IRenderer, arena: Rect, *, offset: Vector2) -> None:
    """Outline the play area with a scuffed dust line.

    Args:
        renderer: Target renderer.
        arena: The play area.
        offset: Screen shake offset.
    """
    left, top = arena.left + offset.x, arena.top + offset.y
    right, bottom = arena.right + offset.x, arena.bottom + offset.y

    for start, end in (
        (Vector2(left, top), Vector2(right, top)),
        (Vector2(left, bottom), Vector2(right, bottom)),
        (Vector2(left, top), Vector2(left, bottom)),
        (Vector2(right, top), Vector2(right, bottom)),
    ):
        renderer.draw_line(start, end, DUST_PALE, 2)

    renderer.end_frame()


# ---- The anteater --------------------------------------------------


def draw_anteater(
    renderer: IRenderer,
    position: Vector2,
    angle: float,
    *,
    time: float,
    offset: Vector2,
    moving: bool,
    flashing: bool = False,
) -> None:
    """Draw the player: a giant anteater seen from above.

    Two layers, because the backend drains rects, then circles, then
    lines, and only a flush separates one drain from the next:

    1. The tail fan and the legs -- lines, flushed on their own so the
       body lands on top of them rather than under.
    2. The body, snout and claws (circles) together with the shoulder
       flag (lines), which need no flush between them: lines already
       drain after circles, which is exactly the order the marking wants.

    Args:
        renderer: Target renderer.
        position: Centre of the body, in screen space.
        angle: Facing, in radians.
        time: Seconds since the scene started, for the gait.
        offset: Screen shake offset.
        moving: Whether the player is walking, which drives the gait.
        flashing: Whether to wash the whole animal white -- invincibility
            after a hit.
    """
    centre = position + offset
    forward = Vector2(math.cos(angle), math.sin(angle))
    right = Vector2(-math.sin(angle), math.cos(angle))

    fur_dark = HURT_TINT if flashing else FUR_DARK
    fur = HURT_TINT if flashing else FUR
    fur_light = HURT_TINT if flashing else FUR_LIGHT

    # The gait: a slow sway of the whole body when standing, a faster one
    # when walking. It drives the tail and the legs off the same phase, so
    # the animal moves as one thing.
    rate = 9.0 if moving else 2.2
    swing = math.sin(time * rate) * (0.26 if moving else 0.07)

    # -- layer 1: the tail fan, then the legs ------------------------
    # The tail is half the silhouette from above and the single thing
    # that says "anteater" rather than "grey blob", so it is drawn larger
    # than the body it hangs off -- but kept dark, with only a couple of
    # lit strands, or it out-reads the animal in front of it.
    tail_base = centre - forward * 13
    for index in range(11):
        spread = (index - 5) / 5.0
        tail_angle = angle + math.pi + spread * 0.66 + swing * 0.6
        length = 48.0 - abs(spread) * 14.0
        tip = tail_base + Vector2(
            math.cos(tail_angle) * length, math.sin(tail_angle) * length
        )
        renderer.draw_line(tail_base, tip, fur_dark, 12)
        if index % 3 == 1:
            renderer.draw_line(tail_base + (tip - tail_base) * 0.45, tip, fur, 5)

    for side, phase in ((1.0, 0.0), (-1.0, math.pi)):
        for along in (8.0, -7.0):
            hip = centre + forward * along + right * (side * 8)
            step = math.sin(time * rate + phase + along) * (0.5 if moving else 0.12)
            foot = hip + right * (side * 12.0) + forward * (step * 6)
            renderer.draw_line(hip, foot, fur_dark, 7)

    renderer.end_frame()

    # -- layer 2: the body, the snout, and the flag over both --------
    for along, radius, color in (
        (-13.0, 13.0, fur_dark),
        (-4.0, 16.0, fur),
        (5.0, 14.0, fur),
        (13.0, 10.0, fur_light),
    ):
        renderer.draw_circle(centre + forward * along, radius, color)

    # The snout: a long taper, pale at the tip, and the thing the shots
    # come out of.
    for step in range(7):
        t = step / 6.0
        renderer.draw_circle(
            centre + forward * (18.0 + t * 27.0) + right * (swing * 3.5 * t),
            6.4 - t * 4.2,
            fur if t < 0.65 else fur_light,
        )

    renderer.draw_circle(centre + forward * 15 + right * 6, 1.9, BAND_BLACK)
    renderer.draw_circle(centre + forward * 15 - right * 6, 1.9, BAND_BLACK)

    claw_color = HURT_TINT if flashing else CLAW
    for side in (1.0, -1.0):
        renderer.draw_circle(
            centre + forward * 11 + right * (side * 12), 2.8, claw_color
        )

    # The flag: the dark wedge across one shoulder that the
    # tamanduá-bandeira is named for. Two lines rather than a chain of
    # circles -- a chain reads as a caterpillar sitting on the animal,
    # where a capsule reads as a marking on it. Submitted here, in the
    # same batch as the body, because lines drain after circles.
    band_white = HURT_TINT if flashing else BAND_WHITE
    band_black = BAND_BLACK
    shoulder = centre + forward * 7 + right * 3
    flank = centre - forward * 9 - right * 13
    renderer.draw_line(shoulder, flank, band_white, 12)
    renderer.draw_line(shoulder, flank, band_black, 10)

    renderer.end_frame()


def draw_muzzle_flash(
    renderer: IRenderer,
    position: Vector2,
    angle: float,
    strength: float,
    *,
    offset: Vector2,
) -> None:
    """Flare at the snout for the frames just after a shot.

    Deliberately over-bright: this is bloom input, and the halo on screen
    is the pass's work rather than a stack of translucent circles here.

    Args:
        renderer: Target renderer.
        position: Centre of the player's body.
        angle: Facing, in radians.
        strength: 0.0 to 1.0; the flash's own decay envelope.
        offset: Screen shake offset.
    """
    if strength <= 0.0:
        return

    forward = Vector2(math.cos(angle), math.sin(angle))
    muzzle = position + offset + forward * 50

    # Kept small on purpose: bloom is what makes this read as a flash, and
    # a large bright disc this close to the player bleeds back over the
    # animal until the anteater is a white silhouette of itself.
    renderer.draw_circle(muzzle, 7.0 * strength, PLAYER_SHOT)
    renderer.draw_circle(muzzle, 3.4 * strength, PLAYER_SHOT_CORE)
    renderer.end_frame()


# ---- The swarm -----------------------------------------------------


@dataclass(slots=True)
class EnemyView:
    """Everything `draw_enemies` needs about one enemy for one frame."""

    kind: str  # "chaser", "shooter" or "bomber"
    position: Vector2
    angle: float
    phase: float  # Per-enemy offset, so a swarm does not march in step.
    flash: float  # 0.0 to 1.0, fading after a hit.


def draw_enemies(
    renderer: IRenderer, enemies: list[EnemyView], *, time: float, offset: Vector2
) -> None:
    """Draw the whole swarm, in layers rather than one creature at a time.

    Legs for every enemy, then a flush, then every body: the backend
    batches by shape type, so drawing one complete creature at a time
    would need a flush per creature to keep its legs underneath it.

    Args:
        renderer: Target renderer.
        enemies: This frame's swarm.
        time: Seconds since the scene started, for the scuttle.
        offset: Screen shake offset.
    """
    if not enemies:
        return

    # -- legs and antennae ------------------------------------------
    for enemy in enemies:
        centre = enemy.position + offset
        forward = Vector2(math.cos(enemy.angle), math.sin(enemy.angle))
        right = Vector2(-math.sin(enemy.angle), math.cos(enemy.angle))
        scuttle = math.sin(time * 16.0 + enemy.phase)

        leg_color = _enemy_leg_color(enemy)
        for side, side_phase in ((1.0, 0.0), (-1.0, math.pi)):
            for index, along in enumerate((7.0, 0.0, -7.0)):
                hip = centre + forward * along + right * (side * 5)
                kick = math.sin(time * 16.0 + enemy.phase + side_phase + index) * 0.45
                foot = (
                    hip + right * (side * 13.5) + forward * (kick * 7.0 + along * 0.35)
                )
                renderer.draw_line(hip, foot, leg_color, 3)

        if enemy.kind != "bomber":
            for side in (1.0, -1.0):
                base = centre + forward * 11
                tip = base + forward * 10 + right * (side * (7.0 + scuttle * 1.8))
                renderer.draw_line(base, tip, leg_color, 2)

    renderer.end_frame()

    # -- bodies ------------------------------------------------------
    for enemy in enemies:
        centre = enemy.position + offset
        forward = Vector2(math.cos(enemy.angle), math.sin(enemy.angle))
        right = Vector2(-math.sin(enemy.angle), math.cos(enemy.angle))

        if enemy.kind == "shooter":
            _draw_beetle(renderer, centre, forward, right, enemy)
        elif enemy.kind == "bomber":
            _draw_bomber(renderer, centre, forward, enemy, time=time)
        else:
            _draw_ant(renderer, centre, forward, right, enemy)

    renderer.end_frame()


def _enemy_leg_color(enemy: EnemyView) -> Color:
    """Pick the leg colour for one enemy, washed out while it is flashing."""
    if enemy.flash > 0.5:
        return HIT_WHITE
    if enemy.kind == "shooter":
        return Color(30, 34, 56)
    if enemy.kind == "bomber":
        return Color(72, 34, 14)
    return ANT_LEG


def _draw_ant(
    renderer: IRenderer,
    centre: Vector2,
    forward: Vector2,
    right: Vector2,
    enemy: EnemyView,
) -> None:
    """A fire ant: gaster, thorax, head, in three shrinking beads."""
    body = HIT_WHITE if enemy.flash > 0.5 else ANT_BODY
    dark = HIT_WHITE if enemy.flash > 0.5 else ANT_DARK

    renderer.draw_circle(centre - forward * 11, 9.5, body)
    renderer.draw_circle(centre - forward * 11 - right * 2.5, 5.0, dark)
    renderer.draw_circle(centre, 6.5, dark)
    renderer.draw_circle(centre + forward * 10, 7.0, body)
    renderer.draw_circle(centre + forward * 12 + right * 2.8, 1.7, BAND_BLACK)
    renderer.draw_circle(centre + forward * 12 - right * 2.8, 1.7, BAND_BLACK)


def _draw_beetle(
    renderer: IRenderer,
    centre: Vector2,
    forward: Vector2,
    right: Vector2,
    enemy: EnemyView,
) -> None:
    """A shield beetle: a split carapace with a glowing eye between."""
    shell = HIT_WHITE if enemy.flash > 0.5 else BEETLE
    lit = HIT_WHITE if enemy.flash > 0.5 else BEETLE_LIT

    renderer.draw_circle(centre - forward * 2, 13.5, shell)
    for side in (1.0, -1.0):
        renderer.draw_circle(centre - forward * 3 + right * (side * 5.5), 8.0, lit)
    renderer.draw_circle(centre + forward * 11, 7.0, shell)
    renderer.draw_circle(centre + forward * 12, 3.0, BEETLE_EYE)


def _draw_bomber(
    renderer: IRenderer,
    centre: Vector2,
    forward: Vector2,
    enemy: EnemyView,
    *,
    time: float,
) -> None:
    """A bombardier: a swollen abdomen with a fuse that brightens as it closes."""
    shell = HIT_WHITE if enemy.flash > 0.5 else BOMBER_SHELL
    # The pulse is what warns the player: it is the only thing on the
    # field that throbs, and it is bright enough to bloom at the peak.
    pulse = 0.55 + 0.45 * math.sin(time * 9.0 + enemy.phase)

    renderer.draw_circle(centre - forward * 3, 14.5, shell)
    renderer.draw_circle(centre - forward * 4, 9.5 * (0.8 + pulse * 0.3), BOMBER_HOT)
    renderer.draw_circle(centre - forward * 4, 4.8 * pulse, BOMBER_CORE)
    renderer.draw_circle(centre + forward * 11, 6.5, shell)


# ---- Shots ---------------------------------------------------------


def draw_shots(
    renderer: IRenderer,
    shots: list[tuple[Vector2, Vector2, str]],
    *,
    offset: Vector2,
) -> None:
    """Draw every live projectile as a tracer: a streak behind a hot head.

    Args:
        renderer: Target renderer.
        shots: `(position, velocity, team)` per live projectile.
        offset: Screen shake offset.
    """
    if not shots:
        return

    for position, _velocity, team in shots:
        head = position + offset
        color = PLAYER_SHOT if team == "player" else ENEMY_SHOT
        core = PLAYER_SHOT_CORE if team == "player" else ENEMY_SHOT_CORE
        renderer.draw_circle(head, 4.5, color)
        renderer.draw_circle(head, 2.2, core)

    renderer.end_frame()

    for position, velocity, team in shots:
        head = position + offset
        color = PLAYER_SHOT if team == "player" else ENEMY_SHOT
        # A fixed fraction of velocity, so a fast shot streaks further --
        # which is the whole reason a tracer reads as speed.
        renderer.draw_line(head - velocity * 0.028, head, color, 3)

    renderer.end_frame()


def draw_spawn_warnings(
    renderer: IRenderer,
    warnings: list[tuple[Vector2, float]],
    *,
    offset: Vector2,
) -> None:
    """Ring the ground where an enemy is about to arrive.

    A telegraph, not decoration: enemies enter from off-screen, and
    without this the first thing the player knows about a bomber is the
    hit. The ring tightens as the spawn approaches.

    Args:
        renderer: Target renderer.
        warnings: `(position, progress)` per pending spawn, progress
            running 0.0 at the warning's start to 1.0 at the spawn.
        offset: Screen shake offset.
    """
    if not warnings:
        return

    for position, progress in warnings:
        centre = position + offset
        radius = 34.0 * (1.0 - progress) + 9.0
        alpha = int(90 + 165 * progress)
        renderer.draw_circle(centre, radius, Color(255, 120, 60, alpha), width=2)
        renderer.draw_circle(centre, 3.0, Color(255, 180, 90, alpha))

    renderer.end_frame()


# ---- HUD -----------------------------------------------------------


def draw_hud_panels(
    renderer: IRenderer,
    *,
    arena: Rect,
    width: int,
    height: int,
    health: float,
    max_health: float,
    combo: int,
    combo_fraction: float,
    wave_fraction: float,
) -> None:
    """Draw the arcade bezel: the shaped half of the HUD.

    Text is written separately, by `draw_hud_text`, because `draw_text`
    draws immediately and would land under any shape submitted after it.

    Args:
        renderer: Target renderer.
        arena: The play area the bands sit above and below.
        width: Window width.
        height: Window height.
        health: The player's current health.
        max_health: The player's maximum health.
        combo: Current kill chain.
        combo_fraction: How much of the combo window is left, 0.0 to 1.0.
        wave_fraction: Fraction of the current wave still standing.
    """
    top_h = arena.top - 8
    bottom_y = arena.bottom + 8

    renderer.draw_rect(Rect(0, 0, width, top_h), PANEL)
    renderer.draw_rect(Rect(0, top_h - 2, width, 2), PANEL_EDGE)
    renderer.draw_rect(Rect(0, bottom_y, width, height - bottom_y), PANEL)
    renderer.draw_rect(Rect(0, bottom_y, width, 2), PANEL_EDGE)

    # -- portrait box -----------------------------------------------
    renderer.draw_rect(Rect(14, 12, 56, 56), Color(38, 20, 18))
    renderer.draw_rect(Rect(14, 12, 56, 2), PANEL_EDGE_HOT)
    renderer.draw_rect(Rect(14, 66, 56, 2), PANEL_EDGE_HOT)
    renderer.draw_rect(Rect(14, 12, 2, 56), PANEL_EDGE_HOT)
    renderer.draw_rect(Rect(68, 12, 2, 56), PANEL_EDGE_HOT)

    # -- health pips, one per point, arcade style --------------------
    pips = int(round(max_health))
    for index in range(pips):
        x = 84 + index * 22
        filled = index < int(math.ceil(health))
        low = health <= max_health * 0.34
        renderer.draw_rect(Rect(x, 44, 18, 16), Color(52, 24, 22))
        if filled:
            renderer.draw_rect(
                Rect(x + 2, 46, 14, 12), HEALTH_LOW if low else HEALTH_FULL
            )

    # -- wave meter: what is left of the wave, draining right to left --
    meter = Rect(width - 232, 46, 200, 10)
    renderer.draw_rect(meter, Color(48, 26, 20))
    remaining = max(0.0, min(1.0, wave_fraction))
    if remaining > 0.0:
        renderer.draw_rect(
            Rect(meter.x, meter.y, meter.width * remaining, meter.height), GOLD
        )

    # -- combo meter, bottom band ------------------------------------
    if combo > 1:
        bar = Rect(width / 2 - 90, bottom_y + 30, 180, 8)
        renderer.draw_rect(bar, Color(48, 26, 20))
        renderer.draw_rect(
            Rect(bar.x, bar.y, bar.width * max(0.0, combo_fraction), bar.height),
            COMBO_COLOR,
        )

    renderer.end_frame()

    # The portrait itself: a tiny anteater head, drawn as circles over the
    # box, after the rects have flushed.
    head = Vector2(42, 40)
    renderer.draw_circle(head + Vector2(-6, 2), 11.0, FUR)
    renderer.draw_circle(head + Vector2(-9, -2), 8.0, FUR_LIGHT)
    for step in range(5):
        t = step / 4.0
        renderer.draw_circle(head + Vector2(2 + t * 15, 4 + t * 5), 4.4 - t * 2.8, FUR)
    renderer.draw_circle(head + Vector2(-6, -1), 1.6, BAND_BLACK)
    renderer.end_frame()


def draw_hud_text(
    renderer: IRenderer,
    *,
    arena: Rect,
    width: int,
    height: int,
    score: int,
    high_score: int,
    wave: int,
    kills: int,
    combo: int,
    banner: str = "",
    banner_strength: float = 0.0,
) -> None:
    """Write the HUD's text, over every shape in the frame.

    Args:
        renderer: Target renderer.
        arena: The play area the bands sit above and below.
        width: Window width.
        height: Window height.
        score: Current score.
        high_score: Best score this session.
        wave: Current wave number.
        kills: Total kills this run.
        combo: Current kill chain.
        banner: Centre-screen announcement, or empty for none.
        banner_strength: 0.0 to 1.0; fades the banner in and out.
    """
    renderer.draw_text("TAMANDUÁ", Vector2(84, 12), TEXT, 18)
    renderer.draw_text("BANDEIRA", Vector2(84, 28), GOLD, 14)

    renderer.draw_text("SCORE", Vector2(width / 2 - 40, 10), TEXT_DIM, 13)
    renderer.draw_text(f"{score:07d}", Vector2(width / 2 - 46, 24), TEXT, 24)

    renderer.draw_text("HI", Vector2(width - 232, 10), TEXT_DIM, 13)
    renderer.draw_text(f"{high_score:07d}", Vector2(width - 210, 8), GOLD, 18)
    renderer.draw_text(f"WAVE {wave}", Vector2(width - 232, 28), TEXT, 16)

    renderer.draw_text(f"KILLS {kills}", Vector2(18, arena.bottom + 26), TEXT_DIM, 14)
    renderer.draw_text(
        "WASD/ARROWS MOVE   SPACE FIRE   ESC MENU",
        Vector2(width - 336, arena.bottom + 26),
        TEXT_DIM,
        13,
    )

    if combo > 1:
        renderer.draw_text(
            f"{combo} CHAIN",
            Vector2(width / 2 - 34, arena.bottom + 12),
            COMBO_COLOR,
            16,
        )

    if banner and banner_strength > 0.0:
        size = int(30 + 16 * banner_strength)
        shade = int(255 * min(1.0, banner_strength))
        renderer.draw_text(
            banner,
            Vector2(width / 2 - len(banner) * size * 0.28, height / 2 - 40),
            Color(GOLD.r, GOLD.g, GOLD.b, shade),
            size,
        )
