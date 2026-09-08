"""SolidMover: solids carry riders and push what's in their way.

`CharacterMover` covers a character moving under its own control; this is
the other half of the model -- a platform (or a crate a character shoves)
moving *the character*. Every test here checks the same thing `move_solid`
promises: an actor riding or in the way ends up exactly where the solid's
motion put it, and if that position has no room, it's flagged rather than
silently allowed to overlap.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.components import (
    CharacterBody,
    Collider,
    MovingSolid,
    Pushable,
    RigidBody,
)
from pyguara.physics.events import OnActorSquished
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.platformer_controller import PlatformerController, PlatformerInput
from pyguara.physics.platformer_system import PlatformerSystem
from pyguara.physics.solid_mover import SolidMover
from pyguara.physics.solid_system import SolidSystem
from pyguara.physics.types import BodyType, ShapeType

pytestmark = pytest.mark.integration

DT = 1.0 / 60.0
HALF = Vector2(12.0, 20.0)


class World:
    """Static geometry, solids and actors, wired the way a game would."""

    def __init__(self) -> None:
        """Create an empty world."""
        self.entities = EntityManager()
        self.dispatcher = EventDispatcher()
        self.engine = PymunkEngine()
        self.engine.set_collision_system(CollisionSystem(self.dispatcher))
        self.physics = PhysicsSystem(
            self.engine, self.entities, self.dispatcher, gravity=Vector2(0, 0)
        )
        self.mover = SolidMover(self.entities, self.engine, self.dispatcher)

    def wall(self, centre: Vector2, dimensions: list[float]) -> Entity:
        """A static, immovable box."""
        entity = self.entities.create_entity()
        entity.add_component(Transform(position=centre))
        entity.add_component(RigidBody(body_type=BodyType.STATIC))
        entity.add_component(Collider(shape_type=ShapeType.BOX, dimensions=dimensions))
        return entity

    def solid(
        self, centre: Vector2, dimensions: list[float], pushable: bool = False
    ) -> Entity:
        """A MovingSolid: still a real KINEMATIC body, as far as Chipmunk cares."""
        entity = self.entities.create_entity()
        entity.add_component(Transform(position=centre))
        entity.add_component(RigidBody(body_type=BodyType.KINEMATIC))
        entity.add_component(Collider(shape_type=ShapeType.BOX, dimensions=dimensions))
        entity.add_component(MovingSolid())
        if pushable:
            entity.add_component(Pushable())
        return entity

    def actor(self, centre: Vector2, dimensions: list[float]) -> Entity:
        """A mover-driven character: no shape in the engine at all."""
        entity = self.entities.create_entity()
        entity.add_component(Transform(position=centre))
        entity.add_component(CharacterBody())
        entity.add_component(Collider(shape_type=ShapeType.BOX, dimensions=dimensions))
        return entity

    def build(self) -> None:
        """Create every body in the backend."""
        self.physics.update(DT)

    def move_solid_by(self, entity: Entity, delta: Vector2) -> None:
        """Apply a solid's authored displacement, then react to it.

        Mirrors what SolidSystem does every tick: something else (a patrol
        script, a tween) moves the Transform first; SolidMover only reacts
        to a displacement that's already happened, it never applies one.
        """
        transform = entity.get_component(Transform)
        transform.position = transform.position + delta
        self.mover.move_solid(entity, delta)


def test_riding_a_platform_moves_with_it() -> None:
    """An actor resting on top of a solid is carried the exact same delta."""
    world = World()
    platform = world.solid(Vector2(400, 480), [200.0, 20.0])
    rider = world.actor(Vector2(400, 480 - 10 - HALF.y), [HALF.x * 2, HALF.y * 2])
    world.build()

    world.move_solid_by(platform, Vector2(50, 0))

    assert rider.get_component(Transform).position == Vector2(450, 480 - 10 - HALF.y)
    assert rider.get_component(CharacterBody).riding == platform.id


def test_an_actor_not_touching_the_solid_is_left_alone() -> None:
    """The control: an actor nowhere near the solid isn't touched."""
    world = World()
    platform = world.solid(Vector2(400, 480), [200.0, 20.0])
    bystander = world.actor(Vector2(400, 100), [HALF.x * 2, HALF.y * 2])
    world.build()

    world.move_solid_by(platform, Vector2(50, 0))

    assert bystander.get_component(Transform).position == Vector2(400, 100)
    assert not bystander.get_component(CharacterBody).riding


def test_a_solid_pushes_an_actor_clear_of_its_new_footprint() -> None:
    """A solid closing in from the side shoves a standing actor clear.

    The actor isn't riding -- it's beside the solid at the same height --
    so this is the push branch, not the carry one.
    """
    world = World()
    platform = world.solid(Vector2(300, 400), [40.0, 40.0])
    actor = world.actor(Vector2(335, 400), [HALF.x * 2, HALF.y * 2])
    world.build()

    world.move_solid_by(platform, Vector2(30, 0))

    # Platform's right face moved from 320 to 350; the actor should be shoved
    # to sit exactly flush against it, not left overlapping.
    pushed = actor.get_component(Transform).position
    assert pushed.x == pytest.approx(362.0)
    assert not actor.get_component(CharacterBody).squished


