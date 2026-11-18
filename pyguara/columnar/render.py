"""Sprites drawn from columns, in one native call per frame.

`ColumnarSprite` and `ColumnarTransform` hold the fields `Scene.render`
reads from `Sprite` and `Transform`, as columns. `ColumnarSpriteRenderer`
pushes every visible sprite into a `NativeGpu` by the same rules and the
same arithmetic as the object path, without a `RenderCommand` or a
`RenderBatch` in between.

A texture is the id `GpuFrame.image()` returns, and a colour is four
0-255 channels. Atlas regions, materials and flips are not columns; a
sprite needing any of them stays in the object ECS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from pyguara import native
from pyguara.columnar.world import ColumnarWorld
from pyguara.common.types import Rect, Vector2
from pyguara.graphics.components.camera import Camera2D

_SPRITE_COLUMNS: Final = (
    "texture",
    "layer",
    "z_index",
    "visible",
    "y_sort",
    "sort_offset",
    "sort_group",
    "position.x",
    "position.y",
    "rotation",
    "scale.x",
    "scale.y",
    "red",
    "green",
    "blue",
    "alpha",
)
_TRANSFORM_COLUMNS: Final = (
    "position.x",
    "position.y",
    "previous_position.x",
    "previous_position.y",
    "interpolate",
)


@dataclass(slots=True)
class ColumnarTransform:
    """Where an entity is, as `Scene.render` reads a `Transform`.

    Attributes:
        position: The world position.
        previous_position: The position one fixed step ago.
        interpolate: Draw at `previous_position.lerp(position, alpha)`.
    """

    position: Vector2 = field(default_factory=Vector2.zero)
    previous_position: Vector2 = field(default_factory=Vector2.zero)
    interpolate: bool = False


@dataclass(slots=True)
class ColumnarSprite:
    """A sprite's drawing state, as `Scene.render` reads a `Sprite`.

    Attributes:
        texture: The GPU texture id from `GpuFrame.image()`.
        layer: Drawn above every lower layer.
        z_index: Depth within the layer, unless `y_sort`.
        visible: Skipped when False.
        y_sort: Use the drawn world Y plus `sort_offset` as the depth.
        sort_offset: Added to the world Y of a y-sorted sprite.
        sort_group: Compared after the layer and before the depth.
        position: The offset from the transform, or the world position
            of an entity with no transform.
        rotation: Degrees.
        scale: Per-axis factors.
        red: Tint channel, 0-255.
        green: Tint channel, 0-255.
        blue: Tint channel, 0-255.
        alpha: Opacity, 0-255.
    """

    texture: int
    layer: int = 0
    z_index: int = 0
    visible: bool = True
    y_sort: bool = False
    sort_offset: float = 0.0
    sort_group: int = 0
    position: Vector2 = field(default_factory=Vector2.zero)
    rotation: float = 0.0
    scale: Vector2 = field(default_factory=lambda: Vector2(1.0, 1.0))
    red: int = 255
    green: int = 255
    blue: int = 255
    alpha: int = 255


class ColumnarSpriteRenderer:
    """Pushes a world's `ColumnarSprite`s into a `NativeGpu` each frame."""

    def __init__(self, world: ColumnarWorld) -> None:
        """Bind to a world's sprite and transform columns.

        Args:
            world: The world to draw. Both component types are registered
                in it if they are not already.
        """
        self._world = world
        sprite = world.register(ColumnarSprite)
        transform = world.register(ColumnarTransform)
        self._extraction = native.require_extension(
            "pyguara.columnar"
        ).SpriteExtraction(
            world._tables[ColumnarSprite],
            [sprite.column_names.index(name) for name in _SPRITE_COLUMNS],
            (
                world._tables[ColumnarTransform],
                [transform.column_names.index(name) for name in _TRANSFORM_COLUMNS],
            ),
        )

    def draw(
        self, gpu: Any, camera: Camera2D, viewport: Rect, alpha: float = 1.0
    ) -> int:
        """Push every visible sprite's instance into `gpu`, in draw order.

        Args:
            gpu: The `NativeGpu` building the frame.
            camera: Supplies the zoom and the world-to-screen offset.
            viewport: The region being drawn into.
            alpha: How far between fixed steps this frame is, for
                interpolated transforms.

        Returns:
            How many sprites were pushed.

        Raises:
            ValueError: For a NaN depth, a texture id below zero, or a
                colour channel outside 0-255. Nothing is pushed.
            KeyError: For a texture id `gpu` has not uploaded. Nothing is
                pushed.
        """
        offset = camera.screen_offset(viewport)
        count: int = self._extraction.draw(
            self._world._native, gpu, camera.zoom, offset.x, offset.y, alpha
        )
        return count
