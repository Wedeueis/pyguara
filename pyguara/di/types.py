"""Type definitions and data structures for DI."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Type


class ServiceLifetime(Enum):
    """Service lifecycle management strategies."""

    SINGLETON = "singleton"  # One instance per container (shared)
    TRANSIENT = "transient"  # New instance every time it is requested
    SCOPED = "scoped"  # One instance per active scope


class ErrorHandlingStrategy(Enum):
    """Strategy for handling errors during dependency resolution.

    Attributes:
        LOG: Log the error and return None or raise.
            Use this in production for graceful degradation.
        RAISE: Log the error and re-raise the exception.
            Use this in development for fail-fast debugging (default).
        IGNORE: Silently ignore errors without logging.
            Not recommended - use only for testing or specific edge cases.

    Example:
        >>> from pyguara.di.container import DIContainer
        >>> from pyguara.di.types import ErrorHandlingStrategy
        >>> # Development mode - fail fast
        >>> container = DIContainer(error_strategy=ErrorHandlingStrategy.RAISE)
        >>> # Production mode - graceful degradation
        >>> container = DIContainer(error_strategy=ErrorHandlingStrategy.LOG)
    """

    LOG = "log"
    """Log the error and continue (may return None or raise depending on context)."""

    RAISE = "raise"
    """Log the error and re-raise the exception (fail-fast)."""

    IGNORE = "ignore"
    """Silently ignore errors (not recommended)."""


@dataclass
class ServiceRegistration:
    """Storage for service registration metadata.

    Attributes:
        interface: The abstract type or interface key.
        implementation: The concrete class to instantiate.
        factory: A callable that produces the instance.
        instance: A pre-created object instance (for singletons).
        lifetime: The lifecycle strategy for this service.
        dependencies: A map of parameter names to their required types.
    """

    interface: Type[Any]
    implementation: Optional[Type[Any]] = None
    factory: Optional[Callable[..., Any]] = None
    instance: Optional[Any] = None
    lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    # FIX: Explicitly mark as Optional to avoid 'unreachable' errors in post_init
    dependencies: Optional[Dict[str, Type[Any]]] = None

    def __post_init__(self) -> None:
        """Ensure dependencies dict is initialized."""
        if self.dependencies is None:
            self.dependencies = {}
