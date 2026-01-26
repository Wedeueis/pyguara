"""Module 3: Systems.

Reusing the MovementSystem logic.
"""

from pyguara.ecs.manager import EntityManager
from pyguara.common.types import Vector2
from games.asset_pipeline.components import Transform


class MovementSystem:
    """Updates entity positions."""

    def __init__(self, entity_manager: EntityManager):
        """Initialize the system."""
        self._em = entity_manager
        self._em.register_cached_query(Transform)

    def update(self, dt: float) -> None:
        """Move all entities with a Transform."""
        for entity in self._em.get_entities_with_cached(Transform):
            transform = entity.get_component(Transform)

            speed = 100.0
            new_x = transform.position.x + speed * dt
            new_y = transform.position.y + speed * dt

            transform.position = Vector2(new_x, new_y)

            if transform.position.x > 800:
                transform.position = Vector2(0, transform.position.y)
            if transform.position.y > 600:
                transform.position = Vector2(transform.position.x, 0)
