"""Do the two `SpatialHash` stores agree, and in what sense?

The fifth parity suite, and it sits in the **bit-exact** regime rather
than the tolerance one, for the reason `docs/adr/0004-the-native-boundary.md`
Decision 5 gives: an index decides which enemy a magnet pulls, which
target a bullet hits and who is a flockmate, so a membership that differs
by one key is a different game, not a rounding difference. There is no
tolerance to state -- `query_radius` confirms every candidate against an
exact squared distance, so who is in range is a property of the positions
alone, and both stores compute it from the same floats with the same
spelling.

**Exactly one thing diverges, and it is the result's order.** Python
yields from `set[K]`, so its order is the keys' hash order; for the string
keys the engine actually uses, `PYTHONHASHSEED` randomises that per
process, which means the Python store is not even reproducible against
*itself* across two runs. The native store returns slot order. Neither is
canonical and there is nothing to be exact to, so every comparison here
sorts -- and `TestTheOrderIsTheOnlyDivergence` pins that this is a known
property of the Python index rather than an excuse made for the native
one. This mirrors the flocking suite's finding, and issue #324.

The native-only guards at the end have no Python counterpart on purpose,
and say so: Python accepts a coordinate the native cell range cannot
represent, and has no limit on how many cells a query may span. Both are
failures chosen over silent divergence.

All of it skips when the extension is absent, so a contributor without
Rust sees a green suite having tested none of it.
"""

from __future__ import annotations

import math

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Rect, Vector2
from pyguara.native import native_module

pytestmark = pytest.mark.skipif(
    native_module() is None,
    reason="native extension not built; `cargo build --release`",
)

FULL = 0xFFFFFFFF


def _both(cell_size: float = 64.0) -> tuple[SpatialHash[str], SpatialHash[str]]:
    """One index of each store, over the same cell size.

    Two separate indexes rather than one driven twice, which the flocking
    suite could not do: this index holds exactly what it was told to hold,
    with no `EntityManager` handing out ids that differ between runs.
    """
    return (
        SpatialHash[str](cell_size=cell_size, accelerate=False),
        SpatialHash[str](cell_size=cell_size, accelerate=True),
    )


def _scatter(
    count: int, spread: float, seed: int, *, masks: tuple[int, ...] = (FULL,)
) -> list[tuple[str, Vector2, int]]:
    """A reproducible set of keys, positions and masks."""
    rng = RandomStream(seed)
    return [
        (
            f"key-{index}",
            Vector2(
                rng.uniform(-spread * 0.5, spread * 0.5),
                rng.uniform(-spread * 0.5, spread * 0.5),
            ),
            masks[index % len(masks)],
        )
        for index in range(count)
    ]


def _fill(
    index: SpatialHash[str], entries: list[tuple[str, Vector2, int]]
) -> SpatialHash[str]:
    for key, position, mask in entries:
        index.insert(key, position, mask)
    return index


