"""Trigger volumes, end to end through the real pymunk backend.

The component-level tests in ``tests/test_trigger_volumes.py`` dispatch
``OnTriggerEnter``/``Exit`` by hand and never touch pymunk. That hid two
breakages for a long time:

* ``CollisionSystem`` assumed the sensor was always the first entity in a
  contact pair. Chipmunk's pair order is arbitrary, so trigger events came
  out with ``trigger_entity`` and ``other_entity`` swapped about half the
  time, and ``TriggerSystem`` silently dropped every swapped one.
* A ``TriggerVolume`` entity built the documented way -- ``Transform`` plus
  ``TriggerVolume``, no ``RigidBody`` -- never entered the simulation at
  all, because ``PhysicsSystem`` only registers shapes for entities that
  have a ``RigidBody``.

These drive the whole stack the way ``application/bootstrap.py`` wires it.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.trigger_system import TriggerSystem
from pyguara.physics.trigger_volume import EntityTags, TriggerVolume
from pyguara.physics.types import BodyType, ShapeType

pytestmark = pytest.mark.integration

DT = 1.0 / 60.0


class World:
    """ECS world with physics + collision + trigger systems wired together."""

    def __init__(self, gravity: Vector2 = Vector2(0, 60)) -> None:
        self.entities = EntityManager()
        self.dispatcher = EventDispatcher()
        self.engine = PymunkEngine()
        self.engine.set_collision_system(CollisionSystem(self.dispatcher))
        self.physics = PhysicsSystem(
            self.engine, self.entities, self.dispatcher, gravity=gravity
        )
        self.triggers = TriggerSystem(self.entities, self.dispatcher)

    def step(self, count: int = 1) -> None:
        for _ in range(count):
            self.triggers.update(DT)
            self.physics.update(DT)
            self.triggers.update(DT)  # drain events the step produced

    def make_zone(self, **kwargs):
        zone = self.entities.create_entity()
        zone.add_component(Transform(position=Vector2(100, 100)))
        zone.add_component(
            TriggerVolume(shape_type=ShapeType.BOX, dimensions=[80, 80], **kwargs)
        )
        return zone

    def make_faller(self, y: float = 40.0, tags: set[str] | None = None):
        ball = self.entities.create_entity()
        ball.add_component(Transform(position=Vector2(100, y)))
        ball.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=1.0))
        ball.add_component(Collider(shape_type=ShapeType.CIRCLE, dimensions=[5]))
        if tags:
            ball.add_component(EntityTags(tags=tags))
        return ball


@pytest.mark.parametrize("zone_first", [True, False])
def test_faller_registers_and_clears_regardless_of_creation_order(zone_first):
    """entities_inside holds the body while it overlaps, empties on exit.

    Parametrised on creation order because that is what decides Chipmunk's
    pair ordering here, and the pre-fix code worked for exactly one of the
    two orders.
    """
    world = World()
    if zone_first:
        zone = world.make_zone()
        ball = world.make_faller()
    else:
        ball = world.make_faller()
        zone = world.make_zone()

    tv = zone.get_component(TriggerVolume)
    seen_inside = False
    for _ in range(240):
        world.step()
        if tv.contains_entity(ball.id):
            seen_inside = True
        if seen_inside and tv.is_empty():
            break

    assert seen_inside, "ball never registered as inside the trigger"
    assert tv.is_empty(), "ball left the trigger but was not removed"


def test_documented_trigger_has_no_rigidbody_but_still_fires():
    """A zone built the way the docstring shows still emits events.

    ``TriggerSystem`` must add both the sensor Collider and a static
    RigidBody; without the body the sensor shape never reaches the space.
    """
    world = World()
    zone = world.make_zone()
    assert not zone.has_component(RigidBody)
    assert not zone.has_component(Collider)

    ball = world.make_faller()
    world.step(2)

    assert zone.has_component(Collider)
    assert zone.has_component(RigidBody)
    assert zone.get_component(RigidBody).body_type == BodyType.STATIC

    tv = zone.get_component(TriggerVolume)
    entered = any((world.step(), tv.contains_entity(ball.id))[1] for _ in range(180))
    assert entered


def test_tag_filter_end_to_end():
    """Only entities whose tags match get tracked."""
    world = World()
    zone = world.make_zone(tags={"player"})
    matching = world.make_faller(tags={"player"})
    world.step(1)
    other = world.entities.create_entity()
    other.add_component(Transform(position=Vector2(100, 45)))
    other.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=1.0))
    other.add_component(Collider(shape_type=ShapeType.CIRCLE, dimensions=[5]))
    other.add_component(EntityTags(tags={"enemy"}))

    tv = zone.get_component(TriggerVolume)
    saw_matching = False
    for _ in range(180):
        world.step()
        if tv.contains_entity(matching.id):
            saw_matching = True
        assert not tv.contains_entity(other.id), "unmatched tag was tracked"
    assert saw_matching


def test_one_shot_deactivates_after_first_entry():
    """A one-shot zone goes inactive once something enters it."""
    world = World()
    zone = world.make_zone(one_shot=True)
    world.make_faller()

    tv = zone.get_component(TriggerVolume)
    for _ in range(180):
        world.step()
        if not tv.active:
            break

    assert tv.active is False
