"""ECS throughput: pool churn and component queries.

`EntityPool` exists so that a game with high-frequency spawn and despawn
does not churn the garbage collector -- its own docstring says so. A pool
whose release cost grows with how much of it is in use does not deliver
that, and the largest pool anywhere else in the suite is size 4, which is
why it went unnoticed.

**Release order used to be the whole story here**, and the guard below is
what holds the fix in place. When the active set was a list, `release()`
did an `in` scan followed by a `list.remove()` -- two linear scans from
index 0 -- so cost depended entirely on the order entities came back:

- *Oldest-first* found its match at index 0 and removed it with a C-level
  memmove. Near-linear, and reassuring, and an accident.
- *Newest-first* scanned the whole list every time. Quadratic:
  500 -> 2.1 ms, 1000 -> 8.3, 2000 -> 32.9, **3000 -> 73.4 ms**, four and
  a half frames to put a pool away.

The active set is now a dict keyed on entity id, so release is O(1) in
any order. `test_pool_churn_is_linear` measures the worst of the old
orders precisely because it was the one that fell over; keep it that way,
or a regression back to a list would pass unnoticed.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import EntityPool, Poolable
from tests.performance.conftest import assert_scales_no_worse_than, measure


def _make_entity(manager: EntityManager, index: int):
    """Pool factory: `EntityPool` requires the factory to attach `Poolable`."""
    entity = manager.create_entity(f"pooled_{index}")
    entity.add_component(Transform(position=Vector2.zero()))
    entity.add_component(Poolable())
    return entity


def _build_pool(size: int) -> EntityPool:
    """Build a pool of `size` entities.

    Deliberately called outside every timed region: constructing 2000
    entities costs far more than churning them, and timing the two
    together hides the thing being measured.
    """
    return EntityPool(EntityManager(), "bench", size, _make_entity)


def _drain_newest_first(pool: EntityPool) -> None:
    """Acquire the whole pool, then release it newest-first.

    The worst case for a list-backed active set -- see the module
    docstring for why, and for what the fast case looks like.
    """
    taken = [pool.acquire() for _ in range(pool.available_count)]
    for entity in reversed(taken):
        if entity is not None:
            pool.release(entity)


@pytest.mark.performance
def test_pool_churn_is_linear() -> None:
    """Filling and draining 4x the pool should cost about 4x."""
    small_pool = _build_pool(500)
    large_pool = _build_pool(2000)

    small = measure(lambda: _drain_newest_first(small_pool))
    large = measure(lambda: _drain_newest_first(large_pool))

    assert_scales_no_worse_than(
        small=small,
        large=large,
        factor=4,
        limit=8.0,
        what="EntityPool acquire + release (newest-first)",
    )


@pytest.mark.performance
def test_cached_queries_are_no_slower_than_uncached() -> None:
    """`get_entities_with_cached` should never lose to the uncached form.

    It is registered but used by no core system, which makes it an
    untested claim. This is the floor that claim has to clear.
    """
    manager = EntityManager()
    for _ in range(2000):
        entity = manager.create_entity()
        entity.add_component(Transform(position=Vector2.zero()))
        entity.add_component(Poolable())

    manager.register_cached_query(Transform, Poolable)
    # Warm the cache, so this measures steady-state reads rather than the
    # first build.
    list(manager.get_entities_with_cached(Transform, Poolable))

    uncached = measure(lambda: list(manager.get_entities_with(Transform, Poolable)))
    cached = measure(
        lambda: list(manager.get_entities_with_cached(Transform, Poolable))
    )

    assert cached <= uncached * 1.5, (
        f"cached query ({cached * 1e3:.2f}ms) lost to uncached "
        f"({uncached * 1e3:.2f}ms) over 2000 entities"
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("size", [500, 1000, 2000, 3000])
def test_sweep_pool_drain_newest_first(benchmark, size: int) -> None:
    """Report drain cost by pool size, worst-case order."""
    pool = _build_pool(size)
    benchmark.pedantic(lambda: _drain_newest_first(pool), rounds=3, iterations=1)
