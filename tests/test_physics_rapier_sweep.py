"""Rapier's native sweep ends every move where the Python loop does.

`RapierEngine.sweep_box` runs `CharacterMover.move` natively and
`step_bodies` runs `TopDownSystem`'s step for many bodies. Each is
compared with the same engine stripped of both, so the mover's own loop
asks `overlap_box` one pixel at a time. Comparisons are on `repr`, so
`-0.0` does not pass for `0.0` nor an `int` for a `float`.
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
from pyguara.physics.backends.rapier_impl import RapierEngine
from pyguara.physics.character_mover import CharacterMover
from pyguara.physics.components import Collider
from pyguara.physics.types import BodyType, CollisionLayer, PhysicsMaterial, ShapeType

DT = 1.0 / 60.0


class _LoopOnly(RapierEngine):
    """The same engine, without the native sweep: callers use their loop."""

    sweep_box = None  # type: ignore[assignment]
    step_bodies = None  # type: ignore[assignment]


def _engine(native: bool, seed: int, kind: str) -> RapierEngine:
    engine: RapierEngine = RapierEngine() if native else _LoopOnly()
    engine.initialize(Vector2(0, 0))
    stream = RandomStream(seed)
    number = 0
    for row in range(-6, 7):
        for column in range(-6, 7):
            if stream.random() >= 0.25:
                continue
            # "edges" puts faces a skin's width off the pixel grid, where a
            # probe touches exactly.
            nudge = 0.05 if kind == "edges" else 0.0
            body = engine.create_body(
                f"wall{number}",
                BodyType.STATIC,
                Vector2(column * 32.0 + nudge, row * 32.0 - nudge),
            )
            engine.add_shape(
                body,
                ShapeType.BOX,
                [31.9 if kind == "edges" else 32.0] * 2,
                Vector2(0, 0),
                PhysicsMaterial(),
                CollisionLayer(),
                False,
            )
            number += 1
    # Moving solids too.
    for crate in range(4):
        body = engine.create_body(
            f"crate{crate}",
            BodyType.DYNAMIC,
            Vector2(stream.uniform(-150, 150), stream.uniform(-150, 150)),
        )
        engine.add_shape(
            body,
            ShapeType.CIRCLE if crate % 2 else ShapeType.BOX,
            [9.0] if crate % 2 else [14.0, 14.0],
            Vector2(0, 0),
            PhysicsMaterial(),
            CollisionLayer(),
            False,
        )
    return engine


@pytest.mark.parametrize("kind", ["grid", "edges"])
@pytest.mark.parametrize("seed", range(3))
def test_a_mover_ends_where_the_loop_ends(kind: str, seed: int) -> None:
    worlds = [_engine(native, seed, kind) for native in (False, True)]
    movers = [CharacterMover(world) for world in worlds]
    assert movers[0]._sweep is None and movers[1]._sweep is not None
    stream = RandomStream(1000 + seed)
    for _ in range(400):
        position = Vector2(
            float(round(stream.uniform(-200, 200))),
            float(round(stream.uniform(-200, 200))),
        )
        heading = stream.uniform(0, math.tau)
        speed = stream.choice([0.4, 3.5, 17.0, 64.0])
        delta = Vector2(math.cos(heading) * speed, math.sin(heading) * speed)
        remainder = Vector2(stream.uniform(-0.5, 0.5), stream.uniform(-0.5, 0.5))
        half = Vector2(stream.choice([4.0, 7.5, 12.0]), stream.choice([4.0, 9.0]))
        owner = "crate0" if stream.random() < 0.2 else None
        results = [
            repr(mover.move(position, half, delta, remainder, owner))
            for mover in movers
        ]
        assert results[1] == results[0]


@pytest.mark.parametrize("step", [0.5, 1.5, 2.5, -0.5, -1.5, -2.5])
def test_a_half_pixel_rounds_to_even(step: float) -> None:
    """Python's `round` sends a tie to the even neighbour, never away."""
    results = []
    for native in (False, True):
        mover = CharacterMover(_engine(native, 0, "grid"))
        results.append(
            repr(
                mover.move(
                    Vector2(400.0, 400.0),
                    Vector2(4.0, 4.0),
                    Vector2(step, step),
                    Vector2(0.0, 0.0),
                )
            )
        )
    assert results[1] == results[0]


