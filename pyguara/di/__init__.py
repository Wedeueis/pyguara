"""
Dependency Injection package.

Provides a lightweight, type-safe container with support for lifecycle
management (Singleton, Scoped, Transient), circular dependency detection,
and automatic dependency resolution.
"""

from pyguara.di.container import DIContainer, DIScope
from pyguara.di.decorators import (
    auto_register,
    scoped,
    singleton,
    transient,
)
from pyguara.di.exceptions import (
    CircularDependencyException,
    DIException,
    ServiceNotFoundException,
)
from pyguara.di.types import ServiceLifetime

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
