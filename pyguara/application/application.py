"""Main application runtime.

Implements a fixed timestep game loop for deterministic physics simulation.
The accumulator pattern decouples physics updates (fixed rate) from rendering
(display framerate), preventing tunneling and ensuring consistent behavior
regardless of frame rate variations.
"""

import pygame

from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer, IRenderer
from pyguara.graphics.window import Window
from pyguara.input.manager import InputManager
from pyguara.log.manager import LogManager
from pyguara.log.types import LogCategory
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.systems.manager import SystemManager
from pyguara.ui.manager import UIManager

# Event queue processing budget (milliseconds per frame)
DEFAULT_EVENT_QUEUE_TIME_BUDGET_MS = 5.0


class Application:
    """The main runtime loop coordinator.

    Uses a fixed timestep game loop for deterministic physics:
    - Physics/logic updates run at a fixed rate (default 60 Hz)
    - Rendering runs at display framerate (vsync or target FPS)
    - Accumulator pattern prevents physics tunneling on lag spikes
    """

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

        self._log_manager = self._container.get(LogManager)
        self.logger = self._log_manager.get_logger("Application", LogCategory.SYSTEM)
        self._window = container.get(Window)
        self._event_dispatcher = container.get(EventDispatcher)
        self._input_manager = container.get(InputManager)
        self._scene_manager = container.get(SceneManager)
        self._config_manager = container.get(ConfigManager)
        self._ui_manager = container.get(UIManager)
        self._system_manager = container.get(SystemManager)
        self._coroutine_manager = container.get(CoroutineManager)

        # Retrieve Renderer
        self._world_renderer = container.get(IRenderer)  # type: ignore[type-abstract]
        self._ui_renderer = container.get(UIRenderer)  # type: ignore[type-abstract]

        self._scene_manager.set_container(container)

        # Initialize all registered systems
        self._system_manager.initialize()

        self._clock = pygame.time.Clock()

        # Fixed timestep accumulator
        self._accumulator = 0.0

        self.logger.info("Application instance created.")

    def run(self, starting_scene: Scene) -> None:
        """Execute the main game loop with fixed timestep physics.

        The loop uses the accumulator pattern:
        1. Measure frame time (variable)
        2. Accumulate time for physics
        3. Run physics updates at fixed rate (e.g., 60 Hz)
        4. Render at display framerate

        This ensures deterministic physics regardless of display framerate.
        """
        self.logger.info(f"Starting with scene: {starting_scene.name}")

        self._scene_manager.register(starting_scene)
        self._scene_manager.switch_to(starting_scene.name)

        self._is_running = True
        target_fps = self._config_manager.config.display.fps_target
        physics_config = self._config_manager.config.physics
        fixed_dt = physics_config.fixed_dt
        max_frame_time = physics_config.max_frame_time

        self.logger.debug(
            f"Game loop: target_fps={target_fps}, physics_hz={physics_config.fixed_timestep_hz}, fixed_dt={fixed_dt}"
        )

        # Force an initial event pump to show the window immediately
        pygame.event.pump()

        try:
            while self._is_running and self._window.is_open:
                # 1. Measure frame time
                frame_time = self._clock.tick(target_fps) / 1000.0

                # Clamp frame time to prevent spiral of death
                # (when updates take longer than real time, causing ever-growing backlog)
                if frame_time > max_frame_time:
                    frame_time = max_frame_time

                # 2. Input (once per frame, before physics)
                self._process_input()

                # 3. Accumulate time and run fixed updates
                self._accumulator += frame_time

                while self._accumulator >= fixed_dt:
                    # Fixed-rate update (physics, game logic)
                    self._fixed_update(fixed_dt)
                    self._accumulator -= fixed_dt

                # 4. Variable-rate update (UI, animations that should be smooth)
                self._update(frame_time)

                # 5. Render (at display framerate)
                # The alpha value represents how far we are between physics steps
                # This can be used for interpolation in the future
                # alpha = self._accumulator / fixed_dt
                self._render()
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            self.logger.info("KeyboardInterrupt received. Stopping.")
        except Exception as e:
            # Log unexpected crashes before shutting down
            self.logger.critical(f"Uncaught exception in game loop: {e}", exc_info=True)
            raise e  # Re-raise to show traceback
        finally:
            # CRITICAL: This ensures cleanup happens even if sys.exit() is called
            self.shutdown()

    def _process_input(self) -> None:
        """Poll system events."""
        # This call is CRITICAL. It keeps the OS window responsive.
        for event in self._window.poll_events():
            if hasattr(event, "type") and event.type == pygame.QUIT:
                self._is_running = False

            # Dispatch to input manager
            self._input_manager.process_event(event)

    def _fixed_update(self, fixed_dt: float) -> None:
        """Fixed-rate update for physics and deterministic game logic.

        This method runs at a fixed rate (default 60 Hz) regardless of display
        framerate. Use this for:
        - Physics simulation
        - Game logic that must be deterministic
        - AI decision making
        - Collision detection

        Args:
            fixed_dt: Fixed delta time in seconds (e.g., 1/60 for 60 Hz).
        """
        # 1. Process background thread events with time budget (P1-009)
        # Enforce time budget to prevent event death spirals
        self._event_dispatcher.process_queue(
            max_time_ms=self._event_queue_time_budget_ms
        )

        # 2. Update all registered systems (AI, Animation, etc.)
        self._system_manager.update(fixed_dt)

        # 3. Update Scene (Physics, Logic) at fixed rate
        self._scene_manager.fixed_update(fixed_dt)

    def _update(self, dt: float) -> None:
        """Variable-rate update for UI and smooth animations.

        This method runs once per frame at display framerate. Use this for:
        - UI updates
        - Smooth visual animations (tweens, particles)
        - Camera smoothing
        - Audio updates
        - Coroutine-based scripting

        Args:
            dt: Variable delta time in seconds (frame time).
        """
        # Update UI at display framerate for smooth interactions
        self._ui_manager.update(dt)

        # Update coroutines (scripted sequences)
        self._coroutine_manager.update(dt)

        # Variable-rate scene update (animations, camera, etc.)
        self._scene_manager.update(dt)

    def _render(self) -> None:
        """Render frame."""
        self._window.clear()
        self._scene_manager.render(self._world_renderer, self._ui_renderer)
        self._ui_manager.render(self._ui_renderer)
        self._ui_renderer.present()  # Finalize UI (composites for GL backends)
        self._window.present()

    def shutdown(self) -> None:
        """Close Application."""
        self.logger.info("Shutting down application")
        self._scene_manager.cleanup()
        self._system_manager.cleanup()
        self._window.close()
