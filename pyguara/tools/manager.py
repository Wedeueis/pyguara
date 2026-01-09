"""Tool management system for coordinating developer tools."""

import pygame
from typing import Dict, List, Optional, Any

from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool


class ToolManager:
    """Orchestrates all developer tools.

    Manages initialization, updating, rendering, and input routing for
    registered tools. It also handles global shortcuts to toggle specific tools.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the tool manager.

        Args:
            container: The global dependency injection container.
        """
        self._container = container
        self._tools: Dict[str, Tool] = {}
        # Render order determines Z-index (last item is drawn on top)
        self._render_order: List[str] = []
        self._shortcuts: Dict[int, str] = {}
        self._is_globally_visible: bool = False

    def register_tool(self, tool: Tool, shortcut_key: Optional[int] = None) -> None:
        """Register a new tool with the manager.

        Args:
            tool: The tool instance to register.
            shortcut_key: Optional pygame key code to toggle this tool.
        """
        self._tools[tool.name] = tool
        self._render_order.append(tool.name)

        if shortcut_key:
            self._shortcuts[shortcut_key] = tool.name

        # By default, tools start hidden until the global toggle (F12) is active
        # or the specific tool is toggled.
        tool.hide()

        print(f"[ToolManager] Registered {tool.name} (Key: {shortcut_key})")

    def get_tool(self, name: str) -> Optional[Tool]:
        """Retrieve a registered tool by name.

        Args:
            name: The name of the tool.

        Returns:
            The tool instance or None if not found.
        """
        return self._tools.get(name)

    def update(self, dt: float) -> None:
        """Update all active tools.

        Args:
            dt: Delta time in seconds.
        """
        # Tools run even if UI is hidden, so they can track history/stats
        for name in self._render_order:
            tool = self._tools[name]
            if tool.is_active:
                tool.update(dt)

    def render(self, renderer: UIRenderer) -> None:
        """Render all visible tools.

        Args:
            renderer: The UI renderer backend.
        """
        if not self._is_globally_visible:
            return

        for name in self._render_order:
            tool = self._tools[name]
            if tool.is_visible:
                tool.render(renderer)

    def process_event(self, event: Any) -> bool:
        """Handle input events for tools and global shortcuts.

        This allows tools to intercept input (e.g., clicking a button in the
        debug panel shouldn't fire a gun in the game).

        Args:
            event: The raw input event.

        Returns:
            True if the event was consumed, False otherwise.
        """
        if event.type == pygame.KEYDOWN:
            # F12: Toggle Master Switch
            if event.key == pygame.K_F12:
                self.toggle_global_visibility()
                return True

            # Tool Specific Toggles (Only if master switch is ON)
            if self._is_globally_visible and event.key in self._shortcuts:
                tool_name = self._shortcuts[event.key]
                if tool := self._tools.get(tool_name):
                    tool.toggle()
                    print(f"[ToolManager] Toggled {tool_name}: {tool.is_visible}")
                    return True

        if not self._is_globally_visible:
            return False

        # Pass event to tools in reverse render order (top-most first)
        for name in reversed(self._render_order):
            tool = self._tools[name]
            if tool.is_active and tool.is_visible:
                if tool.process_event(event):
                    return True

        return False

    def toggle_global_visibility(self) -> None:
        """Toggle the visibility of the entire tool overlay."""
        self._is_globally_visible = not self._is_globally_visible

        # When turning on, ensure at least one tool is visible?
        # For now, we respect individual tool state.
        state = "Enabled" if self._is_globally_visible else "Disabled"
        print(f"[ToolManager] Global Overlay {state}")
