"""Asset hot-reload: watch loaded assets on disk and re-import them live.

Bridges :class:`~pyguara.dev.file_watcher.PollingFileWatcher` to
:meth:`ResourceManager.reload`. A file change is detected on the watcher's
polling thread, queued, and applied on the thread that calls :meth:`drain`
-- the game loop -- because ``ResourceManager`` is not safe to mutate from
under a running frame.

Development-only. Off by default; ``Application.enable_asset_hot_reload()``
turns it on and ``SandboxApplication`` calls that automatically.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from pyguara.dev.file_watcher import PollingFileWatcher
from pyguara.log import get_logger
from pyguara.resources.manager import ResourceManager

logger = get_logger(__name__)

# Seconds between reconciliations of the watch set with the resource cache.
_REFRESH_INTERVAL = 1.0


class AssetReloadWatcher:
    """Watches every loaded asset's file and reloads it when it changes.

    The watch set follows the ``ResourceManager`` cache: :meth:`drain`
    periodically reconciles it, so assets loaded after :meth:`start` are
    picked up and evicted ones are dropped.

    Callers that already hold the *previous* resource instance keep that
    stale object -- ``reload()`` swaps the cache entry, it does not mutate
    the old one. Re-``load()`` after a reload to pick up the new instance.

    Example:
        watcher = AssetReloadWatcher(resource_manager)
        watcher.start()
        # each frame, on the main thread:
        reloaded = watcher.drain()
        ...
        watcher.stop()
    """

    def __init__(
        self, resource_manager: ResourceManager, poll_interval: float = 0.5
    ) -> None:
        """Initialize the watcher.

        Args:
            resource_manager: The manager whose cached resources to watch.
            poll_interval: Seconds between file-modification polls.
        """
        self._rm = resource_manager
        self._watcher = PollingFileWatcher(poll_interval=poll_interval)
        self._lock = threading.Lock()
        # Absolute file path -> resource cache key.
        self._watched: dict[str, str] = {}
        # Cache keys with a detected change, awaiting drain() on the main thread.
        self._pending: list[str] = []
        self._last_refresh = 0.0

    @property
    def is_running(self) -> bool:
        """Whether the underlying file watcher thread is running."""
        return self._watcher.is_running

    @property
    def pending_count(self) -> int:
        """Number of changed assets queued for the next :meth:`drain`."""
        with self._lock:
            return len(self._pending)

    def start(self) -> None:
        """Reconcile the watch set and start polling."""
        self.refresh()
        self._watcher.start()
        logger.info("Asset hot-reload watching %d file(s)", len(self._watched))

    def stop(self) -> None:
        """Stop polling and drop any queued reloads. Idempotent."""
        self._watcher.stop()
        with self._lock:
            self._pending.clear()

    def refresh(self) -> None:
        """Reconcile the watch set with the current ``ResourceManager`` cache.

        Assets whose file exists on disk are watched; entries for resources
        no longer cached are dropped. Called automatically from :meth:`start`
        and throttled inside :meth:`drain`; safe to call directly.
        """
        current: dict[str, str] = {}
        for key, resource in self._rm.iter_cached():
            try:
                path = Path(resource.path)
            except (TypeError, ValueError):
                continue
            if path.is_file():
                current[str(path.resolve())] = key

        with self._lock:
            previous = self._watched
            self._watched = current

        for abspath in previous.keys() - current.keys():
            self._watcher.unwatch(abspath)
        for abspath in current.keys() - previous.keys():
            self._watcher.watch(abspath, self._on_file_changed)
        self._last_refresh = time.monotonic()

    def drain(self) -> list[str]:
        """Apply queued reloads. Call once per frame, on the main thread.

        Returns:
            The cache keys successfully reloaded this call.
        """
        if time.monotonic() - self._last_refresh >= _REFRESH_INTERVAL:
            self.refresh()

        with self._lock:
            pending = self._pending
            self._pending = []

        reloaded: list[str] = []
        for key in dict.fromkeys(pending):  # de-dup, preserve order
            try:
                self._rm.reload(key)
            except KeyError:
                # Unloaded between the change and now -- nothing to reload.
                continue
            except (ValueError, TypeError) as exc:
                logger.error("Asset hot-reload failed for %s: %s", key, exc)
                continue
            logger.info("Hot-reloaded asset: %s", key)
            reloaded.append(key)
        return reloaded

    def _on_file_changed(self, abspath: str) -> None:
        """Watcher-thread callback: queue the asset's key for the next drain."""
        with self._lock:
            key = self._watched.get(abspath)
            if key is not None and key not in self._pending:
                self._pending.append(key)
