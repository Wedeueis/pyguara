"""Serialization logic for converting objects to storage formats."""

import dataclasses
import json
import pickle
from typing import Any

from pyguara.common.types import Color, Rect, Vector2
from pyguara.persistence.types import SerializationFormat

# --- Pre-processing for JSON ---


def prepare_for_json(o: Any) -> Any:
    """
    Recursively convert game objects into JSON-friendly dicts.

    This bypasses json.dumps treating iterables (Vector2) as lists,
    and avoids dataclasses.asdict() deepcopy issues with C-types.
    """
    # 1. Engine Types
    if isinstance(o, Vector2):
        return {"__type__": "Vector2", "x": o.x, "y": o.y}

    if isinstance(o, Color):
        return {"__type__": "Color", "r": o.r, "g": o.g, "b": o.b, "a": o.a}

    if isinstance(o, Rect):
        return {"__type__": "Rect", "x": o.x, "y": o.y, "w": o.width, "h": o.height}

    # 2. Dataclasses (Components)
    if dataclasses.is_dataclass(o):
        data = {}
        # Manually iterate fields to avoid deepcopy issues in asdict
        for field in dataclasses.fields(o):
            value = getattr(o, field.name)
            data[field.name] = prepare_for_json(value)

        if hasattr(o, "__class__"):
            data["__type__"] = o.__class__.__name__
        return data

    # 3. Containers
    if isinstance(o, list):
        return [prepare_for_json(i) for i in o]

    if isinstance(o, dict):
        return {k: prepare_for_json(v) for k, v in o.items()}

    # 4. Primitives
    return o


# --- Custom Decoders ---


def game_object_hook(dct: dict[str, Any]) -> Any:
    """Rebuild engine value types from their JSON representation.

    Passed to `json.loads` as its `object_hook`.

    Args:
        dct: One decoded JSON object.

    Returns:
        A `Vector2`, `Color` or `Rect` when the dict carries a matching
        `__type__` tag, otherwise the dict unchanged.
    """
    if "__type__" in dct:
        t = dct["__type__"]

        if t == "Vector2":
            return Vector2(dct["x"], dct["y"])
        if t == "Color":
            return Color(dct["r"], dct["g"], dct["b"], dct.get("a", 255))
        if t == "Rect":
            return Rect(dct["x"], dct["y"], dct["w"], dct["h"])

        # Dataclass reconstruction happens here if we have a registry.
        # For now, we leave it as a dict with metadata, letting the loader
        # instantiate the specific Component class.

    return dct


class Serializer:
    """Serialises game data to JSON or pickled bytes, and back."""

    def __init__(self, default_format: SerializationFormat = SerializationFormat.JSON):
        """Initialise the serialiser.

        Args:
            default_format: Format used when a call does not name one.
        """
        self.default_format = default_format

    def serialize(
        self, data: Any, format_type: SerializationFormat | None = None
    ) -> bytes:
        """Encode data to bytes.

        Args:
            data: The object graph to encode.
            format_type: Format to use. Defaults to the instance default.

        Returns:
            The encoded bytes.

        Raises:
            ValueError: If the format is not supported.
        """
        fmt = format_type or self.default_format

        if fmt == SerializationFormat.JSON:
            # Pre-process the data tree
            clean_data = prepare_for_json(data)
            return json.dumps(clean_data, indent=2).encode("utf-8")

        elif fmt == SerializationFormat.BINARY:
            return pickle.dumps(data)

        raise ValueError(f"Unsupported serialization format: {fmt}")

    def deserialize(
        self, data: bytes, format_type: SerializationFormat | None = None
    ) -> Any:
        """Decode bytes produced by `serialize`.

        Args:
            data: The encoded bytes.
            format_type: Format to use. Defaults to the instance default.

        Returns:
            The decoded object graph.

        Raises:
            ValueError: If the format is not supported.
        """
        fmt = format_type or self.default_format

        if fmt == SerializationFormat.JSON:
            return json.loads(data.decode("utf-8"), object_hook=game_object_hook)

        elif fmt == SerializationFormat.BINARY:
            return pickle.loads(data)

        raise ValueError(f"Unsupported serialization format: {fmt}")
