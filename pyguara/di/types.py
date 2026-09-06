"""Type definitions and data structures for DI."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pyguara.errors import ErrorHandlingStrategy


class ServiceLifetime(Enum):
    """Service lifecycle management strategies."""

    SINGLETON = "singleton"  # One instance per container (shared)
    TRANSIENT = "transient"  # New instance every time it is requested
    SCOPED = "scoped"  # One instance per active scope


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
        param_defaults: A set of parameter names that have default values.
            Cached during registration to avoid inspect.signature at runtime.
    """

    interface: type[Any]
    implementation: type[Any] | None = None
    factory: Callable[..., Any] | None = None
    instance: Any | None = None
    lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    # FIX: Explicitly mark as Optional to avoid 'unreachable' errors in post_init
    dependencies: dict[str, type[Any]] | None = None
    param_defaults: set[str] | None = None

    def __post_init__(self) -> None:
        """Ensure dependencies dict and param_defaults set are initialized."""
        if self.dependencies is None:
            self.dependencies = {}
        if self.param_defaults is None:
            self.param_defaults = set()


# Re-exported so `from pyguara.di.types import ErrorHandlingStrategy` keeps
# working. The definition lives in pyguara.errors because EventDispatcher needs
# the same enum and must not be imported from here.
__all__ = ["ErrorHandlingStrategy", "ServiceLifetime", "ServiceRegistration"]
