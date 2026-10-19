"""Tests for `pyguara/tilemap/tiled_loader.py` (`load_tmx`)."""

from __future__ import annotations

import base64
import gzip
import struct
import zlib
from pathlib import Path

import pytest

from pyguara.common.types import Rect
from pyguara.tilemap import ObjectShape, Tilemap, load_tmx

_SIMPLE_MAP = """<?xml version="1.0" encoding="UTF-8"?>
<map version="1.10" tiledversion="1.10.2" orientation="orthogonal"
     renderorder="right-down" width="2" height="2" tilewidth="16"
     tileheight="16" infinite="0" nextlayerid="2" nextobjectid="1">
 <tileset firstgid="1" name="ground" tilewidth="16" tileheight="16" tilecount="4" columns="4">
  <tile id="0">
   <properties>
    <property name="solid" type="bool" value="true"/>
    <property name="damage" type="int" value="5"/>
    <property name="label" value="wall"/>
   </properties>
  </tile>
 </tileset>
 <layer id="1" name="ground" width="2" height="2">
  <data encoding="csv">
1,2,
2,1
</data>
 </layer>
</map>
"""

_NON_SQUARE_MAP = _SIMPLE_MAP.replace('tileheight="16"', 'tileheight="32"', 1)

_EXTERNAL_TILESET_MAP = _SIMPLE_MAP.replace(
    '<tileset firstgid="1" name="ground" tilewidth="16" tileheight="16" '
    'tilecount="4" columns="4">\n  <tile id="0">\n   <properties>\n    '
    '<property name="solid" type="bool" value="true"/>\n    '
    '<property name="damage" type="int" value="5"/>\n    '
    '<property name="label" value="wall"/>\n   </properties>\n  </tile>\n </tileset>',
    '<tileset firstgid="1" source="ground.tsx"/>',
)

_EXTERNAL_TILESET = """<?xml version="1.0" encoding="UTF-8"?>
<tileset version="1.10" name="ground" tilewidth="16" tileheight="16"
         tilecount="4" columns="4">
 <tile id="0">
  <properties>
   <property name="solid" type="bool" value="true"/>
   <property name="damage" type="int" value="5"/>
  </properties>
 </tile>
</tileset>
"""


def _base64_map(compression: str = "", gids: list[int] | None = None) -> str:
    """The simple map with its layer re-encoded as base64.

    Built rather than pasted: a hand-written base64 blob is unreadable,
    and a reader cannot tell a wrong expectation from a wrong decoder.
    """
    payload = struct.pack("<4I", *(gids or [1, 2, 2, 1]))
    if compression == "gzip":
        payload = gzip.compress(payload)
    elif compression == "zlib":
        payload = zlib.compress(payload)
    attribute = f' compression="{compression}"' if compression else ""
    return _SIMPLE_MAP.replace(
        '<data encoding="csv">\n1,2,\n2,1\n</data>',
        f'<data encoding="base64"{attribute}>'
        f"{base64.b64encode(payload).decode()}</data>",
    )


def _grid(tilemap: Tilemap, layer_name: str) -> list[list[int]]:
    """A layer's tile ids as nested lists, for readable expectations."""
    layer = tilemap.layers[layer_name]
    return [
        [layer.get_tile((x, y)) for x in range(layer.width)]
        for y in range(layer.height)
    ]


def _write(tmp_path: Path, content: str, name: str = "map.tmx") -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


def test_load_tmx_parses_tile_size_from_root_attributes(tmp_path: Path) -> None:
    tilemap = load_tmx(_write(tmp_path, _SIMPLE_MAP))

    assert tilemap.tile_size == 16


def test_load_tmx_parses_csv_layer_data(tmp_path: Path) -> None:
    tilemap = load_tmx(_write(tmp_path, _SIMPLE_MAP))

    layer = tilemap.layers["ground"]
    assert layer.get_tile((0, 0)) == 1
    assert layer.get_tile((1, 0)) == 2
    assert layer.get_tile((0, 1)) == 2
    assert layer.get_tile((1, 1)) == 1