def test_both_paths_hand_back_the_same_values() -> None:
    """Whole-number input comes back the same from both paths, as floats."""
    results = []
    for native in (False, True):
        mover = CharacterMover(_engine(native, 0, "grid"))
        moved = mover.move(Vector2(5, 7), Vector2(4, 4), Vector2(3, -2), Vector2(0, 0))
        results.append(
            (
                repr(moved),
                [type(value) for value in (*moved.position, *moved.remainder)],
            )
        )
    assert results[1] == results[0]
    assert results[0][1] == [float, float, float, float]


def test_the_blocker_is_named() -> None:
    engine = RapierEngine()
    engine.initialize(Vector2(0, 0))
    wall = engine.create_body("wall", BodyType.STATIC, Vector2(50, 0))
    engine.add_shape(
        wall,
        ShapeType.BOX,
        [10, 100],
        Vector2(0, 0),
        PhysicsMaterial(),
        CollisionLayer(),
        False,
    )
    swept = engine.sweep_box(
        Vector2(0.0, 0.0), Vector2(9.95, 9.95), Vector2(80.0, 0.0), Vector2(0.0, 0.0)
    )
    assert swept == (35.0, 0.0, 0.0, 0.0, "wall", None)


def _spawn(manager: EntityManager, stream: RandomStream, count: int) -> None:
    for number in range(count):
        entity = manager.create_entity(f"body{number:03d}")
        entity.add_component(
            Transform(
                position=Vector2(stream.uniform(-200, 200), stream.uniform(-200, 200))
            )
        )
        entity.add_component(TopDownBody())
        shape = number % 4
        if shape == 0:
            continue
        offset = (
            Vector2(0, 0)
            if shape == 1
            else Vector2(stream.uniform(-6, 6), stream.uniform(-6, 6))
        )
        entity.add_component(
            Collider(
                dimensions=[
                    stream.choice([12.0, 20.0, 25.0]),
                    stream.choice([12.0, 0.08]),
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


@pytest.mark.parametrize("kind", ["grid", "edges"])
@pytest.mark.parametrize("seed", range(3))
def test_a_top_down_walk_ends_in_the_same_place(kind: str, seed: int) -> None:
    managers = []
    systems = []
    for native in (False, True):
        manager = EntityManager()
        _spawn(manager, RandomStream(seed), 40)
        managers.append(manager)
        systems.append(
            TopDownSystem(manager, _engine(native, seed, kind), SpatialHash[str]())
        )
    assert systems[0]._step_bodies is None and systems[1]._step_bodies is not None
    stream = RandomStream(100 + seed)
    for tick in range(240):
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
        for system in systems:
            system.update(DT)
        assert _state(managers[1]) == _state(managers[0]), f"tick {tick}"


def test_the_batch_answers_for_every_body() -> None:
    """A batch that declined everything would agree perfectly; it doesn't."""
    manager = EntityManager()
    _spawn(manager, RandomStream(1), 30)
    system = TopDownSystem(manager, _engine(True, 1, "grid"), SpatialHash[str]())
    original: Any = system._step_bodies
    declined = [0, 0]

    def counting(rows: Any, delta_time: float, skin: float) -> Any:
        steps = original(rows, delta_time, skin)
        declined[0] += len(rows)
        declined[1] += sum(step is None for step in steps)
        return steps

    system._step_bodies = counting
    for entity in manager.get_entities_with(TopDownBody):
        entity.get_component(TopDownBody).velocity = Vector2(90.0, -40.0)
    for _ in range(30):
        system.update(DT)
    assert declined == [900, 0]
