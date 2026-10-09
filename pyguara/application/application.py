"""Main application runtime.

Implements a fixed timestep game loop for deterministic physics simulation.
The accumulator pattern decouples physics updates (fixed rate) from rendering
(display framerate), preventing tunneling and ensuring consistent behavior
regardless of frame rate variations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from pyguara.application.clock import Clock
from pyguara.audio.audio_system import IAudioSystem
from pyguara.config.manager import ConfigManager
from pyguara.dev.asset_reload import AssetReloadWatcher
from pyguara.di.container import DIContainer
from pyguara.di.exceptions import ServiceNotFoundException
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.lifecycle import ApplicationStartEvent, QuitEvent
from pyguara.events.resources import ResourceReloaded
from pyguara.events.window import WindowResizeEvent
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.window import Window
from pyguara.input.manager import InputManager
from pyguara.log.manager import LogManager
from pyguara.replay.player import ReplayPlayer
from pyguara.replay.recorder import ReplayRecorder
from pyguara.replay.serializer import ReplaySerializer
from pyguara.replay.types import ReplayData
from pyguara.resources.async_load import DEFAULT_PUMP_BUDGET_MS
from pyguara.resources.manager import ResourceManager
from pyguara.scene.base import Scene
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.ui.manager import UIManager

if TYPE_CHECKING:
    from pyguara.graphics.pipeline.graph import RenderGraph

# Event queue processing budget (milliseconds per frame)
DEFAULT_EVENT_QUEUE_TIME_BUDGET_MS = 5.0


@runtime_checkable
class EditorInputSink(Protocol):
    """Something that may consume an input event before the game sees it.

    Declared here, structurally, rather than importing `EditorLayer`:
    `pyguara/editor` is an optional dev surface that needs Dear ImGui, and
    the core runtime must import cleanly without it. `Protocol` over `ABC`
    for the usual reason in this codebase -- the editor does not have to
    know this type exists to satisfy it.
    """

    def process_event(self, event: object) -> bool:
        """Take one engine event and report whether it was consumed.

        Args:
            event: An engine event from `Window.poll_events()`.

        Returns:
            True when the implementation is using that input this frame, so
            the caller must not also route it to the game.
        """
        ...


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
        self._ui_manager.set_screen_size(self._window.width, self._window.height)
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

        self._clock: Clock = container.get(Clock)  # type: ignore[type-abstract]

        # Pumped each frame so queued asset loads finish a slice at a time
        # instead of stalling the frame they were requested on. Free when
        # nothing is queued -- `pump()` returns immediately on an empty
        # queue.
        self._resource_manager: ResourceManager = container.get(ResourceManager)
        self._resource_pump_budget_ms = DEFAULT_PUMP_BUDGET_MS

        # Fixed timestep accumulator
        self._accumulator = 0.0
        # All three are set for real in begin(), from config. `_fixed_dt`
        # being 0.0 until then is also what makes `step()` before `begin()`
        # a no-op rather than an infinite accumulator loop.
        self._fixed_dt = 0.0
        self._target_fps = 0
        self._max_frame_time = 0.0

        # Global time-scale and pause. Freely settable by game code at any
        # point; see _effective_time_scale() for how they combine, and
        # run()'s docstring for how they interact with fixed_dt and replay.
        self.time_scale: float = 1.0
        self.paused: bool = False

        # Replay recording/playback (mutually exclusive; see start_recording()/
        # load_replay()). Idle by default: near-zero overhead when neither is active.
        self._replay_serializer = ReplaySerializer()
        self._replay_recorder: ReplayRecorder | None = None
        self._replay_player: ReplayPlayer | None = None
        self._replay_frame_id = 0
        self._replay_clock = 0.0

        # Asset hot-reload (dev only). Idle unless enable_asset_hot_reload()
        # is called; SandboxApplication calls it automatically.
        self._asset_reload_watcher: AssetReloadWatcher | None = None

        # The editor layer, looked up once on first use. `attach_editor()`
        # runs after this constructor, so the lookup cannot happen here.
        self._editor_layer_checked = False
        self._editor_layer_cache: EditorInputSink | None = None

        self.logger.info("Application instance created.")

    @property
    def _editor_layer(self) -> EditorInputSink | None:
        """The attached editor layer, or None when none is attached.

        Resolved from the container on each access rather than cached in
        `__init__`, because `attach_editor()` runs *after* the application
        is built -- it needs the render graph the constructor resolves --
        so a value captured at construction time would always be None.

        The container lookup is a dict hit on a hot path (once per input
        event), which is why the result is cached for the frame by
        `_process_input`'s local rather than re-resolved per event.

        Returns:
            Something that can take an engine event and say whether it used
            it, or None.
        """
        if not self._editor_layer_checked:
            self._editor_layer_checked = True
            try:
                from pyguara.editor.layer import EditorLayer

                self._editor_layer_cache = cast(
                    "EditorInputSink | None", self._container.get(EditorLayer)
                )
            except Exception:
                # No editor attached, or ImGui is not installed. Both are
                # the normal case for a shipped game.
                self._editor_layer_cache = None
        return self._editor_layer_cache

    @property
    def container(self) -> DIContainer:
        """The service container this application was built on.

        `create_application()` builds the container itself, so without a
        public accessor anything that needs to resolve or register a
        service afterwards -- `pyguara.editor.attach_editor()`, a game's
        own systems -- has to reach for `app._container`.

        Returns:
            The DI container.
        """
        return self._container

    def enable_asset_hot_reload(self, poll_interval: float = 0.5) -> None:
        """Watch every loaded asset's file and re-import it on change.

        Development aid: edit a texture, tilemap or data file on disk and the
        running game picks it up. Reloads are applied on the main thread at
        frame start (see `_update()`), never from the watcher thread.

        Idempotent -- a second call is a no-op. There is no matching
        disable(); `shutdown()` stops the watcher.

        Args:
            poll_interval: Seconds between file-modification polls.
        """
        if self._asset_reload_watcher is not None:
            return
        resource_manager = self._container.get(ResourceManager)
        self._asset_reload_watcher = AssetReloadWatcher(
            resource_manager, poll_interval=poll_interval
        )
        self._asset_reload_watcher.start()
        self.logger.info("Asset hot-reload enabled")

    def run(self, starting_scene: Scene) -> None:
        """Execute the main game loop with a fixed timestep, until the window closes.

        A thin loop over `step()`, which is where a frame is actually
        defined; `begin()` does the one-time setup. Everything the loop
        does per frame is documented on `step()`.

        Dispatches `ApplicationStartEvent` before the first frame, and always
        calls `shutdown()` on the way out.

        Args:
            starting_scene: Scene to register and activate before the loop.

        Raises:
            ValueError: If `physics.fixed_timestep_hz` is not positive.
            Exception: Anything raised inside the loop, after logging it.
        """
        self.begin(starting_scene)

        try:
            while self.step():
                pass
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

    def begin(self, starting_scene: Scene) -> None:
        """Register and activate `starting_scene`, then arm the frame loop.

        Split out of `run()` so a frame can be driven from outside it --
        `step()` is unusable before this has run, because `_fixed_dt` is
        still `0.0` and no scene is active. A headless harness, a test, or
        PyGuara Studio's play-in-editor calls `begin()` then `step()`
        rather than monkeypatching `_render` and flipping `_is_running`,
        which is what every such caller in this repository had to do.

        Args:
            starting_scene: Scene to register and activate.

        Raises:
            ValueError: If `physics.fixed_timestep_hz` is not positive.
        """
        self.logger.info(f"Starting with scene: {starting_scene.name}")

        self._scene_manager.register(starting_scene)
        self._scene_manager.switch_to(starting_scene.name)

        self._is_running = True
        physics_config = self._config_manager.config.physics
        # Read once and held, not per frame: these three decide the shape of
        # every frame, and re-reading them mid-loop would let a config edit
        # change the timestep underneath the accumulator.
        self._target_fps = self._config_manager.config.display.fps_target
        self._fixed_dt = physics_config.fixed_dt  # also lets _render() get alpha
        self._max_frame_time = physics_config.max_frame_time

        self.logger.debug(
            f"Game loop: target_fps={self._target_fps}, "
            f"physics_hz={physics_config.fixed_timestep_hz}, "
            f"fixed_dt={self._fixed_dt}"
        )

        self._event_dispatcher.dispatch(ApplicationStartEvent(source=self))

    def step(self) -> bool:
        """Run exactly one frame, and report whether to run another.

        Each frame measures its own duration, clamps it to
        `physics.max_frame_time`, accumulates it, and runs as many fixed-rate
        updates as that buys before rendering once. Physics therefore behaves
        identically regardless of display framerate. While a replay loaded via
        `load_replay()` is driving the game, each frame's duration is taken from
        the recording instead, so a replay reproduces time-dependent state on
        any machine.

        `self.time_scale`/`self.paused` (see `_effective_time_scale()`) scale
        that measured duration before it reaches the accumulator and
        `_update()` -- not `fixed_dt` itself, which stays constant so physics
        step size and stability are unaffected; slow-mo means fewer fixed
        steps per real second, not smaller ones. Ignored entirely while a
        replay drives the game: `recorded_dt` already fixes exactly how much
        simulated time -- and therefore how many fixed steps -- the original
        recording session spent on that frame, and scaling it here would
        reproduce a different physics simulation than what was recorded.

        Exceptions propagate: `run()` owns the logging and the `shutdown()`,
        so a caller driving frames by hand decides for itself what a crash
        in frame N means.

        Returns:
            True while the loop should continue -- the app is running and the
            window is open. False once either stops being true, so
            `while app.step(): pass` terminates exactly where `run()` does.
            Also False when called before `begin()`.
        """
        if not (self._is_running and self._window.is_open):
            return False

        # 1. Measure frame time
        frame_time = self._clock.tick(self._target_fps) / 1000.0

        # Clamp frame time to prevent spiral of death
        # (when updates take longer than real time, causing ever-growing backlog)
        if frame_time > self._max_frame_time:
            frame_time = self._max_frame_time

        # While a replay drives the game, step the simulation by the
        # recorded per-frame delta instead of wall-clock time, so the
        # fixed-step count, tweens, particles and WaitForSeconds
        # reproduce. clock.tick() above still throttles rendering to the
        # display rate.
        is_replay_driven = False
        if self._replay_player is not None and self._replay_player.is_playing:
            is_replay_driven = True
            recorded_dt = self._replay_player.peek_delta()
            if recorded_dt is not None:
                frame_time = recorded_dt

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

        # 4. Accumulate time and run fixed updates. time_scale/paused
        # are ignored while a replay drives the game -- see step()'s
        # docstring for why scaling recorded_dt would desync physics
        # from what was actually recorded.
        simulated_time = (
            frame_time
            if is_replay_driven
            else frame_time * self._effective_time_scale()
        )
        # Delayed events run on the same scaled clock as physics,
        # so a pending `dispatch_after` waits out a pause instead of
        # firing into a frozen world.
        self._event_dispatcher.advance(simulated_time)

        self._accumulator += simulated_time

        while self._accumulator >= self._fixed_dt:
            # Fixed-rate update (physics, game logic)
            self._fixed_update(self._fixed_dt)
            self._accumulator -= self._fixed_dt

        # 5. Variable-rate update (UI, animations that should be smooth)
        self._update(simulated_time)

        # 6. Render at display framerate, interpolating between the
        # last two fixed steps.
        self._render()

        return self._is_running and self._window.is_open

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

        # poll_events() pumps the OS event queue (keeping the window
        # responsive) and hands back engine events, never raw SDL structs.
        for event in self._window.poll_events():
            if isinstance(event, QuitEvent):
                self._is_running = False
                # Re-publish with this app as the source so game code and
                # tools can react before shutdown() runs.
                self._event_dispatcher.dispatch(QuitEvent(source=self))
                continue

            if isinstance(event, WindowResizeEvent):
                # The window boundary is the only place a resize is detected;
                # nothing else could give WindowResizeEvent a publisher.
                self._event_dispatcher.dispatch(event)
                continue

            # The editor, when one is attached, gets first refusal. It
            # returns True for an event it is using -- the cursor is over a
            # panel, or a text field has focus -- and that event must not
            # also reach the game, or typing an entity name into the
            # Inspector would drive the player character at the same time.
            #
            # This routing is why the editor is usable at all: `attach_editor`
            # installs a render pass, so the panels drew from the first
            # frame, but nothing ever called `EditorLayer.process_event` and
            # every click fell through to the game.
            if self._editor_layer is not None and self._editor_layer.process_event(
                event
            ):
                continue

            # While a replay drives the game, real input is swallowed rather
            # than dispatched, so both runs see exactly the same events.
            if self._replay_player is None:
                self._input_manager.process_event(event)

        self._end_replay_frame(frame_time)

    def _effective_time_scale(self) -> float:
        """Return the scale actually applied to this frame's simulated time.

        `paused` takes priority over `time_scale` rather than the two being
        multiplied together: a game that sets `time_scale = 0.3` for a boss's
        slow-mo phase and then also pauses (menu opened on top) gets that 0.3
        back automatically on unpause, without having to save and restore it
        around the pause itself.

        Returns:
            0.0 if `self.paused`, otherwise `self.time_scale`.
        """
        return 0.0 if self.paused else self.time_scale

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

        # Lets a scripted sequence wait on the fixed step. The coroutine
        # manager itself is ticked from the variable-rate `_update`, so
        # without this signal `WaitForFixedUpdate` has nothing to watch and
        # a sequence cannot be synchronised with physics at all.
        self._coroutine_manager.notify_fixed_update()

    def _update(self, dt: float) -> None:
        """Advance everything that should track display framerate, once a frame.

        UI, tweens, particles, camera smoothing and coroutines belong here:
        they should look smooth rather than be reproducible.

        Args:
            dt: This frame's duration in seconds.
        """
        # Apply any pending asset hot-reloads (dev only; no-op when disabled).
        if self._asset_reload_watcher is not None:
            for key in self._asset_reload_watcher.drain():
                # `reload()` swaps the cache entry and leaves every holder of
                # the previous instance stale, so the swap has to be announced
                # or a hot-reloaded sprite changes nothing on screen.
                # `drain()` always returned these keys; nothing used them.
                self._event_dispatcher.dispatch(ResourceReloaded(key, source=self))

        # Finish a slice of any queued asynchronous loads. Device uploads
        # happen here because this is the thread that owns the context; the
        # decode half already ran on a worker for loaders that opted in.
        # See `pyguara/resources/async_load.py` for why it is split that way.
        self._resource_manager.pump(self._resource_pump_budget_ms)

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

    def _render_overlays(self) -> None:
        """Draw anything layered above the game's own UI.

        Nothing by default. The extension point exists so a subclass can add
        a layer *without* restating the frame loop: `SandboxApplication` used
        to override `_render()` wholesale to draw its tool overlay, and in
        doing so quietly dropped the render graph and the game's `UIManager`
        from every sandbox frame.

        Called after `UIManager.render()` and before `UIRenderer.present()`,
        on both the direct and the render-graph path, so an overlay sits on
        top of the game's UI and is still composited by the backend.
        """

    def _render_direct(self, alpha: float) -> None:
        """Draw straight to the window, for backends with no render graph.

        Args:
            alpha: Interpolation factor between the last two fixed steps.
        """
        self._window.clear()
        self._scene_manager.render(self._world_renderer, self._ui_renderer, alpha)
        self._ui_manager.render(self._ui_renderer)
        self._render_overlays()
        self._ui_renderer.present()
        self._window.present()

    def _render_with_graph(self, alpha: float) -> None:
        """Draw through the multi-pass render graph (ModernGL backend).

        The world is drawn into an offscreen buffer, every other registered
        pass then runs in registration order (light, composite,
        post-process, final -- whatever a bootstrap actually assembled),
        and UI is drawn on top.

        Before this, only the graph's `"final"` pass ever ran here -- a
        game whose graph had passes in between (lighting, post-processing)
        had to execute them itself, which every ModernGL demo in this repo
        (`true_coral`, `protocolo_bandeira`, `mourisco_ressonancia`) did,
        each hand-rolling the identical `for name in (...): pass.execute()`
        loop from its own scene code. That workaround still configures
        each pass's per-frame state (a camera, a set of lights) that only
        the scene knows -- this loop cannot invent that -- but the
        executing itself belongs here, once, not once per game.

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

        # Render scenes to the world FBO. `WorldPass` itself is not run:
        # its own camera-gated `Renderable` queue is a second, unrelated
        # drawing path (see its own docstring) that no current game
        # submits to -- every one of them draws immediately here instead,
        # which needs the "world" FBO bound first, exactly as above.
        # Re-bound before *each* stacked scene, not once: a scene below
        # may still execute a pass itself and leave its output bound.
        self._scene_manager.render(
            self._world_renderer, self._ui_renderer, alpha, before_each=world_fbo.bind
        )

        # Every other pass, in the order its bootstrap registered them --
        # light/composite/post-process (whichever exist) and finally
        # `"final"`, which blits the result to the screen.
        for render_pass in self._render_graph.passes:
            if render_pass.name == "world" or not render_pass.enabled:
                continue
            render_pass.execute(self._render_graph.ctx, self._render_graph)

        # Render UI on top (directly to screen)
        self._ui_manager.render(self._ui_renderer)
        self._render_overlays()
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
        if self._asset_reload_watcher is not None:
            steps.insert(0, ("asset hot-reload stop", self._asset_reload_watcher.stop))

        # Worker threads outlive the loop otherwise. Idempotent, and a no-op
        # when nothing ever loaded asynchronously.
        steps.insert(
            0, ("decode pool stop", self._resource_manager.shutdown_decode_pool)
        )
        if self._render_graph is not None:
            steps.insert(1, ("render graph release", self._render_graph.release))

        for name, step in steps:
            try:
                step()
            except Exception:
                self.logger.error(f"Error during {name}; continuing.", exc_info=True)

        # Last: it owns the logger everything above reports through.
        self._log_manager.shutdown()
