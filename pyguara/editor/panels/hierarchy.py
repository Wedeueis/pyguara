"""Hierarchy Panel for the Editor."""

from typing import Optional, Callable

try:
    import imgui  #
except ImportError:
    imgui = None

from pyguara.ecs.manager import EntityManager
from pyguara.ecs.entity import Entity
from pyguara.common.components import Tag


class HierarchyPanel:
    """Displays a list of all entities in the scene."""

    def __init__(self, manager_provider: Callable[[], Optional[EntityManager]]) -> None:
        """
        Initialize the Hierarchical Panel.

        Args:
            manager_provider: A function that returns the current EntityManager.
                              (Because scenes change, we can't store a static reference).
        """
        self._provider = manager_provider
        self.selected_entity: Optional[Entity] = None

    def render(self) -> None:
        """Draw the panel."""
        if not imgui:
            return

        imgui.begin("Hierarchy", True)

        manager = self._provider()
        if not manager:
            imgui.text("No Active Scene/Manager")
            imgui.end()
            return

        # List Entities
        # We convert to list to avoid runtime modification issues during iteration
        entities = list(manager.get_all_entities())

        for entity in entities:
            # Determine display name
            label = f"{entity.id[:8]}"

            # Check for Tag component
            if entity.has_component(Tag):
                tag = entity.get_component(Tag)
                label = f"{tag.name} ({label})"

            flags = imgui.SELECTABLE_NONE
            if self.selected_entity and self.selected_entity.id == entity.id:
                flags = imgui.SELECTABLE_SELECTED

            clicked, _ = imgui.selectable(label, (flags & imgui.SELECTABLE_SELECTED))

            if clicked:
                self.selected_entity = entity

        imgui.end()