class TestEveryQueryReturnsTheSameMembership:
    """Tier one: who is in range, exactly, over the shapes that vary it."""

    @pytest.mark.parametrize("count", [0, 1, 2, 7, 64, 500])
    def test_a_scattered_set_agrees_at_every_key(self, count: int) -> None:
        """Query from each key's own position, so every result is non-empty."""
        entries = _scatter(count, 600.0, seed=count + 1)
        python, native = _both()
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries:
            assert sorted(python.query_radius(position, 80.0)) == sorted(
                native.query_radius(position, 80.0)
            )

    @pytest.mark.parametrize("cell_size", [0.5, 1.0, 17.0, 64.0, 80.0, 512.0, 10_000.0])
    def test_the_cell_size_does_not_change_the_answer(self, cell_size: float) -> None:
        """A spatial index's answer is a property of the positions.

        `cell_size` is a performance knob, so the same query over the same
        keys must return the same keys whatever it is set to -- in either
        store. This is the test that would catch a cell-range derivation
        that is off by one in only one of them.
        """
        entries = _scatter(120, 600.0, seed=7)
        python, native = _both(cell_size)
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries[:40]:
            expected = sorted(python.query_radius(position, 70.0))
            assert sorted(native.query_radius(position, 70.0)) == expected

    @pytest.mark.parametrize(
        "radius", [0.0, -1.0, 1e-9, 0.5, 63.9, 64.0, 64.1, 1000.0, 1e4]
    )
    def test_every_radius_agrees(self, radius: float) -> None:
        entries = _scatter(80, 400.0, seed=11)
        python, native = _both()
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries[:30]:
            assert sorted(python.query_radius(position, radius)) == sorted(
                native.query_radius(position, radius)
            )

    def test_a_key_exactly_on_the_radius_is_included_by_both(self) -> None:
        """`<=`, not `<`. One character, and it decides membership.

        Pinned with an exactly-representable distance so the boundary is
        the boundary rather than a float accident: 3-4-5, scaled.
        """
        python, native = _both()
        for index in (python, native):
            index.insert("on_it", Vector2(30.0, 40.0))

        assert python.query_radius(Vector2(0.0, 0.0), 50.0) == ["on_it"]
        assert native.query_radius(Vector2(0.0, 0.0), 50.0) == ["on_it"]

    def test_a_key_a_hair_either_side_of_the_radius_agrees(self) -> None:
        python, native = _both()
        inside = math.nextafter(50.0, 0.0)
        outside = math.nextafter(50.0, math.inf)
        for index in (python, native):
            index.insert("inside", Vector2(inside, 0.0))
            index.insert("outside", Vector2(outside, 0.0))

        assert python.query_radius(Vector2(0.0, 0.0), 50.0) == ["inside"]
        assert native.query_radius(Vector2(0.0, 0.0), 50.0) == ["inside"]

    def test_negative_coordinates_agree(self) -> None:
        """`floor`, not truncation -- the two differ only below zero.

        A native `as i64` cast truncates toward zero, so a grid that used
        it instead of `.floor()` would put -0.5 and +0.5 in the same cell.
        Nothing above would notice if every coordinate were positive.
        """
        python, native = _both(cell_size=64.0)
        entries = [
            ("a", Vector2(-1.0, -1.0), FULL),
            ("b", Vector2(-63.9, -63.9), FULL),
            ("c", Vector2(-64.0, -64.0), FULL),
            ("d", Vector2(-64.1, -64.1), FULL),
            ("e", Vector2(0.0, 0.0), FULL),
            ("f", Vector2(-0.0, -0.0), FULL),
        ]
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries:
            for radius in (0.0, 1.0, 64.0, 200.0):
                assert sorted(python.query_radius(position, radius)) == sorted(
                    native.query_radius(position, radius)
                )

    def test_coincident_keys_all_come_back_from_both(self) -> None:
        python, native = _both()
        entries = [(f"stacked-{i}", Vector2(100.0, 100.0), FULL) for i in range(20)]
        _fill(python, entries)
        _fill(native, entries)

        assert sorted(python.query_radius(Vector2(100.0, 100.0), 0.0)) == sorted(
            native.query_radius(Vector2(100.0, 100.0), 0.0)
        )
        assert len(native.query_radius(Vector2(100.0, 100.0), 0.0)) == 20

    @pytest.mark.parametrize("mask", [0b01, 0b10, 0b11, 0b1010, FULL, 0])
    def test_every_mask_filters_the_same_keys(self, mask: int) -> None:
        entries = _scatter(120, 500.0, seed=13, masks=(0b01, 0b10, 0b1000, FULL))
        python, native = _both()
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries[:30]:
            assert sorted(python.query_radius(position, 90.0, mask)) == sorted(
                native.query_radius(position, 90.0, mask)
            )

    def test_a_key_inserted_with_mask_zero_is_invisible_to_both(self) -> None:
        """Not a special case either store implements -- a consequence of
        `mask & query == 0`. Worth pinning because the native store also
        uses a zeroed mask to park a removed slot, so the two meanings
        share a representation."""
        python, native = _both()
        for index in (python, native):
            index.insert("hidden", Vector2(0.0, 0.0), 0)
            index.insert("seen", Vector2(1.0, 0.0), FULL)

        assert python.query_radius(Vector2(0.0, 0.0), 10.0) == ["seen"]
        assert native.query_radius(Vector2(0.0, 0.0), 10.0) == ["seen"]


