import dataclasses
from pyguara.persistence.serializer import Serializer, SerializationFormat
from pyguara.common.types import Vector2, Color


@dataclasses.dataclass
class TestComponent:
    name: str
    position: Vector2
    color: Color


def test_json_vector2():
    s = Serializer()
    v = Vector2(10.5, 20.0)

    # Serialize
    data = s.serialize(v, SerializationFormat.JSON)
    json_str = data.decode("utf-8")
    assert '"x": 10.5' in json_str
    assert '"__type__": "Vector2"' in json_str

    # Deserialize
    obj = s.deserialize(data, SerializationFormat.JSON)
    assert isinstance(obj, Vector2)
    assert obj.x == 10.5
    assert obj.y == 20.0


def test_json_color():
    s = Serializer()
    c = Color(255, 100, 50, 128)

    data = s.serialize(c, SerializationFormat.JSON)
    obj = s.deserialize(data, SerializationFormat.JSON)

    assert isinstance(obj, Color)
    assert obj.r == 255
    assert obj.a == 128


def test_json_dataclass_roundtrip():
    """
    Note: Dataclass roundtrip currently returns a DICT for the dataclass itself,
    but nested Vector/Colors should be objects.
    Full dataclass reconstruction requires a schema-aware loader (Phase 2).
    """
    s = Serializer()
    comp = TestComponent("Player", Vector2(1, 1), Color(0, 0, 0))

    data = s.serialize(comp, SerializationFormat.JSON)
    res_dict = s.deserialize(data, SerializationFormat.JSON)

    assert res_dict["name"] == "Player"
    assert isinstance(res_dict["position"], Vector2)
    assert isinstance(res_dict["color"], Color)
