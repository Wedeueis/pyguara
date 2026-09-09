"""Tests for TransformGizmo -- the visual transform-handle tool.

Wired into `SandboxApplication` (F9) by the pyguara/tools audit; it had zero
coverage before. Uses the real `create_headless_application()` bootstrap so
the tool resolves its SceneManager through the actual composition root.
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
from pyguara.events.input import KeyDownEvent, MouseButtonEvent
from pyguara.graphics.protocols import UIRenderer
from pyguara.input import keys
from pyguara.scene.base import Scene
from pyguara.tools.gizmos import GizmoMode, TransformGizmo


class _Scene(Scene):
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


@pytest.fixture
def app_scene():
    app = create_headless_application()
    scene = _Scene("s", app._event_dispatcher)
    app._scene_manager.register(scene)
    app._scene_manager.switch_to(scene.name)
    yield app, scene
    app.shutdown()


def _key(code: int) -> KeyDownEvent:
    return KeyDownEvent(key_code=code)


def _entity_with_transform(scene, x=0.0, y=0.0):
    e = scene.entity_manager.create_entity()
    e.add_component(Transform(position=Vector2(x, y), interpolate=False))
    return e


class TestModeSwitching:
    def test_qwe_switch_modes_and_consume(self, app_scene) -> None:
        app, _ = app_scene
        gizmo = TransformGizmo(app._container)

        assert gizmo.mode is GizmoMode.TRANSLATE
        assert gizmo.process_event(_key(keys.W)) is True
        assert gizmo.mode is GizmoMode.ROTATE
        assert gizmo.process_event(_key(keys.E)) is True
        assert gizmo.mode is GizmoMode.SCALE
        assert gizmo.process_event(_key(keys.Q)) is True
        assert gizmo.mode is GizmoMode.TRANSLATE


class TestClickSelectionMode:
    """No selection_provider: the gizmo owns selection via viewport clicks."""

    def test_click_selects_entity_under_cursor(self, app_scene) -> None:
        app, scene = app_scene
        entity = _entity_with_transform(scene, 100, 100)
        gizmo = TransformGizmo(app._container)

        click = MouseButtonEvent(button=1, x=100, y=100, is_down=True)
        gizmo.process_event(click)

        assert gizmo.selected_entity is entity

    def test_escape_clears_selection(self, app_scene) -> None:
        app, scene = app_scene
        gizmo = TransformGizmo(app._container)
        gizmo.selected_entity = _entity_with_transform(scene)

        assert gizmo.process_event(_key(keys.ESCAPE)) is True
        assert gizmo.selected_entity is None


class TestProvidedSelectionMode:
    """With a selection_provider (the sandbox wiring), the gizmo follows it."""

    def test_update_pulls_selection_from_provider(self, app_scene) -> None:
        app, scene = app_scene
        entity = _entity_with_transform(scene)
        current = {"e": entity}
        gizmo = TransformGizmo(app._container, selection_provider=lambda: current["e"])

        gizmo.update(0.016)
        assert gizmo.selected_entity is entity

        current["e"] = None
        gizmo.update(0.016)
        assert gizmo.selected_entity is None

    def test_click_and_escape_are_inert_when_provided(self, app_scene) -> None:
        app, scene = app_scene
        entity = _entity_with_transform(scene, 50, 50)
        gizmo = TransformGizmo(app._container, selection_provider=lambda: entity)
        gizmo.update(0.016)

        # ESC must not clear a provider-driven selection
        assert gizmo.process_event(_key(keys.ESCAPE)) is False
        assert gizmo.selected_entity is entity

        # A viewport click must not hijack selection
        click = MouseButtonEvent(button=1, x=50, y=50, is_down=True)
        gizmo.process_event(click)
        assert gizmo.selected_entity is entity


class TestValidationAndRender:
    def test_update_drops_selection_that_lost_its_transform(self, app_scene) -> None:
        app, scene = app_scene
        entity = _entity_with_transform(scene)
        gizmo = TransformGizmo(app._container)
        gizmo.selected_entity = entity

        entity.remove_component(Transform)
        gizmo.update(0.016)

        assert gizmo.selected_entity is None

    def test_render_is_a_noop_without_a_selection(self, app_scene) -> None:
        app, _ = app_scene
        gizmo = TransformGizmo(app._container)
        renderer = MagicMock(spec=UIRenderer)

        gizmo.render(renderer)

        renderer.draw_line.assert_not_called()
        renderer.draw_rect.assert_not_called()

    def test_render_draws_handles_for_each_mode(self, app_scene) -> None:
        app, scene = app_scene
        gizmo = TransformGizmo(app._container)
        gizmo.selected_entity = _entity_with_transform(scene, 200, 150)
        renderer = MagicMock(spec=UIRenderer)

        for mode in GizmoMode:
            gizmo.mode = mode
            renderer.reset_mock()
            gizmo.render(renderer)
            assert renderer.draw_line.called or renderer.draw_circle.called
