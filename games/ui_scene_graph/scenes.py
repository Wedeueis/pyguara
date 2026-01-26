"""Module 6: UI Scenes.

Menu and Gameplay scenes demonstrating the UI Scene Graph.
"""

import sys
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.common.types import Vector2, Color
from pyguara.ui.manager import UIManager
from pyguara.ui.layout import BoxContainer
from pyguara.ui.components.button import Button
from pyguara.ui.components.label import Label


class GameScene(Scene):
    """A dummy gameplay scene."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize scene."""
        super().__init__("GameScene", event_dispatcher)

    def on_enter(self) -> None:
        """Create UI."""
        print("GameScene entered!")
        ui_manager = self.container.get(UIManager)

        # Clear previous UI (Tutorial simplification)
        ui_manager._root_elements.clear()

        # Create Back Button
        btn_back = Button("BACK", position=Vector2(20, 20), size=Vector2(100, 40))
        btn_back.on_click = self.on_back_click

        ui_manager.add_element(btn_back)

        # Create Label
        label = Label("GAMEPLAY ACTIVE", position=Vector2(300, 250))
        ui_manager.add_element(label)

    def on_back_click(self, el) -> None:
        """Handle back button."""
        print("Back clicked!")
        self.container.get(SceneManager).pop()

    def on_exit(self) -> None:
        """Cleanup."""
        pass

    def update(self, dt: float) -> None:
        """Update logic."""
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render scene."""
        world_renderer.clear(Color(20, 50, 20))  # Greenish bg


class MenuScene(Scene):
    """The main menu scene."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize scene."""
        super().__init__("MenuScene", event_dispatcher)

    def on_enter(self) -> None:
        """Create menu UI."""
        print("MenuScene entered!")
        ui_manager = self.container.get(UIManager)

        # Clear previous UI
        ui_manager._root_elements.clear()

        # Create a vertical box container
        container = BoxContainer(
            position=Vector2(300, 200), size=Vector2(200, 200), spacing=10
        )

        # Start Button
        btn_start = Button("START GAME", position=Vector2(0, 0))
        btn_start.on_click = self.on_start_click
        container.add_child(btn_start)

        # Quit Button
        btn_quit = Button("QUIT", position=Vector2(0, 0))
        btn_quit.on_click = self.on_quit_click
        container.add_child(btn_quit)

        # Apply layout
        container.layout()

        # Add to manager
        ui_manager.add_element(container)

    def on_start_click(self, el) -> None:
        """Handle start button."""
        print("Start Game clicked!")
        scene_manager = self.container.get(SceneManager)
        scene_manager.push(GameScene(self.event_dispatcher))

    def on_quit_click(self, el) -> None:
        """Handle quit button."""
        print("Quit clicked!")
        sys.exit(0)

    def on_exit(self) -> None:
        """Cleanup."""
        pass

    def update(self, dt: float) -> None:
        """Update logic."""
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render scene."""
        world_renderer.clear(Color(50, 20, 20))  # Reddish bg
