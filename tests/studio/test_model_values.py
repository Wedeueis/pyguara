"""`studio.model.values`: encoding field values to JSON and back.

The case that drives the design is the one that cannot be encoded. A field
holding a texture, a material or a callback is something an agent will
meet, and `null` is the wrong answer -- it reads as "this field is empty"
when the truth is "I cannot show you this and you cannot set it from
JSON". Those are marked instead.
"""

from __future__ import annotations

import enum

import pytest

from pyguara.common.types import Color, Vector2
from pyguara.physics.types import BodyType, ShapeType
from pyguara.scene.serializer import RESOURCE_KEY
from pyguara.studio.model.values import (
    UNENCODABLE_KEY,
    decode,
    encode,
    is_encodable,
    type_name,
)


class Flavour(enum.Enum):
    """A test enum."""

    SWEET = "sweet"
    SOUR = "sour"


class TestEncodeScalars:
    """The passthrough types."""

    @pytest.mark.parametrize("value", [True, False, 0, 42, -1, 0.5, "", "text"])
    def test_scalars_pass_through(self, value: object) -> None:
        assert encode(value) == value

    def test_none_encodes_as_null(self) -> None:
        assert encode(None) is None

    def test_a_bool_stays_a_bool(self) -> None:
        """`bool` subclasses `int`, so an int-first arm would turn True
        into 1 and an editor would draw a checkbox as a number field."""
        assert encode(True) is True
        assert isinstance(encode(True), bool)


class TestEncodeValueTypes:
    """The engine's own value types."""

    def test_vector2_encodes_as_x_y(self) -> None:
        """The same shape `SceneSerializer` writes, so a value Studio
        reports looks like the value in the scene file."""
        assert encode(Vector2(1.5, -2)) == {"x": 1.5, "y": -2.0}

    def test_color_encodes_as_channels(self) -> None:
        assert encode(Color(1, 2, 3, 4)) == {"r": 1, "g": 2, "b": 3, "a": 4}

    def test_an_enum_encodes_as_its_value(self) -> None:
        assert encode(BodyType.DYNAMIC) == BodyType.DYNAMIC.value

    def test_a_resource_encodes_as_its_path(self) -> None:
        """Not field by field: that would describe a backend surface
        rather than the path needed to load it again."""
        from tests.test_scene_serializer import FakeTexture

        assert encode(FakeTexture("art/hero.png")) == {RESOURCE_KEY: "art/hero.png"}

    def test_a_nested_dataclass_encodes_as_an_object(self) -> None:
        from pyguara.physics.types import PhysicsMaterial

        encoded = encode(PhysicsMaterial())
        assert isinstance(encoded, dict)
        assert "friction" in encoded


class TestEncodeContainers:
    """Lists, tuples and dicts, recursively."""

    def test_a_list_encodes_elementwise(self) -> None:
        assert encode([Vector2(1, 2)]) == [{"x": 1.0, "y": 2.0}]

    def test_a_tuple_becomes_a_list(self) -> None:
        """JSON has no tuple."""
        assert encode((1, 2)) == [1, 2]

    def test_a_dict_encodes_its_values(self) -> None:
        assert encode({"at": Vector2(0, 1)}) == {"at": {"x": 0.0, "y": 1.0}}

    def test_dict_keys_become_strings(self) -> None:
        assert encode({1: "one"}) == {"1": "one"}


class TestUnencodable:
    """The marker, and why it is not null."""

    def test_an_arbitrary_object_is_marked(self) -> None:
        class Opaque:
            def __repr__(self) -> str:
                return "<opaque>"

        assert encode(Opaque()) == {UNENCODABLE_KEY: "<opaque>"}

    def test_the_marker_is_distinguishable_from_none(self) -> None:
        """The whole point: "cannot show you this" is not "this is
        empty"."""

        class Opaque:
            pass

        assert encode(Opaque()) is not None
        assert encode(None) is None

    def test_is_encodable_reports_the_difference(self) -> None:
        class Opaque:
            pass

        assert is_encodable(Vector2(1, 2)) is True
        assert is_encodable(None) is True
        assert is_encodable(Opaque()) is False

    def test_writing_a_marker_back_is_refused(self) -> None:
        """An agent that read a field and tries to write it back
        unchanged gets told why it cannot, not a silent corruption."""
        with pytest.raises(ValueError, match="has no JSON form"):
            decode({UNENCODABLE_KEY: "<opaque>"})


