"""A scene reaches the engine's common services through typed accessors.

ADR 0012: `scene.ui_manager`, `scene.scene_manager`, `scene.application` and
`scene.input_manager` are the sanctioned way in; `scene.container.get(T)` is
the escape hatch for everything else. Uses the real headless bootstrap so the
accessors resolve against the actual composition root.
"""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.manager import InputManager
from pyguara.scene.base import Scene, SceneNotReadyError
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager


class _Probe(Scene):
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


def _entered(app: Application) -> _Probe:
    scene = _Probe("probe", app.container.get(EventDispatcher))
    manager = app.container.get(SceneManager)
    manager.register(scene)
    manager.switch_to(scene.name)
    return scene


def test_the_accessors_return_the_applications_own_services() -> None:
    app = create_headless_application()
    scene = _entered(app)

    assert scene.application is app
    assert scene.scene_manager is app.container.get(SceneManager)
    assert scene.ui_manager is app.container.get(UIManager)
    assert scene.input_manager is app.container.get(InputManager)


@pytest.mark.parametrize(
    "accessor", ["application", "scene_manager", "ui_manager", "input_manager"]
)
def test_an_accessor_before_the_scene_is_resolved_says_when_to_ask(
    accessor: str,
) -> None:
    scene = _Probe("early", EventDispatcher())

    with pytest.raises(SceneNotReadyError, match="on_enter"):
        getattr(scene, accessor)


def test_not_ready_is_still_a_runtime_error() -> None:
    # Code that caught the RuntimeError `start_coroutine` raised keeps working.
    assert issubclass(SceneNotReadyError, RuntimeError)
