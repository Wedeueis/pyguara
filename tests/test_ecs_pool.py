"""Tests for `pyguara/ecs/pool.py` (EntityPool/Poolable)."""

from __future__ import annotations

import pytest

from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import EntityPool, Poolable


def _factory(em: EntityManager, index: int) -> Entity:
    entity = em.create_entity(f"pooled_{index}")
    entity.add_component(Poolable())
    return entity


def test_preallocates_every_entity_as_inactive() -> None:
    manager = EntityManager()
    pool = EntityPool(manager, "test", size=3, factory=_factory)

    assert pool.available_count == 3
    assert pool.active_count == 0
    for entity in manager.get_entities_with(Poolable):
        assert entity.get_component(Poolable).is_active is False
        assert entity.get_component(Poolable).pool_name == "test"


def test_acquire_marks_the_entity_active() -> None:
    manager = EntityManager()
    pool = EntityPool(manager, "test", size=2, factory=_factory)

    entity = pool.acquire()

    assert entity is not None
    assert entity.get_component(Poolable).is_active is True
    assert pool.active_count == 1
    assert pool.available_count == 1
    assert pool.get_active() == [entity]


def test_acquire_on_an_exhausted_pool_returns_none() -> None:
    manager = EntityManager()
    pool = EntityPool(manager, "test", size=1, factory=_factory)

    pool.acquire()

    assert pool.acquire() is None


def test_release_returns_the_entity_to_the_pool() -> None:
    manager = EntityManager()
    pool = EntityPool(manager, "test", size=1, factory=_factory)
    entity = pool.acquire()
    assert entity is not None

    pool.release(entity)

    assert entity.get_component(Poolable).is_active is False
    assert pool.active_count == 0
    assert pool.available_count == 1


def test_releasing_an_already_idle_entity_is_a_noop() -> None:
    """A double-release must not duplicate the entity in the available list."""
    manager = EntityManager()
    pool = EntityPool(manager, "test", size=1, factory=_factory)
    entity = pool.acquire()
    assert entity is not None

    pool.release(entity)
    pool.release(entity)  # second release: must not double-add

    assert pool.available_count == 1


def test_a_released_entity_can_be_reacquired() -> None:
    manager = EntityManager()
    pool = EntityPool(manager, "test", size=1, factory=_factory)
    first = pool.acquire()
    assert first is not None
    pool.release(first)

    second = pool.acquire()

    assert second is first


def test_factory_receives_a_0_based_index_per_entity() -> None:
    manager = EntityManager()
    seen_indices = []

    def factory(em: EntityManager, index: int) -> Entity:
        seen_indices.append(index)
        entity = em.create_entity(f"pooled_{index}")
        entity.add_component(Poolable())
        return entity

    EntityPool(manager, "test", size=4, factory=factory)

    assert seen_indices == [0, 1, 2, 3]


def test_a_factory_that_forgets_poolable_raises() -> None:
    def bad_factory(em: EntityManager, index: int) -> Entity:
        return em.create_entity(f"bad_{index}")  # no Poolable attached

    with pytest.raises(KeyError):
        EntityPool(EntityManager(), "test", size=1, factory=bad_factory)
