"""Reflection-based component editing for the selected entity.

Dispatches on each field's **runtime value type**, not its declared
annotation: component modules use `from __future__ import annotations`, so
`dataclasses.field.type` is the *string* `"Vector2"` rather than the class,
and a type-name lookup would either need a registry to keep in sync or
silently fall through to read-only for everything.

Two failure modes the previous editor shipped are handled here rather than
discovered at runtime:

- **Frozen components.** Its `_draw_dataclass` called `setattr`
  unconditionally, raising `FrozenInstanceError` on any `frozen=True`
  component. A frozen dataclass is drawn read-only, and says so.
- **Writes that nothing hears.** Mutating a component behind the
  `EntityManager`'s back leaves anything mirroring it -- physics bodies,
  render batches, the spatial index -- holding stale data. Every accepted
  edit ends with `notify_component_changed()`.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from imgui_bundle import imgui

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import Component
from pyguara.ecs.manager import EntityManager
from pyguara.editor.panels.base import EditorPanel, PanelContext


class InspectorPanel(EditorPanel):
    """Shows, and edits, the components of the selected entity."""

    def __init__(self, *, visible: bool = True) -> None:
        """Initialize the panel.

        Args:
            visible: Whether it draws from the first frame.
        """
        super().__init__("Inspector", visible=visible)

    def draw(self, context: PanelContext) -> None:
        """Draw the selected entity's components.

        Args:
            context: The world and selection to read.
        """
        imgui.begin(self.title)
        try:
            manager = context.entity_manager
            if manager is None:
                imgui.text_disabled("No active scene.")
                return

            entity_id = context.selection.entity_id
            if entity_id is None:
                imgui.text_disabled("Nothing selected.")
                return

            entity = manager.get_entity(entity_id)
            if entity is None:
                # Selected, then destroyed. Saying so beats an empty panel
                # that looks identical to "selected something with no
                # components".
                imgui.text_disabled(f"Entity '{entity_id}' no longer exists.")
                return

            imgui.text(entity_id)
            if entity.tags:
                imgui.text_disabled("tags: " + ", ".join(sorted(entity.tags)))
            imgui.separator()

            components = entity.get_all_components()
            if not components:
                imgui.text_disabled("No components.")
                return

            for component in sorted(components, key=lambda c: type(c).__name__):
                self._draw_component(manager, entity_id, component)
        finally:
            imgui.end()

    def _draw_component(
        self, manager: EntityManager, entity_id: str, component: Component
    ) -> None:
        """Draw one component as a collapsible section of fields.

        Args:
            manager: The world, for change notification.
            entity_id: The owning entity.
            component: The component to draw.
        """
        component_type = type(component)
        name = component_type.__name__
        frozen = self._is_frozen(component)
        header = f"{name}  [frozen]" if frozen else name

        if not imgui.collapsing_header(header):
            return

        imgui.push_id(name)
        try:
            # Widened to `object` first: `is_dataclass` is a TypeGuard, and
            # narrowing the `Component` protocol through it leaves mypy with
            # an empty intersection, so it calls the rest of this block
            # unreachable.
            instance: object = component
            if not dataclasses.is_dataclass(instance):
                # Not every component is a dataclass; there is nothing to
                # reflect over, so show the value rather than nothing.
                imgui.text_disabled(repr(component))
                return

            fields = dataclasses.fields(instance)
            if not fields:
                imgui.text_disabled("No fields.")
                return

            for field in fields:
                value = getattr(component, field.name, None)
                changed, new_value = self._draw_field(
                    field.name, value, read_only=frozen
                )
                if changed:
                    setattr(component, field.name, new_value)
                    manager.notify_component_changed(entity_id, component_type)
        finally:
            imgui.pop_id()

    @staticmethod
    def _is_frozen(component: Component) -> bool:
        """Whether `component` is a frozen dataclass.

        Args:
            component: The component to test.

        Returns:
            True if assignment to its fields would raise.
        """
        params = getattr(type(component), "__dataclass_params__", None)
        return bool(getattr(params, "frozen", False))

    def _draw_field(
        self, label: str, value: Any, *, read_only: bool
    ) -> tuple[bool, Any]:
        """Draw one field, returning whether it changed and its new value.

        Dispatch is on `type(value)` exactly -- not `isinstance` -- for
        `bool`/`int`, because `bool` is a subclass of `int` and an
        `isinstance(value, int)` arm would draw every checkbox as a number
        field.

        Args:
            label: The field name.
            value: Its current value.
            read_only: Draw it without editing.

        Returns:
            `(changed, new_value)`. `new_value` is `value` when unchanged.
        """
        if read_only or not self._is_editable(value):
            imgui.text_disabled(f"{label}: {value!r}")
            return False, value

        # Each arm binds its own names: ImGui returns `(changed, value)`
        # with a different value type per widget, and reusing one pair
        # would pin it to whichever came first.
        if type(value) is bool:
            bool_changed, bool_value = imgui.checkbox(label, value)
            return bool_changed, bool_value

        if type(value) is int:
            int_changed, int_value = imgui.input_int(label, value)
            return int_changed, int_value

        if type(value) is float:
            float_changed, float_value = imgui.drag_float(label, value)
            return float_changed, float_value

        if type(value) is str:
            str_changed, str_value = imgui.input_text(label, value)
            return str_changed, str_value

        if isinstance(value, Vector2):
            # Vector2 subclasses pymunk's immutable Vec2d, so an edit
            # replaces the whole value rather than assigning to .x/.y.
            vec_changed, vec_value = imgui.drag_float2(label, [value.x, value.y])
            if not vec_changed:
                return False, value
            return True, Vector2(vec_value[0], vec_value[1])

        if isinstance(value, Color):
            col_changed, col_value = imgui.color_edit4(
                label,
                [value.r / 255.0, value.g / 255.0, value.b / 255.0, value.a / 255.0],
            )
            if not col_changed:
                return False, value
            return True, Color(
                int(round(col_value[0] * 255)),
                int(round(col_value[1] * 255)),
                int(round(col_value[2] * 255)),
                int(round(col_value[3] * 255)),
            )

        # _is_editable gates every arm above, so this is unreachable.
        imgui.text_disabled(f"{label}: {value!r}")
        return False, value

    @staticmethod
    def _is_editable(value: Any) -> bool:
        """Whether `_draw_field` has an editor for this value.

        Args:
            value: The value to test.

        Returns:
            True if an editing widget exists for it.
        """
        return type(value) in (bool, int, float, str) or isinstance(
            value, Vector2 | Color
        )
