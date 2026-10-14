"""Studio's menus.

Every editor has a menu bar, and the temptation is to write one that calls
into the editor's internals. This one does not: an entry that changes the
scene goes through the **operation registry**, the same surface an agent
drives over MCP or JSON lines. So a person choosing *Entity > Create
Empty* and an agent calling `create_entity` take the same path, land in
the same history, and appear the same way in the journal.

That has a consequence worth stating: the menus can only offer what the
operations offer. Where an entry is missing -- opening a scene, prefabs --
it is missing because the operation is, and the honest fix is to add the
operation rather than to reach around it from the UI.

The layout follows Godot and Unity where they agree, because a menu bar is
not the place to be original:

- **Scene** is Godot's name for Unity's File, and this is a scene editor.
- **Edit** carries undo and redo, as everywhere.
- **Entity** is this engine's word for Godot's Node and Unity's GameObject.
- **View** holds the panels and the layout.
- **Run** is the play controls, which Unity puts in a toolbar and Godot
  under Debug; here they are a menu because the toolbar is a panel.
- **Agent** has no equivalent in either, and is the point of Studio: the
  approval mode, the journal, and the commands that let an agent in.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from imgui_bundle import imgui

from pyguara.log import get_logger
from pyguara.studio.agent.journal import Actor

logger = get_logger(__name__)

DOCS_URL = "https://github.com/Wedeueis/pyguara/blob/main/docs/systems/studio.md"
"""Where *Help > Documentation* points. Copied to the clipboard rather
than opened: Studio has no business launching a browser, and on a headless
or remote display there may not be one."""

SPEED_PRESETS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0)
"""The time scales offered. Slow for watching a jump arc, fast for getting
through a level to the part being authored."""


class StudioMenus:
    """Builds Studio's menu bar over the operation registry."""

    def __init__(self, attachment: Any) -> None:
        """Initialize the menus.

        Args:
            attachment: The `StudioAttachment` they act on. Held rather
                than unpacked because the session is replaced on a scene
                switch, and a menu holding the old one would edit a world
                that is no longer on screen.
        """
        self._attachment = attachment
        self._about_open = False

    def menus(self) -> Sequence[tuple[str, Callable[[], None]]]:
        """Return the menus, in bar order.

        Returns:
            Each a title and something that draws its items.
        """
        return (
            ("Scene", self._scene_menu),
            ("Edit", self._edit_menu),
            ("Entity", self._entity_menu),
            ("View", self._view_menu),
            ("Run", self._run_menu),
            ("Agent", self._agent_menu),
            ("Help", self._help_menu),
        )

    def draw_overlays(self) -> None:
        """Draw anything a menu opened, such as the About window.

        A popup begun inside a menu closes with it, so a window that
        outlives the click is drawn from the frame instead.
        """
        if not self._about_open:
            return
        _, still_open = imgui.begin("About PyGuara Studio", self._about_open)
        self._about_open = bool(still_open)
        try:
            imgui.text("PyGuara Studio")
            imgui.text_disabled(_version())
            imgui.separator()
            imgui.text_wrapped(
                "A scene editor whose every edit is an operation, so a "
                "person and an agent change the scene the same way."
            )
            imgui.spacing()
            if imgui.button("Copy the documentation link"):
                imgui.set_clipboard_text(DOCS_URL)
        finally:
            imgui.end()

    # ----------------------------------------------------------------
    # The menus
    # ----------------------------------------------------------------

    def _scene_menu(self) -> None:
        """Scene: saving, opening, emptying, and leaving."""
        session = self._session()
        name = session.scene_name if session is not None else None
        imgui.text_disabled(name or "no scene open")
        imgui.separator()

        can_write = session is not None and session.scene_io is not None
        if imgui.menu_item("Save Scene", "Ctrl+S", False, can_write)[0]:
            self._invoke("scene", {"operation": "save"})

        if imgui.begin_menu("Open Scene", can_write):
            try:
                self._scene_items()
            finally:
                imgui.end_menu()

        if imgui.menu_item("New Scene", "", False, session is not None)[0]:
            self._invoke("scene", {"operation": "new"})

        imgui.separator()
        if imgui.menu_item_simple("Quit", "Alt+F4"):
            self._quit()

    def _scene_items(self) -> None:
        """List every saved scene as a menu entry."""
        result = self._invoke("scene", {"operation": "list"}, record=False)
        names = []
        if result is not None and isinstance(result.get("scenes"), list):
            names = [str(name) for name in result["scenes"]]
        if not names:
            imgui.text_disabled("nothing saved yet")
            return
        for name in names:
            if imgui.menu_item_simple(name):
                self._invoke("scene", {"operation": "open", "name": name})

    def _edit_menu(self) -> None:
        """Edit: the history, and acting on the selection."""
        session = self._session()
        stack = session.stack if session is not None else None
        can_undo = bool(stack and stack.can_undo)
        can_redo = bool(stack and stack.can_redo)

        if imgui.menu_item("Undo", "Ctrl+Z", False, can_undo)[0]:
            self._invoke("history", {"operation": "undo"})
        if imgui.menu_item("Redo", "Ctrl+Y", False, can_redo)[0]:
            self._invoke("history", {"operation": "redo"})
        imgui.separator()

        selected = self._selected_id()
        if imgui.menu_item("Duplicate", "Ctrl+D", False, selected is not None)[0]:
            self._invoke("duplicate_entity", {"entity_id": selected})
        if imgui.menu_item("Delete Entity", "Del", False, selected is not None)[0]:
            self._invoke("destroy_entity", {"entity_id": selected})
        if imgui.menu_item("Deselect", "Esc", False, selected is not None)[0]:
            self._selection().clear()

    def _entity_menu(self) -> None:
        """Entity: making one, and giving it components."""
        if imgui.menu_item_simple("Create Empty"):
            self._invoke("create_entity", {"entity_id": self._free_entity_id()})

        selected = self._selected_id()
        enabled = selected is not None
        if imgui.begin_menu("Add Component", enabled):
            try:
                self._component_items(selected)
            finally:
                imgui.end_menu()

        imgui.separator()
        if imgui.menu_item("Enable", "", False, enabled)[0]:
            self._invoke("set_enabled", {"entity_id": selected, "enabled": True})
        if imgui.menu_item("Disable", "", False, enabled)[0]:
            self._invoke("set_enabled", {"entity_id": selected, "enabled": False})

    def _component_items(self, entity_id: str | None) -> None:
        """List every attachable component as a menu entry.

        Args:
            entity_id: The entity to attach to.
        """
        result = self._invoke("list_components", {}, record=False)
        names = []
        if result is not None and isinstance(result.get("components"), list):
            names = [str(item.get("name", item)) for item in result["components"]]
        if not names:
            imgui.text_disabled("no components registered")
            return
        for name in names:
            if imgui.menu_item_simple(name):
                self._invoke(
                    "add_component", {"entity_id": entity_id, "component": name}
                )

    def _view_menu(self) -> None:
        """View: which panels are open, and where they sit."""
        self._attachment.layer.draw_panel_menu_items()
        imgui.separator()
        if imgui.menu_item_simple("Reset Layout"):
            self._reset_layout()

    def _run_menu(self) -> None:
        """Run: the same controls the Play panel carries."""
        play = self._play_panel()
        if play is None:
            imgui.text_disabled("no application attached")
            return

        label = "Resume" if play.paused else "Pause"
        if imgui.menu_item_simple(label, "F5"):
            play.toggle_pause()
        if imgui.menu_item("Step One Frame", "F10", False, play.paused)[0]:
            play.request_step()

        imgui.separator()
        application = self._application()
        current = getattr(application, "time_scale", 1.0) if application else 1.0
        for preset in SPEED_PRESETS:
            selected = abs(current - preset) < 1e-6
            if imgui.menu_item(f"{preset:g}x", "", selected, application is not None)[
                0
            ]:
                application.time_scale = preset

    def _agent_menu(self) -> None:
        """Agent: who may change the scene, and how one gets in."""
        from pyguara.studio.session import ApprovalMode

        session = self._session()
        mode = session.approval_mode if session is not None else None
        for candidate in ApprovalMode:
            selected = mode is candidate
            if imgui.menu_item(candidate.value, "", selected, session is not None)[0]:
                session.set_approval_mode(candidate)
        imgui.separator()

        pending = len(session.pending) if session is not None else 0
        if imgui.menu_item_simple(f"Approvals ({pending})"):
            self._show_panel("Journal")
        if imgui.menu_item_simple("Journal"):
            self._show_panel("Journal")
        if imgui.menu_item_simple("Command Palette"):
            self._show_panel("Commands")
        imgui.separator()

        if imgui.menu_item_simple("Copy `pyguara studio ops`"):
            imgui.set_clipboard_text("pyguara studio ops")
        if imgui.menu_item_simple("Copy `pyguara studio mcp`"):
            imgui.set_clipboard_text("pyguara studio mcp")

    def _help_menu(self) -> None:
        """Help: where to read more."""
        if imgui.menu_item_simple("Copy Documentation Link"):
            imgui.set_clipboard_text(DOCS_URL)
        if imgui.menu_item_simple("About"):
            self._about_open = True

    # ----------------------------------------------------------------
    # Reaching the things the menus act on
    # ----------------------------------------------------------------

    def _session(self) -> Any:
        """Return the live session, or None before a scene is open.

        Returns:
            The session, or None.
        """
        return self._attachment.session

    def _selection(self) -> Any:
        """Return the editor's selection.

        Returns:
            The shared selection object.
        """
        return self._attachment.layer.selection

    def _selected_id(self) -> str | None:
        """Return the primary selected entity's id.

        Returns:
            The id, or None when nothing is selected.
        """
        # `Selection.entity_id` is the accessor; there is no `primary`.
        # Guessing at the name meant this always returned None, which left
        # Delete, Duplicate and Add Component greyed out whatever was
        # selected -- a menu that is never enabled looks like one that does
        # not work.
        entity_id = self._selection().entity_id
        return str(entity_id) if entity_id is not None else None

    def _play_panel(self) -> Any:
        """Return the Play panel.

        Returns:
            The panel, or None when no application is attached.
        """
        return self._find_panel("Play")

    def _free_entity_id(self) -> str:
        """Return an entity id nothing holds.

        `create_entity` takes an id rather than minting one, so that undo
        and redo produce the same entity -- which means the menu has to
        pick one. Unity names it GameObject and Godot Node2D; here the
        word for the thing is entity.

        Returns:
            An unused id.
        """
        session = self._session()
        if session is None:
            return "entity"
        world = session.world
        index = 1
        while world.get_entity(f"entity_{index}") is not None:
            index += 1
        return f"entity_{index}"

    def _find_panel(self, title: str) -> Any:
        """Return the panel with `title`, or None.

        Args:
            title: The panel's title.
        """
        for panel in self._attachment.layer.panels:
            if panel.title == title:
                return panel
        return None

    def _show_panel(self, title: str) -> None:
        """Make the panel with `title` visible.

        Args:
            title: The panel's title.
        """
        panel = self._find_panel(title)
        if panel is not None and not panel.visible:
            panel.toggle()

    def _application(self) -> Any:
        """Return the running application.

        Returns:
            The application, or None.
        """
        return self._attachment._application()

    def _reset_layout(self) -> None:
        """Put every panel back where Studio opens it."""
        from pyguara.studio.attach import default_layout

        # Forced: this is the one action that is meant to discard both the
        # arrangement saved last session and whatever has been dragged
        # since. Everything else leaves them alone.
        self._attachment.layer.set_default_layout(default_layout(), force=True)
        self._attachment.layer.save_settings()

    def _quit(self) -> None:
        """Ask the application to shut down, as the close button does."""
        bar = self._attachment.layer.title_bar
        if bar is not None:
            bar.request_close()
            return
        # No bar of our own, so the operating system still draws one --
        # and the window is what knows how to ask for a shutdown.
        from pyguara.graphics.window import Window

        try:
            chrome = self._attachment.container.get(Window).chrome
        except Exception as exc:  # pragma: no cover - a hand-built container
            logger.debug(f"No window to close: {exc}")
            return
        if chrome is None:
            logger.info("This backend offers no way to ask the window to close.")
            return
        chrome.request_close()

    def _invoke(
        self, name: str, arguments: dict[str, Any], *, record: bool = True
    ) -> dict[str, Any] | None:
        """Run one operation as the human, and report a failure in the log.

        Args:
            name: The operation's name.
            arguments: Its arguments.
            record: Whether a failure is worth a log line. A menu that
                merely lists what is available asks every frame it is
                open, and a log line per frame is noise.

        Returns:
            The operation's payload, or None when it failed or there is
            no session.
        """
        session = self._session()
        if session is None:
            return None
        result = self._attachment.operations.invoke(
            session, name, arguments, actor=Actor.HUMAN
        )
        payload = result.to_dict()
        if not payload.get("ok", False):
            if record:
                # On screen, not only in the log. A menu item that closes
                # and does nothing is indistinguishable from one that is
                # broken, and the operation's error already names the
                # correction -- it just had nowhere to be read.
                error = str(payload.get("error") or "failed")
                logger.warning(f"Menu action '{name}' failed: {error}")
                self._attachment.layer.toasts.error(f"{name}: {error}")
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else payload


def _version() -> str:
    """Return the installed version, or a placeholder.

    Returns:
        A line for the About window.
    """
    try:
        from importlib.metadata import version

        return f"PyGuara {version('pyguara')}"
    except Exception:  # pragma: no cover - a source checkout without metadata
        return "PyGuara (source checkout)"
