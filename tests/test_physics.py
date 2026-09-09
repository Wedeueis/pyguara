from unittest.mock import MagicMock

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.events import EntityDestroyed
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, CollisionLayer, PhysicsMaterial, ShapeType


def _wire_entity_destroyed(manager: EntityManager, dispatcher: EventDispatcher) -> None:
    """Wire a manager's removal hook to dispatch EntityDestroyed, mirroring
    Scene.resolve_dependencies()."""
    manager.subscribe_entity_removed(
        lambda e: dispatcher.dispatch(EntityDestroyed(entity=e, source=None))
    )


def test_physics_initialization(event_dispatcher):
    mock_engine = MagicMock()
    mock_entity_manager = MagicMock()
    PhysicsSystem(mock_engine, mock_entity_manager, event_dispatcher)

    mock_engine.initialize.assert_called_once()


def test_entity_registration(event_dispatcher):
    mock_engine = MagicMock()
    manager = EntityManager()
    sys = PhysicsSystem(mock_engine, manager, event_dispatcher)

    # Mock Body Handle
    mock_body = MagicMock()
    mock_engine.create_body.return_value = mock_body

    # Setup ECS
    e = manager.create_entity()
    e.add_component(Transform(position=Vector2(10, 10)))
    rb = e.add_component(RigidBody(body_type=BodyType.DYNAMIC))
    e.add_component(Collider(shape_type=ShapeType.CIRCLE, dimensions=[10]))

    # Update - Pull pattern
    sys.update(0.1)

    # Verify Body Creation
    mock_engine.create_body.assert_called_once()
    assert rb._body_handle == mock_body

    # Verify Shape Creation
    mock_engine.add_shape.assert_called_once()

    # Verify Sync (Initial pos)
    # create_body arg 3 is position
    args = mock_engine.create_body.call_args
    assert args[0][2] == Vector2(10, 10)


def test_simulation_sync_dynamic(event_dispatcher):
    """Test Physics -> ECS sync for dynamic bodies."""
    mock_engine = MagicMock()
    manager = EntityManager()
    sys = PhysicsSystem(mock_engine, manager, event_dispatcher)

    mock_body = MagicMock()
    # Simulate physics moving the body
    mock_body.position = Vector2(50, 50)
    mock_body.rotation = 1.5

    e = manager.create_entity()
    trans = e.add_component(Transform(position=Vector2(0, 0)))
    rb = e.add_component(RigidBody(body_type=BodyType.DYNAMIC))
    rb._body_handle = mock_body  # Inject mock handle to skip creation

    # Pull pattern
    sys.update(0.1)

    assert trans.position == Vector2(50, 50)
    assert trans.rotation == 1.5


def test_simulation_sync_kinematic(event_dispatcher):
    """Test ECS -> Physics sync for kinematic bodies."""
    mock_engine = MagicMock()
    manager = EntityManager()
    sys = PhysicsSystem(mock_engine, manager, event_dispatcher)

    mock_body = MagicMock()
    mock_body.position = Vector2(0, 0)

    e = manager.create_entity()
    # Move entity in Game Logic
    e.add_component(Transform(position=Vector2(100, 100)))
    rb = e.add_component(RigidBody(body_type=BodyType.KINEMATIC))
    rb._body_handle = mock_body

    # Pull pattern
    sys.update(0.1)

    # Physics body should have moved to match ECS
    assert mock_body.position == Vector2(100, 100)


# -- Physics teardown bridge (wayfinder ticket 27) --


