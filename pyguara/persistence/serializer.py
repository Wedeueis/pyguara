"""Serialization logic for converting objects to storage formats."""

import json
import pickle
from typing import Any, Optional, TypeVar

from pyguara.persistence.types import SerializationFormat

T = TypeVar("T")


class Serializer:
    """
    Handle serialization and deserialization of game objects.

    Supports multiple formats to balance between human-readability (JSON)
    and performance/size (Binary/Pickle).
    """

    def __init__(self, default_format: SerializationFormat = SerializationFormat.JSON):
        """Initialize the serializer.

        Args:
            default_format: The default format to use if none is specified.
        """
        self.default_format = default_format

    def serialize(
        self, data: Any, format_type: Optional[SerializationFormat] = None
    ) -> bytes:
        """Serialize an object into bytes.

        Args:
            data: The Python object to serialize.
            format_type: The format to use. Defaults to self.default_format.

        Returns:
            The serialized byte string.

        Raises:
            ValueError: If the format is not supported.
            TypeError: If the data cannot be serialized.
        """
        fmt = format_type or self.default_format

        if fmt == SerializationFormat.JSON:
            # default=str handles UUIDs, Datetimes, etc. as strings
            return json.dumps(data, default=str).encode("utf-8")

        elif fmt == SerializationFormat.BINARY:
            # Pickle is standard for Python-only engines, though security risk if sharing saves
            return pickle.dumps(data)

        # Add MsgPack here if needed

        raise ValueError(f"Unsupported serialization format: {fmt}")

    def deserialize(
        self, data: bytes, format_type: Optional[SerializationFormat] = None
    ) -> Any:
        """Deserialize bytes back into a Python object.

        Args:
            data: The byte string to deserialize.
            format_type: The format the data is in. Defaults to self.default_format.

        Returns:
            The reconstructed Python object.

        Raises:
            ValueError: If the format is not supported.
        """
        fmt = format_type or self.default_format

        if fmt == SerializationFormat.JSON:
            return json.loads(data.decode("utf-8"))

        elif fmt == SerializationFormat.BINARY:
            return pickle.loads(data)

        raise ValueError(f"Unsupported serialization format: {fmt}")
