"""Factory and registry for engine loggers."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from pyguara.log.logger import EngineLogger
from pyguara.log.types import LogLevel

if TYPE_CHECKING:
    from pyguara.events.dispatcher import EventDispatcher

# Distinguishes "leave the dispatcher alone" from "detach the dispatcher",
# which a plain None default cannot express.
_UNCHANGED: Final[Any] = object()


class LogManager:
    """Creates and configures `EngineLogger` instances from shared settings.

    Settings apply to every logger the manager has handed out, including ones
    created before `configure()` was called.

    Note:
        Loggers wrap `logging.getLogger(name)`, which is process-global, so two
        managers using the same name share one underlying logger. Each removes
        only the handlers it installed, but level and propagation are shared,
        last writer winning. Prefer the single `default_log_manager`.
    """

    def __init__(self, event_dispatcher: EventDispatcher | None = None) -> None:
        """Initialise a manager with default settings.

        Args:
            event_dispatcher: If given, every logger also dispatches records as
                `OnLogEvent`.
        """
        self._loggers: dict[str, EngineLogger] = {}
        self._event_dispatcher = event_dispatcher
        self._level = LogLevel.INFO
        self._log_file: Path | None = None
        self._console = True
        self._propagate = True
        self._lock = threading.RLock()

    def configure(
        self,
        level: LogLevel = LogLevel.INFO,
        log_file: str | Path | None = None,
        console: bool = True,
        dispatcher: EventDispatcher | None = _UNCHANGED,
        propagate: bool = True,
    ) -> None:
        """Apply settings to this manager and every logger it has created.

        Args:
            level: Minimum level to emit.
            log_file: Write records here. None disables file logging.
            console: Write records to stdout.
            dispatcher: Dispatch records as `OnLogEvent`. Omit to keep the
                current dispatcher; pass None explicitly to detach it.
            propagate: Let records reach ancestor loggers, including root.
                Leave enabled so an application's logging configuration can
                capture engine output; disable it if that configuration also
                prints, to avoid every record appearing twice.
        """
        with self._lock:
            self._level = level
            self._log_file = Path(log_file) if log_file else None
            self._console = console
            self._propagate = propagate
            if dispatcher is not _UNCHANGED:
                self._event_dispatcher = dispatcher

            # Rebuild handlers on every already-constructed logger, not merely
            # setLevel(): most leaf modules build theirs eagerly at import time
            # via get_logger(), long before this runs, so file and event output
            # configured afterwards would otherwise never reach them.
            for logger in self._loggers.values():
                logger.reconfigure(
                    level=self._level,
                    event_dispatcher=self._event_dispatcher,
                    log_file=self._log_file,
                    console_output=self._console,
                    propagate=self._propagate,
                )

    def get_logger(self, name: str) -> EngineLogger:
        """Return the logger for a name, creating it on first request.

        Args:
            name: Logger name, conventionally the module's `__name__`.

        Returns:
            The logger, configured with this manager's current settings.
        """
        with self._lock:
            logger = self._loggers.get(name)
            if logger is None:
                logger = EngineLogger(
                    name=name,
                    level=self._level,
                    event_dispatcher=self._event_dispatcher,
                    log_file=self._log_file,
                    console_output=self._console,
                    propagate=self._propagate,
                )
                self._loggers[name] = logger
            return logger

    def shutdown(self) -> None:
        """Close and detach the handlers of every logger this manager created.

        Detaching matters as much as closing: a closed `FileHandler` that is
        still attached silently reopens its file on the next record, so closing
        alone leaves logging running.
        """
        with self._lock:
            for logger in self._loggers.values():
                logger.detach_handlers()
            self._loggers.clear()


# Shared default instance backing the module-level `get_logger()` accessor, so
# genuinely non-DI leaf modules and DI-constructed classes (via constructor
# injection of this same instance) never drift into two independent registries.
default_log_manager = LogManager()


def get_logger(name: str) -> EngineLogger:
    """Return a logger from the shared default manager.

    Args:
        name: Logger name, conventionally the module's `__name__`.

    Returns:
        The logger for that name.
    """
    return default_log_manager.get_logger(name)