def test_entity_destroyed_queues_body_and_drains_before_engine_step(event_dispatcher):
    """destroy_body must be called for the removed entity's handle, and
    before the engine steps this frame -- not synchronously at dispatch."""
    mock_engine = MagicMock()
    manager = EntityManager()
    _wire_entity_destroyed(manager, event_dispatcher)
    sys = PhysicsSystem(mock_engine, manager, event_dispatcher)

    mock_body = MagicMock()
    e = manager.create_entity()
    e.add_component(Transform(position=Vector2(0, 0)))
    rb = e.add_component(RigidBody(body_type=BodyType.DYNAMIC))
    rb._body_handle = mock_body

    manager.remove_entity(e.id)

    # Dispatch is synchronous, but teardown must not have happened yet --
    # only queued.
    mock_engine.destroy_body.assert_not_called()

    calls: list[str] = []
    mock_engine.destroy_body.side_effect = lambda *_: calls.append("destroy")
    mock_engine.update.side_effect = lambda *_: calls.append("step")

    sys.update(0.1)

    mock_engine.destroy_body.assert_called_once_with(mock_body)
    assert calls == ["destroy", "step"]

    # Draining is one-shot -- a second update doesn't re-destroy anything.
    sys.update(0.1)
    mock_engine.destroy_body.assert_called_once_with(mock_body)


def test_entity_destroyed_before_body_created_is_noop(event_dispatcher):
    """An entity removed before PhysicsSystem.update() ever ran (so
    `_body_handle` is still None) must not queue a phantom teardown."""
    mock_engine = MagicMock()
    manager = EntityManager()
    _wire_entity_destroyed(manager, event_dispatcher)
    sys = PhysicsSystem(mock_engine, manager, event_dispatcher)

    e = manager.create_entity()
    e.add_component(Transform(position=Vector2(0, 0)))
    e.add_component(RigidBody(body_type=BodyType.DYNAMIC))

    manager.remove_entity(e.id)
    sys.update(0.1)

    mock_engine.destroy_body.assert_not_called()


def test_entity_destroyed_without_rigidbody_is_noop(event_dispatcher):
    """An entity with no RigidBody at all must not error out the handler."""
    mock_engine = MagicMock()
    manager = EntityManager()
    _wire_entity_destroyed(manager, event_dispatcher)
    sys = PhysicsSystem(mock_engine, manager, event_dispatcher)

    e = manager.create_entity()
    e.add_component(Transform(position=Vector2(0, 0)))

    manager.remove_entity(e.id)
    sys.update(0.1)

    mock_engine.destroy_body.assert_not_called()


def test_destroy_body_removes_body_and_shapes_from_pymunk_space():
    """PymunkEngine.destroy_body() against the real backend, per ticket 15's
    decision: body and shapes both leave `self.space`, and `self._bodies`
    drops the entry."""
    engine = PymunkEngine()
    engine.initialize(gravity=Vector2(0, 0))

    handle = engine.create_body("e1", BodyType.DYNAMIC, Vector2(0, 0), mass=1.0)
    engine.add_shape(
        handle,
        ShapeType.CIRCLE,
        [10],
        Vector2(0, 0),
        material=PhysicsMaterial(),
        collision_layer=CollisionLayer(),
        is_sensor=False,
    )

    assert "e1" in engine._bodies
    assert len(engine.space.bodies) == 1
    assert len(engine.space.shapes) == 1

    engine.destroy_body(handle)

    assert "e1" not in engine._bodies
    assert len(engine.space.bodies) == 0
    assert len(engine.space.shapes) == 0


def test_destroyed_entity_body_stops_advancing_through_physics_system(event_dispatcher):
    """End-to-end: PhysicsSystem + real PymunkEngine. After an entity is
    removed, its body is torn down and no longer participates in
    simulation -- stepping again produces no further movement."""
    engine = PymunkEngine()
    manager = EntityManager()
    _wire_entity_destroyed(manager, event_dispatcher)
    sys = PhysicsSystem(engine, manager, event_dispatcher, gravity=Vector2(0, 100))

    e = manager.create_entity()
    e.add_component(Transform(position=Vector2(0, 0)))
    rb = e.add_component(RigidBody(body_type=BodyType.DYNAMIC))

    sys.update(0.1)
    assert rb._body_handle is not None
    handle = rb._body_handle
    pymunk_body = handle._body

    manager.remove_entity(e.id)
    sys.update(0.1)

    assert pymunk_body not in engine.space.bodies
    assert engine._bodies == {}

    # Stepping further must not raise (body is fully detached) and must not
    # resurrect it into the space.
    sys.update(0.1)
    assert engine._bodies == {}
