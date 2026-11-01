"""What the host simulates, and how anyone draws it.

Only the host runs this simulation. A client has no flocking and no spawning: everything
it draws arrived over the network, which is the point of the demo.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import IRenderer
from pyguara.net import (
    Angle,
    QuantisedVector,
    Replicated,
    ReplicationSchema,
    UInt8,
)

ARENA = Vector2(480, 480)
HORDE_SIZE = 200
DROP_EVERY_TICKS = 120
SWARM_RADIUS = 150.0
SWARM_RATE = 0.4
TICK = 1 / 60

ENEMY_COLORS = (Color(230, 110, 80), Color(240, 180, 70), Color(120, 200, 110))
DROP_COLOR = Color(120, 180, 255)
BACKGROUND = Color(24, 26, 32)
ARENA_COLOR = Color(38, 42, 52)


@dataclass(slots=True)
class Tint(StrictComponent):
    """Which colour to draw. Data every client needs, and interpolating it means nothing.

    Attributes:
        index: Into `ENEMY_COLORS`.
    """

    index: int = 0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class Drop(StrictComponent):
    """Marks a drop, which only its owner ever hears about."""

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


def make_schema() -> ReplicationSchema:
    """Return what crosses the wire. Host and clients must build the same one."""
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=0.25), rotation=Angle())
    schema.register(Tint, index=UInt8())
    return schema


def make_spawners(world: EntityManager) -> dict[str, object]:
    """Return how a client creates each thing it can be told about.

    Args:
        world: The client's world.

    Returns:
        Name to a function creating it. A name from the network can only choose among these.
    """

    def enemy() -> Entity:
        entity = world.create_entity()
        entity.add_component(Transform())
        entity.add_component(Tint())
        return entity

    def drop() -> Entity:
        entity = enemy()
        entity.add_component(Drop())
        return entity

    return {"enemy": enemy, "drop": drop}


class HordeSimulation:
    """A flock chasing a moving point, with drops for each player. Host only."""

    def __init__(self, world: EntityManager, seed: int = 1) -> None:
        """Create the horde.

        Args:
            world: The host's world.
            seed: Decides everything random here.
        """
        self._world = world
        self._rng = random.Random(seed)
        self._flock = FlockingSystem(world, cell_size=48.0)
        self._ticks = 0
        self._player_slots: list[int] = []
        self._drops: list[Entity] = []
        for index in range(HORDE_SIZE):
            self._spawn_enemy(index % len(ENEMY_COLORS))

    def _spawn_enemy(self, tint: int) -> Entity:
        entity = self._world.create_entity()
        entity.add_component(
            Transform(
                position=Vector2(
                    self._rng.uniform(0, ARENA.x), self._rng.uniform(0, ARENA.y)
                )
            )
        )
        entity.add_component(Tint(index=tint))
        entity.add_component(
            FlockingAgent(max_speed=70.0, seek_weight=1.0, seek_target=ARENA / 2)
        )
        entity.add_component(Replicated("enemy"))
        return entity

    def set_players(self, slots: list[int]) -> None:
        """Say who gets drops.

        Args:
            slots: Every player's slot, including the host's 0.
        """
        self._player_slots = slots

    def fixed_update(self) -> None:
        """Advance one tick."""
        self._ticks += 1
        angle = self._ticks * TICK * SWARM_RATE
        target = ARENA / 2 + Vector2(math.cos(angle), math.sin(angle)) * SWARM_RADIUS
        for entity in self._world.get_entities_with(FlockingAgent):
            entity.get_component(FlockingAgent).seek_target = target
        self._flock.update(TICK)
        if self._ticks % DROP_EVERY_TICKS == 0:
            self._drop_for_everyone()

    def _drop_for_everyone(self) -> None:
        """Roll one drop per player, each seen only by that player."""
        for drop in self._drops:
            self._world.remove_entity(drop.id)
        self._drops.clear()
        for slot in self._player_slots:
            entity = self._world.create_entity()
            entity.add_component(
                Transform(
                    position=Vector2(
                        self._rng.uniform(40, ARENA.x - 40),
                        self._rng.uniform(40, ARENA.y - 40),
                    )
                )
            )
            entity.add_component(Tint())
            entity.add_component(Drop())
            entity.add_component(Replicated("drop", owner=slot))
            self._drops.append(entity)


def draw_world(
    renderer: IRenderer,
    world: EntityManager,
    origin: Vector2,
    my_slot: int,
) -> int:
    """Draw one player's view of a world.

    The host's world holds everybody's drops, so this has to filter by owner. A client's
    never holds anyone else's, since they were never sent.

    Args:
        renderer: Where to draw.
        world: The world to draw.
        origin: Where the arena's corner goes on screen.
        my_slot: Whose view this is.

    Returns:
        How many things were drawn.
    """
    renderer.draw_rect(Rect(origin.x, origin.y, ARENA.x, ARENA.y), ARENA_COLOR)
    drawn = 0
    for entity in world.get_entities_with(Transform, Tint):
        position = entity.get_component(Transform).position
        at = origin + position
        if entity.has_component(Drop):
            if (
                entity.has_component(Replicated)
                and entity.get_component(Replicated).owner != my_slot
            ):
                continue
            renderer.draw_rect(Rect(at.x - 6, at.y - 6, 12, 12), DROP_COLOR)
        else:
            color = ENEMY_COLORS[entity.get_component(Tint).index % len(ENEMY_COLORS)]
            renderer.draw_rect(Rect(at.x - 2, at.y - 2, 5, 5), color)
        drawn += 1
    return drawn
