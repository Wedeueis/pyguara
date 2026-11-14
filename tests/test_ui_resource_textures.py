"""A UI can draw what `ResourceManager` loads (#363).

Both UI renderers used to return silently for anything but a raw
`pygame.Surface`, so a `resources.Texture` was an empty rectangle with no clue
why, which made a path-based `Image` or `NinePatchPanel` impossible.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pygame
import pytest

from pyguara.common.types import Vector2
from pyguara.graphics.backends import surface_texture
from pyguara.graphics.backends.pygame.loaders import PygameImageLoader
from pyguara.graphics.backends.pygame.types import PygameTexture
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.backends.surface_texture import as_surface
from pyguara.graphics.ninepatch import NinePatchMetrics, NinePatchSprite
from pyguara.resources.manager import ResourceManager
from pyguara.ui.components.image import Image
from pyguara.ui.components.nine_patch_panel import NinePatchPanel

RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
GREEN = (0, 255, 0, 255)


@pytest.fixture(autouse=True)
def _display() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))


@pytest.fixture
def plate_path(tmp_path: Path) -> str:
    """12x12: a 4 px red frame around a blue centre."""
    plate = pygame.Surface((12, 12), pygame.SRCALPHA)
    plate.fill(RED)
    plate.fill(BLUE, pygame.Rect(4, 4, 4, 4))
    path = tmp_path / "plate.png"
    pygame.image.save(plate, str(path))
    return str(path)


def _target() -> pygame.Surface:
    target = pygame.Surface((64, 64), pygame.SRCALPHA)
    target.fill(GREEN)
    return target


class TestAsSurface:
    def test_a_surface_passes_through(self) -> None:
        surface = pygame.Surface((2, 2))

        assert as_surface(surface) is surface

    def test_a_pygame_texture_is_unwrapped(self) -> None:
        surface = pygame.Surface((2, 2))

        assert as_surface(PygameTexture("t.png", surface)) is surface

    def test_something_unusable_warns_once_and_draws_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class Unusable:
            pass

        surface_texture._warned_unusable.discard("Unusable")
        with caplog.at_level(logging.WARNING):
            assert as_surface(Unusable()) is None
            assert as_surface(Unusable()) is None

        assert sum("Unusable" in r.getMessage() for r in caplog.records) == 1


class TestThroughResourceManager:
    """Against pixels, on the backend with a surface to hand over."""

    @staticmethod
    def _manager() -> ResourceManager:
        manager = ResourceManager()
        manager.register_loader(PygameImageLoader())
        return manager

    def test_an_image_draws_a_loaded_texture(self, plate_path: str) -> None:
        from pyguara.resources.types import Texture

        target = _target()
        texture = self._manager().load(plate_path, Texture)  # type: ignore[type-abstract]

        Image(texture, Vector2(0, 0), Vector2(12, 12)).render(PygameUIRenderer(target))

        assert tuple(target.get_at((1, 1))) == RED
        assert tuple(target.get_at((6, 6))) == BLUE

    def test_a_panel_loads_its_own_texture_from_the_sprite(
        self, plate_path: str
    ) -> None:
        target = _target()
        sprite = NinePatchSprite(plate_path, NinePatchMetrics.uniform(4))
        panel = NinePatchPanel.from_resources(
            self._manager(), sprite, Vector2(0, 0), Vector2(40, 40)
        )

        panel.render(PygameUIRenderer(target))

        assert tuple(target.get_at((1, 1))) == RED
        assert tuple(target.get_at((20, 20))) == BLUE
