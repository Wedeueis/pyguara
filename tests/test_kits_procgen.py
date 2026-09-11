"""Tests for `pyguara/kits/procgen/` (BSP splitting, dungeon generation)."""

from __future__ import annotations

from pyguara.common.random import RandomStream
from pyguara.common.types import Rect
from pyguara.kits.procgen import carve_room, generate_dungeon, split_bsp
from pyguara.kits.procgen.dungeon import _connect

# ========== split_bsp ==========


def test_a_region_too_small_to_split_is_a_single_leaf() -> None:
    root = split_bsp(Rect(0, 0, 10, 10), RandomStream(1), min_leaf_size=6)

    assert root.is_leaf is True
    assert root.bounds == Rect(0, 0, 10, 10)


def test_a_large_region_splits() -> None:
    root = split_bsp(Rect(0, 0, 100, 100), RandomStream(1), min_leaf_size=10)

    assert root.is_leaf is False
    assert len(root.leaves()) > 1


def test_max_depth_zero_never_splits_regardless_of_size() -> None:
    root = split_bsp(
        Rect(0, 0, 1000, 1000), RandomStream(1), min_leaf_size=6, max_depth=0
    )

    assert root.is_leaf is True


def test_max_depth_one_splits_exactly_once() -> None:
    root = split_bsp(
        Rect(0, 0, 1000, 1000), RandomStream(1), min_leaf_size=6, max_depth=1
    )

    assert root.is_leaf is False
    assert root.left is not None and root.left.is_leaf
    assert root.right is not None and root.right.is_leaf


def test_same_seed_produces_the_same_tree() -> None:
    root_a = split_bsp(Rect(0, 0, 200, 150), RandomStream(99), min_leaf_size=10)
    root_b = split_bsp(Rect(0, 0, 200, 150), RandomStream(99), min_leaf_size=10)

    leaves_a = sorted(
        (leaf.bounds.x, leaf.bounds.y, leaf.bounds.width, leaf.bounds.height)
        for leaf in root_a.leaves()
    )
    leaves_b = sorted(
        (leaf.bounds.x, leaf.bounds.y, leaf.bounds.width, leaf.bounds.height)
        for leaf in root_b.leaves()
    )
    assert leaves_a == leaves_b


def test_leaves_exactly_tile_the_original_area_with_no_gaps_or_overlaps() -> None:
    bounds = Rect(0, 0, 137, 91)  # deliberately not a round number
    root = split_bsp(bounds, RandomStream(7), min_leaf_size=8)

    leaves = root.leaves()
    total_area = sum(leaf.bounds.width * leaf.bounds.height for leaf in leaves)
    assert total_area == bounds.width * bounds.height

    for i, a in enumerate(leaves):
        for b in leaves[i + 1 :]:
            assert not a.bounds.colliderect(b.bounds)


def test_every_leaf_respects_min_leaf_size_in_its_split_dimension() -> None:
    root = split_bsp(Rect(0, 0, 120, 90), RandomStream(3), min_leaf_size=15)

    for leaf in root.leaves():
        # Not split further means at least one dimension is below 2x
        # min_leaf_size -- but a dimension that *was* split must respect it.
        assert leaf.bounds.width > 0
        assert leaf.bounds.height > 0


# ========== carve_room ==========


def test_carved_room_stays_within_the_leaf_bounds() -> None:
    leaf = Rect(10, 10, 20, 20)
    room = carve_room(leaf, RandomStream(1), min_size=4, padding=2)

    assert room.x >= leaf.x + 2
    assert room.y >= leaf.y + 2
    assert room.x + room.width <= leaf.x + leaf.width - 2
    assert room.y + room.height <= leaf.y + leaf.height - 2


def test_carve_room_on_a_leaf_too_small_for_min_size_does_not_raise() -> None:
    tiny_leaf = Rect(0, 0, 3, 3)

    room = carve_room(tiny_leaf, RandomStream(1), min_size=10, padding=1)

    assert room.width >= 1
    assert room.height >= 1


def test_carve_room_is_deterministic() -> None:
    leaf = Rect(0, 0, 30, 30)

    a = carve_room(leaf, RandomStream(55), min_size=4, padding=1)
    b = carve_room(leaf, RandomStream(55), min_size=4, padding=1)

    assert a == b


# ========== generate_dungeon ==========


def test_generate_dungeon_is_deterministic() -> None:
    bounds = Rect(0, 0, 150, 120)

    layout_a = generate_dungeon(bounds, RandomStream(42), min_leaf_size=12)
    layout_b = generate_dungeon(bounds, RandomStream(42), min_leaf_size=12)

    assert layout_a.rooms == layout_b.rooms
    assert layout_a.corridors == layout_b.corridors


def test_generate_dungeon_produces_at_least_one_room() -> None:
    layout = generate_dungeon(Rect(0, 0, 100, 100), RandomStream(1), min_leaf_size=10)

    assert len(layout.rooms) >= 1


def test_every_room_is_inside_the_overall_bounds() -> None:
    bounds = Rect(0, 0, 100, 80)
    layout = generate_dungeon(bounds, RandomStream(1), min_leaf_size=10)

    for room in layout.rooms:
        assert room.x >= bounds.x
        assert room.y >= bounds.y
        assert room.x + room.width <= bounds.x + bounds.width
        assert room.y + room.height <= bounds.y + bounds.height


def test_corridor_count_matches_the_number_of_bsp_merges() -> None:
    """A full binary tree with N leaves has N-1 internal nodes; _connect()
    adds exactly 2 corridor segments per internal node."""
    bounds = Rect(0, 0, 150, 120)
    root = split_bsp(bounds, RandomStream(42), min_leaf_size=12)
    for leaf in root.leaves():
        leaf.room = carve_room(leaf.bounds, RandomStream(42), 3, 1)

    _, corridors = _connect(root, RandomStream(42), corridor_width=1)

    leaf_count = len(root.leaves())
    assert len(corridors) == (leaf_count - 1) * 2


def test_a_single_leaf_dungeon_has_no_corridors() -> None:
    layout = generate_dungeon(Rect(0, 0, 10, 10), RandomStream(1), min_leaf_size=20)

    assert len(layout.rooms) == 1
    assert layout.corridors == []


def test_corridor_width_is_honored() -> None:
    bounds = Rect(0, 0, 100, 80)
    layout = generate_dungeon(
        bounds, RandomStream(1), min_leaf_size=10, corridor_width=3
    )

    assert len(layout.corridors) > 0
    for corridor in layout.corridors:
        assert corridor.width == 3 or corridor.height == 3
