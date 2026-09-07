"""Collision behaviour a 2D engine must get right, through the real ECS path.

These go through EntityManager -> PhysicsSystem -> PymunkEngine, wired the
way `application/bootstrap.py` wires it, because that is where the behaviour
a game actually sees is decided. Testing the backend alone would miss the
wiring, and testing pymunk alone would test pymunk.
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
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.events import OnCollisionBegin
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, PhysicsMaterial, ShapeType

pytestmark = pytest.mark.integration

DT = 1.0 / 60.0


class World:
    """An ECS world with physics wired as the application bootstrap wires it."""

    def __init__(self, gravity: Vector2, substeps: int | None = None) -> None:
        """Build the world, optionally overriding the engine's substep count."""
        self.entities = EntityManager()
        self.dispatcher = EventDispatcher()
        engine = PymunkEngine() if substeps is None else PymunkEngine(substeps)
        engine.set_collision_system(CollisionSystem(self.dispatcher))
        self.system = PhysicsSystem(
            engine, self.entities, self.dispatcher, gravity=gravity
        )

    def add(
        self,
        position: Vector2,
        body_type: BodyType,
        dimensions: list[float],
        shape: ShapeType = ShapeType.BOX,
        material: PhysicsMaterial | None = None,
    ) -> Entity:
        """Add a body with a collider at a world position."""
        entity = self.entities.create_entity()
        entity.add_component(Transform(position=position))
        entity.add_component(RigidBody(mass=1.0, body_type=body_type))
        entity.add_component(
            Collider(
                shape_type=shape,
                dimensions=dimensions,
                material=material or PhysicsMaterial(),
            )
        )
        return entity

    def run(self, ticks: int) -> None:
        """Advance the simulation."""
        for _ in range(ticks):
            self.system.update(DT)


def fire_at_wall(speed: float, wall_thickness: float, substeps: int | None) -> float:
    """Launch a small body at a wall and return where it ends up.

    Args:
        speed: Horizontal speed in pixels per second.
        wall_thickness: Width of the static wall at x=400.
        substeps: Engine substep count, or None for the default.

    Returns:
        The body's final x. Greater than 400 means it went through.
    """
    world = World(gravity=Vector2(0, 0), substeps=substeps)
    world.add(Vector2(400, 300), BodyType.STATIC, [wall_thickness, 400.0])
    bullet = world.add(Vector2(100, 300), BodyType.DYNAMIC, [8.0, 8.0])

    world.run(1)  # one tick creates the bodies
    bullet.get_component(RigidBody)._body_handle.velocity = Vector2(speed, 0)
    world.run(120)

    return bullet.get_component(Transform).position.x


@pytest.mark.parametrize("speed", [600.0, 900.0, 1200.0])
def test_a_fast_body_does_not_pass_through_a_thin_wall(speed: float) -> None:
    """A body at platformer speeds is stopped by a 10px wall.

    600 px/s is not exotic: under the 900 px/s^2 gravity `guara_falcao`
    uses, a character reaches it after two thirds of a second of falling.
    With a single solver step per tick it moved 10px per step and cleared a
    10px wall outright, so a player falling onto a thin platform went
    straight through it.
    """
    assert fire_at_wall(speed, wall_thickness=10.0, substeps=None) < 400.0


def test_substepping_is_what_stops_it() -> None:
    """Pin the mechanism, not just the symptom.

    One step per tick tunnels at a speed four substeps catch. If this ever
    stops holding, the fix above is being carried by something else and the
    substep count is no longer doing the work its cost is paying for.
    """
    assert fire_at_wall(1200.0, wall_thickness=10.0, substeps=1) > 400.0
    assert fire_at_wall(1200.0, wall_thickness=10.0, substeps=4) < 400.0


def test_substeps_must_be_positive() -> None:
    """Zero substeps would freeze the simulation rather than fail loudly."""
    with pytest.raises(ValueError, match="substeps must be positive"):
        PymunkEngine(0)


def test_a_dropped_box_comes_to_rest_on_the_ground() -> None:
    """Substepping must not disturb ordinary resting contact.

    Ground top is y=480 and the box is 50 tall, so it settles at y=455.
    """
    world = World(gravity=Vector2(0, 900))
    world.add(Vector2(400, 500), BodyType.STATIC, [800.0, 40.0])
    box = world.add(Vector2(400, 100), BodyType.DYNAMIC, [50.0, 50.0])

    world.run(240)

    assert box.get_component(Transform).position.y == pytest.approx(455, abs=2)


def test_a_collision_raises_an_event() -> None:
    """Contact reaches game code as an OnCollisionBegin."""
    world = World(gravity=Vector2(0, 900))
    seen: list[OnCollisionBegin] = []
    world.dispatcher.subscribe(OnCollisionBegin, seen.append)

    world.add(Vector2(400, 500), BodyType.STATIC, [800.0, 40.0])
    world.add(Vector2(400, 100), BodyType.DYNAMIC, [50.0, 50.0])
    world.run(240)

    assert seen, "a box landing on the ground raised no collision event"
