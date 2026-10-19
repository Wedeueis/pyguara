"""Tests for `pyguara/tilemap/ldtk_loader.py` (`load_ldtk`).

The fixture is built as a Python dict and dumped, not pasted as JSON: an
LDtk file is mostly editor bookkeeping, and a 200-line literal would
bury the half-dozen fields these tests actually depend on.

What is being checked throughout is the **translation**, since LDtk and
Tiled disagree about four things that matter -- a file is a world rather
than a map, tile ids are per-tileset rather than global, tile layers are
sparse rather than dense, and IntGrid layers have no tileset at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pyguara.tilemap import Tilemap, load_ldtk, load_ldtk_level


def _tileset_def(uid: int = 1, identifier: str = "Ground") -> dict[str, Any]:
    return {
        "uid": uid,
        "identifier": identifier,
        "tileGridSize": 16,
        "__cWid": 2,
        "__cHei": 2,
        "customData": [
            {"tileId": 0, "data": '{"solid": true, "damage": 3}'},
            {"tileId": 1, "data": "just a note"},
        ],
    }


def _tiles_layer(**overrides: Any) -> dict[str, Any]:
    layer = {
        "__identifier": "Ground",
        "__type": "Tiles",
        "__cWid": 2,
        "__cHei": 2,
        "__gridSize": 16,
        "__tilesetDefUid": 1,
        "gridTiles": [
            {"px": [0, 0], "t": 0},
            {"px": [16, 0], "t": 1},
            {"px": [16, 16], "t": 3},
        ],
    }
    layer.update(overrides)
    return layer


def _intgrid_layer(**overrides: Any) -> dict[str, Any]:
    layer = {
        "__identifier": "Collisions",
        "__type": "IntGrid",
        "__cWid": 2,
        "__cHei": 2,
        "__gridSize": 16,
        "intGridCsv": [1, 0, 2, 1],
    }
    layer.update(overrides)
    return layer


def _entities_layer(**overrides: Any) -> dict[str, Any]:
    layer = {
        "__identifier": "Entities",
        "__type": "Entities",
        "__cWid": 2,
        "__cHei": 2,
        "__gridSize": 16,
        "entityInstances": [
            {
                "__identifier": "Player",
                "px": [8, 24],
                "width": 16,
                "height": 16,
                "fieldInstances": [
                    {"__identifier": "hp", "__type": "Int", "__value": 10},
                    {"__identifier": "name", "__type": "String", "__value": "guara"},
                ],
            },
            {"__identifier": "Marker", "px": [32, 32], "width": 0, "height": 0},
        ],
    }
    layer.update(overrides)
    return layer


def _project(
    levels: list[dict[str, Any]] | None = None, **overrides: Any
) -> dict[str, Any]:
    project = {
        "jsonVersion": "1.5.3",
        "defaultGridSize": 16,
        "defs": {
            "tilesets": [_tileset_def()],
            "layers": [
                {
                    "identifier": "Collisions",
                    "type": "IntGrid",
                    "intGridValues": [
                        {"value": 1, "identifier": "Solid"},
                        {"value": 2, "identifier": "Water"},
                    ],
                }
            ],
        },
        "levels": levels
        if levels is not None
        else [
            {
                "identifier": "Level_0",
                "uid": 0,
                "layerInstances": [
                    _entities_layer(),
                    _tiles_layer(),
                    _intgrid_layer(),
                ],
            }
        ],
    }
    project.update(overrides)
    return project


def _write(tmp_path: Path, data: Any, name: str = "world.ldtk") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _grid(tilemap: Tilemap, layer_name: str) -> list[list[int]]:
    layer = tilemap.layers[layer_name]
    return [
        [layer.get_tile((x, y)) for x in range(layer.width)]
        for y in range(layer.height)
    ]


class TestAFileIsAWorld:
    """An LDtk project holds many levels; a Tiled file holds one map."""

    def test_each_level_becomes_its_own_tilemap(self, tmp_path: Path) -> None:
        project = _project(
            levels=[
                {"identifier": "Cave", "layerInstances": [_tiles_layer()]},
                {"identifier": "Surface", "layerInstances": [_tiles_layer()]},
            ]
        )

        maps = load_ldtk(_write(tmp_path, project))

        assert list(maps) == ["Cave", "Surface"]
        assert all(isinstance(m, Tilemap) for m in maps.values())

    def test_one_level_can_be_asked_for_by_name(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _project())

        tilemap = load_ldtk_level(path, "Level_0")

        assert tilemap.tile_size == 16

    def test_a_misspelled_level_name_lists_the_real_ones(self, tmp_path: Path) -> None:
        """A typo is the likeliest way to call this wrongly, and
        `KeyError: 'Levl_0'` on its own does not help."""
        path = _write(tmp_path, _project())

        with pytest.raises(KeyError, match="Level_0"):
            load_ldtk_level(path, "Levl_0")

    def test_multi_world_projects_are_flattened(self, tmp_path: Path) -> None:
        """LDtk moves levels under `worlds` once a project has more than
        one, which is a save option rather than exotica."""
        project = _project(
            levels=[],
            worlds=[
                {
                    "identifier": "Overworld",
                    "levels": [
                        {"identifier": "Field", "layerInstances": [_tiles_layer()]}
                    ],
                }
            ],
        )

        assert list(load_ldtk(_write(tmp_path, project))) == ["Field"]

    def test_a_level_saved_to_a_separate_file_is_followed(self, tmp_path: Path) -> None:
        """LDtk's "Save levels to separate files" option."""
        _write(
            tmp_path,
            {"identifier": "Cave", "layerInstances": [_tiles_layer()]},
            "Cave.ldtkl",
        )
        project = _project(
            levels=[{"identifier": "Cave", "externalRelPath": "Cave.ldtkl"}]
        )

        maps = load_ldtk(_write(tmp_path, project))

        assert _grid(maps["Cave"], "Ground")[0][0] == 1

    def test_a_missing_external_level_says_where_it_looked(
        self, tmp_path: Path
    ) -> None:
        project = _project(
            levels=[{"identifier": "Cave", "externalRelPath": "Cave.ldtkl"}]
        )

        with pytest.raises(ValueError, match="Cave.ldtkl"):
            load_ldtk(_write(tmp_path, project))

    def test_a_file_that_is_not_a_project_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not look like an LDtk project"):
            load_ldtk(_write(tmp_path, {"jsonVersion": "1.5.3"}))


