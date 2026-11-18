"""Sprites drawn from columns against the same sprites drawn as objects.

Both paths build a frame into a fresh `GpuFrame` and the instance bytes
are compared before anything is rendered, so a difference in position,
size, turn, tint, texture coordinates or order fails here. The object
path is `Scene.render`'s loop, `RenderSystem.submit`, the queue's sort,
the `Batcher` and `WgpuRenderer.render_batch`. Skips when no graphics
adapter can be opened.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara.columnar import ColumnarWorld
from pyguara.columnar.render import (
    ColumnarSprite,
    ColumnarSpriteRenderer,
    ColumnarTransform,
)
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.backends.pygame.types import PygameTexture
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport

WIDTH, HEIGHT = 320, 240
ALPHA = 0.37


@pytest.fixture(scope="module")
def wgpu() -> Any:
    """The wgpu backend, or a skip if no adapter opens."""
    pygame.init()
    from pyguara.graphics.backends import wgpu as backend
    from tests.conftest import REQUIRE_GPU

    try:
        backend.GpuFrame(8, 8)
    except RuntimeError as error:
        if REQUIRE_GPU:
            pytest.fail(f"PYGUARA_REQUIRE_GPU is set and no adapter opened: {error}")
        pytest.skip(f"no graphics adapter for wgpu: {error}")
    return backend


@dataclass
class _Spec:
    """One sprite, in terms both paths can be built from."""

    texture: int
    transform: tuple[Vector2, Vector2, bool] | None
    offset: Vector2
    layer: int
    z_index: int
    y_sort: bool
    sort_offset: float
    sort_group: int
    rotation: float
    scale: Vector2
    color: tuple[int, int, int, int]
    visible: bool


def _specs(count: int, seed: int = 11) -> list[_Spec]:
    rng = RandomStream(seed)
    specs = []
    for index in range(count):
        position = Vector2(rng.uniform(-400, 400), rng.uniform(-300, 300))
        previous = position - Vector2(rng.uniform(-5, 5), rng.uniform(-5, 5))
        specs.append(
            _Spec(
                texture=index % 3,
                transform=None
                if index % 7 == 0
                else (position, previous, index % 2 == 0),
                offset=Vector2(rng.uniform(-8, 8), rng.uniform(-8, 8)),
                layer=rng.choice([0, 10, 10, 20]),
                z_index=rng.randint(-2, 2),
                y_sort=index % 5 == 0,
                sort_offset=rng.choice([0.0, 4.5]),
                sort_group=rng.choice([0, 0, 1]),
                rotation=rng.choice([0.0, 0.0, 30.0, -112.5, 90.0]),
                scale=rng.choice(
                    [Vector2(1, 1), Vector2(1, 1), Vector2(1.5, 0.75), Vector2(-1, 1)]
                ),
                color=rng.choice([(255, 255, 255, 255), (200, 40, 90, 128)]),
                visible=index % 11 != 0,
            )
        )
    return specs


def _textures(wgpu: Any, frame: Any) -> tuple[list[PygameTexture], list[int]]:
    """Three images of different sizes, uploaded in the same order to `frame`."""
    textures = []
    for width, height in ((16, 16), (24, 10), (9, 31)):
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        surface.fill((255, 255, 255, 255))
        textures.append(PygameTexture(f"t{width}x{height}", surface))
    ids = []
    for texture in textures:
        image = frame.image(texture)
        assert image is not None
        ids.append(image[0])
    return textures, ids


def _camera() -> tuple[Camera2D, Viewport]:
    camera = Camera2D(WIDTH, HEIGHT)
    camera.zoom = 1.25
    camera.position = Vector2(13.5, -7.25)
    return camera, Viewport.create_fullscreen(WIDTH, HEIGHT)


def _objects(wgpu: Any, specs: list[_Spec]) -> bytes:
    """Draw through `Scene.render`'s loop and the batched object path."""
    frame = wgpu.GpuFrame(WIDTH, HEIGHT)
    textures, _ = _textures(wgpu, frame)
    renderer = wgpu.WgpuRenderer(frame)
    manager = EntityManager()
    for spec in specs:
        entity = manager.create_entity()
        if spec.transform is not None:
            position, previous, interpolate = spec.transform
            transform = Transform(position=position, interpolate=interpolate)
            transform.previous_position = previous
            entity.add_component(transform)
        entity.add_component(
            Sprite(
                texture=textures[spec.texture],
                layer=spec.layer,
                z_index=spec.z_index,
                visible=spec.visible,
                y_sort=spec.y_sort,
                sort_offset=spec.sort_offset,
                sort_group=spec.sort_group,
                position=spec.offset,
                rotation=spec.rotation,
                scale=spec.scale,
                color=Color(*spec.color),
            )
        )

    system = RenderSystem(renderer)
    # `Scene.render`, line for line, up to the flush.
    for entity in manager.get_entities_with(Sprite):
        sprite = entity.get_component(Sprite)
        if sprite.visible:
            if entity.has_component(Transform):
                transform = entity.get_component(Transform)
                if transform.interpolate:
                    base = transform.previous_position.lerp(transform.position, ALPHA)
                else:
                    base = transform.position
                world_position = base + sprite.position
            else:
                world_position = sprite.position
            system.submit(sprite, position=world_position)
    camera, viewport = _camera()
    system._queue.sort()
    for batch in system._batcher.create_batches(
        system._queue.commands, camera, viewport
    ):
        renderer.render_batch(batch)
    return bytes(frame.gpu.pending_instance_bytes())


