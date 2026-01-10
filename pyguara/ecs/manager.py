"""Entity Manager implementation for ECS with Spatial Indexing."""

from typing import Dict, Optional, Type, Iterator, Set
from collections import defaultdict

from pyguara.ecs.component import Component
from pyguara.ecs.entity import Entity


class EntityManager:
    """Manages the lifecycle and querying of entities.

    Acts as the central database for the game world.
    Optimized with Inverted Indexes for O(1) component lookups.
    """

    def __init__(self) -> None:
        """Initialize the entity manager."""
        self._entities: Dict[str, Entity] = {}

        # The Inverted Index: ComponentType -> Set[EntityID]
        # This solves the O(N) Query Problem.
        self._component_index: Dict[Type[Component], Set[str]] = defaultdict(set)

    def create_entity(self, entity_id: Optional[str] = None) -> Entity:
        """Create and register a new entity."""
        entity = Entity(entity_id)
        self.add_entity(entity)
        return entity

    def add_entity(self, entity: Entity) -> None:
        """Register an existing entity."""
        self._entities[entity.id] = entity

        # Hook into the entity's lifecycle to keep our index updated
        # This dependency injection allows the Entity to notify us without
        # knowing who we are (Observer pattern light).
        entity._on_component_added = self._on_entity_component_added
        entity._on_component_removed = self._on_entity_component_removed

        # Index any components that might already exist on this entity
        for comp_type in entity._components:
            self._component_index[comp_type].add(entity.id)

    def remove_entity(self, entity_id: str) -> None:
        """Destroy an entity and clean up indexes."""
        if entity_id in self._entities:
            entity = self._entities[entity_id]

            # Remove from all indexes
            # This is O(C) where C is number of components on the entity
            for comp_type in entity._components:
                if comp_type in self._component_index:
                    self._component_index[comp_type].discard(entity_id)

            del self._entities[entity_id]

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Retrieve an entity by ID."""
        return self._entities.get(entity_id)

    def get_all_entities(self) -> Iterator[Entity]:
        """Return all registered entities."""
        return iter(self._entities.values())

    def get_entities_with(self, *component_types: Type[Component]) -> Iterator[Entity]:
        """
        Query for entities containing ALL specified component types.

        Performance: O(K) where K is the number of entities matching the query,
        independent of the total number of entities in the world.
        """
        if not component_types:
            return

        # 1. Get the sets of entity IDs for each requested component
        # If any component type has no entities, the intersection is empty.
        sets = []
        for c_type in component_types:
            if c_type not in self._component_index:
                return  # Empty result
            sets.append(self._component_index[c_type])

        # 2. Sort by size (optimization: intersection is faster if we start small)
        sets.sort(key=len)

        # 3. Perform intersection
        result_ids = sets[0]
        for i in range(1, len(sets)):
            result_ids = result_ids & sets[i]  # Intersection

        # 4. Yield actual entities
        for eid in result_ids:
            yield self._entities[eid]

    def _on_entity_component_added(
        self, entity_id: str, component_type: Type[Component]
    ) -> None:
        """Update inverted index when an entity adds a component.

        Adds the entity to the inverted index for the component type,
        ensuring it appears in queries for this component.

        Args:
            entity_id: The ID of the entity that added a component.
            component_type: The type of component that was added.
        """
        self._component_index[component_type].add(entity_id)

    def _on_entity_component_removed(
        self, entity_id: str, component_type: Type[Component]
    ) -> None:
        """Update inverted index when an entity removes a component.

        Removes the entity from the inverted index for the component type,
        ensuring it no longer appears in queries for this component.

        Args:
            entity_id: The ID of the entity that removed a component.
            component_type: The type of component that was removed.
        """
        if component_type in self._component_index:
            self._component_index[component_type].discard(entity_id)
