"""Tests for HierarchyTool -- entity list + click selection.

Uses the real `create_headless_application()` bootstrap so the tool resolves
its SceneManager through the actual composition root.
"""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from unittest.mock import MagicMock

import pygame
import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.common.components import Tag
from pyguara.events.input import MouseButtonEvent
from pyguara.graphics.protocols import UIRenderer
from pyguara.scene.base import Scene
from pyguara.tools.hierarchy import HierarchyTool


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


def _renderer() -> MagicMock:
    r = MagicMock(spec=UIRenderer)
    r.get_text_size.return_value = (50, 16)
    return r


def _click(tool: HierarchyTool, x: int, y: int) -> bool:
    event = MouseButtonEvent(button=1, x=x, y=y, is_down=True)
    return tool.process_event(event)


def _app_with_scene():
    app = create_headless_application()
    scene = _Scene("s", app._event_dispatcher)
    app._scene_manager.register(scene)
    app._scene_manager.switch_to(scene.name)
    return app, scene


def test_render_lists_one_row_per_entity() -> None:
    app, scene = _app_with_scene()
    for _ in range(3):
        scene.entity_manager.create_entity()

    tool = HierarchyTool(app._container)
    tool.render(_renderer())

    assert len(tool._rows) == 3
    app.shutdown()


def test_clicking_a_row_selects_that_entity() -> None:
    app, scene = _app_with_scene()
    e1 = scene.entity_manager.create_entity()
    scene.entity_manager.create_entity()

    tool = HierarchyTool(app._container)
    tool.render(_renderer())
    rect, entity_id = next((r, i) for r, i in tool._rows if i == e1.id)

    consumed = _click(tool, rect.x + 5, rect.y + 5)

    assert consumed is True
    assert tool.selected_entity is e1
    app.shutdown()


def test_label_uses_the_tag_when_present() -> None:
    app, scene = _app_with_scene()
    entity = scene.entity_manager.create_entity()
    entity.add_component(Tag(name="Boss"))

    assert HierarchyTool._label_for(entity).startswith("Boss (")
    app.shutdown()


def test_selection_is_dropped_when_the_entity_leaves_the_scene() -> None:
    app, scene = _app_with_scene()
    entity = scene.entity_manager.create_entity()
    tool = HierarchyTool(app._container)
    tool.selected_entity = entity

    scene.entity_manager.remove_entity(entity.id)
    scene.entity_manager.flush_pending_removals()
    tool.update(0.016)

    assert tool.selected_entity is None
    app.shutdown()


def test_click_outside_any_row_changes_nothing() -> None:
    app, scene = _app_with_scene()
    scene.entity_manager.create_entity()
    tool = HierarchyTool(app._container)
    tool.render(_renderer())

    assert _click(tool, 5000, 5000) is False
    assert tool.selected_entity is None
    app.shutdown()
