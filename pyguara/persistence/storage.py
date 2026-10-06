"""Concrete storage backend implementations."""

import contextlib
import os
import tempfile
from datetime import UTC, datetime

from pyguara.log import get_logger

logger = get_logger(__name__)

_TEMP_PREFIX = ".tmp_"

# `{key}.save.bak` holds the value this key had before the most recent
# write, so a save that is valid-but-unreadable (bit-rot, a bad migration,
# an interrupted disk) is not the end of the run. Deliberately *not* ending
# in `.save`, so `list_keys()` cannot report a backup as a save of its own.
_BACKUP_SUFFIX = ".bak"

# A primary that failed to decode is moved aside under this suffix rather
# than deleted, so it can still be inspected after the fact.
_CORRUPT_SUFFIX = ".corrupt"


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

    Each write also keeps the previous value as ``{key}.save.bak``, which
    `PersistenceManager` falls back to when the primary will not decode.
    The atomic rename already prevents a *torn* write; a backup is what
    covers a write that completed and is still unusable.

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
        self._rotate_backup(path, key)
        try:
            _atomic_write_bytes(path, blob)
            logger.debug("Saved '%s' (%d bytes)", key, len(blob))
            return True
        except OSError as e:
            logger.error("Save failed for '%s': %s", key, e, exc_info=True)
            return False

    def _rotate_backup(self, path: str, key: str) -> None:
        """Copy the current value of `key` to its backup slot.

        Copied rather than renamed: a rename would leave no primary at all
        if the write that follows then failed, turning a failed save into a
        missing one. A copy means the worst case is a backup identical to
        the primary.

        A failure here is logged and ignored -- losing the backup is worth
        strictly less than refusing the save.

        Args:
            path: The primary file's path.
            key: The storage key, for logging.
        """
        if not os.path.exists(path):
            return
        try:
            with open(path, "rb") as f:
                previous = f.read()
            _atomic_write_bytes(path + _BACKUP_SUFFIX, previous)
        except OSError as e:
            logger.warning("Could not back up '%s' before overwriting: %s", key, e)

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
        # The backup goes with it. Leaving it behind would let a later
        # `load` recover data the caller asked to be gone.
        with contextlib.suppress(OSError):
            os.remove(path + _BACKUP_SUFFIX)
        try:
            os.remove(path)
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.error("Delete failed for '%s': %s", key, e, exc_info=True)
            return False
        logger.debug("Deleted '%s'", key)
        return True

    def load_backup(self, key: str) -> bytes | None:
        """Return the value this key held before the most recent write.

        Args:
            key: Unique identifier for the data.

        Returns:
            The backed-up bytes, or None if there is no backup.

        Raises:
            ValueError: If the key is not filesystem-safe.
        """
        path = self._path_for(key) + _BACKUP_SUFFIX
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError as e:
            logger.error("Backup read failed for '%s': %s", key, e)
            return None

    def quarantine(self, key: str) -> str | None:
        """Move an unreadable primary aside, keeping it for inspection.

        Named with a timestamp so repeated failures do not overwrite each
        other, and with a suffix that `list_keys()` ignores.

        Args:
            key: Unique identifier for the data.

        Returns:
            The path the file was moved to, or None if there was nothing to
            move or the move failed.

        Raises:
            ValueError: If the key is not filesystem-safe.
        """
        path = self._path_for(key)
        if not os.path.exists(path):
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        target = f"{path}{_CORRUPT_SUFFIX}.{stamp}"
        try:
            os.replace(path, target)
        except OSError as e:
            logger.error("Could not quarantine '%s': %s", key, e)
            return None
        logger.warning("Quarantined unreadable save '%s' to %s", key, target)
        return target

    def load_header(self, key: str, max_bytes: int = 64 * 1024) -> bytes | None:
        """Return the blob's first line without reading the whole file.

        What a save menu needs: the metadata header is the first line of
        every blob, so listing twenty slots should not mean deserialising
        twenty payloads.

        Args:
            key: Unique identifier for the data.
            max_bytes: Give up after this many bytes without finding a
                newline, rather than reading a whole corrupt file into
                memory looking for one.

        Returns:
            The bytes before the first newline, or None if the key is
            absent, unreadable, or has no newline within `max_bytes`.

        Raises:
            ValueError: If the key is not filesystem-safe.
        """
        path = self._path_for(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                chunk = f.read(max_bytes)
        except OSError as e:
            logger.error("Header read failed for '%s': %s", key, e)
            return None
        header, sep, _rest = chunk.partition(b"\n")
        if not sep:
            return None
        return header

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
