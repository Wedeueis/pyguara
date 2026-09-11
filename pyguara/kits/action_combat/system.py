"""Ticks `Health`'s invincibility timer down each frame."""

from __future__ import annotations

from pyguara.ecs.manager import EntityManager
from pyguara.kits.action_combat.health import Health


class HealthSystem:
    """Ticks every `Health` component's invincibility timer down."""

    def __init__(self, entity_manager: EntityManager) -> None:
        """Store the entity source.

        Args:
            entity_manager: EntityManager to query `Health` entities from.
        """
        self._entity_manager = entity_manager

    def update(self, dt: float) -> None:
        """Count every active `invincible_timer` down by `dt`, floored at 0."""
        for entity in self._entity_manager.get_entities_with(Health):
            health = entity.get_component(Health)
            if health.invincible_timer > 0:
                health.invincible_timer = max(0.0, health.invincible_timer - dt)
