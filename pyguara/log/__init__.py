"""
Logging subsystem.

Provides structured, event-integrated logging for the engine.
"""

from pyguara.log.types import LogLevel, LogCategory
from pyguara.log.events import OnLogEvent, OnExceptionEvent
from pyguara.log.logger import EngineLogger
from pyguara.log.manager import LogManager

__all__ = [
    "LogLevel",
    "LogCategory",
    "OnLogEvent",
    "OnExceptionEvent",
    "EngineLogger",
    "LogManager",
]
