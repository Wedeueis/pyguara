"""Type definitions and data structures for DI."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Type


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