class TestTileIdsBecomeGlobalIds:
    """LDtk addresses a tile as `(tilesetUid, t)` and has no gid space.

    `Tilemap.properties_for` resolves through one, so the ranges are
    synthesised -- which is what lets an LDtk map use the same collision
    query, the same property lookup and the same `Tileset` as a Tiled one.
    """

    def test_a_sparse_tile_list_becomes_a_dense_grid(self, tmp_path: Path) -> None:
        """LDtk stores placed tiles; `TileLayer` is a grid. A cell nothing
        was placed in stays empty rather than becoming tile 0."""
        maps = load_ldtk(_write(tmp_path, _project()))

        assert _grid(maps["Level_0"], "Ground") == [[1, 2], [0, 4]]

    def test_gids_start_at_one_so_zero_stays_empty(self, tmp_path: Path) -> None:
        maps = load_ldtk(_write(tmp_path, _project()))

        assert maps["Level_0"].tilesets[0].first_gid == 1

    def test_tile_custom_data_that_is_json_becomes_properties(
        self, tmp_path: Path
    ) -> None:
        """LDtk gives a tile one free-text string, and people put JSON in
        it -- which is what makes `{"solid": true}` work with
        `collision_rects` and no translation table."""
        maps = load_ldtk(_write(tmp_path, _project()))

        assert dict(maps["Level_0"].properties_for(1)) == {
            "solid": True,
            "damage": 3,
        }

    def test_tile_custom_data_that_is_not_json_is_kept_verbatim(
        self, tmp_path: Path
    ) -> None:
        """Throwing away a note someone wrote on a tile is worse than
        handing it over unparsed."""
        maps = load_ldtk(_write(tmp_path, _project()))

        assert dict(maps["Level_0"].properties_for(2)) == {"data": "just a note"}

    def test_collision_rects_work_through_the_same_path_as_tiled(
        self, tmp_path: Path
    ) -> None:
        """The whole reason for sharing the model."""
        maps = load_ldtk(_write(tmp_path, _project()))

        rects = maps["Level_0"].collision_rects("Ground")

        assert [(r.x, r.y, r.width, r.height) for r in rects] == [(0, 0, 16, 16)]

    def test_auto_layer_tiles_are_read_too(self, tmp_path: Path) -> None:
        """A generated layer stores its result in `autoLayerTiles`; a
        caller should not have to know which kind it was looking at."""
        project = _project(
            levels=[
                {
                    "identifier": "L",
                    "layerInstances": [
                        _tiles_layer(
                            gridTiles=[],
                            autoLayerTiles=[{"px": [0, 16], "t": 2}],
                        )
                    ],
                }
            ]
        )

        maps = load_ldtk(_write(tmp_path, project))

        assert _grid(maps["L"], "Ground") == [[0, 0], [3, 0]]

    def test_tiles_with_no_tileset_are_dropped_with_a_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        project = _project(
            levels=[
                {
                    "identifier": "L",
                    "layerInstances": [_tiles_layer(__tilesetDefUid=None)],
                }
            ]
        )

        with caplog.at_level("WARNING"):
            maps = load_ldtk(_write(tmp_path, project))

        assert _grid(maps["L"], "Ground") == [[0, 0], [0, 0]]
        assert "names no tileset" in caplog.text


