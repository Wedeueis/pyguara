"""Load a Tiled (`.tmx`) map into a `Tilemap`.

What this reads: embedded **and** external (`.tsx`) tilesets; tile layers
encoded as CSV, as base64 with no compression, gzip or zlib, or as Tiled's
original `<tile gid="...">` elements; layers nested inside `<group>`; and
`<objectgroup>` object layers.

Three of those were previously absent, and the three failed differently,
which is the point:

- An **external tileset** raised. Loud, and fair enough -- except that
  Tiled writes one by default the moment a tileset is shared between two
  maps, which is the normal case for a game rather than an edge one.
- A **non-CSV encoding** raised. Also loud. base64+zlib is what Tiled
  picks for a large map, and the stated reason for refusing it was "a
  compression dependency" -- but `gzip` and `zlib` are in the standard
  library, so there was never one to pull in.
- An **`<objectgroup>`**, or a layer inside a **`<group>`**, was silently
  dropped. A map with spawn points loaded "successfully" and lost them.
  That asymmetry was the real defect: a loud refusal is a decision, and
  silence is a bug report from a confused author six months later.

Still refused, deliberately: non-square tiles (`Tilemap.tile_size` is one
integer, and `merge_tile_rects` beneath `TileLayer.collision_rects` takes
one size, so supporting them is a change to the tilemap model rather than
to this loader) and `zstd` compression (not in the standard library).
Infinite maps -- `<data>` split into `<chunk>` elements -- are refused by
name rather than quietly returning the first chunk.
"""

from __future__ import annotations

import base64
import gzip
import struct
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pyguara.log import get_logger
from pyguara.tilemap.layer import TileLayer
from pyguara.tilemap.objects import MapObject, ObjectLayer, ObjectShape
from pyguara.tilemap.tilemap import Tilemap
from pyguara.tilemap.tileset import Tileset

logger = get_logger(__name__)

_PROPERTY_CONVERTERS: dict[str, Callable[[str], Any]] = {
    "int": int,
    "float": float,
    "bool": lambda v: v == "true",
}

GID_FLAG_MASK = 0x1FFFFFFF
"""Keeps the tile id and discards Tiled's three orientation flags.

Tiled packs horizontal (`0x80000000`), vertical (`0x40000000`) and
diagonal (`0x20000000`) flips into a gid's top bits. Unmasked, a
horizontally flipped tile 1 arrives as 2147483649, no `Tileset`'s range
contains it, and `Tilemap.properties_for` returns `{}` -- so **a flipped
wall silently stops being solid**, and only in the places the author
happened to mirror a tile. The flags themselves are not yet exposed;
masking them is what makes the tile id usable at all.
"""

_DECOMPRESSORS: dict[str, Callable[[bytes], bytes]] = {
    "gzip": gzip.decompress,
    "zlib": zlib.decompress,
}


def load_tmx(path: str | Path) -> Tilemap:
    """Parse a `.tmx` file into a `Tilemap`.

    Args:
        path: Path to the `.tmx` file. External tilesets are resolved
            relative to it, as Tiled writes them.

    Returns:
        A `Tilemap` carrying every tileset, every tile layer (including
        those nested in `<group>`), and every `<objectgroup>`. Image
        layers are still ignored -- they are decoration with no data a
        game reads.

    Raises:
        ValueError: The map uses non-square tiles, an unsupported layer
            encoding or compression, or is an infinite map.
        FileNotFoundError: An external tileset's `source` does not
            resolve.
    """
    map_path = Path(path)
    root = ElementTree.parse(map_path).getroot()

    tile_width = int(root.attrib["tilewidth"])
    tile_height = int(root.attrib["tileheight"])
    if tile_width != tile_height:
        raise ValueError(
            f"non-square tiles are not supported ({tile_width}x{tile_height}); "
            f"Tilemap.tile_size is a single edge length"
        )
    if root.attrib.get("infinite") == "1":
        raise ValueError(
            "infinite maps are not supported: their layer data is split into "
            "<chunk> elements with no fixed extent, which a dense TileLayer "
            "cannot hold. Re-export the map as a finite one."
        )

    tilemap = Tilemap(
        tile_size=tile_width,
        tilesets=[
            _parse_tileset(element, map_path.parent)
            for element in root.findall("tileset")
        ],
    )
    _collect_layers(root, tilemap)
    return tilemap


