"""EntityManager: registration, lifecycle and querying for the ECS world."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from collections.abc import Set as AbstractSet
from typing import TypeVar, overload

from pyguara.ecs.component import Component
from pyguara.ecs.entity import Entity
from pyguara.ecs.query_cache import QueryCache
from pyguara.ecs.relations import ChildOf

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

        # Entities that exist and keep every component, but are excluded
        # from every query. See `set_entity_enabled()`.
        self._disabled: set[str] = set()

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

        # The `ChildOf` relation, both ways. `_parent_of` is the authority
        # -- it is what lets the component-removed hook know which parent
        # to detach from, since the component is already gone by then --
        # and `_children` is the reverse index that makes a cascade O(its
        # own subtree) rather than a scan of the world.
        self._parent_of: dict[str, str] = {}
        self._children: dict[str, set[str]] = defaultdict(set)

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

    def create_entities(self, count: int) -> list[Entity]:
        """Create and register `count` empty entities in one call.

        For spawning a wave at once -- a burst of projectiles, a room's
        worth of props from a generator -- where the caller then attaches
        components to each.

        **This is convenience, not a speed-up.** Measured against a
        `create_entity()` loop it is within noise (1.06x at 20,000), and it
        deliberately goes through `add_entity()` rather than inlining the
        registration: a hand-rolled copy of that body measured 1.21x, which
        does not buy a second path to keep in step with the first.

        The entities also come back live and queryable rather than behind a
        deferred index. A half-registered entity is a far worse thing to
        hand a caller than a few microseconds.

        What actually made bulk spawning expensive was neither -- it was
        `QueryCache` copying a whole result set for every component added,
        which is quadratic across a wave: 4000 entities cost 214ms with one
        cached query registered against 40ms with none. That is fixed in
        the cache, so every spawn benefits and not only this call.

        Args:
            count: How many entities to create. Zero returns an empty list.

        Returns:
            The new entities, in creation order.

        Raises:
            ValueError: If `count` is negative.
        """
        if count < 0:
            raise ValueError(f"count must not be negative, got {count}")

        entities = [Entity() for _ in range(count)]
        for entity in entities:
            self.add_entity(entity)
        return entities

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

        **Destruction cascades.** Every entity owning a `ChildOf` pointing
        at this one is removed too, depth first, and so are theirs. That is
        what stops a despawned enemy leaking the health bar, weapon and
        aura its prefab attached: nothing else in the engine knows those
        entities were only ever meaningful as part of it.

        Removing an unknown id is a no-op.

        Args:
            entity_id: The id of the entity to destroy.
        """
        entity = self._entities.get(entity_id)
        if entity is None:
            return

        # Soft-dead first, before the hook below can run any user code, so no
        # reentrant mutation can resurrect this id -- and before the cascade,
        # so that a removal subscriber cannot `set_parent()` something onto
        # this entity while it is being torn down. By now it is gone from
        # `_entities`, so that call raises instead of attaching a child to a
        # corpse that will never cascade again.
        entity._on_component_added = None
        entity._on_component_removed = None
        entity._is_removed = True
        del self._entities[entity_id]

        # Detach from this entity's own parent. `_unlink` would otherwise
        # run from the component-removed hook, which a soft-dead entity
        # never fires.
        self._unlink(entity_id)
        # A destroyed entity is not a parked one. Leaving its id behind
        # would disable whatever reused that id later, and `create_entity`
        # takes an explicit id.
        self._disabled.discard(entity_id)

        # Iterate a copy: a subscriber may unsubscribe itself, or tear down a
        # subsystem that unsubscribes, while it is being notified.
        for callback in list(self._entity_removed_callbacks):
            callback(entity)

        for component_type in entity._components:
            self._pending_index_cleanup.append((component_type, entity_id))

        # Then the subtree, read as a snapshot: each child's own removal
        # detaches it from this set. Depth first, so a grandchild is gone
        # before the child that owned it is reported.
        for child_id in self.children_of(entity_id):
            self.remove_entity(child_id)

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

    def clear(self) -> None:
        """Remove every entity from the world, then flush the indexes.

        Each entity is taken through `remove_entity()`, so
        `subscribe_entity_removed()` callbacks fire and downstream state
        (physics bodies, render batches, spatial indexes) is torn down, then
        `flush_pending_removals()` empties the inverted index and every cached
        query. The world is left empty and safe to repopulate -- the intended
        entry point for reloading a scene from disk, instead of clearing the
        internal dicts by hand (which leaves cached queries and subscribers
        out of sync).
        """
        for entity_id in list(self._entities):
            self.remove_entity(entity_id)
        self.flush_pending_removals()

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

    def set_entity_enabled(self, entity_id: str, enabled: bool) -> None:
        """Include or exclude an entity from every query, without changing it.

        A disabled entity still exists, still answers `get_entity()`, and
        **keeps every component it had** -- it simply stops matching
        `get_entities_with()` and friends. Re-enabling it brings it back
        exactly as it was.

        This is what `EntityPool` uses to park an idle entity. A pooled
        entity is never destroyed, so anything still attached to it goes
        on matching queries for the life of the scene: a pool of 700
        insects carrying a `FlockingAgent` each costs `FlockingSystem` all
        700 every tick whether ten are in play or seven hundred. Measured
        in `games/tamandua_murundus`, that alone was the difference
        between ~60 and ~18 frames per second.

        The alternative games reached for first -- attaching and detaching
        the query-visible components by hand on acquire and release --
        works, but it destroys component state that pooling exists to
        preserve, and it silently stops working the moment someone adds a
        component and forgets to add it to both lists.

        Args:
            entity_id: The entity to enable or disable. Unknown ids are
                ignored, so a caller need not check first.
            enabled: True to include it in queries again, False to park it.
        """
        if entity_id not in self._entities:
            self._disabled.discard(entity_id)
            return

        if enabled:
            self._disabled.discard(entity_id)
        else:
            self._disabled.add(entity_id)

    def is_entity_enabled(self, entity_id: str) -> bool:
        """Whether `entity_id` currently matches queries.

        Unknown and removed entities report False -- they match nothing
        either way, and reporting True for something that does not exist
        would be the more surprising answer.
        """
        return entity_id in self._entities and entity_id not in self._disabled

    # -------------------------------------------------------------------------
    # Relations
    # -------------------------------------------------------------------------

    def set_parent(self, child_id: str, parent_id: str | None) -> None:
        """Make one entity own another, or detach it.

        Ownership means destruction cascades: removing the parent removes
        the child. It says nothing about position -- a child that should
        also *move* with its parent sets its `Transform` parent too. See
        `ecs.relations` for why those are separate.

        Args:
            child_id: The entity to be owned.
            parent_id: The owning entity, or None to detach and leave the
                child standing on its own.

        Raises:
            KeyError: If either entity is unknown. Silently doing nothing
                would leave a caller believing a cascade is wired up when
                it is not, and the symptom would be a leak much later.
            ValueError: If the link would make an entity its own ancestor.
                A cycle makes the cascade unbounded, and the natural
                mistake -- re-parenting a node under its own descendant --
                is easy to make and invisible until something is destroyed.
        """
        child = self._entities.get(child_id)
        if child is None:
            raise KeyError(f"Unknown child entity '{child_id}'")

        if parent_id is None:
            if child.has_component(ChildOf):
                child.remove_component(ChildOf)
            return

        if parent_id not in self._entities:
            raise KeyError(f"Unknown parent entity '{parent_id}'")
        if parent_id == child_id:
            raise ValueError(f"Entity '{child_id}' cannot be its own parent")

        ancestor: str | None = parent_id
        while ancestor is not None:
            if ancestor == child_id:
                raise ValueError(
                    f"Parenting '{child_id}' to '{parent_id}' would make it its "
                    "own ancestor; the destroy cascade would not terminate."
                )
            ancestor = self._parent_of.get(ancestor)

        # Replace rather than mutate: the component add/remove hooks are
        # what keep the reverse index true, and assigning `parent_id` in
        # place runs neither.
        if child.has_component(ChildOf):
            child.remove_component(ChildOf)
        child.add_component(ChildOf(parent_id=parent_id))

    def parent_of(self, child_id: str) -> str | None:
        """Return the id of the entity owning `child_id`, if any.

        Args:
            child_id: The entity to look up.

        Returns:
            The parent's id, or None if the entity has no parent or does
            not exist.
        """
        return self._parent_of.get(child_id)

    def children_of(self, parent_id: str) -> list[str]:
        """Return the ids of the entities `parent_id` owns, directly.

        Direct children only -- walk it yourself for a whole subtree.

        Args:
            parent_id: The owning entity.

        Returns:
            A snapshot list, safe to iterate while destroying what is in
            it. The live set is mutated by every detach.
        """
        return list(self._children.get(parent_id, ()))

    def _link(self, child_id: str, parent_id: str) -> None:
        """Record a parent-child relation in both directions.

        Called from the component-added hook, which fires only once the
        relation is attached -- and `set_parent()` detaches any previous
        one first, so there is never a stale link to clear here.

        Args:
            child_id: The owned entity.
            parent_id: The owning entity.
        """
        self._parent_of[child_id] = parent_id
        self._children[parent_id].add(child_id)

    def _unlink(self, child_id: str) -> None:
        """Drop whatever relation `child_id` had, if any.

        Args:
            child_id: The formerly owned entity.
        """
        previous = self._parent_of.pop(child_id, None)
        if previous is None:
            return
        siblings = self._children.get(previous)
        if siblings is not None:
            siblings.discard(child_id)
            if not siblings:
                del self._children[previous]

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

    def get_entities_with(
        self,
        *component_types: type[Component],
        without: tuple[type[Component], ...] = (),
        any_of: tuple[type[Component], ...] = (),
    ) -> Iterator[Entity]:
        """Iterate entities matching a component query.

        The positional types are an **all-of**: an entity must carry every
        one. `without` and `any_of` narrow that further, and each is
        resolved through the same inverted index rather than by filtering
        the results, so "every enemy that is not stunned" costs one set
        difference instead of a `has_component` call per enemy per frame.

        ```python
        for enemy in manager.get_entities_with(Enemy, without=(Stunned,)):
            ...
        for burning in manager.get_entities_with(any_of=(OnFire, Scalded)):
            ...
        ```

        Args:
            *component_types: Classes the entity must all carry.
            without: Classes the entity must carry none of.
            any_of: Classes the entity must carry at least one of. Given
                alongside positional types it narrows them; given alone it
                is the whole query.

        Yields:
            Each matching entity. Yields nothing when no term is given at
            all.

        Note:
            `without` on its own -- "everything that is not X" -- has no
            positive term to start from, so it scans every entity. Every
            other shape starts from an index set.
        """
        if not component_types and not without and not any_of:
            return

        disabled = self._disabled
        for entity_id in self._matching_entity_ids(component_types, without, any_of):
            if entity_id in disabled:
                continue
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

        disabled = self._disabled
        for entity_id in cached_ids:
            if entity_id in disabled:
                continue
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

        disabled = self._disabled
        for entity_id in self._matching_entity_ids(component_types):
            if entity_id in disabled:
                continue
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

        disabled = self._disabled
        for entity_id in self._matching_entity_ids(component_types):
            if entity_id in disabled:
                continue
            entity = self._entities.get(entity_id)
            if entity is None:
                continue
            components = tuple(entity._components[c_type] for c_type in component_types)
            yield entity, components

    # -------------------------------------------------------------------------
    # Index maintenance
    # -------------------------------------------------------------------------

    def entity_ids_with(
        self,
        component_types: tuple[type[Component], ...],
        without: tuple[type[Component], ...] = (),
        any_of: tuple[type[Component], ...] = (),
    ) -> Iterator[str]:
        """Iterate live entity ids carrying every given component type.

        Unlike `get_entities_with()`, this does **not** skip disabled
        entities. It backs the query cache, which mirrors the component
        index: dormancy is applied when a query is iterated, never when
        its cache is built. Building the cache with disabled entities
        filtered out would strand them -- they are added to a cache by
        `add_component`, and nothing re-adds an entity that was merely
        parked.

        Args:
            component_types: Classes an entity must all carry.
            without: Classes an entity must carry none of.
            any_of: Classes an entity must carry at least one of.

        Yields:
            Matching entity ids, excluding entities already removed.
        """
        if not component_types and not without and not any_of:
            return
        entities = self._entities
        for entity_id in self._matching_entity_ids(component_types, without, any_of):
            if entity_id in entities:
                yield entity_id

    def _matching_entity_ids(
        self,
        component_types: tuple[type[Component], ...],
        without: tuple[type[Component], ...] = (),
        any_of: tuple[type[Component], ...] = (),
    ) -> AbstractSet[str]:
        """Resolve a query against the inverted index.

        Smallest index set first, so each intersection step scans as few ids as
        possible.

        For a single component type and no other terms the result is the live
        index set itself, not a copy. That is safe only because index cleanup
        is deferred to `flush_pending_removals()`, so the set cannot change
        mid-frame; callers must still skip ids whose entity is already
        soft-removed. Any additional term produces a new set, so the aliasing
        never escapes into a result the caller could be surprised by.

        Args:
            component_types: Classes an entity must all carry. May be empty
                if `any_of` or `without` is given.
            without: Classes an entity must carry none of.
            any_of: Classes an entity must carry at least one of.

        Returns:
            The ids of entities satisfying every term, possibly empty.
        """
        result: AbstractSet[str]

        if component_types:
            sets = []
            for component_type in component_types:
                index = self._component_index.get(component_type)
                if not index:
                    return _EMPTY_IDS
                sets.append(index)

            sets.sort(key=len)
            result = sets[0]
            for other in sets[1:]:
                result = result & other
        elif any_of:
            result = self._union_of(any_of)
        elif without:
            # No positive term at all: the candidate set is the whole world,
            # which is the only honest answer to "everything that is not X".
            # It costs a full scan, unlike every other shape here.
            result = self._entities.keys()
        else:
            return _EMPTY_IDS

        if component_types and any_of:
            result = result & self._union_of(any_of)

        if without:
            excluded = self._union_of(without)
            if excluded:
                result = result - excluded

        return result

    def _union_of(self, component_types: tuple[type[Component], ...]) -> set[str]:
        """Union the index sets for several component types.

        Args:
            component_types: The classes whose indexes to combine.

        Returns:
            A new set of every id carrying at least one of them.
        """
        union: set[str] = set()
        for component_type in component_types:
            index = self._component_index.get(component_type)
            if index:
                union |= index
        return union

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

        if component_type is ChildOf:
            entity = self._entities.get(entity_id)
            if entity is not None:
                self._link(entity_id, entity.get_component(ChildOf).parent_id)

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

        if component_type is ChildOf:
            self._unlink(entity_id)
