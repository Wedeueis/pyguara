"""File watching for hot-reloading.

Monitors files for changes to trigger hot-reload.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Type alias for change callback
ChangeCallback = Callable[[str], None]


@dataclass
class WatchedFile:
    """Information about a watched file.

    Attributes:
        path: Absolute path to the file.
        last_modified: Last modification time.
        last_size: Last file size.
    """

    path: str
    last_modified: float = 0.0
    last_size: int = 0

    def has_changed(self) -> bool:
        """Check if the file has changed since last check.

        Returns:
            True if file has been modified.
        """
        try:
            stat = os.stat(self.path)
            modified = stat.st_mtime
            size = stat.st_size

            if modified != self.last_modified or size != self.last_size:
                self.last_modified = modified
                self.last_size = size
                return True

            return False
        except OSError:
            return False

    @classmethod
    def from_path(cls, path: str) -> WatchedFile:
        """Create a WatchedFile from a path.

        Args:
            path: Path to the file.

        Returns:
            New WatchedFile instance.
        """
        instance = cls(path=str(Path(path).absolute()))
        # Initialize with current state
        try:
            stat = os.stat(instance.path)
            instance.last_modified = stat.st_mtime
            instance.last_size = stat.st_size
        except OSError:
            pass
        return instance


class PollingFileWatcher:
    """Watches files for changes using polling.

    A simple, cross-platform file watcher that periodically checks
    file modification times. Less efficient than OS-level notifications
    but works everywhere.

    Example:
        watcher = PollingFileWatcher(poll_interval=0.5)
        watcher.watch("path/to/file.py", on_change_callback)
        watcher.start()
        # ...
        watcher.stop()
    """

    def __init__(self, poll_interval: float = 0.5) -> None:
        """Initialize the file watcher.

        Args:
            poll_interval: Seconds between polls.
        """
        self._poll_interval = poll_interval
        self._watched_files: Dict[str, WatchedFile] = {}
        self._callbacks: Dict[str, List[ChangeCallback]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._running

    @property
    def watched_count(self) -> int:
        """Get number of watched files."""
        with self._lock:
            return len(self._watched_files)

    def watch(
        self,
        path: str,
        callback: ChangeCallback,
    ) -> bool:
        """Start watching a file.

        Args:
            path: Path to the file to watch.
            callback: Function to call when file changes.

        Returns:
            True if watch was added successfully.
        """
        abs_path = str(Path(path).absolute())

        if not Path(abs_path).exists():
            logger.warning(f"File does not exist: {path}")
            return False

        with self._lock:
            if abs_path not in self._watched_files:
                self._watched_files[abs_path] = WatchedFile.from_path(abs_path)
                self._callbacks[abs_path] = []

            if callback not in self._callbacks[abs_path]:
                self._callbacks[abs_path].append(callback)

        logger.debug(f"Watching file: {abs_path}")
        return True

    def unwatch(self, path: str, callback: Optional[ChangeCallback] = None) -> None:
        """Stop watching a file.

        Args:
            path: Path to the file.
            callback: Specific callback to remove. If None, removes all.
        """
        abs_path = str(Path(path).absolute())

        with self._lock:
            if abs_path not in self._watched_files:
                return

            if callback is None:
                # Remove all
                del self._watched_files[abs_path]
                del self._callbacks[abs_path]
            else:
                # Remove specific callback
                if callback in self._callbacks[abs_path]:
                    self._callbacks[abs_path].remove(callback)

                # If no callbacks left, stop watching
                if not self._callbacks[abs_path]:
                    del self._watched_files[abs_path]
                    del self._callbacks[abs_path]

        logger.debug(f"Stopped watching: {abs_path}")

    def watch_directory(
        self,
        directory: str,
        callback: ChangeCallback,
        pattern: str = "*.py",
        recursive: bool = True,
    ) -> int:
        """Watch all matching files in a directory.

        Args:
            directory: Directory path.
            callback: Function to call when any file changes.
            pattern: Glob pattern for files to watch.
            recursive: Whether to watch subdirectories.

        Returns:
            Number of files being watched.
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning(f"Directory does not exist: {directory}")
            return 0

        if recursive:
            files = dir_path.rglob(pattern)
        else:
            files = dir_path.glob(pattern)

        count = 0
        for file_path in files:
            if file_path.is_file():
                if self.watch(str(file_path), callback):
                    count += 1

        logger.info(f"Watching {count} files in {directory}")
        return count

    def start(self) -> None:
        """Start the file watching thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

        logger.info("File watcher started")

    def stop(self) -> None:
        """Stop the file watching thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        logger.info("File watcher stopped")

    def check_now(self) -> List[str]:
        """Manually check all watched files for changes.

        Returns:
            List of changed file paths.
        """
        changed: List[str] = []

        with self._lock:
            for path, watched in self._watched_files.items():
                if watched.has_changed():
                    changed.append(path)
                    self._notify_change(path)

        return changed

    def _poll_loop(self) -> None:
        """Poll files for changes in a loop (runs in thread)."""
        while self._running:
            self.check_now()
            time.sleep(self._poll_interval)

    def _notify_change(self, path: str) -> None:
        """Notify callbacks of a file change.

        Args:
            path: Path of the changed file.
        """
        callbacks = self._callbacks.get(path, [])

        for callback in callbacks:
            try:
                callback(path)
            except Exception as e:
                logger.error(f"Error in file change callback: {e}")


class FileChangeEvent:
    """Event representing a file change."""

    def __init__(self, path: str, change_type: str = "modified") -> None:
        """Initialize the event.

        Args:
            path: Path to the changed file.
            change_type: Type of change (modified, created, deleted).
        """
        self.path = path
        self.change_type = change_type
        self.timestamp = time.time()
