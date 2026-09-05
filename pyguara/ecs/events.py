"""Events emitted by the ECS core."""

import time
from dataclasses import dataclass, field
from typing import Any

from pyguara.ecs.entity import Entity
from pyguara.events.protocols import Event


@dataclass
class EntityDestroyed(Event):
    """Fired synchronously at the moment an entity is soft-removed.

    Dispatched inside `EntityManager.remove_entity()`, immediately after the
    entity is soft-dead (removed from `_entities`, callbacks detached) but
    before its component index entries are physically cleaned up (deferred to
    the next frame boundary) -- handlers can still read the entity's
    components off `event.entity` here.
    """

    entity: Entity
    timestamp: float = field(default_factory=time.time)
    source: Any = None
