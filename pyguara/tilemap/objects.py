"""Map objects: the things placed on a map that are not tiles.

Spawn points, trigger regions, camera bounds, patrol routes, collision
shapes drawn by hand. Tiled calls them objects and puts them in an
`<objectgroup>`; `load_tmx` ignored the element entirely, so a map with
spawn points loaded "successfully" and lost them -- which is worse than
the two encodings it *refused*, because nothing told the author.

**These are data, not entities.** Turning an object into an entity means
knowing which prefab a `type` names, which component a property maps to,
and which entity manager to put it in -- none of which belongs in a
module whose other half is a grid of integers. `pyguara/tilemap` imports
nothing from `prefabs`, `physics` or `ecs`, and keeping it that way is
what lets `load_tmx` be tested with no world at all. The spawning half is
tracked separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["MapObject", "ObjectLayer", "ObjectShape"]


class ObjectShape(Enum):
    """What geometry an object describes.

    Tiled encodes the shape by which child element an `<object>` has --
    none for a rectangle, `<point/>`, `<ellipse/>`, `<polygon>` or
    `<polyline>` -- plus a `gid` attribute for a tile stamped as an
    object. Flattened into one field here, because "which of these five
    is it" is the first thing every consumer asks.
    """

    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    POINT = "point"
    POLYGON = "polygon"
    POLYLINE = "polyline"
    TILE = "tile"


@dataclass(frozen=True)
class MapObject:
    """One object placed on a map.

    Attributes:
        id: The object's id, unique within the map.
        name: The author's name for it, or `""`.
        type: Tiled's `type` (called `class` since Tiled 1.9; both are
            read into this field). Usually what a game switches on to
            decide what to spawn.
        x: Left edge in pixels, except for a tile object, where Tiled
            uses the **bottom** left -- see `shape`.
        y: Top edge in pixels, with the same exception.
        width: Width in pixels; 0 for a point or an unsized polygon.
        height: Height in pixels; 0 likewise.
        rotation: Clockwise rotation in degrees.
        gid: The tile this object stamps, for `TILE` objects; None
            otherwise. Flip flags are already masked off.
        visible: Tiled's per-object visibility toggle.
        points: Vertices for `POLYGON` and `POLYLINE`, **relative to
            `(x, y)`** as Tiled stores them, not absolute.
        properties: Custom properties, with Tiled's declared types
            applied -- an `int` property is an `int` here.
    """

    id: int
    name: str = ""
    type: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    rotation: float = 0.0
    gid: int | None = None
    visible: bool = True
    shape: ObjectShape = ObjectShape.RECTANGLE
    points: tuple[tuple[float, float], ...] = ()
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> tuple[float, float]:
        """The centre of the object's bounding box, in map pixels.

        A point object has no extent, so its centre is its position.
        """
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def absolute_points(self) -> tuple[tuple[float, float], ...]:
        """Return `points` translated into map coordinates.

        Tiled stores a polygon's vertices relative to the object's
        position, which is convenient for editing and wrong for anything
        that wants to draw or collide with it.
        """
        return tuple((self.x + px, self.y + py) for px, py in self.points)


@dataclass(frozen=True)
class ObjectLayer:
    """A named group of map objects, mirroring Tiled's `<objectgroup>`.

    Attributes:
        name: The layer's name.
        objects: The objects in it, in file order.
        visible: Tiled's per-layer visibility toggle.
        properties: The layer's own custom properties.
    """

    name: str
    objects: tuple[MapObject, ...] = ()
    visible: bool = True
    properties: dict[str, Any] = field(default_factory=dict)

    def by_type(self, type_name: str) -> tuple[MapObject, ...]:
        """Return the objects whose `type` matches, in file order.

        Args:
            type_name: The Tiled type/class to match, exactly.
        """
        return tuple(obj for obj in self.objects if obj.type == type_name)

    def by_name(self, name: str) -> MapObject | None:
        """Return the first object with this name, or None.

        Args:
            name: The object name to match, exactly.
        """
        for obj in self.objects:
            if obj.name == name:
                return obj
        return None
