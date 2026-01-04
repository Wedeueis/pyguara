"""Decorators for auto-registering services."""

from typing import Type, TypeVar, Any
from pyguara.di.types import ServiceLifetime
from pyguara.di.container import DIContainer

T = TypeVar("T")


def singleton(interface: Type[T]) -> Any:
    """Mark a class as a Singleton service."""

    def decorator(implementation: Type[T]) -> Type[T]:
        # We attach metadata to the class itself
        setattr(implementation, "_di_interface", interface)
        setattr(implementation, "_di_lifetime", ServiceLifetime.SINGLETON)
        return implementation

    return decorator


def transient(interface: Type[T]) -> Any:
    """Mark a class as a Transient service."""

    def decorator(implementation: Type[T]) -> Type[T]:
        setattr(implementation, "_di_interface", interface)
        setattr(implementation, "_di_lifetime", ServiceLifetime.TRANSIENT)
        return implementation

    return decorator


def scoped(interface: Type[T]) -> Any:
    """Mark a class as a Scoped service."""

    def decorator(implementation: Type[T]) -> Type[T]:
        setattr(implementation, "_di_interface", interface)
        setattr(implementation, "_di_lifetime", ServiceLifetime.SCOPED)
        return implementation

    return decorator


def auto_register(container: DIContainer, *classes: Type[Any]) -> None:
    """Register multiple decorated classes into the container automatically."""
    for cls in classes:
        if hasattr(cls, "_di_interface") and hasattr(cls, "_di_lifetime"):
            interface = getattr(cls, "_di_interface")
            lifetime = getattr(cls, "_di_lifetime")

            if lifetime == ServiceLifetime.SINGLETON:
                container.register_singleton(interface, cls)
            elif lifetime == ServiceLifetime.TRANSIENT:
                container.register_transient(interface, cls)
            elif lifetime == ServiceLifetime.SCOPED:
                container.register_scoped(interface, cls)