def test_load_tmx_parses_embedded_tile_properties_with_types(tmp_path: Path) -> None:
    tilemap = load_tmx(_write(tmp_path, _SIMPLE_MAP))

    # gid 1 is local tile id 0 in the "ground" tileset (firstgid=1).
    properties = tilemap.properties_for(1)
    assert properties == {"solid": True, "damage": 5, "label": "wall"}


def test_load_tmx_result_produces_correct_collision_rects(tmp_path: Path) -> None:
    tilemap = load_tmx(_write(tmp_path, _SIMPLE_MAP))

    # gid 1 (top-left, bottom-right) is solid; gid 2 (top-right, bottom-left)
    # has no properties at all, so it is not solid. The two solid tiles are
    # diagonal, not adjacent, so they stay two separate rectangles.
    rects = tilemap.collision_rects("ground")

    assert rects == [Rect(0, 0, 16, 16), Rect(16, 16, 16, 16)]


def test_load_tmx_rejects_non_square_tiles(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-square"):
        load_tmx(_write(tmp_path, _NON_SQUARE_MAP))


# The two rejections these replace were real, documented decisions -- and
# both have been overtaken. Tiled writes an external tileset the moment
# one is shared between two maps, which is the normal case for a game
# rather than an edge one; and the stated reason for refusing base64 was
# "a compression dependency", when `gzip` and `zlib` are in the standard
# library and there was never one to pull in.


def test_load_tmx_reads_an_external_tileset(tmp_path: Path) -> None:
    _write(tmp_path, _EXTERNAL_TILESET, "ground.tsx")

    tilemap = load_tmx(_write(tmp_path, _EXTERNAL_TILESET_MAP))

    assert [t.name for t in tilemap.tilesets] == ["ground"]
    assert dict(tilemap.properties_for(1)) == {"solid": True, "damage": 5}


def test_an_external_tileset_takes_its_first_gid_from_the_map(
    tmp_path: Path,
) -> None:
    """`firstgid` stays behind in the map on purpose.

    A tileset shared between two maps occupies a different gid range in
    each, so the range is a property of the *use*, not of the tileset --
    which is why Tiled leaves the attribute on the `<tileset>` reference
    and not in the `.tsx`.
    """
    _write(tmp_path, _EXTERNAL_TILESET, "ground.tsx")
    shifted = _EXTERNAL_TILESET_MAP.replace('firstgid="1"', 'firstgid="100"')

    tilemap = load_tmx(_write(tmp_path, shifted))

    assert tilemap.tilesets[0].first_gid == 100
    assert dict(tilemap.properties_for(100)) == {"solid": True, "damage": 5}


def test_a_missing_external_tileset_says_where_it_looked(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="ground.tsx"):
        load_tmx(_write(tmp_path, _EXTERNAL_TILESET_MAP))


def test_an_external_source_that_is_not_a_tileset_is_refused(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "<notatileset/>", "ground.tsx")

    with pytest.raises(ValueError, match="not a tileset file"):
        load_tmx(_write(tmp_path, _EXTERNAL_TILESET_MAP))


@pytest.mark.parametrize("compression", ["", "gzip", "zlib"])
def test_load_tmx_reads_base64_layer_data(tmp_path: Path, compression: str) -> None:
    """All three give the same grid as the CSV map they were built from."""
    tilemap = load_tmx(_write(tmp_path, _base64_map(compression)))

    assert _grid(tilemap, "ground") == [[1, 2], [2, 1]]


def test_base64_and_csv_agree(tmp_path: Path) -> None:
    csv_map = load_tmx(_write(tmp_path, _SIMPLE_MAP, "csv.tmx"))
    b64_map = load_tmx(_write(tmp_path, _base64_map("zlib"), "b64.tmx"))

    assert _grid(csv_map, "ground") == _grid(b64_map, "ground")


def test_an_unsupported_compression_names_itself(tmp_path: Path) -> None:
    """zstd is a real Tiled option and genuinely needs a dependency."""
    with pytest.raises(ValueError, match="zstd"):
        load_tmx(_write(tmp_path, _base64_map("zstd")))


def test_an_unsupported_encoding_names_itself(tmp_path: Path) -> None:
    broken = _SIMPLE_MAP.replace('encoding="csv"', 'encoding="json"')

    with pytest.raises(ValueError, match="json"):
        load_tmx(_write(tmp_path, broken))


def test_load_tmx_reads_tiled_s_original_tile_elements(tmp_path: Path) -> None:
    """No `encoding` at all: one `<tile gid=...>` per cell.

    Verbose, still written by older tools, and five lines to read.
    """
    xml_data = (
        "<data>" + "".join(f'<tile gid="{gid}"/>' for gid in (1, 2, 2, 1)) + "</data>"
    )
    old_format = _SIMPLE_MAP.replace(
        '<data encoding="csv">\n1,2,\n2,1\n</data>', xml_data
    )

    tilemap = load_tmx(_write(tmp_path, old_format))

    assert _grid(tilemap, "ground") == [[1, 2], [2, 1]]


def test_a_layer_whose_data_does_not_match_its_size_is_refused(
    tmp_path: Path,
) -> None:
    """Silently reshaping it would misplace every tile after the first row."""
    short = _SIMPLE_MAP.replace("1,2,\n2,1", "1,2,2")

    with pytest.raises(ValueError, match="decoded to 3 tiles"):
        load_tmx(_write(tmp_path, short))


def test_an_infinite_map_is_refused_by_name(tmp_path: Path) -> None:
    """Rather than returning whatever the first chunk happened to hold."""
    infinite = _SIMPLE_MAP.replace('infinite="0"', 'infinite="1"')

    with pytest.raises(ValueError, match="infinite"):
        load_tmx(_write(tmp_path, infinite))


class TestTileFlipFlags:
    """Tiled packs three flip flags into a gid's top bits.

    Unmasked, a horizontally flipped tile 1 arrives as 2147483649, no
    tileset's range contains it, and `properties_for` returns `{}` -- so
    **a flipped wall silently stops being solid**, and only in the places
    the author happened to mirror a tile. Nothing in the loader
    acknowledged the flags existed.
    """

    HORIZONTAL = 0x80000000
    VERTICAL = 0x40000000
    DIAGONAL = 0x20000000

    def _flipped(self, flag: int) -> str:
        return _SIMPLE_MAP.replace("1,2,\n2,1", f"{1 | flag},2,\n2,1")

    @pytest.mark.parametrize(
        "flag", [HORIZONTAL, VERTICAL, DIAGONAL, HORIZONTAL | VERTICAL]
    )
    def test_a_flipped_tile_keeps_its_tile_id(self, tmp_path: Path, flag: int) -> None:
        tilemap = load_tmx(_write(tmp_path, self._flipped(flag)))

        assert _grid(tilemap, "ground")[0][0] == 1

    def test_a_flipped_wall_is_still_solid(self, tmp_path: Path) -> None:
        """The consequence, stated as the thing a game would notice."""
        tilemap = load_tmx(_write(tmp_path, self._flipped(self.HORIZONTAL)))

        assert dict(tilemap.properties_for(1)) == {
            "solid": True,
            "damage": 5,
            "label": "wall",
        }
        assert tilemap.collision_rects("ground")

    def test_flags_are_masked_in_base64_data_too(self, tmp_path: Path) -> None:
        """base64 is where flipped tiles actually come from in practice --
        it is what Tiled writes for any map large enough to mirror tiles in."""
        gids = [1 | self.HORIZONTAL, 2, 2, 1]
        tilemap = load_tmx(_write(tmp_path, _base64_map("zlib", gids)))

        assert _grid(tilemap, "ground") == [[1, 2], [2, 1]]


_OBJECT_MAP = _SIMPLE_MAP.replace(
    "</map>",
    """ <objectgroup id="2" name="spawns">
  <object id="1" name="player_start" type="PlayerSpawn" x="32" y="48">
   <point/>
  </object>
  <object id="2" name="exit" class="Trigger" x="64" y="16" width="32" height="24">
   <properties><property name="target" value="level2"/></properties>
  </object>
  <object id="3" name="pond" type="Water" x="8" y="8" width="16" height="16">
   <ellipse/>
  </object>
  <object id="4" name="patrol" x="10" y="20">
   <polyline points="0,0 16,0 16,16"/>
  </object>
  <object id="5" name="arena" x="0" y="0" rotation="45" visible="0">
   <polygon points="0,0 32,0 32,32 0,32"/>
  </object>
  <object id="6" name="crate" type="Prop" gid="2147483650" x="48" y="64"
          width="16" height="16"/>
 </objectgroup>
</map>""",
)

_GROUPED_MAP = _SIMPLE_MAP.replace(
    "</map>",
    """ <group id="9" name="decor">
  <layer id="4" name="grass" width="2" height="2">
   <data encoding="csv">3,3,3,3</data>
  </layer>
  <objectgroup id="5" name="props">
   <object id="1" name="bench" type="Prop" x="4" y="4"/>
  </objectgroup>
  <group id="6" name="deeper">
   <layer id="7" name="canopy" width="2" height="2">
    <data encoding="csv">4,4,4,4</data>
   </layer>
  </group>
 </group>
</map>""",
)


class TestObjectGroupsAreNoLongerDropped:
    """The defect the two refusals above were not.

    `load_tmx` walked only `tileset` and `layer`, so an `<objectgroup>`
    was ignored entirely: a map with spawn points loaded "successfully"
    and lost them. A loud refusal is a decision; silence is a bug report
    from a confused author six months later.
    """

    def test_the_object_layer_is_loaded(self, tmp_path: Path) -> None:
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        assert list(tilemap.object_layers) == ["spawns"]
        assert len(tilemap.object_layers["spawns"].objects) == 6

    def test_a_spawn_point_keeps_its_name_type_and_position(
        self, tmp_path: Path
    ) -> None:
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        spawn = tilemap.object_layers["spawns"].by_name("player_start")
        assert spawn is not None
        assert spawn.type == "PlayerSpawn"
        assert (spawn.x, spawn.y) == (32.0, 48.0)
        assert spawn.shape is ObjectShape.POINT

    def test_tiled_1_9_s_class_attribute_reads_as_type(self, tmp_path: Path) -> None:
        """Tiled renamed `type` to `class`; both are in the wild, and a
        file written by either should mean the same thing here."""
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        assert tilemap.objects("Trigger")[0].name == "exit"

    def test_object_properties_are_typed_like_tile_properties(
        self, tmp_path: Path
    ) -> None:
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        exit_object = tilemap.object_layers["spawns"].by_name("exit")
        assert exit_object is not None
        assert exit_object.properties == {"target": "level2"}

    @pytest.mark.parametrize(
        "name,shape",
        [
            ("player_start", ObjectShape.POINT),
            ("exit", ObjectShape.RECTANGLE),
            ("pond", ObjectShape.ELLIPSE),
            ("patrol", ObjectShape.POLYLINE),
            ("arena", ObjectShape.POLYGON),
            ("crate", ObjectShape.TILE),
        ],
    )
    def test_every_shape_tiled_can_draw_is_recognised(
        self, tmp_path: Path, name: str, shape: ObjectShape
    ) -> None:
        """Tiled encodes the shape as *which child element is present*,
        which is five different checks rather than one attribute."""
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        found = tilemap.object_layers["spawns"].by_name(name)
        assert found is not None
        assert found.shape is shape

    def test_polygon_points_are_relative_and_can_be_made_absolute(
        self, tmp_path: Path
    ) -> None:
        """Tiled stores vertices relative to the object's position, which
        is convenient for editing and wrong for drawing or colliding."""
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        patrol = tilemap.object_layers["spawns"].by_name("patrol")
        assert patrol is not None
        assert patrol.points == ((0.0, 0.0), (16.0, 0.0), (16.0, 16.0))
        assert patrol.absolute_points() == (
            (10.0, 20.0),
            (26.0, 20.0),
            (26.0, 36.0),
        )

    def test_a_tile_object_has_its_flip_flags_masked(self, tmp_path: Path) -> None:
        """gid 2147483650 is tile 2 with the horizontal-flip bit set."""
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        crate = tilemap.object_layers["spawns"].by_name("crate")
        assert crate is not None
        assert crate.gid == 2

    def test_rotation_and_visibility_survive(self, tmp_path: Path) -> None:
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        arena = tilemap.object_layers["spawns"].by_name("arena")
        assert arena is not None
        assert arena.rotation == 45.0
        assert arena.visible is False

    def test_objects_can_be_found_across_layers_by_type(self, tmp_path: Path) -> None:
        """Most callers want "every spawn point in this map" and should
        not have to know which layer the author filed them under."""
        tilemap = load_tmx(_write(tmp_path, _GROUPED_MAP))

        assert [obj.name for obj in tilemap.objects("Prop")] == ["bench"]

    def test_the_centre_of_a_rectangle_object(self, tmp_path: Path) -> None:
        tilemap = load_tmx(_write(tmp_path, _OBJECT_MAP))

        exit_object = tilemap.object_layers["spawns"].by_name("exit")
        assert exit_object is not None
        assert exit_object.center == (80.0, 28.0)

    def test_a_map_with_no_objects_has_an_empty_mapping(self, tmp_path: Path) -> None:
        """Not None, so a caller can iterate without checking."""
        tilemap = load_tmx(_write(tmp_path, _SIMPLE_MAP))

        assert tilemap.object_layers == {}
        assert tilemap.objects() == []


class TestLayerGroupsAreNoLongerDropped:
    """The same silence, one element over.

    Tiled nests layers inside `<group>` whenever an author makes a folder
    in the layer panel, and the loader looked only at the root's direct
    children -- so *organising* a map made its layers disappear.
    """

    def test_a_grouped_tile_layer_is_loaded(self, tmp_path: Path) -> None:
        tilemap = load_tmx(_write(tmp_path, _GROUPED_MAP))

        assert "grass" in tilemap.layers
        assert _grid(tilemap, "grass") == [[3, 3], [3, 3]]

    def test_nesting_goes_as_deep_as_the_author_filed_it(self, tmp_path: Path) -> None:
        tilemap = load_tmx(_write(tmp_path, _GROUPED_MAP))

        assert _grid(tilemap, "canopy") == [[4, 4], [4, 4]]

    def test_a_grouped_object_layer_is_loaded_too(self, tmp_path: Path) -> None:
        tilemap = load_tmx(_write(tmp_path, _GROUPED_MAP))

        assert list(tilemap.object_layers) == ["props"]

    def test_a_grouped_layer_keeps_its_own_name(self, tmp_path: Path) -> None:
        """Not a path. `Tilemap` keys layers by name in one flat dict, and
        inventing "decor/grass" would make the key depend on how the
        author happened to file it."""
        tilemap = load_tmx(_write(tmp_path, _GROUPED_MAP))

        assert set(tilemap.layers) == {"ground", "grass", "canopy"}

    def test_the_ungrouped_layer_is_still_there(self, tmp_path: Path) -> None:
        tilemap = load_tmx(_write(tmp_path, _GROUPED_MAP))

        assert _grid(tilemap, "ground") == [[1, 2], [2, 1]]
