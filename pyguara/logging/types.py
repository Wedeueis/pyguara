"""Type definitions for the Logging System."""

from enum import Enum, IntEnum
import logging


class LogLevel(IntEnum):
    """Maps standard Python logging levels to our system."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class LogCategory(str, Enum):
    """Categories for organizing log streams."""

    SYSTEM = "system"
    # FIX: Added DEBUG category to resolve 'attr-defined' error
    DEBUG = "debug"
    GRAPHICS = "graphics"
    AUDIO = "audio"
    INPUT = "input"
    PHYSICS = "physics"
    GAMEPLAY = "gameplay"
    PERFORMANCE = "performance"
    NETWORK = "network"
    EDITOR = "editor"
