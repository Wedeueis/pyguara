"""Core Persistence Manager."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from pyguara.log import get_logger
from pyguara.persistence.serializer import Serializer
from pyguara.persistence.types import SaveMetadata, SerializationFormat, StorageBackend

if TYPE_CHECKING:
    from pyguara.persistence.migration import MigrationManager

logger = get_logger(__name__)

_HEADER_SEP = b"\n"

try:
    _ENGINE_VERSION = version("pyguara")
except PackageNotFoundError:  # pragma: no cover - only when run uninstalled
    _ENGINE_VERSION = "0.0.0"


class PersistenceManager:
    """Coordinator for the data persistence subsystem.

    Orchestrates serialization, integrity checking and storage, acting as
    the facade the rest of the engine uses to save and load data.

    A save is written as a single blob: a one-line JSON metadata header,
    a newline, then the serialized (and optionally compressed) payload.
    The storage backend only has to make that one blob durable, so there is
    no window in which metadata and payload can disagree.

    Attributes:
        storage: The backend blob store.
        serializer: The serialization handler.
        migration_manager: Optional manager for schema migrations.
    """

    def __init__(
        self,
        storage_backend: StorageBackend,
        migration_manager: MigrationManager | None = None,
    ):
        """Initialize the persistence manager.

        Args:
            storage_backend: The concrete blob store to persist to.
            migration_manager: Optional manager for handling schema
                migrations on load.
        """
        self.storage = storage_backend
        self.serializer = Serializer(default_format=SerializationFormat.JSON)
        self.migration_manager = migration_manager

    def save_data(
        self,
        key: str,
        data: Any,
        save_version: int = 1,
        compress: bool = False,
        fmt: SerializationFormat = SerializationFormat.JSON,
    ) -> bool:
        """Save an object to storage.

        Serializes the object, records integrity and schema metadata, and
        writes the result as one atomic blob.

        Args:
            key: Unique identifier for this save data (e.g. "player_save_1").
            data: The object to save.
            save_version: The schema version of the data, for migrations.
            compress: If True, gzip the serialized payload before writing.
            fmt: Serialization format. JSON (the default) stays
                human-readable; MSGPACK is more compact; BINARY (pickle)
                handles arbitrary objects but must only be loaded from
                trusted files.

        Returns:
            True if the blob was written, False if serialization or the
            storage write failed.
        """
        try:
            payload = self.serializer.serialize(data, format_type=fmt)
            if compress:
                payload = gzip.compress(payload)

            metadata = SaveMetadata(
                version=_ENGINE_VERSION,
                timestamp=datetime.now(timezone.utc),  # noqa: UP017 (mypy py3.10)
                data_type=type(data).__name__,
                checksum=hashlib.md5(payload).hexdigest(),  # noqa: S324
                save_version=save_version,
                format=fmt.value,
                compressed=compress,
            )
            blob = self._frame(metadata, payload)
        except Exception as e:
            logger.error(f"Failed to serialize data '{key}': {e}", exc_info=True)
            return False

        if not self.storage.save(key, blob):
            logger.error(f"Storage backend rejected write for '{key}'")
            return False

        logger.info(f"Successfully saved data '{key}'")
        return True

    def load_data(self, key: str, verify_integrity: bool = True) -> Any | None:
        """Load an object from storage.

        Args:
            key: Unique identifier for the save data.
            verify_integrity: If True, validate the payload's MD5 checksum
                before deserializing.

        Returns:
            The deserialized object, or None if the key is absent, the blob
            is corrupt, or a migration failed.
        """
        try:
            blob = self.storage.load(key)
            if blob is None:
                logger.warning(f"No data found for key '{key}'")
                return None

            meta_dict, payload = self._unframe(blob)

            if verify_integrity:
                stored = meta_dict.get("checksum")
                calculated = hashlib.md5(payload).hexdigest()  # noqa: S324
                if stored != calculated:
                    logger.error(
                        f"Integrity check failed for '{key}'. File may be corrupted."
                    )
                    return None

            if meta_dict.get("compressed"):
                payload = gzip.decompress(payload)

            fmt = SerializationFormat(meta_dict.get("format", "json"))
            data = self.serializer.deserialize(payload, format_type=fmt)

            if self.migration_manager and isinstance(data, dict):
                save_version = meta_dict.get("save_version", 1)
                if self.migration_manager.needs_migration(save_version):
                    logger.info(
                        f"Migrating save data '{key}' from v{save_version} "
                        f"to v{self.migration_manager.current_version}"
                    )
                    data = self.migration_manager.migrate(data, save_version)

            return data

        except Exception as e:
            logger.error(f"Failed to load data '{key}': {e}", exc_info=True)
            return None

    @staticmethod
    def _frame(metadata: SaveMetadata, payload: bytes) -> bytes:
        """Combine metadata and payload into one blob.

        Args:
            metadata: The save metadata.
            payload: The serialized (and optionally compressed) payload.

        Returns:
            ``<header json><newline><payload bytes>``.
        """
        meta_dict = asdict(metadata)
        meta_dict["timestamp"] = metadata.timestamp.isoformat()
        header = json.dumps(meta_dict, separators=(",", ":")).encode("utf-8")
        return header + _HEADER_SEP + payload

    @staticmethod
    def _unframe(blob: bytes) -> tuple[dict[str, Any], bytes]:
        """Split a blob back into its metadata dict and payload bytes.

        Args:
            blob: A blob produced by :meth:`_frame`.

        Returns:
            ``(metadata_dict, payload_bytes)``.

        Raises:
            ValueError: If the blob has no header separator.
        """
        header, sep, payload = blob.partition(_HEADER_SEP)
        if not sep:
            raise ValueError("Save blob is missing its metadata header")
        return json.loads(header.decode("utf-8")), payload