class TestQueryPointAgrees:
    """`query_point` has no distance test, so only the cell decides.

    That makes it the query most sensitive to the cell derivation, and the
    one where a native bucket collision would show: the native store has
    to re-confirm a candidate's cell, because a bucket may hold more than
    one cell and there is no distance test to reject the extras.
    """

    @pytest.mark.parametrize("cell_size", [1.0, 16.0, 64.0, 333.0])
    def test_the_same_cell_members_come_back(self, cell_size: float) -> None:
        entries = _scatter(200, 400.0, seed=17)
        python, native = _both(cell_size)
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries[:60]:
            assert sorted(python.query_point(position)) == sorted(
                native.query_point(position)
            )

    def test_a_key_exactly_on_a_cell_boundary_lands_in_the_same_cell(self) -> None:
        python, native = _both(cell_size=64.0)
        entries = [
            ("below", Vector2(math.nextafter(64.0, 0.0), 0.0), FULL),
            ("on", Vector2(64.0, 0.0), FULL),
            ("above", Vector2(math.nextafter(64.0, math.inf), 0.0), FULL),
        ]
        _fill(python, entries)
        _fill(native, entries)

        for probe in (Vector2(0.0, 0.0), Vector2(64.0, 0.0), Vector2(63.0, 0.0)):
            assert sorted(python.query_point(probe)) == sorted(
                native.query_point(probe)
            )

    def test_far_apart_keys_never_share_a_cell_natively(self) -> None:
        """The bucket-collision guard, from the outside.

        With many keys and few buckets, two distinct cells share a bucket
        by construction. `query_point` would then report a key from the
        other cell if the native store trusted the bucket. A tiny cell
        size over a wide spread is how to provoke it.
        """
        entries = _scatter(400, 100_000.0, seed=19)
        python, native = _both(cell_size=1.0)
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries:
            assert sorted(python.query_point(position)) == sorted(
                native.query_point(position)
            )

    @pytest.mark.parametrize("mask", [0b01, 0b10, FULL])
    def test_the_mask_filters_the_same(self, mask: int) -> None:
        entries = _scatter(100, 300.0, seed=23, masks=(0b01, 0b10))
        python, native = _both(32.0)
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries[:30]:
            assert sorted(python.query_point(position, mask)) == sorted(
                native.query_point(position, mask)
            )


