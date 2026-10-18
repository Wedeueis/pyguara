"""Tests for `SpatialHash` (pyguara/common/spatial.py).

Every test runs against **both stores**. That is not thoroughness for its
own sake: `SpatialHash` grew a native implementation behind the same
methods, and an unparametrised file would have gone on passing while
testing only whichever store the contributor running it happened to have
built. The Python store is always exercised; the native one skips when
the extension is absent, which `test_the_stores_are_both_reached` makes
visible rather than silent.

The behavioural parity suite is `tests/test_native_spatial_hash_parity.py`
-- this file is the unit suite, and it earns its keep by stating what each
operation means rather than only that the two agree on it.
"""

from __future__ import annotations

import pytest

from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Rect, Vector2
from pyguara.native import native_module

_STORES = [
    pytest.param(False, id="python"),
    pytest.param(
        True,
        id="native",
        marks=pytest.mark.skipif(
            native_module() is None,
            reason="native extension not built; `cargo build --release`",
        ),
    ),
]


@pytest.fixture(params=_STORES)
def accelerate(request: pytest.FixtureRequest) -> bool:
    """Which store the test under it builds."""
    return bool(request.param)


def test_the_stores_are_both_reached(accelerate: bool) -> None:
    """The fixture builds the store it says it does.

    Guards the guard. Every other test in this file would pass against one
    store twice, so this is what notices if `accelerate` stops being
    honoured.
    """
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)

    assert grid.accelerated is accelerate


def test_query_radius_finds_keys_within_range(accelerate: bool) -> None:
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)
    grid.insert("near", Vector2(10, 10))
    grid.insert("far", Vector2(1000, 1000))

    result = grid.query_radius(Vector2(0, 0), radius=50.0)

    assert result == ["near"]


def test_query_radius_excludes_keys_in_range_cell_but_outside_exact_radius(
    accelerate: bool,
) -> None:
    """Candidate cells are a superset of the exact answer -- confirms the
    exact-distance check actually filters, not just the cell lookup."""
    grid = SpatialHash[str](cell_size=64.0, accelerate=accelerate)
    # Same cell as the origin, but outside a tight radius.
    grid.insert("corner", Vector2(60, 60))

    result = grid.query_radius(Vector2(0, 0), radius=10.0)

    assert result == []


def test_query_point_finds_only_keys_sharing_the_cell(accelerate: bool) -> None:
    grid = SpatialHash[str](cell_size=10.0, accelerate=accelerate)
    grid.insert("same_cell", Vector2(1, 1))
    grid.insert("other_cell", Vector2(50, 50))

    result = grid.query_point(Vector2(2, 2))

    assert result == ["same_cell"]


def test_query_rect_finds_keys_inside_bounds(accelerate: bool) -> None:
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)
    grid.insert("inside", Vector2(5, 5))
    grid.insert("outside", Vector2(500, 500))

    result = grid.query_rect(Rect(0, 0, 20, 20))

    assert result == ["inside"]


def test_reinserting_at_a_new_position_moves_the_key(accelerate: bool) -> None:
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)
    grid.insert("key", Vector2(0, 0))

    grid.insert("key", Vector2(1000, 1000))

    assert grid.query_radius(Vector2(0, 0), radius=10.0) == []
    assert grid.query_radius(Vector2(1000, 1000), radius=10.0) == ["key"]


def test_reinserting_within_the_same_cell_does_not_duplicate_the_key(
    accelerate: bool,
) -> None:
    grid = SpatialHash[str](cell_size=64.0, accelerate=accelerate)
    grid.insert("key", Vector2(0, 0))

    grid.insert("key", Vector2(1, 1))

    assert grid.query_radius(Vector2(0, 0), radius=10.0) == ["key"]


def test_remove_drops_the_key_from_future_queries(accelerate: bool) -> None:
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)
    grid.insert("key", Vector2(0, 0))

    grid.remove("key")

    assert grid.query_radius(Vector2(0, 0), radius=100.0) == []


def test_remove_of_untracked_key_is_a_noop(accelerate: bool) -> None:
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)

    grid.remove("never inserted")  # must not raise


def test_query_respects_mask_filter(accelerate: bool) -> None:
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)
    grid.insert("enemy", Vector2(0, 0), mask=0b01)
    grid.insert("pickup", Vector2(1, 1), mask=0b10)

    enemies_only = grid.query_radius(Vector2(0, 0), radius=10.0, mask=0b01)

    assert enemies_only == ["enemy"]


def test_a_removed_key_frees_its_slot_for_the_next_insert(accelerate: bool) -> None:
    """A native slot is recycled; a Python key simply vanishes.

    Both stores have to behave the same from the outside, which is the
    only thing a caller can see. The native store is where this could go
    wrong: it parks a removed slot rather than compacting the arrays, so
    this is what notices if a recycled slot comes back carrying its old
    position or mask.
    """
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)
    grid.insert("first", Vector2(0, 0), mask=0b01)
    grid.remove("first")

    grid.insert("second", Vector2(0, 0), mask=0b10)

    assert grid.query_radius(Vector2(0, 0), radius=10.0, mask=0b10) == ["second"]
    assert grid.query_radius(Vector2(0, 0), radius=10.0, mask=0b01) == []


def test_a_key_reinserted_with_a_new_mask_is_filtered_by_the_new_one(
    accelerate: bool,
) -> None:
    """Re-inserting is the documented way to move a key, and it carries
    the mask with it -- so the old mask must not survive."""
    grid = SpatialHash[str](cell_size=16.0, accelerate=accelerate)
    grid.insert("key", Vector2(0, 0), mask=0b01)

    grid.insert("key", Vector2(0, 0), mask=0b10)

    assert grid.query_radius(Vector2(0, 0), radius=10.0, mask=0b01) == []
    assert grid.query_radius(Vector2(0, 0), radius=10.0, mask=0b10) == ["key"]


def test_the_index_can_be_mutated_from_inside_a_loop_over_a_query(
    accelerate: bool,
) -> None:
    """A query result is a materialised list, not a live view.

    This is the engine's actual pattern and it is native-only hazardous:
    `ProjectileSystem` iterates `query_radius` and applies damage, which
    dispatches an event, which can destroy an entity, which brings
    `SpatialIndexSystem._on_entity_destroyed` round to `remove()` -- all
    while the `for` loop is still running. The native methods take
    `&mut self`, so if a query ever handed back something lazy the
    re-entry would raise `RuntimeError: Already borrowed` instead of
    working.

    Pinned rather than assumed, because the natural optimisation -- return
    an iterator, skip building the list -- would break it, and nothing
    else in the suite would notice.
    """
    grid = SpatialHash[str](cell_size=64.0, accelerate=accelerate)
    for index in range(8):
        grid.insert(f"key-{index}", Vector2(float(index), 0.0))

    seen = []
    for key in grid.query_radius(Vector2(0.0, 0.0), 100.0):
        seen.append(key)
        grid.remove(key)
        grid.insert(f"replacement-{key}", Vector2(100.0, 100.0))

    assert sorted(seen) == sorted(f"key-{index}" for index in range(8))
    assert grid.query_radius(Vector2(0.0, 0.0), 100.0) == []
    assert len(grid.query_radius(Vector2(100.0, 100.0), 1.0)) == 8
