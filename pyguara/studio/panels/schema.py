"""What components exist, and what each one's fields are.

Reads the same `ComponentSchema` the Inspector's widgets and an agent's
JSON Schema come from, so the three cannot describe a component
differently. A browser over a second, hand-maintained list of components
is a browser that is wrong.

Practical use, in order of how often: finding the name to type into a
prefab file, checking whether a field is settable before trying, and
reading an enum's members -- which is the one thing nothing else on screen
tells you.
"""

from __future__ import annotations

from imgui_bundle import imgui

from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.studio.model.schema import ComponentSchema, describe_registry

_DERIVED_COLOUR = (0.6, 0.6, 0.6, 1.0)
_READONLY_COLOUR = (0.85, 0.75, 0.55, 1.0)
_EDITABLE_COLOUR = (0.8, 0.95, 0.8, 1.0)


class SchemaPanel(EditorPanel):
    """Browses every registered component and its fields."""

    def __init__(self, registry: ComponentRegistry, *, visible: bool = False) -> None:
        """Initialize the panel.

        Args:
            registry: The registry to describe.
            visible: Whether it draws from the first frame. Hidden by
                default -- it is a reference, consulted rather than
                watched.
        """
        super().__init__("Components", visible=visible)
        self._registry = registry
        self._filter = ""
        self._schemas: dict[str, ComponentSchema] | None = None
        self._described_count = 0

    def draw(self, context: PanelContext) -> None:
        """Draw the component list.

        Args:
            context: The world and selection to read. Unused: the schema
                is a property of the registry, not of any scene.
        """
        imgui.begin(self.title)
        try:
            schemas = self._resolve_schemas()

            imgui.set_next_item_width(-1)
            _, self._filter = imgui.input_text("##filter", self._filter)
            if not self._filter:
                imgui.text_disabled(f"{len(schemas)} components. Type to filter.")

            needle = self._filter.lower()
            shown = 0
            for name, schema in schemas.items():
                if needle and needle not in name.lower():
                    continue
                shown += 1
                self._draw_component(schema)

            if needle and shown == 0:
                imgui.text_disabled(f"Nothing matches '{self._filter}'.")
        finally:
            imgui.end()

    def _resolve_schemas(self) -> dict[str, ComponentSchema]:
        """Return the schemas, reflecting only when the registry changed.

        `describe_registry` calls `typing.get_type_hints` once per
        component, which is far too slow to run every frame. The registry
        grows when a game registers its own components, so the cache is
        keyed on how many it holds rather than built once -- a count is
        enough, because nothing unregisters.

        Returns:
            Schemas by component name.
        """
        count = len(self._registry.list_components())
        if self._schemas is None or count != self._described_count:
            self._schemas = describe_registry(self._registry)
            self._described_count = count
        return self._schemas

    def _draw_component(self, schema: ComponentSchema) -> None:
        """Draw one component as a collapsible list of fields.

        Args:
            schema: The component to draw.
        """
        header = schema.name
        if schema.frozen:
            header = f"{header}  [frozen]"

        if not imgui.collapsing_header(header):
            return

        imgui.push_id(schema.name)
        try:
            if schema.doc:
                imgui.text_wrapped(schema.doc)
            imgui.text_disabled(f"reflected as: {schema.kind}")

            if not schema.fields:
                imgui.text_disabled("No fields.")
                return

            for field in schema.fields:
                self._draw_field(field)
        finally:
            imgui.pop_id()

    def _draw_field(self, field: object) -> None:
        """Draw one field, coloured by whether it can be set.

        Args:
            field: A `FieldSchema`.
        """
        name = getattr(field, "name", "?")
        type_name = getattr(field, "type_name", "?")
        editable = bool(getattr(field, "editable", False))
        writable = bool(getattr(field, "writable", False))
        derived = bool(getattr(field, "derived", False))
        enum_values = tuple(getattr(field, "enum_values", ()))
        has_default = bool(getattr(field, "has_default", False))
        default = getattr(field, "default", None)

        if derived:
            colour = _DERIVED_COLOUR
            note = "derived"
        elif editable:
            colour = _EDITABLE_COLOUR
            note = ""
        elif writable:
            colour = _READONLY_COLOUR
            note = "no JSON form"
        else:
            colour = _READONLY_COLOUR
            note = "read-only"

        line = f"  {name}: {type_name}"
        if has_default:
            line += f" = {default!r}"
        if note:
            line += f"   ({note})"
        imgui.text_colored(imgui.ImVec4(*colour), line)

        if enum_values:
            # The one thing a reader cannot work out from anywhere else on
            # screen, so it is always shown rather than hidden behind a
            # hover.
            imgui.text_disabled(f"      one of: {', '.join(enum_values)}")

        doc = getattr(field, "doc", None)
        if doc and imgui.is_item_hovered():
            imgui.set_tooltip(str(doc))
