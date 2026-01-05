"""Core logger wrapper implementation."""

import logging
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, cast, Iterator  # FIX: Added Iterator

from pyguara.events.dispatcher import EventDispatcher
from pyguara.log.events import OnExceptionEvent
from pyguara.log.handlers import ContextualFilter, EventIntegratedHandler
from pyguara.log.types import LogCategory, LogLevel


class EngineLogger:
    """Enhanced logger with context management and event integration.

    Wraps the standard python logging.Logger to provide structured logging,
    thread-safe context stacks, and seamless event system integration.
    """

    def __init__(
        self,
        name: str,
        level: LogLevel,
        event_dispatcher: Optional[EventDispatcher],
        log_file: Optional[Path],
        console_output: bool,
    ) -> None:
        """Initialize the logger wrapper."""
        self.name = name
        self._event_dispatcher = event_dispatcher

        # Thread-local storage ensures contexts don't leak between threads
        self._thread_local = threading.local()

        # Setup internal Python logger
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level.value)
        self._logger.handlers.clear()

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

    @property
    def _context_stack(self) -> List[Dict[str, Any]]:
        """Safe access to thread-local context stack."""
        if not hasattr(self._thread_local, "stack"):
            self._thread_local.stack = []
        return cast(List[Dict[str, Any]], self._thread_local.stack)

    @contextmanager
    # FIX: Added return annotation -> Iterator[None]
    def context(self, **context_data: Any) -> Iterator[None]:
        """Add contextual information to all logs within this block."""
        # 1. Push context
        self._context_stack.append(context_data)

        # 2. Apply filter
        ctx_filter = ContextualFilter(context_data)
        for h in self._logger.handlers:
            h.addFilter(ctx_filter)

        try:
            yield
        finally:
            # 3. Cleanup
            for h in self._logger.handlers:
                h.removeFilter(ctx_filter)
            self._context_stack.pop()

    def _get_merged_context(self) -> Dict[str, Any]:
        """Merge all contexts in the stack."""
        final_ctx = {}
        for ctx in self._context_stack:
            final_ctx.update(ctx)
        return final_ctx

    def _log(
        self, level: LogLevel, message: str, category: LogCategory, **kwargs: Any
    ) -> None:
        """Perform internal logging operations with context merging."""
        extra = {"category": category}
        extra.update(self._get_merged_context())
        extra.update(kwargs)
        self._logger.log(level.value, message, extra=extra)

    # --- Public API ---

    def debug(
        self, msg: str, category: LogCategory = LogCategory.DEBUG, **kwargs: Any
    ) -> None:
        """Log a debug message."""
        self._log(LogLevel.DEBUG, msg, category, **kwargs)

    def info(
        self, msg: str, category: LogCategory = LogCategory.SYSTEM, **kwargs: Any
    ) -> None:
        """Log an info message."""
        self._log(LogLevel.INFO, msg, category, **kwargs)

    def warning(
        self, msg: str, category: LogCategory = LogCategory.SYSTEM, **kwargs: Any
    ) -> None:
        """Log a warning message."""
        self._log(LogLevel.WARNING, msg, category, **kwargs)

    def error(
        self, msg: str, category: LogCategory = LogCategory.SYSTEM, **kwargs: Any
    ) -> None:
        """Log an error message."""
        self._log(LogLevel.ERROR, msg, category, **kwargs)

    def critical(
        self, msg: str, category: LogCategory = LogCategory.SYSTEM, **kwargs: Any
    ) -> None:
        """Log a critical message."""
        self._log(LogLevel.CRITICAL, msg, category, **kwargs)

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
