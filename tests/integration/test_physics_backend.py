"""Integration tests for Pymunk backend implementation."""

import pytest

from pyguara.common.types import Vector2
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.types import BodyType, CollisionLayer, PhysicsMaterial, ShapeType


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


# --- body sleeping -----------------------------------------------------------
#
# Chipmunk's own default (sleep_time_threshold = inf) simulates every idle
# body forever. PhysicsConfig now defaults it to 0.5s so settled props and
# debris drop out of the solver. These pin the behaviour the engine relies
# on -- in particular that a direct state write wakes a sleeping body, which
# is what SolidSystem and manual kinematic-style moves depend on.

MAT = PhysicsMaterial()
FLOOR = CollisionLayer()


def _resting_stack(threshold: float = 0.5, count: int = 4) -> PymunkEngine:
    """A floor with `count` boxes dropped on it, stepped until settled."""
    engine = PymunkEngine(substeps=1, sleep_time_threshold=threshold)
    engine.initialize(gravity=Vector2(0, 900))
    floor = engine.create_body("floor", BodyType.STATIC, Vector2(200, 400))
    engine.add_shape(floor, ShapeType.BOX, [400, 20], Vector2(0, 0), MAT, FLOOR, False)
    for i in range(count):
        b = engine.create_body(f"b{i}", BodyType.DYNAMIC, Vector2(200, 380 - i * 21))
        engine.add_shape(b, ShapeType.BOX, [20, 20], Vector2(0, 0), MAT, FLOOR, False)
    for _ in range(600):  # 10s at 60Hz, well past the 0.5s threshold
        engine.update(1 / 60)
    return engine


def test_a_settled_stack_goes_to_sleep():
    engine = _resting_stack()
    dynamic = [engine._bodies[f"b{i}"]._body for i in range(4)]
    assert all(b.is_sleeping for b in dynamic)


def test_sleeping_is_disabled_when_the_threshold_is_zero():
    engine = _resting_stack(threshold=0.0)
    dynamic = [engine._bodies[f"b{i}"]._body for i in range(4)]
    assert not any(b.is_sleeping for b in dynamic)


def test_a_manual_position_write_wakes_a_sleeping_body():
    engine = _resting_stack()
    adapter = engine._bodies["b0"]
    assert adapter._body.is_sleeping

    adapter.position = Vector2(50, 50)

    assert not adapter._body.is_sleeping
    assert adapter.position == Vector2(50, 50)


def test_a_manual_velocity_write_wakes_a_sleeping_body():
    engine = _resting_stack()
    adapter = engine._bodies["b0"]
    assert adapter._body.is_sleeping

    adapter.velocity = Vector2(0, -200)

    assert not adapter._body.is_sleeping


def test_a_sleeping_body_is_still_found_by_queries():
    engine = _resting_stack()
    assert engine._bodies["b0"]._body.is_sleeping
    # b0 landed on the floor at rest; probe where the stack sits.
    found = engine.overlap_box(Vector2(200, 389), Vector2(60, 60))
    assert found is not None
    assert engine.point_query(Vector2(200, engine._bodies["b0"].position.y))


def test_a_negative_sleep_threshold_is_rejected():
    with pytest.raises(ValueError, match="sleep_time_threshold must be non-negative"):
        PymunkEngine(sleep_time_threshold=-0.1)
