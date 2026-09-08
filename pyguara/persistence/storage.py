"""Concrete storage backend implementations."""

import contextlib
import os
import tempfile

from pyguara.log import get_logger

logger = get_logger(__name__)

_TEMP_PREFIX = ".tmp_"


def _atomic_write_bytes(path: str, data: bytes) -> None:
    """Atomically write bytes to a file using write-to-temp-then-rename.

    This ensures that the target file is never left in a partial state.
    If a crash occurs during the write, only the temp file is affected;
    the previous contents of ``path`` remain intact until the rename.

    Args:
        path: The target file path.
        data: The bytes to write.

    Raises:
        OSError: If the write or rename fails.
    """
    dir_path = os.path.dirname(path) or "."

    # Create temp file in the same directory to ensure same filesystem
    fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix=_TEMP_PREFIX)
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

    # Flush the rename itself so the swap survives a crash, not just the
    # bytes inside the file.
    try:
        dir_fd = os.open(dir_path, os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        # Directory fsync is a durability nicety; platforms without
        # O_DIRECTORY (or where it is not permitted) still get the rename.
        pass


class FileStorageBackend:
    """Storage backend that saves each key as one file on the local disk.

    Each key maps to a single ``{key}.save`` file under ``base_path``,
    written with an atomic temp-file-then-rename so a crash mid-write never
    corrupts the previous value.

    Keys must be filesystem-safe as given: alphanumerics, ``_`` and ``-``.
    A key that would need rewriting to be safe is rejected with
    ``ValueError`` rather than silently mangled -- two keys that sanitise to
    the same name would otherwise overwrite each other.
    """

    SUFFIX = ".save"

    def __init__(self, base_path: str = "saves") -> None:
        """Initialize the file storage.

        Args:
            base_path: Directory where files will be stored. Created if
                absent.
        """
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        self._sweep_temp_files()

    def _sweep_temp_files(self) -> None:
        """Remove orphaned temp files left by a crashed write."""
        try:
            entries = os.listdir(self.base_path)
        except OSError:
            return
        for name in entries:
            if name.startswith(_TEMP_PREFIX):
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(self.base_path, name))

    def _path_for(self, key: str) -> str:
        """Return the file path for a key, validating the key first.

        Args:
            key: The storage key.

        Returns:
            Absolute-or-relative path to the key's ``.save`` file.

        Raises:
            ValueError: If the key is empty or contains characters that are
                not alphanumeric, ``_`` or ``-``.
        """
        if not key:
            raise ValueError("Storage key must be a non-empty string")
        if any(not (c.isalnum() or c in ("_", "-")) for c in key):
            raise ValueError(
                f"Invalid storage key {key!r}: only letters, digits, '_' and "
                f"'-' are allowed (no spaces, dots or path separators)"
            )
        return os.path.join(self.base_path, f"{key}{self.SUFFIX}")

    def save(self, key: str, blob: bytes) -> bool:
        """Write a blob to disk atomically.

        Args:
            key: Unique identifier for the data.
            blob: The bytes to store.

        Returns:
            True if the write succeeded, False on an OS-level failure.

        Raises:
            ValueError: If the key is not filesystem-safe.
        """
        path = self._path_for(key)
        try:
            _atomic_write_bytes(path, blob)
            logger.debug("Saved '%s' (%d bytes)", key, len(blob))
            return True
        except OSError as e:
            logger.error("Save failed for '%s': %s", key, e, exc_info=True)
            return False

    def load(self, key: str) -> bytes | None:
        """Read the blob stored under a key.

        Args:
            key: Unique identifier for the data.

        Returns:
            The stored bytes, or None if the file is absent or unreadable.

        Raises:
            ValueError: If the key is not filesystem-safe.
        """
        path = self._path_for(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                blob = f.read()
            logger.debug("Loaded '%s' (%d bytes)", key, len(blob))
            return blob
        except OSError as e:
            logger.error("Load failed for '%s': %s", key, e, exc_info=True)
            return None

    def delete(self, key: str) -> bool:
        """Delete the file for a key.

        Args:
            key: Unique identifier for the data to delete.

        Returns:
            True if a file was removed, False if it was already absent.

        Raises:
            ValueError: If the key is not filesystem-safe.
        """
        path = self._path_for(key)
        try:
            os.remove(path)
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.error("Delete failed for '%s': %s", key, e, exc_info=True)
            return False
        logger.debug("Deleted '%s'", key)
        return True

    def list_keys(self) -> list[str]:
        """List all keys currently present in storage.

        Returns:
            Key names (files ending in ``.save``, suffix stripped).
        """
        try:
            entries = os.listdir(self.base_path)
        except OSError:
            return []
        return [n[: -len(self.SUFFIX)] for n in entries if n.endswith(self.SUFFIX)]
