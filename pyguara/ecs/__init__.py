"""Entity Component System core.

Public surface:

- `Entity`: a uniquely identified container for components.
- `Component`: the structural protocol every component satisfies.
- `BaseComponent`: reference implementation; warns on logic methods.
- `StrictComponent`: rejects logic methods at class-definition time.
- `EntityManager`: registration, lifecycle and querying for one world.
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
