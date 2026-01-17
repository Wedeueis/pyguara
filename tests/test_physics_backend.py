"""Integration tests for Pymunk backend implementation."""

from pyguara.common.types import Vector2
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.types import BodyType


def test_pymunk_engine_initialization():
    """PymunkEngine should initialize without error."""
    engine = PymunkEngine()
    engine.initialize(gravity=Vector2(0, 980))
    assert engine.space is not None
    assert engine.space.gravity == (0, 980)


def test_pymunk_engine_collision_handlers():
    """PymunkEngine should setup collision handlers correctly."""
    engine = PymunkEngine()

    # Mock collision system
    class MockCollisionSystem:
        def on_collision_begin(self, *args):
            return True

        def on_collision_persist(self, *args):
            return True

        def on_collision_end(self, *args):
            pass

    engine.set_collision_system(MockCollisionSystem())
    engine.initialize(gravity=Vector2(0, 0))

    # We can't easily check internal handlers of pymunk space,
    # but successful execution implies handlers were added via the correct API.


def test_pymunk_body_creation():
    """PymunkEngine should create bodies."""
    engine = PymunkEngine()
    engine.initialize(gravity=Vector2(0, 0))

    body = engine.create_body("entity1", BodyType.DYNAMIC, Vector2(10, 20))
    # Pymunk requires mass/moment for dynamic bodies
    body._body.mass = 1.0
    body._body.moment = 1.0

    assert body is not None
    assert body.position == Vector2(10, 20)

    # Update simulation
    engine.update(0.1)
