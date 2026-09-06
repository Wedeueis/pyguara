"""Engine logger: a structured wrapper around `logging.Logger`."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

# Frames between the caller and `Logger.log()`: the level method (info, error,
# ...) and `_log`. Without this every record would attribute itself to the
# `self._logger.log(...)` line in this module, making %(lineno)d, %(module)s and
# %(funcName)s useless everywhere they appear.
_WRAPPER_FRAMES = 2


class EngineLogger:
    """A `logging.Logger` wrapper adding categories, context and event output.

    Level methods accept a `category` and arbitrary keyword arguments; the
    keywords become structured fields on the record, reachable by handlers and
    carried into `OnLogEvent`.

    Note:
        This wraps `logging.getLogger(name)`, which is process-global. Two
        `LogManager` instances asking for the same name therefore share one
        underlying logger. Each instance only removes the handlers it installed
        itself, so they no longer silently tear down each other's -- but
        settings still apply to the shared logger, last writer winning. Prefer
        the single `default_log_manager`.
    """

    def __init__(
        self,
        name: str,
        level: LogLevel,
        event_dispatcher: EventDispatcher | None,
        log_file: Path | None,
        console_output: bool,
        propagate: bool = True,
    ) -> None:
        """Create a logger and install its handlers.

        Args:
            name: Logger name, conventionally the module's `__name__`.
            level: Minimum level to emit.
            event_dispatcher: If given, records are also dispatched as
                `OnLogEvent`.
            log_file: If given, records are written there. Parent directories
                are created.
            console_output: Write records to stdout.
            propagate: Let records reach ancestor loggers, including root.
                Leave enabled so an application's own logging configuration
                can capture engine output; disable it if that configuration
                also prints, to avoid every record appearing twice.
        """
        self.name = name
        self._logger = logging.getLogger(name)
        # Only handlers in here are removed on reconfigure, so a handler added
        # by the application -- or by another LogManager sharing this stdlib
        # logger -- survives.
        self._own_handlers: list[logging.Handler] = []
        self._event_dispatcher: EventDispatcher | None = None
        self.reconfigure(
            level=level,
            event_dispatcher=event_dispatcher,
            log_file=log_file,
            console_output=console_output,
            propagate=propagate,
        )

    def reconfigure(
        self,
        level: LogLevel,
        event_dispatcher: EventDispatcher | None,
        log_file: Path | None,
        console_output: bool,
        propagate: bool = True,
    ) -> None:
        """Rebuild this logger's own handlers for new settings.

        Closes and detaches the handlers this logger installed previously, so
        repeated calls neither leak file descriptors nor double-log. Handlers
        installed by anyone else are left alone.

        Args:
            level: Minimum level to emit.
            event_dispatcher: If given, records are also dispatched as
                `OnLogEvent`.
            log_file: If given, records are written there.
            console_output: Write records to stdout.
            propagate: Let records reach ancestor loggers.
        """
        self._event_dispatcher = event_dispatcher

        self.detach_handlers()
        self._logger.setLevel(level.value)
        self._logger.propagate = propagate

        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            self._add_own_handler(console_handler)

        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)8s] %(name)s:%(lineno)d: %(message)s"
                )
            )
            self._add_own_handler(file_handler)

        if event_dispatcher:
            self._add_own_handler(EventIntegratedHandler(event_dispatcher))

    def detach_handlers(self) -> None:
        """Close and remove every handler this logger installed.

        Detaching as well as closing is what makes teardown stick: a closed
        `FileHandler` that is still attached silently reopens its file on the
        next record, so closing alone does not stop logging.
        """
        for handler in self._own_handlers:
            self._logger.removeHandler(handler)
            handler.close()
        self._own_handlers.clear()

    def debug(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.DEBUG,
        **kwargs: Any,
    ) -> None:
        """Log at DEBUG.

        Args:
            msg: Message, optionally printf-style.
            *args: Printf-style arguments for `msg`.
            category: Log category for filtering and routing.
            **kwargs: `exc_info`, `stack_info` and `stacklevel` are passed to
                the stdlib logger; anything else becomes a structured field.
        """
        self._log(LogLevel.DEBUG, msg, category, *args, **kwargs)

    def info(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.SYSTEM,
        **kwargs: Any,
    ) -> None:
        """Log at INFO.

        Args:
            msg: Message, optionally printf-style.
            *args: Printf-style arguments for `msg`.
            category: Log category for filtering and routing.
            **kwargs: Stdlib log keywords, or structured fields.
        """
        self._log(LogLevel.INFO, msg, category, *args, **kwargs)

    def warning(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.SYSTEM,
        **kwargs: Any,
    ) -> None:
        """Log at WARNING.

        Args:
            msg: Message, optionally printf-style.
            *args: Printf-style arguments for `msg`.
            category: Log category for filtering and routing.
            **kwargs: Stdlib log keywords, or structured fields.
        """
        self._log(LogLevel.WARNING, msg, category, *args, **kwargs)

    def error(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.SYSTEM,
        **kwargs: Any,
    ) -> None:
        """Log at ERROR.

        Args:
            msg: Message, optionally printf-style.
            *args: Printf-style arguments for `msg`.
            category: Log category for filtering and routing.
            **kwargs: Stdlib log keywords, or structured fields.
        """
        self._log(LogLevel.ERROR, msg, category, *args, **kwargs)

    def critical(
        self,
        msg: str,
        *args: Any,
        category: LogCategory = LogCategory.SYSTEM,
        **kwargs: Any,
    ) -> None:
        """Log at CRITICAL.

        Args:
            msg: Message, optionally printf-style.
            *args: Printf-style arguments for `msg`.
            category: Log category for filtering and routing.
            **kwargs: Stdlib log keywords, or structured fields.
        """
        self._log(LogLevel.CRITICAL, msg, category, *args, **kwargs)

    def exception(self, ex: Exception, msg: str | None = None, **kwargs: Any) -> None:
        """Log an exception with its traceback, and dispatch `OnExceptionEvent`.

        Unlike `logging.Logger.exception`, this takes the exception itself
        rather than reading the ambient one, so it works outside an `except`
        block.

        Args:
            ex: The exception to report.
            msg: Message to log. Defaults to a summary of `ex`.
            **kwargs: Structured fields, also carried as the event's context.
        """
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
            self._event_dispatcher.dispatch(
                OnExceptionEvent(
                    exception=ex, context=kwargs, category=LogCategory.SYSTEM
                )
            )

    def performance(self, operation: str, duration: float, **context: Any) -> None:
        """Log a timing measurement under the PERFORMANCE category.

        Args:
            operation: What was measured.
            duration: Elapsed time in seconds.
            **context: Extra structured fields.
        """
        self._log(
            LogLevel.INFO,
            f"Operation '{operation}' completed in {duration:.3f}s",
            LogCategory.PERFORMANCE,
            operation=operation,
            duration=duration,
            **context,
        )

    def _log(
        self,
        level: LogLevel,
        message: str,
        category: LogCategory,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Emit one record, splitting stdlib keywords from structured fields.

        Args:
            level: Level to emit at.
            message: Message, optionally printf-style.
            category: Log category, attached as a record attribute.
            *args: Printf-style arguments for `message`.
            **kwargs: `exc_info`, `stack_info` and `stacklevel` are forwarded
                to the stdlib logger; everything else becomes `extra`.
        """
        log_kwargs = {key: kwargs.pop(key) for key in _LOG_CALL_KWARGS if key in kwargs}
        # Skip past this method and the level method, so the record points at
        # the code that actually logged rather than at this module.
        log_kwargs["stacklevel"] = (
            int(log_kwargs.get("stacklevel", 1)) + _WRAPPER_FRAMES
        )

        extra: dict[str, Any] = {"category": category, **kwargs}

        # A caller-supplied key that shadows a real LogRecord attribute would
        # otherwise raise KeyError inside logging's makeRecord(); rename it
        # instead of dropping the data.
        safe_extra = {
            (f"{key}_" if key in _RESERVED_LOG_RECORD_ATTRS else key): value
            for key, value in extra.items()
        }

        self._logger.log(level.value, message, *args, extra=safe_extra, **log_kwargs)

    def _add_own_handler(self, handler: logging.Handler) -> None:
        """Attach a handler and record it as this logger's to remove later.

        Args:
            handler: The handler to install.
        """
        self._logger.addHandler(handler)
        self._own_handlers.append(handler)
