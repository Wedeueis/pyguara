"""Vinagre: Matilha - Presentation.

All drawing lives here so `scenes.py` stays wiring rather than art. The
demo ships no image assets (like every other demo in this repo), so
everything is composed from `IRenderer`'s primitives -- but composed
*deliberately*: creatures are built from oriented body/head/ear/tail
shapes that turn to face their heading, terrain gets scatter detail and
drop shadows for depth, and water animates.

Scatter detail (grass tufts, rocks, ripples) is generated once from a
seeded `RandomStream` and cached, not re-rolled per frame: regenerating it
every frame would both cost draw-call setup and make the ground visibly
crawl.
"""

from __future__ import annotations

import math

from games.vinagre_matilha.combat import (
    SWIPE_ARC_DEGREES,
    SWIPE_RANGE,
    WINDUP_SECONDS,
)
from games.vinagre_matilha.components import (
    DogState,
    JaguarPhase,
    JaguarState,
    LogGate,
    PressurePlate,
)
from games.vinagre_matilha.level_builder import StageConfig
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import IRenderer
from pyguara.kits.action_combat import Health
from pyguara.kits.pack import PackMember, PackRole

# ========== Palette ==========

BACKGROUND = Color(24, 32, 20)
BANK_FAR = Color(38, 52, 30)
BANK_NEAR = Color(46, 62, 36)
SOIL = Color(74, 68, 44)
SOIL_DARK = Color(58, 54, 36)
SOIL_DAMP = Color(66, 60, 40)
SOIL_PEBBLE = Color(104, 98, 76)
SOIL_GRIT = Color(92, 86, 62)
GRASS_TUFT = Color(96, 122, 58)
GRASS_TUFT_DRY = Color(132, 130, 66)
ROCK = Color(86, 88, 80)

WATER_DEEP = Color(32, 78, 96)
WATER = Color(46, 104, 126)
WATER_LIGHT = Color(86, 152, 172)
FOAM = Color(198, 226, 232)

DOG_BODY = Color(150, 74, 38)
DOG_BODY_VANGUARD = Color(214, 116, 40)
DOG_BELLY = Color(96, 46, 24)
DOG_DOWNED = Color(92, 74, 62)
DOG_MARKER = Color(255, 214, 120)

JAGUAR_BODY = Color(198, 150, 62)
JAGUAR_BELLY = Color(150, 108, 44)
JAGUAR_SPOT = Color(58, 44, 24)
JAGUAR_HURT = Color(255, 176, 150)
JAGUAR_TELEGRAPH = Color(255, 92, 70)

LOG = Color(104, 70, 38)
LOG_DARK = Color(74, 48, 24)
PLATE_CLOSED = Color(122, 102, 58)
PLATE_ACTIVE = Color(196, 168, 70)
PLATE_OPEN = Color(96, 168, 96)
CORNER_ZONE = Color(226, 196, 82)
PACK_BOND = Color(214, 140, 70)
SHADOW = Color(0, 0, 0, 70)

_BOND_RADIUS = 96.0


def _shifted(rect: Rect, offset: Vector2) -> Rect:
    """`rect` translated into screen space by `-offset`."""
    return Rect(
        int(rect.x - offset.x),
        int(rect.y - offset.y),
        int(rect.width),
        int(rect.height),
    )


