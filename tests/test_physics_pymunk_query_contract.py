"""Two places the pymunk backend broke `IPhysicsEngine`'s promises.

A ray passed through a sensor in `raycast_all` but stopped at it in
`raycast`, though the protocol says both skip sensors. And a body moved
by setting its position stayed indexed where it had been until the next
step -- for a static body, until forever -- so a query found it at its
old place and nothing at its new one.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Vector2
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.types import BodyType, CollisionLayer, PhysicsMaterial, ShapeType


@pytest.fixture(params=[False, None], ids=["chipmunk", "with-mirror"])
def engine(request: pytest.FixtureRequest) -> PymunkEngine:
    built = PymunkEngine(accelerate=request.param)
    built.initialize(Vector2(0, 0))
    return built


def _box(
    engine: PymunkEngine, entity: str, at: Vector2, kind: BodyType, sensor: bool = False
):
    body = engine.create_body(entity, kind, at)
    engine.add_shape(
        body,
        ShapeType.BOX,
        [20, 20],
        Vector2(0, 0),
        PhysicsMaterial(),
        CollisionLayer(),
        sensor,
    )
    return body


class TestARaySkipsSensors:
    def test_raycast_passes_through_a_sensor(self, engine: PymunkEngine) -> None:
        _box(engine, "trigger", Vector2(100, 100), BodyType.STATIC, sensor=True)
        assert engine.raycast(Vector2(0, 100), Vector2(300, 100)) is None

    def test_it_stops_at_the_solid_behind_one(self, engine: PymunkEngine) -> None:
        _box(engine, "trigger", Vector2(100, 100), BodyType.STATIC, sensor=True)
        _box(engine, "wall", Vector2(200, 100), BodyType.STATIC)
        hit = engine.raycast(Vector2(0, 100), Vector2(300, 100))
        assert hit is not None and hit.entity_id == "wall"

    def test_raycast_and_raycast_all_agree(self, engine: PymunkEngine) -> None:
        _box(engine, "trigger", Vector2(100, 100), BodyType.STATIC, sensor=True)
        _box(engine, "wall", Vector2(200, 100), BodyType.STATIC)
        first = engine.raycast(Vector2(0, 100), Vector2(300, 100))
        every = engine.raycast_all(Vector2(0, 100), Vector2(300, 100))
        assert first is not None and every and first.entity_id == every[0].entity_id

    def test_ignoring_the_caster_still_works(self, engine: PymunkEngine) -> None:
        _box(engine, "me", Vector2(100, 100), BodyType.STATIC)
        _box(engine, "wall", Vector2(200, 100), BodyType.STATIC)
        hit = engine.raycast(
            Vector2(100, 100), Vector2(300, 100), ignore_entity_id="me"
        )
        assert hit is not None and hit.entity_id == "wall"


@pytest.mark.parametrize(
    "kind", [BodyType.STATIC, BodyType.KINEMATIC, BodyType.DYNAMIC]
)
def test_a_moved_body_is_found_where_it_now_is(
    engine: PymunkEngine, kind: BodyType
) -> None:
    body = _box(engine, "moved", Vector2(50, 50), kind)
    assert engine.overlap_box(Vector2(50, 50), Vector2(1, 1)) == "moved"

    body.position = Vector2(500, 500)

    assert engine.overlap_box(Vector2(50, 50), Vector2(1, 1)) is None
    assert engine.overlap_box(Vector2(500, 500), Vector2(1, 1)) == "moved"
    assert engine.point_query(Vector2(500, 500)) == ["moved"]


def test_a_turned_body_is_found_where_it_now_reaches(engine: PymunkEngine) -> None:
    body = engine.create_body("bar", BodyType.STATIC, Vector2(0, 0))
    engine.add_shape(
        body,
        ShapeType.BOX,
        [100, 4],
        Vector2(0, 0),
        PhysicsMaterial(),
        CollisionLayer(),
        False,
    )
    body.rotation = 90.0
    assert engine.overlap_box(Vector2(0, 40), Vector2(1, 1)) == "bar"
    assert engine.overlap_box(Vector2(40, 0), Vector2(1, 1)) is None
