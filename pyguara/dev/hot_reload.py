"""Hot-reloading system for faster iteration.

Reloads Python modules at runtime when source files change.
"""

from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Type

from pyguara.dev.file_watcher import PollingFileWatcher

logger = logging.getLogger(__name__)


class StatefulSystem(Protocol):
    """Protocol for systems that can preserve state across reloads.

    Implement this protocol in systems that need to maintain state
    when hot-reloaded.
    """

    def get_state(self) -> Dict[str, Any]:
        """Get the current state for preservation.

        Returns:
            Dictionary of state to preserve.
        """
        ...

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore preserved state after reload.

        Args:
            state: Previously preserved state dictionary.
        """
        ...


@dataclass
class ReloadableModule:
    """Information about a module that can be hot-reloaded.

    Attributes:
        module_name: Fully qualified module name.
        file_path: Path to the module file.
        module: The actual module object.
        classes: Classes to reinstantiate after reload.
    """

    module_name: str
    file_path: str
    module: Optional[Any] = None
    classes: List[str] = field(default_factory=list)


class HotReloadManager:
    """Manages hot-reloading of Python modules.

    Watches source files and automatically reloads them when they change.
    Can preserve state for systems that implement StatefulSystem.

    Example:
        manager = HotReloadManager()
        manager.watch_module("myproject.systems.player")
        manager.add_reload_callback(on_reload)
        manager.start()
    """

    def __init__(
        self,
        poll_interval: float = 0.5,
        auto_reload: bool = True,
    ) -> None:
        """Initialize the hot-reload manager.

        Args:
            poll_interval: Seconds between file polls.
            auto_reload: Whether to automatically reload on change.
        """
        self._watcher = PollingFileWatcher(poll_interval=poll_interval)
        self._modules: Dict[str, ReloadableModule] = {}
        self._reload_callbacks: List[Callable[[str], None]] = []
        self._auto_reload = auto_reload
        self._paused = False
        self._pending_reloads: List[str] = []

    @property
    def is_running(self) -> bool:
        """Check if hot-reload is running."""
        return self._watcher.is_running

    @property
    def is_paused(self) -> bool:
        """Check if hot-reload is paused."""
        return self._paused

    def watch_module(self, module_name: str) -> bool:
        """Watch a module for hot-reloading.

        Args:
            module_name: Fully qualified module name.

        Returns:
            True if module was added to watch list.
        """
        # Try to import the module
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            logger.error(f"Could not import module {module_name}: {e}")
            return False

        # Get the file path
        file_path = getattr(module, "__file__", None)
        if not file_path:
            logger.error(f"Module {module_name} has no __file__ attribute")
            return False

        # Register the module
        self._modules[module_name] = ReloadableModule(
            module_name=module_name,
            file_path=file_path,
            module=module,
        )

        # Watch the file
        self._watcher.watch(file_path, lambda p: self._on_file_changed(module_name))

        logger.info(f"Watching module for hot-reload: {module_name}")
        return True

    def watch_package(self, package_name: str) -> int:
        """Watch all modules in a package.

        Args:
            package_name: Package name to watch.

        Returns:
            Number of modules being watched.
        """
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.error(f"Could not import package {package_name}: {e}")
            return 0

        package_path = getattr(package, "__path__", None)
        if not package_path:
            # Single module, not a package
            return 1 if self.watch_module(package_name) else 0

        count = 0
        for path in package_path:
            for file_path in Path(path).rglob("*.py"):
                # Convert file path to module name
                rel_path = file_path.relative_to(path)
                parts = list(rel_path.parts)
                parts[-1] = parts[-1][:-3]  # Remove .py

                if parts[-1] == "__init__":
                    parts = parts[:-1]

                if parts:
                    module_name = f"{package_name}.{'.'.join(parts)}"
                else:
                    module_name = package_name

                if self.watch_module(module_name):
                    count += 1

        logger.info(f"Watching {count} modules in package {package_name}")
        return count

    def unwatch_module(self, module_name: str) -> None:
        """Stop watching a module.

        Args:
            module_name: Module to stop watching.
        """
        if module_name in self._modules:
            reloadable = self._modules[module_name]
            self._watcher.unwatch(reloadable.file_path)
            del self._modules[module_name]
            logger.debug(f"Stopped watching module: {module_name}")

    def add_reload_callback(self, callback: Callable[[str], None]) -> None:
        """Add a callback to be called after a module is reloaded.

        Args:
            callback: Function that takes the module name.
        """
        self._reload_callbacks.append(callback)

    def remove_reload_callback(self, callback: Callable[[str], None]) -> None:
        """Remove a reload callback.

        Args:
            callback: Callback to remove.
        """
        if callback in self._reload_callbacks:
            self._reload_callbacks.remove(callback)

    def reload_module(self, module_name: str) -> bool:
        """Manually reload a specific module.

        Args:
            module_name: Module to reload.

        Returns:
            True if reload was successful.
        """
        if module_name not in self._modules:
            logger.warning(f"Module {module_name} not being watched")
            return False

        reloadable = self._modules[module_name]

        try:
            logger.info(f"Reloading module: {module_name}")

            # Get the module from sys.modules
            if module_name in sys.modules:
                old_module = sys.modules[module_name]

                # Reload
                new_module = importlib.reload(old_module)
                reloadable.module = new_module

                # Notify callbacks
                for callback in self._reload_callbacks:
                    try:
                        callback(module_name)
                    except Exception as e:
                        logger.error(f"Error in reload callback: {e}")

                logger.info(f"Successfully reloaded: {module_name}")
                return True
            else:
                # Module not loaded yet
                module = importlib.import_module(module_name)
                reloadable.module = module
                return True

        except Exception as e:
            logger.error(f"Failed to reload module {module_name}: {e}")
            return False

    def reload_all_pending(self) -> int:
        """Reload all modules with pending changes.

        Returns:
            Number of modules reloaded.
        """
        count = 0
        pending = self._pending_reloads.copy()
        self._pending_reloads.clear()

        for module_name in pending:
            if self.reload_module(module_name):
                count += 1

        return count

    def start(self) -> None:
        """Start the hot-reload watcher."""
        self._watcher.start()
        logger.info("Hot-reload started")

    def stop(self) -> None:
        """Stop the hot-reload watcher."""
        self._watcher.stop()
        logger.info("Hot-reload stopped")

    def pause(self) -> None:
        """Pause automatic reloading.

        Changes will be queued and applied when resumed.
        """
        self._paused = True
        logger.debug("Hot-reload paused")

    def resume(self) -> int:
        """Resume automatic reloading and apply pending changes.

        Returns:
            Number of pending modules reloaded.
        """
        self._paused = False
        count = self.reload_all_pending()
        logger.debug(f"Hot-reload resumed, reloaded {count} modules")
        return count

    def _on_file_changed(self, module_name: str) -> None:
        """Handle file change notification.

        Args:
            module_name: Name of the module whose file changed.
        """
        logger.debug(f"File changed for module: {module_name}")

        if self._paused:
            if module_name not in self._pending_reloads:
                self._pending_reloads.append(module_name)
            return

        if self._auto_reload:
            self.reload_module(module_name)
        else:
            if module_name not in self._pending_reloads:
                self._pending_reloads.append(module_name)


def reload_system_class(
    old_instance: Any,
    new_class: Type,
    preserve_state: bool = True,
) -> Any:
    """Reload a system instance with a new class.

    Creates a new instance of the class and optionally
    preserves state from the old instance.

    Args:
        old_instance: The old system instance.
        new_class: The new class to instantiate.
        preserve_state: Whether to preserve state if possible.

    Returns:
        New instance of the system.
    """
    state = None

    # Try to get state from old instance
    if preserve_state and hasattr(old_instance, "get_state"):
        try:
            state = old_instance.get_state()
        except Exception as e:
            logger.warning(f"Could not get state from old instance: {e}")

    # Create new instance
    try:
        new_instance = new_class()
    except TypeError:
        # Constructor might need arguments
        logger.warning(f"Could not create {new_class.__name__} without arguments")
        return old_instance

    # Restore state
    if state and hasattr(new_instance, "set_state"):
        try:
            new_instance.set_state(state)
        except Exception as e:
            logger.warning(f"Could not restore state to new instance: {e}")

    return new_instance
