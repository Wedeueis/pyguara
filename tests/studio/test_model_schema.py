"""`studio.model.schema`: reflecting a component's authorable shape.

The reason this is not four lines of `dataclasses.fields`: `Transform` is
not a dataclass. It stores private state and exposes `position`,
`rotation` and `scale` as properties, plus `interpolate` as an attribute
assigned in `__init__` with no class annotation. `dataclasses.fields`
returns nothing for it, which is why every pre-existing reflection site in
the engine special-cases `Transform` by name. These tests pin that it is
handled structurally instead.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.graphics.components.sprite import Sprite
from pyguara.physics.components import Collider, RigidBody
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.studio.model.schema import describe_component, describe_registry


class Flavour(enum.Enum):
    """A test enum."""

    SWEET = "sweet"
    SOUR = "sour"


@dataclass
class Everything(BaseComponent):
    """A component with one field of each interesting kind."""

    flag: bool = False
    count: int = 0
    amount: float = 0.0
    label: str = ""
    where: Vector2 = field(default_factory=Vector2.zero)
    tint: Color = field(default_factory=lambda: Color(1, 2, 3, 4))
    flavour: Flavour = Flavour.SWEET
    numbers: list[float] = field(default_factory=list)
    opaque: object = None

    def __post_init__(self) -> None:
        BaseComponent.__init__(self)


@dataclass(frozen=True)
class Frozen(BaseComponent):
    """A frozen component, whose fields cannot be assigned."""

    value: int = 0


@pytest.fixture
def core_registry() -> ComponentRegistry:
    """A registry wired as `create_application()` wires it."""
    from pyguara.application.bootstrap import _register_core_components

    registry = ComponentRegistry()
    _register_core_components(registry)
    return registry


class TestDataclassComponents:
    """The common case."""

    def test_reports_the_kind(self) -> None:
        assert describe_component(Tag).kind == "dataclass"

    def test_lists_the_fields_in_declaration_order(self) -> None:
        names = [f.name for f in describe_component(Everything).fields]
        assert names[:4] == ["flag", "count", "amount", "label"]

    def test_resolves_the_declared_type_not_the_string(self) -> None:
        """Component modules use `from __future__ import annotations`, so
        `field.type` is the *string* "Vector2"."""
        schema = describe_component(Everything)
        assert schema.field("where").type_name == "Vector2"

    def test_reports_defaults(self) -> None:
        schema = describe_component(Everything)
        assert schema.field("count").default == 0
        assert schema.field("count").has_default is True

    def test_calls_a_default_factory(self) -> None:
        """The only way to see what the default actually is."""
        schema = describe_component(Everything)
        assert schema.field("tint").default == {"r": 1, "g": 2, "b": 3, "a": 4}

    def test_a_field_with_no_default_says_so(self) -> None:
        """Distinguishing "defaults to None" from "has no default"."""
        schema = describe_component(Sprite)
        assert schema.field("texture").has_default is False

    def test_private_fields_are_skipped(self) -> None:
        schema = describe_component(Everything)
        assert all(not f.name.startswith("_") for f in schema.fields)

    def test_the_entity_backref_is_hidden(self) -> None:
        """Not authored data."""
        assert describe_component(Everything).field("entity") is None

    def test_the_summary_docstring_is_carried(self) -> None:
        assert describe_component(Tag).doc is not None


class TestEditability:
    """Which fields Studio and an agent can set."""

    def test_scalars_and_value_types_are_editable(self) -> None:
        schema = describe_component(Everything)
        for name in ("flag", "count", "amount", "label", "where", "tint"):
            assert schema.field(name).editable is True, name

    def test_an_enum_field_is_editable(self) -> None:
        assert describe_component(Everything).field("flavour").editable is True

    def test_a_typed_list_is_editable(self) -> None:
        assert describe_component(Everything).field("numbers").editable is True

    def test_an_opaque_field_is_not_editable(self) -> None:
        assert describe_component(Everything).field("opaque").editable is False

    def test_a_resource_field_is_writable_but_not_editable(self) -> None:
        """There is no JSON form for a live texture handle to arrive as."""
        texture = describe_component(Sprite).field("texture")
        assert texture.writable is True
        assert texture.editable is False

    def test_a_nested_dataclass_is_editable(self) -> None:
        """Tweaking a physics material's friction is exactly the sort of
        edit an inspector is for."""
        assert describe_component(Collider).field("material").editable is True

    def test_frozen_fields_are_neither_writable_nor_editable(self) -> None:
        schema = describe_component(Frozen)
        assert schema.frozen is True
        assert schema.field("value").writable is False
        assert schema.field("value").editable is False

    def test_editable_fields_filters(self) -> None:
        schema = describe_component(Everything)
        names = {f.name for f in schema.editable_fields}
        assert "opaque" not in names
        assert "flag" in names


class TestEnumFields:
    """The one thing an agent cannot guess."""

    def test_the_member_names_are_carried(self) -> None:
        values = describe_component(Everything).field("flavour").enum_values
        assert values == ("SOUR", "SWEET")

    def test_a_non_enum_field_carries_none(self) -> None:
        assert describe_component(Everything).field("count").enum_values == ()

    def test_the_json_schema_constrains_to_the_members(self) -> None:
        schema = describe_component(Everything).to_json_schema()
        assert schema["properties"]["flavour"]["enum"] == ["SOUR", "SWEET"]

    def test_a_real_engine_enum_is_covered(self) -> None:
        values = describe_component(RigidBody).field("body_type").enum_values
        assert "DYNAMIC" in values


class TestPropertyComponents:
    """`Transform`, which is why this module is not trivial."""

    def test_reports_the_kind(self) -> None:
        assert describe_component(Transform).kind == "properties"

    def test_finds_the_writable_properties(self) -> None:
        schema = describe_component(Transform)
        for name in ("position", "rotation", "scale"):
            assert schema.field(name).writable is True, name

    def test_a_derived_property_is_read_only(self) -> None:
        """Reported rather than hidden: `world_scale` is useful to see and
        genuinely not settable, and an agent told so will not try."""
        assert describe_component(Transform).field("world_scale").writable is False

    def test_finds_an_attribute_with_no_class_annotation(self) -> None:
        """`interpolate` is assigned in `__init__`, so `get_type_hints`
        cannot see it -- yet the scene serializer round-trips it and an
        inspector should show it. A default instance is the only way."""
        interpolate = describe_component(Transform).field("interpolate")
        assert interpolate is not None
        assert interpolate.type_name == "bool"
        assert interpolate.editable is True

    def test_the_direction_vectors_are_hidden(self) -> None:
        """Noise in an inspector; they restate the rotation."""
        schema = describe_component(Transform)
        for name in ("right", "left", "up", "down", "forward"):
            assert schema.field(name) is None, name

    def test_the_child_list_is_hidden(self) -> None:
        """The hierarchy panel shows it better."""
        assert describe_component(Transform).field("children") is None

    def test_type_labels_carry_no_module_paths(self) -> None:
        """`Transform | None` is the same information as
        `pyguara.common.components.Transform | None` and four times
        shorter, in a schema an agent pays for by the token."""
        label = describe_component(Transform).field("parent").type_name
        assert label == "Transform | None"


class TestJsonSchema:
    """What an agent reads as an operation's argument schema."""

    def test_is_an_object_schema(self) -> None:
        schema = describe_component(Tag).to_json_schema()
        assert schema["type"] == "object"
        assert schema["title"] == "Tag"

    def test_rejects_unknown_properties(self) -> None:
        """So a typo'd field name is an argument error rather than a
        silently ignored key."""
        assert describe_component(Tag).to_json_schema()["additionalProperties"] is False

    def test_nothing_is_required(self) -> None:
        """Every component here is constructible from its defaults, and a
        partial dict is the normal way to author one."""
        assert "required" not in describe_component(Everything).to_json_schema()

    def test_scalars_map_to_json_types(self) -> None:
        properties = describe_component(Everything).to_json_schema()["properties"]
        assert properties["flag"]["type"] == "boolean"
        assert properties["count"]["type"] == "integer"
        assert properties["amount"]["type"] == "number"
        assert properties["label"]["type"] == "string"

    def test_vector2_maps_to_an_x_y_object(self) -> None:
        properties = describe_component(Everything).to_json_schema()["properties"]
        assert properties["where"]["required"] == ["x", "y"]

    def test_color_channels_are_bounded(self) -> None:
        properties = describe_component(Everything).to_json_schema()["properties"]
        assert properties["tint"]["properties"]["r"]["maximum"] == 255

    def test_a_list_maps_to_an_array(self) -> None:
        properties = describe_component(Everything).to_json_schema()["properties"]
        assert properties["numbers"]["type"] == "array"

    def test_non_editable_fields_are_absent(self) -> None:
        """An agent is not offered an argument it cannot supply."""
        properties = describe_component(Sprite).to_json_schema()["properties"]
        assert "texture" not in properties
        assert "layer" in properties


