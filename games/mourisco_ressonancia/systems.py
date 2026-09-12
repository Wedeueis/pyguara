"""Mourisco: Ressonância - Game systems.

Movement collides against the same tile grid the echolocation marches
through, so what the player can walk on and what the pulse can light are
one source of truth rather than two representations that can disagree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from games.mourisco_ressonancia.cave import TILE, CaveLayout, march
from pyguara.common.grid import Cell
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.kits.echolocation import ActivePulse, RevealMemory

GRAVITY = 1750.0
MOVE_SPEED = 205.0
JUMP_SPEED = 560.0
MAX_FALL = 900.0
COYOTE_TIME = 0.09
PLAYER_HALF = Vector2(11.0, 9.0)

# How far past the wavefront a surface still counts as "swept". Without a
# little slack, a tile the ray enters exactly as the pulse passes can be
# skipped between frames, leaving pinholes in the reveal.
_SWEEP_SLACK = 6.0


def _solid_overlap(layout: CaveLayout, centre: Vector2, half: Vector2) -> bool:
    """Whether an axis-aligned box overlaps any solid tile."""
    min_x = int(math.floor((centre.x - half.x) / TILE))
    max_x = int(math.floor((centre.x + half.x - 0.001) / TILE))
    min_y = int(math.floor((centre.y - half.y) / TILE))
    max_y = int(math.floor((centre.y + half.y - 0.001) / TILE))
    for cell_y in range(min_y, max_y + 1):
        for cell_x in range(min_x, max_x + 1):
            if layout.is_solid((cell_x, cell_y)):
                return True
    return False


@dataclass
class PlayerState:
    """Everything the jaguarundi's movement needs."""

    position: Vector2
    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    facing: float = 1.0
    grounded: bool = False
    coyote: float = 0.0
    call_flash: float = 0.0
    hurt_flash: float = 0.0
    reached_exit: bool = False


class PlayerController:
    """Grid-collided platforming for the player.

    Axis-separated: horizontal motion resolves before vertical, which is
    what lets the player slide along a wall while falling instead of
    catching on it.
    """

    def __init__(self, layout: CaveLayout, state: PlayerState) -> None:
        self._layout = layout
        self._state = state
        self.move_input = 0.0
        self.jump_requested = False

    def update(self, dt: float) -> None:
        state = self._state
        state.call_flash = max(0.0, state.call_flash - dt * 3.2)
        state.hurt_flash = max(0.0, state.hurt_flash - dt * 1.4)

        state.velocity = Vector2(
            self.move_input * MOVE_SPEED,
            min(MAX_FALL, state.velocity.y + GRAVITY * dt),
        )
        if self.move_input != 0.0:
            state.facing = 1.0 if self.move_input > 0 else -1.0

        if state.grounded:
            state.coyote = COYOTE_TIME
        else:
            state.coyote = max(0.0, state.coyote - dt)

        if self.jump_requested and state.coyote > 0.0:
            state.velocity = Vector2(state.velocity.x, -JUMP_SPEED)
            state.coyote = 0.0
        self.jump_requested = False

        self._move_axis(Vector2(state.velocity.x * dt, 0.0))
        landed = self._move_axis(Vector2(0.0, state.velocity.y * dt))
        state.grounded = landed and state.velocity.y >= 0.0
        if landed:
            state.velocity = Vector2(state.velocity.x, 0.0)

    def _move_axis(self, delta: Vector2) -> bool:
        """Step one axis, backing off to the contact point. True if blocked."""
        state = self._state
        candidate = state.position + delta
        if not _solid_overlap(self._layout, candidate, PLAYER_HALF):
            state.position = candidate
            return False

        # Blocked: binary-search the free distance so the player ends up
        # flush against the surface rather than a whole step short of it,
        # which is what makes tight gaps passable.
        low, high = 0.0, 1.0
        for _ in range(6):
            mid = (low + high) / 2
            if _solid_overlap(self._layout, state.position + delta * mid, PLAYER_HALF):
                high = mid
            else:
                low = mid
        state.position = state.position + delta * low
        return True


@dataclass
class _Fan:
    """One pulse's precomputed rays: the cells each crosses, and when."""

    pulse: ActivePulse
    rays: list[list[tuple[float, Cell]]]
    cursors: list[int]