class TestIntGridLayers:
    """A dense grid of small integers, with no tileset anywhere.

    Each gets a synthetic one so its values resolve through the same
    `properties_for` path as every other tile, rather than needing a
    second code path in every consumer.
    """

    def test_values_become_tiles_in_a_synthetic_tileset(self, tmp_path: Path) -> None:
        maps = load_ldtk(_write(tmp_path, _project()))
        tilemap = maps["Level_0"]

        grid = _grid(tilemap, "Collisions")
        assert grid[0][1] == 0  # the zero in the CSV is genuinely empty
        assert grid[0][0] != 0

    def test_a_value_keeps_its_ldtk_name(self, tmp_path: Path) -> None:
        """The names live in the layer *definition*, so a level's
        `intGridCsv` is bare integers until the two are joined."""
        maps = load_ldtk(_write(tmp_path, _project()))
        tilemap = maps["Level_0"]

        first = tilemap.layers["Collisions"].get_tile((0, 0))
        assert tilemap.properties_for(first)["identifier"] == "Solid"
        assert tilemap.properties_for(first)["int_value"] == 1

    def test_nothing_is_solid_unless_the_caller_says_so(self, tmp_path: Path) -> None:
        """LDtk records a value's name and colour and nothing that says
        whether it blocks. Guessing from the name would be right for
        English projects and wrong for the rest."""
        maps = load_ldtk(_write(tmp_path, _project()))

        assert maps["Level_0"].collision_rects("Collisions") == []

    def test_naming_a_value_solid_makes_it_collide(self, tmp_path: Path) -> None:
        maps = load_ldtk(_write(tmp_path, _project()), solid_int_grid_values=["Solid"])

        rects = maps["Level_0"].collision_rects("Collisions")

        # Value 1 sits at (0,0) and (1,1); value 2 (Water) is not solid.
        assert sorted((r.x, r.y) for r in rects) == [(0, 0), (16, 16)]

    def test_water_stays_passable(self, tmp_path: Path) -> None:
        maps = load_ldtk(_write(tmp_path, _project()), solid_int_grid_values=["Solid"])
        tilemap = maps["Level_0"]

        water = tilemap.layers["Collisions"].get_tile((0, 1))
        assert tilemap.properties_for(water)["identifier"] == "Water"
        assert tilemap.properties_for(water)["solid"] is False

    def test_an_intgrid_tileset_does_not_collide_with_a_real_one(
        self, tmp_path: Path
    ) -> None:
        """Both resolve through one gid space, so the ranges must not
        overlap -- or an IntGrid value would answer for an art tile."""
        maps = load_ldtk(_write(tmp_path, _project()))
        tilemap = maps["Level_0"]

        ranges = [
            range(t.first_gid, t.first_gid + t.tile_count) for t in tilemap.tilesets
        ]
        for i, first in enumerate(ranges):
            for second in ranges[i + 1 :]:
                assert not set(first) & set(second)


class TestEntityLayers:
    """LDtk entities, through the `MapObject` the Tiled loader also uses."""

    def test_entities_become_an_object_layer(self, tmp_path: Path) -> None:
        maps = load_ldtk(_write(tmp_path, _project()))

        assert list(maps["Level_0"].object_layers) == ["Entities"]

    def test_an_entity_keeps_its_identifier_as_both_name_and_type(
        self, tmp_path: Path
    ) -> None:
        """LDtk has one name where Tiled has a name and a class, and the
        one it has is the one a game switches on."""
        maps = load_ldtk(_write(tmp_path, _project()))

        player = maps["Level_0"].objects("Player")
        assert len(player) == 1
        assert player[0].name == "Player"

    def test_entity_fields_arrive_already_typed(self, tmp_path: Path) -> None:
        """Unlike Tiled's string attributes, LDtk resolves the value."""
        maps = load_ldtk(_write(tmp_path, _project()))

        player = maps["Level_0"].objects("Player")[0]
        assert player.properties == {"hp": 10, "name": "guara"}

    def test_an_entity_is_positioned_by_its_top_left(self, tmp_path: Path) -> None:
        """`px` is LDtk's already-resolved top-left, so `x`/`y` mean the
        same thing here as for a Tiled object rather than something that
        depends on where the author put the pivot."""
        maps = load_ldtk(_write(tmp_path, _project()))

        player = maps["Level_0"].objects("Player")[0]
        assert (player.x, player.y) == (8.0, 24.0)
        assert player.center == (16.0, 32.0)

    def test_a_sizeless_entity_is_a_point(self, tmp_path: Path) -> None:
        from pyguara.tilemap import ObjectShape

        maps = load_ldtk(_write(tmp_path, _project()))

        marker = maps["Level_0"].objects("Marker")[0]
        assert marker.shape is ObjectShape.POINT


class TestGridSize:
    """`Tilemap.tile_size` is a single integer, which LDtk does not promise."""

    def test_a_level_mixing_grid_sizes_is_refused(self, tmp_path: Path) -> None:
        """Otherwise a collision grid is silently offset from the art."""
        project = _project(
            levels=[
                {
                    "identifier": "L",
                    "layerInstances": [
                        _tiles_layer(),
                        _intgrid_layer(__gridSize=8),
                    ],
                }
            ]
        )

        with pytest.raises(ValueError, match="mixes grid sizes"):
            load_ldtk(_write(tmp_path, project))

    def test_a_level_with_no_layers_is_refused(self, tmp_path: Path) -> None:
        project = _project(levels=[{"identifier": "L", "layerInstances": []}])

        with pytest.raises(ValueError, match="no layers with a grid size"):
            load_ldtk(_write(tmp_path, project))