class StageArtwork:
    """Cached scatter detail for one stage's terrain.

    Built once per stage from a seeded stream so the ground is stable
    frame to frame (and identical run to run, which also keeps the
    headless render smoke test deterministic).
    """

    def __init__(self, stage: StageConfig, seed: int = 20260911) -> None:
        rng = RandomStream(seed)
        self.tufts: list[tuple[Vector2, float, Color]] = []
        self.rocks: list[tuple[Vector2, float]] = []
        self.ripples: list[tuple[Vector2, float, float]] = []
        self.bed: list[tuple[Vector2, float, Color]] = []

        # Riverbed scatter: pebbles and damp patches, so the channel the
        # fight happens on isn't a flat empty slab.
        for _ in range(150):
            point = Vector2(
                rng.uniform(0, stage.world_width),
                rng.uniform(
                    stage.corridor_top, stage.corridor_top + stage.corridor_height
                ),
            )
            roll = rng.uniform(0, 1)
            if roll > 0.72:
                self.bed.append((point, rng.uniform(2.0, 4.2), SOIL_PEBBLE))
            elif roll > 0.4:
                self.bed.append((point, rng.uniform(5.0, 11.0), SOIL_DAMP))
            else:
                self.bed.append((point, rng.uniform(1.2, 2.4), SOIL_GRIT))

        for rect in stage.wall_rects:
            area = rect.width * rect.height
            for _ in range(max(6, int(area / 2600))):
                point = Vector2(
                    rng.uniform(rect.left + 4, rect.right - 4),
                    rng.uniform(rect.top + 4, rect.bottom - 4),
                )
                color = GRASS_TUFT if rng.uniform(0, 1) > 0.35 else GRASS_TUFT_DRY
                self.tufts.append((point, rng.uniform(3.0, 6.5), color))
            for _ in range(max(2, int(area / 12000))):
                self.rocks.append(
                    (
                        Vector2(
                            rng.uniform(rect.left + 6, rect.right - 6),
                            rng.uniform(rect.top + 6, rect.bottom - 6),
                        ),
                        rng.uniform(2.5, 5.0),
                    )
                )

        for rect in stage.water_zones:
            for _ in range(max(8, int(rect.width * rect.height / 5200))):
                self.ripples.append(
                    (
                        Vector2(
                            rng.uniform(rect.left + 6, rect.right - 6),
                            rng.uniform(rect.top, rect.bottom),
                        ),
                        rng.uniform(7.0, 16.0),
                        rng.uniform(0.0, 1.0),
                    )
                )


def draw_terrain(
    renderer: IRenderer,
    stage: StageConfig,
    art: StageArtwork,
    offset: Vector2,
    elapsed: float,
) -> None:
    """Draw banks, scatter detail, and the animated water channels."""
    renderer.clear(BACKGROUND)

    # Riverbed floor: a lighter strip between the two banks reads as the
    # walkable channel without needing a separate "floor" rect per stage.
    renderer.draw_rect(
        _shifted(Rect(0, 0, stage.world_width, stage.world_height), offset), SOIL_DARK
    )
    renderer.draw_rect(
        _shifted(
            Rect(
                0,
                stage.corridor_top,
                stage.world_width,
                stage.corridor_height,
            ),
            offset,
        ),
        SOIL,
    )

    for point, radius, color in art.bed:
        renderer.draw_circle(point - offset, radius, color)

    for rect in stage.wall_rects:
        renderer.draw_rect(_shifted(rect, offset), BANK_FAR)
        # A lighter lip along the bank edge facing the channel gives the
        # wall a readable silhouette instead of a flat block.
        lip = (
            Rect(rect.x, rect.bottom - 8, rect.width, 8)
            if rect.top < stage.corridor_top
            else Rect(rect.x, rect.y, rect.width, 8)
        )
        renderer.draw_rect(_shifted(lip, offset), BANK_NEAR)

    for point, radius, color in art.tufts:
        screen = point - offset
        renderer.draw_circle(screen, radius, color)
        renderer.draw_line(
            screen, Vector2(screen.x, screen.y - radius * 1.6), color, width=2
        )
    for point, radius in art.rocks:
        renderer.draw_circle(point - offset + Vector2(1, 2), radius, SHADOW)
        renderer.draw_circle(point - offset, radius, ROCK)

    for rect in stage.water_zones:
        renderer.draw_rect(_shifted(rect, offset), WATER)
        renderer.draw_rect(
            _shifted(Rect(rect.x, rect.y, 5, rect.height), offset), WATER_DEEP
        )
        renderer.draw_rect(
            _shifted(Rect(rect.right - 5, rect.y, 5, rect.height), offset), WATER_DEEP
        )

    # Ripples drift downstream and wrap, so the channel visibly flows.
    for point, length, phase in art.ripples:
        drift = ((elapsed * 34.0) + phase * 400.0) % 480.0
        y = point.y + drift - 240.0
        for rect in stage.water_zones:
            if not (
                rect.top <= y <= rect.bottom and rect.left <= point.x <= rect.right
            ):
                continue
            # Drawn as horizontal surface chop rather than a vertical
            # streak: a vertical line capped with a foam dot read on screen
            # as a row of little "1" glyphs rather than as moving water.
            start = Vector2(point.x - length * 0.5, y) - offset
            renderer.draw_line(
                start, Vector2(start.x + length, start.y), WATER_LIGHT, width=2
            )
            renderer.draw_line(
                Vector2(start.x + length * 0.25, start.y + 3),
                Vector2(start.x + length * 0.8, start.y + 3),
                FOAM,
                width=1,
            )