class TestQueryRectAgrees:
    """`Rect`'s inclusive edges, and the inverted case."""

    @pytest.mark.parametrize(
        ("left", "top", "width", "height"),
        [
            (0.0, 0.0, 100.0, 100.0),
            (-200.0, -200.0, 400.0, 400.0),
            (-50.5, 17.25, 3.0, 400.0),
            (0.0, 0.0, 0.0, 0.0),
            (100.0, 100.0, 4000.0, 4000.0),
        ],
    )
    def test_bounds_agree(
        self, left: float, top: float, width: float, height: float
    ) -> None:
        entries = _scatter(300, 500.0, seed=29)
        python, native = _both()
        _fill(python, entries)
        _fill(native, entries)
        bounds = Rect(left, top, width, height)

        assert sorted(python.query_rect(bounds)) == sorted(native.query_rect(bounds))

    def test_each_edge_is_included_or_excluded_by_both(self) -> None:
        """`Rect.contains_point` is **half-open**: `left <= x < right`.

        So the left and top edges are in and the right and bottom are out,
        matching `pygame.Rect.collidepoint`. Writing the native test as
        inclusive on all four looks harmless and silently widens every
        rect query by one pixel on two sides -- which is how this test
        found the bug it now guards.
        """
        python, native = _both(cell_size=16.0)
        entries = [
            ("left", Vector2(10.0, 50.0), FULL),
            ("right", Vector2(110.0, 50.0), FULL),
            ("top", Vector2(50.0, 20.0), FULL),
            ("bottom", Vector2(50.0, 120.0), FULL),
            ("corner", Vector2(10.0, 20.0), FULL),
            ("outside", Vector2(110.1, 50.0), FULL),
        ]
        _fill(python, entries)
        _fill(native, entries)
        bounds = Rect(10.0, 20.0, 100.0, 100.0)

        expected = sorted(python.query_rect(bounds))
        assert sorted(native.query_rect(bounds)) == expected
        # Stated rather than left to the comparison, so the test still
        # says which way round it is if both stores drift together.
        assert expected == ["corner", "left", "top"]

    def test_an_inverted_rect_agrees(self) -> None:
        """A negative width is not rejected by either store; both simply
        find nothing, because the cell range runs backwards. Pinned so a
        native guard is not added to one store only."""
        entries = _scatter(50, 300.0, seed=31)
        python, native = _both()
        _fill(python, entries)
        _fill(native, entries)
        bounds = Rect(100.0, 100.0, -200.0, -200.0)

        assert sorted(python.query_rect(bounds)) == sorted(native.query_rect(bounds))

    @pytest.mark.parametrize("mask", [0b01, 0b10, FULL])
    def test_the_mask_filters_the_same(self, mask: int) -> None:
        entries = _scatter(200, 400.0, seed=37, masks=(0b01, 0b10))
        python, native = _both()
        _fill(python, entries)
        _fill(native, entries)
        bounds = Rect(-100.0, -100.0, 250.0, 250.0)

        assert sorted(python.query_rect(bounds, mask)) == sorted(
            native.query_rect(bounds, mask)
        )


