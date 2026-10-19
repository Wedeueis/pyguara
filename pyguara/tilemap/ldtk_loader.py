"""Load an LDtk (`.ldtk`) project into the same `Tilemap` the Tiled loader builds.

**One level model, two front ends.** The alternative -- an `LdtkLevel`
beside `Tilemap`, each with its own layers, its own tilesets and its own
collision query -- would mean every consumer in the engine, and every
game, learning both. `TileLayer.collision_rects`, `Tilemap.properties_for`
and `MapObject` already exist and already work; this translates LDtk into
them.

The translation is not a renaming exercise, because the two formats
disagree about four things:

- **A file is a world, not a map.** An LDtk project holds many levels, so
  `load_ldtk` returns one `Tilemap` per level rather than one map.
- **Tile ids are per-tileset.** LDtk has no global id space; a tile is
  `(tilesetUid, t)`. Tiled's `firstgid` scheme is synthesised here, by
  laying each tileset's tiles out end to end, so `Tilemap.properties_for`
  works unchanged.
- **Tile layers are sparse.** LDtk stores a list of placed tiles with
  pixel positions; `TileLayer` is a dense grid. The grid is filled from
  the list, and a cell nothing was placed in stays `EMPTY_GID`.
- **IntGrid layers have no tileset at all.** They are a dense grid of
  small integers with names attached in the layer *definition*. Each one
  gets a synthetic tileset so the values resolve through the same
  `properties_for` path as everything else -- see `solid_int_grid_values`
  for the one thing that cannot be inferred.

What is deliberately not translated: level backgrounds, LDtk's
auto-layer *rules* (the resulting tiles are read; the rules that produced
them are an editor concern), and entity references between levels.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pyguara.log import get_logger
from pyguara.tilemap.layer import EMPTY_GID, TileLayer
from pyguara.tilemap.objects import MapObject, ObjectLayer, ObjectShape
from pyguara.tilemap.tilemap import Tilemap
from pyguara.tilemap.tileset import Tileset

logger = get_logger(__name__)

__all__ = ["load_ldtk", "load_ldtk_level"]

_TILE_LAYER_TYPES = {"Tiles", "AutoLayer", "IntGrid"}


def load_ldtk(
    path: str | Path,
    *,
    solid_int_grid_values: Iterable[str] = (),
) -> dict[str, Tilemap]:
    """Parse an `.ldtk` project into one `Tilemap` per level.

    Args:
        path: Path to the `.ldtk` file. Levels saved to separate files
            (`.ldtkl`, LDtk's "Save levels to separate files" option) are
            resolved relative to it.
        solid_int_grid_values: Identifiers of IntGrid values that should
            count as solid, so `Tilemap.collision_rects` works on an
            IntGrid layer. **There is no default and no guess.** LDtk
            gives an IntGrid value a name and a colour and nothing else,
            so nothing in the file says whether `"Solid"`, `"Wall"` or
            `"1"` blocks movement; inferring it from the name would be
            right for English projects and wrong for the rest.

    Returns:
        One `Tilemap` per level, keyed by the level's identifier, in file
        order. Each carries every tile and IntGrid layer as a
        `TileLayer`, every entity layer as an `ObjectLayer`, and the
        project's tilesets with synthesised gid ranges.

    Raises:
        ValueError: The file is not an LDtk project, a level's layers
            disagree about grid size, or a level references a separate
            file that is not there.
    """
    project_path = Path(path)
    project = _read_json(project_path)
    if "levels" not in project and "worlds" not in project:
        raise ValueError(
            f"{project_path} does not look like an LDtk project: it has "
            f"neither a 'levels' nor a 'worlds' key"
        )

    tilesets, tileset_gids = _build_tilesets(project)
    int_grid_names = _int_grid_definitions(project)
    solid = set(solid_int_grid_values)

    maps: dict[str, Tilemap] = {}
    for level in _levels(project, project_path):
        identifier = level.get("identifier", f"Level_{len(maps)}")
        maps[identifier] = _build_level(
            level, tilesets, tileset_gids, int_grid_names, solid
        )
    return maps


def load_ldtk_level(
    path: str | Path,
    identifier: str,
    *,
    solid_int_grid_values: Iterable[str] = (),
) -> Tilemap:
    """Parse one named level out of an `.ldtk` project.

    Args:
        path: Path to the `.ldtk` file.
        identifier: The level's LDtk identifier.
        solid_int_grid_values: As `load_ldtk`.

    Returns:
        That level's `Tilemap`.

    Raises:
        KeyError: No level of that name, with the available names listed
            -- a typo'd level name is the most likely way to call this
            wrongly, and "KeyError: 'Levl_0'" alone would not help.
    """
    maps = load_ldtk(path, solid_int_grid_values=solid_int_grid_values)
    if identifier not in maps:
        raise KeyError(
            f"no level '{identifier}' in {path}; it has: "
            f"{', '.join(sorted(maps)) or '(none)'}"
        )
    return maps[identifier]


def _read_json(path: Path) -> dict[str, Any]:
    """Read and parse one JSON file.

    Args:
        path: The file to read.

    Returns:
        Its parsed contents.

    Raises:
        ValueError: The file does not hold a JSON object.
    """
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} holds {type(data).__name__}, not a JSON object")
    return data


def _levels(project: Mapping[str, Any], project_path: Path) -> list[dict[str, Any]]:
    """Return every level in the project, loading external ones.

    LDtk's "Save levels to separate files" replaces each level's contents
    with an `externalRelPath`, and multi-world projects move the levels
    under a `worlds` array. Both are ordinary save options rather than
    exotica, and a loader that handled neither would fail on a project
    the moment it grew.

    Args:
        project: The parsed `.ldtk` contents.
        project_path: Used to resolve `externalRelPath`.

    Returns:
        Level dictionaries, worlds flattened in order.

    Raises:
        ValueError: An external level file is missing.
    """
    raw: list[dict[str, Any]] = list(project.get("levels", []))
    for world in project.get("worlds", []):
        raw.extend(world.get("levels", []))

    levels: list[dict[str, Any]] = []
    for level in raw:
        external = level.get("externalRelPath")
        if not external:
            levels.append(level)
            continue
        external_path = (project_path.parent / external).resolve()
        if not external_path.is_file():
            raise ValueError(
                f"level '{level.get('identifier')}' is saved to a separate file "
                f"'{external}', which does not exist at {external_path}"
            )
        levels.append(_read_json(external_path))
    return levels


def _build_tilesets(
    project: Mapping[str, Any],
) -> tuple[list[Tileset], dict[int, int]]:
    """Give every tileset definition a gid range, as Tiled would.

    LDtk addresses a tile as `(tilesetUid, t)` and has no global id
    space. `Tilemap` resolves properties through one, so the ranges are
    laid out here, end to end in definition order -- which is stable for
    a given project file, and that is all a gid needs to be.

    Args:
        project: The parsed `.ldtk` contents.

    Returns:
        The tilesets, and a map from LDtk tileset uid to its `first_gid`.
    """
    definitions = project.get("defs", {}).get("tilesets", [])
    tilesets: list[Tileset] = []
    gids: dict[int, int] = {}

    # gid 0 is EMPTY_GID in `TileLayer`, so the first real tile is 1.
    next_gid = 1
    for definition in definitions:
        columns = int(definition.get("__cWid", 0))
        rows = int(definition.get("__cHei", 0))
        count = columns * rows
        uid = int(definition.get("uid", 0))
        gids[uid] = next_gid
        tilesets.append(
            Tileset(
                name=definition.get("identifier", f"tileset_{uid}"),
                first_gid=next_gid,
                tile_count=count,
                properties=_tile_custom_data(definition),
            )
        )
        next_gid += count
    return tilesets, gids


def _tile_custom_data(definition: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    """Read a tileset definition's per-tile custom data.

    LDtk gives a tile one free-text string rather than a property map.
    In practice people put JSON in it, so a string that parses as a JSON
    **object** is used as the properties directly -- which is what makes
    `{"solid": true}` work with `collision_rects` without a translation
    table. Anything else is kept verbatim under `"data"`, because
    throwing away a comment someone wrote on a tile is worse than
    handing it over unparsed.

    Args:
        definition: One entry from `defs.tilesets`.

    Returns:
        Local tile id to properties.
    """
    result: dict[int, dict[str, Any]] = {}
    for entry in definition.get("customData", []):
        raw = entry.get("data", "")
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            result[int(entry["tileId"])] = parsed
        elif raw:
            result[int(entry["tileId"])] = {"data": raw}
    return result


def _int_grid_definitions(project: Mapping[str, Any]) -> dict[str, dict[int, str]]:
    """Map each IntGrid layer's name to its value names.

    The names live in the layer *definition*, not in the level, so a
    level's `intGridCsv` is a column of bare integers until this is
    joined onto it.

    Args:
        project: The parsed `.ldtk` contents.

    Returns:
        Layer identifier to `{value: identifier}`.
    """
    names: dict[str, dict[int, str]] = {}
    for definition in project.get("defs", {}).get("layers", []):
        if definition.get("type") != "IntGrid":
            continue
        names[definition.get("identifier", "")] = {
            int(value["value"]): value.get("identifier") or str(value["value"])
            for value in definition.get("intGridValues", [])
        }
    return names


def _build_level(
    level: Mapping[str, Any],
    tilesets: list[Tileset],
    tileset_gids: dict[int, int],
    int_grid_names: dict[str, dict[int, str]],
    solid: set[str],
) -> Tilemap:
    """Turn one LDtk level into a `Tilemap`.

    Args:
        level: The level dictionary.
        tilesets: The project's tilesets, already gid-ranged.
        tileset_gids: LDtk tileset uid to `first_gid`.
        int_grid_names: IntGrid layer identifier to value names.
        solid: IntGrid value identifiers that count as solid.

    Returns:
        The level.

    Raises:
        ValueError: The level has no layers with a grid size to take, or
            its layers disagree about one.
    """
    instances = list(level.get("layerInstances") or [])
    tile_size = _grid_size(level, instances)

    # LDtk orders layers front-to-back; reversing makes the iteration
    # order bottom-to-top, matching how Tiled writes a file and how
    # anything drawing them wants to walk them.
    tilemap = Tilemap(tile_size=tile_size, tilesets=tilesets)

    # `tilemap.tilesets` and not a local list: `Tilemap.__init__` copies
    # what it is given, so a synthetic IntGrid tileset appended to the
    # list passed in would never reach the map -- every IntGrid value
    # would then resolve to no tileset and report no properties at all.
    for instance in reversed(instances):
        kind = instance.get("__type")
        name = instance.get("__identifier", "")
        if kind == "Entities":
            tilemap.add_object_layer(_entity_layer(instance))
        elif kind in _TILE_LAYER_TYPES:
            layer, synthetic = _tile_layer(
                instance, tileset_gids, int_grid_names, solid, tilemap.tilesets
            )
            if synthetic is not None:
                tilemap.tilesets.append(synthetic)
            tilemap.add_layer(name, layer)
        else:
            logger.debug(f"ignoring LDtk layer '{name}' of type '{kind}'")
    return tilemap


def _grid_size(level: Mapping[str, Any], instances: list[Mapping[str, Any]]) -> int:
    """Return the one grid size every layer in the level agrees on.

    `Tilemap.tile_size` is a single integer, so a level whose layers use
    different grid sizes cannot be represented -- which LDtk does allow,
    and which would otherwise show up as a collision grid silently
    offset from the art.

    Args:
        level: The level dictionary.
        instances: Its layer instances.

    Returns:
        The grid size in pixels.

    Raises:
        ValueError: The layers disagree, or there are none to ask.
    """
    sizes = {int(i["__gridSize"]) for i in instances if "__gridSize" in i}
    if not sizes:
        raise ValueError(
            f"level '{level.get('identifier')}' has no layers with a grid size; "
            f"Tilemap needs one tile size"
        )
    if len(sizes) > 1:
        raise ValueError(
            f"level '{level.get('identifier')}' mixes grid sizes "
            f"{sorted(sizes)}; Tilemap.tile_size is a single value, so the "
            f"layers would be drawn at different scales on one grid"
        )
    return sizes.pop()


def _tile_layer(
    instance: Mapping[str, Any],
    tileset_gids: dict[int, int],
    int_grid_names: dict[str, dict[int, str]],
    solid: set[str],
    tilesets: list[Tileset],
) -> tuple[TileLayer, Tileset | None]:
    """Build a dense `TileLayer` from a tile or IntGrid layer instance.

    Args:
        instance: The layer instance.
        tileset_gids: LDtk tileset uid to `first_gid`.
        int_grid_names: IntGrid layer identifier to value names.
        solid: IntGrid value identifiers that count as solid.
        tilesets: Existing tilesets, used to place a synthetic one after.

    Returns:
        The layer, and a synthetic `Tileset` when the layer is an IntGrid
        and therefore needs one.
    """
    width = int(instance.get("__cWid", 0))
    height = int(instance.get("__cHei", 0))
    grid = int(instance.get("__gridSize", 1)) or 1
    tiles = [[EMPTY_GID] * width for _ in range(height)]

    int_grid = instance.get("intGridCsv") or []
    if int_grid:
        synthetic = _int_grid_tileset(instance, int_grid_names, solid, tilesets)
        for index, value in enumerate(int_grid):
            if not value:
                continue
            x, y = index % width, index // width
            if 0 <= y < height:
                tiles[y][x] = synthetic.first_gid + int(value)
        return TileLayer(width, height, tiles), synthetic

    first_gid = tileset_gids.get(int(instance.get("__tilesetDefUid") or -1))
    # `gridTiles` for a hand-painted layer, `autoLayerTiles` for a
    # generated one. A layer never has both populated, and reading each
    # separately would mean the caller having to know which it is.
    placed = list(instance.get("gridTiles") or []) + list(
        instance.get("autoLayerTiles") or []
    )
    if placed and first_gid is None:
        logger.warning(
            f"LDtk layer '{instance.get('__identifier')}' places tiles but "
            f"names no tileset; its tiles are dropped"
        )
    elif first_gid is not None:
        for tile in placed:
            px, py = tile.get("px", (0, 0))
            x, y = int(px) // grid, int(py) // grid
            if 0 <= x < width and 0 <= y < height:
                tiles[y][x] = first_gid + int(tile.get("t", 0))
    return TileLayer(width, height, tiles), None


def _int_grid_tileset(
    instance: Mapping[str, Any],
    int_grid_names: dict[str, dict[int, str]],
    solid: set[str],
    tilesets: list[Tileset],
) -> Tileset:
    """Invent a `Tileset` so IntGrid values resolve like any other tile.

    An IntGrid layer has no tileset: it is a grid of small integers whose
    meaning lives in the layer definition. Giving it a gid range of its
    own is what lets `Tilemap.properties_for` and therefore
    `collision_rects` work on it without a second code path.

    `solid` is set from the caller's `solid_int_grid_values`, because
    LDtk records a value's name and colour and nothing that says whether
    it blocks.

    Args:
        instance: The IntGrid layer instance.
        int_grid_names: Layer identifier to value names.
        solid: Value identifiers that count as solid.
        tilesets: Existing tilesets, to place this one after.

    Returns:
        The synthetic tileset.
    """
    name = instance.get("__identifier", "")
    values = int_grid_names.get(name, {})
    highest = max(
        [*values, *(v for v in instance.get("intGridCsv", []) if v)], default=0
    )
    first_gid = max((t.first_gid + t.tile_count for t in tilesets), default=1)

    properties: dict[int, dict[str, Any]] = {}
    for value in range(1, int(highest) + 1):
        identifier = values.get(value, str(value))
        properties[value] = {
            "int_value": value,
            "identifier": identifier,
            "solid": identifier in solid,
        }
    return Tileset(
        name=f"{name} (IntGrid)",
        first_gid=first_gid,
        tile_count=int(highest) + 1,
        properties=properties,
    )


def _entity_layer(instance: Mapping[str, Any]) -> ObjectLayer:
    """Build an `ObjectLayer` from an LDtk entity layer.

    Args:
        instance: The layer instance.

    Returns:
        The layer, entities in file order.
    """
    return ObjectLayer(
        name=instance.get("__identifier", ""),
        objects=tuple(
            _entity(entity, index)
            for index, entity in enumerate(instance.get("entityInstances") or [])
        ),
        visible=bool(instance.get("visible", True)),
    )


def _entity(entity: Mapping[str, Any], index: int) -> MapObject:
    """Build a `MapObject` from one LDtk entity instance.

    LDtk positions an entity by its **pivot**, which an author can put
    anywhere in the sprite, and reports the resulting top-left in `px`.
    `px` is what is used, so `MapObject.x`/`y` mean the same thing they
    do for a Tiled object rather than something pivot-dependent.

    Args:
        entity: The entity instance.
        index: Position in the layer, used as an id when LDtk's `iid` is
            a string uuid rather than a number.

    Returns:
        The object.
    """
    px = entity.get("px", (0, 0))
    width = float(entity.get("width", 0))
    height = float(entity.get("height", 0))
    return MapObject(
        id=index,
        name=entity.get("__identifier", ""),
        type=entity.get("__identifier", ""),
        x=float(px[0]),
        y=float(px[1]),
        width=width,
        height=height,
        shape=ObjectShape.POINT if not width and not height else ObjectShape.RECTANGLE,
        properties=_fields(entity),
    )


def _fields(entity: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten an entity's `fieldInstances` into a property map.

    LDtk has already resolved each field to a typed value in
    `__value` -- an `Int` arrives as an int, a `Point` as
    `{"cx": .., "cy": ..}` -- so there is nothing to convert, unlike
    Tiled's string attributes.

    Args:
        entity: The entity instance.

    Returns:
        Field identifier to value.
    """
    return {
        field["__identifier"]: field.get("__value")
        for field in entity.get("fieldInstances") or []
        if "__identifier" in field
    }
