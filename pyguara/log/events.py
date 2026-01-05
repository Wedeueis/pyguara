"""Events emitted by the logging system."""

from dataclasses import dataclass, field
import time
from typing import Any, Dict
from pyguara.log.types import LogLevel, LogCategory
from pyguara.events.protocols import Event


@dataclass
class OnLogEvent(Event):
    """Fired whenever a log message is processed."""

    level: LogLevel
    category: LogCategory
    message: str
    context: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: Any = "Logger"


@dataclass
class OnExceptionEvent(Event):
    """Fired when an exception is explicitly logged."""

    exception: Exception
    context: Dict[str, Any]
    severity: str = "ERROR"
    category: LogCategory = LogCategory.SYSTEM
    timestamp: float = field(default_factory=time.time)
    source: Any = "Logger"
