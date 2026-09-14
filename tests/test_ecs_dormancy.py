"""Tests for entity dormancy: present, componented, and matching nothing.

A pooled entity is never destroyed, so anything still attached to it goes
on matching queries for the life of the scene. `set_entity_enabled()` is
how a pool parks one without stripping it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import EntityPool, Poolable


@dataclass(slots=True)
class Alpha(StrictComponent):
    """A marker component."""

    value: int = 0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class Beta(StrictComponent):
    """A second marker component."""

    value: int = 0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state."""
        StrictComponent.__init__(self)


def world_with(count: int = 3) -> tuple[EntityManager, list]:
    """A manager holding `count` entities, each carrying Alpha and Beta."""
    manager = EntityManager()
    entities = []
    for index in range(count):
        entity = manager.create_entity()
        entity.add_component(Alpha(value=index))
        entity.add_component(Beta(value=index))
        entities.append(entity)
    return manager, entities


def ids_with(manager: EntityManager, *types) -> set[str]:
    """The ids a query yields."""
    return {entity.id for entity in manager.get_entities_with(*types)}


class TestQueriesSkipDisabledEntities:
    def test_a_disabled_entity_leaves_single_type_queries(self) -> None:
        manager, entities = world_with()

        manager.set_entity_enabled(entities[1].id, False)

        assert ids_with(manager, Alpha) == {entities[0].id, entities[2].id}

    def test_a_disabled_entity_leaves_multi_type_queries(self) -> None:
        manager, entities = world_with()

        manager.set_entity_enabled(entities[1].id, False)

        assert ids_with(manager, Alpha, Beta) == {entities[0].id, entities[2].id}

    def test_a_disabled_entity_leaves_component_tuple_queries(self) -> None:
        """`get_components()` is a separate code path from
        `get_entities_with()`, and a filter applied to one and not the
        other is the kind of gap nothing else would catch."""
        manager, entities = world_with()

        manager.set_entity_enabled(entities[1].id, False)
        values = {alpha.value for (alpha,) in manager.get_components(Alpha)}

        assert values == {0, 2}

    def test_a_disabled_entity_leaves_pair_queries(self) -> None:
        manager, entities = world_with()

        manager.set_entity_enabled(entities[1].id, False)
        found = {
            entity.id for entity, _ in manager.get_components_with_entity(Alpha, Beta)
        }

        assert found == {entities[0].id, entities[2].id}

    def test_a_disabled_entity_leaves_cached_queries(self) -> None:
        manager, entities = world_with()
        manager.register_cached_query(Alpha, Beta)

        manager.set_entity_enabled(entities[1].id, False)
        found = {entity.id for entity in manager.get_entities_with_cached(Alpha, Beta)}

        assert found == {entities[0].id, entities[2].id}


class TestDisablingPreservesTheEntity:
    def test_a_disabled_entity_keeps_its_components(self) -> None:
        """The whole difference from detaching them by hand: pooling
        exists to preserve state, and stripping components destroys it."""
        manager, entities = world_with()

        manager.set_entity_enabled(entities[0].id, False)

        assert entities[0].get_component(Alpha).value == 0
        assert entities[0].has_component(Beta)

    def test_a_disabled_entity_is_still_retrievable_by_id(self) -> None:
        manager, entities = world_with()

        manager.set_entity_enabled(entities[0].id, False)

        assert manager.get_entity(entities[0].id) is entities[0]

    def test_re_enabling_restores_it_exactly(self) -> None:
        manager, entities = world_with()
        manager.set_entity_enabled(entities[1].id, False)

        manager.set_entity_enabled(entities[1].id, True)

        assert ids_with(manager, Alpha, Beta) == {e.id for e in entities}

    def test_enabling_is_idempotent(self) -> None:
        manager, entities = world_with()

        manager.set_entity_enabled(entities[0].id, True)
        manager.set_entity_enabled(entities[0].id, True)

        assert manager.is_entity_enabled(entities[0].id)

    def test_disabling_is_idempotent(self) -> None:
        manager, entities = world_with()

        manager.set_entity_enabled(entities[0].id, False)
        manager.set_entity_enabled(entities[0].id, False)

        assert not manager.is_entity_enabled(entities[0].id)

    def test_an_unknown_id_is_ignored_rather_than_raising(self) -> None:
        """A caller parking an entity it may have already destroyed should
        not have to check first."""
        manager, _ = world_with()

        manager.set_entity_enabled("no-such-entity", False)

        assert not manager.is_entity_enabled("no-such-entity")

    def test_a_removed_entity_reports_disabled(self) -> None:
        manager, entities = world_with()

        manager.remove_entity(entities[0].id)

        assert not manager.is_entity_enabled(entities[0].id)

    def test_removing_a_disabled_entity_clears_its_flag(self) -> None:
        """Otherwise the id stays parked, and an entity created later with
        the same explicit id would be born disabled."""
        manager, entities = world_with()
        manager.set_entity_enabled(entities[0].id, False)
        reused = entities[0].id

        manager.remove_entity(reused)
        manager.flush_pending_removals()
        revived = manager.create_entity(reused)
        revived.add_component(Alpha())

        assert manager.is_entity_enabled(reused)
        assert ids_with(manager, Alpha) >= {reused}


