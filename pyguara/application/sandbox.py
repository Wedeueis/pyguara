"""
Sandbox application module.

This module provides a specialized Application subclass that comes pre-loaded
with the developer tool suite (Inspector, Debugger, Profiler, etc.).
It is intended for use during development and testing phases.
"""

from pyguara.application.application import Application
from pyguara.di.container import DIContainer
from pyguara.events.lifecycle import QuitEvent
from pyguara.events.window import WindowResizeEvent
from pyguara.input import keys
from pyguara.tools.assets_browser import AssetsTool
from pyguara.tools.config_inspector import ConfigInspector
from pyguara.tools.debugger import PhysicsDebugger
from pyguara.tools.event_monitor import EventMonitor
from pyguara.tools.gizmos import TransformGizmo
from pyguara.tools.hierarchy import HierarchyTool
from pyguara.tools.inspector import EntityInspector
from pyguara.tools.manager import ToolManager
from pyguara.tools.performance import PerformanceMonitor
from pyguara.tools.shortcuts_panel import ShortcutsPanel


class SandboxApplication(Application):
    """
    An extended Application that includes developer tools and overlays.

    This class injects the ToolManager into the main loop, allowing
    runtime inspection, debugging, and manipulation of the game state.
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

        # 1. Performance Monitor (F1) - FPS and Stats
        perf_monitor = PerformanceMonitor(self._container)
        self._tool_manager.register_tool(perf_monitor, keys.F1)

        # 2. Hierarchy (F5) - entity list + selection. Built before the
        #    inspector and gizmo, which both follow its selection.
        hierarchy = HierarchyTool(self._container)
        self._tool_manager.register_tool(hierarchy, keys.F5)

        # 3. Entity Inspector (F2) - inspects whatever the Hierarchy selects.
        inspector = EntityInspector(
            self._container, selection_provider=lambda: hierarchy.selected_entity
        )
        self._tool_manager.register_tool(inspector, keys.F2)

        # 3b. Transform Gizmo (F9) - visual handles for the selected entity.
        #     Q/W/E switch translate/rotate/scale. Follows the Hierarchy.
        gizmo = TransformGizmo(
            self._container, selection_provider=lambda: hierarchy.selected_entity
        )
        self._tool_manager.register_tool(gizmo, keys.F9)

        # 4. Event Monitor (F3) - Log Viewer
        event_mon = EventMonitor(self._container)
        self._tool_manager.register_tool(event_mon, keys.F3)

        # 5. Physics Debugger (F4) - Collision Wireframes
        debugger = PhysicsDebugger(self._container)
        self._tool_manager.register_tool(debugger, keys.F4)

        # 6. Config Inspector (F6) - Live GameConfig Editor
        config_inspector = ConfigInspector(self._container)
        self._tool_manager.register_tool(config_inspector, keys.F6)

        # 7. Assets Browser (F7) - resource list + spawn from data
        assets = AssetsTool(self._container)
        self._tool_manager.register_tool(assets, keys.F7)

        # 8. Shortcuts Panel (F8) - Help Overlay
        shortcuts = ShortcutsPanel(self._container)
        self._tool_manager.register_tool(shortcuts, keys.F8)

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

    def _render(self) -> None:
        """Render the game scene followed by tool overlays."""
        # 1. Clear Screen
        self._window.clear()

        # 2. Render Game Scene
        alpha = self._accumulator / self._fixed_dt if self._fixed_dt > 0 else 0.0
        if self._scene_manager:
            self._scene_manager.render(self._world_renderer, self._ui_renderer, alpha)

        # 3. Render Tools (On top of everything)
        if self._tool_manager:
            self._tool_manager.render(self._ui_renderer)

        # 4. Finalize UI (composites for GL backends)
        self._ui_renderer.present()

        # 5. Swap Buffers
        self._window.present()
