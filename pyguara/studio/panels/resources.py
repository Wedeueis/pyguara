"""The project's assets: what is indexed, what is loaded, and what is in one.

Two scrolling lists share a filter. Selecting a row previews the
resource, and two buttons act on it: Spawn builds an entity from a data
file, and Reload re-reads a loaded resource from disk.

Everything the panel does is the `resources` operation, so a spawn is
on the session's history and journal and obeys the approval mode. The
listing is re-read every `REFRESH_FRAMES` frames and after each action.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from imgui_bundle import imgui

from pyguara.studio.agent.journal import Actor
from pyguara.studio.ops.resources import DATA_EXTENSIONS
from pyguara.studio.panels.base import EditorPanel, PanelContext

REFRESH_FRAMES = 30
"""How many frames one listing is shown for before it is read again."""

MAX_PREVIEW_CHARS = 4000
"""How much of a data file's contents the preview shows."""

LIST_HEIGHT = 220.0
"""The height of the two lists, in pixels; the preview takes the rest."""


class ResourcesPanel(EditorPanel):
    """Browses indexed and loaded resources, and spawns from data files."""

    def __init__(self, attachment: Any, *, visible: bool = False) -> None:
        """Initialize the panel.

        Args:
            attachment: The `StudioAttachment` whose session and operation
                registry the panel acts through. Held rather than unpacked
                because the session is replaced on a scene switch.
            visible: Whether it draws from the first frame.
        """
        super().__init__("Resources", visible=visible)
        self._attachment = attachment
        self._filter = ""
        self._listed_filter: str | None = None
        self._listing: dict[str, Any] | None = None
        self._frames_until_refresh = 0
        self._selected: str | None = None
        self._preview: dict[str, Any] | None = None

    @property
    def selected(self) -> str | None:
        """The path of the selected resource, or None."""
        return self._selected

    @property
    def preview(self) -> dict[str, Any] | None:
        """What `preview` reported for the selection, or None."""
        return self._preview

    def draw(self, context: PanelContext) -> None:
        """Draw the lists, the actions and the preview.

        Args:
            context: Unused: resources belong to the engine, not to a scene.
        """
        imgui.begin(self.title)
        try:
            listing = self._current_listing()
            if listing is None:
                imgui.text_disabled("No resource manager to browse.")
                return

            imgui.set_next_item_width(-1)
            _, self._filter = imgui.input_text("##filter", self._filter)

            if imgui.begin_child("resources", imgui.ImVec2(0, LIST_HEIGHT)):
                self._draw_loaded(listing["loaded"])
                self._draw_indexed(listing)
            imgui.end_child()

            imgui.separator()
            self._draw_selection(listing)
        finally:
            imgui.end()

    def select(self, path: str) -> None:
        """Select a resource and read its preview.

        Args:
            path: The resource's path.
        """
        self._selected = path
        result = self._invoke({"operation": "preview", "name": path})
        if result is None:
            self._preview = None
        elif result.ok:
            self._preview = result.result
        else:
            self._preview = {"path": path, "loaded": False, "error": result.error}

    def spawn(self) -> None:
        """Create an entity from the selected data file, and report it."""
        if self._selected is None:
            return
        result = self._invoke({"operation": "spawn", "name": self._selected})
        if result is None:
            return
        if not result.ok:
            self.report(str(result.error))
            return
        message = f"Spawned {result.result['entity_id']}"
        skipped = result.result["skipped"]
        if skipped:
            message += f" (not components: {', '.join(skipped)})"
        self.report(message, level="info")
        self._after_action()

    def reload(self) -> None:
        """Re-read the selected resource from disk, and report it."""
        if self._selected is None:
            return
        result = self._invoke({"operation": "reload", "name": self._selected})
        if result is None:
            return
        if result.ok:
            self.report(f"Reloaded {result.result['reloaded']}", level="info")
        else:
            self.report(str(result.error))
        self._after_action()

    def _after_action(self) -> None:
        """Read the listing and the preview again on the next frame."""
        self._frames_until_refresh = 0
        if self._selected is not None:
            self.select(self._selected)

    def _current_listing(self) -> dict[str, Any] | None:
        """Return the listing, reading it again when it is due.

        Returns:
            What `list` reported, or None when there is no session or no
            resource manager behind it.
        """
        session = self._attachment.session
        if session is None or session.resource_manager is None:
            self._listing = None
            return None

        due = self._frames_until_refresh <= 0 or self._listed_filter != self._filter
        if self._listing is None or due:
            result = self._invoke({"operation": "list", "filter": self._filter})
            self._listing = result.result if result is not None and result.ok else None
            self._listed_filter = self._filter
            self._frames_until_refresh = REFRESH_FRAMES
        self._frames_until_refresh -= 1
        return self._listing

    def _draw_loaded(self, loaded: list[dict[str, Any]]) -> None:
        """Draw the loaded resources as selectable rows.

        Args:
            loaded: The `loaded` entries of the listing.
        """
        flags = imgui.TreeNodeFlags_.default_open.value
        if not imgui.collapsing_header(f"Loaded ({len(loaded)})###loaded", flags):
            return
        if not loaded:
            imgui.text_disabled("Nothing is loaded.")
        for entry in loaded:
            label = f"{entry['type']}  {entry['path']}  ({entry['bytes']} B)"
            self._draw_row(f"{label}###loaded:{entry['path']}", entry["path"])

    def _draw_indexed(self, listing: dict[str, Any]) -> None:
        """Draw the indexed files as selectable rows.

        Args:
            listing: The whole listing, for the entries and the total.
        """
        indexed = listing["indexed"]
        total = listing["indexed_total"]
        flags = imgui.TreeNodeFlags_.default_open.value
        if not imgui.collapsing_header(f"Indexed ({total})###indexed", flags):
            return
        if not indexed:
            imgui.text_disabled("Nothing is indexed.")
        for entry in indexed:
            self._draw_row(f"{entry['path']}###indexed:{entry['path']}", entry["path"])
        if total > len(indexed):
            imgui.text_disabled(
                f"{total - len(indexed)} more. Type in the filter to narrow."
            )

    def _draw_row(self, label: str, path: str) -> None:
        """Draw one selectable row.

        Args:
            label: The row's text and ImGui id.
            path: The resource the row selects.
        """
        clicked, _ = imgui.selectable(label, path == self._selected)
        if clicked:
            self.select(path)

    def _draw_selection(self, listing: dict[str, Any]) -> None:
        """Draw the selected resource's actions and preview.

        Args:
            listing: The listing, to tell whether the selection is loaded.
        """
        path = self._selected
        if path is None:
            imgui.text_disabled("Select a resource to preview it.")
            return

        imgui.text(path)
        is_data = Path(path).suffix.lower() in DATA_EXTENSIONS
        is_loaded = any(entry["path"] == path for entry in listing["loaded"])

        imgui.begin_disabled(not is_data)
        if imgui.button("Spawn into Scene"):
            self.spawn()
        imgui.end_disabled()
        imgui.same_line()
        imgui.begin_disabled(not is_loaded)
        if imgui.button("Reload"):
            self.reload()
        imgui.end_disabled()

        for line in preview_lines(self._preview):
            imgui.text_wrapped(line)

    def _invoke(self, arguments: dict[str, Any]) -> Any:
        """Call the `resources` operation as the person at the keyboard.

        Args:
            arguments: The operation's arguments.

        Returns:
            The `OperationResult`, or None when there is no session.
        """
        session = self._attachment.session
        if session is None:
            return None
        return self._attachment.operations.invoke(
            session, "resources", arguments, actor=Actor.HUMAN
        )


def preview_lines(preview: dict[str, Any] | None) -> list[str]:
    """Turn a `preview` result into the lines the panel shows.

    Args:
        preview: What the operation reported, or None.

    Returns:
        The lines, with a data file's contents as indented JSON cut to
        `MAX_PREVIEW_CHARS`.
    """
    if preview is None:
        return []
    if "error" in preview:
        return [str(preview["error"])]
    if not preview.get("loaded"):
        return ["Not loaded."]

    lines = [f"{preview['type']}, {preview['bytes']} bytes"]
    if "data" in preview:
        text = json.dumps(preview["data"], indent=2)
        if len(text) > MAX_PREVIEW_CHARS:
            omitted = len(text) - MAX_PREVIEW_CHARS
            text = f"{text[:MAX_PREVIEW_CHARS]}\n... {omitted} more characters"
        lines.append(text)
    return lines
