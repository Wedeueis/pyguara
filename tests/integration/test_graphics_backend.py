"""Integration tests for Pygame graphics backend."""

import os
import pytest
import pygame
from typing import Iterator
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.common.types import Vector2, Color, Rect
from pyguara.resources.types import Texture
from pyguara.graphics.types import RenderBatch

# Ensure headless execution
os.environ["SDL_VIDEODRIVER"] = "dummy"


@pytest.fixture(scope="module")
def pygame_init() -> Iterator[None]:
    """Initialize pygame for the module."""
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def renderer(pygame_init: None) -> PygameBackend:
    """Create a PygameBackend instance with a dummy surface."""
    surface = pygame.Surface((800, 600))
    return PygameBackend(surface)


def test_backend_initialization(renderer: PygameBackend) -> None:
    """Backend should initialize and report correct dimensions."""
    assert renderer.width == 800
    assert renderer.height == 600


def test_draw_primitives(renderer: PygameBackend) -> None:
    """Backend should draw primitives without error."""
    renderer.clear(Color(0, 0, 0))
    renderer.draw_rect(Rect(10, 10, 100, 100), Color(255, 0, 0))
    renderer.draw_circle(Vector2(200, 200), 50, Color(0, 255, 0))
    renderer.draw_line(Vector2(0, 0), Vector2(800, 600), Color(0, 0, 255))
    # We can't easily verify pixels in dummy mode, but successful execution is key


class MockTexture(Texture):
    def __init__(self, path: str, surface: pygame.Surface):
        super().__init__(path)
        self._surface = surface

    @property
    def width(self) -> int:
        return self._surface.get_width()

    @property
    def height(self) -> int:
        return self._surface.get_height()

    @property
    def native_handle(self) -> pygame.Surface:
        return self._surface


def test_render_batch_fast_path(renderer: PygameBackend) -> None:
    """Backend should handle fast-path batch rendering."""
    # Create a dummy texture
    surf = pygame.Surface((32, 32))
    texture = MockTexture("dummy_path", surf)

    # Create batch data
    batch = RenderBatch(
        texture=texture,
        destinations=[(0, 0), (100, 100)],
        rotations=[],
        scales=[],
        transforms_enabled=False,
    )

    renderer.render_batch(batch)


def test_render_batch_transform_path(renderer: PygameBackend) -> None:
    """Backend should handle transform-path batch rendering."""
    # Create a dummy texture
    surf = pygame.Surface((32, 32))
    texture = MockTexture("dummy_path", surf)

    # Create batch data with transforms
    batch = RenderBatch(
        texture=texture,
        destinations=[(0, 0), (100, 100)],
        rotations=[45.0, 90.0],
        scales=[(1.0, 1.0), (2.0, 2.0)],
        transforms_enabled=True,
    )

    renderer.render_batch(batch)
