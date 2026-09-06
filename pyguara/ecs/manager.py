"""EntityManager: registration, lifecycle and querying for the ECS world."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from collections.abc import Set as AbstractSet
from typing import TypeVar, overload

from pyguara.ecs.component import Component
from pyguara.ecs.entity import Entity
from pyguara.ecs.query_cache import QueryCache

C1 = TypeVar("C1", bound=Component)
C2 = TypeVar("C2", bound=Component)
C3 = TypeVar("C3", bound=Component)
C4 = TypeVar("C4", bound=Component)

_EMPTY_IDS: frozenset[str] = frozenset()

EntityRemovedCallback = Callable[[Entity], None]
"""Called synchronously with an entity at the moment it is soft-removed."""


class EntityManager:
    """Central database for the entities in one world.

    Queries are backed by an inverted index (`ComponentType -> {EntityID}`), so
    matching entities are found by set intersection rather than by scanning
    every entity.

    Entity removal is a two-step process. `remove_entity()` makes an entity
    soft-dead immediately; `flush_pending_removals()` physically cleans up its
    index entries at the frame boundary. Keeping the index stable for the whole
    frame is what makes every query safe to iterate while systems destroy
    entities.
    """

    def __init__(self) -> None:
        """Initialise an empty world."""
        self._entities: dict[str, Entity] = {}

        # The inverted index: ComponentType -> Set[EntityID].
        self._component_index: dict[type[Component], set[str]] = defaultdict(set)

        self._query_cache: QueryCache = QueryCache(self)

        # Entities removed this frame: their id is already gone from
        # _entities (soft-dead), but their component-index entries linger
        # until flush_pending_removals() runs at the frame boundary. This is
        # what makes single-type queries safe to alias the live index set
        # directly -- the set is never mutated mid-frame.
        self._pending_index_cleanup: list[tuple[type[Component], str]] = []

        # Subscribers notified synchronously in remove_entity(), at the moment
        # of soft-death, with the (still component-intact) removed Entity.
        # A list rather than a single slot: EntityManager stays decoupled from
        # the event system (Scene subscribes to dispatch EntityDestroyed), but
        # tools such as the editor inspector need to observe removals too, and
        # a single slot would let whichever registered last silently displace
        # the others.
        self._entity_removed_callbacks: list[EntityRemovedCallback] = []

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def create_entity(self, entity_id: str | None = None) -> Entity:
        """Create an entity and register it with this manager.

        Args:
            entity_id: Explicit id. Defaults to a fresh UUID4 string.

        Returns:
            The newly registered entity.
        """
        entity = Entity(entity_id)
        self.add_entity(entity)
        return entity

    def add_entity(self, entity: Entity) -> None:
        """Register an entity that was built outside this manager.

        Components already attached to the entity — the usual case for clones,
        prefabs and deserialised scenes — are indexed through the same path as
        components added later, so cached queries see them too.

        Args:
            entity: An entity to bring into this world.

        Raises:
            RuntimeError: If the entity has already been removed. Removal is
                terminal; re-registering a soft-dead entity would produce one
                that is reachable by id but invisible to every query.
        """
        if entity._is_removed:
            raise RuntimeError(
                f"Entity {entity.id} has been removed; cannot add_entity() a dead "
                f"entity. Removal is terminal -- use Entity.clone() to make a "
                f"fresh, re-addable entity instead."
            )

        self._entities[entity.id] = entity

        # Observer hookup: the entity notifies us of component changes without
        # holding a reference to the manager itself.
        entity._on_component_added = self._on_entity_component_added
        entity._on_component_removed = self._on_entity_component_removed

        for component_type in entity._components:
            self._on_entity_component_added(entity.id, component_type)

    def remove_entity(self, entity_id: str) -> None:
        """Soft-destroy an entity: immediate, terminal, not reusable.

        The entity is gone from the registry and its manager callbacks detached
        before this method returns, so nothing can see or resurrect it from
        that instant on; further mutation of it raises. Physical index cleanup
        is deferred to `flush_pending_removals()`.

        Subscribers registered via `subscribe_entity_removed()` are notified
        synchronously here, after soft-death but before the deferred cleanup,
        so they can still read the entity's components.

        Removing an unknown id is a no-op.

        Args:
            entity_id: The id of the entity to destroy.
        """
        entity = self._entities.get(entity_id)
        if entity is None:
            return

        # Soft-dead first, before the hook below can run any user code, so no
        # reentrant mutation can resurrect this id.
        entity._on_component_added = None
        entity._on_component_removed = None
        entity._is_removed = True
        del self._entities[entity_id]

        # Iterate a copy: a subscriber may unsubscribe itself, or tear down a
        # subsystem that unsubscribes, while it is being notified.
        for callback in list(self._entity_removed_callbacks):
            callback(entity)

        for component_type in entity._components:
            self._pending_index_cleanup.append((component_type, entity_id))

    def flush_pending_removals(self) -> None:
        """Clean up index entries for entities soft-removed since the last flush.

        Call once per frame at the frame boundary, never mid-frame: holding the
        index stable for the duration of a frame is what keeps that frame's
        queries safe to iterate.
        """
        for component_type, entity_id in self._pending_index_cleanup:
            index = self._component_index.get(component_type)
            if index is not None:
                index.discard(entity_id)
            self._query_cache.on_component_removed(entity_id, component_type)

        self._pending_index_cleanup.clear()

    def subscribe_entity_removed(self, callback: EntityRemovedCallback) -> None:
        """Register a callback to run when an entity is removed from this world.

        The callback fires synchronously from `remove_entity()`, at the moment
        of soft-death and before index cleanup, so it can still read the
        removed entity's components. Exceptions propagate to the caller of
        `remove_entity()`; a subscriber that may fail should handle its own
        errors.

        Subscribing a callback that is already subscribed is a no-op, so a
        scene whose dependencies are resolved twice does not double-notify.

        Args:
            callback: Receives the entity being removed.
        """
        if callback not in self._entity_removed_callbacks:
            self._entity_removed_callbacks.append(callback)

    def unsubscribe_entity_removed(self, callback: EntityRemovedCallback) -> None:
        """Stop notifying a callback registered via `subscribe_entity_removed()`.

        Unsubscribing a callback that is not subscribed is a no-op.

        Args:
            callback: The callback to remove.
        """
        if callback in self._entity_removed_callbacks:
            self._entity_removed_callbacks.remove(callback)

    # -------------------------------------------------------------------------
    # Lookup
    # -------------------------------------------------------------------------

    def get_entity(self, entity_id: str) -> Entity | None:
        """Retrieve a live entity by id.

        Args:
            entity_id: The id to look up.

        Returns:
            The entity, or None if it is unknown or already removed.
        """
        return self._entities.get(entity_id)

    def get_all_entities(self) -> Iterator[Entity]:
        """Iterate every live entity in the world.

        Yields:
            Each registered entity.
        """
        return iter(self._entities.values())

    def get_entities_with(self, *component_types: type[Component]) -> Iterator[Entity]:
        """Iterate entities carrying all of the given component types.

        Args:
            *component_types: Component classes the entity must all carry.

        Yields:
            Each matching entity. Yields nothing if no types are given.
        """
        if not component_types:
            return

        for entity_id in self._matching_entity_ids(component_types):
            entity = self._entities.get(entity_id)
            if entity is not None:
                yield entity

    # -------------------------------------------------------------------------
    # Cached queries
    # -------------------------------------------------------------------------

    def register_cached_query(self, *component_types: type[Component]) -> None:
        """Mark a component combination as hot-path so its result set is cached.

        Register during system initialisation, for queries that run every
        frame. The cache is maintained incrementally as components are added
        and removed, trading a little bookkeeping for a query that skips the
        set intersection entirely. Do not register one-off queries.

        Args:
            *component_types: The component classes forming the query.

        Example:
            ```python
            class PhysicsSystem:
                def __init__(self, entity_manager: EntityManager) -> None:
                    entity_manager.register_cached_query(Transform, RigidBody)
            ```
        """
        self._query_cache.register_query(*component_types)

    def get_entities_with_cached(
        self, *component_types: type[Component]
    ) -> Iterator[Entity]:
        """Iterate entities for a query registered via `register_cached_query()`.

        Falls back to `get_entities_with()` when the exact combination was
        never registered. A registered query that currently matches nothing
        yields nothing — it does not fall back.

        Args:
            *component_types: The component classes forming the query.

        Yields:
            Each matching entity.
        """
        cached_ids = self._query_cache.get_cached(*component_types)

        if cached_ids is None:
            yield from self.get_entities_with(*component_types)
            return

        for entity_id in cached_ids:
            entity = self._entities.get(entity_id)
            if entity is not None:
                yield entity

    # -------------------------------------------------------------------------
    # Fast-path tuple queries
    # -------------------------------------------------------------------------
    # These bypass the Entity wrapper and yield components directly. Use them in
    # hot systems (physics, rendering) that never need the entity itself.

    @overload
    def get_components(
        self, c1: type[C1], c2: type[C2], /
    ) -> Iterator[tuple[C1, C2]]: ...

    @overload
    def get_components(
        self, c1: type[C1], c2: type[C2], c3: type[C3], /
    ) -> Iterator[tuple[C1, C2, C3]]: ...

    @overload
    def get_components(
        self, c1: type[C1], c2: type[C2], c3: type[C3], c4: type[C4], /
    ) -> Iterator[tuple[C1, C2, C3, C4]]: ...

    @overload
    def get_components(
        self, *component_types: type[Component]
    ) -> Iterator[tuple[Component, ...]]: ...

    def get_components(
        self, *component_types: type[Component]
    ) -> Iterator[tuple[Component, ...]]:
        """Iterate component tuples for entities carrying all the given types.

        Args:
            *component_types: Component classes the entity must all carry.
                Overloads give precise tuple types for two to four arguments.

        Yields:
            One tuple per matching entity, with components in the order the
            types were given.

        Example:
            ```python
            for transform, body in manager.get_components(Transform, RigidBody):
                transform.position += body.velocity * dt
            ```
        """
        if not component_types:
            return

        for entity_id in self._matching_entity_ids(component_types):
            entity = self._entities.get(entity_id)
            if entity is None:
                continue
            yield tuple(entity._components[c_type] for c_type in component_types)

    def get_components_with_entity(
        self, *component_types: type[Component]
    ) -> Iterator[tuple[Entity, tuple[Component, ...]]]:
        """Iterate `(entity, components)` pairs for entities carrying all types.

        Use instead of `get_components()` when the loop body also needs the
        entity — its id, its tags, or to attach and detach components.

        Args:
            *component_types: Component classes the entity must all carry.

        Yields:
            `(entity, components)` pairs, with components in the order the
            types were given.
        """
        if not component_types:
            return

        for entity_id in self._matching_entity_ids(component_types):
            entity = self._entities.get(entity_id)
            if entity is None:
                continue
            components = tuple(entity._components[c_type] for c_type in component_types)
            yield entity, components

    # -------------------------------------------------------------------------
    # Index maintenance
    # -------------------------------------------------------------------------

    def _matching_entity_ids(
        self, component_types: tuple[type[Component], ...]
    ) -> AbstractSet[str]:
        """Intersect the inverted index for a non-empty set of component types.

        Smallest index set first, so each intersection step scans as few ids as
        possible.

        For a single component type the result is the live index set itself,
        not a copy. That is safe only because index cleanup is deferred to
        `flush_pending_removals()`, so the set cannot change mid-frame; callers
        must still skip ids whose entity is already soft-removed.

        Args:
            component_types: One or more component classes. Must not be empty.

        Returns:
            The ids of entities carrying every given type, possibly empty.
        """
        sets = []
        for component_type in component_types:
            index = self._component_index.get(component_type)
            if not index:
                return _EMPTY_IDS
            sets.append(index)

        sets.sort(key=len)
        result: AbstractSet[str] = sets[0]
        for other in sets[1:]:
            result = result & other
        return result

    def _on_entity_component_added(
        self, entity_id: str, component_type: type[Component]
    ) -> None:
        """Index an entity under a component type it just gained.

        Args:
            entity_id: The id of the entity that gained the component.
            component_type: The component class that was attached.
        """
        self._component_index[component_type].add(entity_id)
        self._query_cache.on_component_added(entity_id, component_type)

    def _on_entity_component_removed(
        self, entity_id: str, component_type: type[Component]
    ) -> None:
        """Drop an entity from the index for a component type it just lost.

        Args:
            entity_id: The id of the entity that lost the component.
            component_type: The component class that was detached.
        """
        index = self._component_index.get(component_type)
        if index is not None:
            index.discard(entity_id)
        self._query_cache.on_component_removed(entity_id, component_type)
