"""Tests for `pyguara/tilemap/tiled_loader.py` (`load_tmx`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyguara.common.types import Rect
from pyguara.tilemap import load_tmx

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

_BASE64_MAP = _SIMPLE_MAP.replace(
    '<data encoding="csv">\n1,2,\n2,1\n</data>',
    '<data encoding="base64">AQAAAAIAAAACAAAAAQAAAA==</data>',
)


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


def test_load_tmx_rejects_external_tileset_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="external tileset"):
        load_tmx(_write(tmp_path, _EXTERNAL_TILESET_MAP))


def test_load_tmx_rejects_non_csv_encoding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="CSV"):
        load_tmx(_write(tmp_path, _BASE64_MAP))