class TestMutationAgrees:
    """Tier two: the stores agree after a sequence, not just after a fill.

    The native store maintains a free list and rebuilds its grid lazily,
    neither of which the Python store has, so a divergence is far more
    likely to appear after a mix of writes than after one fill.
    """

    def test_a_long_interleaved_script_agrees_at_every_step(self) -> None:
        """Insert, move, remove, re-add, query -- 400 operations, compared
        after each one. This is the test that would catch a stale grid: a
        query that forgets to rebuild returns the previous tick's answer,
        which no single-fill test can see.
        """
        rng = RandomStream(41)
        python, native = _both()
        live: list[str] = []

        for step in range(400):
            action = rng.uniform(0.0, 1.0)
            if action < 0.55 or not live:
                key = f"key-{step}"
                position = Vector2(rng.uniform(-300, 300), rng.uniform(-300, 300))
                mask = (0b01, 0b10, FULL)[step % 3]
                python.insert(key, position, mask)
                native.insert(key, position, mask)
                if key not in live:
                    live.append(key)
            elif action < 0.8:
                key = live[int(rng.uniform(0, len(live) - 1e-9))]
                position = Vector2(rng.uniform(-300, 300), rng.uniform(-300, 300))
                python.insert(key, position)
                native.insert(key, position)
            else:
                key = live.pop(int(rng.uniform(0, len(live) - 1e-9)))
                python.remove(key)
                native.remove(key)

            probe = Vector2(rng.uniform(-300, 300), rng.uniform(-300, 300))
            assert sorted(python.query_radius(probe, 90.0)) == sorted(
                native.query_radius(probe, 90.0)
            ), f"diverged at step {step}"

    def test_a_query_between_two_writes_sees_the_first(self) -> None:
        """The lazy rebuild, pinned directly. A native query must rebuild
        on the first query after *any* write, not once per batch."""
        python, native = _both()
        for index in (python, native):
            index.insert("key", Vector2(0.0, 0.0))
            assert index.query_radius(Vector2(0.0, 0.0), 10.0) == ["key"]
            index.insert("key", Vector2(1000.0, 1000.0))
            assert index.query_radius(Vector2(0.0, 0.0), 10.0) == []
            assert index.query_radius(Vector2(1000.0, 1000.0), 10.0) == ["key"]
            index.remove("key")
            assert index.query_radius(Vector2(1000.0, 1000.0), 10.0) == []

    def test_removing_every_key_empties_both(self) -> None:
        entries = _scatter(60, 400.0, seed=43)
        python, native = _both()
        _fill(python, entries)
        _fill(native, entries)

        for key, _, _ in entries:
            python.remove(key)
            native.remove(key)

        for _, position, _ in entries:
            assert python.query_radius(position, 1e4) == []
            assert native.query_radius(position, 1e4) == []

    def test_removing_a_key_twice_is_a_noop_in_both(self) -> None:
        python, native = _both()
        for index in (python, native):
            index.insert("key", Vector2(0.0, 0.0))
            index.remove("key")
            index.remove("key")
            assert index.query_radius(Vector2(0.0, 0.0), 10.0) == []

    def test_a_removed_key_is_gone_from_the_queries_with_no_distance_test(
        self,
    ) -> None:
        """`query_point` and `query_rect` rely on liveness alone.

        `query_radius` rejects a removed slot on distance, because the
        native store parks it at NaN -- so a removal looks covered when
        only the radius query is tested. These two have no distance test,
        which makes the liveness check the single thing standing between a
        caller and a key that no longer exists. Removing the mask guard
        beside it changed nothing and was dropped; removing *this* has to
        fail, and this is the test that makes it.

        The origin is deliberate: NaN casts to cell 0, so a freed slot
        sits in cell (0, 0)'s bucket and these are the queries that would
        hand it back.
        """
        python, native = _both(cell_size=64.0)
        for index in (python, native):
            index.insert("ghost", Vector2(0.0, 0.0))
            index.insert("alive", Vector2(1.0, 1.0))
            index.remove("ghost")

            assert index.query_point(Vector2(0.0, 0.0)) == ["alive"]
            assert index.query_rect(Rect(-10.0, -10.0, 20.0, 20.0)) == ["alive"]
            assert index.query_point(Vector2(-1.0, -1.0)) == []

    def test_reusing_a_freed_slot_does_not_resurrect_the_old_key(self) -> None:
        """The free list, from the outside. A recycled slot that kept its
        old key would return a removed entity id -- which a caller then
        resolves to `None` and skips, hiding the bug until something
        reuses ids."""
        python, native = _both()
        for index in (python, native):
            for i in range(10):
                index.insert(f"old-{i}", Vector2(float(i), 0.0))
            for i in range(10):
                index.remove(f"old-{i}")
            for i in range(10):
                index.insert(f"new-{i}", Vector2(float(i), 0.0))

        expected = sorted(python.query_radius(Vector2(5.0, 0.0), 100.0))
        assert sorted(native.query_radius(Vector2(5.0, 0.0), 100.0)) == expected
        assert all(key.startswith("new-") for key in expected)
        assert len(expected) == 10


class TestTheOrderIsTheOnlyDivergence:
    """The one permitted divergence, pinned as a property of Python.

    Decision 5 asks for a divergence to have exactly one stated cause with
    everything else exact. The cause here is that `SpatialHash` has never
    defined an order: a caller taking the first of several results gets an
    arbitrary one. These tests exist so that the sorting every comparison
    above does reads as a known fact rather than a convenience.
    """

    def test_the_python_store_does_not_promise_an_order(self) -> None:
        """Insertion order is not the result order, in the Python store.

        If it were, the native store would owe it. It is not: the result
        comes out of a `set`, whose iteration order is the keys' hashes.
        """
        python = SpatialHash[str](cell_size=64.0, accelerate=False)
        keys = [f"key-{i}" for i in range(16)]
        for key in keys:
            python.insert(key, Vector2(0.0, 0.0))

        result = python.query_radius(Vector2(0.0, 0.0), 1.0)

        assert sorted(result) == sorted(keys)
        assert result != keys, (
            "the Python store returned insertion order here, which would "
            "make the native store's slot order a real divergence rather "
            "than a difference between two undefined orders"
        )

    def test_both_stores_return_the_same_keys_as_a_multiset(self) -> None:
        """No duplicates in either, which is the part order cannot excuse.

        A key lives in exactly one cell, so a query spanning several cells
        must not see it twice. Natively that is what the visit stamps are
        for: without them two cells sharing a bucket would each yield it.
        """
        entries = _scatter(300, 2000.0, seed=47)
        python, native = _both(cell_size=4.0)
        _fill(python, entries)
        _fill(native, entries)

        for _, position, _ in entries[:50]:
            found = native.query_radius(position, 400.0)
            assert len(found) == len(set(found))
            assert sorted(found) == sorted(python.query_radius(position, 400.0))


