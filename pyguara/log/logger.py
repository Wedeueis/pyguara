"""Core logger wrapper implementation."""

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from pyguara.log.events import OnExceptionEvent
from pyguara.log.handlers import EventIntegratedHandler
from pyguara.log.types import LogCategory, LogLevel

if TYPE_CHECKING:
    from pyguara.events.dispatcher import EventDispatcher

# Names `logging.Logger.makeRecord` refuses in `extra` because a real LogRecord
# already owns them (stdlib attributes plus "message"/"asctime", added later by
# getMessage()/the formatter). Passing any of these as `extra` raises KeyError.
_RESERVED_LOG_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }
)

# Names that are real keyword arguments of `Logger.log()` rather than `extra` data.
_LOG_CALL_KWARGS = frozenset({"exc_info", "stack_info", "stacklevel"})


class EngineLogger:
    """Enhanced logger with event system integration.

    Wraps the standard python logging.Logger to provide structured logging
    and seamless event system integration.
    """

    def __init__(
        self,
        name: str,
        level: LogLevel,
        event_dispatcher: Optional["EventDispatcher"],
        log_file: Optional[Path],
        console_output: bool,
    ) -> None:
        """Initialize the logger wrapper."""
        self.name = name
        self._logger = logging.getLogger(name)
        self.reconfigure(
            level=level,
            event_dispatcher=event_dispatcher,
            log_file=log_file,
            console_output=console_output,
        )

    def reconfigure(
        self,
        level: LogLevel,
        event_dispatcher: Optional["EventDispatcher"],
        log_file: Optional[Path],
        console_output: bool,
    ) -> None:
        """Rebuild this logger's handler set for new settings.

        Closes and replaces every existing handler so repeated calls (e.g. from
        `LogManager.configure()`) don't leak file descriptors or double-log.
        """
        self._event_dispatcher = event_dispatcher

        for h in self._logger.handlers:
            h.close()
        self._logger.handlers.clear()
        self._logger.setLevel(level.value)

        # 1. Console Handler
        if console_output:
            c_handler = logging.StreamHandler(sys.stdout)
            c_fmt = logging.Formatter(
                "%(asctime)s [%(levelname)8s] %(name)s: %(message)s", datefmt="%H:%M:%S"
            )
            c_handler.setFormatter(c_fmt)
            self._logger.addHandler(c_handler)

        # 2. File Handler
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            f_handler = logging.FileHandler(log_file)
            f_fmt = logging.Formatter(
                "%(asctime)s [%(levelname)8s] %(name)s:%(lineno)d: %(message)s"
            )
            f_handler.setFormatter(f_fmt)
            self._logger.addHandler(f_handler)

        # 3. Event Handler
        if event_dispatcher:
            self._logger.addHandler(EventIntegratedHandler(event_dispatcher))

    def _log(
        self,
        level: LogLevel,
        message: str,
        category: LogCategory,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Perform internal logging operations."""
        log_kwargs = {key: kwargs.pop(key) for key in _LOG_CALL_KWARGS if key in kwargs}

        extra: Dict[str, Any] = {"category": category}
        extra.update(kwargs)

        # A caller-supplied key that shadows a real LogRecord attribute would
        # otherwise raise KeyError inside logging's makeRecord(); rename it
        # instead of dropping the data.
        safe_extra = {
            (f"{key}_" if key in _RESERVED_LOG_RECORD_ATTRS else key): value
            for key, value in extra.items()
        }

        self._logger.log(level.value, message, *args, extra=safe_extra, **log_kwargs)

    # --- Public API ---

    def debug(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.DEBUG,
        **kwargs: Any,
    ) -> None:
        """Log a debug message."""
        self._log(LogLevel.DEBUG, msg, category, *args, **kwargs)

    def info(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.SYSTEM,
        **kwargs: Any,
    ) -> None:
        """Log an info message."""
        self._log(LogLevel.INFO, msg, category, *args, **kwargs)

    def warning(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.SYSTEM,
        **kwargs: Any,
    ) -> None:
        """Log a warning message."""
        self._log(LogLevel.WARNING, msg, category, *args, **kwargs)

    def error(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.SYSTEM,
        **kwargs: Any,
    ) -> None:
        """Log an error message."""
        self._log(LogLevel.ERROR, msg, category, *args, **kwargs)

    def critical(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.SYSTEM,
        **kwargs: Any,
    ) -> None:
        """Log a critical message."""
        self._log(LogLevel.CRITICAL, msg, category, *args, **kwargs)

    def exception(
        self, ex: Exception, msg: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Log an exception with traceback."""
        if msg is None:
            msg = f"Exception occurred: {ex}"

        self._log(
            LogLevel.ERROR,
            msg,
            LogCategory.SYSTEM,
            exc_info=ex,
            exception_type=type(ex).__name__,
            **kwargs,
        )

        if self._event_dispatcher:
            evt = OnExceptionEvent(
                exception=ex, context=kwargs, category=LogCategory.SYSTEM
            )
            self._event_dispatcher.dispatch(evt)

    def performance(self, operation: str, duration: float, **context: Any) -> None:
        """Log a performance metric."""
        msg = f"Operation '{operation}' completed in {duration:.3f}s"
        self._log(
            LogLevel.INFO,
            msg,
            LogCategory.PERFORMANCE,
            operation=operation,
            duration=duration,
            **context,
        )
