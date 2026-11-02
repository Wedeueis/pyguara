"""Saving during play, without stalling a frame.

`PersistenceManager.save_data` serializes and fsyncs on the calling thread, which
is right for a save menu and wrong for a save triggered by gameplay: one fsync can
cost more than a frame. This does that work on a worker thread instead, and writes
only the newest value for a key, so a burst of XP events costs one write.

Crash safety comes from the storage underneath, which writes atomically. So a crash
loses at most the last `min_interval`, and never corrupts a save.

    saver = QuickSaver(persistence, min_interval=1.0)
    saver.request("character", character.to_save_data())   # cheap, each event
    saver.flush()                                          # at the end of a run
    saver.close()                                          # at shutdown
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from pyguara.log import get_logger
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.types import SerializationFormat

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _Pending:
    data: Any
    save_version: int
    fmt: SerializationFormat


class QuickSaver:
    """Writes saves on a worker thread, newest value wins.

    **Hand over a value you will not mutate.** It is serialized later, on another
    thread, so a live object changed in the meantime would be saved half-updated.
    Build a fresh plain structure, which is cheap for the size of a character.

    Attributes:
        writes: How many saves have reached storage.
        failures: How many writes failed. The newest failed value is retried by the
            next `request` or `flush`.
    """

    def __init__(self, persistence: PersistenceManager, min_interval: float = 1.0):
        """Start the worker.

        Args:
            persistence: Where saves go.
            min_interval: Fewest seconds between writes of one key. A crash can lose
                this much progress, so it is the trade against disk work.
        """
        self.writes = 0
        self.failures = 0
        self._persistence = persistence
        self._min_interval = min_interval
        self._pending: dict[str, _Pending] = {}
        self._last_write: dict[str, float] = {}
        self._writing = False
        self._closed = False
        self._flushing = False
        self._condition = threading.Condition()
        self._thread = threading.Thread(
            target=self._run, name="pyguara-quick-save", daemon=True
        )
        self._thread.start()

    def request(
        self,
        key: str,
        data: Any,
        save_version: int = 1,
        fmt: SerializationFormat = SerializationFormat.JSON,
    ) -> None:
        """Ask for `data` to be saved. Returns at once, whatever the disk is doing.

        Args:
            key: The save's key.
            data: A value this caller will not mutate afterwards.
            save_version: The schema version, for migrations.
            fmt: Serialization format.

        Raises:
            RuntimeError: If the saver has been closed.
        """
        with self._condition:
            if self._closed:
                raise RuntimeError("This QuickSaver has been closed")
            self._pending[key] = _Pending(data, save_version, fmt)
            self._condition.notify_all()

    def flush(self, timeout: float | None = None) -> bool:
        """Block until everything requested so far is written, ignoring the interval.

        For the end of a run, or anywhere a stall is acceptable.

        Args:
            timeout: Seconds to wait, or None to wait as long as it takes.

        Returns:
            True if everything was written, False on a timeout or a failed write.
        """
        failures_before = self.failures
        with self._condition:
            self._flushing = True
            self._condition.notify_all()
            finished = self._condition.wait_for(
                lambda: not self._pending and not self._writing, timeout
            )
            self._flushing = False
        return finished and self.failures == failures_before

    def close(self, timeout: float | None = None) -> bool:
        """Write everything outstanding and stop the worker. Safe to call twice.

        Args:
            timeout: Seconds to wait, or None to wait as long as it takes.

        Returns:
            True if everything was written.
        """
        failures_before = self.failures
        with self._condition:
            already_closed = self._closed
            self._closed = True
            self._condition.notify_all()
        self._thread.join(timeout)
        return (
            not self._thread.is_alive()
            and not self._pending
            and (already_closed or self.failures == failures_before)
        )

    def _next_due(self, now: float) -> tuple[str | None, float | None]:
        """Pick a key that may be written now, or say how long until one may."""
        if self._flushing or self._closed:
            return next(iter(self._pending), None), None
        soonest = None
        for key in self._pending:
            due = self._last_write.get(key, -self._min_interval) + self._min_interval
            if due <= now:
                return key, None
            soonest = due if soonest is None else min(soonest, due)
        return None, None if soonest is None else soonest - now

    def _run(self) -> None:
        while True:
            with self._condition:
                while True:
                    key, wait = self._next_due(time.monotonic())
                    if key is not None:
                        break
                    if self._closed:
                        return
                    self._condition.wait(wait)
                pending = self._pending.pop(key)
                self._writing = True
            self._write(key, pending)
            with self._condition:
                self._writing = False
                self._condition.notify_all()

    def _write(self, key: str, pending: _Pending) -> None:
        try:
            saved = self._persistence.save_data(
                key, pending.data, save_version=pending.save_version, fmt=pending.fmt
            )
        except Exception:  # noqa: BLE001 - a save failing must not end the worker
            logger.error("Quick save of '%s' failed", key, exc_info=True)
            saved = False
        with self._condition:
            self._last_write[key] = time.monotonic()
            if saved:
                self.writes += 1
                return
            self.failures += 1
            # Keep the newest value, so a full disk that clears loses nothing,
            # unless a newer one already arrived or nothing is coming to retry it.
            if not self._closed and not self._flushing:
                self._pending.setdefault(key, pending)
