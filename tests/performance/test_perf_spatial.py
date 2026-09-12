"""`SpatialHash` throughput: rebuild cost and query cost.

Two properties are worth pinning, and they are different in kind.

The **rebuild** is linear in key count, and `FlockingSystem` does a full
one every tick rather than maintaining the hash incrementally. That choice
is defended in its docstring on correctness grounds (an incremental hash
can accumulate a stale entry for a despawned entity), and the measurement
backs it up: the rebuild is a small fraction of a flocking tick. This
guard exists so that stays true.

A **query** is supposed to be flat in key count -- that is the entire
point of a spatial index. If the per-query cost starts climbing with the
number of keys in the hash, the index has stopped indexing, and the guard
below is what notices.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Vector2
from tests.performance.conftest import (
    assert_scales_no_worse_than,
    build_hash,
    measure,
    uniform_spread_for,
)

QUERY_RADIUS = 80.0


def _query_all(index, points: list[Vector2]) -> None:
    """Run one radius query per point, consuming each result."""
    for point in points:
        # The result is consumed rather than discarded lazily: if this ever
        # becomes a generator, timing an unconsumed one would measure
        # nothing at all.
        list(index.query_radius(point, QUERY_RADIUS))


def _sample_points(spread: float, count: int) -> list[Vector2]:
    """Evenly spaced query points across the populated area."""
    step = spread / count
    return [Vector2(i * step, i * step) for i in range(count)]


@pytest.mark.performance
def test_rebuild_is_linear_in_key_count() -> None:
    """Inserting 4x the keys should cost about 4x, not 16x."""
    small_n, large_n = 500, 2000
    small_spread = uniform_spread_for(small_n)
    large_spread = uniform_spread_for(large_n)

    small = measure(lambda: build_hash(small_n, spread=small_spread))
    large = measure(lambda: build_hash(large_n, spread=large_spread))

    assert_scales_no_worse_than(
        small=small,
        large=large,
        factor=4,
        limit=8.0,
        what="SpatialHash rebuild",
    )


@pytest.mark.performance
def test_query_cost_is_flat_in_key_count() -> None:
    """A query at constant density should not care how big the hash is.

    Density is held constant so that each query returns roughly the same
    number of candidates; all that changes is how many keys the hash holds
    in total. A spatial index that is doing its job is indifferent to that.
    """
    queries = 400
    small_n, large_n = 500, 2000
    small_spread = uniform_spread_for(small_n)
    large_spread = uniform_spread_for(large_n)

    small_index = build_hash(small_n, spread=small_spread)
    large_index = build_hash(large_n, spread=large_spread)
    small_points = _sample_points(small_spread, queries)
    large_points = _sample_points(large_spread, queries)

    small = measure(lambda: _query_all(small_index, small_points))
    large = measure(lambda: _query_all(large_index, large_points))

    assert_scales_no_worse_than(
        small=small,
        large=large,
        factor=1,
        limit=2.0,
        what="SpatialHash.query_radius per-query cost across hash sizes",
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [1000, 3000, 10000])
def test_sweep_rebuild(benchmark, count: int) -> None:
    """Report the cost of building a hash of `count` keys."""
    spread = uniform_spread_for(count)
    benchmark.pedantic(lambda: build_hash(count, spread=spread), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [1000, 3000, 10000])
def test_sweep_query_radius(benchmark, count: int) -> None:
    """Report the cost of `count` radius queries against a hash of `count`."""
    spread = uniform_spread_for(count)
    index = build_hash(count, spread=spread)
    points = _sample_points(spread, count)
    benchmark.pedantic(lambda: _query_all(index, points), rounds=3, iterations=1)
