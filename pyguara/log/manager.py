"""Central management for application loggers."""

import threading
from pathlib import Path
from typing import Dict, Optional, Union

from pyguara.events.dispatcher import EventDispatcher
from pyguara.log.logger import EngineLogger
from pyguara.log.types import LogCategory, LogLevel


class LogManager:
    """Factory and registry for EngineLogger instances."""

    def __init__(self, event_dispatcher: Optional[EventDispatcher] = None) -> None:
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
        dispatcher: Optional[EventDispatcher] = None,
    ) -> None:
        """Update global logging settings."""
        with self._lock:
            self._level = level
            self._log_file = Path(log_file) if log_file else None
            self._console = console
            if dispatcher:
                self._event_dispatcher = dispatcher

            # Refresh existing loggers
            for logger in self._loggers.values():
                logger._logger.setLevel(level.value)

    def get_logger(
        self, name: str, category: Optional[LogCategory] = None
    ) -> EngineLogger:
        """Get or create a named logger instance."""
        key = name
        if category:
            key = f"{name}.{category.value}"

        with self._lock:
            if key not in self._loggers:
                self._loggers[key] = EngineLogger(
                    name=key,
                    level=self._level,
                    event_dispatcher=self._event_dispatcher,
                    log_file=self._log_file,
                    console_output=self._console,
                )
            return self._loggers[key]

    def shutdown(self) -> None:
        """Close all logger handlers."""
        with self._lock:
            for logger in self._loggers.values():
                for h in logger._logger.handlers:
                    h.close()
            self._loggers.clear()
