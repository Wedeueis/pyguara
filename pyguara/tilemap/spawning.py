"""Turn a map's objects into entities, through prefabs.

The loaders stop at data, so `pyguara/tilemap` stays a grid of integers that can
be tested without a world. This module is the one place the map meets the ECS:
`load_tmx` says an object has `type` "Bat", and the game says which prefab that
means.

```python
map_ = load_tmx("levels/cave.tmx")
spawned = spawn_objects(
    map_,
    factory,
    {"Bat": bat_prefab, "Door": door_trigger_prefab},
    ignore_types={"CameraBounds"},  # read through `map_.objects(...)` instead
)
```

In Tiled, a custom property named `Component.field` overrides that field on the
spawned entity (`Health.max = 30`, or deeper, `Transform.scale.x = 2`). Any other
property is the game's own: it stays on `SpawnedObject.source.properties`.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.types import PrefabData
from pyguara.tilemap.objects import MapObject, ObjectShape
from pyguara.tilemap.tilemap import Tilemap

_SHAPED_COMPONENTS = ("Collider", "TriggerVolume")
"""Components whose geometry is taken from the object's own shape.

Named rather than imported, because a prefab already refers to its components by
name and `pyguara.physics` should not become a dependency of a map.
"""


class MapSpawnError(ValueError):
    """A map asks for something the spawner cannot honour."""


@dataclass(frozen=True, slots=True)
class SpawnedObject:
    """One entity a map object became.

    Attributes:
        entity: The entity.
        source: The object it came from, for a caller wiring things up by
            `name` or reading a property that was not a component override.
    """

    entity: Entity
    source: MapObject


def spawn_objects(
    tilemap: Tilemap,
    factory: PrefabFactory,
    prefabs: Mapping[str, PrefabData],
    *,
    layers: Iterable[str] | None = None,
    ignore_types: Collection[str] = (),
    offset: Vector2 | None = None,
    include_hidden: bool = False,
) -> list[SpawnedObject]:
    """Spawn an entity for every typed object on a map.

    **All or nothing.** Every object is checked before the first is spawned, so
    a map with a mistake raises with the whole list of what is wrong, rather than
    leaving half a level in the world.

    An object with no `type` names nothing, so it is skipped. An object whose
    `type` has no prefab raises: a silently unspawned enemy is a bug nobody finds
    until they notice the room is empty. Name a type in `ignore_types` to say it
    is handled elsewhere.

    The entity's `Transform` is placed at the object's centre, not its `(x, y)`,
    because a collider is centred on its transform. A sized rectangle or a circle
    also sets the shape of any `Collider` or `TriggerVolume` in the prefab, unless
    a `Component.field` property states it outright. A polygon or polyline cannot
    be a collider, because `Collider.dimensions` cannot carry vertices, and asking
    for that raises rather than falling back to a bounding box that collides where
    nothing is drawn.

    Args:
        tilemap: The map to read.
        factory: Builds the entities, in the world it was created for.
        prefabs: What each `type` spawns.
        layers: Object layers to read, or None for all of them. A name the map
            does not have raises.
        ignore_types: Types the game handles itself, such as camera bounds.
        offset: Added to every position, for a room placed inside a larger world.
        include_hidden: Also spawn objects and layers hidden in the editor.

    Returns:
        What was spawned, in layer-then-file order.

    Raises:
        MapSpawnError: Listing every problem found, with nothing spawned.
    """
    objects = _selected_objects(tilemap, layers, include_hidden)
    known_types = set(ignore_types)

    planned: list[tuple[MapObject, PrefabData, dict[str, dict[str, Any]]]] = []
    problems: list[str] = []
    for obj in objects:
        if not obj.type or obj.type in known_types:
            continue
        prefab = prefabs.get(obj.type)
        if prefab is None:
            problems.append(f"{_describe(obj)} has no prefab for type '{obj.type}'")
            continue
        try:
            planned.append((obj, prefab, _overrides(obj, prefab, factory, offset)))
        except MapSpawnError as error:
            problems.append(str(error))

    if problems:
        listing = "\n  ".join(problems)
        raise MapSpawnError(
            f"Cannot spawn this map's objects ({len(problems)} problems, nothing "
            f"spawned):\n  {listing}"
        )

    return [
        SpawnedObject(factory.create(prefab, overrides=overrides), obj)
        for obj, prefab, overrides in planned
    ]


def _selected_objects(
    tilemap: Tilemap, layers: Iterable[str] | None, include_hidden: bool
) -> list[MapObject]:
    """Return the objects to consider, in layer-then-file order."""
    if layers is None:
        selected = list(tilemap.object_layers.values())
    else:
        names = list(layers)
        missing = [name for name in names if name not in tilemap.object_layers]
        if missing:
            raise MapSpawnError(
                f"This map has no object layer(s) {missing}; it has "
                f"{sorted(tilemap.object_layers)}."
            )
        selected = [tilemap.object_layers[name] for name in names]

    return [
        obj
        for layer in selected
        if include_hidden or layer.visible
        for obj in layer.objects
        if include_hidden or obj.visible
    ]


def _describe(obj: MapObject) -> str:
    """Name an object the way an author would find it in the editor."""
    name = f" '{obj.name}'" if obj.name else ""
    return f"Object {obj.id}{name}"


def _overrides(
    obj: MapObject,
    prefab: PrefabData,
    factory: PrefabFactory,
    offset: Vector2 | None,
) -> dict[str, dict[str, Any]]:
    """Work out the component data one object adds to its prefab."""
    x, y = obj.center
    if offset is not None:
        x, y = x + offset.x, y + offset.y
    transform: dict[str, Any] = {"position": {"x": x, "y": y}}
    if obj.rotation:
        transform["rotation"] = math.radians(obj.rotation)
    overrides: dict[str, dict[str, Any]] = {"Transform": transform}

    components = factory.resolve_components(prefab)
    shaped = [name for name in _SHAPED_COMPONENTS if name in components]
    if shaped:
        shape = _collider_shape(obj)
        if shape is not None:
            for name in shaped:
                overrides[name] = dict(shape)

    for key, value in obj.properties.items():
        if "." not in key:
            continue
        component, *path = key.split(".")
        if not factory.knows_component(component):
            raise MapSpawnError(
                f"{_describe(obj)} sets property '{key}', and no component "
                f"'{component}' is registered"
            )
        target = overrides.setdefault(component, {})
        for part in path[:-1]:
            target = target.setdefault(part, {})
        target[path[-1]] = value

    return overrides


def _collider_shape(obj: MapObject) -> dict[str, Any] | None:
    """Return a collider's shape fields for an object, if it has a shape.

    Returns:
        `shape_type` and `dimensions`, or None for an object with no extent, whose
        collider keeps what the prefab says.

    Raises:
        MapSpawnError: For a shape a `Collider` cannot express.
    """
    if obj.shape in (ObjectShape.POLYGON, ObjectShape.POLYLINE):
        raise MapSpawnError(
            f"{_describe(obj)} is a {obj.shape.name.lower()} on a prefab with a "
            "collider, and a collider cannot carry vertices. Use a rectangle or a "
            "circle, or give it a prefab without one"
        )
    if not obj.width or not obj.height:
        return None
    if obj.shape is ObjectShape.RECTANGLE:
        return {"shape_type": "BOX", "dimensions": [obj.width, obj.height]}
    if obj.shape is ObjectShape.ELLIPSE:
        if not math.isclose(obj.width, obj.height):
            raise MapSpawnError(
                f"{_describe(obj)} is an ellipse of {obj.width}x{obj.height} on a "
                "prefab with a collider, and only a circle can collide. Make its "
                "width and height equal"
            )
        return {"shape_type": "CIRCLE", "dimensions": [obj.width / 2.0]}
    return None
