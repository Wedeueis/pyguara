"""Type definitions for the Logging System."""

import logging
from enum import Enum, IntEnum


class LogLevel(IntEnum):
    """Engine log levels, numerically identical to the stdlib's."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class LogCategory(str, Enum):
    """Subsystem tag carried on every record, for filtering and routing.

    Orthogonal to `LogLevel`: a category says *where* a message came from,
    a level says how severe it is. DEBUG is the exception -- it is the default
    category for `EngineLogger.debug()`, for messages that belong to no
    particular subsystem.
    """

    SYSTEM = "system"
    DEBUG = "debug"
    GRAPHICS = "graphics"
    AUDIO = "audio"
    INPUT = "input"
    PHYSICS = "physics"
    GAMEPLAY = "gameplay"
    PERFORMANCE = "performance"
    NETWORK = "network"
    EDITOR = "editor"
