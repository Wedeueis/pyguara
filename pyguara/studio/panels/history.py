"""The edit history, as a list you can rewind to a point in.

What makes undo legible rather than a key you press hopefully. A stack of
labels tells you what you did; clicking one tells you where to go back to.
That second part -- "undo to here" -- is the reason the panel exists at
all, since a plain Ctrl-Z needs no window.

Entries are listed oldest-first so an index stays put as new edits arrive
at the end. A newest-first list renumbers everything on every edit, which
makes the row a user is reaching for move while they reach for it.
"""

from __future__ import annotations

from imgui_bundle import imgui

from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.log import get_logger
from pyguara.studio.commands.base import EditError
from pyguara.studio.session import StudioSession

logger = get_logger(__name__)


class HistoryPanel(EditorPanel):
    """Shows what has been done, and lets it be taken back."""

    def __init__(self, session: StudioSession, *, visible: bool = True) -> None:
        """Initialize the panel.

        Args:
            session: The session whose history to show.
            visible: Whether it draws from the first frame.
        """
        super().__init__("History", visible=visible)
        self._session = session

    def draw(self, context: PanelContext) -> None:
        """Draw the history.

        Args:
            context: The world and selection to read. Unused: the history
                belongs to the session, not the scene.
        """
        imgui.begin(self.title)
        try:
            self._draw_controls()
            imgui.separator()
            self._draw_entries()
        finally:
            # Dear ImGui owes an End for every Begin, collapsed or not.
            imgui.end()

    def _draw_controls(self) -> None:
        """Draw the undo and redo buttons, disabled when they would fail."""
        stack = self._session.stack

        imgui.begin_disabled(not stack.can_undo)
        if imgui.button("Undo"):
            self._session.undo()
        imgui.end_disabled()

        imgui.same_line()
        imgui.begin_disabled(not stack.can_redo)
        if imgui.button("Redo"):
            self._session.redo()
        imgui.end_disabled()

        imgui.same_line()
        imgui.text_disabled(
            f"{len(stack.undo_labels)} undoable / {len(stack.redo_labels)} redoable"
        )

    def _draw_entries(self) -> None:
        """Draw the undoable and redoable entries."""
        stack = self._session.stack
        undo_labels = stack.undo_labels

        if not undo_labels and not stack.redo_labels:
            imgui.text_disabled("Nothing has been edited yet.")
            return

        for index, label in enumerate(undo_labels):
            # push_id, because two identical labels would otherwise share
            # one ImGui id and clicking either would act on the first.
            imgui.push_id(index)
            try:
                if imgui.selectable(f"{index + 1}. {label}", False)[0]:
                    self._undo_to(index)
                if imgui.is_item_hovered():
                    imgui.set_tooltip(
                        f"Undo back to before this edit "
                        f"({len(undo_labels) - index} step(s))."
                    )
            finally:
                imgui.pop_id()

        for label in stack.redo_labels:
            imgui.text_disabled(f"  (undone) {label}")

    def _undo_to(self, index: int) -> None:
        """Rewind so that only the first `index` edits remain applied.

        Args:
            index: The row clicked, which becomes the first edit undone.
        """
        try:
            self._session.stack.undo_to(index)
        except (EditError, ValueError) as exc:
            # The history can move between the click and this call --
            # another panel, or an agent, may have undone something.
            logger.warning(f"Could not rewind the history: {exc}")
