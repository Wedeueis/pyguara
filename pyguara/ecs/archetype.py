"""Archetype storage for cache-friendly ECS iteration.

An archetype represents a unique combination of component types. All entities
with the same set of component types are stored together in contiguous arrays,
enabling fast iteration and cache-friendly access patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Dict,
    FrozenSet,
    Iterator,
    List,
    Optional,
    Tuple,
    Type,
)

if TYPE_CHECKING:
    from pyguara.ecs.component import Component


@dataclass
class Archetype:
    """Storage for entities sharing the same component composition.

    All entities with identical component types are stored in the same archetype.
    Components are stored in parallel arrays for cache-friendly iteration.

    Attributes:
        component_types: Immutable set of component types in this archetype.
        entity_ids: Ordered list of entity IDs (insertion order for determinism).
        component_arrays: Component data stored in parallel arrays by type.
        entity_index: Fast lookup from entity_id to row index.
    """

    component_types: FrozenSet[Type[Component]]
    entity_ids: List[str] = field(default_factory=list)
    component_arrays: Dict[Type[Component], List[Component]] = field(
        default_factory=dict
    )
    entity_index: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize component arrays for each type."""
        for comp_type in self.component_types:
            if comp_type not in self.component_arrays:
                self.component_arrays[comp_type] = []

    def add_entity(
        self, entity_id: str, components: Dict[Type[Component], Component]
    ) -> int:
        """Add an entity with its components to this archetype.

        Args:
            entity_id: Unique identifier for the entity.
            components: Dictionary mapping component types to instances.

        Returns:
            Row index where the entity was stored.

        Raises:
            ValueError: If entity already exists or components don't match archetype.
        """
        if entity_id in self.entity_index:
            raise ValueError(f"Entity {entity_id} already exists in archetype")

        # Verify components match archetype
        if set(components.keys()) != self.component_types:
            raise ValueError(
                f"Component types {set(components.keys())} don't match "
                f"archetype {self.component_types}"
            )

        # Add to arrays
        row = len(self.entity_ids)
        self.entity_ids.append(entity_id)
        self.entity_index[entity_id] = row

        for comp_type, component in components.items():
            self.component_arrays[comp_type].append(component)

        return row

    def remove_entity(self, entity_id: str) -> Dict[Type[Component], Component]:
        """Remove an entity from this archetype.

        Uses swap-and-pop for O(1) removal while maintaining array density.

        Args:
            entity_id: ID of entity to remove.

        Returns:
            Dictionary of the removed entity's components.

        Raises:
            KeyError: If entity doesn't exist in this archetype.
        """
        if entity_id not in self.entity_index:
            raise KeyError(f"Entity {entity_id} not found in archetype")

        row = self.entity_index[entity_id]
        last_row = len(self.entity_ids) - 1

        # Collect components being removed
        removed_components: Dict[Type[Component], Component] = {}
        for comp_type, array in self.component_arrays.items():
            removed_components[comp_type] = array[row]

        # Swap with last element if not already last
        if row != last_row:
            last_entity_id = self.entity_ids[last_row]

            # Swap entity IDs
            self.entity_ids[row] = last_entity_id
            self.entity_index[last_entity_id] = row

            # Swap components in each array
            for comp_type, array in self.component_arrays.items():
                array[row] = array[last_row]

        # Pop last element
        self.entity_ids.pop()
        del self.entity_index[entity_id]
        for array in self.component_arrays.values():
            array.pop()

        return removed_components

    def get_component(self, entity_id: str, comp_type: Type[Component]) -> Component:
        """Get a specific component for an entity.

        Args:
            entity_id: Entity to look up.
            comp_type: Component type to retrieve.

        Returns:
            The component instance.

        Raises:
            KeyError: If entity or component type not found.
        """
        row = self.entity_index[entity_id]
        return self.component_arrays[comp_type][row]

    def get_components(self, entity_id: str) -> Dict[Type[Component], Component]:
        """Get all components for an entity.

        Args:
            entity_id: Entity to look up.

        Returns:
            Dictionary of all components.

        Raises:
            KeyError: If entity not found.
        """
        row = self.entity_index[entity_id]
        return {
            comp_type: array[row] for comp_type, array in self.component_arrays.items()
        }

    def set_component(
        self, entity_id: str, comp_type: Type[Component], component: Component
    ) -> None:
        """Replace a component for an entity.

        Args:
            entity_id: Entity to modify.
            comp_type: Component type to replace.
            component: New component instance.

        Raises:
            KeyError: If entity or component type not found.
        """
        row = self.entity_index[entity_id]
        self.component_arrays[comp_type][row] = component

    def has_entity(self, entity_id: str) -> bool:
        """Check if an entity exists in this archetype."""
        return entity_id in self.entity_index

    def __len__(self) -> int:
        """Return number of entities in this archetype."""
        return len(self.entity_ids)

    def __iter__(self) -> Iterator[str]:
        """Iterate over entity IDs in insertion order."""
        return iter(self.entity_ids)

    def iter_components(
        self, *types: Type[Component]
    ) -> Iterator[Tuple[Component, ...]]:
        """Iterate over component tuples in order.

        Args:
            *types: Component types to include in tuples.

        Yields:
            Tuples of components in the specified order.
        """
        if not types:
            types = tuple(self.component_types)

        arrays = [self.component_arrays[t] for t in types]
        for i in range(len(self.entity_ids)):
            yield tuple(arr[i] for arr in arrays)

    def iter_with_entity_ids(
        self, *types: Type[Component]
    ) -> Iterator[Tuple[str, Tuple[Component, ...]]]:
        """Iterate over (entity_id, components) pairs.

        Args:
            *types: Component types to include in tuples.

        Yields:
            Tuples of (entity_id, (component1, component2, ...)).
        """
        if not types:
            types = tuple(self.component_types)

        arrays = [self.component_arrays[t] for t in types]
        for i, entity_id in enumerate(self.entity_ids):
            yield entity_id, tuple(arr[i] for arr in arrays)


