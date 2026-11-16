"""The runtime developer overlay: read-only diagnostics over a live game.

Drawn on the engine's own `UIRenderer`, so it works on every backend,
including pygame, where the ImGui editor layer in `pyguara.studio`
cannot run.

It reports what the running game is doing: frame timing, the event
stream, collision shapes, the shortcut table. Authoring is Studio's.
See `docs/systems/editor.md`.
"""

from pyguara.tools.base import Tool
from pyguara.tools.debugger import PhysicsDebugger
from pyguara.tools.event_monitor import EventMonitor
from pyguara.tools.manager import ToolManager
from pyguara.tools.performance import PerformanceMonitor
from pyguara.tools.shortcuts_panel import ShortcutsPanel

__all__ = [
    "EventMonitor",
    "PerformanceMonitor",
    "PhysicsDebugger",
    "ShortcutsPanel",
    "Tool",
    "ToolManager",
]
