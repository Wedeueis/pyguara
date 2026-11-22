"""Code hot-reload: edit a system's module and the running game uses it.

Watches the source of every game module that defines a registered system.
Between frames, on the main thread, a changed module is re-imported and
each live system of a class it defines becomes an instance of the new
class: its attributes, and so its state and what it was built with, stay.
A system that must set up something new for the new code gets a call
to `on_reload()` if it defines one.

Development only, and off by default; `Application.enable_code_hot_reload()`
turns it on.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from pyguara.dev.file_watcher import PollingFileWatcher
from pyguara.log import get_logger
from pyguara.systems.manager import SystemManager

__all__ = ["CodeReload", "SystemCodeReloader"]

logger = get_logger(__name__)

# Seconds between reconciliations of the watch set with the registered systems.
_REFRESH_INTERVAL = 1.0

SystemManagers = Callable[[], Iterable[SystemManager]]
"""Returns every system manager whose systems may be reloaded."""


@dataclass(frozen=True)
class CodeReload:
    """The outcome of reloading one module.

    Attributes:
        module: The module's name.
        systems: How many live systems now run the new code.
        error: Why the reload was refused or failed, or None. On an error
            the module and every system are as they were before.
    """

    module: str
    systems: int
    error: str | None = None


def reload_problem(module: ModuleType) -> str | None:
    """Return why `module` cannot be reloaded in place, or None if it can.

    Every class the module defines must be a system: anything else, such as
    a component, an event or an enum, has instances elsewhere that would
    keep the old class, so a query or an `is` check would stop matching.
    """
    for value in vars(module).values():
        if not isinstance(value, type) or value.__module__ != module.__name__:
            continue
        if not callable(getattr(value, "update", None)):
            return (
                f"it defines {value.__name__}, which is not a system; only a "
                f"module that defines nothing but systems can be reloaded. "
                f"Move {value.__name__} to a module of its own."
            )
    return None


class SystemCodeReloader:
    """Re-imports changed system modules and moves live systems onto them.

    The watch set follows the registered systems: `drain()` reconciles it,
    so systems registered later are picked up. Engine modules are never
    watched, only the game's.

    Example:
        reloader = SystemCodeReloader(lambda: [scene.system_manager])
        reloader.start()
        # each frame, on the main thread:
        for result in reloader.drain():
            ...
        reloader.stop()
    """

    def __init__(self, managers: SystemManagers, poll_interval: float = 0.5) -> None:
        """Initialise the reloader.

        Args:
            managers: Returns the system managers to look in, called on
                every reconcile, so scenes added later are covered.
            poll_interval: Seconds between file-modification polls.
        """
        self._managers = managers
        self._watcher = PollingFileWatcher(poll_interval=poll_interval)
        self._lock = threading.Lock()
        self._watched: dict[str, str] = {}  # absolute path -> module name
        self._refused: set[str] = set()
        self._pending: list[str] = []
        self._last_refresh = 0.0

    @property
    def watched_modules(self) -> tuple[str, ...]:
        """The modules currently watched, sorted."""
        with self._lock:
            return tuple(sorted(self._watched.values()))

    @property
    def is_running(self) -> bool:
        """Whether the polling thread is running."""
        return self._watcher.is_running

    def start(self) -> None:
        """Reconcile the watch set and start polling."""
        self.refresh()
        self._watcher.start()
        logger.info(f"Code hot-reload watching {', '.join(self.watched_modules)}")

    def stop(self) -> None:
        """Stop polling and drop queued reloads. Idempotent."""
        self._watcher.stop()
        with self._lock:
            self._pending.clear()

    def check_now(self) -> None:
        """Poll the watched files once, on this thread. For tests and tools."""
        self._watcher.check_now()

    def refresh(self) -> None:
        """Watch the module of every registered game system, and only those."""
        current: dict[str, str] = {}
        for system in self._systems():
            name = type(system).__module__
            module = sys.modules.get(name)
            path = getattr(module, "__file__", None)
            if module is None or path is None or _is_engine(name):
                continue
            problem = reload_problem(module)
            if problem is not None:
                if name not in self._refused:
                    self._refused.add(name)
                    logger.info(f"Not watching {name} for code reload: {problem}")
                continue
            current[str(Path(path).resolve())] = name

        self._last_refresh = time.monotonic()
        with self._lock:
            previous, self._watched = self._watched, current
        for path in previous.keys() - current.keys():
            self._watcher.unwatch(path)
        for path in current.keys() - previous.keys():
            self._watcher.watch(path, self._on_file_changed)

    def drain(self) -> list[CodeReload]:
        """Apply queued reloads. Call once per frame, between frames.

        Returns:
            One result per module reloaded or refused this call.
        """
        if time.monotonic() - self._last_refresh >= _REFRESH_INTERVAL:
            self.refresh()
        with self._lock:
            pending, self._pending = self._pending, []
        return [self.reload(name) for name in dict.fromkeys(pending)]

    def reload(self, name: str) -> CodeReload:
        """Re-import one module and move its live systems onto the new code.

        All or nothing: if the import raises, the module turns out to define
        something other than systems, a class cannot be swapped, or an
        `on_reload()` raises, the module and every system are put back.

        Args:
            name: The module's name, as in `sys.modules`.

        Returns:
            What happened. Never raises for a fault in the game's code.
        """
        module = sys.modules.get(name)
        if module is None:
            return self._failed(name, "it is not imported")
        snapshot = dict(vars(module))
        try:
            importlib.reload(module)
        except Exception as error:  # noqa: BLE001 -- the game's code, reported
            _restore(module, snapshot)
            return self._failed(name, _describe(error))

        problem = reload_problem(module)
        if problem is not None:
            _restore(module, snapshot)
            return self._failed(name, problem)

        swapped: list[tuple[Any, type]] = []
        try:
            for system in self._systems():
                old = type(system)
                if old.__module__ != name:
                    continue
                new = vars(module).get(old.__name__)
                # A reload runs in the module's old namespace, so a class the
                # new code no longer defines is still there, unchanged.
                if not isinstance(new, type) or new is old:
                    logger.warning(
                        f"{name} no longer defines {old.__name__}; that system "
                        f"keeps its old code"
                    )
                    continue
                system.__class__ = new
                swapped.append((system, old))
            for system, _ in swapped:
                hook = getattr(system, "on_reload", None)
                if callable(hook):
                    hook()
        except Exception as error:  # noqa: BLE001 -- the game's code, reported
            for system, old in swapped:
                system.__class__ = old
            _restore(module, snapshot)
            return self._failed(name, _describe(error))

        # Only now, so a reload that is put back leaves no key behind.
        for system, old in swapped:
            for manager in self._managers():
                manager.add_key(type(system), old)
        logger.info(f"Reloaded {name}: {len(swapped)} system(s) run the new code")
        return CodeReload(name, len(swapped))

    def _systems(self) -> list[Any]:
        unique: dict[int, Any] = {}
        for manager in self._managers():
            for system in manager.get_all_systems():
                unique.setdefault(id(system), system)
        return list(unique.values())

    def _failed(self, name: str, reason: str) -> CodeReload:
        logger.error(
            f"Code reload of {name} failed, the old code keeps running: {reason}"
        )
        return CodeReload(name, 0, reason)

    def _on_file_changed(self, path: str) -> None:
        with self._lock:
            name = self._watched.get(path)
            if name is not None and name not in self._pending:
                self._pending.append(name)


def _is_engine(name: str) -> bool:
    return name == "pyguara" or name.startswith("pyguara.")


def _restore(module: ModuleType, snapshot: dict[str, Any]) -> None:
    namespace = vars(module)
    namespace.clear()
    namespace.update(snapshot)


def _describe(error: BaseException) -> str:
    """The error and where in the game's code it was raised."""
    frames = traceback.extract_tb(error.__traceback__)
    where = f" ({frames[-1].filename}:{frames[-1].lineno})" if frames else ""
    if isinstance(error, SyntaxError) and error.filename:
        where = f" ({error.filename}:{error.lineno})"
    return f"{type(error).__name__}: {error}{where}"
