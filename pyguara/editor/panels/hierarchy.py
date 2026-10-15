"""The entity tree, over the ECS parent/child relation.

Reads `EntityManager.parent_of()` / `children_of()` rather than keeping its
own tree, so reparenting in game code shows up here on the next frame with
no synchronisation step to get wrong.

Two things a flat list of 252 entities needs, both taken from Godot's Scene
dock, where a real project lives with hundreds of nodes:

- **A filter.** Typing narrows the list to what is being worked on. It is
  the first thing in the dock there, and the reason a large scene is
  navigable at all.
- **Grouping.** Godot does not need it because a Godot scene *is* a tree:
  a level's tiles hang off a `TileMap`. An ECS scene has no such pressure,
  so a generated level arrives as hundreds of flat siblings -- `tile_0_0`
  through `tile_19_11` -- and the panel that lists them one per row is
  unreadable. Runs of siblings sharing a name prefix collapse into one
  foldable row.

The grouping is **display only**. No entity is named `tile`, nothing is
reparented, and the groups vanish the moment a filter matches across them.
Saying so matters: a row that looked like a parent but was not would be a
worse lie than the long list it replaced.

The panel reads and selects; it does not edit. Every change to the scene
goes through Studio's operations so that it lands on one history and in
one journal, and a panel in the base editor has no session to reach them
through.
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

GROUP_THRESHOLD = 4
"""How many siblings must share a prefix before they are folded away.