class TestCachedQueriesSeeParkedEntities:
    """The cache mirrors the component index; dormancy is applied when a
    query is iterated. Building the cache with disabled entities filtered
    out strands them -- the cache is maintained by component add and
    remove, and parking an entity is neither."""

    def test_a_query_registered_after_the_entities_exist_still_finds_them(
        self,
    ) -> None:
        """The defect this pins. A pool builds its entities up front, so a
        system registering its cached query afterwards -- which is the
        normal order -- saw an empty cache forever, and the pooled
        entities never moved again once acquired.
        """
        manager, entities = world_with()
        for entity in entities:
            manager.set_entity_enabled(entity.id, False)

        manager.register_cached_query(Alpha, Beta)
        manager.set_entity_enabled(entities[0].id, True)

        found = {entity.id for entity in manager.get_entities_with_cached(Alpha, Beta)}
        assert found == {entities[0].id}

    def test_the_cache_still_tracks_components_added_later(self) -> None:
        manager, entities = world_with()
        manager.register_cached_query(Alpha, Beta)

        late = manager.create_entity()
        late.add_component(Alpha())
        late.add_component(Beta())

        found = {entity.id for entity in manager.get_entities_with_cached(Alpha, Beta)}
        assert late.id in found


class TestPoolParksItsEntities:
    def test_a_fresh_pool_matches_no_queries(self) -> None:
        """A factory may attach everything an entity will ever need --
        that is the obvious way to write one, and before dormancy it made
        every idle entity cost every system every tick."""
        manager = EntityManager()

        EntityPool(manager, "test", 5, _factory)

        assert ids_with(manager, Alpha) == set()

    def test_acquiring_brings_an_entity_into_queries(self) -> None:
        manager = EntityManager()
        pool = EntityPool(manager, "test", 5, _factory)

        entity = pool.acquire()

        assert entity is not None
        assert ids_with(manager, Alpha) == {entity.id}

    def test_releasing_takes_it_back_out(self) -> None:
        manager = EntityManager()
        pool = EntityPool(manager, "test", 5, _factory)
        entity = pool.acquire()
        assert entity is not None

        pool.release(entity)

        assert ids_with(manager, Alpha) == set()

    def test_a_released_entity_keeps_its_state(self) -> None:
        """What the hand-rolled workaround could not do: detaching a
        component to hide it destroys whatever it held."""
        manager = EntityManager()
        pool = EntityPool(manager, "test", 5, _factory)
        entity = pool.acquire()
        assert entity is not None
        entity.get_component(Alpha).value = 42

        pool.release(entity)
        reacquired = pool.acquire()

        assert reacquired is entity
        assert reacquired.get_component(Alpha).value == 42

    def test_cost_follows_the_active_count_not_the_pool_size(self) -> None:
        """The property the whole change exists for."""
        manager = EntityManager()
        pool = EntityPool(manager, "test", 200, _factory)

        for _ in range(3):
            pool.acquire()

        assert len(list(manager.get_entities_with(Alpha))) == 3


def _factory(manager: EntityManager, index: int):
    """Build one pooled entity carrying everything it will ever need."""
    entity = manager.create_entity()
    entity.add_component(Poolable())
    entity.add_component(Alpha(value=index))
    entity.add_component(Beta(value=index))
    return entity
