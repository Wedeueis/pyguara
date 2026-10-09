"""Studio's panels, over the ImGui layer the editor already provides.

The viewport lives in `pyguara.studio.viewport`; these are the ones that
read session state rather than the scene: the edit history, the action
journal with its approval queue, the component schema browser, and the
command palette -- which is a person calling the same operations an agent
calls, through the same registry.
"""

from pyguara.studio.panels.history import HistoryPanel
from pyguara.studio.panels.journal import JournalPanel
from pyguara.studio.panels.palette import CommandPalette
from pyguara.studio.panels.schema import SchemaPanel

__all__ = ["CommandPalette", "HistoryPanel", "JournalPanel", "SchemaPanel"]
