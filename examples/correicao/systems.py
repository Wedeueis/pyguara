"""The calango's movement, the raid, and the fight between them.

The raid is one engine `Swarm`: every ant is an agent held natively, not
an entity, so steering, animating and drawing it never visit the ants one
at a time in Python. What this module adds works on the raid in batches.
The spawner adds this tick's ants in one call per kind, and the combat
pass, ten times a second, asks the swarm who is in the pulse, who is
biting and who is left behind.
"""

from __future__ import annotations

import math

from examples.correicao.components import PlayerState
from pyguara.ai.swarm import Swarm, SwarmKind, SwarmLook
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.resources.types import Texture

WORLD_SIZE = 6000.0
PLAYER_SPEED = 120.0
AUTOPILOT_RADIUS = 1500.0
REGEN_PER_SECOND = 4.0

ANT_LAYER = 10
ANT_KINDS = 8
SPAWN_PER_TICK = 250
SPAWN_MARGIN = 450.0
DESPAWN_FACTOR = 2.5
# Ants farther than this past the edge of the screen steer every fourth tick.
DETAIL_MARGIN = 100.0
FAR_PERIOD = 4

COMBAT_PERIOD = 0.1
PULSE_PERIOD = 1.0
PULSE_RADIUS = 150.0
PULSE_FLASH = 0.25
BITE_RADIUS = 16.0
BITE_DAMAGE = 0.05


def make_raid(swarm: Swarm, walk: list[Texture]) -> list[int]:
    """Register the raid's kinds on `swarm` and return their indices.

    Eight kinds span the ants' speeds, from 85 to 140, and the faster an
    ant the quicker its legs, from 7 to 11 steps a second.

    Args:
        swarm: The scene's swarm.
        walk: The walk cycle's frames.

    Returns:
        One kind index per speed, slowest first.
    """
    kinds = []
    for step in range(ANT_KINDS):
        share = step / (ANT_KINDS - 1)
        kind = swarm.add_kind(
            SwarmKind(
                max_speed=85.0 + 55.0 * share,
                max_force=300.0,
                neighbor_radius=26.0,
                separation_radius=12.0,
                cohesion_weight=0.2,
                alignment_weight=0.5,
                separation_weight=2.2,
                seek_weight=1.0,
            )
        )
        swarm.set_look(
            kind,
            SwarmLook(
                frames=tuple(walk),
                frame_rate=7.0 + 4.0 * share,
                layer=ANT_LAYER,
                face_heading=True,
            ),
        )
        kinds.append(kind)
    return kinds


def clamp_to_world(position: Vector2) -> Vector2:
    """Return `position` moved inside the world's square, if it was outside."""
    return Vector2(
        min(max(position.x, 0.0), WORLD_SIZE), min(max(position.y, 0.0), WORLD_SIZE)
    )


class PlayerSystem:
    """Moves the calango by the keys, or on a fixed loop until a key is pressed.

    The loop, the autopilot, is what lets the demo run with nobody at the
    keyboard: the frame captures and the horde benchmark both drive it.
    """

    def __init__(self, state: PlayerState, *, autopilot: bool = True) -> None:
        """Move `state`, starting on the autopilot if `autopilot`.

        Args:
            state: The calango, moved in place.
            autopilot: Whether to walk the loop until a key is pressed.
        """
        self._state = state
        self.autopilot = autopilot
        self.move_direction = Vector2(0, 0)
        self._time = 0.0

    def update(self, dt: float) -> None:
        """Move the calango one tick, and let it recover a little.

        Args:
            dt: Seconds since the last tick.
        """
        state = self._state
        self._time += dt
        if self.move_direction.length > 0.0:
            self.autopilot = False
        if self.autopilot:
            angle = self._time * PLAYER_SPEED / AUTOPILOT_RADIUS
            centre = WORLD_SIZE / 2
            target = Vector2(
                centre + math.cos(angle) * AUTOPILOT_RADIUS,
                centre + math.sin(angle) * AUTOPILOT_RADIUS,
            )
            direction = target - state.position
        else:
            direction = self.move_direction
        if direction.length > 1e-6:
            step = direction.normalized() * PLAYER_SPEED * dt
            if self.autopilot and step.length > direction.length:
                step = direction  # arrive on the loop rather than overshoot it
            state.position = clamp_to_world(state.position + step)
            state.heading = direction.normalized()
        if state.health <= 0.0:
            state.overruns += 1
            state.health = 100.0
        state.health = min(100.0, state.health + REGEN_PER_SECOND * dt)
        state.pulse_flash = max(0.0, state.pulse_flash - dt)


