"""Prefab system for entity templates.

Provides a data-driven approach to entity creation through reusable
templates with support for:
- Component composition
- Inheritance and overrides
- Child entity hierarchies
- JSON/YAML serialization
- Weighted spawn tables
"""

from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.loader import Prefab, PrefabCache, PrefabLoader
from pyguara.prefabs.registry import (
    ComponentRegistry,
    get_component_registry,
    register_component,
)
from pyguara.prefabs.spawn_table import SpawnChoice, SpawnTable, load_spawn_table
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
    # Spawn tables
    "SpawnChoice",
    "SpawnTable",
    "load_spawn_table",
    # Loader
    "Prefab",
    "PrefabCache",
    "PrefabLoader",
]
