"""Tests for JointSystem -- Joint components becoming live constraints.

``test_physics_joints.py`` covers the ``Joint`` dataclass, the factory
functions and the backend's ``create_joint``. None of that connects a
``Joint`` *component* to the simulation: before ``JointSystem`` existed,
adding one to an entity did nothing at all -- a pin-jointed body just
free-fell. These tests drive the component through the real backend.
"""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.events import EntityDestroyed
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.joint_system import JointSystem
from pyguara.physics.joints import Joint, create_pin_joint, create_rope_chain
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType

DT = 1.0 / 60.0


class World:
    """ECS world with PhysicsSystem + JointSystem, wired like a scene."""

    def __init__(self, gravity: Vector2 = Vector2(0, 900)) -> None:
        self.entities = EntityManager()
        self.dispatcher = EventDispatcher()
        self.engine = PymunkEngine()
        self.physics = PhysicsSystem(
            self.engine, self.entities, self.dispatcher, gravity=gravity
        )
        self.joints = JointSystem(self.engine, self.entities, self.dispatcher)
        # Mirror Scene.resolve_dependencies(): republish removals as events.
        self.entities.subscribe_entity_removed(
            lambda e: self.dispatcher.dispatch(EntityDestroyed(entity=e, source=None))
        )

    def step(self, count: int = 1) -> None:
        for _ in range(count):
            self.physics.update(DT)
            self.joints.update(DT)

    def body(self, pos: Vector2, body_type: BodyType = BodyType.DYNAMIC):
        e = self.entities.create_entity()
        e.add_component(Transform(position=pos))
        e.add_component(RigidBody(body_type=body_type, mass=1.0))
        e.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[10, 10]))
        return e

    @property
    def constraint_count(self) -> int:
        return len(self.engine.space.constraints)


def test_pin_joint_holds_body_at_rest_length():
    world = World()
    anchor = world.body(Vector2(100, 100), BodyType.STATIC)
    bob = world.body(Vector2(100, 150))
    bob.add_component(create_pin_joint(target_entity_id=anchor.id))

    world.step(180)

    dist = bob.get_component(Transform).position.distance_to(Vector2(100, 100))
    assert world.constraint_count == 1
    assert 45 < dist < 55, f"pinned body drifted to {dist:.1f}px (expected ~50)"


def test_joint_added_before_bodies_exist_links_up_later():
    """Joint tolerates being created the same tick as its bodies."""
    world = World()
    anchor = world.body(Vector2(100, 100), BodyType.STATIC)
    bob = world.body(Vector2(100, 150))
    # Add the joint the same tick, before any update has created bodies.
    joint = bob.add_component(create_pin_joint(target_entity_id=anchor.id))
    assert joint._joint_handle is None

    world.step(1)  # PhysicsSystem creates bodies, JointSystem still waiting/creating
    world.step(1)

    assert joint._joint_handle is not None
    assert world.constraint_count == 1


def test_constraint_released_when_target_entity_destroyed():
    world = World()
    anchor = world.body(Vector2(100, 100), BodyType.STATIC)
    bob = world.body(Vector2(100, 150))
    bob.add_component(create_pin_joint(target_entity_id=anchor.id))
    world.step(10)
    assert world.constraint_count == 1

    world.entities.remove_entity(anchor.id)
    world.step(1)

    assert world.constraint_count == 0
    assert bob.get_component(Joint)._joint_handle is None


def test_constraint_released_when_owner_entity_destroyed():
    world = World()
    anchor = world.body(Vector2(100, 100), BodyType.STATIC)
    bob = world.body(Vector2(100, 150))
    bob.add_component(create_pin_joint(target_entity_id=anchor.id))
    world.step(10)
    assert world.constraint_count == 1

    world.entities.remove_entity(bob.id)
    world.step(1)

    assert world.constraint_count == 0


def test_constraint_released_when_joint_component_removed():
    world = World()
    anchor = world.body(Vector2(100, 100), BodyType.STATIC)
    bob = world.body(Vector2(100, 150))
    bob.add_component(create_pin_joint(target_entity_id=anchor.id))
    world.step(10)
    assert world.constraint_count == 1

    bob.remove_component(Joint)
    world.step(1)

    assert world.constraint_count == 0


def test_self_targeting_joint_is_ignored():
    world = World()
    bob = world.body(Vector2(100, 150))
    bob.add_component(create_pin_joint(target_entity_id=bob.id))

    world.step(5)  # must not raise

    assert world.constraint_count == 0
    assert bob.get_component(Joint)._joint_handle is None


def test_unconfigured_joint_is_ignored():
    world = World()
    bob = world.body(Vector2(100, 150))
    bob.add_component(Joint())  # target_entity_id == ""

    world.step(5)

    assert world.constraint_count == 0


def test_missing_target_defers_without_error():
    world = World()
    bob = world.body(Vector2(100, 150))
    bob.add_component(create_pin_joint(target_entity_id="does-not-exist"))

    world.step(5)

    assert world.constraint_count == 0
    assert bob.get_component(Joint)._joint_handle is None


def test_rope_chain_holds_together():
    world = World()
    segments = create_rope_chain(
        world.entities,
        start_position=Vector2(200, 50),
        segment_count=4,
        segment_length=20.0,
    )
    # create_rope_chain already gives each segment a RigidBody and a Collider.
    segments[0].get_component(RigidBody).body_type = BodyType.STATIC

    world.step(240)

    # 3 spring links for 4 segments.
    assert world.constraint_count == 3
    ys = [s.get_component(Transform).position.y for s in segments]
    # Each segment hangs below the previous, none has run away to infinity.
    assert ys == sorted(ys)
    assert ys[-1] - ys[0] < 200, f"rope stretched to {ys[-1] - ys[0]:.0f}px"


def test_cleanup_releases_all_constraints():
    world = World()
    anchor = world.body(Vector2(100, 100), BodyType.STATIC)
    bob = world.body(Vector2(100, 150))
    bob.add_component(create_pin_joint(target_entity_id=anchor.id))
    world.step(10)
    assert world.constraint_count == 1

    world.joints.cleanup()

    assert world.constraint_count == 0
