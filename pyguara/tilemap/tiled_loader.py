"""Load a Tiled (.tmx) map into a `Tilemap`.

Deliberately narrow: CSV-encoded tile layers and embedded (not externally
`source`-referenced) tilesets only, since that covers Tiled's modern
default export and the vast majority of hand-authored maps without
pulling in a compression dependency for the base64/zlib/gzip encodings
Tiled also supports. A map using either raises `ValueError` rather than
silently mis-parsing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pyguara.tilemap.layer import TileLayer
from pyguara.tilemap.tilemap import Tilemap
from pyguara.tilemap.tileset import Tileset

_PROPERTY_CONVERTERS: dict[str, Callable[[str], Any]] = {
    "int": int,
    "float": float,
    "bool": lambda v: v == "true",
}


def load_tmx(path: str | Path) -> Tilemap:
    """Parse a `.tmx` file into a `Tilemap`.

    Args:
        path: Path to the `.tmx` file.

    Returns:
        A `Tilemap` with every embedded tileset and CSV-encoded tile layer
        the file contains. Object groups, image layers, and layer groups
        are ignored -- this loads tile data only.

    Raises:
        ValueError: The map uses non-square tiles, a tileset is an
            external `source` reference rather than embedded, or a layer
            uses an encoding other than `csv`.
    """
    root = ElementTree.parse(path).getroot()

    tile_width = int(root.attrib["tilewidth"])
    tile_height = int(root.attrib["tileheight"])
    if tile_width != tile_height:
        raise ValueError(
            f"non-square tiles are not supported ({tile_width}x{tile_height})"
        )

    tilemap = Tilemap(
        tile_size=tile_width,
        tilesets=[_parse_tileset(el) for el in root.findall("tileset")],
    )
    for layer_el in root.findall("layer"):
        tilemap.add_layer(layer_el.attrib["name"], _parse_layer(layer_el))
    return tilemap


def _parse_tileset(element: ElementTree.Element) -> Tileset:
    if "source" in element.attrib:
        raise ValueError(
            f"external tileset files are not supported yet: {element.attrib['source']}"
        )

    properties = {
        int(tile_el.attrib["id"]): _parse_properties(tile_el)
        for tile_el in element.findall("tile")
        if tile_el.find("properties") is not None
    }
    return Tileset(
        name=element.attrib["name"],
        first_gid=int(element.attrib["firstgid"]),
        tile_count=int(element.attrib["tilecount"]),
        properties=properties,
    )


def _parse_properties(tile_element: ElementTree.Element) -> dict[str, Any]:
    properties_el = tile_element.find("properties")
    assert properties_el is not None  # caller only calls us when it exists
    result: dict[str, Any] = {}
    for prop in properties_el.findall("property"):
        name = prop.attrib["name"]
        raw_value = prop.attrib.get("value", prop.text or "")
        convert = _PROPERTY_CONVERTERS.get(prop.attrib.get("type", "string"), str)
        result[name] = convert(raw_value)
    return result


def _parse_layer(element: ElementTree.Element) -> TileLayer:
    width = int(element.attrib["width"])
    height = int(element.attrib["height"])

    data_el = element.find("data")
    if data_el is None or data_el.attrib.get("encoding") != "csv":
        raise ValueError(
            f"layer '{element.attrib.get('name')}' must use CSV encoding "
            "(base64/zlib/gzip-encoded layers are not supported yet)"
        )

    gids = [int(value) for value in data_el.text.split(",") if value.strip()]  # type: ignore[union-attr]
    tiles = [gids[row * width : (row + 1) * width] for row in range(height)]
    return TileLayer(width, height, tiles)
