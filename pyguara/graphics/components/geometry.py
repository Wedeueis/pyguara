"""Procedural geometric shapes that render like any other sprite.

Shapes rasterise themselves once into a `Texture`, cached until a property
changes, so they take part in Z-sorting and batching exactly as a loaded sprite
does. The alternative -- immediate-mode draw calls inside the render loop --
cannot be batched and defeats the pipeline.

Rasterisation produces plain RGBA bytes and hands them to a `TextureFactory`,
so a shape works on whichever backend is running. This module imports no
backend of its own.
"""

from __future__ import annotations

import math
from typing import Any

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import TextureFactory
from pyguara.graphics.types import Layer
from pyguara.resources.types import Texture

_BYTES_PER_PIXEL = 4


class Geometry:
    """Base for procedural shapes, satisfying the `Renderable` protocol.

    Attributes:
        rotation: Rotation in degrees.
        scale: Scale factor, `(1, 1)` for natural size.
        material: Optional material; None uses the default sprite material.
    """

    def __init__(
        self,
        texture_factory: TextureFactory,
        layer: int = Layer.WORLD,
        z_index: float = 0.0,
    ) -> None:
        """Initialise the shared shape state.

        Args:
            texture_factory: Builds the backend's texture from raw RGBA bytes.
                Resolve it from the DI container -- in a scene,
                `self.container.get(TextureFactory)`.
            layer: Sorting layer.
            z_index: Depth key within the layer.
        """
        self._texture_factory = texture_factory
        self._layer = layer
        self._z_index = z_index
        self._position = Vector2.zero()
        self._texture: Texture | None = None
        self.rotation: float = 0.0
        self.scale: Vector2 = Vector2(1, 1)
        self._dirty = True
        self.material: Any = None

    @property
    def position(self) -> Vector2:
        """World-space position."""
        return self._position

    @position.setter
    def position(self, value: Vector2) -> None:
        """Set the world-space position.

        Args:
            value: The new position.
        """
        self._position = value

    @property
    def layer(self) -> int:
        """Sorting layer."""
        return self._layer

    @property
    def z_index(self) -> float:
        """Depth key within the layer."""
        return self._z_index

    @property
    def texture(self) -> Texture:
        """The rasterised shape, regenerated only when something changed.

        Returns:
            The cached texture.
        """
        if self._dirty or self._texture is None:
            self._texture = self._build_texture()
            self._dirty = False
        return self._texture

    def _build_texture(self) -> Texture:
        """Rasterise this shape into a backend texture.

        Returns:
            The new texture.

        Raises:
            NotImplementedError: Always; subclasses must implement it.
        """
        raise NotImplementedError("Subclasses must implement texture generation.")


class Box(Geometry):
    """A solid rectangle, for whiteboxing levels, triggers and backgrounds."""

    def __init__(
        self,
        width: int,
        height: int,
        color: Color,
        texture_factory: TextureFactory,
        layer: int = Layer.WORLD,
        z_index: float = 0.0,
    ) -> None:
        """Initialise a rectangle.

        Args:
            width: Width in pixels.
            height: Height in pixels.
            color: Fill colour.
            texture_factory: Builds the backend's texture.
            layer: Sorting layer.
            z_index: Depth key within the layer.
        """
        super().__init__(texture_factory, layer, z_index)
        self._width = width
        self._height = height
        self._color = color

    def resize(self, width: int, height: int) -> None:
        """Change the dimensions, regenerating on next draw.

        Args:
            width: New width in pixels.
            height: New height in pixels.
        """
        self._width = width
        self._height = height
        self._dirty = True

    def set_color(self, color: Color) -> None:
        """Change the fill colour, regenerating on next draw.

        Args:
            color: The new fill colour.
        """
        self._color = color
        self._dirty = True

    def _build_texture(self) -> Texture:
        """Rasterise a solid rectangle.

        Returns:
            The texture.
        """
        pixel = bytes((self._color.r, self._color.g, self._color.b, self._color.a))
        data = pixel * (self._width * self._height)
        return self._texture_factory.create_from_bytes(
            f"gen_box_{id(self)}", data, self._width, self._height
        )


class Circle(Geometry):
    """A solid circle, for particles, rounded UI and placeholders."""

    def __init__(
        self,
        radius: int,
        color: Color,
        texture_factory: TextureFactory,
        layer: int = Layer.WORLD,
        z_index: float = 0.0,
    ) -> None:
        """Initialise a circle.

        Args:
            radius: Radius in pixels.
            color: Fill colour.
            texture_factory: Builds the backend's texture.
            layer: Sorting layer.
            z_index: Depth key within the layer.
        """
        super().__init__(texture_factory, layer, z_index)
        self._radius = radius
        self._color = color

    @property
    def radius(self) -> int:
        """Radius in pixels."""
        return self._radius

    @radius.setter
    def radius(self, value: int) -> None:
        """Change the radius, regenerating on next draw.

        Args:
            value: The new radius in pixels.
        """
        self._radius = value
        self._dirty = True

    def set_color(self, color: Color) -> None:
        """Change the fill colour, regenerating on next draw.

        Args:
            color: The new fill colour.
        """
        self._color = color
        self._dirty = True

    def _build_texture(self) -> Texture:
        """Rasterise a solid circle onto a transparent square.

        Filled by row spans rather than per-pixel testing: each row's half-width
        follows from the circle equation, so the work is proportional to the
        diameter rather than its square.

        Returns:
            The texture.
        """
        diameter = self._radius * 2
        row_bytes = diameter * _BYTES_PER_PIXEL
        data = bytearray(row_bytes * diameter)
        pixel = bytes((self._color.r, self._color.g, self._color.b, self._color.a))

        for y in range(diameter):
            # Row centre offset from the circle centre, sampled mid-pixel.
            dy = y - self._radius + 0.5
            span = self._radius * self._radius - dy * dy
            if span <= 0:
                continue
            half_width = math.sqrt(span)
            start = max(0, int(self._radius - half_width))
            stop = min(diameter, int(math.ceil(self._radius + half_width)))
            if stop <= start:
                continue
            offset = y * row_bytes + start * _BYTES_PER_PIXEL
            data[offset : offset + (stop - start) * _BYTES_PER_PIXEL] = pixel * (
                stop - start
            )

        return self._texture_factory.create_from_bytes(
            f"gen_circle_{id(self)}", bytes(data), diameter, diameter
        )
