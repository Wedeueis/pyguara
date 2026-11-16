"""Entity Component System core.

- `Entity`: a uniquely identified container for components.
- `Component`: the structural protocol every component satisfies.
- `BaseComponent`: the base class; rejects logic methods when a
  subclass is defined. `StrictComponent` is an alias for it.
- `EntityManager`: registration, lifecycle and querying for one world.
- `ChildOf`: ownership, so destruction cascades. `Transform`
  parenting is the spatial relation.
- `EntityPool`/`Poolable`: pooling for entities that spawn often.
"""

from pyguara.ecs.component import (
    ALLOWED_METHODS,
    BaseComponent,
    Component,
    StrictComponent,
)
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import EntityPool, Poolable
from pyguara.ecs.relations import ChildOf

__all__ = [
    "ALLOWED_METHODS",
    "BaseComponent",
    "Component",
    "Entity",
    "ChildOf",
    "EntityManager",
    "EntityPool",
    "Poolable",
    "StrictComponent",
]
