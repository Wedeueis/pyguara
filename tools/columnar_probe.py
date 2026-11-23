"""Price the columnar world against the object ECS.

    uv run python tools/columnar_probe.py
    uv run python tools/columnar_probe.py --entities 100000

Prints the numbers `docs/adr/0008-the-columnar-world-spike.md` is built
on: what one attribute access costs through a view, what a movement
integration costs each way, what spawning costs, and what a frame of
sprites costs to build from objects and from columns. Figures are the
minimum of several rounds, as everywhere in `docs/guides/performance.md`.
The sprite frame needs a graphics adapter and is skipped without one.
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
        """Run `BaseComponent`'s setup, which the generated `__init__` does not."""
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


def frame_of_sprites(count: int, textures: int) -> None:
    """Build one frame of `count` sprites into a `NativeGpu`, both ways.

    Each sprite has a transform, a turn, a scale and a tint, so every
    column is exercised. The object side is `Scene.render`'s loop,
    `RenderSystem.submit`, the sort, the `Batcher` and
    `WgpuRenderer.render_batch`; the columnar side is one
    `ColumnarSpriteRenderer.draw`. Rendering the frame costs the same either
    way and is left out of both.
    """
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from pyguara.columnar.render import (
        ColumnarSprite,
        ColumnarSpriteRenderer,
        ColumnarTransform,
    )
    from pyguara.common.types import Color
    from pyguara.graphics.backends import wgpu
    from pyguara.graphics.backends.pygame.types import PygameTexture
    from pyguara.graphics.components.camera import Camera2D
    from pyguara.graphics.components.sprite import Sprite
    from pyguara.graphics.pipeline.render_system import RenderSystem
    from pyguara.graphics.pipeline.viewport import Viewport

    pygame.init()
    try:
        frame = wgpu.GpuFrame(1280, 720)
    except RuntimeError as error:
        print(f"sprite frame skipped: no graphics adapter ({error})")
        return
    images = []
    for index in range(textures):
        surface = pygame.Surface((32, 32), pygame.SRCALPHA)
        surface.fill((255, 255, 255, 255))
        images.append(PygameTexture(f"probe{index}", surface))
    ids = [frame.image(image)[0] for image in images]  # type: ignore[index]
    camera = Camera2D(1280, 720)
    viewport = Viewport.create_fullscreen(1280, 720)
    placements = [
        (Vector2((i * 37) % 1280, (i * 53) % 720), (i * 7) % 360, i % textures)
        for i in range(count)
    ]

    manager = EntityManager()
    for position, turn, texture in placements:
        entity = manager.create_entity()
        entity.add_component(Transform(position=position))
        entity.add_component(
            Sprite(
                texture=images[texture],
                rotation=float(turn),
                scale=Vector2(1.5, 1.5),
                color=Color(200, 180, 255, 230),
            )
        )
    renderer = wgpu.WgpuRenderer(frame)
    system = RenderSystem(renderer)

    world = ColumnarWorld()
    columns = ColumnarSpriteRenderer(world)
    for position, turn, texture in placements:
        spawned = world.spawn()
        world.add(spawned, ColumnarTransform(position, position))
        world.add(
            spawned,
            ColumnarSprite(
                texture=ids[texture],
                rotation=float(turn),
                scale=Vector2(1.5, 1.5),
                red=200,
                green=180,
                blue=255,
                alpha=230,
            ),
        )

    def objects() -> None:
        for entity in manager.get_entities_with(Sprite):
            sprite = entity.get_component(Sprite)
            if sprite.visible:
                transform = entity.get_component(Transform)
                system.submit(sprite, position=transform.position + sprite.position)
        system._queue.sort()
        for batch in system._batcher.create_batches(
            system._queue.commands, camera, viewport
        ):
            renderer.render_batch(batch)
        system._queue.clear()

    def from_columns() -> None:
        columns.draw(frame.gpu, camera, viewport)

    def timed(build: Callable[[], None]) -> float:
        fastest = float("inf")
        for _ in range(7):
            start = time.perf_counter()
            build()
            fastest = min(fastest, time.perf_counter() - start)
            frame.gpu.end_frame()
            frame.after_frame()
        return fastest

    reference, columnar = timed(objects), timed(from_columns)
    print(
        f"frame of {count} sprites, {textures} texture(s): objects "
        f"{reference * 1e3:.2f} ms, columns {columnar * 1e3:.3f} ms "
        f"({reference / columnar:.0f}x)"
    )


def main() -> None:
    """Run every measurement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entities", type=int, default=10_000)
    parser.add_argument("--sprites", type=int, default=20_000)
    arguments = parser.parse_args()
    count = arguments.entities
    access(count)
    integrate(count)
    spawn(count)
    for textures in (1, 10):
        frame_of_sprites(arguments.sprites, textures)


if __name__ == "__main__":
    main()
