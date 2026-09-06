"""Incremental result caching for hot-path ECS queries.

The inverted index in `EntityManager` already makes component lookup O(1), but
intersecting several index sets still costs work on every call. A query
registered here keeps its result set materialised and updates it as components
are attached and detached, so the per-frame read is a plain set iteration.

Only register queries that run every frame; each registered query adds
bookkeeping to every component add and remove that touches one of its types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyguara.ecs.component import Component
    from pyguara.ecs.manager import EntityManager

_QueryKey = frozenset["type[Component]"]


class QueryCache:
    """Maintains materialised entity-id sets for registered component queries.

    Caches stay synchronised with the world through the two hooks
    `EntityManager` calls on every component change. Entity removal reuses the
    same path: when `EntityManager.flush_pending_removals()` cleans up a
    removed entity's index entries at the frame boundary, it calls
    `on_component_removed()` once per component type that entity carried, which
    drops it from every cache it belonged to.

    This caches final intersection results rather than implementing archetypes.
    PyGuara's inverted index is already a good fit for component lookup; only
    the repeated intersection needed eliminating.

    Example:
        ```python
        entity_manager.register_cached_query(Transform, RigidBody)

        for entity in entity_manager.get_entities_with_cached(Transform, RigidBody):
            ...
        ```
    """

    def __init__(self, manager: EntityManager) -> None:
        """Initialise an empty cache bound to one world.

        Args:
            manager: The entity manager whose queries are cached.
        """
        self._manager = manager
        self._cache: dict[_QueryKey, frozenset[str]] = {}
        self._registered_queries: set[_QueryKey] = set()
        # ComponentType -> the registered queries mentioning it, so a component
        # change only visits the queries it can actually affect.
        self._queries_by_type: dict[type[Component], list[_QueryKey]] = {}

    def register_query(self, *component_types: type[Component]) -> None:
        """Register a component combination for caching.

        Registering the same combination twice is a no-op. The initial result
        set is built immediately from the current world state.

        Args:
            *component_types: The component classes forming the query.
        """
        query_key: _QueryKey = frozenset(component_types)
        if query_key in self._registered_queries:
            return

        self._registered_queries.add(query_key)
        for component_type in query_key:
            self._queries_by_type.setdefault(component_type, []).append(query_key)
        self._rebuild(query_key)

    def get_cached(self, *component_types: type[Component]) -> frozenset[str] | None:
        """Return the cached entity ids for a query, if it is registered.

        Args:
            *component_types: The component classes forming the query.

        Returns:
            The cached ids — possibly an empty frozenset, when the query is
            registered but nothing currently matches — or None when this exact
            combination was never registered. Callers rely on that distinction:
            only None should fall back to a full intersection.
        """
        query_key: _QueryKey = frozenset(component_types)
        if query_key not in self._registered_queries:
            return None
        return self._cache.get(query_key, frozenset())

    def on_component_added(
        self, entity_id: str, component_type: type[Component]
    ) -> None:
        """Add an entity to every registered query it now satisfies.

        Args:
            entity_id: The id of the entity that gained a component.
            component_type: The component class that was attached.
        """
        entity = self._manager.get_entity(entity_id)
        if entity is None:
            return

        for query_key in self._queries_by_type.get(component_type, ()):
            if all(entity.has_component(ct) for ct in query_key):
                self._cache[query_key] = self._cache.get(query_key, frozenset()) | {
                    entity_id
                }

    def on_component_removed(
        self, entity_id: str, component_type: type[Component]
    ) -> None:
        """Drop an entity from every registered query mentioning a lost type.

        Also called once per component type an entity carried when the entity
        itself is removed — see `EntityManager.flush_pending_removals()`.

        Args:
            entity_id: The id of the entity that lost a component, or that was
                removed outright.
            component_type: The component class that was detached, or one the
                removed entity carried.
        """
        for query_key in self._queries_by_type.get(component_type, ()):
            current = self._cache.get(query_key)
            if current is not None:
                self._cache[query_key] = current - {entity_id}

    def rebuild_all(self) -> None:
        """Recompute every registered query from the current world state.

        Registrations are preserved. Use this after a bulk change that bypassed
        the component hooks, or to recover from a suspected desynchronisation.
        """
        for query_key in self._registered_queries:
            self._rebuild(query_key)

    def get_statistics(self) -> dict[str, Any]:
        """Summarise cache occupancy for monitoring and debugging.

        Returns:
            A mapping with `registered_queries` (int), `total_cached_entities`
            (int) and `queries` — one entry per registered query holding its
            `component_types` names and cached entity count.
        """
        queries: list[dict[str, Any]] = [
            {
                "component_types": sorted(ct.__name__ for ct in query_key),
                "cached_entities": len(self._cache.get(query_key, frozenset())),
            }
            for query_key in self._registered_queries
        ]

        return {
            "registered_queries": len(self._registered_queries),
            "total_cached_entities": sum(len(ids) for ids in self._cache.values()),
            "queries": queries,
        }

    def _rebuild(self, query_key: _QueryKey) -> None:
        """Recompute one query's result set from the inverted index.

        Args:
            query_key: The component types forming the query.
        """
        self._cache[query_key] = frozenset(
            entity.id for entity in self._manager.get_entities_with(*query_key)
        )
