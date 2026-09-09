"""Tool management system for coordinating developer tools."""

from typing import Any

from pyguara.di.container import DIContainer
from pyguara.events.input import KeyDownEvent
from pyguara.graphics.protocols import UIRenderer
from pyguara.input import keys
from pyguara.log import get_logger
from pyguara.tools.base import Tool

logger = get_logger(__name__)


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
        self._tools: dict[str, Tool] = {}
        # Render order determines Z-index (last item is drawn on top)
        self._render_order: list[str] = []
        self._shortcuts: dict[int, str] = {}
        self._is_globally_visible: bool = False

    def register_tool(self, tool: Tool, shortcut_key: int | None = None) -> None:
        """Register a new tool with the manager.

        Registering a name that is already taken *replaces* the old tool: its
        render-order slot and any shortcut it held are dropped first, so the
        replacement is not run twice per frame (a bare ``append`` used to
        leave a stale duplicate in the render order).

        Args:
            tool: The tool instance to register.
            shortcut_key: Optional pygame key code to toggle this tool.
        """
        if tool.name in self._tools:
            logger.debug("Replacing already-registered tool '%s'", tool.name)
            self._forget(tool.name)

        self._tools[tool.name] = tool
        self._render_order.append(tool.name)

        if shortcut_key is not None:
            self._shortcuts[shortcut_key] = tool.name

        # By default, tools start hidden until the global toggle (F12) is active
        # or the specific tool is toggled.
        tool.hide()

        logger.debug("Registered tool '%s' (Key: %s)", tool.name, shortcut_key)

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool, calling its :meth:`Tool.on_removed` hook.

        Drops the tool from the registry, the render order and any shortcut
        binding. Returns ``True`` if a tool by that name was found.
        """
        tool = self._tools.get(name)
        if tool is None:
            return False
        self._forget(name)
        tool.on_removed()
        logger.debug("Unregistered tool '%s'", name)
        return True

    def _forget(self, name: str) -> None:
        """Drop every reference to ``name`` from the manager's own bookkeeping.

        Does not touch the tool object itself (no ``on_removed`` call) -- that
        is ``unregister_tool``'s job; a replacing ``register_tool`` keeps the
        old instance alive on purpose.
        """
        self._tools.pop(name, None)
        self._render_order = [n for n in self._render_order if n != name]
        self._shortcuts = {k: v for k, v in self._shortcuts.items() if v != name}

    def iter_shortcuts(self) -> list[tuple[int, str]]:
        """Return the ``(key_code, tool_name)`` bindings, in key order."""
        return sorted(self._shortcuts.items())

    def clear(self) -> None:
        """Unregister every tool, firing each one's ``on_removed`` hook.

        Used on application shutdown so tools that subscribed to the event
        dispatcher let go of it before it is torn down.
        """
        for name in list(self._tools):
            self.unregister_tool(name)

    def get_tool(self, name: str) -> Tool | None:
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
            event: An engine input event (see `events/input.py`).

        Returns:
            True if the event was consumed, False otherwise.
        """
        if isinstance(event, KeyDownEvent):
            # F12: Toggle Master Switch
            if event.key_code == keys.F12:
                self.toggle_global_visibility()
                return True

            # Tool Specific Toggles (Only if master switch is ON)
            if self._is_globally_visible and event.key_code in self._shortcuts:
                tool_name = self._shortcuts[event.key_code]
                if tool := self._tools.get(tool_name):
                    tool.toggle()
                    logger.debug("Toggled tool '%s': %s", tool_name, tool.is_visible)
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
        logger.debug("Global overlay %s", state)
