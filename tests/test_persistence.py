"""Unit tests for the persistence Serializer."""

import dataclasses

import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.persistence.serializer import SerializationFormat, Serializer


@dataclasses.dataclass
class _Component:
    name: str
    position: Vector2
    color: Color


# --------------------------------------------------------------------------- #
# JSON                                                                         #
# --------------------------------------------------------------------------- #
def test_json_vector2_roundtrip():
    s = Serializer()
    data = s.serialize(Vector2(10.5, 20.0), SerializationFormat.JSON)
    json_str = data.decode("utf-8")
    assert '"x": 10.5' in json_str
    assert '"__type__": "Vector2"' in json_str

    obj = s.deserialize(data, SerializationFormat.JSON)
    assert isinstance(obj, Vector2)
    assert (obj.x, obj.y) == (10.5, 20.0)


def test_json_color_roundtrip():
    s = Serializer()
    obj = s.deserialize(
        s.serialize(Color(255, 100, 50, 128), SerializationFormat.JSON),
        SerializationFormat.JSON,
    )
    assert isinstance(obj, Color)
    assert (obj.r, obj.a) == (255, 128)


def test_json_dataclass_returns_dict_with_rebuilt_value_types():
    """A dataclass round-trips to a dict (no schema-aware loader here),
    but nested Vector2 / Color are rebuilt as objects."""
    s = Serializer()
    comp = _Component("Player", Vector2(1, 1), Color(0, 0, 0))
    res = s.deserialize(
        s.serialize(comp, SerializationFormat.JSON), SerializationFormat.JSON
    )
    assert res["name"] == "Player"
    assert isinstance(res["position"], Vector2)
    assert isinstance(res["color"], Color)


# --------------------------------------------------------------------------- #
# MSGPACK                                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        {"a": 1, "b": [1, 2, 3], "c": {"d": True, "e": None}},
        Vector2(3.5, -2.0),
        Color(10, 20, 30, 40),
        Rect(1, 2, 3, 4),
        {"pos": Vector2(1, 2), "tint": Color(1, 2, 3), "tags": ["x", "y"]},
    ],
)
def test_msgpack_roundtrip_including_engine_types(value):
    s = Serializer()
    raw = s.serialize(value, SerializationFormat.MSGPACK)
    assert isinstance(raw, bytes)
    back = s.deserialize(raw, SerializationFormat.MSGPACK)

    if isinstance(value, Vector2):
        assert isinstance(back, Vector2) and (back.x, back.y) == (value.x, value.y)
    elif isinstance(value, Color):
        assert isinstance(back, Color) and back == value
    elif isinstance(value, Rect):
        assert isinstance(back, Rect) and back == value
    elif "pos" in value:
        assert isinstance(back["pos"], Vector2)
        assert isinstance(back["tint"], Color)
    else:
        assert back == value


def test_msgpack_is_more_compact_than_json():
    s = Serializer()
    payload = {"pos": Vector2(1, 2), "n": list(range(50))}
    assert len(s.serialize(payload, SerializationFormat.MSGPACK)) < len(
        s.serialize(payload, SerializationFormat.JSON)
    )


# --------------------------------------------------------------------------- #
# BINARY (pickle)                                                              #
# --------------------------------------------------------------------------- #
def test_binary_roundtrips_arbitrary_object():
    s = Serializer()
    obj = _Component("P", Vector2(5, 6), Color(1, 1, 1))
    back = s.deserialize(
        s.serialize(obj, SerializationFormat.BINARY), SerializationFormat.BINARY
    )
    assert isinstance(back, _Component)
    assert back.name == "P"


# --------------------------------------------------------------------------- #
# Format handling                                                              #
# --------------------------------------------------------------------------- #
def test_default_format_is_used_when_unspecified():
    s = Serializer(default_format=SerializationFormat.MSGPACK)
    raw = s.serialize({"a": 1})
    assert s.deserialize(raw) == {"a": 1}
    # and it is not JSON
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
