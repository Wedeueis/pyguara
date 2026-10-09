"""The command palette: a person calling the operations an agent calls.

The third front end onto `OperationRegistry`, and the reason the registry
exists rather than a pile of panel methods. A human filtering a list and
an agent choosing a tool are the same act over the same set, so they go
through the same code -- which also means an operation cannot be
available to one and missing from the other.

Arguments are typed as JSON rather than as generated widgets. A form built
from each operation's schema would be nicer for the common cases and
hopeless for the rest -- a nested dataclass, a list of vectors -- and the
JSON shape is the one the schema browser shows and the scene files use, so
it is a shape a user of this editor already reads. The result, including
the diff, is shown underneath.

Arguments the selection can supply are filled in: `entity_id` defaults to
the primary selection. That covers most of what a palette is used for
without pretending to generate a form.
"""

from __future__ import annotations

import json

from imgui_bundle import imgui

from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.studio.ops.registry import (
    OperationRegistry,
    OperationResult,
    RiskClass,
)
from pyguara.studio.session import StudioSession

_RISK_COLOURS: dict[RiskClass, tuple[float, float, float, float]] = {
    RiskClass.READ: (0.7, 0.85, 1.0, 1.0),
    RiskClass.EDIT: (0.75, 1.0, 0.75, 1.0),
    RiskClass.RUN: (1.0, 0.9, 0.6, 1.0),
    RiskClass.WRITE_DISK: (1.0, 0.75, 0.6, 1.0),
}
_ERROR_COLOUR = (1.0, 0.45, 0.45, 1.0)

MAX_RESULT_CHARS = 4000
"""How much of a result to show.

`scene_tree` on a real scene is far larger than a panel, and rendering all
of it costs a frame to produce something nobody reads.
"""


