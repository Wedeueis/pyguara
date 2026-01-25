"""Tests for the hot-reload and file watcher systems."""

import tempfile
import time
from pathlib import Path


from pyguara.dev.file_watcher import PollingFileWatcher, WatchedFile
from pyguara.dev.hot_reload import HotReloadManager, reload_system_class


class TestWatchedFile:
    """Tests for WatchedFile."""

    def test_create_from_path(self):
        """Test creating WatchedFile from path."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            f.flush()

            watched = WatchedFile.from_path(f.name)

            assert watched.path == str(Path(f.name).absolute())
            assert watched.last_modified > 0
            assert watched.last_size > 0

            Path(f.name).unlink()

    def test_has_changed(self):
        """Test detecting file changes."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("initial content")
            f.flush()

            watched = WatchedFile.from_path(f.name)

            # Initially no change
            assert not watched.has_changed()

            # Modify file
            time.sleep(0.1)  # Ensure different mtime
            with open(f.name, "w") as f2:
                f2.write("modified content!")

            # Should detect change
            assert watched.has_changed()

            # Second check should be false (no new changes)
            assert not watched.has_changed()

            Path(f.name).unlink()


class TestPollingFileWatcher:
    """Tests for PollingFileWatcher."""

    def test_watch_file(self):
        """Test watching a file."""
        watcher = PollingFileWatcher()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            f.flush()

            changes = []
            result = watcher.watch(f.name, lambda p: changes.append(p))

            assert result is True
            assert watcher.watched_count == 1

            watcher.unwatch(f.name)
            assert watcher.watched_count == 0

            Path(f.name).unlink()

    def test_watch_nonexistent_file(self):
        """Test watching nonexistent file returns False."""
        watcher = PollingFileWatcher()
        result = watcher.watch("/nonexistent/file.py", lambda p: None)
        assert result is False

    def test_detect_changes(self):
        """Test detecting file changes."""
        watcher = PollingFileWatcher()
        changes = []

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("initial")
            f.flush()

            watcher.watch(f.name, lambda p: changes.append(p))

            # No changes initially
            changed = watcher.check_now()
            assert len(changed) == 0

            # Modify file
            time.sleep(0.1)
            with open(f.name, "w") as f2:
                f2.write("modified content")

            # Should detect change
            changed = watcher.check_now()
            assert len(changed) == 1
            assert len(changes) == 1

            watcher.unwatch(f.name)
            Path(f.name).unlink()

    def test_watch_directory(self):
        """Test watching a directory."""
        watcher = PollingFileWatcher()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            (Path(tmpdir) / "test1.py").write_text("# test1")
            (Path(tmpdir) / "test2.py").write_text("# test2")
            (Path(tmpdir) / "test.txt").write_text("not python")

            count = watcher.watch_directory(
                tmpdir, lambda p: None, pattern="*.py", recursive=False
            )

            assert count == 2

    def test_start_stop(self):
        """Test starting and stopping watcher."""
        watcher = PollingFileWatcher(poll_interval=0.1)

        assert not watcher.is_running

        watcher.start()
        assert watcher.is_running

        watcher.stop()
        assert not watcher.is_running

    def test_multiple_callbacks(self):
        """Test multiple callbacks for same file."""
        watcher = PollingFileWatcher()
        changes1 = []
        changes2 = []

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("initial")
            f.flush()

            watcher.watch(f.name, lambda p: changes1.append(p))
            watcher.watch(f.name, lambda p: changes2.append(p))

            # Still only one watched file
            assert watcher.watched_count == 1

            # Modify
            time.sleep(0.1)
            with open(f.name, "w") as f2:
                f2.write("modified")

            watcher.check_now()

            # Both callbacks should be called
            assert len(changes1) == 1
            assert len(changes2) == 1

            Path(f.name).unlink()


class TestHotReloadManager:
    """Tests for HotReloadManager."""

    def test_create_manager(self):
        """Test creating hot-reload manager."""
        manager = HotReloadManager(poll_interval=0.1, auto_reload=False)
        assert not manager.is_running
        assert not manager.is_paused

    def test_watch_builtin_module(self):
        """Test watching a standard library module."""
        manager = HotReloadManager()

        # os module has a file
        result = manager.watch_module("os")
        assert result is True

        manager.unwatch_module("os")

    def test_watch_nonexistent_module(self):
        """Test watching nonexistent module."""
        manager = HotReloadManager()
        result = manager.watch_module("nonexistent_module_12345")
        assert result is False

    def test_reload_callback(self):
        """Test reload callbacks."""
        manager = HotReloadManager(auto_reload=False)
        callbacks_called = []

        def on_reload(module_name):
            callbacks_called.append(module_name)

        manager.add_reload_callback(on_reload)
        manager.watch_module("json")

        # Manually trigger reload
        manager.reload_module("json")

        assert "json" in callbacks_called

        manager.remove_reload_callback(on_reload)

    def test_pause_resume(self):
        """Test pause and resume."""
        manager = HotReloadManager(auto_reload=True)

        manager.pause()
        assert manager.is_paused

        manager.resume()
        assert not manager.is_paused

    def test_start_stop(self):
        """Test starting and stopping."""
        manager = HotReloadManager(poll_interval=0.1)

        manager.start()
        assert manager.is_running

        manager.stop()
        assert not manager.is_running


class TestReloadSystemClass:
    """Tests for reload_system_class function."""

    def test_reload_simple_class(self):
        """Test reloading a simple class."""

        class OldSystem:
            def __init__(self):
                self.value = 42

        class NewSystem:
            def __init__(self):
                self.value = 0
                self.new_feature = True

        old_instance = OldSystem()
        new_instance = reload_system_class(old_instance, NewSystem)

        assert isinstance(new_instance, NewSystem)
        assert hasattr(new_instance, "new_feature")

    def test_reload_with_state(self):
        """Test reloading preserves state."""

        class StatefulClass:
            def __init__(self):
                self.counter = 0
                self.data = []

            def get_state(self):
                return {"counter": self.counter, "data": self.data}

            def set_state(self, state):
                self.counter = state.get("counter", 0)
                self.data = state.get("data", [])

        old_instance = StatefulClass()
        old_instance.counter = 10
        old_instance.data = [1, 2, 3]

        new_instance = reload_system_class(old_instance, StatefulClass)

        assert new_instance.counter == 10
        assert new_instance.data == [1, 2, 3]

    def test_reload_without_state_preservation(self):
        """Test reloading without preserving state."""

        class StatefulClass:
            def __init__(self):
                self.counter = 0

            def get_state(self):
                return {"counter": self.counter}

            def set_state(self, state):
                self.counter = state.get("counter", 0)

        old_instance = StatefulClass()
        old_instance.counter = 10

        new_instance = reload_system_class(
            old_instance, StatefulClass, preserve_state=False
        )

        # State should NOT be preserved
        assert new_instance.counter == 0