def _collect_layers(parent: ElementTree.Element, tilemap: Tilemap) -> None:
    """Add every tile and object layer under `parent`, recursing into groups.

    Tiled nests layers inside `<group>` whenever an author makes a folder
    in the layer panel, and the loader only looked at the root's direct
    children -- so organising a map made its layers disappear.

    A grouped layer is added under its own name, not a path: `Tilemap`
    keys layers by name in one flat dict, and inventing `"decor/grass"`
    here would make the key depend on how the author filed it.

    Args:
        parent: The element whose children to walk.
        tilemap: The map to add layers to.
    """
    for element in parent:
        if element.tag == "layer":
            tilemap.add_layer(element.attrib["name"], _parse_layer(element))
        elif element.tag == "objectgroup":
            tilemap.add_object_layer(_parse_object_layer(element))
        elif element.tag == "group":
            _collect_layers(element, tilemap)


def _parse_tileset(element: ElementTree.Element, base_dir: Path) -> Tileset:
    """Build a `Tileset` from an embedded or external tileset element.

    Args:
        element: The map's `<tileset>` element.
        base_dir: Directory the map was loaded from, which `source` is
            relative to.

    Returns:
        The tileset, with `first_gid` taken from the map element even
        when everything else comes from a `.tsx` file -- the gid range is
        a property of this map's use of the tileset, not of the tileset,
        which is exactly why Tiled keeps `firstgid` behind in the map.

    Raises:
        FileNotFoundError: `source` does not resolve.
        ValueError: The referenced file's root is not a `<tileset>`.
    """
    first_gid = int(element.attrib["firstgid"])
    source = element.attrib.get("source")
    if source is None:
        return _tileset_from(element, first_gid)

    tileset_path = (base_dir / source).resolve()
    if not tileset_path.is_file():
        raise FileNotFoundError(
            f"external tileset '{source}' referenced by the map does not exist "
            f"at {tileset_path}"
        )
    external_root = ElementTree.parse(tileset_path).getroot()
    if external_root.tag != "tileset":
        raise ValueError(
            f"'{source}' is not a tileset file: its root element is "
            f"<{external_root.tag}>, not <tileset>"
        )
    return _tileset_from(external_root, first_gid)


def _tileset_from(element: ElementTree.Element, first_gid: int) -> Tileset:
    """Read a tileset's name, size and per-tile properties.

    Args:
        element: A `<tileset>` element, embedded or an external root.
        first_gid: The gid this tileset's tile 0 maps to.

    Returns:
        The tileset.
    """
    properties = {
        int(tile_el.attrib["id"]): _parse_properties(tile_el)
        for tile_el in element.findall("tile")
        if tile_el.find("properties") is not None
    }
    return Tileset(
        name=element.attrib.get("name", ""),
        first_gid=first_gid,
        tile_count=int(element.attrib["tilecount"]),
        properties=properties,
    )


def _parse_properties(element: ElementTree.Element) -> dict[str, Any]:
    """Read an element's `<properties>` child, applying Tiled's types.

    Args:
        element: Any element that may carry a `<properties>` child.

    Returns:
        The properties, or `{}` when there is no such child.
    """
    properties_el = element.find("properties")
    if properties_el is None:
        return {}
    result: dict[str, Any] = {}
    for prop in properties_el.findall("property"):
        name = prop.attrib["name"]
        raw_value = prop.attrib.get("value", prop.text or "")
        convert = _PROPERTY_CONVERTERS.get(prop.attrib.get("type", "string"), str)
        result[name] = convert(raw_value)
    return result


def _parse_layer(element: ElementTree.Element) -> TileLayer:
    """Decode one `<layer>` into a dense grid of tile ids.

    Args:
        element: The `<layer>` element.

    Returns:
        The layer.

    Raises:
        ValueError: The encoding or compression is not supported, or the
            decoded data is not `width * height` tiles.
    """
    width = int(element.attrib["width"])
    height = int(element.attrib["height"])
    name = element.attrib.get("name", "?")

    data_el = element.find("data")
    if data_el is None:
        raise ValueError(f"layer '{name}' has no <data> element")
    if data_el.find("chunk") is not None:
        raise ValueError(
            f"layer '{name}' is chunked, which means an infinite map; "
            f"re-export it as a finite one"
        )

    gids = _decode_layer_data(data_el, name)
    if len(gids) != width * height:
        raise ValueError(
            f"layer '{name}' decoded to {len(gids)} tiles, but its size is "
            f"{width}x{height} = {width * height}"
        )

    tiles = [gids[row * width : (row + 1) * width] for row in range(height)]
    return TileLayer(width, height, tiles)


