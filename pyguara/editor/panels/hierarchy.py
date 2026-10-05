"""The entity tree, over the ECS parent/child relation.

Reads `EntityManager.parent_of()` / `children_of()` rather than keeping its
own tree, so reparenting in game code shows up here on the next frame with
no synchronisation step to get wrong.
"""

from __future__ import annotations

from imgui_bundle import imgui

from pyguara.ecs.manager import EntityManager
from pyguara.editor.panels.base import EditorPanel, PanelContext

# A tree rooted deeper than this is almost certainly a cycle (`set_parent`
# rejects the ones it can see, but an id whose parent was reparented
# underneath it can still close a loop). Bailing beats recursing until
# Python's own stack limit takes the window with it.
_MAX_DEPTH = 64


class HierarchyPanel(EditorPanel):
    """Lists the active scene's entities as a selectable tree."""

    def __init__(self, *, visible: bool = True) -> None:
        """Initialize the panel.

        Args:
            visible: Whether it draws from the first frame.
        """
        super().__init__("Hierarchy", visible=visible)

    def draw(self, context: PanelContext) -> None:
        """Draw the entity tree, writing clicks into the selection.

        Args:
            context: The world and selection to read.
        """
        imgui.begin(self.title)
        try:
            manager = context.entity_manager
            if manager is None:
                imgui.text_disabled("No active scene.")
                return

            roots = self._roots(manager)
            imgui.text_disabled(f"{len(roots)} root / {self._total(manager)} total")
            imgui.separator()

            if not roots:
                imgui.text_disabled("No entities.")
                return

            for entity_id in roots:
                self._draw_node(manager, context, entity_id, depth=0)
        finally:
            # Dear ImGui pairs Begin/End unconditionally -- End is owed even
            # when the window is collapsed or an early return skipped the
            # body, so it goes in a finally rather than after each branch.
            imgui.end()

    def _roots(self, manager: EntityManager) -> list[str]:
        """Return the ids with no parent, in a stable order.

        Args:
            manager: The world to read.

        Returns:
            Sorted root entity ids.
        """
        return sorted(
            entity.id
            for entity in manager.get_all_entities()
            if manager.parent_of(entity.id) is None
        )

    def _total(self, manager: EntityManager) -> int:
        """Return how many entities the world holds.

        Args:
            manager: The world to read.

        Returns:
            The entity count.
        """
        return sum(1 for _ in manager.get_all_entities())

    def _draw_node(
        self,
        manager: EntityManager,
        context: PanelContext,
        entity_id: str,
        *,
        depth: int,
    ) -> None:
        """Draw one entity and, if open, its children.

        Args:
            manager: The world to read.
            context: Carries the selection this node may set.
            entity_id: The entity to draw.
            depth: Current recursion depth, against `_MAX_DEPTH`.
        """
        if depth >= _MAX_DEPTH:
            imgui.text_disabled(f"...depth limit at {entity_id}")
            return

        entity = manager.get_entity(entity_id)
        if entity is None:
            # Removed between building the id list and drawing it.
            return

        children = sorted(manager.children_of(entity_id))
        flags = (
            imgui.TreeNodeFlags_.open_on_arrow.value
            | imgui.TreeNodeFlags_.span_avail_width.value
        )
        if not children:
            flags |= imgui.TreeNodeFlags_.leaf.value
        if context.selection.is_selected(entity_id):
            flags |= imgui.TreeNodeFlags_.selected.value

        enabled = manager.is_entity_enabled(entity_id)
        component_count = len(entity.get_all_components())
        label = f"{entity_id}  ({component_count})"
        if not enabled:
            label = f"{label}  [disabled]"

        # push_id keeps two entities with the same label from sharing one
        # ImGui id, which would make them open and select as a single node.
        imgui.push_id(entity_id)
        try:
            opened = imgui.tree_node_ex(label, flags)
            # Selection on click, not on open: clicking the arrow toggles the
            # node, clicking the label selects it.
            if imgui.is_item_clicked() and not imgui.is_item_toggled_open():
                context.selection.select(entity_id)
            if opened:
                try:
                    for child_id in children:
                        self._draw_node(manager, context, child_id, depth=depth + 1)
                finally:
                    # Only an open node pushed onto the tree stack, and only
                    # because `no_tree_push_on_open` is not set.
                    imgui.tree_pop()
        finally:
            imgui.pop_id()
