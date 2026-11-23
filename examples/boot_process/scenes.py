"""Module 1: the boot scene.

A minimal scene to satisfy the Application requirements.
"""

from pyguara.common.types import Color
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.scene.base import Scene


class BootScene(Scene):
    """A simple scene that does nothing but clear the screen."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Create the scene under the name `BootScene`.

        Args:
            event_dispatcher: The engine's event bus.
        """
        super().__init__("BootScene", event_dispatcher)
        self.frame_count = 0

    def on_enter(self) -> None:
        """Report that the scene started."""
        print("BootScene entered!")

    def on_exit(self) -> None:
        """Report that the scene stopped."""
        print("BootScene exited!")

    def update(self, dt: float) -> None:
        """Count the frame.

        Args:
            dt: Seconds since the last frame.
        """
        self.frame_count += 1
        # In a real game, logic goes here

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Clear the screen to blue.

        Args:
            world_renderer: Draws the world.
            ui_renderer: Draws the interface, unused here.
        """
        world_renderer.clear(Color(0, 0, 100))
