"""A tilemap's tiles are `tile_width` by `tile_height` pixels."""

from __future__ import annotations

import pytest

from pyguara.common.types import Rect
from pyguara.tilemap import Tilemap
from pyguara.tilemap.layer import TileLayer
from pyguara.tilemap.tileset import Tileset


def _map(tile_size: int | tuple[int, int]) -> Tilemap:
    tileset = Tileset(
        name="t", first_gid=1, tile_count=1, properties={0: {"solid": True}}
    )
    tilemap = Tilemap(tile_size=tile_size, tilesets=[tileset])
    layer = TileLayer(2, 1)
    layer.set_tile((1, 0), 1)
    tilemap.add_layer("ground", layer)
    return tilemap


def test_a_single_number_is_a_square_tile() -> None:
    tilemap = _map(16)

    assert (tilemap.tile_width, tilemap.tile_height) == (16, 16)
    assert tilemap.tile_size == 16


def test_a_pair_is_width_then_height() -> None:
    tilemap = _map((32, 16))

    assert (tilemap.tile_width, tilemap.tile_height) == (32, 16)
    assert tilemap.collision_rects("ground") == [Rect(32, 0, 32, 16)]


def test_tile_size_of_a_rectangular_map_raises_rather_than_guess() -> None:
    with pytest.raises(ValueError, match="tile_width"):
        _ = _map((32, 16)).tile_size


@pytest.mark.parametrize("size", [0, -8, (16, 0), (16,), (16, 8, 4), 2.5, True])
def test_a_size_that_is_not_positive_whole_pixels_is_refused(size: object) -> None:
    with pytest.raises(ValueError, match="tile size"):
        Tilemap(tile_size=size)  # type: ignore[arg-type]


def test_a_layers_collision_follows_the_size_it_is_asked_with() -> None:
    tileset = Tileset(
        name="t", first_gid=1, tile_count=1, properties={0: {"solid": True}}
    )
    small, large = Tilemap(8, [tileset]), Tilemap((16, 32), [tileset])
    layer = TileLayer(1, 1)
    layer.set_tile((0, 0), 1)
    small.add_layer("g", layer)
    large.add_layer("g", layer)

    assert small.collision_rects("g") == [Rect(0, 0, 8, 8)]
    assert large.collision_rects("g") == [Rect(0, 0, 16, 32)]
