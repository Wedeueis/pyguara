"""Saving during play must never stall the caller, and must never lose the newest."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.multi_scope import MultiScopePersistence
from pyguara.persistence.quick_save import QuickSaver
from pyguara.persistence.storage import FileStorageBackend


class RecordingStorage:
    """A disk as slow as a test wants, which remembers what reached it."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.fail = False
        self.blobs: dict[str, bytes] = {}
        self.write_count = 0
        self.gate: threading.Event | None = None

    def save(self, key: str, blob: bytes) -> bool:
        if self.gate is not None:
            self.gate.wait(timeout=10)
        time.sleep(self.delay)
        self.write_count += 1
        if self.fail:
            return False
        self.blobs[key] = blob
        return True

    def load(self, key: str) -> bytes | None:
        return self.blobs.get(key)

    def delete(self, key: str) -> bool:
        return self.blobs.pop(key, None) is not None

    def list_keys(self) -> list[str]:
        return list(self.blobs)


def saver_on(storage: Any, min_interval: float = 0.0) -> tuple[QuickSaver, Any]:
    manager = PersistenceManager(storage)
    return QuickSaver(manager, min_interval=min_interval), manager


def test_a_request_does_not_wait_for_a_slow_disk() -> None:
    disk_delay = 0.3
    storage = RecordingStorage(delay=disk_delay)
    saver, _ = saver_on(storage)

    began = time.perf_counter()
    for level in range(100):
        saver.request("character", {"level": level})
    spent = time.perf_counter() - began

    assert spent < disk_delay / 3
    saver.close()


def test_a_request_does_not_wait_while_a_write_is_in_progress() -> None:
    storage = RecordingStorage()
    storage.gate = threading.Event()
    saver, _ = saver_on(storage)
    saver.request("character", {"level": 1})
    time.sleep(0.02)

    began = time.perf_counter()
    saver.request("character", {"level": 2})
    spent = time.perf_counter() - began

    assert spent < 0.05
    storage.gate.set()
    assert saver.close()


def test_a_burst_coalesces_and_the_newest_value_wins() -> None:
    storage = RecordingStorage()
    storage.gate = threading.Event()
    saver, manager = saver_on(storage)

    for level in range(1000):
        saver.request("character", {"level": level})
    storage.gate.set()
    assert saver.flush(timeout=5)

    assert storage.write_count <= 2
    assert manager.load_data("character") == {"level": 999}
    saver.close()


def test_writes_of_one_key_respect_the_interval() -> None:
    storage = RecordingStorage()
    saver, manager = saver_on(storage, min_interval=0.2)

    deadline = time.monotonic() + 0.5
    level = 0
    while time.monotonic() < deadline:
        saver.request("character", {"level": level})
        level += 1
        time.sleep(0.005)

    assert 1 <= storage.write_count <= 4
    assert saver.close()
    assert manager.load_data("character") == {"level": level - 1}


def test_one_key_does_not_hold_back_another() -> None:
    storage = RecordingStorage()
    saver, manager = saver_on(storage, min_interval=60.0)
    saver.request("a", {"v": 1})
    time.sleep(0.05)
    saver.request("a", {"v": 2})
    saver.request("b", {"v": 3})
    time.sleep(0.1)

    assert manager.load_data("b") == {"v": 3}
    assert manager.load_data("a") == {"v": 1}
    assert saver.flush(timeout=5)
    assert manager.load_data("a") == {"v": 2}
    saver.close()


def test_flush_ignores_the_interval() -> None:
    storage = RecordingStorage()
    saver, manager = saver_on(storage, min_interval=3600.0)
    saver.request("character", {"level": 1})
    assert saver.flush(timeout=5)
    saver.request("character", {"level": 2})

    assert saver.flush(timeout=5)

    assert manager.load_data("character") == {"level": 2}
    saver.close()


def test_close_writes_what_is_outstanding() -> None:
    storage = RecordingStorage()
    saver, manager = saver_on(storage, min_interval=3600.0)
    saver.request("character", {"level": 1})
    time.sleep(0.05)
    saver.request("character", {"level": 2})

    assert saver.close(timeout=5)

    assert manager.load_data("character") == {"level": 2}


def test_flush_reports_a_timeout_rather_than_blocking_forever() -> None:
    storage = RecordingStorage()
    storage.gate = threading.Event()
    saver, _ = saver_on(storage)
    saver.request("character", {"level": 1})

    assert saver.flush(timeout=0.05) is False

    storage.gate.set()
    assert saver.close(timeout=5)


def test_a_failed_write_is_counted_and_retried_without_losing_the_value() -> None:
    storage = RecordingStorage()
    storage.fail = True
    saver, manager = saver_on(storage, min_interval=0.01)
    saver.request("character", {"level": 7})
    deadline = time.monotonic() + 2
    while saver.failures == 0 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert saver.failures >= 1

    storage.fail = False
    deadline = time.monotonic() + 2
    while saver.writes == 0 and time.monotonic() < deadline:
        time.sleep(0.005)

    assert manager.load_data("character") == {"level": 7}
    saver.close()


def test_an_unserializable_value_does_not_end_the_worker() -> None:
    storage = RecordingStorage()
    saver, manager = saver_on(storage, min_interval=0.0)
    saver.request("bad", object())
    saver.request("good", {"v": 1})
    deadline = time.monotonic() + 2
    while saver.writes == 0 and time.monotonic() < deadline:
        time.sleep(0.005)

    assert manager.load_data("good") == {"v": 1}
    assert saver.failures >= 1
    saver.close(timeout=5)


def test_requesting_after_close_is_an_error() -> None:
    saver, _ = saver_on(RecordingStorage())
    saver.close()
    with pytest.raises(RuntimeError, match="closed"):
        saver.request("character", {})


def test_closing_twice_is_harmless() -> None:
    saver, _ = saver_on(RecordingStorage())
    assert saver.close()
    assert saver.close()


def test_it_writes_a_real_loadable_file(tmp_path: Path) -> None:
    manager = PersistenceManager(FileStorageBackend(str(tmp_path)))
    saver = QuickSaver(manager)
    saver.request("character", {"level": 3, "gear": ["sword"]})
    assert saver.close(timeout=10)

    reloaded = PersistenceManager(FileStorageBackend(str(tmp_path)))

    assert reloaded.load_data("character") == {"level": 3, "gear": ["sword"]}


def test_it_fits_a_scope_of_multi_scope_persistence(tmp_path: Path) -> None:
    scopes = MultiScopePersistence.from_directories(
        str(tmp_path), ["meta", "character"]
    )
    saver = QuickSaver(scopes.store("character"))
    saver.request("slot1", {"xp": 10})
    assert saver.close(timeout=10)

    assert scopes.store("character").load_data("slot1") == {"xp": 10}
    assert scopes.store("meta").load_data("slot1") is None
