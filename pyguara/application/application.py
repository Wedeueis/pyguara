"""Main application runtime.

Implements a fixed timestep game loop for deterministic physics simulation.
The accumulator pattern decouples physics updates (fixed rate) from rendering
(display framerate), preventing tunneling and ensuring consistent behavior
regardless of frame rate variations.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from pyguara.audio.audio_system import IAudioSystem
from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.di.exceptions import ServiceNotFoundException
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.lifecycle import ApplicationStartEvent, QuitEvent
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.window import Window
from pyguara.input.manager import InputManager
from pyguara.log.manager import LogManager
from pyguara.replay.player import ReplayPlayer
from pyguara.replay.recorder import ReplayRecorder
from pyguara.replay.serializer import ReplaySerializer
from pyguara.replay.types import ReplayData
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.ui.manager import UIManager

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.graph import RenderGraph

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
        self._has_shut_down = False
        self._event_queue_time_budget_ms = event_queue_time_budget_ms

        # Resolve Core Dependencies

        self._log_manager = self._container.get(LogManager)
        self.logger = self._log_manager.get_logger("Application")
        self._window = container.get(Window)
        self._event_dispatcher = container.get(EventDispatcher)
        self._input_manager = container.get(InputManager)
        self._scene_manager = container.get(SceneManager)
        self._scene_manager.set_screen_size(self._window.width, self._window.height)
        self._config_manager = container.get(ConfigManager)
        self._ui_manager = container.get(UIManager)
        self._coroutine_manager = container.get(CoroutineManager)
        self._audio_system = container.get(IAudioSystem)  # type: ignore[type-abstract]

        # Retrieve Renderer
        self._world_renderer = container.get(IRenderer)  # type: ignore[type-abstract]
        self._ui_renderer = container.get(UIRenderer)  # type: ignore[type-abstract]

        # Optional render graph for multi-pass rendering (ModernGL only).
        # Pygame backends register a `PygameRenderGraph` stub under this same
        # key so game code using lighting/post-processing degrades gracefully;
        # that stub is resolvable but is not a real RenderGraph, so branch on
        # backend identity (isinstance) rather than mere resolvability.
        self._render_graph: RenderGraph | None = None
        try:
            # Imported here, not at module scope, because the ModernGL pipeline
            # is an optional dependency. ServiceNotFoundException is imported
            # above: naming it in the `except` while importing it inside the
            # `try` meant an ImportError here would raise NameError instead.
            from pyguara.graphics.pipeline.graph import RenderGraph

            candidate = container.get(RenderGraph)
            if isinstance(candidate, RenderGraph):
                self._render_graph = candidate
        except (ImportError, ServiceNotFoundException):
            pass  # Render graph not available (Pygame backend or tests)

        self._scene_manager.set_container(container)

        self._clock = pygame.time.Clock()

        # Fixed timestep accumulator
        self._accumulator = 0.0
        self._fixed_dt = 0.0  # set for real in run(), from config

        # Replay recording/playback (mutually exclusive; see start_recording()/
        # load_replay()). Idle by default: near-zero overhead when neither is active.
        self._replay_serializer = ReplaySerializer()
        self._replay_recorder: ReplayRecorder | None = None
        self._replay_player: ReplayPlayer | None = None
        self._replay_frame_id = 0
        self._replay_clock = 0.0

        self.logger.info("Application instance created.")

    def run(self, starting_scene: Scene) -> None:
        """Execute the main game loop with a fixed timestep, until the window closes.

        Each frame measures its own duration, clamps it to
        `physics.max_frame_time`, accumulates it, and runs as many fixed-rate
        updates as that buys before rendering once. Physics therefore behaves
        identically regardless of display framerate.

        Dispatches `ApplicationStartEvent` before the first frame, and always
        calls `shutdown()` on the way out.

        Args:
            starting_scene: Scene to register and activate before the loop.

        Raises:
            ValueError: If `physics.fixed_timestep_hz` is not positive.
            Exception: Anything raised inside the loop, after logging it.
        """
        self.logger.info(f"Starting with scene: {starting_scene.name}")

        self._scene_manager.register(starting_scene)
        self._scene_manager.switch_to(starting_scene.name)

        self._is_running = True
        target_fps = self._config_manager.config.display.fps_target
        physics_config = self._config_manager.config.physics
        fixed_dt = physics_config.fixed_dt
        self._fixed_dt = fixed_dt  # persisted so _render() can compute alpha
        max_frame_time = physics_config.max_frame_time

        self.logger.debug(
            f"Game loop: target_fps={target_fps}, "
            f"physics_hz={physics_config.fixed_timestep_hz}, fixed_dt={fixed_dt}"
        )

        self._event_dispatcher.dispatch(ApplicationStartEvent(source=self))

        # Force an initial event pump to show the window immediately. No-op
        # (raises pygame.error) under a backend that never initializes SDL's
        # video subsystem at all, e.g. the headless test backend -- which has
        # no window to show in the first place.
        with contextlib.suppress(pygame.error):
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
                # Gamepad state must be fresh before poll_events() drains this
                # frame's SDL events, since that pump is what keeps pygame's
                # internal joystick device list current.
                self._input_manager.update()
                self._process_input(frame_time)

                # 3. Drain queued events once per frame, before the fixed
                # updates that consume them. Not inside the accumulator loop:
                # the time budget exists to stop an event death spiral, and a
                # per-step budget multiplies by the step count, so a lagged
                # frame could spend 15x the budget at exactly the moment the
                # spiral is starting.
                self._event_dispatcher.process_queue(
                    max_time_ms=self._event_queue_time_budget_ms
                )

                # 4. Accumulate time and run fixed updates
                self._accumulator += frame_time

                while self._accumulator >= fixed_dt:
                    # Fixed-rate update (physics, game logic)
                    self._fixed_update(fixed_dt)
                    self._accumulator -= fixed_dt

                # 5. Variable-rate update (UI, animations that should be smooth)
                self._update(frame_time)

                # 6. Render at display framerate, interpolating between the
                # last two fixed steps.
                self._render()
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            self.logger.info("KeyboardInterrupt received. Stopping.")
        except Exception as error:
            # Log unexpected crashes before shutting down. Bare `raise` rather
            # than `raise error`, which would append this frame to the
            # traceback and obscure the original site.
            self.logger.critical(
                f"Uncaught exception in game loop: {error}", exc_info=True
            )
            raise
        finally:
            # CRITICAL: This ensures cleanup happens even if sys.exit() is called
            self.shutdown()

    def start_recording(self, seed: int | None = None, description: str = "") -> int:
        """Start recording input for a deterministic replay.

        Args:
            seed: Random seed to record alongside the session. Generates one if
                not provided.
            description: Optional human-readable description for the replay.

        Returns:
            The seed used for this recording.

        Raises:
            RuntimeError: If a replay is currently being played back.
        """
        if self._replay_player is not None:
            raise RuntimeError("Cannot record while a replay is playing back")

        current_scene = self._scene_manager.current_scene
        scene_name = current_scene.name if current_scene is not None else ""

        self._replay_recorder = ReplayRecorder()
        seed_used = self._replay_recorder.start_recording(
            seed=seed, scene_name=scene_name, description=description
        )
        self._input_manager.attach_recorder(self._replay_recorder)
        self._replay_frame_id = 0
        self._replay_clock = 0.0
        return seed_used

    def stop_recording(self) -> ReplayData | None:
        """Stop recording and return the captured replay data.

        Returns:
            The recorded replay data, or None if nothing was recording.
        """
        if self._replay_recorder is None:
            return None

        data = self._replay_recorder.stop_recording()
        self._input_manager.detach_recorder()
        self._replay_recorder = None
        return data

    def save_recording(
        self, data: ReplayData, path: str, compress: bool = True
    ) -> bool:
        """Save replay data to disk via `ReplaySerializer`.

        Args:
            data: Replay data, e.g. from `stop_recording()`.
            path: File path to save to.
            compress: Whether to gzip-compress the file.

        Returns:
            True if the save succeeded.
        """
        return self._replay_serializer.save(data, path, compress=compress)

    def load_replay(self, path: str) -> bool:
        """Load a saved replay from disk and start driving input from it.

        Args:
            path: File path to load, as saved by `save_recording()`.

        Returns:
            True if the replay was loaded and playback started.

        Raises:
            RuntimeError: If currently recording.
        """
        if self._replay_recorder is not None:
            raise RuntimeError("Cannot play back a replay while recording")

        data = self._replay_serializer.load(path)
        if data is None:
            return False

        self._replay_player = ReplayPlayer(data)
        self._replay_player.start_playback()
        self._replay_frame_id = 0
        return True

    def _begin_replay_frame(self, frame_time: float) -> None:
        """Open a recorder frame, if one is active. Call before polling input."""
        if self._replay_recorder is not None and self._replay_recorder.is_recording:
            self._replay_recorder.begin_frame(
                self._replay_frame_id, self._replay_clock, frame_time
            )

    def _end_replay_frame(self, frame_time: float) -> None:
        """Close the recorder frame and drive playback. Call after polling input."""
        if self._replay_recorder is not None and self._replay_recorder.is_recording:
            self._replay_recorder.end_frame()
            self._replay_clock += frame_time
            self._replay_frame_id += 1

        if self._replay_player is not None and self._replay_player.is_playing:
            frame = self._replay_player.advance_frame()
            if frame is not None:
                for recorded_event in frame.events:
                    self._input_manager.process_replayed_event(recorded_event)
            if self._replay_player.is_finished():
                self._replay_player = None

    def _process_input(self, frame_time: float) -> None:
        """Poll system events, or feed replayed ones when a replay is active.

        Args:
            frame_time: This frame's duration in seconds, recorded alongside
                the events when a replay is being captured.
        """
        self._begin_replay_frame(frame_time)

        # This call is CRITICAL. It keeps the OS window responsive.
        for event in self._window.poll_events():
            if hasattr(event, "type") and event.type == pygame.QUIT:
                self._is_running = False
                # Publish the close request so game code and tools can react
                # before shutdown() runs. QuitEvent had no publisher at all,
                # which left tools/event_monitor.py subscribed to something
                # that could never fire.
                self._event_dispatcher.dispatch(QuitEvent(source=self))

            # While a replay drives the game, real input is swallowed rather
            # than dispatched, so both runs see exactly the same events.
            if self._replay_player is None:
                self._input_manager.process_event(event)

        self._end_replay_frame(frame_time)

    def _fixed_update(self, fixed_dt: float) -> None:
        """Advance physics and deterministic game logic by one fixed step.

        May run several times in one frame, or none at all, depending on how
        much time the accumulator holds. Anything that must be reproducible --
        physics, AI decisions, collision response -- belongs here rather than
        in `_update()`.

        Args:
            fixed_dt: Fixed delta time in seconds, e.g. 1/60.
        """
        # Each scene owns and ticks its own SystemManager (Steering, AI,
        # AudioSource, Animation); there is no global one.
        self._scene_manager.fixed_update(fixed_dt)

    def _update(self, dt: float) -> None:
        """Advance everything that should track display framerate, once a frame.

        UI, tweens, particles, camera smoothing and coroutines belong here:
        they should look smooth rather than be reproducible.

        Args:
            dt: This frame's duration in seconds.
        """
        # Update UI at display framerate for smooth interactions
        self._ui_manager.update(dt)

        # Update coroutines (scripted sequences)
        self._coroutine_manager.update(dt)

        # Variable-rate scene update (animations, camera, etc.)
        self._scene_manager.update(dt)

    def _render(self) -> None:
        """Draw one frame through whichever pipeline the backend provides.

        Computes `alpha` -- how far this frame sits between the last two fixed
        steps -- which `Transform.interpolate` entities use to avoid looking
        like they move at the physics rate.
        """
        alpha = self._accumulator / self._fixed_dt if self._fixed_dt > 0 else 0.0

        if self._render_graph is not None:
            self._render_with_graph(alpha)
        else:
            self._render_direct(alpha)

    def _render_direct(self, alpha: float) -> None:
        """Draw straight to the window, for backends with no render graph.

        Args:
            alpha: Interpolation factor between the last two fixed steps.
        """
        self._window.clear()
        self._scene_manager.render(self._world_renderer, self._ui_renderer, alpha)
        self._ui_manager.render(self._ui_renderer)
        self._ui_renderer.present()
        self._window.present()

    def _render_with_graph(self, alpha: float) -> None:
        """Draw through the multi-pass render graph (ModernGL backend).

        The world is drawn into an offscreen buffer, the final pass blits it to
        the screen, and UI is drawn on top.

        Args:
            alpha: Interpolation factor between the last two fixed steps.
        """
        if self._render_graph is None:
            return

        # Honour the configured clear colour, as the direct path does through
        # window.clear(). This used to be a hardcoded black, so
        # display.default_color silently did nothing under ModernGL.
        world_fbo = self._render_graph.fbo_manager.get_or_create("world")
        world_fbo.bind()
        world_fbo.clear(self._config_manager.config.display.default_color)

        # Render scenes to the world FBO
        self._scene_manager.render(self._world_renderer, self._ui_renderer, alpha)

        # Execute final pass to blit world FBO to screen
        final_pass = self._render_graph.get_pass("final")
        if final_pass is not None:
            final_pass.execute(self._render_graph.ctx, self._render_graph)

        # Render UI on top (directly to screen)
        self._ui_manager.render(self._ui_renderer)
        self._ui_renderer.present()

        # Present to display
        self._window.present()

    def shutdown(self) -> None:
        """Release every resource the application owns.

        Called automatically when `run()` returns, including on the exception
        path, and safe to call again afterwards.

        Each step is isolated: a failure in one is logged and the rest still
        run. Previously a raising `scene_manager.cleanup()` left the window
        open and the log manager running, which is precisely the situation --
        a crash -- where releasing them matters most.
        """
        if self._has_shut_down:
            return
        self._has_shut_down = True

        self.logger.info("Shutting down application")

        steps: list[tuple[str, Callable[[], None]]] = [
            ("scene cleanup", self._scene_manager.cleanup),
            ("audio shutdown", self._audio_system.shutdown),
            ("window close", self._window.close),
        ]
        if self._render_graph is not None:
            steps.insert(1, ("render graph release", self._render_graph.release))

        for name, step in steps:
            try:
                step()
            except Exception:
                self.logger.error(f"Error during {name}; continuing.", exc_info=True)

        # Last: it owns the logger everything above reports through.
        self._log_manager.shutdown()