Three stragglers read better in place than behind a row that has to be
opened to see them; a dozen do not. Low enough that a level's tiles are
always folded, high enough that a handful of hand-named entities are not.
"""

_UNGROUPED = ""
"""The group key for an id that yields no prefix at all."""


class HierarchyPanel(EditorPanel):
    """Lists the active scene's entities as a selectable tree."""

    def __init__(self, *, visible: bool = True) -> None:
        """Initialize the panel.

        Args:
            visible: Whether it draws from the first frame.
        """
        super().__init__("Hierarchy", visible=visible)
        self._filter = ""
        # What was selected last frame. A selection made somewhere else --
        # clicking in the viewport, an agent's operation -- has to be
        # scrolled to, or the panel claims nothing is selected while the
        # row sits two hundred rows below the fold.
        self._last_selected: str | None = None
        self._reveal: str | None = None

    @property
    def filter_text(self) -> str:
        """The current filter, lowercased as it is matched."""
        return self._filter

    def set_filter(self, text: str) -> None:
        """Set the filter, as typing into the box does.

        Args:
            text: What to match ids against, case-insensitively.
        """
        self._filter = text

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

            self._note_foreign_selection(context)
            self._draw_filter()

            roots = self._roots(manager)
            shown = [entity_id for entity_id in roots if self._matches(entity_id)]
            self._draw_summary(len(shown), len(roots), self._total(manager))
            imgui.separator()

            if not roots:
                imgui.text_disabled("No entities.")
                return
            if not shown:
                imgui.text_disabled(f"Nothing matches '{self._filter}'.")
                return

            self._draw_siblings(manager, context, shown, depth=0)
        finally:
            # Dear ImGui pairs Begin/End unconditionally -- End is owed even
            # when the window is collapsed or an early return skipped the
            # body, so it goes in a finally rather than after each branch.
            imgui.end()

    # ----------------------------------------------------------------
    # Chrome
    # ----------------------------------------------------------------

    def _draw_filter(self) -> None:
        """Draw the filter box, and the button that clears it."""
        imgui.set_next_item_width(-60.0)
        changed, text = imgui.input_text_with_hint(
            "##filter", "Filter entities", self._filter
        )
        if changed:
            self._filter = text
        imgui.same_line()
        if imgui.button("Clear"):
            self._filter = ""

    def _draw_summary(self, shown: int, roots: int, total: int) -> None:
        """Describe what is on screen against what exists.

        Args:
            shown: Root entities passing the filter.
            roots: Root entities in all.
            total: Entities in the world, children included.
        """
        if self._filter:
            imgui.text_disabled(f"{shown} of {roots} root / {total} total")
            return
        imgui.text_disabled(f"{roots} root / {total} total")

    # ----------------------------------------------------------------
    # Grouping
    # ----------------------------------------------------------------

    def _draw_siblings(
        self,
        manager: EntityManager,
        context: PanelContext,
        ids: list[str],
        *,
        depth: int,
    ) -> None:
        """Draw one level of the tree, folding long same-prefix runs.

        Args:
            manager: The world to read.
            context: Carries the selection a click may set.
            ids: The sibling ids to draw, already filtered and sorted.
            depth: Current recursion depth, against `_MAX_DEPTH`.
        """
        for key, members in group_siblings(ids).items():
            if key == _UNGROUPED or len(members) < GROUP_THRESHOLD:
                for entity_id in members:
                    self._draw_node(manager, context, entity_id, depth=depth)
                continue
            self._draw_group(manager, context, key, members, depth=depth)

    def _draw_group(
        self,
        manager: EntityManager,
        context: PanelContext,
        key: str,
        members: list[str],
        *,
        depth: int,
    ) -> None:
        """Draw one folded run of siblings.

        Args:
            manager: The world to read.
            context: Carries the selection a click may set.
            key: The shared prefix, which is the group's label.
            members: The ids in it.
            depth: Current recursion depth.
        """
        # Opened while a filter is narrowing the list -- a group that had
        # to be opened by hand to see the three matches inside it would
        # make the filter useless -- and when the entity to reveal is in
        # it, so a viewport click scrolls to a row that is on screen.
        if self._filter or (self._reveal is not None and self._reveal in members):
            imgui.set_next_item_open(True)

        imgui.push_id(f"group::{key}")
        try:
            opened = imgui.tree_node_ex(
                f"{key}  ({len(members)})",
                imgui.TreeNodeFlags_.span_avail_width.value,
            )
            if imgui.is_item_hovered():
                imgui.set_tooltip(
                    f"{len(members)} entities whose names begin '{key}'.\n"
                    f"A grouping this panel draws, not a parent: no entity "
                    f"is named '{key}' and nothing was reparented."
                )
            if opened:
                try:
                    for entity_id in members:
                        self._draw_node(manager, context, entity_id, depth=depth)
                finally:
                    imgui.tree_pop()
        finally:
            imgui.pop_id()

    # ----------------------------------------------------------------
    # Rows
    # ----------------------------------------------------------------

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

    def _matches(self, entity_id: str) -> bool:
        """Whether `entity_id` passes the current filter.

        A root whose *child* matches is kept too, so filtering never hides
        a branch the match lives in.

        Args:
            entity_id: The id to test.

        Returns:
            True when it should be drawn.
        """
        if not self._filter:
            return True
        return self._filter.lower() in entity_id.lower()

    def _note_foreign_selection(self, context: PanelContext) -> None:
        """Record a selection made outside this panel, to scroll to it.

        Args:
            context: Carries the selection.
        """
        current = context.selection.entity_id
        self._reveal = current if current != self._last_selected else None
        self._last_selected = current

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
        selected = context.selection.is_selected(entity_id)
        if selected:
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
            if self._reveal == entity_id:
                # Centred rather than merely scrolled into view: a row that
                # lands against the top or bottom edge reads as "the list
                # happens to end here", not "this is the one".
                imgui.set_scroll_here_y(0.5)
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


def group_key(entity_id: str) -> str:
    """Return the name prefix `entity_id` would be grouped under.

    Everything up to the first segment that is a number: `tile_0_0` and
    `tile_19_11` are both `tile`, `collectible_18_10` is `collectible`,
    and `moving_platform` is itself. A generated level names its entities
    this way because the generator does, which is what makes the prefix a
    reliable stand-in for the parent the scene does not have.

    Args:
        entity_id: The entity's id.

    Returns:
        The prefix, or `""` for an id that is nothing but numbers.
    """
    segments = entity_id.split("_")
    kept: list[str] = []
    for segment in segments:
        if segment.isdigit():
            break
        kept.append(segment)
    if not kept:
        return _UNGROUPED
    if len(kept) == len(segments):
        # Nothing numeric at the end, so the whole name is its own key --
        # `player` groups with nothing, which is right.
        return entity_id
    return "_".join(kept)


def group_siblings(ids: list[str]) -> dict[str, list[str]]:
    """Group `ids` by their name prefix, preserving order.

    Args:
        ids: Sibling ids, already sorted.

    Returns:
        Prefix to the ids under it, in first-seen order.
    """
    groups: dict[str, list[str]] = {}
    for entity_id in ids:
        groups.setdefault(group_key(entity_id), []).append(entity_id)
    return groups
