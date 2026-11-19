"""A scene for integration tests that need one to run, and nothing more."""

from __future__ import annotations

from pyguara.common.types import Color
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.scene.base import Scene


class ClearScene(Scene):
    """Counts its updates and clears the screen; draws nothing else."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        super().__init__("ClearScene", event_dispatcher)
        self.frame_count = 0

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        self.frame_count += 1

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        world_renderer.clear(Color(0, 0, 100))
