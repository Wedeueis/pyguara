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


def test_get_active_is_in_acquisition_order() -> None:
    """The documented order, which `games/` iterates every frame.

    Pinned because the active set is a dict keyed on entity id: dicts
    preserve insertion order, but nothing about "keyed on id" makes that
    obvious to a reader, and a switch to any unordered structure would
    break callers silently rather than loudly.
    """
    pool = EntityPool(EntityManager(), "test", size=4, factory=_factory)

    acquired = [pool.acquire() for _ in range(4)]

    assert pool.get_active() == acquired


def test_get_active_keeps_its_order_after_a_release_in_the_middle() -> None:
    pool = EntityPool(EntityManager(), "test", size=4, factory=_factory)
    acquired = [pool.acquire() for _ in range(4)]
    middle = acquired[1]
    assert middle is not None

    pool.release(middle)

    assert pool.get_active() == [acquired[0], acquired[2], acquired[3]]


def test_entities_can_be_released_in_any_order() -> None:
    """Release cost and correctness are both order-independent.

    Before the active set became a dict, `release()` did two linear scans
    from index 0, so releasing newest-first cost 70x what oldest-first did
    at a pool of 3000. Correctness never depended on order; performance
    entirely did. This pins the correctness half -- the cost half is
    `tests/performance/test_perf_ecs.py`.
    """
    pool = EntityPool(EntityManager(), "test", size=5, factory=_factory)
    acquired = [pool.acquire() for _ in range(5)]

    for entity in (acquired[3], acquired[0], acquired[4], acquired[1], acquired[2]):
        assert entity is not None
        pool.release(entity)

    assert pool.active_count == 0
    assert pool.available_count == 5
    assert pool.get_active() == []


def test_releasing_another_pools_entity_is_a_noop_even_when_ids_collide() -> None:
    """Two pools sharing a manager can hold entities with the same id.

    `EntityManager.create_entity` does not reject a duplicate id, and a
    factory that names entities positionally -- `pooled_0`, `pooled_1`,
    as this file's own `_factory` does -- gives every pool over the same
    manager an identically-named set. So an id alone cannot identify which
    pool an entity belongs to, which is why `release()` compares the
    stored object rather than trusting the key.
    """
    manager = EntityManager()
    pool_a = EntityPool(manager, "a", size=1, factory=_factory)
    pool_b = EntityPool(manager, "b", size=1, factory=_factory)

    mine = pool_a.acquire()
    theirs = pool_b.acquire()
    assert mine is not None and theirs is not None
    assert mine.id == theirs.id, "the collision this test exists for"

    pool_a.release(theirs)

    # B's entity stayed put, and A did not take it.
    assert pool_b.active_count == 1
    assert pool_a.active_count == 1
    assert pool_a.available_count == 0
    assert theirs.get_component(Poolable).is_active is True
