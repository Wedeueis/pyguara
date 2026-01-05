"""Core Persistence Manager."""

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional, TypeVar

from pyguara.persistence.types import SaveMetadata, SerializationFormat, StorageBackend
from pyguara.persistence.serializer import Serializer

logger = logging.getLogger(__name__)
T = TypeVar("T")


class PersistenceManager:
    """
    Coordinator for the Data Persistence subsystem.

    This manager orchestrates serialization, integrity checking, and storage.
    It acts as the Facade for the rest of the engine to save/load data.

    Attributes:
        storage: The backend storage implementation (e.g., FileSystem, SQLite).
        serializer: The serialization handler.
    """

    def __init__(self, storage_backend: StorageBackend):
        """Initialize the persistence manager.

        Args:
            storage_backend: The concrete implementation of where data is stored.
        """
        self.storage = storage_backend
        self.serializer = Serializer(default_format=SerializationFormat.JSON)
        # Placeholder for MigrationManager integration
        self.migration_manager = None

    def save_data(
        self, key: str, data: Any, save_version: int = 1, compress: bool = False
    ) -> bool:
        """Save an object to storage.

        Calculates checksums and attaches metadata automatically.

        Args:
            key: Unique identifier for this save data (e.g., "player_save_1").
            data: The object to save.
            save_version: The schema version of the data (for migrations).
            compress: Whether to apply compression (Not implemented in this snippet).

        Returns:
            True if successful, False otherwise.
        """
        try:
            # 1. Serialize
            # We use JSON by default for debuggability, but this could be config driven
            fmt = SerializationFormat.JSON
            raw_bytes = self.serializer.serialize(data, format_type=fmt)

            # 2. Integrity
            checksum = hashlib.md5(raw_bytes).hexdigest()

            # 3. Metadata
            metadata = SaveMetadata(
                version="1.0.0",  # Engine version
                timestamp=datetime.now(),
                data_type=type(data).__name__,
                checksum=checksum,
                save_version=save_version,
            )

            # Convert metadata to dict for storage
            # (In a real scenario, use asdict)
            meta_dict = {
                "version": metadata.version,
                "timestamp": metadata.timestamp.isoformat(),
                "data_type": metadata.data_type,
                "checksum": metadata.checksum,
                "save_version": metadata.save_version,
                "format": fmt.value,
            }

            # 4. Storage
            self.storage.save(key, raw_bytes, meta_dict)
            logger.info(f"Successfully saved data '{key}'")
            return True

        except Exception as e:
            logger.error(f"Failed to save data '{key}': {e}")
            return False

    def load_data(self, key: str, verify_integrity: bool = True) -> Optional[Any]:
        """Load an object from storage.

        Args:
            key: Unique identifier for the save data.
            verify_integrity: If True, validates MD5 checksum before returning.

        Returns:
            The deserialized object, or None if failed/corrupted.
        """
        try:
            # 1. Retrieve
            result = self.storage.load(key)
            if not result:
                logger.warning(f"No data found for key '{key}'")
                return None

            raw_bytes, meta_dict = result

            # 2. Verify Integrity
            if verify_integrity:
                stored_checksum = meta_dict.get("checksum")
                calculated_checksum = hashlib.md5(raw_bytes).hexdigest()
                if stored_checksum != calculated_checksum:
                    logger.error(
                        f"Integrity check failed for '{key}'. File may be corrupted."
                    )
                    return None

            # 3. Deserialize
            fmt_str = meta_dict.get("format", "json")
            fmt = SerializationFormat(fmt_str)

            data = self.serializer.deserialize(raw_bytes, format_type=fmt)

            # 4. Migration Hook (Placeholder)
            # if self.migration_manager:
            #     current_version = meta_dict.get("save_version", 1)
            #     data = self.migration_manager.migrate(data, current_version)

            return data

        except Exception as e:
            logger.error(f"Failed to load data '{key}': {e}")
            return None
