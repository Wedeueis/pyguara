"""Type definitions for the Error Handling System."""

from enum import Enum, auto


class ErrorSeverity(Enum):
    """Severity levels for error classification."""

    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


class ErrorCategory(str, Enum):
    """Categories for organizing errors."""

    SYSTEM = "system"
    GRAPHICS = "graphics"
    AUDIO = "audio"
    INPUT = "input"
    ASSETS = "assets"
    CONFIG = "config"
    PHYSICS = "physics"
    LOGIC = "logic"  # General game logic errors
    NETWORK = "network"
