"""What has been done and who asked for it, plus the approval queue.

The panel a person watches while an agent works. Two things on it:

- **The journal**, newest last, with failures marked. An agent's mistakes
  sit in the record next to its successes, which is the point -- the
  question after forty edits is "what did it do, in order", and the undo
  stack cannot answer that because an undo *moves* the stack.
- **The approval queue**, when the session is in `ask` mode. Each entry
  carries the diff the edit would produce, so the decision is made
  against the consequence rather than the request.

The filters are the whole interface: an agent run produces a lot of
entries, and "show me only the failures" is how a person finds the moment
something went wrong without reading all of them.
"""

from __future__ import annotations

from imgui_bundle import imgui

from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.log import get_logger
from pyguara.studio.agent.journal import Actor, JournalEntry
from pyguara.studio.commands.base import EditError
from pyguara.studio.session import ApprovalMode, StudioSession

logger = get_logger(__name__)

_ACTOR_COLOURS: dict[Actor, tuple[float, float, float, float]] = {
    Actor.HUMAN: (0.75, 0.85, 1.0, 1.0),
    Actor.AGENT: (0.65, 1.0, 0.75, 1.0),
    Actor.SCRIPT: (1.0, 0.9, 0.6, 1.0),
    Actor.SYSTEM: (0.65, 0.65, 0.65, 1.0),
}
_FAILURE_COLOUR = (1.0, 0.45, 0.45, 1.0)

DEFAULT_VISIBLE_ENTRIES = 50
"""How many recent entries to show before the list is trimmed."""


class JournalPanel(EditorPanel):
    """Shows the action record, and any edits awaiting approval."""

    def __init__(self, session: StudioSession, *, visible: bool = True) -> None:
        """Initialize the panel.

        Args:
            session: The session whose journal to show.
            visible: Whether it draws from the first frame.
        """
        super().__init__("Journal", visible=visible)
        self._session = session
        self._failures_only = False
        self._visible_entries = DEFAULT_VISIBLE_ENTRIES
        self._reject_reason = ""

    def draw(self, context: PanelContext) -> None:
        """Draw the approval queue and the journal.

        Args:
            context: The world and selection to read. Unused: the journal
                belongs to the session, not the scene.
        """
        imgui.begin(self.title)
        try:
            self._draw_mode_selector()
            self._draw_pending()
            imgui.separator()
            self._draw_filters()
            self._draw_entries()
        finally:
            imgui.end()

    def _draw_mode_selector(self) -> None:
        """Draw the approval mode, and let it be changed."""
        current = self._session.approval_mode
        imgui.text("Approval")
        imgui.same_line()
        for mode in ApprovalMode:
            imgui.same_line()
            if imgui.radio_button(mode.value, current is mode):
                self._session.set_approval_mode(mode)
        if current is ApprovalMode.PLAN:
            imgui.text_disabled("Edits are described and nothing changes.")
        elif current is ApprovalMode.ASK:
            imgui.text_disabled("Edits wait for approval below.")

    def _draw_pending(self) -> None:
        """Draw each queued edit with the diff it would make."""
        pending = self._session.pending
        if not pending:
            return

        imgui.separator()
        imgui.text(f"{len(pending)} edit(s) awaiting approval")

        for entry in pending:
            imgui.push_id(entry.pending_id)
            try:
                if not imgui.collapsing_header(
                    f"{entry.label}  [{entry.actor.value}]",
                    imgui.TreeNodeFlags_.default_open.value,
                ):
                    continue

                self._draw_diff(entry.diff.to_dict())

                if imgui.button("Approve"):
                    self._approve(entry.pending_id)
                imgui.same_line()
                if imgui.button("Reject"):
                    self._reject(entry.pending_id)
                imgui.same_line()
                imgui.set_next_item_width(180)
                _, self._reject_reason = imgui.input_text("reason", self._reject_reason)
            finally:
                imgui.pop_id()

    def _draw_diff(self, diff: dict[str, object]) -> None:
        """Summarise a diff in a few lines.

        Not the whole structure: a reviewer needs to know what moved, and
        a wall of JSON is how a review becomes a rubber stamp.

        Args:
            diff: A `SceneDiff.to_dict()`.
        """
        if not diff.get("changed"):
            imgui.text_disabled("No change.")
            return

        for key in (
            "added",
            "removed",
            "tags_changed",
            "enabled_changed",
            "reparented",
        ):
            value = diff.get(key)
            if isinstance(value, list) and value:
                imgui.text_disabled(f"{key}: {', '.join(str(item) for item in value)}")

        for key in ("components_added", "components_removed"):
            entries = diff.get(key)
            if isinstance(entries, list) and entries:
                described = ", ".join(
                    f"{item.get('entity')}.{item.get('component')}"
                    for item in entries
                    if isinstance(item, dict)
                )
                imgui.text_disabled(f"{key}: {described}")

        fields = diff.get("fields")
        if isinstance(fields, list):
            for change in fields:
                if not isinstance(change, dict):
                    continue
                imgui.text_disabled(
                    f"{change.get('entity')}.{change.get('component')}."
                    f"{change.get('field')}: "
                    f"{change.get('before')} -> {change.get('after')}"
                )

    def _draw_filters(self) -> None:
        """Draw the journal's filters."""
        _, self._failures_only = imgui.checkbox("Failures only", self._failures_only)
        imgui.same_line()
        imgui.set_next_item_width(120)
        changed, count = imgui.drag_int("Show", self._visible_entries, 1.0, 5, 500)
        if changed:
            self._visible_entries = max(5, count)

    def _draw_entries(self) -> None:
        """Draw the journal entries, newest last."""
        journal = self._session.journal
        entries = (
            journal.failures()
            if self._failures_only
            else journal.tail(self._visible_entries)
        )

        if not entries:
            imgui.text_disabled(
                "No failures." if self._failures_only else "Nothing recorded."
            )
            return

        for entry in entries:
            self._draw_entry(entry)

    def _draw_entry(self, entry: JournalEntry) -> None:
        """Draw one entry, coloured by actor or by failure.

        Args:
            entry: The entry to draw.
        """
        colour = (
            _FAILURE_COLOUR
            if not entry.ok
            else _ACTOR_COLOURS.get(entry.actor, _ACTOR_COLOURS[Actor.SYSTEM])
        )
        marker = "x" if not entry.ok else "-"
        imgui.push_id(entry.sequence)
        try:
            imgui.text_colored(
                imgui.ImVec4(*colour),
                f"{marker} {entry.sequence:4} [{entry.actor.value}] {entry.action}",
            )
            if entry.error:
                imgui.same_line()
                imgui.text_colored(imgui.ImVec4(*_FAILURE_COLOUR), entry.error)
            elif entry.detail.get("label"):
                imgui.same_line()
                imgui.text_disabled(str(entry.detail["label"]))
        finally:
            imgui.pop_id()

    def _approve(self, pending_id: str) -> None:
        """Apply a queued edit, logging a refusal rather than raising.

        Args:
            pending_id: The edit to approve.
        """
        try:
            self._session.approve(pending_id)
        except EditError as exc:
            # The world can move between queueing and approval, in which
            # case the edit is refused -- which is the intended behaviour,
            # not an error to take the frame down with.
            logger.warning(f"Could not approve {pending_id}: {exc}")

    def _reject(self, pending_id: str) -> None:
        """Discard a queued edit.

        Args:
            pending_id: The edit to reject.
        """
        try:
            self._session.reject(pending_id, self._reject_reason)
            self._reject_reason = ""
        except EditError as exc:
            logger.warning(f"Could not reject {pending_id}: {exc}")
