"""Concrete storage backend implementations."""

import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from pyguara.persistence.types import StorageBackend

logger = logging.getLogger(__name__)


def _atomic_write_bytes(path: str, data: bytes) -> None:
    """Atomically write bytes to a file using write-to-temp-then-rename.

    This ensures that the target file is never left in a partial state.
    If a crash occurs during the write, only the temp file is affected.

    Args:
        path: The target file path.
        data: The bytes to write.

    Raises:
        OSError: If the write or rename fails.
    """
    dir_path = os.path.dirname(path) or "."

    # Create temp file in the same directory to ensure same filesystem
    fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix=".tmp_")
    try:
        os.write(fd, data)
        os.fsync(fd)  # Ensure data is flushed to disk
        os.close(fd)
        fd = -1  # Mark as closed

        # Atomic rename (on POSIX systems)
        os.replace(temp_path, path)
    except Exception:
        # Clean up temp file on failure
        if fd >= 0:
            os.close(fd)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def _atomic_write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    """Atomically write text to a file using write-to-temp-then-rename.

    Args:
        path: The target file path.
        text: The text to write.
        encoding: The text encoding to use.

    Raises:
        OSError: If the write or rename fails.
    """
    _atomic_write_bytes(path, text.encode(encoding))


class FileStorageBackend(StorageBackend):
    """
    Storage backend that saves data to the local filesystem.

    Each 'key' maps to a file in the base directory.
    Format:
        {key}.dat -> Raw Data
        {key}.meta -> Metadata (JSON)

    Uses atomic writes to prevent data corruption on crash.
    """

    def __init__(self, base_path: str = "saves") -> None:
        """
        Initialize the file storage.

        Args:
            base_path: Directory where files will be stored.
        """
        self.base_path = base_path
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)

    def _get_paths(self, key: str) -> Tuple[str, str]:
        """Return (data_path, meta_path) for a given key."""
        # Sanitize key to avoid path traversal
        safe_key = "".join(c for c in key if c.isalnum() or c in ("_", "-"))
        return (
            os.path.join(self.base_path, f"{safe_key}.dat"),
            os.path.join(self.base_path, f"{safe_key}.meta"),
        )

    def save(self, key: str, data: bytes, metadata: Dict[str, Any]) -> bool:
        """Save data and metadata to disk atomically.

        Uses atomic writes to prevent data corruption. Both files are
        written to temporary files first, then atomically renamed.
        If a crash occurs during save, the previous version remains intact.

        Args:
            key: Unique identifier for the data.
            data: The raw binary data to store.
            metadata: Dictionary of metadata associated with the data.

        Returns:
            True if the save was successful, False otherwise.
        """
        data_path, meta_path = self._get_paths(key)

        try:
            # Write data file atomically first
            _atomic_write_bytes(data_path, data)

            # Write metadata file atomically
            meta_json = json.dumps(metadata, indent=4)
            _atomic_write_text(meta_path, meta_json)

            logger.debug("Saved '%s' (%d bytes)", key, len(data))
            return True
        except OSError as e:
            logger.error("Save failed for '%s': %s", key, e, exc_info=True)
            return False

    def load(self, key: str) -> Optional[tuple[bytes, Dict[str, Any]]]:
        """Load data and metadata from disk.

        Args:
            key: Unique identifier for the data.

        Returns:
            A tuple (data, metadata) if found and valid, None otherwise.
            Returns None if either file is missing (possibly corrupted save).
        """
        data_path, meta_path = self._get_paths(key)

        # Check both files exist (atomic save ensures both or neither)
        if not os.path.exists(data_path):
            if os.path.exists(meta_path):
                logger.warning(
                    "Corrupted save '%s': metadata exists but data missing", key
                )
            return None

        if not os.path.exists(meta_path):
            logger.warning("Corrupted save '%s': data exists but metadata missing", key)
            return None

        try:
            with open(data_path, "rb") as f:
                data = f.read()

            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            logger.debug("Loaded '%s' (%d bytes)", key, len(data))
            return data, meta
        except OSError as e:
            logger.error("Load failed for '%s': %s", key, e, exc_info=True)
            return None
        except json.JSONDecodeError as e:
            logger.error("Metadata corrupted for '%s': %s", key, e, exc_info=True)
            return None

    def delete(self, key: str) -> bool:
        """Delete data and metadata files for a key.

        Args:
            key: Unique identifier for the data to delete.

        Returns:
            True if at least the data file was deleted, False if not found.
        """
        data_path, meta_path = self._get_paths(key)

        success = False
        if os.path.exists(data_path):
            os.remove(data_path)
            success = True

        if os.path.exists(meta_path):
            os.remove(meta_path)

        if success:
            logger.debug("Deleted '%s'", key)

        return success

    def list_keys(self) -> List[str]:
        """List all available keys in storage.

        Returns:
            List of key names (based on .meta files present).
        """
        keys = []
        if not os.path.exists(self.base_path):
            return []

        for filename in os.listdir(self.base_path):
            if filename.endswith(".meta"):
                keys.append(filename[:-5])
        return keys