def draw_objectives(
    renderer: IRenderer,
    stage: StageConfig,
    entity_manager: EntityManager,
    offset: Vector2,
    elapsed: float,
) -> None:
    """Draw the log gate, pressure plate, and the corner-zone marker."""
    for plate_entity in entity_manager.get_entities_with(PressurePlate):
        plate = plate_entity.get_component(PressurePlate)
        if stage.plate_rect is None:
            continue
        rect = stage.plate_rect
        if plate.opened:
            color = PLATE_OPEN
        else:
            # Pulse while it waits, so it reads as "interact with me".
            pulse = 0.5 + 0.5 * math.sin(elapsed * 4.0)
            color = PLATE_CLOSED.lerp(PLATE_ACTIVE, pulse)
        renderer.draw_rect(_shifted(rect, offset), color)
        renderer.draw_rect(_shifted(rect, offset), SOIL_DARK, width=3)
        inner = Rect(rect.x + 12, rect.y + 12, rect.width - 24, rect.height - 24)
        renderer.draw_rect(_shifted(inner, offset), SOIL_DARK, width=2)

    for log_entity in entity_manager.get_entities_with(LogGate):
        del log_entity  # only its existence matters; the rect is the stage's
        if stage.log_rect is None:
            continue
        rect = stage.log_rect
        renderer.draw_rect(
            _shifted(Rect(rect.x + 3, rect.y + 4, rect.width, rect.height), offset),
            SHADOW,
        )
        renderer.draw_rect(_shifted(rect, offset), LOG)
        for i in range(rect.y, rect.bottom, 22):
            renderer.draw_line(
                Vector2(rect.x, i) - offset,
                Vector2(rect.right, i) - offset,
                LOG_DARK,
                width=2,
            )

    zone = stage.corner_zone
    renderer.draw_rect(_shifted(zone, offset), CORNER_ZONE, width=2)
    tick = 12
    for x in range(zone.left, zone.right, tick * 2):
        renderer.draw_line(
            Vector2(x, zone.top) - offset,
            Vector2(min(x + tick, zone.right), zone.top) - offset,
            CORNER_ZONE,
            width=4,
        )


def draw_pack_bonds(
    renderer: IRenderer, entity_manager: EntityManager, offset: Vector2
) -> None:
    """Draw faint links between nearby packmates.

    This is the flocking cohesion the demo exists to show, made visible:
    a tight pack is visibly webbed together, a scattered one visibly
    isn't, which is the feedback the Scatter/Pincer commands otherwise
    lack.
    """
    dogs = [
        (entity.get_component(Transform).position, entity.get_component(DogState))
        for entity in entity_manager.get_entities_with(PackMember, DogState, Transform)
    ]
    for i, (position, state) in enumerate(dogs):
        if state.is_downed:
            continue
        for other_position, other_state in dogs[i + 1 :]:
            if other_state.is_downed:
                continue
            distance = (other_position - position).length
            if distance > _BOND_RADIUS:
                continue
            fade = int(70 * (1.0 - distance / _BOND_RADIUS))
            renderer.draw_line(
                position - offset,
                other_position - offset,
                Color(PACK_BOND.r, PACK_BOND.g, PACK_BOND.b, fade),
                width=1,
            )