def _columns(wgpu: Any, specs: list[_Spec], *, despawn_every: int = 0) -> bytes:
    """Draw the same sprites from a columnar world."""
    frame = wgpu.GpuFrame(WIDTH, HEIGHT)
    _, ids = _textures(wgpu, frame)
    world = ColumnarWorld()
    renderer = ColumnarSpriteRenderer(world)
    for index, spec in enumerate(specs):
        if despawn_every and index % despawn_every == 0:
            # A doomed entity before each real one: its rows are
            # tombstoned, and not flushed, when the frame is drawn.
            doomed = world.spawn()
            world.add(doomed, ColumnarSprite(texture=ids[0]))
            world.add(doomed, ColumnarTransform())
            world.despawn(doomed)
        entity = world.spawn()
        if spec.transform is not None:
            position, previous, interpolate = spec.transform
            world.add(entity, ColumnarTransform(position, previous, interpolate))
        red, green, blue, alpha = spec.color
        world.add(
            entity,
            ColumnarSprite(
                texture=ids[spec.texture],
                layer=spec.layer,
                z_index=spec.z_index,
                visible=spec.visible,
                y_sort=spec.y_sort,
                sort_offset=spec.sort_offset,
                sort_group=spec.sort_group,
                position=spec.offset,
                rotation=spec.rotation,
                scale=spec.scale,
                red=red,
                green=green,
                blue=blue,
                alpha=alpha,
            ),
        )
    camera, viewport = _camera()
    drawn = renderer.draw(frame.gpu, camera, viewport, ALPHA)
    assert drawn == sum(1 for spec in specs if spec.visible)
    return bytes(frame.gpu.pending_instance_bytes())


def test_the_columns_draw_the_instances_the_objects_draw(wgpu: Any) -> None:
    specs = _specs(600)
    expected = _objects(wgpu, specs)
    assert len(expected) > 0
    assert _columns(wgpu, specs) == expected


def test_a_despawned_entity_is_not_drawn(wgpu: Any) -> None:
    specs = _specs(200, seed=3)
    assert _columns(wgpu, specs, despawn_every=4) == _objects(wgpu, specs)


def test_an_unknown_texture_pushes_nothing(wgpu: Any) -> None:
    frame = wgpu.GpuFrame(WIDTH, HEIGHT)
    _, ids = _textures(wgpu, frame)
    world = ColumnarWorld()
    renderer = ColumnarSpriteRenderer(world)
    world.add(world.spawn(), ColumnarSprite(texture=ids[0]))
    world.add(world.spawn(), ColumnarSprite(texture=max(ids) + 100))
    camera, viewport = _camera()
    with pytest.raises(KeyError):
        renderer.draw(frame.gpu, camera, viewport)
    assert frame.gpu.pending == 0


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"red": 256}, "outside 0-255"),
        ({"alpha": -1}, "outside 0-255"),
        ({"texture": -1}, "not a texture id"),
        ({"y_sort": True, "sort_offset": math.nan}, "NaN depth"),
    ],
)
def test_an_unusable_value_raises_and_pushes_nothing(
    wgpu: Any, change: dict[str, Any], error: str
) -> None:
    frame = wgpu.GpuFrame(WIDTH, HEIGHT)
    _, ids = _textures(wgpu, frame)
    world = ColumnarWorld()
    renderer = ColumnarSpriteRenderer(world)
    world.add(world.spawn(), ColumnarSprite(texture=ids[0]))
    world.add(world.spawn(), ColumnarSprite(**{"texture": ids[0], **change}))
    camera, viewport = _camera()
    with pytest.raises(ValueError, match=error):
        renderer.draw(frame.gpu, camera, viewport)
    assert frame.gpu.pending == 0