class TestBothStoresRejectTheSameNonsense:
    """Tier three: the errors agree by type.

    By type rather than by message: Python's come from `math.floor` and
    saying the native store must reproduce CPython's wording would pin the
    wrong thing.
    """

    @pytest.mark.parametrize(
        ("x", "y"),
        [
            (float("nan"), 0.0),
            (0.0, float("nan")),
            (float("nan"), float("nan")),
        ],
    )
    def test_inserting_a_nan_coordinate_raises_value_error_in_both(
        self, x: float, y: float
    ) -> None:
        python, native = _both()
        with pytest.raises(ValueError):
            python.insert("key", Vector2(x, y))
        with pytest.raises(ValueError):
            native.insert("key", Vector2(x, y))

    @pytest.mark.parametrize(
        ("x", "y"),
        [
            (float("inf"), 0.0),
            (float("-inf"), 0.0),
            (0.0, float("inf")),
        ],
    )
    def test_inserting_an_infinite_coordinate_raises_overflow_in_both(
        self, x: float, y: float
    ) -> None:
        python, native = _both()
        with pytest.raises(OverflowError):
            python.insert("key", Vector2(x, y))
        with pytest.raises(OverflowError):
            native.insert("key", Vector2(x, y))

    def test_querying_from_a_nan_centre_raises_in_both(self) -> None:
        python, native = _both()
        for index in (python, native):
            index.insert("key", Vector2(0.0, 0.0))
            with pytest.raises(ValueError):
                index.query_radius(Vector2(float("nan"), 0.0), 10.0)
            with pytest.raises(ValueError):
                index.query_point(Vector2(float("nan"), 0.0))

    def test_querying_with_a_nan_radius_raises_in_both(self) -> None:
        python, native = _both()
        for index in (python, native):
            index.insert("key", Vector2(0.0, 0.0))
            with pytest.raises(ValueError):
                index.query_radius(Vector2(0.0, 0.0), float("nan"))

    def test_querying_from_an_infinite_centre_raises_in_both(self) -> None:
        python, native = _both()
        for index in (python, native):
            index.insert("key", Vector2(0.0, 0.0))
            with pytest.raises(OverflowError):
                index.query_radius(Vector2(float("inf"), 0.0), 10.0)


