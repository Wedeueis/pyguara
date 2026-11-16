"""The engine configuration, section by section, edited in place.

Every accepted edit becomes the `config` operation, so it lands on the
session's history and journal and obeys the approval mode, and a value
the configuration refuses is reported with the manager's own reason.

A widget is chosen from the setting's current value: a checkbox, a
number field, a text field, a colour picker, or a list of an enum's
members. A setting holding None, or pinned by an active profile, is
shown and not editable here.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from imgui_bundle import imgui

from pyguara.common.types import Color
from pyguara.studio.agent.journal import Actor
from pyguara.studio.model.values import encode
from pyguara.studio.panels.base import EditorPanel, PanelContext

FLOAT_DRAG_SPEED = 0.01
"""How far a float moves per pixel dragged. Ctrl+click types a value."""

_PINNED_COLOUR = (0.85, 0.75, 0.55, 1.0)


class ConfigPanel(EditorPanel):
    """Shows, edits and saves the engine configuration."""

    def __init__(self, attachment: Any, *, visible: bool = False) -> None:
        """Initialize the panel.

        Args:
            attachment: The `StudioAttachment` whose session and operation
                registry the edits go through. Held rather than unpacked
                because the session is replaced on a scene switch.
            visible: Whether it draws from the first frame.
        """
        super().__init__("Config", visible=visible)
        self._attachment = attachment
        self._filter = ""

    def draw(self, context: PanelContext) -> None:
        """Draw every section as a collapsible list of settings.

        Args:
            context: Unused: the configuration belongs to the engine, not
                to a scene.
        """
        imgui.begin(self.title)
        try:
            session = self._attachment.session
            manager = session.config_manager if session is not None else None
            if manager is None:
                imgui.text_disabled("No configuration to edit.")
                return

            if imgui.button("Save"):
                self.save()
            imgui.same_line()
            imgui.text_disabled(str(manager.file_path))
            active = manager.active_profiles
            if active:
                imgui.text_colored(
                    imgui.ImVec4(*_PINNED_COLOUR),
                    f"Active profiles: {', '.join(active)}",
                )

            imgui.set_next_item_width(-1)
            _, self._filter = imgui.input_text("##filter", self._filter)
            needle = self._filter.lower()

            for name, section in manager.config.sections():
                self._draw_section(manager, name, section, needle)
        finally:
            imgui.end()

    def _draw_section(self, manager: Any, name: str, section: Any, needle: str) -> None:
        """Draw one section's settings.

        Args:
            manager: The `ConfigManager`, to ask which settings are pinned.
            name: The section's name.
            section: The live section instance.
            needle: The lowered filter text; a setting is drawn when its
                name or its section's contains it.
        """
        fields = [
            field
            for field in dataclasses.fields(section)
            if not needle or needle in field.name.lower() or needle in name.lower()
        ]
        if not fields:
            return
        flags = imgui.TreeNodeFlags_.default_open.value if needle else 0
        if not imgui.collapsing_header(name, flags):
            return

        imgui.push_id(name)
        try:
            for field in fields:
                value = getattr(section, field.name)
                pinned_by = manager.pinned_by(name, field.name)
                if pinned_by is not None:
                    imgui.text_colored(
                        imgui.ImVec4(*_PINNED_COLOUR),
                        f"{field.name}: {value!r}   (set by profile '{pinned_by}')",
                    )
                    continue
                changed, new_value, gesture = self._draw_setting(field.name, value)
                if changed:
                    self.write(name, field.name, new_value, coalesce=gesture)
        finally:
            imgui.pop_id()

    def _draw_setting(self, label: str, value: Any) -> tuple[bool, Any, bool]:
        """Draw one setting's widget.

        Dispatch is on `type(value)` exactly for `bool` and `int`, because
        `bool` is a subclass of `int`.

        Args:
            label: The setting's name.
            value: Its current value.

        Returns:
            Whether it changed, the new value, and whether the change is
            one step of a continuous gesture that should fold into the
            previous history entry.
        """
        if type(value) is bool:
            bool_changed, bool_value = imgui.checkbox(label, value)
            return bool_changed, bool_value, False

        if type(value) is int:
            int_changed, int_value = imgui.input_int(label, value)
            return int_changed, int_value, False

        if type(value) is float:
            float_changed, float_value = imgui.drag_float(
                label, value, FLOAT_DRAG_SPEED, 0.0, 0.0, "%.4f"
            )
            return float_changed, float_value, True

        if type(value) is str:
            # Committed on Enter: a half-typed path is not a setting.
            str_changed, str_value = imgui.input_text(
                label, value, imgui.InputTextFlags_.enter_returns_true.value
            )
            return str_changed, str_value, False

        if isinstance(value, enum.Enum):
            return self._draw_enum(label, value)

        if isinstance(value, Color):
            col_changed, col_value = imgui.color_edit4(
                label,
                [value.r / 255.0, value.g / 255.0, value.b / 255.0, value.a / 255.0],
            )
            if not col_changed:
                return False, value, False
            return (
                True,
                Color(*(int(round(channel * 255)) for channel in col_value)),
                True,
            )

        imgui.text_disabled(f"{label}: {value!r}")
        return False, value, False

    @staticmethod
    def _draw_enum(label: str, value: enum.Enum) -> tuple[bool, Any, bool]:
        """Draw an enum setting as a list of its members.

        Args:
            label: The setting's name.
            value: The current member.

        Returns:
            Whether another member was picked, the member, and False.
        """
        members = list(type(value))
        changed, index = imgui.combo(
            label, members.index(value), [member.name for member in members]
        )
        if not changed:
            return False, value, False
        return True, members[index], False

    def write(
        self, section: str, setting: str, value: Any, *, coalesce: bool = False
    ) -> None:
        """Apply one accepted edit through the `config` operation.

        Args:
            section: The section's name.
            setting: The setting within it.
            value: Its new value.
            coalesce: Fold into the previous edit of the same setting.
        """
        result = self._invoke(
            {
                "operation": "set",
                "section": section,
                "setting": setting,
                "value": value.name if isinstance(value, enum.Enum) else encode(value),
                "coalesce": coalesce,
            }
        )
        if result is not None and not result.ok:
            self.report(f"{section}.{setting}: {result.error}")

    def save(self) -> None:
        """Write the configuration file, and say whether it worked."""
        result = self._invoke({"operation": "save"})
        if result is None:
            return
        if result.ok:
            self.report(f"Saved {result.result['saved']}", level="info")
        else:
            self.report(str(result.error))

    def _invoke(self, arguments: dict[str, Any]) -> Any:
        """Call the `config` operation as the person at the keyboard.

        Args:
            arguments: The operation's arguments.

        Returns:
            The `OperationResult`, or None when there is no session.
        """
        session = self._attachment.session
        if session is None:
            return None
        return self._attachment.operations.invoke(
            session, "config", arguments, actor=Actor.HUMAN
        )