def _draw_quadruped(
    renderer: IRenderer,
    position: Vector2,
    facing: Vector2,
    length: float,
    girth: float,
    body: Color,
    belly: Color,
    *,
    crouch: float = 0.0,
) -> None:
    """Draw a four-legged animal as an oriented body/head/ears/tail.

    `crouch` (0-1) shortens the body and drops the head -- used for a
    dog's bite lunge and the jaguar's wind-up, so both read as *loading*
    an attack rather than just changing colour.
    """
    if facing.length < 0.001:
        facing = Vector2(1, 0)
    forward = facing.normalized()
    side = Vector2(-forward.y, forward.x)
    span = length * (1.0 - 0.18 * crouch)

    renderer.draw_circle(position + Vector2(2, 4), girth * 1.15, SHADOW)

    # Body: three overlapping circles along the heading make a capsule
    # that reads as a torso from any angle.
    rear = position - forward * (span * 0.32)
    mid = position
    front = position + forward * (span * 0.30)
    renderer.draw_circle(rear, girth * 0.88, belly)
    renderer.draw_circle(mid, girth, body)
    renderer.draw_circle(front, girth * 0.92, body)

    # Tail, tapering back and kicked slightly to one side.
    tail_base = rear - forward * (girth * 0.5)
    tail_tip = tail_base - forward * (span * 0.42) + side * (girth * 0.35)
    renderer.draw_line(tail_base, tail_tip, belly, width=max(2, int(girth * 0.42)))
    renderer.draw_circle(tail_tip, girth * 0.22, belly)

    # Head and ears.
    head = position + forward * (span * 0.58) + forward * (girth * 0.12)
    head_radius = girth * 0.72
    renderer.draw_circle(head, head_radius, body)
    muzzle = head + forward * (head_radius * 0.75)
    renderer.draw_circle(muzzle, head_radius * 0.45, belly)
    for sign in (1.0, -1.0):
        ear = head - forward * (head_radius * 0.35) + side * (head_radius * 0.72 * sign)
        renderer.draw_circle(ear, head_radius * 0.38, belly)


def draw_pack(
    renderer: IRenderer, entity_manager: EntityManager, offset: Vector2, elapsed: float
) -> None:
    """Draw every dog, oriented, with role tint and downed/biting state."""
    for entity in entity_manager.get_entities_with(PackMember, DogState, Transform):
        state = entity.get_component(DogState)
        member = entity.get_component(PackMember)
        position = entity.get_component(Transform).position - offset
        is_vanguard = member.role is PackRole.VANGUARD
        length = 26.0 if is_vanguard else 23.0
        girth = 7.5 if is_vanguard else 6.6

        if state.is_downed:
            # Flat on its side, greyed, with a "rallying" pip that ticks up
            # as packmates close in.
            renderer.draw_circle(position + Vector2(2, 4), girth * 1.2, SHADOW)
            renderer.draw_circle(position, girth * 1.05, DOG_DOWNED)
            renderer.draw_circle(position, girth * 0.5, SOIL_DARK)
            blink = 0.5 + 0.5 * math.sin(elapsed * 9.0)
            renderer.draw_circle(
                position + Vector2(0, -girth * 2.4),
                2.6,
                DOG_DOWNED.lerp(DOG_MARKER, blink),
            )
            continue

        crouch = 1.0 if state.bite_flash > 0.0 else 0.0
        body = DOG_BODY_VANGUARD if is_vanguard else DOG_BODY
        if state.bite_flash > 0.0:
            body = body.lerp(Color(255, 236, 180), 0.45)
        _draw_quadruped(
            renderer,
            position,
            state.facing,
            length,
            girth,
            body,
            DOG_BELLY,
            crouch=crouch,
        )
        if is_vanguard:
            # The player's own dog wears a marker so it never gets lost in
            # a twelve-dog scrum.
            renderer.draw_circle(position + Vector2(0, -girth * 2.6), 3.4, DOG_MARKER)
            renderer.draw_circle(position, girth * 1.45, DOG_MARKER, width=1)


