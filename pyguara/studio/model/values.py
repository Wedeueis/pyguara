"""Turning component field values into JSON, and back.

Four places in the engine already reflect over component fields, each with
its own ad-hoc value handling: `ComponentRegistry._instantiate_dataclass`,
`SceneSerializer`'s two halves, and `InspectorPanel._draw_field`. This is
the fifth, and the one the others could be rewritten onto -- it is
deliberately shape-compatible with what `SceneSerializer` writes, so a
value Studio reports to an agent looks like the value in the scene file
the agent might open next.

The encoding that matters most is the one for a value that **cannot** be
encoded. A field holding a texture, a material or a live callback is a
real thing an agent will meet, and `null` is the wrong answer: it reads as
"the field is empty" when the truth is "I cannot show you this, and you
cannot set it from JSON". Those come back as
`{"__unencodable__": "<repr>"}` instead, which says so.
"""

from __future__ import annotations

import dataclasses
import enum
import typing
from typing import Any

from pyguara.common.types import Color, Vector2
from pyguara.resources.types import Resource
from pyguara.scene.serializer import RESOURCE_KEY

UNENCODABLE_KEY = "__unencodable__"
"""Marks a value that has no JSON form, holding its `repr`.

Distinct from `null`, which means the field genuinely holds None.
"""

# The scalars that pass through untouched. `bool` is listed before `int`
# wherever these are tested in order, because `bool` is a subclass of
# `int`: an `isinstance(value, int)` test matches True and False, which is
# how an editor ends up drawing a checkbox as a number field.
_PASSTHROUGH = (bool, int, float, str)


def encode(value: Any) -> Any:
    """Return a JSON-serializable form of `value`.

    Args:
        value: Any component field value.

    Returns:
        The encoded value. Anything without a JSON form comes back as
        `{"__unencodable__": "<repr>"}` rather than None.
    """
    if value is None:
        return None

    # `type(value) in` rather than isinstance, so a bool is not caught by
    # the int arm and an IntEnum is not caught by either -- it belongs to
    # the enum arm below.
    if type(value) in _PASSTHROUGH:
        return value

    if isinstance(value, Vector2):
        return {"x": float(value.x), "y": float(value.y)}

    if isinstance(value, Color):
        return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}

    if isinstance(value, enum.Enum):
        return value.value

    # Before the dataclass arm: a resource may well be one, and encoding a
    # texture field by field would describe a backend surface instead of
    # the path needed to find it again.
    if isinstance(value, Resource):
        return {RESOURCE_KEY: value.path}

    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]

    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: encode(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if not field.name.startswith("_")
        }

    # A subclass of a scalar that reached here -- a numpy scalar, an
    # IntEnum-like that is not an Enum -- still has a JSON form.
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)

    return {UNENCODABLE_KEY: repr(value)}


def is_encodable(value: Any) -> bool:
    """Whether `encode` can represent `value` in JSON.

    Args:
        value: The value to test.

    Returns:
        True when encoding it loses nothing an editor or agent needs.
    """
    encoded = encode(value)
    return not (isinstance(encoded, dict) and UNENCODABLE_KEY in encoded)


def decode(value: Any, target_type: Any = None) -> Any:
    """Turn an encoded value back into the Python value a field wants.

    Args:
        value: An encoded value, as `encode` produces.
        target_type: The field's declared type, when known. Without it,
            `{"x":..,"y":..}` and `{"r":..,"g":..}` are still recognised by
            shape, which is what makes an agent's JSON work without it
            having to name types.

    Returns:
        The decoded value.

    Raises:
        ValueError: If the value cannot be decoded into `target_type` --
            an unknown enum member, or an unencodable marker being written
            back. The message names the valid alternatives where there is
            a finite set of them, because the caller is often an agent
            that can correct itself from the error.
    """
    if isinstance(value, dict) and UNENCODABLE_KEY in value:
        raise ValueError(
            f"{value[UNENCODABLE_KEY]} has no JSON form and cannot be set "
            f"this way. It is reported for reading only."
        )

    if target_type is not None:
        decoded = _decode_as(value, target_type)
        if decoded is not _UNHANDLED:
            return decoded

    # No type hint, or one this does not handle: fall back to shape.
    if isinstance(value, dict):
        if {"x", "y"} <= set(value):
            return Vector2(float(value["x"]), float(value["y"]))
        if {"r", "g", "b"} <= set(value):
            return Color(
                int(value["r"]),
                int(value["g"]),
                int(value["b"]),
                int(value.get("a", 255)),
            )
    return value


class _Unhandled:
    """Sentinel for "this decoder did not apply"."""


_UNHANDLED = _Unhandled()


