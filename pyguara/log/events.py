"""Events emitted by the logging system."""

import time
from dataclasses import dataclass, field
from typing import Any

from pyguara.events.protocols import Event
from pyguara.log.types import LogCategory, LogLevel


@dataclass
class OnLogEvent(Event):
    """Fired whenever a log message is processed."""

    level: LogLevel
    category: LogCategory
    message: str
    context: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: Any = "Logger"


@dataclass
class OnExceptionEvent(Event):
    """Fired when an exception is explicitly logged."""

    exception: Exception
    context: dict[str, Any]
    severity: str = "ERROR"
    category: LogCategory = LogCategory.SYSTEM
    timestamp: float = field(default_factory=time.time)
    source: Any = "Logger"
