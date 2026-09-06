"""Logging handlers that bridge into the engine's event system."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pyguara.log.events import OnLogEvent
from pyguara.log.types import LogCategory, LogLevel

if TYPE_CHECKING:
    from pyguara.events.dispatcher import EventDispatcher

# Attributes every LogRecord carries, so `emit` can tell caller-supplied extras
# apart from stdlib ones. Computed once from a throwaway record rather than
# hand-listed (which would drift) -- and once at import, not per record.
_STANDARD_RECORD_KEYS: frozenset[str] = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
)


class EventIntegratedHandler(logging.Handler):
    """Republishes log records as `OnLogEvent` on the engine's dispatcher."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialise the handler.

        Args:
            event_dispatcher: Where records are dispatched.
        """
        super().__init__()
        self._dispatcher = event_dispatcher

    def emit(self, record: logging.LogRecord) -> None:
        """Convert a record to an `OnLogEvent` and dispatch it.

        Structured fields attached via the logger's keyword arguments are
        merged into the event context alongside the record's own location.

        Args:
            record: The record to republish.
        """
        try:
            try:
                level = LogLevel(record.levelno)
            except ValueError:
                level = LogLevel.INFO

            context: dict[str, Any] = {
                "logger": record.name,
                "module": record.module,
                "line": record.lineno,
                "thread": record.threadName,
            }
            for key, value in record.__dict__.items():
                if key not in _STANDARD_RECORD_KEYS and key not in context:
                    context[key] = value

            self._dispatcher.dispatch(
                OnLogEvent(
                    level=level,
                    category=getattr(record, "category", LogCategory.SYSTEM),
                    message=record.getMessage(),
                    context=context,
                    timestamp=record.created,
                )
            )
        except Exception:
            self.handleError(record)
