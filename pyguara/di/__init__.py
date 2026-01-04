"""
Dependency Injection package.

Provides a lightweight, type-safe container with support for lifecycle
management (Singleton, Scoped, Transient), circular dependency detection,
and automatic dependency resolution.
"""

from pyguara.di.container import DIContainer, DIScope
from pyguara.di.exceptions import (
    DIException,
    CircularDependencyException,
    ServiceNotFoundException,
)
from pyguara.di.types import ServiceLifetime
from pyguara.di.decorators import (
    singleton,
    transient,
    scoped,
    auto_register,
)

__all__ = [
    "DIContainer",
    "DIScope",
    "DIException",
    "CircularDependencyException",
    "ServiceNotFoundException",
    "ServiceLifetime",
    "singleton",
    "transient",
    "scoped",
    "auto_register",
]
