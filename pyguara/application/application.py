"""Main application runtime."""

import pygame

from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer
from pyguara.graphics.window import Window
from pyguara.input.manager import InputManager
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager


class Application:
    """
    The main runtime loop coordinator.

    This class relies on the DIContainer to resolve all necessary subsystems
    (Window, Input, Scenes, etc.) and orchestrates the frame lifecycle.

    Attributes:
        container: The dependency injection container holding engine services.
        is_running: Boolean flag controlling the main loop.
    """

    def __init__(self, container: DIContainer) -> None:
        """
        Initialize the application using the provided container.

        Args:
            container: A configured DIContainer with core services registered.
        """
        self._container = container
        self._is_running = False

        # Resolve Core Dependencies immediately to fail fast if missing
        self._window = container.get(Window)
        self._event_dispatcher = container.get(EventDispatcher)
        self._input_manager = container.get(InputManager)
        self._scene_manager = container.get(SceneManager)
        self._config_manager = container.get(ConfigManager)

        # Resolve Renderer (UI)
        # Note: In a real scenario, UIRenderer might be registered, or created here
        self._ui_manager = container.get(UIManager)
        # We might need to resolve the concrete renderer if registered,
        # or rely on the one passed to render()
        self._ui_renderer = container.get(UIRenderer)  # type: ignore[type-abstract]

        self._clock = pygame.time.Clock()

    def run(self, starting_scene: Scene) -> None:
        """
        Execute the main game loop.

        Args:
            starting_scene: The initial scene to display.
        """
        # Register and switch to the starting scene
        self._scene_manager.register(starting_scene)
        self._scene_manager.switch_to(starting_scene.name)

        self._is_running = True
        target_fps = self._config_manager.config.display.fps_target

        while self._is_running and self._window.is_open:
            # 1. Time
            dt = self._clock.tick(target_fps) / 1000.0

            # 2. Input
            self._process_input()

            # 3. Update
            self._update(dt)

            # 4. Render
            self._render()

        self.shutdown()

    def _process_input(self) -> None:
        """Poll and dispatch input events."""
        # Use the Window abstraction to poll events
        for event in self._window.poll_events():
            # Handle native close event
            if hasattr(event, "type") and event.type == pygame.QUIT:
                self._is_running = False

            # Forward to Input Manager
            self._input_manager.process_event(event)

    def _update(self, dt: float) -> None:
        """Update game logic."""
        self._ui_manager.update(dt)
        self._scene_manager.update(dt)

    def _render(self) -> None:
        """Render the current frame."""
        self._window.clear()

        # Render Scene
        self._scene_manager.render(self._ui_renderer)

        # Render UI
        self._ui_manager.render(self._ui_renderer)

        self._window.present()

    def shutdown(self) -> None:
        """Clean up resources."""
        self._window.close()
        # The container might handle disposal of other services
