"""
Sandbox application module.

This module provides a specialized Application subclass that comes pre-loaded
with the developer tool suite (Inspector, Debugger, Profiler, etc.).
It is intended for use during development and testing phases.
"""

import pygame
from typing import Optional

from pyguara.application.application import Application
from pyguara.di.container import DIContainer
from pyguara.tools.manager import ToolManager
from pyguara.tools.performance import PerformanceMonitor
from pyguara.tools.inspector import EntityInspector
from pyguara.tools.event_monitor import EventMonitor
from pyguara.tools.debugger import PhysicsDebugger
from pyguara.tools.shortcuts_panel import ShortcutsPanel
from pyguara.editor.layer import EditorTool


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
        self._tool_manager: Optional[ToolManager] = None
        self._initialize_tools()

    def _initialize_tools(self) -> None:
        """Configure the tool manager and register all available tools."""
        print("[Sandbox] Initializing Developer Tools...")

        self._tool_manager = ToolManager(self._container)

        # 1. Performance Monitor (F1) - FPS and Stats
        perf_monitor = PerformanceMonitor(self._container)
        self._tool_manager.register_tool(perf_monitor, pygame.K_F1)

        # 2. Entity Inspector (F2) - ECS Data Viewer
        inspector = EntityInspector(self._container)
        self._tool_manager.register_tool(inspector, pygame.K_F2)

        # 3. Event Monitor (F3) - Log Viewer
        event_mon = EventMonitor(self._container)
        self._tool_manager.register_tool(event_mon, pygame.K_F3)

        # 4. Physics Debugger (F4) - Collision Wireframes
        debugger = PhysicsDebugger(self._container)
        self._tool_manager.register_tool(debugger, pygame.K_F4)

        # 5. Robust Editor (F5) - ImGui Based
        editor_tool = EditorTool(self._container)
        self._tool_manager.register_tool(editor_tool, pygame.K_F5)

        # 6. Shortcuts Panel (F8) - Help Overlay
        shortcuts = ShortcutsPanel(self._container)
        self._tool_manager.register_tool(shortcuts, pygame.K_F8)

        # Enable global visibility by default in Sandbox mode
        self._tool_manager.toggle_global_visibility()

        print("[Sandbox] Tools loaded. Press F8 for help.")

    def _process_input(self) -> None:
        """Process input events, prioritizing developer tools."""
        # Poll events from the window backend
        events = self._window.poll_events()

        for event in events:
            # 1. Update Internal State (Quit, etc.)
            if hasattr(event, "type") and event.type == pygame.QUIT:
                self._is_running = False

            # 2. Tool Manager (High Priority)
            if self._tool_manager and self._tool_manager.process_event(event):
                continue

            # 3. Game Input Manager (Normal Priority)
            self._input_manager.process_event(event)

    def _update(self, dt: float) -> None:
        """Update game logic and tools."""
        # 1. Standard Game Update (Scenes, Systems)
        super()._update(dt)

        # 2. Update Tools
        if self._tool_manager:
            self._tool_manager.update(dt)

    def _render(self) -> None:
        """Render the game scene followed by tool overlays."""
        # 1. Clear Screen
        self._window.clear()

        # 2. Render Game Scene
        if self._scene_manager:
            self._scene_manager.render(self._world_renderer, self._ui_renderer)

        # 3. Render Tools (On top of everything)
        if self._tool_manager:
            self._tool_manager.render(self._ui_renderer)

        # 4. Swap Buffers
        self._window.present()
