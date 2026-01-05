"""Type definitions for the persistence system."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Protocol


class SerializationFormat(Enum):
    """Supported formats for object serialization."""

    JSON = "json"
    MSGPACK = "msgpack"
    BINARY = "binary"


@dataclass
class SaveMetadata:
    """
    Metadata associated with a stored object.

    Attributes:
        version: The version string of the engine/game when saved.
        timestamp: When the data was saved.
        data_type: The class name of the stored object.
        checksum: MD5 hash for integrity verification.
        save_version: Integer version for migration tracking.
    """

    version: str
    timestamp: datetime
    data_type: str
    checksum: Optional[str] = None
    save_version: int = 1


class StorageBackend(Protocol):
    """Interface for physical data storage mechanisms."""

    def save(self, key: str, data: bytes, metadata: Dict[str, Any]) -> bool:
        """Save raw bytes and metadata to the storage medium.

        Args:
            key: Unique identifier for the data.
            data: The raw binary data to store.
            metadata: Dictionary of metadata associated with the data.

        Returns:
            True if the save was successful, False otherwise.
        """
        ...

    def load(self, key: str) -> Optional[tuple[bytes, Dict[str, Any]]]:
        """Load raw bytes and metadata from the storage medium.

        Args:
            key: Unique identifier for the data.

        Returns:
            A tuple (data, metadata) if found, None otherwise.
        """
        ...

    def delete(self, key: str) -> bool:
        """Delete data from the storage medium.

        Args:
            key: Unique identifier for the data.

        Returns:
            True if deleted, False if not found or failed.
        """
        ...

    def list_keys(self) -> list[str]:
        """List all available keys in storage."""
        ...
