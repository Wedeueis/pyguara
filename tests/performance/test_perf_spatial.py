"""`SpatialHash` throughput: rebuild cost and query cost.

The rebuild must stay linear in key count; `FlockingSystem` does a
full one every tick. A query must stay flat in key count, or the index
has stopped indexing.

Both complexity guards run against the shipped index, which is Rust
only. The comparisons further down use the Python reference from
`tests.reference.spatial` as their baseline.
"""

from __future__ import annotations

import pytest

from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from tests.performance.conftest import (
    assert_scales_no_worse_than,
    build_hash,
    measure,
    uniform_spread_for,
)
from tests.reference.spatial import ReferenceSpatialHash

QUERY_RADIUS = 80.0

STORES = [
    pytest.param(False, id="python"),
    pytest.param(True, id="native"),
]


def _hash(count: int, *, spread: float, accelerate: bool):
    """`build_hash`: the Rust index, or the Python reference for False."""
    return build_hash(count, spread=spread, accelerate=accelerate)


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
def test_the_native_store_is_wired_up_and_materially_faster() -> None:
    """One tick of the shape every consumer has: re-sync, then query.

    `SpatialIndexSystem` re-inserts every tracked entity each tick and the
    consumers query once per entity, so both halves are timed. Generating
    the positions is outside the timed region, since it is the same Python
    work on both stores.

    The bound is loose: its job is to notice that the native path stopped
    being taken, which nothing else fails on.
    """
    count = 1000
    spread = uniform_spread_for(count)
    points = _sample_points(spread, count)
    entries = [(key, point) for key, point in enumerate(points)]

    python = _hash(count, spread=spread, accelerate=False)
    native = _hash(count, spread=spread, accelerate=True)

    def tick(index: SpatialHash[int]) -> None:
        for key, point in entries:
            index.insert(key, point)
        _query_all(index, points)

    python_time = measure(lambda: tick(python))
    native_time = measure(lambda: tick(native))

    assert native_time < python_time * 0.25, (
        f"a native tick took {native_time * 1e3:.2f}ms against Python's "
        f"{python_time * 1e3:.2f}ms ({python_time / native_time:.1f}x). "
        "Expected around 17x."
    )


@pytest.mark.performance
def test_alternating_writes_and_queries_is_not_slower_natively() -> None:
    """The regime the native store used to lose, by a growing margin.

    The native grid is a snapshot. It used to be rebuilt on the first
    query after any write, which made a loop that alternates the two
    quadratic. A written slot is now checked directly until enough have
    piled up to be worth a rebuild.

    Asserted as "not slower than Python", loosely; the measured figure
    is in `docs/guides/performance.md`.
    """
    count = 4000
    spread = uniform_spread_for(count)
    keys = list(range(count))
    points = _sample_points(spread, count)
    _hash(1, spread=spread, accelerate=True)

    def alternate(accelerate: bool) -> None:
        index = (SpatialHash if accelerate else ReferenceSpatialHash)[int]()
        for key, point in zip(keys, points, strict=True):
            index.insert(key, point)
            index.query_radius(point, QUERY_RADIUS)

    python_time = measure(lambda: alternate(False), rounds=3)
    native_time = measure(lambda: alternate(True), rounds=3)

    assert native_time < python_time, (
        f"alternating insert and query cost the native store "
        f"{native_time * 1e3:.1f}ms against Python's "
        f"{python_time * 1e3:.1f}ms. A write between two queries should "
        f"cost a scan of the pending slots, not a rebuild of the grid."
    )


@pytest.mark.performance
def test_alternating_writes_and_queries_does_not_go_quadratic() -> None:
    """Four times the keys should cost about eight times, not sixteen.

    A query scans at most `sqrt(2n)` pending slots, so the loop is
    O(n sqrt n). A rebuild per query would be O(n^2).
    """
    _hash(1, spread=1.0, accelerate=True)

    def alternate(count: int) -> None:
        spread = uniform_spread_for(count)
        index = SpatialHash[int]()
        for key, point in enumerate(_sample_points(spread, count)):
            index.insert(key, point)
            index.query_radius(point, QUERY_RADIUS)

    small = measure(lambda: alternate(2000), rounds=3)
    large = measure(lambda: alternate(8000), rounds=3)

    assert large < small * 12.0, (
        f"4x the keys cost {large / small:.1f}x the time alternating writes "
        f"and queries; O(n sqrt n) predicts 8x and a rebuild per query 16x."
    )


@pytest.mark.performance
def test_the_native_advantage_does_not_wash_out_with_density() -> None:
    """The native advantage is about flat in `k`, candidates per query.

    The crossing scales with how many candidates a query returns, and so
    does the Python broad-phase, at a higher cost per candidate. If the
    crossing ever came to dominate, the ratio at high density would
    collapse while the low-density guard stayed green.
    """
    count = 1000
    spread = uniform_spread_for(count)
    points = _sample_points(spread, count)

    python = _hash(count, spread=spread, accelerate=False)
    native = _hash(count, spread=spread, accelerate=True)

    sparse = measure(lambda: _query_all(python, points)) / measure(
        lambda: _query_all(native, points)
    )

    def dense_query(index: SpatialHash[int]) -> None:
        for point in points:
            list(index.query_radius(point, QUERY_RADIUS * 4.0))

    dense = measure(lambda: dense_query(python)) / measure(lambda: dense_query(native))

    assert dense > sparse * 0.6, (
        f"the native advantage fell from {sparse:.1f}x at the default "
        f"radius to {dense:.1f}x at four times it. The crossing is "
        "supposed to scale with density no worse than the Python "
        "broad-phase it replaces."
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("accelerate", STORES)
@pytest.mark.parametrize("count", [1000, 3000, 10000])
def test_sweep_rebuild(benchmark, count: int, accelerate: bool) -> None:
    """Report the cost of building a hash of `count` keys."""
    spread = uniform_spread_for(count)
    benchmark.pedantic(
        lambda: build_hash(count, spread=spread, accelerate=accelerate),
        rounds=5,
        iterations=1,
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("accelerate", STORES)
@pytest.mark.parametrize("count", [1000, 3000, 10000])
def test_sweep_query_radius(benchmark, count: int, accelerate: bool) -> None:
    """Report the cost of `count` radius queries against a hash of `count`."""
    spread = uniform_spread_for(count)
    index = _hash(count, spread=spread, accelerate=accelerate)
    points = _sample_points(spread, count)
    benchmark.pedantic(lambda: _query_all(index, points), rounds=3, iterations=1)