class HordeSpawner:
    """Keeps the raid at `target` ants, spawning them just out of view.

    New ants appear on a ring around the calango, past the edge of the
    screen, at most `SPAWN_PER_TICK` a tick, so a full raid builds up over
    the first second rather than in one frame.
    """

    def __init__(
        self,
        swarm: Swarm,
        state: PlayerState,
        kinds: list[int],
        rng: RandomStream,
        *,
        target: int,
        view_radius: float,
    ) -> None:
        """Spawn ants into `swarm` around `state`.

        Args:
            swarm: The raid.
            state: The calango the ants hunt.
            kinds: The raid's kinds, from `make_raid`; each ant is one at random.
            rng: The stream every spawn position and kind is drawn from.
            target: How many ants the raid keeps.
            view_radius: Half the screen's diagonal, so spawns stay unseen.
        """
        self._swarm = swarm
        self._state = state
        self._kinds = kinds
        self._rng = rng
        self.target = target
        self._spawn_radius = view_radius + 40.0

    @property
    def alive(self) -> int:
        """How many ants the raid has now."""
        return self._swarm.count

    def update(self, dt: float) -> None:
        """Spawn this tick's share of the ants the raid is missing.

        Args:
            dt: Seconds since the last tick.
        """
        self.spawn(min(SPAWN_PER_TICK, self.target - self.alive))

    def spawn(self, count: int = 1) -> list[int]:
        """Add `count` ants on the ring around the calango, and return their ids."""
        rng = self._rng
        by_kind: dict[int, list[Vector2]] = {}
        for _ in range(count):
            angle = rng.uniform(0.0, math.tau)
            distance = self._spawn_radius + rng.uniform(0.0, SPAWN_MARGIN)
            offset = Vector2(math.cos(angle), math.sin(angle)) * distance
            kind = rng.choice(self._kinds)
            by_kind.setdefault(kind, []).append(
                clamp_to_world(self._state.position + offset)
            )
        ids: list[int] = []
        for kind, positions in by_kind.items():
            ids += self._swarm.spawn(kind, positions)
        return ids


class RaidSystem:
    """Steps the raid toward the calango, natively, each tick.

    Ants near the screen steer every tick; the rest, every `FAR_PERIOD`th,
    and all of them move every tick.
    """

    def __init__(
        self, swarm: Swarm, state: PlayerState, kinds: list[int], *, view_radius: float
    ) -> None:
        """Steer `swarm`'s `kinds` toward `state`.

        Args:
            swarm: The raid.
            state: The calango.
            kinds: The raid's kinds.
            view_radius: Half the screen's diagonal.
        """
        self._swarm = swarm
        self._state = state
        self._kinds = kinds
        swarm.set_detail_bands(
            [
                (view_radius + DETAIL_MARGIN, 1),
                (view_radius + DETAIL_MARGIN + 1.0, FAR_PERIOD),
            ]
        )

    def update(self, dt: float) -> None:
        """Point the raid at the calango and step it.

        Args:
            dt: Seconds since the last tick.
        """
        player = self._state.position
        for kind in self._kinds:
            self._swarm.set_kind_seek(kind, player)
        self._swarm.set_detail_focus(player)
        self._swarm.update(dt)


class CombatSystem:
    """Bites, pulses and stragglers, ten times a second.

    Every `COMBAT_PERIOD` it asks the swarm three questions: who is inside
    a pulse, who is touching the calango, and who is left so far behind
    that the spawner should replace them near it. Each is one query, not a
    walk over the raid.
    """

    def __init__(
        self,
        swarm: Swarm,
        state: PlayerState,
        *,
        view_radius: float,
    ) -> None:
        """Fight between `state` and the ants in `swarm`.

        Args:
            swarm: The raid.
            state: The calango, hurt and credited in place.
            view_radius: Half the screen's diagonal; stragglers are culled
                at `DESPAWN_FACTOR` times it.
        """
        self._swarm = swarm
        self._state = state
        self._despawn_radius = view_radius * DESPAWN_FACTOR
        self._clock = 0.0

    def update(self, dt: float) -> None:
        """Count down to the next pass, and run it when due.

        Args:
            dt: Seconds since the last tick.
        """
        state = self._state
        state.pulse_cooldown -= dt
        self._clock += dt
        if self._clock < COMBAT_PERIOD:
            return
        self._clock -= COMBAT_PERIOD
        self.resolve()

    def resolve(self) -> None:
        """Run one pass: pulse, bites and stragglers."""
        state = self._state
        swarm = self._swarm
        player = state.position
        killed: list[int] = []
        bites = 0
        if state.pulse_cooldown <= 0.0:
            # The pulse reaches past the calango's body: every biter dies.
            state.pulse_cooldown = PULSE_PERIOD
            state.pulse_flash = PULSE_FLASH
            killed = swarm.query_radius(player, PULSE_RADIUS)
        else:
            bites = len(swarm.query_radius(player, BITE_RADIUS))
        stragglers = swarm.query_outside(player, self._despawn_radius)
        swarm.kill(killed + stragglers)
        state.kills += len(killed)
        state.bites += bites
        state.health = max(0.0, state.health - bites * BITE_DAMAGE)
