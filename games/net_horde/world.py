"""What the host simulates, and how anyone draws it.

Only the host runs this simulation. A client has no flocking and no spawning: everything
it draws arrived over the network, except its own character, which it predicts.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer
from pyguara.kits.topdown_movement import TopDownBody, TopDownPrediction, TopDownSystem
from pyguara.net import (
    Angle,
    CommandSchema,
    PredictionHost,
    Quantised,
    QuantisedVector,
    Replicated,
    ReplicationSchema,
    UInt8,
)
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.character_mover import CharacterMover
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType

ARENA = Vector2(480, 480)
HORDE_SIZE = 200
DROP_EVERY_TICKS = 120
SWARM_RADIUS = 150.0
SWARM_RATE = 0.4
TICK = 1 / 60

HOST_SLOT = 0
PLAYER_SPEED = 180.0
PLAYER_SIZE = 20.0
PLAYER_START = ARENA / 2
# Centre x, centre y, width, height. Both machines build the same ones.
WALLS = (
    (240.0, -10.0, 500.0, 20.0),
    (240.0, 490.0, 500.0, 20.0),
    (-10.0, 240.0, 20.0, 500.0),
    (490.0, 240.0, 20.0, 500.0),
    (130.0, 130.0, 60.0, 60.0),
    (350.0, 130.0, 60.0, 60.0),
    (130.0, 350.0, 60.0, 60.0),
    (350.0, 350.0, 60.0, 60.0),
)

WALL_COLOR = Color(70, 76, 92)
PLAYER_COLORS = (
    Color(250, 230, 90),
    Color(120, 230, 240),
    Color(240, 130, 220),
    Color(170, 240, 120),
)
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


@dataclass(slots=True)
class Avatar(StrictComponent):
    """Marks a player's character.

    Attributes:
        slot: Whose it is.
    """

    slot: int = 0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


@dataclass(frozen=True, slots=True)
class Move:
    """What a player is doing on one tick: which way they're pushing, each axis -1 to 1."""

    x: float = 0.0
    y: float = 0.0


NO_MOVE = Move()


def make_commands() -> CommandSchema[Move]:
    """Return how a command is packed. Host and clients must build the same one."""
    return CommandSchema(Move, x=Quantised(step=1 / 64), y=Quantised(step=1 / 64))


def velocity_of(command: Move) -> Vector2:
    """Turn a command into a velocity, on both machines.

    On the host this came from the network, so it's limited here. A modified client
    can't push harder than a held key.

    Args:
        command: The command.

    Returns:
        The velocity, at most `PLAYER_SPEED`.
    """
    direction = Vector2(command.x, command.y)
    if direction.magnitude > 1.0:
        direction = direction.normalize()
    return direction * PLAYER_SPEED


def make_solids() -> tuple[PymunkEngine, CharacterMover]:
    """Return this machine's own copy of the walls, and a mover against them."""
    solids = EntityManager()
    engine = PymunkEngine()
    engine.initialize(Vector2(0, 0))
    physics = PhysicsSystem(engine, solids, EventDispatcher())
    for x, y, width, height in WALLS:
        wall = solids.create_entity()
        wall.add_component(Transform(position=Vector2(x, y)))
        wall.add_component(RigidBody(body_type=BodyType.STATIC))
        wall.add_component(
            Collider(shape_type=ShapeType.BOX, dimensions=[width, height])
        )
    physics.update(TICK)
    return engine, CharacterMover(engine)


def _add_character(world: EntityManager) -> Entity:
    entity = world.create_entity()
    entity.add_component(Transform(position=PLAYER_START))
    entity.add_component(Avatar())
    entity.add_component(TopDownBody())
    entity.add_component(
        Collider(shape_type=ShapeType.BOX, dimensions=[PLAYER_SIZE, PLAYER_SIZE])
    )
    return entity


def make_schema() -> ReplicationSchema:
    """Return what crosses the wire. Host and clients must build the same one."""
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=0.25), rotation=Angle())
    schema.register(Tint, index=UInt8())
    schema.register(Avatar, slot=UInt8())
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

    return {
        "enemy": enemy,
        "drop": drop,
        "player": lambda: _add_character(world),
    }


class HordeSimulation:
    """A flock chasing a moving point, players, and drops for each. Host only."""

    def __init__(
        self,
        world: EntityManager,
        prediction: PredictionHost[Move] | None = None,
        seed: int = 1,
    ) -> None:
        """Create the horde.

        Args:
            world: The host's world.
            prediction: Where remote players' commands come from.
            seed: Decides everything random here.
        """
        self._world = world
        self._prediction = prediction
        self._engine, self._mover = make_solids()
        self._topdown = TopDownSystem(world, self._engine, SpatialHash(cell_size=48.0))
        self._avatars: dict[int, Entity] = {}
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
        for slot in [s for s in self._avatars if s not in slots]:
            if self._prediction is not None:
                self._prediction.bind(slot, None)
            self._world.remove_entity(self._avatars.pop(slot).id)
        for slot in slots:
            if slot in self._avatars:
                continue
            entity = _add_character(self._world)
            entity.get_component(Avatar).slot = slot
            entity.get_component(Transform).position = PLAYER_START + Vector2(
                (slot - 1.5) * 2 * PLAYER_SIZE, 0
            )
            entity.add_component(Replicated("player", controller=slot))
            self._avatars[slot] = entity
            if self._prediction is not None:
                self._prediction.bind(
                    slot, TopDownPrediction(entity, self._mover, velocity_of)
                )

    def avatar(self, slot: int) -> Entity | None:
        """Return a player's character, or None if they have none."""
        return self._avatars.get(slot)

    def fixed_update(self, tick: int = 0, local: Move = NO_MOVE) -> None:
        """Advance one tick.

        Args:
            tick: The tick being simulated, which is the one each command must name.
            local: What the host's own player is doing.
        """
        for slot, entity in self._avatars.items():
            if slot == HOST_SLOT or self._prediction is None:
                command = local
            else:
                command = self._prediction.take(slot, tick)
            entity.get_component(TopDownBody).velocity = velocity_of(command)
        self._topdown.update(TICK)

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
    for x, y, width, height in WALLS[4:]:
        renderer.draw_rect(
            Rect(origin.x + x - width / 2, origin.y + y - height / 2, width, height),
            WALL_COLOR,
        )
    drawn = 0
    # Characters are drawn last, so the horde can't hide the one you're steering.
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
    half = PLAYER_SIZE / 2
    for entity in world.get_entities_with(Transform, Avatar):
        at = origin + entity.get_component(Transform).position
        slot = entity.get_component(Avatar).slot
        renderer.draw_rect(
            Rect(at.x - half, at.y - half, PLAYER_SIZE, PLAYER_SIZE),
            PLAYER_COLORS[slot % len(PLAYER_COLORS)],
        )
    return drawn
