"""Type definitions for the persistence system."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable


class SerializationFormat(Enum):
    """Supported formats for object serialization."""

    JSON = "json"
    MSGPACK = "msgpack"
    BINARY = "binary"


@dataclass
class SaveMetadata:
    """Metadata recorded alongside a stored object.

    Serialised into the header of every save blob and re-read on load; the
    load path uses ``format``/``compressed`` to reverse the encoding and
    ``checksum`` to verify integrity.

    Attributes:
        version: The engine version string when the data was saved.
        timestamp: When the data was saved (timezone-aware, UTC).
        data_type: The class name of the stored object.
        checksum: MD5 hash of the stored payload bytes, for integrity
            verification. Covers the payload exactly as written to disk
            (after compression, if any).
        save_version: Integer schema version, for migration tracking.
        format: The ``SerializationFormat`` value the payload is encoded in.
        compressed: Whether the payload bytes are gzip-compressed.
    """

    version: str
    timestamp: datetime
    data_type: str
    checksum: str | None = None
    save_version: int = 1
    format: str = "json"
    compressed: bool = False


@runtime_checkable
class StorageBackend(Protocol):
    """Interface for physical data storage mechanisms.

    A backend is a plain key -> blob store. Framing of metadata into the
    blob is the ``PersistenceManager``'s job, so a backend only has to make
    a single value durable per key rather than keep two files consistent.
    """

    def save(self, key: str, blob: bytes) -> bool:
        """Persist a blob under a key, replacing any existing value.

        Args:
            key: Unique identifier for the data.
            blob: The bytes to store.

        Returns:
            True if the write succeeded, False otherwise.
        """
        ...

    def load(self, key: str) -> bytes | None:
        """Return the blob stored under a key.

        Args:
            key: Unique identifier for the data.

        Returns:
            The stored bytes, or None if the key is absent or unreadable.
        """
        ...

    def delete(self, key: str) -> bool:
        """Delete the value stored under a key.

        Args:
            key: Unique identifier for the data.

        Returns:
            True if a value was removed, False if the key was absent.
        """
        ...

    def list_keys(self) -> list[str]:
        """List all keys currently present in storage."""
        ...
