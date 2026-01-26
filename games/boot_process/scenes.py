"""Module 1: Boot Scene

A minimal scene to satisfy the Application requirements.
"""

from pyguara.scene.base import Scene
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.common.types import Color

class BootScene(Scene):
    """A simple scene that does nothing but clear the screen."""
    
    def __init__(self, event_dispatcher: EventDispatcher):
        super().__init__("BootScene", event_dispatcher)
        self.frame_count = 0

    def on_enter(self) -> None:
        print("BootScene entered!")

    def on_exit(self) -> None:
        print("BootScene exited!")

    def update(self, dt: float) -> None:
        self.frame_count += 1
        # In a real game, logic goes here

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        # Clear the screen to blue
        world_renderer.clear(Color(0, 0, 100))
