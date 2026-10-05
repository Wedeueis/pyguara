"""The editor's panels."""

from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.editor.panels.hierarchy import HierarchyPanel
from pyguara.editor.panels.inspector import InspectorPanel

__all__ = [
    "EditorPanel",
    "HierarchyPanel",
    "InspectorPanel",
    "PanelContext",
]
