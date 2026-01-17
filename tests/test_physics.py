from unittest.mock import MagicMock
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.components import RigidBody, Collider
from pyguara.physics.types import BodyType, ShapeType
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager


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

    # Update - P2-013: Pull pattern
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

    # P2-013: Pull pattern
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

    # P2-013: Pull pattern
    sys.update(0.1)

    # Physics body should have moved to match ECS
    assert mock_body.position == Vector2(100, 100)