class TestDecodeByType:
    """Decoding with the field's declared type in hand."""

    def test_vector2_from_an_object(self) -> None:
        assert decode({"x": 1, "y": 2}, Vector2) == Vector2(1, 2)

    def test_vector2_from_a_pair(self) -> None:
        """An agent writing `[x, y]` is being reasonable."""
        assert decode([3, 4], Vector2) == Vector2(3, 4)

    def test_vector2_from_nonsense_is_refused(self) -> None:
        with pytest.raises(ValueError, match="Expected a Vector2"):
            decode("over there", Vector2)

    def test_color_from_an_object(self) -> None:
        assert decode({"r": 1, "g": 2, "b": 3, "a": 4}, Color) == Color(1, 2, 3, 4)

    def test_color_alpha_defaults_to_opaque(self) -> None:
        assert decode({"r": 1, "g": 2, "b": 3}, Color) == Color(1, 2, 3, 255)

    def test_color_from_a_sequence(self) -> None:
        assert decode([1, 2, 3], Color) == Color(1, 2, 3, 255)

    def test_an_int_into_a_bool_field_is_refused(self) -> None:
        """`bool(2)` is True, which would be a silent coercion."""
        with pytest.raises(ValueError, match="Expected true or false"):
            decode(2, bool)

    def test_a_bool_into_a_number_field_is_refused(self) -> None:
        with pytest.raises(ValueError, match="Expected a number"):
            decode(True, float)

    def test_a_whole_float_into_an_int_field_is_accepted(self) -> None:
        """JSON has one number type, so 3 arrives as 3.0 routinely."""
        assert decode(3.0, int) == 3

    def test_a_fractional_float_into_an_int_field_is_refused(self) -> None:
        with pytest.raises(ValueError, match="Expected an integer"):
            decode(3.5, int)

    def test_an_int_into_a_float_field_is_accepted(self) -> None:
        assert decode(3, float) == 3.0

    def test_a_number_into_a_string_field_is_refused(self) -> None:
        with pytest.raises(ValueError, match="Expected a string"):
            decode(3, str)


class TestDecodeEnums:
    """The latitude a scene file and an agent both get."""

    def test_by_exact_name(self) -> None:
        assert decode("SWEET", Flavour) is Flavour.SWEET

    def test_by_name_in_any_case(self) -> None:
        assert decode("sweet", Flavour) is Flavour.SWEET

    def test_by_value(self) -> None:
        assert decode(ShapeType.CIRCLE.value, ShapeType) is ShapeType.CIRCLE

    def test_a_member_passes_through(self) -> None:
        assert decode(Flavour.SOUR, Flavour) is Flavour.SOUR

    def test_an_unknown_member_names_the_valid_ones(self) -> None:
        """The error is the agent's correction path, so it has to carry
        the alternatives."""
        with pytest.raises(ValueError, match="Valid values: SOUR, SWEET"):
            decode("salty", Flavour)


class TestDecodeNestedDataclasses:
    """What makes `Collider.material` settable."""

    def test_builds_from_a_full_object(self) -> None:
        from pyguara.physics.types import PhysicsMaterial

        material = decode(
            {"friction": 0.2, "restitution": 0.5, "density": 2.0}, PhysicsMaterial
        )
        assert material == PhysicsMaterial(friction=0.2, restitution=0.5, density=2.0)

    def test_a_partial_object_keeps_the_other_defaults(self) -> None:
        """Setting one channel should not require restating the rest."""
        from pyguara.physics.types import PhysicsMaterial

        material = decode({"friction": 0.2}, PhysicsMaterial)
        assert material.friction == 0.2
        assert material.density == PhysicsMaterial().density

    def test_an_unknown_field_names_the_valid_ones(self) -> None:
        from pyguara.physics.types import PhysicsMaterial

        with pytest.raises(ValueError, match="valid fields"):
            decode({"bounciness": 1.0}, PhysicsMaterial)

    def test_a_non_object_is_refused(self) -> None:
        from pyguara.physics.types import PhysicsMaterial

        with pytest.raises(ValueError, match="Expected an object"):
            decode("slippery", PhysicsMaterial)


class TestDecodeByShape:
    """Decoding with no type hint at all."""

    def test_an_x_y_object_becomes_a_vector(self) -> None:
        """So an agent's JSON works without it having to name types."""
        assert decode({"x": 1, "y": 2}) == Vector2(1, 2)

    def test_an_rgb_object_becomes_a_colour(self) -> None:
        assert decode({"r": 1, "g": 2, "b": 3}) == Color(1, 2, 3, 255)

    def test_anything_else_passes_through(self) -> None:
        assert decode({"unrelated": 1}) == {"unrelated": 1}
        assert decode(5) == 5


class TestRoundTrip:
    """Encode then decode is the identity for every editable type."""

    @pytest.mark.parametrize(
        ("value", "declared"),
        [
            (True, bool),
            (42, int),
            (1.5, float),
            ("text", str),
            (Vector2(1.5, -2.5), Vector2),
            (Color(10, 20, 30, 40), Color),
            (BodyType.KINEMATIC, BodyType),
            (ShapeType.CIRCLE, ShapeType),
        ],
    )
    def test_round_trips(self, value: object, declared: type) -> None:
        assert decode(encode(value), declared) == value


class TestTypeName:
    """Labels for a reader."""

    def test_names_the_runtime_type(self) -> None:
        assert type_name(Vector2(0, 0)) == "Vector2"

    def test_none_is_reported_as_none(self) -> None:
        """Not "NoneType", which suggests a type the field has."""
        assert type_name(None) == "None"
