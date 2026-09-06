"""Regression tests for the live-tweakable inspector tools (wayfinder ticket 38).

Uses the real `create_headless_application()` bootstrap so `EntityInspector`
and `ConfigInspector` resolve their real dependencies (SceneManager,
ConfigManager) through the actual composition root, not a hand-rolled stub.
"""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from unittest.mock import MagicMock

import pygame
import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.config.manager import ConfigManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.physics.platformer_controller import PlatformerController
from pyguara.scene.base import Scene
from pyguara.tools.config_inspector import ConfigInspector
from pyguara.tools.inspector import EntityInspector


class _TestScene(Scene):
    """Minimal concrete Scene, matching test_scene_owned_systems.py's."""

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


def _click_at(tool, x: int, y: int) -> bool:
    event = MagicMock()
    event.type = pygame.MOUSEBUTTONDOWN
    event.button = 1
    event.pos = (x, y)
    return tool.process_event(event)


class TestEntityInspectorEditing:
    def test_clicking_a_bool_field_toggles_the_live_component(self) -> None:
        app = create_headless_application()
        scene = _TestScene("test_scene", app._event_dispatcher)
        app._scene_manager.register(scene)
        app._scene_manager.switch_to(scene.name)

        entity = scene.entity_manager.create_entity()
        transform = Transform(position=Vector2(0, 0), interpolate=False)
        entity.add_component(transform)

        inspector = EntityInspector(app._container)
        renderer = MagicMock(spec=UIRenderer)
        renderer.get_text_size.return_value = (50, 16)

        inspector.render(renderer)  # populates _tweakable_rows

        rect, leaf = next(
            (r, leaf)
            for r, leaf in inspector._tweakable_rows
            if leaf.label == "interpolate"
        )
        assert leaf.value is False

        consumed = _click_at(inspector, rect.x + 5, rect.y + 5)

        assert consumed is True
        assert transform.interpolate is True  # live component actually changed

        app.shutdown()

    def test_clicking_a_number_field_steps_the_live_component(self) -> None:
        """Uses PlatformerController.jump_force (a plain dataclass field),
        not Transform.position -- Transform's position/rotation/scale are
        property-backed by underscore-prefixed storage, so they were never
        reachable via EntityInspector's `__dict__` walk even before this
        ticket; that's an existing, deliberate scope boundary (ticket 38's
        decision to match EntityInspector's prior walk exactly), not a gap
        introduced here."""
        app = create_headless_application()
        scene = _TestScene("test_scene", app._event_dispatcher)
        app._scene_manager.register(scene)
        app._scene_manager.switch_to(scene.name)

        entity = scene.entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        controller = PlatformerController(jump_force=400.0)
        entity.add_component(controller)

        inspector = EntityInspector(app._container)
        renderer = MagicMock(spec=UIRenderer)
        renderer.get_text_size.return_value = (50, 16)
        inspector.render(renderer)

        rect, leaf = next(
            (r, leaf)
            for r, leaf in inspector._tweakable_rows
            if leaf.label == "jump_force"
        )
        assert leaf.value == 400.0

        # Click the right half: increments.
        _click_at(inspector, rect.x + rect.width - 5, rect.y + 5)

        assert controller.jump_force == 401.0

        app.shutdown()


class TestConfigInspectorEditing:
    def test_renders_game_config_tree_without_crashing(self) -> None:
        app = create_headless_application()
        inspector = ConfigInspector(app._container)
        renderer = MagicMock(spec=UIRenderer)
        renderer.get_text_size.return_value = (50, 16)

        inspector.render(renderer)

        assert renderer.draw_text.called
        assert len(inspector._tweakable_rows) > 0

        app.shutdown()

    def test_editing_and_saving_round_trips_through_config_manager(
        self, tmp_path
    ) -> None:
        app = create_headless_application()
        config_manager = app._container.get(ConfigManager)
        config_manager._file_path = tmp_path / "game_config.json"

        inspector = ConfigInspector(app._container)
        renderer = MagicMock(spec=UIRenderer)
        renderer.get_text_size.return_value = (50, 16)
        inspector.render(renderer)

        rect, leaf = next(
            (r, leaf)
            for r, leaf in inspector._tweakable_rows
            if leaf.label == "audio.master_volume"
        )
        original = leaf.value
        _click_at(inspector, rect.x + rect.width - 5, rect.y + 5)  # increment

        assert config_manager.config.audio.master_volume == original + 1.0

        save_event = MagicMock()
        save_event.type = pygame.KEYDOWN
        save_event.key = pygame.K_s
        assert inspector.process_event(save_event) is True

        assert config_manager._file_path.exists()

        # A fresh ConfigManager loading from the same file sees the saved value.
        reloaded = ConfigManager()
        reloaded.load(config_manager._file_path)
        assert reloaded.config.audio.master_volume == original + 1.0

        app.shutdown()
