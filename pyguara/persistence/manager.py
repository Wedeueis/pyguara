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
from pyguara.persistence.types import (
    BackupCapableStorage,
    HeaderReadableStorage,
    SaveMetadata,
    SerializationFormat,
    StorageBackend,
)

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
        blob = self.storage.load(key)
        if blob is None:
            logger.warning(f"No data found for key '{key}'")
            return None

        try:
            return self._decode(key, blob, verify_integrity)
        except Exception as primary_error:
            logger.error(f"Failed to load data '{key}': {primary_error}")
            return self._recover_from_backup(key, verify_integrity)

    def _recover_from_backup(self, key: str, verify_integrity: bool) -> Any | None:
        """Try the previous value of `key` after the primary failed to decode.

        The atomic write already rules out a torn file, so a primary that
        will not decode means something worse: bit-rot, a half-finished
        migration, a disk that lied. For a permadeath roguelike that is the
        difference between a lost run and a recovered one.

        On success the corrupt primary is quarantined and the backup is
        promoted in its place, so the *next* load does not have to repeat
        this -- a read that silently left the broken file in place would
        fail again every time.

        Args:
            key: Unique identifier for the data.
            verify_integrity: Passed through to the decode.

        Returns:
            The recovered object, or None if there is no usable backup.
        """
        if not isinstance(self.storage, BackupCapableStorage):
            return None

        backup = self.storage.load_backup(key)
        if backup is None:
            logger.error(f"No backup available for '{key}'; data is unrecoverable")
            return None

        try:
            data = self._decode(key, backup, verify_integrity)
        except Exception as backup_error:
            logger.error(f"Backup for '{key}' is also unusable: {backup_error}")
            return None

        logger.warning(
            f"Recovered '{key}' from its backup; the primary save was unreadable"
        )
        self.storage.quarantine(key)
        if not self.storage.save(key, backup):
            # The caller still gets its data; only the self-heal failed.
            logger.error(f"Could not promote the backup of '{key}' to primary")
        return data

    def _decode(self, key: str, blob: bytes, verify_integrity: bool) -> Any:
        """Turn one blob back into the object it was framed from.

        Raises rather than returning None so the caller can tell "this blob
        is bad" from "this blob held None", which is what makes falling
        back to a backup possible at all.

        Args:
            key: Unique identifier, for log messages.
            blob: The framed bytes.
            verify_integrity: Validate the payload checksum.

        Returns:
            The deserialized object, migrated if a migration applies.

        Raises:
            ValueError: If the header is missing or the checksum disagrees.
            Exception: Whatever decompression or deserialization raises.
        """
        meta_dict, payload = self._unframe(blob)

        if verify_integrity:
            stored = meta_dict.get("checksum")
            calculated = hashlib.md5(payload).hexdigest()  # noqa: S324
            if stored != calculated:
                raise ValueError(
                    f"Integrity check failed for '{key}': checksum {calculated} "
                    f"does not match the recorded {stored}"
                )

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

    def list_saves(self) -> list[str]:
        """Return every key currently in storage.

        Args:
            None.

        Returns:
            The keys, in whatever order the backend reports them.
        """
        return self.storage.list_keys()

    def exists(self, key: str) -> bool:
        """Whether a save exists under `key`.

        Args:
            key: Unique identifier for the save data.

        Returns:
            True if the backend holds a value for it.
        """
        return key in self.storage.list_keys()

    def delete(self, key: str) -> bool:
        """Delete the save stored under `key`.

        Here so callers stop reaching through `.storage` for it, which left
        the manager's facade half-complete and tied game code to the
        backend's own interface.

        Args:
            key: Unique identifier for the save data.

        Returns:
            True if something was removed, False if it was already absent.
        """
        return self.storage.delete(key)

    def read_metadata(self, key: str) -> SaveMetadata | None:
        """Return a save's metadata without deserializing its payload.

        What a load-game screen needs: slot timestamps and schema versions
        for a list of saves, at the cost of one short read each rather than
        a full decode each. Uses the backend's `load_header()` when it has
        one and falls back to reading the whole blob when it does not.

        The payload is never touched, so this answers for a save whose
        *data* is corrupt as long as the header survived.

        Args:
            key: Unique identifier for the save data.

        Returns:
            The metadata, or None if the key is absent or its header is
            unreadable.
        """
        header: bytes | None
        if isinstance(self.storage, HeaderReadableStorage):
            header = self.storage.load_header(key)
        else:
            blob = self.storage.load(key)
            header = None if blob is None else blob.partition(_HEADER_SEP)[0]

        if not header:
            return None

        try:
            raw = json.loads(header.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.error(f"Unreadable metadata header for '{key}': {e}")
            return None

        return self._metadata_from(key, raw)

    @staticmethod
    def _metadata_from(key: str, raw: dict[str, Any]) -> SaveMetadata | None:
        """Rebuild `SaveMetadata` from a decoded header.

        Only known fields are read, so a header written by a newer build
        with extra fields still loads instead of raising `TypeError` on an
        unexpected keyword.

        Args:
            key: Unique identifier, for log messages.
            raw: The decoded header mapping.

        Returns:
            The metadata, or None if a required field is missing or the
            timestamp will not parse.
        """
        try:
            return SaveMetadata(
                version=str(raw["version"]),
                timestamp=datetime.fromisoformat(raw["timestamp"]),
                data_type=str(raw["data_type"]),
                checksum=raw.get("checksum"),
                save_version=int(raw.get("save_version", 1)),
                format=str(raw.get("format", "json")),
                compressed=bool(raw.get("compressed", False)),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Malformed metadata header for '{key}': {e}")
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
