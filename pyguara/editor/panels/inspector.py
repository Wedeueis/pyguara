"""Inspector Panel module."""

from typing import Any, Optional, cast
import dataclasses

try:
    import imgui
except ImportError:
    imgui = None

from pyguara.ecs.entity import Entity
from pyguara.common.components import ResourceLink
from pyguara.resources.manager import ResourceManager
from pyguara.resources.data import DataResource
from pyguara.editor.drawers import InspectorDrawer


class InspectorPanel:
    """Displays and edits details of the selected entity."""

    def __init__(self, resource_manager: ResourceManager) -> None:
        """Initialize the inspector panel."""
        self.selected_entity: Optional[Entity] = None
        self._resource_manager = resource_manager

    def render(self) -> None:
        """Draw the panel."""
        if not imgui:
            return

        imgui.begin("Inspector")

        if not self.selected_entity:
            imgui.text("No entity selected.")
            imgui.end()
            return

        entity = self.selected_entity
        imgui.text(f"Entity ID: {entity.id}")

        # Source Linking Logic
        if entity.has_component(ResourceLink):
            link = entity.get_component(ResourceLink)
            imgui.text(f"Source: {link.resource_path}")
            if imgui.button("Save to Source Asset"):
                self._save_entity_to_source(entity, link.resource_path)

        imgui.separator()

        # Iterate through components
        # We assume entity.components is Dict[Type, Component]
        for comp_type, component in entity.components.items():
            if imgui.collapsing_header(
                comp_type.__name__, imgui.TREE_NODE_DEFAULT_OPEN
            ):
                InspectorDrawer.draw_component(component)

        imgui.end()

    def _save_entity_to_source(self, entity: Entity, path: str) -> None:
        """Update the source DataResource with current component values."""
        try:
            resource = self._resource_manager.load(path, DataResource)

            # Map components to dict
            new_data = {}
            for comp_type, comp in entity.components.items():
                if comp_type == ResourceLink:
                    continue

                if dataclasses.is_dataclass(comp):
                    comp_dict = dataclasses.asdict(cast(Any, comp))
                    new_data[comp_type.__name__] = comp_dict
                else:
                    pass

            resource._data.update(new_data)
            resource.save()
            print(f"[Editor] Updated source asset: {path}")
        except Exception as e:
            print(f"[Editor] Failed to save to source: {e}")