def _decode_as(value: Any, target_type: Any) -> Any:
    """Decode `value` into `target_type`, or return the sentinel.

    Args:
        value: The encoded value.
        target_type: The type to decode into.

    Returns:
        The decoded value, or `_UNHANDLED` when this does not apply.

    Raises:
        ValueError: If the value is wrong for a type this does handle.
    """
    if isinstance(target_type, type) and issubclass(target_type, enum.Enum):
        return _decode_enum(value, target_type)

    if target_type is Vector2 or (
        isinstance(target_type, type) and issubclass(target_type, Vector2)
    ):
        if isinstance(value, dict) and {"x", "y"} <= set(value):
            return Vector2(float(value["x"]), float(value["y"]))
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return Vector2(float(value[0]), float(value[1]))
        raise ValueError(
            f'Expected a Vector2 as {{"x": ..., "y": ...}} or [x, y], got {value!r}.'
        )

    if target_type is Color:
        if isinstance(value, dict) and {"r", "g", "b"} <= set(value):
            return Color(
                int(value["r"]),
                int(value["g"]),
                int(value["b"]),
                int(value.get("a", 255)),
            )
        if isinstance(value, (list, tuple)) and len(value) in (3, 4):
            return Color(*(int(channel) for channel in value))
        raise ValueError(
            f'Expected a Color as {{"r": ..., "g": ..., "b": ..., '
            f'"a": ...}} or [r, g, b, a], got {value!r}.'
        )

    # `bool` first: `bool(2)` is True, and an int reaching a bool field
    # should be a type error rather than a silent truthiness coercion.
    if target_type is bool:
        if isinstance(value, bool):
            return value
        raise ValueError(f"Expected true or false, got {value!r}.")

    if target_type is int and not isinstance(value, bool):
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise ValueError(f"Expected an integer, got {value!r}.")

    if target_type is float:
        if isinstance(value, bool):
            raise ValueError(f"Expected a number, got {value!r}.")
        if isinstance(value, (int, float)):
            return float(value)
        raise ValueError(f"Expected a number, got {value!r}.")

    if target_type is str:
        if isinstance(value, str):
            return value
        raise ValueError(f"Expected a string, got {value!r}.")

    if (
        isinstance(target_type, type)
        and dataclasses.is_dataclass(target_type)
        and not issubclass(target_type, enum.Enum)
    ):
        return _decode_dataclass(value, target_type)

    return _UNHANDLED


def _decode_dataclass(value: Any, target_type: type) -> Any:
    """Rebuild a nested dataclass from a dict of its fields.

    What makes `Collider.material` and `Collider.layer` settable -- a
    physics material's friction is exactly the sort of thing an inspector
    or an agent reaches for.

    A partial dict is accepted: the fields given are decoded and the rest
    keep their defaults, so setting one channel of a material does not
    require restating the others.

    Args:
        value: The encoded dict.
        target_type: The dataclass to build.

    Returns:
        The instance.

    Raises:
        ValueError: If the value is not a dict, or names a field the
            dataclass does not have -- listing the ones it does, the same
            way `ComponentRegistry` does.
    """
    if not isinstance(value, dict):
        raise ValueError(
            f"Expected an object with {target_type.__name__}'s fields, got {value!r}."
        )

    hints = _dataclass_hints(target_type)
    assignable = {
        field.name
        for field in dataclasses.fields(target_type)
        if not field.name.startswith("_")
    }
    unknown = set(value) - assignable
    if unknown:
        raise ValueError(
            f"{target_type.__name__} has no field(s) {sorted(unknown)}; "
            f"valid fields: {sorted(assignable)}."
        )

    kwargs = {name: decode(item, hints.get(name)) for name, item in value.items()}
    return target_type(**kwargs)


def _dataclass_hints(target_type: type) -> dict[str, Any]:
    """Resolve a dataclass's annotations to objects, not strings.

    Args:
        target_type: The dataclass.

    Returns:
        Hints by field name, empty when they cannot be resolved.
    """
    try:
        return typing.get_type_hints(target_type)
    except Exception:  # pragma: no cover - unresolvable annotation
        return {}


def _decode_enum(value: Any, enum_type: type[enum.Enum]) -> Any:
    """Resolve `value` to a member of `enum_type`.

    Accepts a member, its exact name, its name in any case, or its value --
    the same latitude `ComponentRegistry._convert_enum` allows, so a scene
    file and an agent call behave alike.

    Args:
        value: The encoded value.
        enum_type: The enum to resolve against.

    Returns:
        The member.

    Raises:
        ValueError: If nothing matches, naming every member.
    """
    if isinstance(value, enum_type):
        return value

    if isinstance(value, str):
        if value in enum_type.__members__:
            return enum_type[value]
        upper = value.upper()
        if upper in enum_type.__members__:
            return enum_type[upper]

    try:
        return enum_type(value)
    except ValueError:
        pass

    members = ", ".join(sorted(enum_type.__members__))
    raise ValueError(
        f"{value!r} is not a {enum_type.__name__}. Valid values: {members}."
    )


def type_name(value: Any) -> str:
    """Return a readable type name for an encoded field's value.

    Args:
        value: The live (unencoded) value.

    Returns:
        The type's name, or "None" for a null value -- a field holding
        None has no useful runtime type, and saying "NoneType" to an agent
        suggests one.
    """
    if value is None:
        return "None"
    return type(value).__name__
