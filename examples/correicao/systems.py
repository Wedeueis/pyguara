"""The calango's movement, the raid's spawning, and the fight between them.

The ants' movement is not here: `FlockingSystem` steers every ant toward
the calango and apart from its neighbours, natively, in one call a tick.
What this module adds is cheap per tick on purpose. The spawner touches
only the ants it creates, and the combat pass, the one loop over the
whole raid, runs ten times a second rather than sixty.
"""

from __future__ import annotations

import math

from examples.correicao.components import Ant, PlayerState
from pyguara.ai.flocking_system import FlockingAgent
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.animation import (
    AnimationClip,
    Animator,
    add_clip,
    play_clip,
)
from pyguara.graphics.components.sprite import Sprite
from pyguara.resources.types import Texture

WORLD_SIZE = 6000.0
PLAYER_SPEED = 120.0
AUTOPILOT_RADIUS = 1500.0
REGEN_PER_SECOND = 4.0

ANT_LAYER = 10
SPAWN_PER_TICK = 250
SPAWN_MARGIN = 450.0
DESPAWN_FACTOR = 2.5

COMBAT_PERIOD = 0.1
PULSE_PERIOD = 1.0
PULSE_RADIUS = 150.0
PULSE_FLASH = 0.25
BITE_RADIUS = 16.0
BITE_DAMAGE = 0.05


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
        entity_manager: EntityManager,
        state: PlayerState,
        walk: list[Texture],
        rng: RandomStream,
        *,
        target: int,
        view_radius: float,
    ) -> None:
        """Spawn ants into `entity_manager` around `state`.

        Args:
            entity_manager: The scene's entities.
            state: The calango the ants hunt.
            walk: The walk cycle's frames.
            rng: The stream every spawn position and speed is drawn from.
            target: How many ants the raid keeps.
            view_radius: Half the screen's diagonal, so spawns stay unseen.
        """
        self._em = entity_manager
        self._state = state
        self._walk = walk
        self._rng = rng
        self.target = target
        self._spawn_radius = view_radius + 40.0
        self.alive = 0

    def update(self, dt: float) -> None:
        """Spawn this tick's share of the ants the raid is missing.

        Args:
            dt: Seconds since the last tick.
        """
        for _ in range(min(SPAWN_PER_TICK, self.target - self.alive)):
            self.spawn()

    def spawn(self) -> None:
        """Create one ant on the ring around the calango."""
        rng = self._rng
        angle = rng.uniform(0.0, math.tau)
        distance = self._spawn_radius + rng.uniform(0.0, SPAWN_MARGIN)
        offset = Vector2(math.cos(angle), math.sin(angle)) * distance
        position = clamp_to_world(self._state.position + offset)

        entity = self._em.create_entity()
        entity.add_component(Transform(position=position))
        sprite = Sprite(texture=self._walk[0], layer=ANT_LAYER)
        entity.add_component(sprite)
        animator = Animator(sprite)
        add_clip(
            animator,
            AnimationClip(
                name="walk", frames=self._walk, frame_rate=rng.uniform(7.0, 11.0)
            ),
        )
        play_clip(animator, "walk")
        entity.add_component(animator)
        entity.add_component(
            FlockingAgent(
                max_speed=rng.uniform(85.0, 140.0),
                max_force=300.0,
                neighbor_radius=26.0,
                separation_radius=12.0,
                cohesion_weight=0.2,
                alignment_weight=0.5,
                separation_weight=2.2,
                seek_weight=1.0,
                seek_target=self._state.position,
            )
        )
        entity.add_component(Ant())
        self.alive += 1


class CombatSystem:
    """Bites, pulses and stragglers: the one pass over the whole raid.

    Every `COMBAT_PERIOD` it walks every ant once. An ant inside a pulse
    dies; one touching the calango bites; one left far behind is removed
    for the spawner to replace near the calango. The same pass points each
    ant's seek at where the calango is now, and turns its sprite to face
    the way it walks.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        state: PlayerState,
        spawner: HordeSpawner,
        *,
        view_radius: float,
    ) -> None:
        """Fight between `state` and the ants in `entity_manager`.

        Args:
            entity_manager: The scene's entities.
            state: The calango, hurt and credited in place.
            spawner: Told how many ants are gone, so it replaces them.
            view_radius: Half the screen's diagonal; stragglers are culled
                at `DESPAWN_FACTOR` times it.
        """
        self._em = entity_manager
        self._state = state
        self._spawner = spawner
        self._despawn_radius = view_radius * DESPAWN_FACTOR
        self._clock = 0.0
        entity_manager.register_cached_query(Ant, Transform)

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
        """Run one pass: pulse, bites, stragglers, seeks and facing."""
        state = self._state
        player = state.position
        pulsing = state.pulse_cooldown <= 0.0
        if pulsing:
            state.pulse_cooldown = PULSE_PERIOD
            state.pulse_flash = PULSE_FLASH
        pulse_sq = PULSE_RADIUS * PULSE_RADIUS
        bite_sq = BITE_RADIUS * BITE_RADIUS
        despawn_sq = self._despawn_radius * self._despawn_radius

        dead: list[str] = []
        killed = bites = 0
        for entity in self._em.get_entities_with_cached(Ant, Transform):
            position = entity.get_component(Transform).position
            dx = position.x - player.x
            dy = position.y - player.y
            distance_sq = dx * dx + dy * dy
            if pulsing and distance_sq <= pulse_sq:
                dead.append(entity.id)
                killed += 1
                continue
            if distance_sq > despawn_sq:
                dead.append(entity.id)
                continue
            if distance_sq <= bite_sq:
                bites += 1
            agent = entity.get_component(FlockingAgent)
            agent.seek_target = player
            velocity = agent.velocity
            if velocity.x or velocity.y:
                sprite = entity.get_component(Sprite)
                sprite.rotation = math.degrees(math.atan2(velocity.y, velocity.x))

        for entity_id in dead:
            self._em.remove_entity(entity_id)
        self._spawner.alive -= len(dead)
        state.kills += killed
        state.bites += bites
        state.health = max(0.0, state.health - bites * BITE_DAMAGE)
