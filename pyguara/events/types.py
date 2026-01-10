"""Type definitions for the Event System."""

from enum import Enum
from typing import Callable, TypeVar, Optional

# We use a Forward Reference because Event is defined in protocols.py
E_contra = TypeVar("E_contra", contravariant=True)

# A Handler is a callable that takes an Event and returns nothing.
EventHandler = Callable[[E_contra], Optional[bool]]


class ErrorHandlingStrategy(Enum):
    """Strategy for handling errors that occur in event handlers.

    Attributes:
        LOG: Log the error and continue processing subsequent handlers.
            Use this in production for graceful degradation.
        RAISE: Log the error and re-raise the exception.
            Use this in development for fail-fast debugging (default).
        IGNORE: Silently ignore errors without logging.
            Not recommended - use only for testing or specific edge cases.

    Example:
        >>> from pyguara.events.dispatcher import EventDispatcher
        >>> from pyguara.events.types import ErrorHandlingStrategy
        >>> # Development mode - fail fast
        >>> dispatcher = EventDispatcher(error_strategy=ErrorHandlingStrategy.RAISE)
        >>> # Production mode - graceful degradation
        >>> dispatcher = EventDispatcher(error_strategy=ErrorHandlingStrategy.LOG)
    """

    LOG = "log"
    """Log the error and continue processing."""

    RAISE = "raise"
    """Log the error and re-raise the exception (fail-fast)."""

    IGNORE = "ignore"
    """Silently ignore errors (not recommended)."""