def _decode_layer_data(data_el: ElementTree.Element, layer_name: str) -> list[int]:
    """Turn a `<data>` element into a flat list of tile ids.

    Args:
        data_el: The `<data>` element.
        layer_name: Used only in error messages.

    Returns:
        Tile ids in row-major order, with orientation flags masked off.

    Raises:
        ValueError: The encoding or compression is not supported.
    """
    encoding = data_el.attrib.get("encoding")

    if encoding == "csv":
        raw = [int(value) for value in (data_el.text or "").split(",") if value.strip()]
    elif encoding == "base64":
        raw = _decode_base64(data_el, layer_name)
    elif encoding is None:
        # Tiled's original format: one <tile> element per cell. Verbose,
        # still written by older tools, and trivial to read.
        raw = [int(tile.attrib.get("gid", 0)) for tile in data_el.findall("tile")]
    else:
        raise ValueError(
            f"layer '{layer_name}' uses encoding '{encoding}', which is not "
            f"supported (use csv, base64, or no encoding)"
        )

    return [gid & GID_FLAG_MASK for gid in raw]


def _decode_base64(data_el: ElementTree.Element, layer_name: str) -> list[int]:
    """Decode base64 layer data, decompressing it if Tiled compressed it.

    Args:
        data_el: The `<data>` element, with `encoding="base64"`.
        layer_name: Used only in error messages.

    Returns:
        The raw gids, flags included -- the caller masks them.

    Raises:
        ValueError: The compression is not supported, or the payload is
            not a whole number of 32-bit tile ids.
    """
    payload = base64.b64decode((data_el.text or "").strip())
    compression = data_el.attrib.get("compression")
    if compression:
        decompress = _DECOMPRESSORS.get(compression)
        if decompress is None:
            raise ValueError(
                f"layer '{layer_name}' uses '{compression}' compression, which "
                f"is not supported. gzip and zlib are; zstd needs a dependency "
                f"outside the standard library."
            )
        payload = decompress(payload)

    if len(payload) % 4:
        raise ValueError(
            f"layer '{layer_name}' decoded to {len(payload)} bytes, which is "
            f"not a whole number of 32-bit tile ids"
        )
    # Little-endian unsigned, which is what the format specifies -- signed
    # would turn every flipped tile into a negative number.
    return list(struct.unpack(f"<{len(payload) // 4}I", payload))


def _parse_object_layer(element: ElementTree.Element) -> ObjectLayer:
    """Build an `ObjectLayer` from an `<objectgroup>`.

    Args:
        element: The `<objectgroup>` element.

    Returns:
        The layer, objects in file order.
    """
    return ObjectLayer(
        name=element.attrib.get("name", ""),
        objects=tuple(_parse_object(el) for el in element.findall("object")),
        visible=element.attrib.get("visible", "1") != "0",
        properties=_parse_properties(element),
    )


def _parse_object(element: ElementTree.Element) -> MapObject:
    """Build a `MapObject` from an `<object>`.

    Args:
        element: The `<object>` element.

    Returns:
        The object, with its shape resolved from whichever child element
        Tiled used to express it.
    """
    shape = ObjectShape.RECTANGLE
    points: tuple[tuple[float, float], ...] = ()
    gid: int | None = None

    if "gid" in element.attrib:
        shape = ObjectShape.TILE
        gid = int(element.attrib["gid"]) & GID_FLAG_MASK
    elif element.find("point") is not None:
        shape = ObjectShape.POINT
    elif element.find("ellipse") is not None:
        shape = ObjectShape.ELLIPSE
    else:
        for tag, kind in (
            ("polygon", ObjectShape.POLYGON),
            ("polyline", ObjectShape.POLYLINE),
        ):
            child = element.find(tag)
            if child is not None:
                shape = kind
                points = _parse_points(child.attrib.get("points", ""))
                break

    return MapObject(
        id=int(element.attrib.get("id", 0)),
        # Tiled 1.9 renamed `type` to `class`; both appear in the wild,
        # and a file written by either should mean the same thing here.
        name=element.attrib.get("name", ""),
        type=element.attrib.get("type", element.attrib.get("class", "")),
        x=float(element.attrib.get("x", 0.0)),
        y=float(element.attrib.get("y", 0.0)),
        width=float(element.attrib.get("width", 0.0)),
        height=float(element.attrib.get("height", 0.0)),
        rotation=float(element.attrib.get("rotation", 0.0)),
        gid=gid,
        visible=element.attrib.get("visible", "1") != "0",
        shape=shape,
        points=points,
        properties=_parse_properties(element),
    )


def _parse_points(raw: str) -> tuple[tuple[float, float], ...]:
    """Parse Tiled's `"x,y x,y x,y"` point list.

    Args:
        raw: The `points` attribute's value.

    Returns:
        The vertices, relative to the object's position as Tiled stores
        them.
    """
    vertices = []
    for pair in raw.split():
        x_text, _, y_text = pair.partition(",")
        vertices.append((float(x_text), float(y_text)))
    return tuple(vertices)
