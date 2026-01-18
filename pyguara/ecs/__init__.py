"""Entity Component System (ECS) Core.

Provides the foundational architecture for game objects:
- Entity: Container for components.
- Component: Data Protocol (interface).
- BaseComponent: Reference implementation with legacy method support.
- StrictComponent: Enforces data-only pattern (recommended for new components).
- EntityManager: Database and query system.
"""

from pyguara.ecs.component import (
    ALLOWED_METHODS,
    BaseComponent,
    Component,
    StrictComponent,
)
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager

__all__ = [
    "ALLOWED_METHODS",
    "BaseComponent",
    "Component",
    "Entity",
    "EntityManager",
    "StrictComponent",
]