class ArchetypeGraph:
    """Graph of archetype transitions for efficient component add/remove.

    Maintains edges between archetypes to enable O(1) lookups when
    adding or removing components from entities.
    """

    def __init__(self) -> None:
        """Initialize the archetype graph."""
        # add_edges[archetype][component_type] = resulting_archetype
        self._add_edges: Dict[
            FrozenSet[Type[Component]],
            Dict[Type[Component], FrozenSet[Type[Component]]],
        ] = {}
        # remove_edges[archetype][component_type] = resulting_archetype
        self._remove_edges: Dict[
            FrozenSet[Type[Component]],
            Dict[Type[Component], FrozenSet[Type[Component]]],
        ] = {}

    def get_add_target(
        self, source: FrozenSet[Type[Component]], comp_type: Type[Component]
    ) -> Optional[FrozenSet[Type[Component]]]:
        """Get the archetype resulting from adding a component.

        Args:
            source: Current archetype's component types.
            comp_type: Component type being added.

        Returns:
            Target archetype's component types, or None if not cached.
        """
        return self._add_edges.get(source, {}).get(comp_type)

    def get_remove_target(
        self, source: FrozenSet[Type[Component]], comp_type: Type[Component]
    ) -> Optional[FrozenSet[Type[Component]]]:
        """Get the archetype resulting from removing a component.

        Args:
            source: Current archetype's component types.
            comp_type: Component type being removed.

        Returns:
            Target archetype's component types, or None if not cached.
        """
        return self._remove_edges.get(source, {}).get(comp_type)

    def add_edge(
        self,
        source: FrozenSet[Type[Component]],
        comp_type: Type[Component],
        target: FrozenSet[Type[Component]],
    ) -> None:
        """Record an add transition edge.

        Args:
            source: Source archetype's component types.
            comp_type: Component type being added.
            target: Target archetype's component types.
        """
        if source not in self._add_edges:
            self._add_edges[source] = {}
        self._add_edges[source][comp_type] = target

    def remove_edge(
        self,
        source: FrozenSet[Type[Component]],
        comp_type: Type[Component],
        target: FrozenSet[Type[Component]],
    ) -> None:
        """Record a remove transition edge.

        Args:
            source: Source archetype's component types.
            comp_type: Component type being removed.
            target: Target archetype's component types.
        """
        if source not in self._remove_edges:
            self._remove_edges[source] = {}
        self._remove_edges[source][comp_type] = target
