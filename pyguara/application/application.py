"""Main application runtime."""

import pygame

from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer, IRenderer
from pyguara.graphics.window import Window
from pyguara.input.manager import InputManager
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager

# Event queue processing budget (milliseconds per frame)
DEFAULT_EVENT_QUEUE_TIME_BUDGET_MS = 5.0


class Application:
    """The main runtime loop coordinator."""

    def __init__(
        self,
        container: DIContainer,
        event_queue_time_budget_ms: float = DEFAULT_EVENT_QUEUE_TIME_BUDGET_MS,
    ) -> None:
        """Initialize Application with a DI container.

        Args:
            container: The dependency injection container.
            event_queue_time_budget_ms: Time budget in milliseconds for processing
                event queue per frame. Defaults to 5ms.
        """
        self._container = container
        self._is_running = False
        self._event_queue_time_budget_ms = event_queue_time_budget_ms

        # Resolve Core Dependencies
        self._window = container.get(Window)
        self._event_dispatcher = container.get(EventDispatcher)
        self._input_manager = container.get(InputManager)
        self._scene_manager = container.get(SceneManager)
        self._config_manager = container.get(ConfigManager)
        self._ui_manager = container.get(UIManager)

        # Retrieve Renderer
        self._world_renderer = container.get(IRenderer)  # type: ignore[type-abstract]
        self._ui_renderer = container.get(UIRenderer)  # type: ignore[type-abstract]

        self._scene_manager.set_container(container)

        self._clock = pygame.time.Clock()

    def run(self, starting_scene: Scene) -> None:
        """Execute the main game loop."""
        print(f"[Application] Starting with scene: {starting_scene.name}")

        self._scene_manager.register(starting_scene)
        self._scene_manager.switch_to(starting_scene.name)

        self._is_running = True
        target_fps = self._config_manager.config.display.fps_target

        # Force an initial event pump to show the window immediately
        pygame.event.pump()

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
        """Poll system events."""
        # This call is CRITICAL. It keeps the OS window responsive.
        for event in self._window.poll_events():
            if hasattr(event, "type") and event.type == pygame.QUIT:
                self._is_running = False

            # Dispatch to input manager
            self._input_manager.process_event(event)

    def _update(self, dt: float) -> None:
        """Update game logic."""
        # 1. Process background thread events with time budget (P1-009)
        # Enforce time budget to prevent event death spirals
        self._event_dispatcher.process_queue(
            max_time_ms=self._event_queue_time_budget_ms
        )

        # 2. Update UI
        self._ui_manager.update(dt)

        # 3. Update Scene (Physics, Logic)
        self._scene_manager.update(dt)

    def _render(self) -> None:
        """Render frame."""
        self._window.clear()
        self._scene_manager.render(self._world_renderer, self._ui_renderer)
        self._ui_manager.render(self._ui_renderer)
        self._window.present()

    def shutdown(self) -> None:
        """Close Application."""
        print("[Application] Shutting down...")
        self._window.close()