def test_a_pinned_actor_is_flagged_and_reported() -> None:
    """Pushed into a wall behind it, with nowhere left to go.

    The push formula only resolves the overlap against the solid doing the
    pushing; it has no notion of a wall on the other side. That's what the
    post-push overlap check catches.
    """
    world = World()
    world.wall(Vector2(375, 400), [40.0, 200.0])  # left face at 355
    platform = world.solid(Vector2(300, 400), [40.0, 40.0])
    actor = world.actor(Vector2(335, 400), [HALF.x * 2, HALF.y * 2])
    world.build()

    events: list[OnActorSquished] = []
    world.dispatcher.subscribe(OnActorSquished, events.append)

    world.move_solid_by(platform, Vector2(30, 0))

    assert actor.get_component(CharacterBody).squished
    assert len(events) == 1
    assert events[0].entity_id == actor.id
    assert events[0].solid_entity_id == platform.id


def test_solid_system_reads_delta_from_the_transform_that_already_moved() -> None:
    """SolidSystem never applies a solid's motion -- only reacts to it.

    Whatever authors a platform's patrol (not built here) already moved its
    Transform by the time SolidSystem runs; `previous_position` is how it
    recovers *how far*, the same mechanism the render-interpolation
    snapshot already maintains every fixed tick.
    """
    world = World()
    platform = world.solid(Vector2(400, 480), [200.0, 20.0])
    rider = world.actor(Vector2(400, 480 - 10 - HALF.y), [HALF.x * 2, HALF.y * 2])
    world.build()
    system = SolidSystem(world.entities, world.mover)

    transform = platform.get_component(Transform)
    transform.previous_position = transform.position  # this tick's "before"
    transform.position = transform.position + Vector2(40, 0)  # already moved

    system.update(DT)

    assert rider.get_component(Transform).position == Vector2(440, 480 - 10 - HALF.y)
    assert rider.get_component(CharacterBody).riding == platform.id


def test_solid_system_clears_riding_for_a_platform_left_behind() -> None:
    """Riding is re-decided every tick, not remembered from a stale one."""
    world = World()
    platform = world.solid(Vector2(400, 480), [200.0, 20.0])
    actor = world.actor(Vector2(400, 480 - 10 - HALF.y), [HALF.x * 2, HALF.y * 2])
    world.build()
    system = SolidSystem(world.entities, world.mover)
    actor.get_component(CharacterBody).riding = platform.id  # stale, from before

    transform = platform.get_component(Transform)
    transform.previous_position = transform.position  # didn't move this tick

    system.update(DT)

    assert actor.get_component(CharacterBody).riding is None


FLOOR_TOP = 480.0


class TestPushableCrate:
    """A character shoving a Pushable solid, through PlatformerSystem.

    Grounded, not airborne: `_apply_movement` deliberately refuses to push
    into whatever `on_wall_left`/`on_wall_right` sees while airborne (so a
    jumping character doesn't fight the mover), and that check doesn't
    distinguish a `Pushable` from an ordinary wall. A crate is a ground-level
    mechanic (`guara_falcao`'s GDD calls it "Bash"), so these characters
    stand on a floor like a real one would.
    """

    def _world(self) -> tuple[World, PlatformerSystem, Entity]:
        world = World()
        world.wall(Vector2(400, FLOOR_TOP + 20), [2000.0, 40.0])
        solid_mover = SolidMover(world.entities, world.engine, world.dispatcher)
        platformer = PlatformerSystem(
            world.entities,
            world.engine,
            gravity=Vector2(0, 900),
            solid_mover=solid_mover,
        )
        # A gap, not contact: the character has to walk 48px before it even
        # reaches the crate, so this exercises the approach, not just an
        # already-touching edge case.
        character = world.actor(Vector2(350, FLOOR_TOP - 20), [24.0, 40.0])
        character.add_component(PlatformerController(move_speed=180.0))
        world.build()
        for _ in range(30):  # settle onto the floor before either test starts
            world.physics.update(DT)
            platformer.update(DT)
        return world, platformer, character

    def test_walking_into_a_free_crate_pushes_it_along(self) -> None:
        world, platformer, character = self._world()
        crate = world.solid(Vector2(430, FLOOR_TOP - 20), [40.0, 40.0], pushable=True)
        world.build()

        controller = character.get_component(PlatformerController)
        for _ in range(120):
            controller.pending_input = PlatformerInput(move=1.0)
            world.physics.update(DT)
            platformer.update(DT)

        crate_x = crate.get_component(Transform).position.x
        character_x = character.get_component(Transform).position.x
        assert crate_x > 430, "crate should have been pushed along"
        assert character_x > 350, "character should have kept moving behind it"

    def test_a_crate_blocked_by_a_wall_stops_the_character_too(self) -> None:
        world, platformer, character = self._world()
        crate = world.solid(Vector2(430, FLOOR_TOP - 20), [40.0, 40.0], pushable=True)
        world.wall(Vector2(470, FLOOR_TOP - 20), [20.0, 200.0])  # left face at 460
        world.build()

        controller = character.get_component(PlatformerController)
        for _ in range(150):
            controller.pending_input = PlatformerInput(move=1.0)
            world.physics.update(DT)
            platformer.update(DT)

        crate_x = crate.get_component(Transform).position.x
        # The crate can travel at most 10px before its own right face (450)
        # meets the wall's left face (460).
        assert crate_x <= 440 + 0.5
        character_right = character.get_component(Transform).position.x + 12.0
        crate_left = crate_x - 20.0
        assert character_right <= crate_left + 0.5
