"""Tests for AssetsTool -- resource browser + spawn-from-DataResource.

Uses the real `create_headless_application()` bootstrap so the tool resolves
its ResourceManager, ComponentRegistry and SceneManager through the actual
composition root.
"""

import json
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from unittest.mock import MagicMock

import pygame
import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.common.components import ResourceLink, Tag, Transform
from pyguara.graphics.protocols import UIRenderer
from pyguara.scene.base import Scene
from pyguara.tools.assets_browser import AssetsTool


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


def _app_with_scene():
    app = create_headless_application()
    scene = _Scene("s", app._event_dispatcher)
    app._scene_manager.register(scene)
    app._scene_manager.switch_to(scene.name)
    return app, scene


def _write_goblin(tmp_path) -> str:
    path = tmp_path / "goblin.json"
    path.write_text(
        json.dumps(
            {
                "Tag": {"name": "Goblin"},
                "Transform": {"position": {"x": 10, "y": 20}},
                "unregistered_key": 5,
            }
        )
    )
    return str(path)


def test_render_lists_indexed_and_loaded_resources(tmp_path) -> None:
    app, _ = _app_with_scene()
    (tmp_path / "goblin.json").write_text("{}")

    from pyguara.resources.manager import ResourceManager

    resources = app._container.get(ResourceManager)
    resources.index_directory(str(tmp_path))

    tool = AssetsTool(app._container)
    tool.render(_renderer())

    paths = [p for _r, p in tool._rows]
    assert str(tmp_path / "goblin.json") in paths
    app.shutdown()


def test_spawn_builds_an_entity_through_the_component_registry(tmp_path) -> None:
    app, scene = _app_with_scene()
    path = _write_goblin(tmp_path)

    tool = AssetsTool(app._container)
    tool._selected_path = path
    entity = tool._spawn_selected()

    assert entity is not None
    kinds = {type(c).__name__ for c in entity.get_all_components()}
    assert kinds == {"ResourceLink", "Tag", "Transform"}
    assert entity.get_component(Tag).name == "Goblin"
    assert entity.get_component(Transform).position.x == 10
    assert entity.get_component(ResourceLink).resource_path == path
    app.shutdown()


def test_spawn_skips_unregistered_keys_without_failing(tmp_path) -> None:
    app, scene = _app_with_scene()
    tool = AssetsTool(app._container)
    tool._selected_path = _write_goblin(tmp_path)

    entity = tool._spawn_selected()

    assert entity is not None
    assert "2 components" in tool._status  # Tag + Transform, not the junk key
    app.shutdown()


def test_spawn_without_an_active_scene_reports_and_returns_none(tmp_path) -> None:
    app = create_headless_application()  # no scene switched to
    tool = AssetsTool(app._container)
    tool._selected_path = _write_goblin(tmp_path)

    assert tool._spawn_selected() is None
    assert "No active scene" in tool._status
    app.shutdown()


def test_reload_button_is_not_clickable_when_resource_is_not_loaded(tmp_path) -> None:
    """An indexed-but-unloaded path: Reload is greyed AND has no hit rect,
    so clicking where it draws does nothing (the 'enabled' flag used to be
    cosmetic only)."""
    app, _ = _app_with_scene()
    path = _write_goblin(tmp_path)
    from pyguara.resources.manager import ResourceManager

    app._container.get(ResourceManager).index_directory(str(tmp_path))
    tool = AssetsTool(app._container)
    tool._selected_path = path
    tool.render(_renderer())

    assert tool._reload_rect is None  # not loaded -> no Reload
    assert tool._spawn_rect is not None  # might be data -> Spawn stays live
    app.shutdown()


def test_spawn_button_is_not_clickable_for_a_loaded_non_data_resource(
    tmp_path,
) -> None:
    app, _ = _app_with_scene()
    tool = AssetsTool(app._container)
    tool._selected_path = "/some/sprite.png"

    class _FakeTexture:
        native_handle = object()

    tool._resources.iter_cached = lambda: iter(  # type: ignore[method-assign]
        [("/some/sprite.png", _FakeTexture())]
    )
    tool.render(_renderer())

    assert tool._spawn_rect is None  # loaded and not a DataResource -> dead
    assert tool._reload_rect is not None  # loaded -> Reload is fine

    # And a click where the (now absent) Spawn button drew is a no-op.
    event = MagicMock()
    event.type = pygame.MOUSEBUTTONDOWN
    event.button = 1
    event.pos = (tool._panel_rect.x + 20, tool._panel_rect.y + 400)
    assert tool.process_event(event) is False
    app.shutdown()


def test_clicking_a_row_selects_it(tmp_path) -> None:
    app, _ = _app_with_scene()
    (tmp_path / "goblin.json").write_text("{}")
    from pyguara.resources.manager import ResourceManager

    app._container.get(ResourceManager).index_directory(str(tmp_path))
    tool = AssetsTool(app._container)
    tool.render(_renderer())
    rect, path = tool._rows[0]

    event = MagicMock()
    event.type = pygame.MOUSEBUTTONDOWN
    event.button = 1
    event.pos = (rect.x + 2, rect.y + 2)

    assert tool.process_event(event) is True
    assert tool._selected_path == path
    app.shutdown()