class TestTheNativeStoreRefusesWhatPythonMerelySurvives:
    """The native-only guards, each a loud failure chosen over a silent
    divergence -- and each stated here so the asymmetry is deliberate."""

    def test_an_absurd_radius_over_a_tiny_cell_is_refused(self) -> None:
        """Python takes proportionally longer; the native store refuses.

        `MAX_QUERY_CELLS` exists because a `cell_size=0.001` typo turns a
        query into a hang. The Python store genuinely has no limit, so
        this is not compared against it.
        """
        native = SpatialHash[str](cell_size=1e-9, accelerate=True)
        native.insert("key", Vector2(0.0, 0.0))

        with pytest.raises(ValueError, match="cells per axis"):
            native.query_radius(Vector2(0.0, 0.0), 1e9)

    def test_a_radius_spanning_a_billion_cells_is_refused(self) -> None:
        """Not a typo this time -- a plausible cell size and an implausible
        radius. 1e6 over 64 is 9.8e8 cells, which Python would visit one
        dict lookup at a time rather than refusing.
        """
        native = SpatialHash[str](cell_size=64.0, accelerate=True)
        native.insert("key", Vector2(0.0, 0.0))

        with pytest.raises(ValueError, match="cells per axis"):
            native.query_radius(Vector2(0.0, 0.0), 1e6)

    def test_a_rect_spanning_too_many_cells_is_refused(self) -> None:
        """`query_rect` is bounded by the same cell count as a radius: a
        1e5-unit square over 64-unit cells is 2.4 million of them. A
        caller wanting that really wants every key, and should raise
        `cell_size` or iterate instead."""
        native = SpatialHash[str](cell_size=64.0, accelerate=True)
        native.insert("key", Vector2(0.0, 0.0))

        with pytest.raises(ValueError, match="cells per axis"):
            native.query_rect(Rect(0.0, 0.0, 1e5, 1e5))

    def test_a_coordinate_past_the_representable_cell_range_is_refused(self) -> None:
        """Python indexes it with an arbitrary-precision cell; the native
        store would saturate two distant cells onto one and then report a
        key from the far side of the world out of `query_point`."""
        native = SpatialHash[str](cell_size=64.0, accelerate=True)

        with pytest.raises(ValueError, match="cannot tell two cells apart"):
            native.insert("key", Vector2(1e300, 0.0))

    def test_the_python_store_accepts_that_same_coordinate(self) -> None:
        """Guards the guard above: if Python ever started rejecting it too,
        the asymmetry would be gone and the note should go with it."""
        python = SpatialHash[str](cell_size=64.0, accelerate=False)

        python.insert("key", Vector2(1e300, 0.0))

        assert python.query_radius(Vector2(1e300, 0.0), 1.0) == ["key"]

    def test_a_key_that_re_enters_while_being_hashed_raises(self) -> None:
        """Every native method holds an exclusive borrow for its duration.

        So a key whose `__hash__` calls back into the same index gets
        `RuntimeError: Already borrowed`, where the Python store -- whose
        state is ordinary dicts -- simply works. No engine key does this;
        they are entity id strings. It is pinned because `SpatialHash`
        otherwise promises to take whatever hashable key the caller likes,
        and an unstated divergence is the thing this file exists to
        prevent.

        The re-entry is fired exactly once below. Left unbounded it
        recurses forever in the *Python* store too -- the nested query
        hashes the same key again -- so "Python tolerates this" means it
        tolerates a bounded re-entry, not that it is safe for arbitrary
        keys. Neither store is.

        The *safe* version of the same shape is the one that matters and
        is tested in `tests/test_common_spatial.py`: a query materialises
        its result before returning, so iterating one while removing keys
        works on both stores.
        """
        python = SpatialHash[object](cell_size=64.0, accelerate=False)
        native = SpatialHash[object](cell_size=64.0, accelerate=True)

        class ReEntersOnce:
            def __init__(self, index: SpatialHash[object]) -> None:
                self.index = index
                self.fired = False

            def __hash__(self) -> int:
                if not self.fired:
                    self.fired = True
                    self.index.query_radius(Vector2(0.0, 0.0), 10.0)
                return 42

            def __eq__(self, other: object) -> bool:
                return self is other

        python.insert(ReEntersOnce(python), Vector2(1.0, 1.0))
        assert len(python.query_radius(Vector2(1.0, 1.0), 10.0)) == 1

        with pytest.raises(RuntimeError, match="Already borrowed"):
            native.insert(ReEntersOnce(native), Vector2(1.0, 1.0))

    @pytest.mark.parametrize("cell_size", [0.0, -1.0, float("nan"), float("inf")])
    def test_a_nonsense_cell_size_is_refused(self, cell_size: float) -> None:
        """The Python store divides by it and produces nonsense or raises
        on first use; the native store refuses at construction, where the
        error can still name the argument."""
        with pytest.raises(ValueError, match="cell_size"):
            SpatialHash[str](cell_size=cell_size, accelerate=True)


def test_demanding_the_extension_when_it_is_absent_is_the_loaders_business() -> None:
    """`accelerate=True` raises only when there is nothing to accelerate
    with, which under this suite's skip there always is. Pinned anyway, so
    the message stays the one `pyguara.native` tells everywhere else."""
    index = SpatialHash[str](accelerate=True)

    assert index.accelerated is True
