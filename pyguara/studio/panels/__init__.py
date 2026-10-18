"""Studio's panels, over the ImGui layer this package also provides.

Three groups. `base` is the contract -- a panel is a pure function of the
world plus the selection -- and is the only module here that does not
import Dear ImGui. `hierarchy` and `inspector` read the scene. The rest
read session state: the edit history, the action journal with its
approval queue, the component schema browser, and the command palette,
which is a person calling the same operations an agent calls, through the
same registry.

The viewport lives in `pyguara.studio.viewport`, because it is a render
target and a picking surface before it is a panel.
"""

from pyguara.studio.panels.base import EditorPanel, PanelContext
from pyguara.studio.panels.hierarchy import HierarchyPanel
from pyguara.studio.panels.history import HistoryPanel
from pyguara.studio.panels.inspector import InspectorPanel
from pyguara.studio.panels.journal import JournalPanel
from pyguara.studio.panels.palette import CommandPalette
from pyguara.studio.panels.schema import SchemaPanel

__all__ = [
    "CommandPalette",
    "EditorPanel",
    "HierarchyPanel",
    "HistoryPanel",
    "InspectorPanel",
    "JournalPanel",
    "PanelContext",
    "SchemaPanel",
]
