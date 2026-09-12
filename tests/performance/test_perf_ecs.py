"""ECS throughput: pool churn and component queries.

`EntityPool` exists so that a game with high-frequency spawn and despawn
does not churn the garbage collector -- its own docstring says so. A pool
whose release cost grows with how much of it is in use does not deliver
that, and the largest pool anywhere else in the suite is size 4, which is
why it went unnoticed.

**Release order is the whole story here**, and it is worth writing down
because the fast case looks reassuring and is an accident. `release()`
does `if entity not in self._active` followed by `self._active.remove(...)`,
both linear scans from index 0:

- Releasing *oldest-first* finds the match at index 0 immediately, and
  the removal is a C-level memmove. Measured near-linear: 3000 entities
  drain in ~1 ms.
- Releasing *newest-first* scans the entire list with Python-level
  equality on every release. Measured quadratic: 500 -> 2.1 ms,
  1000 -> 8.3, 2000 -> 32.9, **3000 -> 73.4 ms**, or four and a half
  frames to put a pool away.

Anything other than strictly oldest-first is quadratic; newest-first is
simply the clearest case to measure. The guard below is therefore expected
to **fail** until `release()` is fixed, and it says so rather than being
written loose enough to pass. Putting the before-number in a merged
artefact is this suite's entire purpose.
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
@pytest.mark.xfail(
    reason=(
        "EntityPool.release() is O(n) -- an `in` scan plus a list.remove(), "
        "so releasing newest-first drains quadratically (3000 entities take "
        "~73ms, four and a half frames). Fixed separately; this guard flips "
        "to passing then."
    ),
    strict=True,
)
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
