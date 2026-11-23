"""Drawing a scene's sprites keeps what was already on the frame.

`RenderSystem.flush()` used to clear its viewport to black first. A scene
that cleared to its own colour lost it, `display.default_color` never
showed behind sprites, and a layer drawing sprites blacked out the scene
beneath it.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara.common.types import Color, Vector2
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.types import PygameTexture
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.render_system import RenderSystem

WIDTH, HEIGHT = 64, 48
SAND = (196, 168, 120)


@pytest.fixture(autouse=True)
def _pygame():
    pygame.init()
    yield
    pygame.quit()


def _square(color: tuple[int, int, int]) -> PygameTexture:
    surface = pygame.Surface((8, 8), pygame.SRCALPHA)
    surface.fill((*color, 255))
    return PygameTexture(f"square{color}", surface)


def _camera() -> Camera2D:
    camera = Camera2D(WIDTH, HEIGHT)
    camera.position = Vector2(WIDTH / 2, HEIGHT / 2)
    return camera


def test_the_colour_cleared_to_stays_behind_the_sprites() -> None:
    screen = pygame.Surface((WIDTH, HEIGHT))
    backend = PygameBackend(screen)
    system = RenderSystem(backend)
    backend.clear(Color(*SAND))

    system.submit(Sprite(texture=_square((255, 0, 0)), position=Vector2(32, 24)))
    system.flush(_camera())

    assert screen.get_at((2, 2))[:3] == SAND
    assert screen.get_at((32, 24))[:3] == (255, 0, 0)


def test_a_layer_drawing_sprites_keeps_the_scene_beneath_it() -> None:
    """Each scene has its own `RenderSystem`, flushed in turn onto one frame."""
    screen = pygame.Surface((WIDTH, HEIGHT))
    backend = PygameBackend(screen)
    game, hud = RenderSystem(backend), RenderSystem(backend)

    game.submit(Sprite(texture=_square((0, 255, 0)), position=Vector2(12, 12)))
    game.flush(_camera())
    hud.submit(Sprite(texture=_square((0, 0, 255)), position=Vector2(52, 36)))
    hud.flush(_camera())

    assert screen.get_at((12, 12))[:3] == (0, 255, 0)
    assert screen.get_at((52, 36))[:3] == (0, 0, 255)
