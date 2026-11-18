"""`Sprite.flip_x` and `flip_y` mirror the image inside the same box.

Drawn through `RenderSystem` on the software renderer, the reference the
wgpu pixel tests hold the GPU path to.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara.common.types import Vector2
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.types import PygameTexture
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.render_system import RenderSystem

WIDTH, HEIGHT = 64, 48


def _texture() -> PygameTexture:
    """Eight by six, with no symmetry: one red corner, one green column."""
    surface = pygame.Surface((8, 6), pygame.SRCALPHA)
    surface.fill((0, 0, 255, 255))
    surface.fill((0, 255, 0, 255), (0, 0, 2, 6))
    surface.fill((255, 0, 0, 255), (6, 0, 2, 2))
    return PygameTexture("asymmetric", surface)


def _draw(sprite: Sprite) -> pygame.Surface:
    pygame.init()
    screen = pygame.Surface((WIDTH, HEIGHT))
    screen.fill((0, 0, 0))
    system = RenderSystem(PygameBackend(screen))
    camera = Camera2D(WIDTH, HEIGHT)
    camera.position = Vector2(WIDTH / 2, HEIGHT / 2)
    system.submit(sprite)
    system.flush(camera)
    return screen


def _lit(screen: pygame.Surface) -> pygame.Rect:
    """The smallest rectangle holding every pixel that is not black."""
    xs, ys = [], []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if screen.get_at((x, y))[:3] != (0, 0, 0):
                xs.append(x)
                ys.append(y)
    return pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


@pytest.mark.parametrize(
    ("flip_x", "flip_y", "scale"),
    [
        (True, False, Vector2(1, 1)),
        (False, True, Vector2(1, 1)),
        (True, True, Vector2(1, 1)),
        (True, False, Vector2(2, 2)),
    ],
)
def test_a_flipped_sprite_is_the_mirror_of_the_unflipped_one(
    flip_x: bool, flip_y: bool, scale: Vector2
) -> None:
    texture = _texture()
    at = Vector2(20, 14)
    plain = _draw(Sprite(texture=texture, position=at, scale=scale))
    flipped = _draw(
        Sprite(texture=texture, position=at, scale=scale, flip_x=flip_x, flip_y=flip_y)
    )

    box = _lit(plain)
    assert _lit(flipped) == box
    mirrored = pygame.transform.flip(plain.subsurface(box), flip_x, flip_y)
    expected = pygame.image.tobytes(mirrored, "RGB")
    assert pygame.image.tobytes(flipped.subsurface(box), "RGB") == expected


def test_flipping_a_negative_scale_turns_it_back() -> None:
    texture = _texture()
    at = Vector2(20, 14)
    plain = _draw(Sprite(texture=texture, position=at))
    twice = _draw(
        Sprite(texture=texture, position=at, scale=Vector2(-1, 1), flip_x=True)
    )
    assert pygame.image.tobytes(twice, "RGB") == pygame.image.tobytes(plain, "RGB")
