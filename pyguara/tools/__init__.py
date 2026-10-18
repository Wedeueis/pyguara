"""The runtime developer overlay: read-only diagnostics over a live game.

Drawn on the engine's own `UIRenderer`, so it works on every backend --
including the Pygame one, whose window is a software surface with no GL
context and which therefore cannot run the ImGui editor layer in
`pyguara.studio`. That is the whole reason this package still exists
beside Studio: the two are not two attempts at the same thing.

**It diagnoses; it does not author.** Everything here reports what the
running game is doing -- frame timing, the event stream, collision
shapes, the shortcut table. Selecting an entity, editing its components,
dragging a transform handle, editing the config and browsing resources
used to live here too, drawn with the same primitives; those went to
Studio, which has an undo stack, an audit journal and a scrolling,
dockable surface to put them on. See `docs/systems/editor.md`.
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
