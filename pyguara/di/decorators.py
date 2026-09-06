"""Decorators that let a class carry its own DI registration metadata."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar, cast

from pyguara.di.container import DIContainer
from pyguara.di.types import ServiceLifetime

T = TypeVar("T")

_INTERFACE_ATTR = "_di_interface"
_LIFETIME_ATTR = "_di_lifetime"


class _DIMarked(Protocol):
    """A class carrying registration metadata written by these decorators."""

    _di_interface: type[Any]
    _di_lifetime: ServiceLifetime


def _mark(
    interface: type[T], lifetime: ServiceLifetime
) -> Callable[[type[T]], type[T]]:
    """Build a decorator that stamps registration metadata onto a class.

    Args:
        interface: The type the class should be registered against.
        lifetime: The lifecycle to register it with.

    Returns:
        A class decorator returning its argument unchanged.
    """

    def decorator(implementation: type[T]) -> type[T]:
        marked = cast(_DIMarked, implementation)
        marked._di_interface = interface
        marked._di_lifetime = lifetime
        return implementation

    return decorator


def singleton(interface: type[T]) -> Callable[[type[T]], type[T]]:
    """Mark a class for singleton registration.

    Args:
        interface: The type to register the class against.

    Returns:
        A class decorator.
    """
    return _mark(interface, ServiceLifetime.SINGLETON)


def transient(interface: type[T]) -> Callable[[type[T]], type[T]]:
    """Mark a class for transient registration.

    Args:
        interface: The type to register the class against.

    Returns:
        A class decorator.
    """
    return _mark(interface, ServiceLifetime.TRANSIENT)


def scoped(interface: type[T]) -> Callable[[type[T]], type[T]]:
    """Mark a class for scoped registration.

    Args:
        interface: The type to register the class against.

    Returns:
        A class decorator.
    """
    return _mark(interface, ServiceLifetime.SCOPED)


def auto_register(container: DIContainer, *classes: type[Any]) -> None:
    """Register every marked class into a container.

    Classes without registration metadata are skipped.

    Args:
        container: The container to register into.
        *classes: Candidate classes, marked by `singleton`, `transient` or
            `scoped`.
    """
    registrars = {
        ServiceLifetime.SINGLETON: container.register_singleton,
        ServiceLifetime.TRANSIENT: container.register_transient,
        ServiceLifetime.SCOPED: container.register_scoped,
    }

    for cls in classes:
        interface = getattr(cls, _INTERFACE_ATTR, None)
        lifetime = getattr(cls, _LIFETIME_ATTR, None)
        if interface is None or lifetime is None:
            continue
        register = registrars.get(lifetime)
        if register is not None:
            register(interface, cls)
