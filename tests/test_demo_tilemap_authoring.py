"""The Tiled map module 6 ships, and the contract between it and the game.

`games/tilemap_authoring/assets/cerrado_cave.tmx` is meant to be opened in
Tiled and edited. These tests are what makes that safe: they pin the three
custom properties the scene reads, so a re-save that drops them fails here
rather than showing up as a level with no walls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from games.tilemap_authoring.scenes import (  # noqa: E402
    MAP_PATH,
    TERRAIN_LAYER,
    TILE_COLORS,
)
from pyguara.tilemap import EMPTY_GID, load_tmx  # noqa: E402


@pytest.fixture(scope="module")
def tilemap():
    return load_tmx(MAP_PATH)


def _tiles(tilemap):
    """Every non-empty (cell, gid) in the terrain layer."""
    layer = tilemap.layers[TERRAIN_LAYER]
    return [
        ((x, y), layer.get_tile((x, y)))
        for y in range(layer.height)
        for x in range(layer.width)
        if layer.get_tile((x, y)) != EMPTY_GID
    ]


def test_the_checked_in_map_loads():
    assert MAP_PATH.exists()
    assert load_tmx(MAP_PATH).tile_size == 32


def test_it_has_the_layer_the_scene_reads_by_name(tilemap):
    """Named, not indexed: a map with a second decorative layer should not
    shift what the game reads."""
    assert TERRAIN_LAYER in tilemap.layers


def test_the_map_fills_the_window_the_module_opens(tilemap):
    layer = tilemap.layers[TERRAIN_LAYER]

    assert layer.width * tilemap.tile_size == 800
    assert layer.height * tilemap.tile_size == 576


def test_every_tile_carries_a_kind(tilemap):
    """`kind` is what the scene maps to a colour, and what a game with a
    tileset image would map to a source rect."""
    for cell, gid in _tiles(tilemap):
        assert tilemap.properties_for(gid).get("kind"), (
            f"tile at {cell} (gid {gid}) has no 'kind' property"
        )


def test_every_drawable_kind_has_a_colour(tilemap):
    """A kind with no colour is skipped at render time, so a typo'd kind
    would quietly vanish from the level."""
    drawn = {
        str(tilemap.properties_for(gid)["kind"])
        for _, gid in _tiles(tilemap)
        if tilemap.properties_for(gid).get("solid")
    }

    assert drawn <= set(TILE_COLORS)


def test_solid_tiles_exist_and_hollow_ones_do_too(tilemap):
    """A map where everything is solid, or nothing is, would pass every
    other test here and be unplayable."""
    solid = [
        gid for _, gid in _tiles(tilemap) if tilemap.properties_for(gid).get("solid")
    ]
    hollow = [
        gid
        for _, gid in _tiles(tilemap)
        if not tilemap.properties_for(gid).get("solid")
    ]

    assert solid
    assert hollow


def test_the_spawn_marker_is_present_and_not_solid(tilemap):
    """A solid spawn tile would wall the player into the geometry."""
    markers = [
        cell
        for cell, gid in _tiles(tilemap)
        if tilemap.properties_for(gid).get("spawn")
    ]

    assert len(markers) == 1
    gid = tilemap.layers[TERRAIN_LAYER].get_tile(markers[0])
    assert not tilemap.properties_for(gid).get("solid")


def test_hazard_tiles_carry_a_damage_value(tilemap):
    hazards = [
        gid for _, gid in _tiles(tilemap) if tilemap.properties_for(gid).get("damage")
    ]

    assert hazards
    assert all(
        isinstance(tilemap.properties_for(gid)["damage"], int) for gid in hazards
    )


def test_collision_merging_is_doing_real_work(tilemap):
    """The lesson of the module: a per-tile collider is the obvious first
    implementation and how a tile game ends up with a physics step it
    cannot afford."""
    solid_tiles = sum(
        1 for _, gid in _tiles(tilemap) if tilemap.properties_for(gid).get("solid")
    )
    rects = tilemap.collision_rects(TERRAIN_LAYER)

    assert solid_tiles > 100
    assert len(rects) < solid_tiles / 10


def test_the_merged_rects_cover_exactly_the_solid_area(tilemap):
    """Merging that lost a tile would be a hole in the floor."""
    size = tilemap.tile_size
    solid_tiles = sum(
        1 for _, gid in _tiles(tilemap) if tilemap.properties_for(gid).get("solid")
    )

    covered = sum(
        rect.width * rect.height for rect in tilemap.collision_rects(TERRAIN_LAYER)
    )

    assert covered == solid_tiles * size * size


def test_the_scene_builds_one_static_body_per_merged_rect():
    """End to end: the map's geometry really does reach the physics world."""
    from games.tilemap_authoring.scenes import TilemapScene
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.physics.components import RigidBody

    app = create_headless_application()
    try:
        scene = TilemapScene(app._container.get(EventDispatcher))
        scene.resolve_dependencies(app._container)
        scene.on_enter()

        assert scene.tilemap is not None
        expected = len(scene.tilemap.collision_rects(TERRAIN_LAYER))
        bodies = list(scene.entity_manager.get_entities_with(RigidBody))

        # The terrain bodies, plus the one dynamic body dropped into them.
        assert len(bodies) == expected + 1
        scene.on_exit()
    finally:
        app.shutdown()


def test_the_player_spawns_at_the_marker():
    from games.tilemap_authoring.scenes import TilemapScene
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.events.dispatcher import EventDispatcher

    app = create_headless_application()
    try:
        scene = TilemapScene(app._container.get(EventDispatcher))
        scene.resolve_dependencies(app._container)
        scene.on_enter()

        assert scene.tilemap is not None
        assert scene._player is not None
        marker = next(iter(scene._cells_with(scene.tilemap, "spawn")))
        size = scene.tilemap.tile_size
        position = scene._player.transform.position

        assert position.x == pytest.approx(marker[0] * size + size / 2)
        assert position.y == pytest.approx(marker[1] * size + size / 2)
        scene.on_exit()
    finally:
        app.shutdown()
