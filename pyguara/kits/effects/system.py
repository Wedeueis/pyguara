"""Ticks every active `Effect` and removes any that expire."""

from __future__ import annotations

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.effects.container import EffectContainer, remove_effect


class EffectSystem:
    """Ticks every `EffectContainer` entity's effects, expiring as needed."""

    def __init__(
        self, entity_manager: EntityManager, dispatcher: EventDispatcher
    ) -> None:
        """Store collaborators.

        Args:
            entity_manager: Source of `EffectContainer` entities.
            dispatcher: Forwarded to `remove_effect()` for an expired effect's
                `on_remove()`.
        """
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher

    def update(self, dt: float) -> None:
        """Advance every active effect by `dt`, removing any now expired.

        Iterates a snapshot of each container's effect list, since
        `remove_effect()` mutates it in place -- removing a just-expired
        effect mid-iteration must not skip the one after it.
        """
        for entity in self._entity_manager.get_entities_with(EffectContainer):
            container = entity.get_component(EffectContainer)
            for effect in list(container.effects):
                effect.update(dt)
                if effect.is_expired:
                    remove_effect(self._dispatcher, entity.id, container, effect)
