"""Central management for application loggers."""

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Union

from pyguara.log.logger import EngineLogger
from pyguara.log.types import LogLevel

if TYPE_CHECKING:
    from pyguara.events.dispatcher import EventDispatcher


class LogManager:
    """Factory and registry for EngineLogger instances."""

    def __init__(self, event_dispatcher: Optional["EventDispatcher"] = None) -> None:
        """Initialize the manager."""
        self._loggers: Dict[str, EngineLogger] = {}
        self._event_dispatcher = event_dispatcher
        self._level = LogLevel.INFO
        self._log_file: Optional[Path] = None
        self._console = True
        self._lock = threading.RLock()

    def configure(
        self,
        level: LogLevel = LogLevel.INFO,
        log_file: Optional[Union[str, Path]] = None,
        console: bool = True,
        dispatcher: Optional["EventDispatcher"] = None,
    ) -> None:
        """Update global logging settings and rebuild existing loggers' handlers."""
        with self._lock:
            self._level = level
            self._log_file = Path(log_file) if log_file else None
            self._console = console
            if dispatcher:
                self._event_dispatcher = dispatcher

            # Rebuild handlers on every already-constructed logger. Most of the
            # 31 leaf modules build their EngineLogger eagerly at import time via
            # get_logger(), before this is ever called — without rebuilding
            # handlers here (not just setLevel()), file/event logging configured
            # afterward would silently never reach them.
            for logger in self._loggers.values():
                logger.reconfigure(
                    level=self._level,
                    event_dispatcher=self._event_dispatcher,
                    log_file=self._log_file,
                    console_output=self._console,
                )

    def get_logger(self, name: str) -> EngineLogger:
        """Get or create a named logger instance."""
        with self._lock:
            if name not in self._loggers:
                self._loggers[name] = EngineLogger(
                    name=name,
                    level=self._level,
                    event_dispatcher=self._event_dispatcher,
                    log_file=self._log_file,
                    console_output=self._console,
                )
            return self._loggers[name]

    def shutdown(self) -> None:
        """Close all logger handlers."""
        with self._lock:
            for logger in self._loggers.values():
                for h in logger._logger.handlers:
                    h.close()
            self._loggers.clear()


# Shared default instance backing the module-level `get_logger()` accessor, so
# genuinely non-DI leaf modules and DI-constructed classes (via constructor
# injection of this same instance) never drift into two independent registries.
default_log_manager = LogManager()


def get_logger(name: str) -> EngineLogger:
    """Get or create a named logger from the shared default LogManager."""
    return default_log_manager.get_logger(name)