class CommandPalette(EditorPanel):
    """Filter, configure and run any Studio operation."""

    def __init__(
        self,
        session: StudioSession,
        registry: OperationRegistry,
        *,
        visible: bool = False,
    ) -> None:
        """Initialize the palette.

        Args:
            session: The session operations act on.
            registry: The operations to offer.
            visible: Whether it draws from the first frame. Hidden by
                default: it is summoned, not watched.
        """
        super().__init__("Commands", visible=visible)
        self._session = session
        self._registry = registry
        self._filter = ""
        self._selected: str | None = None
        self._arguments = "{}"
        self._result: OperationResult | None = None
        self._argument_error: str | None = None

    @property
    def selected(self) -> str | None:
        """The operation currently chosen, if any."""
        return self._selected

    def draw(self, context: PanelContext) -> None:
        """Draw the palette.

        Args:
            context: The world and selection, used to prefill arguments.
        """
        imgui.begin(self.title)
        try:
            imgui.set_next_item_width(-1)
            _, self._filter = imgui.input_text("##filter", self._filter)

            self._draw_list(context)
            if self._selected is not None:
                imgui.separator()
                self._draw_selected(context)
            self._draw_result()
        finally:
            imgui.end()

    def _draw_list(self, context: PanelContext) -> None:
        """Draw the filtered operation list.

        Args:
            context: The world and selection, for prefilling on select.
        """
        needle = self._filter.lower().replace(" ", "_")
        matches = [
            operation
            for operation in self._registry
            if not needle
            or needle in operation.name
            or needle in operation.summary.lower()
        ]

        if not matches:
            imgui.text_disabled(f"Nothing matches '{self._filter}'.")
            return

        if imgui.begin_child("operations", imgui.ImVec2(0, 180)):
            for operation in matches:
                imgui.push_id(operation.name)
                try:
                    clicked, _ = imgui.selectable(
                        operation.name, operation.name == self._selected
                    )
                    if clicked:
                        self._select(operation.name, context)
                    imgui.same_line()
                    imgui.text_colored(
                        imgui.ImVec4(*_RISK_COLOURS[operation.risk]),
                        operation.risk.value,
                    )
                    if imgui.is_item_hovered():
                        imgui.set_tooltip(operation.description)
                finally:
                    imgui.pop_id()
        imgui.end_child()

    def _draw_selected(self, context: PanelContext) -> None:
        """Draw the chosen operation's summary, arguments and run button.

        Args:
            context: The world and selection, for re-prefilling.
        """
        operation = self._registry.get(self._selected or "")
        if operation is None:
            # Removed between frames, which only a test does.
            self._selected = None
            return

        imgui.text_wrapped(operation.description)

        imgui.text("Arguments (JSON)")
        changed, text = imgui.input_text_multiline(
            "##arguments", self._arguments, imgui.ImVec2(-1, 90)
        )
        if changed:
            self._arguments = text
            self._argument_error = None

        if imgui.button("Run"):
            self._run()
        imgui.same_line()
        if imgui.button("Prefill from selection"):
            self._select(operation.name, context)
        imgui.same_line()
        properties = operation.parameters.get("properties", {})
        imgui.text_disabled(f"takes: {', '.join(sorted(properties)) or 'nothing'}")

        if self._argument_error:
            imgui.text_colored(imgui.ImVec4(*_ERROR_COLOUR), self._argument_error)

    def _draw_result(self) -> None:
        """Draw the last result, successful or not."""
        result = self._result
        if result is None:
            return

        imgui.separator()
        if not result.ok:
            imgui.text_colored(imgui.ImVec4(*_ERROR_COLOUR), "failed")
            imgui.text_wrapped(result.error or "")
            return

        imgui.text_disabled(f"{result.name} ok")
        rendered = self._render(result.result)
        imgui.input_text_multiline(
            "##result",
            rendered,
            imgui.ImVec2(-1, 160),
            imgui.InputTextFlags_.read_only.value,
        )

    def _select(self, name: str, context: PanelContext) -> None:
        """Choose an operation and prefill what the selection can supply.

        Args:
            name: The operation to select.
            context: The world and selection to read.
        """
        self._selected = name
        self._result = None
        self._argument_error = None

        operation = self._registry.get(name)
        if operation is None:  # pragma: no cover - called with a live name
            self._arguments = "{}"
            return

        prefilled: dict[str, object] = {}
        properties = operation.parameters.get("properties", {})
        entity_id = context.selection.entity_id
        if "entity_id" in properties and entity_id is not None:
            prefilled["entity_id"] = entity_id

        self._arguments = json.dumps(prefilled, indent=2)

    def _run(self) -> None:
        """Parse the arguments and invoke the operation.

        A JSON error is reported in the panel rather than sent to the
        registry, where it would come back as a less specific failure
        about the argument shape.
        """
        if self._selected is None:  # pragma: no cover - guarded by the caller
            return

        text = self._arguments.strip() or "{}"
        try:
            arguments = json.loads(text)
        except json.JSONDecodeError as exc:
            self._argument_error = f"Not valid JSON: {exc}"
            return

        if not isinstance(arguments, dict):
            self._argument_error = (
                f"Arguments must be a JSON object, got {type(arguments).__name__}."
            )
            return

        self._argument_error = None
        # Attributed to the session's current actor, which for a palette
        # click is the human at the keyboard.
        self._result = self._registry.invoke(
            self._session, self._selected, arguments, actor=self._session.actor
        )

    @staticmethod
    def _render(value: object) -> str:
        """Render a result as readable, bounded JSON.

        Args:
            value: The operation's return value.

        Returns:
            JSON text, truncated with a note when it is very large.
        """
        try:
            rendered = json.dumps(value, indent=2)
        except (TypeError, ValueError):  # pragma: no cover - ops encode already
            rendered = repr(value)

        if len(rendered) <= MAX_RESULT_CHARS:
            return rendered
        return (
            rendered[:MAX_RESULT_CHARS]
            + f"\n... truncated at {MAX_RESULT_CHARS} characters"
        )
