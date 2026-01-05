"""Main application entry point."""

import pygame
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.input.manager import InputManager
from pyguara.ui.manager import UIManager
from pyguara.ui.components import Button, Panel, Label


class GameEngine:
    """Core game engine class managing the main loop and subsystems."""

    def __init__(self) -> None:
        """Initialize the game engine, window, and subsystems."""
        pygame.init()
        self.window = pygame.display.set_mode((1280, 720))
        self.running = True

        # Core Systems
        self.event_dispatcher = EventDispatcher()
        self.input_manager = InputManager(self.event_dispatcher)

        # UI Systems
        self.ui_renderer = PygameUIRenderer(self.window)
        self.ui_manager = UIManager(self.event_dispatcher)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Configure the initial UI layout."""
        # Create a background panel
        panel = Panel(position=Vector2(100, 100), size=Vector2(300, 400))
        self.ui_manager.add_element(panel)

        # Add a title
        title = Label("Main Menu", position=Vector2(20, 20), font_size=24)
        panel.add_child(title)

        # Add a button
        btn = Button("Start Game", position=Vector2(20, 80))

        # Callback fix: lambda needs valid signature or ignore
        btn.on_click = lambda e: print("Start Game Clicked!")
        panel.add_child(btn)

    def run(self) -> None:
        """Start the main game loop."""
        clock = pygame.time.Clock()

        while self.running:
            dt = clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                # Pass events to Input Manager (which dispatches to UI)
                self.input_manager.process_event(event)

            self.update(dt)
            self.render()

        pygame.quit()

    def update(self, dt: float) -> None:
        """Update game state and subsystems."""
        self.ui_manager.update(dt)

    def render(self) -> None:
        """Render the current frame."""
        self.window.fill((0, 0, 0))
        self.ui_manager.render(self.ui_renderer)
        pygame.display.flip()


if __name__ == "__main__":
    app = GameEngine()
    app.run()
