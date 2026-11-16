"""`pyguara.run()` is a whole entry point, and a scene needs no dispatcher.

Runs the real bootstrap on the software renderer with SDL's dummy drivers,
so the loop, the scene manager and the shutdown are the ones a game gets.
"""

import os
import subprocess
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

import pyguara
from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.scene.base import Scene, SceneNotReadyError
from pyguara.scene.manager import SceneManager

FRAMES = 3


class _Counting(Scene):
    """Counts its updates and quits after `FRAMES` of them."""

    entered: int = 0
    updates: int = 0

    def on_enter(self) -> None:
        type(self).entered += 1

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        type(self).updates += 1
        if type(self).updates >= FRAMES:
            self.application.quit()


@pytest.fixture(autouse=True)
def _reset():
    _Counting.entered = 0
    _Counting.updates = 0
    yield
    pygame.quit()


def _software(config: GameConfig) -> None:
    config.display.backend = RenderingBackend.PYGAME


class TestASceneWithoutADispatcher:
    def test_its_name_defaults_to_the_class_name(self) -> None:
        assert _Counting().name == "_Counting"

    def test_the_dispatcher_is_refused_before_the_container_arrives(self) -> None:
        with pytest.raises(SceneNotReadyError, match="on_enter"):
            _ = _Counting().event_dispatcher

    def test_the_engine_supplies_the_applications_own(self) -> None:
        app = create_headless_application()
        scene = _Counting()

        app.container.get(SceneManager).register(scene)

        assert scene.event_dispatcher is app.container.get(EventDispatcher)

    def test_one_passed_to_the_constructor_is_kept(self) -> None:
        app = create_headless_application()
        own = EventDispatcher()
        scene = _Counting("named", own)

        app.container.get(SceneManager).register(scene)

        assert scene.name == "named"
        assert scene.event_dispatcher is own


class TestRun:
    def test_a_scene_class_is_built_and_run_to_the_end(self) -> None:
        pyguara.run(_Counting, configure=_software)

        assert _Counting.entered == 1
        assert _Counting.updates == FRAMES

    def test_a_scene_instance_is_run_as_given(self) -> None:
        scene = _Counting("given")

        pyguara.run(scene, configure=_software)

        assert _Counting.updates == FRAMES
        assert scene.container is not None

    def test_setup_sees_the_container_before_the_application_is_built(self) -> None:
        seen: list[DIContainer] = []

        class _Marker:
            pass

        def setup(container: DIContainer) -> None:
            seen.append(container)
            container.register_instance(_Marker, _Marker())

        scene = _Counting()
        pyguara.run(scene, configure=_software, setup=setup)

        assert len(seen) == 1
        assert scene.container is seen[0]
        assert isinstance(seen[0].get(_Marker), _Marker)
        assert seen[0].get(Application) is scene.application

    def test_something_that_is_not_a_scene_is_refused_before_anything_is_built(
        self,
    ) -> None:
        with pytest.raises(TypeError, match="Scene or a Scene subclass"):
            pyguara.run("TitleScene")  # type: ignore[arg-type]


def test_importing_pyguara_does_not_import_the_engine() -> None:
    probe = (
        "import sys, pyguara; "
        "assert callable(pyguara.run); "
        "print('pyguara.application' in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "False"
