#!/usr/bin/env python
"""Measure Rapier at 1, 2 and 4 substeps: cost, stacking, thin walls, joints.

Every world is wired as bootstrap wires it -- `PhysicsSystem` over
`RapierEngine`, with a collision system that accepts every pair -- and
stepped at 60 Hz under 900 px/s^2 of gravity.

    uv run python tools/substep_probe.py
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.backends.rapier_impl import RapierEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    JointType,
    PhysicsMaterial,
    ShapeType,
)

DT = 1.0 / 60.0
GRAVITY = Vector2(0, 900)
SUBSTEPS = (1, 2, 4)


class World:
    """An ECS world with physics, at a given substep count."""

    def __init__(self, substeps: int, gravity: Vector2 = GRAVITY) -> None:
        """Wire the systems."""
        self.entities = EntityManager()
        dispatcher = EventDispatcher()
        engine = RapierEngine(substeps)
        engine.set_collision_system(CollisionSystem(dispatcher))
        self.system = PhysicsSystem(engine, self.entities, dispatcher, gravity=gravity)

    def add(self, at: Vector2, kind: BodyType, size: list[float]) -> Entity:
        """Add a box body."""
        entity = self.entities.create_entity()
        entity.add_component(Transform(position=at))
        entity.add_component(RigidBody(mass=1.0, body_type=kind))
        entity.add_component(Collider(shape_type=ShapeType.BOX, dimensions=size))
        return entity

    def run(self, ticks: int) -> None:
        """Advance the simulation."""
        for _ in range(ticks):
            self.system.update(DT)


def _tick_ms(world: World, ticks: int = 60) -> float:
    times = []
    for _ in range(ticks):
        start = time.perf_counter()
        world.run(1)
        times.append(time.perf_counter() - start)
    return statistics.median(times) * 1000


def cost(count: int, substeps: int) -> tuple[float, float]:
    """Milliseconds a tick for `count` 20 px boxes falling, then settled."""
    world = World(substeps)
    world.add(Vector2(1000, 1000), BodyType.STATIC, [2400.0, 40.0])
    for index in range(count):
        at = Vector2(220 + (index % 40) * 40, 900 - (index // 40) * 30)
        world.add(at, BodyType.DYNAMIC, [20.0, 20.0])
    world.run(1)
    falling = _tick_ms(world)
    world.run(300)
    return falling, _tick_ms(world)


def column(height: int, substeps: int) -> tuple[float, float]:
    """A column of 20 px boxes after 5 s: (how far the top sank, worst overlap)."""
    world = World(substeps)
    world.add(Vector2(400, 620), BodyType.STATIC, [800.0, 40.0])
    boxes = [
        world.add(Vector2(400, 590 - index * 20), BodyType.DYNAMIC, [20.0, 20.0])
        for index in range(height)
    ]
    world.run(300)
    ys = [box.get_component(Transform).position.y for box in boxes]
    gaps = [20 - (ys[index] - ys[index + 1]) for index in range(height - 1)]
    return ys[-1] - (590 - (height - 1) * 20), max([ys[0] - 590, *gaps])


def thin_wall(speed: float, thickness: float, substeps: int) -> float:
    """Fire an 8 px box at a wall at x=400; return its final x."""
    world = World(substeps, Vector2(0, 0))
    world.add(Vector2(400, 300), BodyType.STATIC, [thickness, 400.0])
    bullet = world.add(Vector2(100, 300), BodyType.DYNAMIC, [8.0, 8.0])
    world.run(1)
    handle: Any = bullet.get_component(RigidBody)._body_handle
    handle.velocity = Vector2(speed, 0)
    world.run(120)
    return float(bullet.get_component(Transform).position.x)


def chain_stretch(end_weight: float, substeps: int) -> float:
    """Hang 20 pinned 10 px links for 5 s; return the stretch as a fraction."""
    engine: Any = RapierEngine(substeps)
    engine.initialize(GRAVITY)
    origin = Vector2(0, 0)
    previous = engine.create_body("anchor", BodyType.STATIC, origin)
    pairs = []
    for index in range(1, 21):
        density = end_weight if index == 20 else 1.0
        link = engine.create_body(
            f"link{index}", BodyType.DYNAMIC, Vector2(index * 10, 0)
        )
        material = PhysicsMaterial(density=density)
        engine.add_shape(
            link, ShapeType.CIRCLE, [3.0], origin, material, CollisionLayer(), False
        )
        engine.create_joint(
            previous, link, JointType.PIN, origin, origin, 0, 0, 0, 0, 0, False
        )
        pairs.append((previous, link))
        previous = link
    for _ in range(300):
        engine.update(DT)
    length = sum((a.position - b.position).length for a, b in pairs)
    engine.cleanup()
    return float(length / 200.0 - 1.0)


def _row(label: str, cells: list[str]) -> None:
    print(f"  {label:<24}" + "".join(f"{cell:>22}" for cell in cells))


def main() -> None:
    """Print each measurement at each substep count."""
    print("ms a tick, falling / settled")
    for count in (200, 800):
        cells = [
            f"{s}: {f:.2f} / {r:.2f}" for s in SUBSTEPS for f, r in [cost(count, s)]
        ]
        _row(f"{count} boxes", cells)
    print("column after 5 s: top sank px / worst overlap px")
    for height in (10, 20):
        cells = [
            f"{s}: {t:+.2f} / {o:.2f}" for s in SUBSTEPS for t, o in [column(height, s)]
        ]
        _row(f"{height} boxes", cells)
    print("8 px box at a wall: final x (over 400 went through)")
    for thickness in (10.0, 2.0):
        for speed in (2000.0, 60000.0):
            cells = [f"{s}: {thin_wall(speed, thickness, s):.0f}" for s in SUBSTEPS]
            _row(f"{thickness:.0f} px wall, {speed:.0f} px/s", cells)
    print("chain of 20 pinned links: stretch")
    for weight in (1.0, 50.0):
        cells = [f"{s}: {chain_stretch(weight, s) * 100:+.1f}%" for s in SUBSTEPS]
        _row(f"end link {weight:.0f}x", cells)


if __name__ == "__main__":
    main()
