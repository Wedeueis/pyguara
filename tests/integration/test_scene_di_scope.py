"""Regression tests for Scene/SceneManager DIScope wiring (#65).

Uses the real `create_headless_application()` bootstrap, not a hand-rolled
container, so `Scene.resolve_dependencies()` exercises the actual
composition root -- the same reasoning `test_scene_owned_systems.py` gives.
"""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pytest

from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application
from pyguara.di.container import DIScope
from pyguara.scene.base import Scene


class _TestScene(Scene):
    """Minimal concrete Scene relying entirely on the base class defaults."""

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass


def _register(app: Application, name: str) -> _TestScene:
    scene = _TestScene(name, app._event_dispatcher)
    app._scene_manager.register(scene)
    return scene


@pytest.fixture
def app():
    return create_headless_application()


def test_resolve_dependencies_creates_a_scope(app: Application) -> None:
    scene = _register(app, "scene_a")
    app._scene_manager.switch_to("scene_a")

    assert isinstance(scene.scope, DIScope)
    assert scene.scope.disposed is False


def test_switching_away_disposes_the_previous_scenes_scope(app: Application) -> None:
    scene_a = _register(app, "scene_a")
    scene_b = _register(app, "scene_b")
    app._scene_manager.switch_to("scene_a")

    app._scene_manager.switch_to("scene_b")

    assert scene_a.scope is not None
    assert scene_a.scope.disposed is True
    assert scene_b.scope is not None
    assert scene_b.scope.disposed is False


def test_popping_a_pushed_scene_disposes_its_scope(app: Application) -> None:
    scene_a = _register(app, "scene_a")
    scene_b = _register(app, "scene_b")
    app._scene_manager.switch_to("scene_a")
    app._scene_manager.push_scene("scene_b")

    popped = app._scene_manager.pop_scene()

    assert popped is scene_b
    assert scene_b.scope is not None
    assert scene_b.scope.disposed is True
    # scene_a was never exited, only paused/resumed -- its scope survives.
    assert scene_a.scope is not None
    assert scene_a.scope.disposed is False


def test_cleanup_disposes_every_scenes_scope(app: Application) -> None:
    scene_a = _register(app, "scene_a")
    scene_b = _register(app, "scene_b")
    app._scene_manager.switch_to("scene_a")
    app._scene_manager.push_scene("scene_b")

    app._scene_manager.cleanup()

    assert scene_a.scope is not None and scene_a.scope.disposed is True
    assert scene_b.scope is not None and scene_b.scope.disposed is True


def test_each_scene_gets_its_own_distinct_scope(app: Application) -> None:
    scene_a = _register(app, "scene_a")
    scene_b = _register(app, "scene_b")
    app._scene_manager.switch_to("scene_a")
    app._scene_manager.push_scene("scene_b")

    assert scene_a.scope is not scene_b.scope
