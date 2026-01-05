"""Entity Manager implementation for ECS."""

from typing import Dict, List, Optional, Type, Iterator

from pyguara.ecs.component import Component
from pyguara.ecs.entity import Entity


class EntityManager:
    """Manages the lifecycle and querying of entities.

    Acts as the central database for the game world.
    """

    def __init__(self) -> None:
        """Initialize the entity manager."""
        self._entities: Dict[str, Entity] = {}
        # Cache for queries: Signature (Component Types) -> List[Entity]
        self._query_cache: Dict[frozenset[Type[Component]], List[Entity]] = {}

    def create_entity(self, entity_id: Optional[str] = None) -> Entity:
        """Create and register a new entity.

        Args:
            entity_id: Optional custom ID.

        Returns:
            The created entity.
        """
        entity = Entity(entity_id)
        self.add_entity(entity)
        return entity

    def add_entity(self, entity: Entity) -> None:
        """Register an existing entity.

        Args:
            entity: The entity to add.
        """
        if entity.id in self._entities:
            # If ID exists but object is different, warning/error
            # For now, overwrite
            pass
        self._entities[entity.id] = entity
        self._invalidate_query_cache()

    def remove_entity(self, entity_id: str) -> None:
        """Destroy an entity.

        Args:
            entity_id: ID of the entity to remove.
        """
        if entity_id in self._entities:
            del self._entities[entity_id]
            self._invalidate_query_cache()

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Retrieve an entity by ID."""
        return self._entities.get(entity_id)

    def get_entities_with(self, *component_types: Type[Component]) -> Iterator[Entity]:
        """Query for entities containing ALL specified component types.

        This is the primary method Systems use to find relevant entities.

        Args:
            *component_types: Variable list of Component classes.

        Yields:
            Entities that have instances of all requested component types.
        """
        # Check cache if query is complex, but for now simple iteration is fine
        # for a Python engine unless entity count > 10,000

        # Optimization: Find component type with fewest entities (if we maintained reverse map)
        # For simplicity in this version:

        for entity in self._entities.values():
            if all(entity.has_component(ctype) for ctype in component_types):
                yield entity

    def _invalidate_query_cache(self) -> None:
        """Clear query cache when entity composition changes."""
        self._query_cache.clear()
