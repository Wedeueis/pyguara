"""Module 2: ECS Systems

Logic processors. They query data and update it.
"""

from pyguara.ecs.manager import EntityManager
from pyguara.common.types import Vector2
from games.ecs_mental_model.components import Transform

class MovementSystem:
    """Updates entity positions."""

    def __init__(self, entity_manager: EntityManager):
        self._em = entity_manager
        
        # Optimization: Register query for caching
        # This speeds up lookups from O(N) to O(1)
        self._em.register_cached_query(Transform)

    def update(self, dt: float) -> None:
        """Move all entities with a Transform."""
        
        # Use the cached query for performance
        # dt is 'delta time' (time passed since last frame)
        for entity in self._em.get_entities_with_cached(Transform):
            transform = entity.get_component(Transform)
            
            # Move diagonally
            speed = 100.0  # pixels per second
            new_x = transform.position.x + speed * dt
            new_y = transform.position.y + speed * dt
            
            transform.position = Vector2(new_x, new_y)
            
            # Simple bounds check to wrap around screen (assuming 800x600)
            if transform.position.x > 800:
                transform.position = Vector2(0, transform.position.y)
            if transform.position.y > 600:
                transform.position = Vector2(transform.position.x, 0)
