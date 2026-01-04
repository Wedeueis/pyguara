"""
Logging subsystem.

Provides structured, event-integrated logging for the engine.
"""

from pyguara.logging.types import LogLevel, LogCategory
from pyguara.logging.events import OnLogEvent, OnExceptionEvent
from pyguara.logging.logger import EngineLogger
from pyguara.logging.manager import LogManager

__all__ = [
    "LogLevel",
    "LogCategory",
    "OnLogEvent",
    "OnExceptionEvent",
    "EngineLogger",
    "LogManager",
]