class TestDescribeRegistry:
    """Pairing `list_components()` with `get()`."""

    def test_describes_every_registered_component(
        self, core_registry: ComponentRegistry
    ) -> None:
        schemas = describe_registry(core_registry)
        assert set(schemas) == set(core_registry.list_components())

    def test_every_core_component_describes_without_error(
        self, core_registry: ComponentRegistry
    ) -> None:
        """A real sweep, not a sample: reflection is exactly the kind of
        code that works on the component you tested it with."""
        schemas = describe_registry(core_registry)
        for name, schema in schemas.items():
            assert schema.name == name
            assert schema.kind in ("dataclass", "properties")

    def test_every_core_component_emits_a_json_schema(
        self, core_registry: ComponentRegistry
    ) -> None:
        for schema in describe_registry(core_registry).values():
            emitted = schema.to_json_schema()
            assert emitted["type"] == "object"

    def test_a_component_that_cannot_be_described_is_skipped(self) -> None:
        """One broken component must not take the schema browser down."""

        class Unresolvable(BaseComponent):
            """Annotated with something that does not exist at runtime."""

            __annotations__ = {"field": "NoSuchTypeAnywhere"}

        registry = ComponentRegistry()
        registry.register(Tag)
        registry.register(Unresolvable)

        schemas = describe_registry(registry)
        assert "Tag" in schemas


class TestSerialization:
    """The dict forms."""

    def test_field_to_dict_omits_empty_keys(self) -> None:
        """A schema handed to an agent carries no filler."""
        data = describe_component(Sprite).field("texture").to_dict()
        assert "default" not in data
        assert data["name"] == "texture"

    def test_schema_to_dict_includes_the_fields(self) -> None:
        data = describe_component(Tag).to_dict()
        assert data["name"] == "Tag"
        assert [f["name"] for f in data["fields"]] == ["name"]

    def test_frozen_is_only_reported_when_true(self) -> None:
        assert "frozen" not in describe_component(Tag).to_dict()
        assert describe_component(Frozen).to_dict()["frozen"] is True
