"""
Entity Component System (ECS) Core.

Provides the foundational architecture for game objects:
- Entity: Container for components.
- Component: Data Protocol.
- EntityManager: Database and query system.
"""

from pyguara.ecs.component import Component
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager

__all__ = ["Component", "Entity", "EntityManager"]
