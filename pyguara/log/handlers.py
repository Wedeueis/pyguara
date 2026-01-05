"""Custom logging handlers and filters."""

import logging
from typing import Any, Dict

from pyguara.events.dispatcher import EventDispatcher
from pyguara.log.events import OnLogEvent
from pyguara.log.types import LogCategory, LogLevel


class ContextualFilter(logging.Filter):
    """Filter that adds contextual information to log records."""

    def __init__(self, context: Dict[str, Any]) -> None:
        """Initialize with context data."""
        super().__init__()
        self.context = context

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject context data into the record attributes."""
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


class EventIntegratedHandler(logging.Handler):
    """Log handler that dispatches log records as engine events."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialize with a target dispatcher."""
        super().__init__()
        self._dispatcher = event_dispatcher

    def emit(self, record: logging.LogRecord) -> None:
        """Emit log record as an event."""
        try:
            # Safe conversion of level
            try:
                level = LogLevel(record.levelno)
            except ValueError:
                level = LogLevel.INFO

            # Infer Category (defaulting to SYSTEM if not present)
            category = getattr(record, "category", LogCategory.SYSTEM)

            # Build Context from record attributes
            context = {
                "logger": record.name,
                "module": record.module,
                "line": record.lineno,
                "thread": record.threadName,
            }

            # Merge extra attributes (filtering out standard LogRecord attrs)
            # We create a dummy record to get the standard keys efficiently
            standard_keys = logging.LogRecord(
                "", 0, "", 0, "", (), None
            ).__dict__.keys()

            for key, value in record.__dict__.items():
                if key not in standard_keys and key not in context:
                    context[key] = value

            # Dispatch
            event = OnLogEvent(
                level=level,
                category=category,
                message=record.getMessage(),
                context=context,
                timestamp=record.created,
            )
            self._dispatcher.dispatch(event)

        except Exception:
            self.handleError(record)
