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

Both complexity guards run against the **Python** store, which is what
`build_hash`'s `accelerate=False` default is for: they are about the
Python index's own asymptotics, and pointing them at whichever store a
contributor happens to have built would make them measure something
different on two machines. The native store has its own guards further
down, and the sweeps report both.
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

QUERY_RADIUS = 80.0

STORES = [
    pytest.param(False, id="python"),
    pytest.param(True, id="native"),
]


def _hash(count: int, *, spread: float, accelerate: bool) -> SpatialHash[int]:
    """`build_hash`, skipping the native store when it is not built."""
    if accelerate and not SpatialHash[int]().accelerated:
        pytest.skip("native extension not built; `cargo build --release`")
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
    consumers then query once per entity, so a tick is `count` inserts
    into an index that already holds those keys, plus `count` queries.
    Both halves are timed because they do not win equally -- the inserts
    are 4.9x and the queries 20.5x -- and timing only the queries would
    quote a number no consumer ever sees. Together: 17x.

    The scatter is deliberately *outside* the timed region. Generating
    positions is identical Python work in both branches, so including it
    would dilute the ratio and make this guard less able to do its one
    job, which is to notice the native path has stopped being taken at
    all. A loader that finds no library falls back to Python exactly as
    designed and every parity test *skips*, so this is one of the few
    places a silently absent extension fails. Asserted at 4x against a
    measured 17x for that reason.
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
def test_alternating_writes_and_queries_stays_within_its_known_penalty() -> None:
    """The one regime where the native store is asymptotically worse.

    The native grid rebuilds on the first query after any write, which is
    free when a caller fills the whole index and then sweeps it -- one
    rebuild for `count` queries, which is what every consumer in the
    engine does. A caller that alternates instead pays one rebuild per
    query: O(n^2) against Python's O(n).

    Measured: 1.9x *faster* at 250 keys, 0.52x at 1000, 0.13x at 4000. So
    this is not a guard against a regression, it is a guard on a cost that
    is already there and must not grow -- and the number in the docstring
    of `SpatialHash` has to keep matching it. If someone makes the rebuild
    incremental, this test should start failing in the good direction and
    both docstrings want rewriting.
    """
    count = 4000
    spread = uniform_spread_for(count)
    keys = list(range(count))
    points = _sample_points(spread, count)
    _hash(1, spread=spread, accelerate=True)

    def alternate(accelerate: bool) -> None:
        index = SpatialHash[int](accelerate=accelerate)
        for key, point in zip(keys, points, strict=True):
            index.insert(key, point)
            index.query_radius(point, QUERY_RADIUS)

    python_time = measure(lambda: alternate(False), rounds=3)
    native_time = measure(lambda: alternate(True), rounds=3)

    assert native_time < python_time * 15.0, (
        f"alternating insert and query cost the native store "
        f"{native_time * 1e3:.1f}ms against Python's "
        f"{python_time * 1e3:.1f}ms -- {native_time / python_time:.1f}x "
        "worse, where 7.5x is the known cost of rebuilding the grid once "
        "per query. Something has made the rebuild more expensive."
    )


@pytest.mark.performance
def test_the_native_advantage_does_not_wash_out_with_density() -> None:
    """The ratio is supposed to be flat in `k`, and that is the whole case.

    ADR 0004 originally ruled this port out because the crossing scales
    with how many candidates a query returns. It does -- but so does the
    Python broad-phase, at about twenty times the cost per candidate, so
    the ratio barely moves. Measured 20.5x at k=17 and 22.6x at k=32, and
    16.6x in the degenerate case where every key is everyone's neighbour.

    This is the test that would catch the original objection turning out
    to be right after all: if the crossing ever starts to dominate, the
    ratio at high density collapses while the low-density one above stays
    green.
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
    if accelerate and not SpatialHash[int]().accelerated:
        pytest.skip("native extension not built; `cargo build --release`")
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
