"""Price the columnar world against the object ECS.

    uv run python tools/columnar_probe.py
    uv run python tools/columnar_probe.py --entities 100000

Prints the three numbers `docs/adr/0008-the-columnar-world-spike.md` is
built on: what one attribute access costs through a view, what a movement
integration costs each way, and what spawning costs. Figures are the
minimum of several rounds, as everywhere in `docs/guides/performance.md`.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pyguara.columnar import ColumnarWorld
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.manager import EntityManager

DT = 1 / 60


@dataclass(slots=True)
class Drift(BaseComponent):
    """An object-ECS velocity, for the reference side."""

    value: Vector2

    def __post_init__(self) -> None:
        BaseComponent.__init__(self)


@dataclass
class Position:
    """A columnar position."""

    value: Vector2


@dataclass
class Velocity:
    """A columnar velocity."""

    value: Vector2


def best(fn: Callable[[], Any], rounds: int = 7) -> float:
    """Return the fastest of `rounds` runs of `fn`, in seconds."""
    fastest = float("inf")
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        fastest = min(fastest, time.perf_counter() - start)
    return fastest


def build_objects(count: int) -> EntityManager:
    """An object ECS holding `count` moving entities."""
    manager = EntityManager()
    for number in range(count):
        entity = manager.create_entity()
        entity.add_component(Transform(position=Vector2(float(number), 0.0)))
        entity.add_component(Drift(Vector2(1.0, 2.0)))
    return manager


def build_columns(count: int) -> tuple[ColumnarWorld, list[int]]:
    """A columnar world holding `count` moving entities."""
    world = ColumnarWorld()
    entities = world.spawn_many(count)
    for number, entity in enumerate(entities):
        world.add(entity, Position(Vector2(float(number), 0.0)))
        world.add(entity, Velocity(Vector2(1.0, 2.0)))
    return world, entities


def access(count: int) -> None:
    """One attribute read and one write, per entity."""
    manager = build_objects(count)
    transforms = [e.get_component(Transform) for e in manager.get_all_entities()]
    drifts = [e.get_component(Drift) for e in manager.get_all_entities()]
    world, entities = build_columns(count)
    views = [world.view(entity, Position) for entity in entities]
    target = Vector2(3.0, 4.0)

    def read_dataclass() -> None:
        for drift in drifts:
            _ = drift.value

    def read_transform() -> None:
        for transform in transforms:
            _ = transform.position

    def read_view() -> None:
        for view in views:
            _ = view.value

    def read_fresh_view() -> None:
        for entity in entities:
            _ = world.view(entity, Position).value

    def write_dataclass() -> None:
        for drift in drifts:
            drift.value = target

    def write_transform() -> None:
        for transform in transforms:
            transform.position = target

    def write_view() -> None:
        for view in views:
            view.value = target

    def loop_only() -> None:
        for _ in views:
            pass

    floor = best(loop_only)
    print(f"\nPer-entity access, {count} entities -- ns per access")
    rows = [
        ("read  dataclass field (slots)", read_dataclass),
        ("read  Transform.position", read_transform),
        ("read  columnar view, held", read_view),
        ("read  columnar view, made per access", read_fresh_view),
        ("write dataclass field (slots)", write_dataclass),
        ("write Transform.position", write_transform),
        ("write columnar view, held", write_view),
    ]
    for label, fn in rows:
        print(f"  {label:<40}{(best(fn) - floor) / count * 1e9:8.1f}")


def integrate(count: int) -> None:
    """`position += velocity * dt` for every entity, four ways."""
    manager = build_objects(count)
    world, _ = build_columns(count)

    def objects() -> None:
        for transform, drift in manager.get_components(Transform, Drift):
            position, velocity = transform.position, drift.value
            transform.position = Vector2(
                position.x + velocity.x * DT, position.y + velocity.y * DT
            )

    def numpy_views() -> None:
        position, velocity = world.arrays(Position), world.arrays(Velocity)
        position["value.x"] += velocity["value.x"] * DT
        position["value.y"] += velocity["value.y"] * DT

    def native() -> None:
        world.add_scaled(Position, "value.x", Velocity, "value.x", DT)
        world.add_scaled(Position, "value.y", Velocity, "value.y", DT)

    reference = best(objects)
    print(f"\nIntegrate {count} entities -- ms per tick")
    print(f"  {'object ECS, Python loop':<40}{reference * 1e3:8.3f}")
    for label, fn in (("columns, NumPy", numpy_views), ("columns, native", native)):
        taken = best(fn)
        print(f"  {label:<40}{taken * 1e3:8.3f}   {reference / taken:6.0f}x")


def spawn(count: int) -> None:
    """Create `count` entities with two components each."""
    reference = best(lambda: build_objects(count), rounds=3)
    taken = best(lambda: build_columns(count), rounds=3)
    print(f"\nSpawn {count} entities, two components each -- ms")
    print(f"  {'object ECS':<40}{reference * 1e3:8.2f}")
    print(f"  {'columnar world':<40}{taken * 1e3:8.2f}   {reference / taken:6.1f}x")


def main() -> None:
    """Run every measurement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entities", type=int, default=10_000)
    count = parser.parse_args().entities
    access(count)
    integrate(count)
    spawn(count)


if __name__ == "__main__":
    main()
