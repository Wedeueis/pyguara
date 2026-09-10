"""Syncs `SpatialTracked` entities into a `SpatialHash` every tick."""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.ecs.events import EntityDestroyed
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.spatial.components import SpatialTracked


class SpatialIndexSystem:
    """Keeps a `SpatialHash` current with every `SpatialTracked` entity.

    Re-inserts every tracked entity each tick -- cheap, since `SpatialHash`
    treats staying within the same cell as a no-op -- and removes an entity
    the moment it is destroyed, via `EntityDestroyed`, the same cleanup path
    `PhysicsSystem` uses for physics bodies.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        index: SpatialHash[str],
        event_dispatcher: EventDispatcher,
    ) -> None:
        """Store collaborators and subscribe to entity destruction.

        Args:
            entity_manager: Source of `SpatialTracked` entities.
            index: The hash to keep in sync.
            event_dispatcher: Notifies this system when an entity is
                destroyed, so its key can be dropped from `index`.
        """
        self._entity_manager = entity_manager
        self._index = index
        event_dispatcher.subscribe(EntityDestroyed, self._on_entity_destroyed)

    def update(self, delta_time: float) -> None:
        """Re-insert every tracked entity at its current world position.

        Args:
            delta_time: Unused; positions are read fresh from `Transform`
                every call, not integrated from a velocity here.
        """
        for entity in self._entity_manager.get_entities_with(SpatialTracked, Transform):
            tracked = entity.get_component(SpatialTracked)
            transform = entity.get_component(Transform)
            self._index.insert(entity.id, transform.world_position, tracked.mask)

    def _on_entity_destroyed(self, event: EntityDestroyed) -> None:
        """Drop a destroyed entity's key from the index, if it was tracked."""
        if not event.entity.has_component(SpatialTracked):
            return
        self._index.remove(event.entity.id)
