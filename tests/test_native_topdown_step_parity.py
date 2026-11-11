"""Does `TopDownSystem`'s batched step move every body exactly as `step_body` does?

`TopDownSystem` hands every body it moves to the engine's `step_bodies` in
one call, and steps only what that declines through `step_body`. This suite
runs the same walk in two worlds -- one whose engine has no mirror, so
every body goes through `step_body` and Chipmunk, and one that batches --
and compares every position and remainder after every tick.

The comparison is on `repr`, not `==`. `==` would let `-0.0` pass for
`0.0` and an `int` pass for a `float`, and both are differences: the first
is the reason the centre is handed over already offset, and the second
encodes differently on the wire.

`TestTheBatchIsActuallyTaken` is what keeps the rest honest. A batch that
declined every body would agree with the reference perfectly.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.kits.topdown_movement.body import TopDownBody
from pyguara.kits.topdown_movement.system import TopDownSystem
from pyguara.native import native_module
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import Collider
from pyguara.physics.types import BodyType, CollisionLayer, PhysicsMaterial, ShapeType

pytestmark = pytest.mark.skipif(
    native_module() is None or not hasattr(native_module(), "NativeSolids"),
    reason="native extension not built; `make native`",
)

Box = tuple[float, float, float, float]

DT = 1.0 / 60.0


def _walls(stream: RandomStream, kind: str) -> list[Box]:
    if kind == "empty":
        return []
    if kind == "tiles":
        return [
            (column * 32.0, row * 32.0, 32.0, 32.0)
            for row in range(-6, 7)
            for column in range(-6, 7)
            if stream.random() < 0.3
        ]
    # Edges a skin's width off the pixel grid, where a probe touches exactly
    # and the mirror has to decline.
    return [
        (column * 40 + 0.05, row * 40 - 0.05, 39.9, 39.9)
        for row in range(-4, 5)
        for column in range(-4, 5)
        if stream.random() < 0.3
    ]


def _engine(walls: list[Box], accelerate: bool) -> PymunkEngine:
    engine = PymunkEngine(accelerate=accelerate)
    engine.initialize(Vector2(0, 0))
    for number, (x, y, width, height) in enumerate(walls):
        body = engine.create_body(f"wall{number}", BodyType.STATIC, Vector2(x, y))
        engine.add_shape(
            body,
            ShapeType.BOX,
            [width, height],
            Vector2(0, 0),
            PhysicsMaterial(),
            CollisionLayer(),
            False,
        )
    return engine


def _spawn(manager: EntityManager, stream: RandomStream, count: int) -> None:
    """Bodies of every shape the batch has to get right."""
    for number in range(count):
        entity = manager.create_entity(f"body{number:03d}")
        x = stream.uniform(-200, 200)
        y = stream.uniform(-200, 200)
        entity.add_component(Transform(position=Vector2(x, y)))
        entity.add_component(TopDownBody())
        shape = number % 4
        if shape == 0:
            continue  # no collider: the default box, and no offset added
        offset = (
            Vector2(0, 0)  # the dataclass default: integer zeros
            if shape == 1
            else Vector2(stream.uniform(-6, 6), stream.uniform(-6, 6))
        )
        entity.add_component(
            Collider(
                dimensions=[
                    stream.choice([12.0, 20.0, 25.0]),
                    stream.choice([12.0, 20.0, 0.08]),
                ],
                offset=offset,
            )
        )


def _state(manager: EntityManager) -> list[str]:
    out = []
    for entity in sorted(manager.get_entities_with(TopDownBody), key=lambda e: e.id):
        body = entity.get_component(TopDownBody)
        position = entity.get_component(Transform).position
        out.append(
            repr(
                (
                    entity.id,
                    position[0],
                    position[1],
                    type(position[0]),
                    type(position[1]),
                    body._remainder[0],
                    body._remainder[1],
                    type(body._remainder[0]),
                    type(body._remainder[1]),
                )
            )
        )
    return out


def _world(walls: list[Box], accelerate: bool, seed: int, count: int) -> Any:
    manager = EntityManager()
    _spawn(manager, RandomStream(seed), count)
    system = TopDownSystem(manager, _engine(walls, accelerate), SpatialHash[str]())
    return manager, system


def _steer(managers: list[EntityManager], stream: RandomStream) -> None:
    """Give the same body in each world the same new velocity."""
    ids = sorted(e.id for e in managers[0].get_entities_with(TopDownBody))
    for entity_id in ids:
        if stream.random() >= 0.15:
            continue
        heading = stream.uniform(0, math.tau)
        speed = stream.choice([0.0, 18.0, 150.0, 420.0, 2400.0])
        velocity = Vector2(math.cos(heading) * speed, math.sin(heading) * speed)
        for manager in managers:
            entity = manager.get_entity(entity_id)
            assert entity is not None
            entity.get_component(TopDownBody).velocity = velocity


@pytest.mark.parametrize("kind", ["empty", "tiles", "edges-on-the-skin"])
@pytest.mark.parametrize("seed", range(3))
def test_a_walk_ends_in_the_same_place(kind: str, seed: int) -> None:
    walls = _walls(RandomStream(seed), kind)
    slow, slow_system = _world(walls, accelerate=False, seed=seed, count=40)
    fast, fast_system = _world(walls, accelerate=True, seed=seed, count=40)
    stream = RandomStream(100 + seed)

    for tick in range(240):
        _steer([slow, fast], stream)
        slow_system.update(DT)
        fast_system.update(DT)
        assert _state(fast) == _state(slow), f"tick {tick}"


class TestTheBatchIsActuallyTaken:
    def _counted(self, system: TopDownSystem) -> list[int]:
        seen = [0, 0]
        original = system._step_bodies
        assert original is not None

        def counting(rows: Any, delta_time: float, skin: float) -> Any:
            steps = original(rows, delta_time, skin)
            seen[0] += len(rows)
            seen[1] += sum(step is None for step in steps)
            return steps

        system._step_bodies = counting
        return seen

    def test_open_ground_is_stepped_without_python(self) -> None:
        manager, system = _world([(0.0, 600.0, 50.0, 50.0)], True, seed=1, count=30)
        seen = self._counted(system)
        for entity in manager.get_entities_with(TopDownBody):
            entity.get_component(TopDownBody).velocity = Vector2(90.0, -40.0)

        for _ in range(30):
            system.update(DT)

        assert seen == [900, 0]

    def test_a_touch_is_declined_and_still_ends_in_the_same_place(self) -> None:
        # Pressed against a wall whose face lands exactly on a skinned probe
        # edge: a 60-wide body probes 29.95 either side of a whole-pixel
        # centre, and this wall's left face is at 69.95. At x = 40 the probe
        # touches, the batch must decline, and the body must still stop
        # where `step_body` stops it.
        walls = [(79.95, 0.0, 20.0, 400.0)]
        results = []
        seen: list[int] = []
        for accelerate in (False, True):
            manager = EntityManager()
            entity = manager.create_entity("pressed")
            entity.add_component(Transform(position=Vector2(0.0, 0.0)))
            entity.add_component(TopDownBody(velocity=Vector2(600.0, 0.0)))
            entity.add_component(Collider(dimensions=[60.0, 20.0]))
            system = TopDownSystem(
                manager, _engine(walls, accelerate), SpatialHash[str]()
            )
            if accelerate:
                seen = self._counted(system)
            for _ in range(20):
                system.update(DT)
            results.append(_state(manager))

        assert results[1] == results[0]
        assert seen[1] > 0


class TestWhatTheBatchLeavesAlone:
    def test_an_integer_position_stays_an_integer(self) -> None:
        results = []
        for accelerate in (False, True):
            manager = EntityManager()
            entity = manager.create_entity("whole")
            entity.add_component(Transform(position=Vector2(5, 7)))
            entity.add_component(TopDownBody(velocity=Vector2(60, 0)))
            entity.add_component(Collider(dimensions=[10.0, 10.0]))
            system = TopDownSystem(
                manager,
                _engine([(100.0, 0.0, 10.0, 10.0)], accelerate),
                SpatialHash[str](),
            )
            system.update(1.0)
            results.append(_state(manager))

        assert results[1] == results[0]
        assert "<class 'int'>" in results[0][0]

    def test_negative_zero_survives_a_body_with_no_collider(self) -> None:
        # Without a collider `step_body` adds no offset, and -0.0 + 0.0 is
        # +0.0: the reason the centre is handed to the engine pre-offset.
        manager = EntityManager()
        entity = manager.create_entity("signed")
        entity.add_component(Transform(position=Vector2(-0.0, -0.0)))
        entity.add_component(TopDownBody())
        system = TopDownSystem(
            manager, _engine([(100.0, 0.0, 10.0, 10.0)], True), SpatialHash[str]()
        )

        system.update(DT)

        assert repr(tuple(entity.get_component(Transform).position)) == "(-0.0, -0.0)"

    def test_a_body_stepped_elsewhere_is_not_moved(self) -> None:
        manager = EntityManager()
        entity = manager.create_entity("predicted")
        entity.add_component(Transform(position=Vector2(0.0, 0.0)))
        entity.add_component(
            TopDownBody(velocity=Vector2(600.0, 0.0), moved_elsewhere=True)
        )
        system = TopDownSystem(manager, _engine([], True), SpatialHash[str]())

        system.update(DT)

        assert entity.get_component(Transform).position == Vector2(0.0, 0.0)

    def test_a_world_with_a_moving_solid_is_stepped_the_ordinary_way(self) -> None:
        engine = _engine([(60.0, 0.0, 20.0, 200.0)], True)
        crate = engine.create_body("crate", BodyType.DYNAMIC, Vector2(500.0, 500.0))
        engine.add_shape(
            crate,
            ShapeType.BOX,
            [10.0, 10.0],
            Vector2(0, 0),
            PhysicsMaterial(),
            CollisionLayer(),
            False,
        )
        assert engine.step_bodies([], DT, 0.05) is None

        manager = EntityManager()
        entity = manager.create_entity("walker")
        entity.add_component(Transform(position=Vector2(0.0, 0.0)))
        entity.add_component(TopDownBody(velocity=Vector2(600.0, 0.0)))
        entity.add_component(Collider(dimensions=[20.0, 20.0]))
        system = TopDownSystem(manager, engine, SpatialHash[str]())

        for _ in range(20):
            system.update(DT)

        # Stopped by the wall: its left face is at 50, the body is 10 wide.
        assert entity.get_component(Transform).position.x == 40.0
