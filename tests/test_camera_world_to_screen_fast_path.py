"""`Camera2D.world_to_screen`'s scalar path against the vector expression.

The method is `world * zoom + screen_offset(viewport)`. It now computes
that component by component for the common argument types; this holds the
two spellings together, to the bit, across zoom, shake and viewport.
"""

from __future__ import annotations

import pymunk

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2
from pyguara.graphics.components.camera import Camera2D


def _long_way(camera: Camera2D, world: Vector2, viewport: Rect | None) -> Vector2:
    vp = viewport if viewport is not None else camera._default_viewport
    return world * camera.zoom + camera.screen_offset(vp)


def test_the_scalar_path_is_the_vector_expression() -> None:
    stream = RandomStream(5)
    camera = Camera2D(800, 600)
    viewports = [None, Rect(0, 0, 800, 600), Rect(13, 7, 401, 299), Rect(-5, 40, 1, 1)]

    for _ in range(2000):
        camera.position = Vector2(stream.uniform(-5e4, 5e4), stream.uniform(-5e4, 5e4))
        camera.zoom = stream.choice([1.0, 2.0, 0.5, 1 / 3, stream.uniform(0.1, 4.0)])
        camera._shake_offset = Vector2(stream.uniform(-9, 9), stream.uniform(-9, 9))
        world = Vector2(stream.uniform(-5e4, 5e4), stream.uniform(-5e4, 5e4))
        viewport = stream.choice(viewports)

        result = camera.world_to_screen(world, viewport)

        assert type(result) is Vector2
        assert repr(result) == repr(_long_way(camera, world, viewport))


def test_whole_number_inputs_keep_their_types() -> None:
    camera = Camera2D(800, 600)
    camera.position = Vector2(10, 20)
    world = Vector2(3, 4)

    assert repr(camera.world_to_screen(world)) == repr(_long_way(camera, world, None))


def test_a_plain_pymunk_vector_takes_the_long_way_and_still_works() -> None:
    camera = Camera2D(800, 600)
    world = pymunk.Vec2d(3.5, 4.5)

    assert camera.world_to_screen(world) == camera.world_to_screen(Vector2(3.5, 4.5))  # type: ignore[arg-type]
