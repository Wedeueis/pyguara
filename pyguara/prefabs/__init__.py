"""Prefab system for entity templates.

Provides a data-driven approach to entity creation through reusable
templates with support for:
- Component composition
- Inheritance and overrides
- Child entity hierarchies
- JSON/YAML serialization
"""

from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.loader import Prefab, PrefabCache, PrefabLoader
from pyguara.prefabs.registry import (
    ComponentRegistry,
    get_component_registry,
    register_component,
)
from pyguara.prefabs.types import (
    PrefabChild,
    PrefabData,
    PrefabInstance,
)

__all__ = [
    # Types
    "PrefabChild",
    "PrefabData",
    "PrefabInstance",
    # Registry
    "ComponentRegistry",
    "get_component_registry",
    "register_component",
    # Factory
    "PrefabFactory",
    # Loader
    "Prefab",
    "PrefabCache",
    "PrefabLoader",
]
