"""A game can end its own loop, from inside a frame.

Runs the real bootstrap on the software renderer with SDL's dummy drivers.
"""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

from pyguara.application.application import Application
from pyguara.application.bootstrap import create_application
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.lifecycle import QuitEvent
from pyguara.graphics.window import Window
from pyguara.scene.base import Scene

FRAMES = 3


class _Leaving(Scene):
    """Leaves after `FRAMES` updates, by whichever way it was told to."""

    def __init__(self, dispatcher: EventDispatcher, how: str) -> None:
        super().__init__("leaving", dispatcher)
        self.how = how
        self.updates = 0
        self.renders = 0

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        self.updates += 1
        if self.updates == FRAMES:
            if self.how == "quit":
                self.application.quit()
            else:
                assert self.container is not None
                self.container.get(Window).close()

    def render(self, world_renderer: object, ui_renderer: object) -> None:
        self.renders += 1
        super().render(world_renderer, ui_renderer)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


def _software(config: GameConfig) -> None:
    config.display.backend = RenderingBackend.PYGAME


def _application() -> Application:
    return create_application(configure=_software)


def test_quit_finishes_the_frame_and_ends_the_loop() -> None:
    app = _application()
    dispatcher = app.container.get(EventDispatcher)
    heard: list[QuitEvent] = []
    dispatcher.subscribe(QuitEvent, heard.append)
    scene = _Leaving(dispatcher, "quit")

    app.run(scene)

    assert scene.updates == FRAMES
    assert scene.renders == FRAMES, "the frame that asked to quit was not drawn"
    assert [event.source for event in heard] == [app]
    assert app.container.get(Window).is_open is False


def test_quit_outside_the_loop_does_nothing() -> None:
    app = _application()
    heard: list[QuitEvent] = []
    app.container.get(EventDispatcher).subscribe(QuitEvent, heard.append)
    try:
        app.quit()
        assert heard == []
    finally:
        app.shutdown()


def test_closing_the_window_inside_a_frame_ends_the_loop_without_drawing() -> None:
    app = _application()
    scene = _Leaving(app.container.get(EventDispatcher), "close")

    app.run(scene)

    assert scene.updates == FRAMES
    assert scene.renders == FRAMES - 1, "a frame was drawn to a closed window"
