"""Rapier's joints keep the meaning each joint type has.

The joint types map onto constraints as they did on Chipmunk (`PIN` is a
rod, `SLIDER` a pair of distance limits), and what is held here is that
mapping's behaviour, to a pixel or a degree.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.common.types import Vector2
from pyguara.physics.backends.rapier_impl import RapierEngine
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    JointType,
    PhysicsMaterial,
    ShapeType,
)

DT = 1.0 / 60.0
SOLID = PhysicsMaterial(friction=0.5, restitution=0.0, density=1.0)
ORIGIN = Vector2(0, 0)


@pytest.fixture
def engine() -> Any:
    built: Any = RapierEngine()
    built.initialize(Vector2(0, 980))
    yield built
    built.cleanup()


def _box(
    engine: Any,
    entity: str,
    at: Vector2,
    kind: BodyType = BodyType.DYNAMIC,
    **body: Any,
) -> Any:
    handle = engine.create_body(entity, kind, at, **body)
    engine.add_shape(
        handle, ShapeType.BOX, [20, 20], ORIGIN, SOLID, CollisionLayer(), False
    )
    return handle


def _joint(
    engine: Any,
    a: Any,
    b: Any,
    kind: JointType,
    low: float = 0.0,
    high: float = 0.0,
    stiffness: float = 0.0,
    damping: float = 0.0,
    max_force: float = 0.0,
    collide: bool = False,
) -> Any:
    return engine.create_joint(
        a, b, kind, ORIGIN, ORIGIN, low, high, stiffness, damping, max_force, collide
    )


def _run(engine: Any, seconds: float) -> None:
    for _ in range(round(seconds / DT)):
        engine.update(DT)


def _distance(a: Any, b: Any) -> float:
    return (a.position - b.position).length


def test_a_pin_is_a_rod_at_the_starting_distance(engine: Any) -> None:
    anchor = _box(engine, "anchor", Vector2(0, 0), BodyType.STATIC)
    bob = _box(engine, "bob", Vector2(100, 0))
    _joint(engine, anchor, bob, JointType.PIN)
    _run(engine, 2.0)
    assert _distance(anchor, bob) == pytest.approx(100.0, abs=1.0)
    assert bob.position.y > 20, "it swung down"


def test_distance_limits_hold_the_far_end(engine: Any) -> None:
    anchor = _box(engine, "anchor", Vector2(0, 0), BodyType.STATIC)
    bob = _box(engine, "bob", Vector2(0, 40))
    _joint(engine, anchor, bob, JointType.DISTANCE, 30.0, 120.0)
    _run(engine, 2.0)
    assert _distance(anchor, bob) == pytest.approx(120.0, abs=1.5)


def test_a_slider_is_distance_limits_too(engine: Any) -> None:
    anchor = _box(engine, "anchor", Vector2(0, 0), BodyType.STATIC)
    bob = _box(engine, "bob", Vector2(0, 40))
    _joint(engine, anchor, bob, JointType.SLIDER, 30.0, 80.0)
    _run(engine, 2.0)
    assert _distance(anchor, bob) == pytest.approx(80.0, abs=1.5)


def test_equal_distance_limits_are_a_stiff_spring(engine: Any) -> None:
    anchor = _box(engine, "anchor", Vector2(0, 0), BodyType.STATIC)
    bob = _box(engine, "bob", Vector2(0, 50))
    _joint(engine, anchor, bob, JointType.DISTANCE, 50.0, 50.0)
    # Damping 100 on a mass of 400 is underdamped, so it still swings after
    # seconds: the mean length is what settles. 400 mass under 980 gravity
    # on a 10000 spring stretches 39.2.
    samples = []
    for _ in range(600):
        engine.update(DT)
        samples.append(_distance(anchor, bob))
    assert sum(samples) / len(samples) == pytest.approx(89.2, abs=3.0)


def test_a_spring_settles_where_its_force_meets_gravity(engine: Any) -> None:
    anchor = _box(engine, "anchor", Vector2(0, 0), BodyType.STATIC)
    bob = _box(engine, "bob", Vector2(0, 100))
    _joint(
        engine, anchor, bob, JointType.SPRING, 100.0, stiffness=8000.0, damping=600.0
    )
    _run(engine, 4.0)
    # 400 * 980 / 8000 = 49 past the rest length.
    assert _distance(anchor, bob) == pytest.approx(149.0, abs=3.0)


def test_a_gear_turns_the_second_body_with_the_first(engine: Any) -> None:
    engine.initialize(Vector2(0, 0))
    a = _box(engine, "a", Vector2(0, 0))
    b = _box(engine, "b", Vector2(100, 0))
    _joint(engine, a, b, JointType.GEAR)
    a.apply_impulse(Vector2(0, 2000), Vector2(10, 0))
    _run(engine, 0.5)
    assert abs(a.rotation) > 5.0
    assert b.rotation == pytest.approx(a.rotation, abs=1.0)


def test_a_motor_at_rest_turns_them_together(engine: Any) -> None:
    engine.initialize(Vector2(0, 0))
    a = _box(engine, "a", Vector2(0, 0))
    b = _box(engine, "b", Vector2(100, 0))
    _joint(engine, a, b, JointType.MOTOR)
    a.apply_impulse(Vector2(0, 2000), Vector2(10, 0))
    _run(engine, 0.5)
    assert abs(b.rotation) > 1.0
    assert b.rotation == pytest.approx(a.rotation, abs=2.0)


@pytest.mark.parametrize("collide", [False, True])
def test_jointed_bodies_collide_only_when_asked(engine: Any, collide: bool) -> None:
    engine.initialize(Vector2(0, 0))
    a = _box(engine, "a", Vector2(0, 0), BodyType.STATIC)
    b = _box(engine, "b", Vector2(5, 0))
    _joint(engine, a, b, JointType.DISTANCE, 0.0, 200.0, collide=collide)
    _run(engine, 0.5)
    pushed_apart = _distance(a, b) > 15.0
    assert pushed_apart is collide


def test_a_destroyed_joint_lets_go(engine: Any) -> None:
    anchor = _box(engine, "anchor", Vector2(0, 0), BodyType.STATIC)
    bob = _box(engine, "bob", Vector2(0, 50))
    joint = _joint(engine, anchor, bob, JointType.PIN)
    _run(engine, 0.5)
    engine.destroy_joint(joint)
    _run(engine, 1.0)
    assert bob.position.y > 200


def test_rapier_refuses_a_force_limit_it_cannot_honour() -> None:
    engine = RapierEngine()
    engine.initialize(Vector2(0, 0))
    a = _box(engine, "a", Vector2(0, 0))
    b = _box(engine, "b", Vector2(50, 0))
    with pytest.raises(NotImplementedError, match="MOTOR"):
        _joint(engine, a, b, JointType.PIN, max_force=100.0)
    _joint(engine, a, b, JointType.MOTOR, max_force=100.0)