class PulseSystem:
    """Owns live pulses, and reveals the cave as each wavefront passes.

    Each ray's path is marched **once**, when the pulse is emitted, and
    then consumed progressively as the wavefront overtakes it. Re-marching
    every frame would be the obvious implementation and is far too slow:
    128 rays times a hundred-odd cells, sixty times a second. This way the
    total work over a pulse's whole life is one march per ray.
    """

    def __init__(
        self,
        layout: CaveLayout,
        memory: RevealMemory,
        ray_count: int = 140,
    ) -> None:
        self._layout = layout
        self._memory = memory
        self._ray_count = ray_count
        self._fans: list[_Fan] = []
        self._rng = RandomStream(4242)
        # A second memory, same shape as the first, recording which
        # surfaces were found by a *scream* rather than a chirp. Kept
        # separate rather than folded into the brightness value so the two
        # decay independently: a wall stays violet for as long as it stays
        # visible, instead of the tint and the fade fighting each other.
        self.scream_memory = RevealMemory(decay_per_second=memory.decay_per_second)

    @property
    def active(self) -> list[ActivePulse]:
        """Every pulse still travelling."""
        return [fan.pulse for fan in self._fans]

    def emit(self, pulse: ActivePulse) -> None:
        """March every ray of a new pulse and start tracking it."""
        offset = self._rng.uniform(0.0, 2.0 * math.pi)
        rays: list[list[tuple[float, Cell]]] = []
        for i in range(self._ray_count):
            angle = offset + (2.0 * math.pi * i / self._ray_count)
            direction = Vector2(math.cos(angle), math.sin(angle))
            rays.append(march(self._layout, pulse.origin, direction, pulse.max_radius))
        self._fans.append(_Fan(pulse=pulse, rays=rays, cursors=[0] * len(rays)))

    def update(self, dt: float) -> None:
        """Advance every wavefront and reveal what it has now reached."""
        for fan in self._fans:
            fan.pulse.elapsed += dt
            reach = fan.pulse.radius + _SWEEP_SLACK
            # Brightness falls off with distance so the far edge of a big
            # scream is a hint rather than a floodlight.
            for index, ray in enumerate(fan.rays):
                cursor = fan.cursors[index]
                while cursor < len(ray) and ray[cursor][0] <= reach:
                    distance, cell = ray[cursor]
                    # Revealed above full brightness on purpose: drawing
                    # clamps at 1.0, so the surplus buys a moment of
                    # steady full-bright before the decay starts showing.
                    # That reads as the surface being *struck* by the
                    # wavefront and then settling, rather than beginning
                    # to fade the instant it is touched.
                    falloff = 1.0 - (distance / max(fan.pulse.max_radius, 1.0)) * 0.5
                    self._memory.reveal(cell, max(0.55, falloff) * 1.55)
                    if fan.pulse.is_scream:
                        self.scream_memory.reveal(cell, 1.0)
                    cursor += 1
                fan.cursors[index] = cursor

        self.scream_memory.decay(dt)
        self._fans = [fan for fan in self._fans if not fan.pulse.is_spent]

    def scream_amount(self, cell: Cell) -> float:
        """How strongly `cell` is remembered as found by a scream."""
        return self.scream_memory.brightness(cell)

    def lit_amount(self, position: Vector2) -> float:
        """How strongly `position`'s cell is currently remembered."""
        return self._memory.brightness(
            (int(position.x // TILE), int(position.y // TILE))
        )


@dataclass
class Bat:
    """A roosting bat that scatters when a scream reaches it."""

    position: Vector2
    home: Vector2
    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    agitation: float = 0.0
    phase: float = 0.0


@dataclass
class Spider:
    """A cave spider that lunges at a player who strays too close."""

    position: Vector2
    home: Vector2
    agitated: bool = False
    lunge_cooldown: float = 0.0


class CreatureSystem:
    """Bats scatter from screams; spiders react to proximity.

    Bats are the cost side of the scream: the wide pulse that shows you
    the room is also the one that fills it with noise.
    """

    AGITATION_RADIUS = 150.0
    SPIDER_WAKE_RADIUS = 96.0
    SPIDER_TOUCH_RADIUS = 22.0
    SPIDER_RECOVERY = 1.6

    def __init__(self, layout: CaveLayout, bats: list[Bat], spiders: list[Spider]):
        self._layout = layout
        self.bats = bats
        self.spiders = spiders
        self._rng = RandomStream(99)
        # Set for one frame when a spider lands a hit, for the scene to
        # react to. A flag rather than a callback keeps this system free of
        # any knowledge of flashes, knockback or memory.
        self.struck_by: Spider | None = None

    def on_pulse(self, pulse: ActivePulse) -> None:
        """React to a newly emitted pulse."""
        if not pulse.is_scream:
            return
        for bat in self.bats:
            if (bat.home - pulse.origin).length <= pulse.max_radius:
                bat.agitation = 1.0
                angle = self._rng.uniform(0.0, 2.0 * math.pi)
                bat.velocity = Vector2(math.cos(angle), math.sin(angle)) * 190.0

    def update(self, dt: float, player: Vector2) -> None:
        for bat in self.bats:
            bat.phase += dt * (16.0 if bat.agitation > 0.05 else 5.0)
            if bat.agitation > 0.0:
                bat.agitation = max(0.0, bat.agitation - dt * 0.32)
                candidate = bat.position + bat.velocity * dt
                if _solid_overlap(self._layout, candidate, Vector2(5, 5)):
                    bat.velocity = Vector2(-bat.velocity.x, -bat.velocity.y)
                else:
                    bat.position = candidate
            else:
                # Drift home, so a scattered roost re-forms instead of
                # leaving bats stuck wherever the panic ended.
                to_home = bat.home - bat.position
                if to_home.length > 2.0:
                    bat.position = bat.position + to_home.normalized() * 42.0 * dt

        self.struck_by = None
        for spider in self.spiders:
            spider.lunge_cooldown = max(0.0, spider.lunge_cooldown - dt)
            distance = (player - spider.position).length
            spider.agitated = distance < self.SPIDER_WAKE_RADIUS
            if distance < self.SPIDER_TOUCH_RADIUS and spider.lunge_cooldown <= 0.0:
                spider.lunge_cooldown = self.SPIDER_RECOVERY
                self.struck_by = spider
