"""Tests for pyguara.dev -- the file watcher and asset hot-reload."""

import json
import threading
import time
from pathlib import Path

import pytest

from pyguara.dev.asset_reload import AssetReloadWatcher
from pyguara.dev.file_watcher import PollingFileWatcher, WatchedFile
from pyguara.resources.data import DataResource
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager


class TestWatchedFile:
    def test_create_from_path(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("test content")

        watched = WatchedFile.from_path(str(f))

        assert watched.path == str(f.absolute())
        assert watched.last_modified > 0
        assert watched.last_size > 0

    def test_has_changed(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("initial content")
        watched = WatchedFile.from_path(str(f))

        assert not watched.has_changed()

        time.sleep(0.01)
        f.write_text("modified content!")

        assert watched.has_changed()
        # A second check with no further edit reports no change.
        assert not watched.has_changed()

    def test_has_changed_tolerates_a_deleted_file(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x")
        watched = WatchedFile.from_path(str(f))

        f.unlink()

        assert watched.has_changed() is False


class TestPollingFileWatcher:
    def test_watch_and_unwatch(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_text("x = 1")
        watcher = PollingFileWatcher()

        assert watcher.watch(str(f), lambda p: None) is True
        assert watcher.watched_count == 1

        watcher.unwatch(str(f))
        assert watcher.watched_count == 0

    def test_watch_nonexistent_file_returns_false(self) -> None:
        watcher = PollingFileWatcher()
        assert watcher.watch("/nope/missing.py", lambda p: None) is False

    def test_detect_changes(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("initial")
        watcher = PollingFileWatcher()
        seen: list[str] = []
        watcher.watch(str(f), seen.append)

        assert watcher.check_now() == []

        time.sleep(0.01)
        f.write_text("modified")

        changed = watcher.check_now()
        assert len(changed) == 1
        assert seen == [str(f.absolute())]

    def test_watch_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("# a")
        (tmp_path / "b.py").write_text("# b")
        (tmp_path / "c.txt").write_text("not python")
        watcher = PollingFileWatcher()

        count = watcher.watch_directory(
            str(tmp_path), lambda p: None, pattern="*.py", recursive=False
        )
        assert count == 2

    def test_start_stop(self) -> None:
        watcher = PollingFileWatcher(poll_interval=0.05)
        assert not watcher.is_running

        watcher.start()
        assert watcher.is_running

        watcher.stop()
        assert not watcher.is_running

    def test_multiple_callbacks_for_one_file(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("initial")
        watcher = PollingFileWatcher()
        a: list[str] = []
        b: list[str] = []
        watcher.watch(str(f), a.append)
        watcher.watch(str(f), b.append)

        assert watcher.watched_count == 1

        time.sleep(0.01)
        f.write_text("modified")
        watcher.check_now()

        assert len(a) == 1
        assert len(b) == 1

    def test_callback_may_call_back_into_the_watcher_without_deadlock(
        self, tmp_path: Path
    ) -> None:
        """A change callback that touches the watcher API must not deadlock.

        `check_now()` used to hold a non-reentrant lock across the callback,
        so a callback calling `watched_count` / `unwatch()` / `watch()` hung
        the polling thread forever.
        """
        f = tmp_path / "f.py"
        f.write_text("x = 1")
        watcher = PollingFileWatcher()
        observed: list[int] = []

        def on_change(path: str) -> None:
            observed.append(watcher.watched_count)  # re-enters the watcher
            watcher.unwatch(path)  # ...and mutates it

        watcher.watch(str(f), on_change)
        time.sleep(0.01)
        f.write_text("x = 2")

        done = threading.Event()
        threading.Thread(
            target=lambda: (watcher.check_now(), done.set()), daemon=True
        ).start()

        assert done.wait(timeout=3.0), "check_now() deadlocked in the callback"
        assert observed == [1]
        assert watcher.watched_count == 0

    def test_poll_loop_survives_a_raising_callback(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("initial")
        watcher = PollingFileWatcher()
        good: list[str] = []

        def boom(_path: str) -> None:
            raise RuntimeError("callback blew up")

        watcher.watch(str(f), boom)
        watcher.watch(str(f), good.append)

        time.sleep(0.01)
        f.write_text("edit one")
        watcher.check_now()  # must not raise

        time.sleep(0.01)
        f.write_text("edit two")
        watcher.check_now()

        # The raising callback never suppressed the well-behaved one.
        assert good == [str(f.absolute())] * 2


def _manager_with_json(path: Path, payload: dict) -> tuple[ResourceManager, str]:
    path.write_text(json.dumps(payload))
    rm = ResourceManager()
    rm.register_loader(JsonLoader())
    key = str(path)
    rm.load(key, DataResource)
    return rm, key


class TestAssetReloadWatcher:
    def test_change_is_queued_then_applied_by_drain(self, tmp_path: Path) -> None:
        asset = tmp_path / "data.json"
        rm, key = _manager_with_json(asset, {"hp": 10})
        watcher = AssetReloadWatcher(rm)
        watcher.refresh()

        asset.write_text(json.dumps({"hp": 99}))
        watcher._watcher.check_now()  # simulate one poll cycle

        # Detected, queued -- but not yet reloaded.
        assert watcher.pending_count == 1
        assert rm.load(key, DataResource).native_handle == {"hp": 10}

        reloaded = watcher.drain()

        assert reloaded == [key]
        assert watcher.pending_count == 0
        assert rm.load(key, DataResource).native_handle == {"hp": 99}

    def test_drain_dedups_repeated_changes_to_one_reload(self, tmp_path: Path) -> None:
        asset = tmp_path / "data.json"
        rm, key = _manager_with_json(asset, {"v": 1})
        watcher = AssetReloadWatcher(rm)
        watcher.refresh()

        for v in (2, 3, 4):
            asset.write_text(json.dumps({"v": v}))
            time.sleep(0.01)
            watcher._watcher.check_now()

        assert watcher.drain() == [key]

    def test_drain_ignores_an_asset_unloaded_since_the_change(
        self, tmp_path: Path
    ) -> None:
        asset = tmp_path / "data.json"
        rm, key = _manager_with_json(asset, {"hp": 1})
        watcher = AssetReloadWatcher(rm)
        watcher.refresh()

        asset.write_text(json.dumps({"hp": 2}))
        watcher._watcher.check_now()
        assert watcher.pending_count == 1

        rm.unload(key, force=True)

        assert watcher.drain() == []  # KeyError from reload() is swallowed

    def test_refresh_drops_watches_for_evicted_assets(self, tmp_path: Path) -> None:
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        rm, key_a = _manager_with_json(a, {})
        b.write_text("{}")
        rm.load(str(b), DataResource)

        watcher = AssetReloadWatcher(rm)
        watcher.refresh()
        assert watcher._watcher.watched_count == 2

        rm.unload(key_a, force=True)
        watcher.refresh()

        assert watcher._watcher.watched_count == 1

    def test_stop_is_idempotent(self, tmp_path: Path) -> None:
        rm, _ = _manager_with_json(tmp_path / "d.json", {})
        watcher = AssetReloadWatcher(rm, poll_interval=0.05)
        watcher.start()

        watcher.stop()
        watcher.stop()

        assert not watcher.is_running

    def test_end_to_end_with_the_polling_thread(self, tmp_path: Path) -> None:
        asset = tmp_path / "data.json"
        rm, key = _manager_with_json(asset, {"n": 1})
        watcher = AssetReloadWatcher(rm, poll_interval=0.05)
        watcher.start()
        try:
            asset.write_text(json.dumps({"n": 2}))

            deadline = time.monotonic() + 3.0
            while watcher.pending_count == 0 and time.monotonic() < deadline:
                time.sleep(0.02)

            # The polling thread only queued the change; it did not reload.
            assert watcher.pending_count == 1
            assert rm.load(key, DataResource).native_handle == {"n": 1}

            assert watcher.drain() == [key]
            assert rm.load(key, DataResource).native_handle == {"n": 2}
        finally:
            watcher.stop()


@pytest.mark.parametrize("name", ["hot_reload", "HotReloadManager", "StatefulSystem"])
def test_removed_code_reload_symbols_are_gone(name: str) -> None:
    import pyguara.dev as dev

    assert not hasattr(dev, name)
    with pytest.raises(ModuleNotFoundError):
        __import__("pyguara.dev.hot_reload")