def draw_jaguar(
    renderer: IRenderer,
    entity_manager: EntityManager,
    jaguar_id: str,
    offset: Vector2,
    elapsed: float,
) -> None:
    """Draw the jaguar plus whichever attack-phase tell is active."""
    jaguar = entity_manager.get_entity(jaguar_id)
    if jaguar is None:
        return
    state = jaguar.get_component(JaguarState)
    world = jaguar.get_component(Transform).position
    position = world - offset

    if state.phase is JaguarPhase.WINDUP:
        _draw_windup(renderer, position, state, elapsed)
    elif state.phase is JaguarPhase.SWIPE:
        _draw_swipe(renderer, position, state)

    body = JAGUAR_BODY
    if state.hurt_flash > 0.0:
        body = body.lerp(JAGUAR_HURT, 0.7)
    elif state.phase is JaguarPhase.RECOVER:
        # Visibly staggered, so the punish window is legible.
        body = body.lerp(Color(150, 140, 120), 0.35)

    crouch = 1.0 if state.phase in (JaguarPhase.WINDUP, JaguarPhase.SWIPE) else 0.0
    _draw_quadruped(
        renderer, position, state.facing, 46.0, 13.0, body, JAGUAR_BELLY, crouch=crouch
    )

    # Rosettes, placed along the body axis so they turn with it.
    forward = (
        state.facing.normalized() if state.facing.length > 0.001 else Vector2(1, 0)
    )
    side = Vector2(-forward.y, forward.x)
    for along, across in ((-0.22, 0.42), (0.06, -0.46), (0.22, 0.34), (-0.05, 0.1)):
        spot = position + forward * (46.0 * along) + side * (13.0 * across)
        renderer.draw_circle(spot, 2.6, JAGUAR_SPOT)

    if state.cornered:
        ring = 26.0 + 4.0 * math.sin(elapsed * 6.0)
        renderer.draw_circle(position, ring, CORNER_ZONE, width=3)


def _draw_windup(
    renderer: IRenderer, position: Vector2, state: JaguarState, elapsed: float
) -> None:
    """Draw the swipe telegraph: a growing arc the player can read and dodge."""
    progress = 1.0 - max(0.0, min(1.0, state.phase_timer / WINDUP_SECONDS))
    radius = SWIPE_RANGE * (0.45 + 0.55 * progress)
    base = math.atan2(state.swipe_direction.y, state.swipe_direction.x)
    half = math.radians(SWIPE_ARC_DEGREES) * 0.5
    alpha = int(90 + 130 * progress)
    color = Color(JAGUAR_TELEGRAPH.r, JAGUAR_TELEGRAPH.g, JAGUAR_TELEGRAPH.b, alpha)

    steps = 16
    previous: Vector2 | None = None
    for i in range(steps + 1):
        angle = base - half + (2 * half) * (i / steps)
        point = position + Vector2(math.cos(angle), math.sin(angle)) * radius
        if previous is not None:
            renderer.draw_line(previous, point, color, width=3)
        previous = point
    renderer.draw_line(
        position,
        position + state.swipe_direction * radius,
        color,
        width=2,
    )
    # A flashing warning pip right on the jaguar, for peripheral vision.
    if math.sin(elapsed * 22.0) > 0:
        renderer.draw_circle(position + Vector2(0, -26), 4.0, JAGUAR_TELEGRAPH)


def _draw_swipe(renderer: IRenderer, position: Vector2, state: JaguarState) -> None:
    """Draw the swipe itself as a bright filled sweep."""
    base = math.atan2(state.swipe_direction.y, state.swipe_direction.x)
    half = math.radians(SWIPE_ARC_DEGREES) * 0.5
    steps = 18
    for i in range(steps):
        angle = base - half + (2 * half) * (i / steps)
        direction = Vector2(math.cos(angle), math.sin(angle))
        renderer.draw_line(
            position + direction * (SWIPE_RANGE * 0.35),
            position + direction * SWIPE_RANGE,
            Color(255, 240, 220, 210),
            width=3,
        )


def draw_health_bar(
    renderer: IRenderer,
    entity_manager: EntityManager,
    jaguar_id: str,
    offset: Vector2,
) -> None:
    """Draw the jaguar's health as a world-space bar above it."""
    jaguar = entity_manager.get_entity(jaguar_id)
    if jaguar is None or not jaguar.has_component(Health):
        return
    health = jaguar.get_component(Health)
    position = jaguar.get_component(Transform).position - offset
    width, height = 54, 6
    top_left = Vector2(position.x - width / 2, position.y - 34)
    renderer.draw_rect(
        Rect(int(top_left.x) - 1, int(top_left.y) - 1, width + 2, height + 2),
        Color(18, 14, 10),
    )
    fraction = max(0.0, health.current / health.max_health)
    renderer.draw_rect(
        Rect(int(top_left.x), int(top_left.y), int(width * fraction), height),
        Color(214, 78, 54).lerp(Color(228, 188, 72), fraction),
    )
