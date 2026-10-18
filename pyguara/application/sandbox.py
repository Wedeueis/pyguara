"""An `Application` with the runtime developer overlay already installed.

The overlay is `pyguara/tools`: frame timing, the event stream, collision
wireframes and the shortcut table, drawn on the engine's own `UIRenderer`
so they work on every backend. It is a *diagnostic* surface.

**It is not the authoring surface, and does not try to be.** Selecting an
entity, editing its components, dragging a transform handle, editing the
config and browsing resources were registered here too, on F2/F5/F9/F6/F7.
They are gone: `pyguara.studio` does all of that with an undo stack, an
audit journal and a scrolling, dockable surface, and keeping a second,
weaker copy meant two ways to change the world, only one of which kept a
record. `attach_studio(app.container)` is the authoring answer, on the
ModernGL backend; this is what a running game gets on any backend.
"""

from pyguara.application.application import Application
from pyguara.di.container import DIContainer
from pyguara.events.lifecycle import QuitEvent
from pyguara.events.window import WindowResizeEvent
from pyguara.input import keys
from pyguara.tools.debugger import PhysicsDebugger
from pyguara.tools.event_monitor import EventMonitor
from pyguara.tools.manager import ToolManager
from pyguara.tools.performance import PerformanceMonitor
from pyguara.tools.shortcuts_panel import ShortcutsPanel


class SandboxApplication(Application):
    """An `Application` that runs the diagnostic overlay above the frame.

    Installs a `ToolManager` into the frame loop and gives it the event
    stream before the game sees it, so a tool can take a key the game
    also binds.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the sandbox application with tools enabled.

        Args:
            container: The dependency injection container.
        """
        super().__init__(container)
        self._tool_manager: ToolManager | None = None

        self.tools_logger = self._log_manager.get_logger("Sandbox")
        self.tools_logger.info("Sandbox Tools Initializing...")
        self._initialize_tools()

        # Edit an asset on disk, see it in the running game.
        self.enable_asset_hot_reload()

    def _initialize_tools(self) -> None:
        """Configure the tool manager and register all available tools."""
        self.logger.info("Initializing Developer Tools")

        self._tool_manager = ToolManager(self._container)
        # Registered so tools (e.g. ShortcutsPanel) can read the live shortcut
        # map instead of hard-coding a copy that drifts.
        self._container.register_instance(ToolManager, self._tool_manager)

        # The keys keep the numbers they have always had, with F2, F5,
        # F6, F7 and F9 now unbound rather than renumbered: those were the
        # inspector, the hierarchy, the config editor, the assets browser
        # and the gizmo, and a developer with the old mapping in their
        # fingers should find nothing there rather than something else.
        # `ShortcutsPanel` reads the live map, so the help overlay is
        # correct either way.

        # F1 - frame timing and counts.
        self._tool_manager.register_tool(PerformanceMonitor(self._container), keys.F1)

        # F3 - a rolling log of recent engine events.
        self._tool_manager.register_tool(EventMonitor(self._container), keys.F3)

        # F4 - collision shape wireframes.
        self._tool_manager.register_tool(PhysicsDebugger(self._container), keys.F4)

        # F8 - the help overlay, built from the map above.
        self._tool_manager.register_tool(ShortcutsPanel(self._container), keys.F8)

        # Enable global visibility by default in Sandbox mode
        self._tool_manager.toggle_global_visibility()

        self.logger.info("Tools loaded. Press F8 for help")

    def shutdown(self) -> None:
        """Tear tools down before the engine, then shut the engine down.

        `EventMonitor` and any custom tool that subscribed to the dispatcher
        must let go of it while it is still alive.
        """
        if self._tool_manager is not None:
            self._tool_manager.clear()
        super().shutdown()

    def _process_input(self, frame_time: float) -> None:
        """Process input events, prioritizing developer tools."""
        self._begin_replay_frame(frame_time)

        for event in self._window.poll_events():
            # 1. Update Internal State (Quit, resize)
            if isinstance(event, QuitEvent):
                self._is_running = False
                self._event_dispatcher.dispatch(QuitEvent(source=self))
                continue

            if isinstance(event, WindowResizeEvent):
                self._event_dispatcher.dispatch(event)
                continue

            # 2. Tool Manager (High Priority)
            if self._tool_manager and self._tool_manager.process_event(event):
                continue

            # 3. Game Input Manager (Normal Priority). While a replay drives
            # the game, real input is swallowed so both runs see the same
            # events (mirrors the base Application's behavior).
            if self._replay_player is None:
                self._input_manager.process_event(event)

        self._end_replay_frame(frame_time)

    def _fixed_update(self, fixed_dt: float) -> None:
        """Fixed-rate update for physics and game logic."""
        # 1. Standard Fixed Update (Physics, Game Logic)
        super()._fixed_update(fixed_dt)

        # Tools don't typically need fixed updates, but could be extended

    def _update(self, dt: float) -> None:
        """Variable-rate update for UI and tools."""
        # 1. Standard Game Update (Scenes, Animations)
        super()._update(dt)

        # 2. Update Tools (variable rate for smooth UI)
        if self._tool_manager:
            self._tool_manager.update(dt)

    def _render_overlays(self) -> None:
        """Draw the developer tool overlay above the game and its UI.

        This used to be a wholesale override of `_render()`, which restated
        the frame loop and in doing so dropped two things from every sandbox
        frame:

        - **The render graph.** It never executed a single pass, so on the
          ModernGL backend the sandbox skipped lighting, compositing,
          post-processing and the `final` blit -- `Application` and
          `SandboxApplication` disagreed about how a GL frame is drawn.
        - **The game's own UI.** It called `ToolManager.render()` but never
          `UIManager.render()`, so no game UI widget drew under the sandbox
          app at all.

        Overriding the overlay hook instead inherits whichever path the
        backend provides and adds only what the sandbox is actually for.
        """
        if self._tool_manager:
            self._tool_manager.render(self._ui_renderer)
