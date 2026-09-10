"""Tests for `pyguara/tilemap/` (Tileset, TileLayer, Tilemap)."""

from __future__ import annotations

import pytest

from pyguara.common.types import Rect
from pyguara.tilemap import EMPTY_GID, TileLayer, Tilemap, Tileset

# ========== Tileset ==========


def test_tileset_contains_its_own_gid_range() -> None:
    tileset = Tileset(name="ground", first_gid=1, tile_count=10)

    assert tileset.contains(1) is True
    assert tileset.contains(10) is True
    assert tileset.contains(11) is False
    assert tileset.contains(0) is False


def test_tileset_properties_for_resolves_local_id() -> None:
    tileset = Tileset(
        name="ground", first_gid=5, tile_count=3, properties={0: {"solid": True}}
    )

    # gid 5 is local id 0 within this tileset.
    assert tileset.properties_for(5) == {"solid": True}


def test_tileset_properties_for_unlisted_tile_is_empty() -> None:
    tileset = Tileset(name="ground", first_gid=1, tile_count=10)

    assert tileset.properties_for(3) == {}


# ========== TileLayer ==========


def test_new_layer_is_all_empty() -> None:
    layer = TileLayer(width=3, height=2)

    assert layer.get_tile((0, 0)) == EMPTY_GID
    assert layer.get_tile((2, 1)) == EMPTY_GID


def test_layer_seeded_with_tiles_matches_input() -> None:
    layer = TileLayer(width=2, height=2, tiles=[[1, 2], [3, 4]])

    assert layer.get_tile((0, 0)) == 1
    assert layer.get_tile((1, 0)) == 2
    assert layer.get_tile((0, 1)) == 3
    assert layer.get_tile((1, 1)) == 4


def test_layer_rejects_mismatched_tile_dimensions() -> None:
    with pytest.raises(ValueError):
        TileLayer(width=2, height=2, tiles=[[1, 2]])


def test_layer_deep_copies_seed_data() -> None:
    """Mutating a layer must never mutate the caller's original list."""
    original = [[1, 2], [3, 4]]
    layer = TileLayer(width=2, height=2, tiles=original)

    layer.set_tile((0, 0), 99)

    assert original[0][0] == 1


def test_set_tile_updates_get_tile() -> None:
    layer = TileLayer(width=2, height=2)

    layer.set_tile((1, 1), 7)

    assert layer.get_tile((1, 1)) == 7


def test_collision_rects_merges_solid_tiles() -> None:
    layer = TileLayer(width=2, height=1, tiles=[[1, 1]])

    rects = layer.collision_rects(lambda gid: {"solid": True}, tile_size=16)

    assert rects == [Rect(0, 0, 32, 16)]


def test_collision_rects_ignores_non_solid_tiles() -> None:
    layer = TileLayer(width=2, height=1, tiles=[[1, 1]])

    rects = layer.collision_rects(lambda gid: {"solid": False}, tile_size=16)

    assert rects == []


def test_collision_rects_cache_is_invalidated_by_set_tile() -> None:
    calls = []

    def properties_for(gid: int) -> dict:
        calls.append(gid)
        return {"solid": gid != EMPTY_GID}

    layer = TileLayer(width=1, height=1, tiles=[[1]])
    layer.collision_rects(properties_for, tile_size=16)
    first_call_count = len(calls)

    # Same tiles, second call should hit the cache -- no new property lookups.
    layer.collision_rects(properties_for, tile_size=16)
    assert len(calls) == first_call_count

    layer.set_tile((0, 0), EMPTY_GID)
    rects = layer.collision_rects(properties_for, tile_size=16)
    assert rects == []
    assert len(calls) > first_call_count


# ========== Tilemap ==========


def test_tilemap_properties_for_resolves_via_owning_tileset() -> None:
    tilemap = Tilemap(
        tile_size=16,
        tilesets=[
            Tileset(name="a", first_gid=1, tile_count=5, properties={0: {"x": 1}}),
            Tileset(name="b", first_gid=6, tile_count=5, properties={0: {"x": 2}}),
        ],
    )

    assert tilemap.properties_for(1) == {"x": 1}
    assert tilemap.properties_for(6) == {"x": 2}


def test_tilemap_properties_for_unowned_gid_is_empty() -> None:
    tilemap = Tilemap(tile_size=16)

    assert tilemap.properties_for(EMPTY_GID) == {}
    assert tilemap.properties_for(999) == {}


def test_tilemap_collision_rects_delegates_to_named_layer() -> None:
    tilemap = Tilemap(
        tile_size=16,
        tilesets=[
            Tileset(
                name="a", first_gid=1, tile_count=1, properties={0: {"solid": True}}
            )
        ],
    )
    tilemap.add_layer("ground", TileLayer(width=2, height=1, tiles=[[1, 1]]))

    assert tilemap.collision_rects("ground") == [Rect(0, 0, 32, 16)]


def test_tilemap_collision_rects_raises_for_unknown_layer() -> None:
    tilemap = Tilemap(tile_size=16)

    with pytest.raises(KeyError):
        tilemap.collision_rects("nope")


def test_overlapping_tileset_ranges_prefer_the_last_one_added() -> None:
    tilemap = Tilemap(
        tile_size=16,
        tilesets=[
            Tileset(
                name="first", first_gid=1, tile_count=10, properties={0: {"x": "old"}}
            ),
            Tileset(
                name="second", first_gid=1, tile_count=10, properties={0: {"x": "new"}}
            ),
        ],
    )

    assert tilemap.properties_for(1) == {"x": "new"}
