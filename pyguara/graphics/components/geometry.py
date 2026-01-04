"""
Procedural Geometric Components.

This module provides components that generate their own textures programmatically
(Circles, Rectangles, etc.) rather than loading them from disk.

Architecture Note:
    To maintain compatibility with the standard `RenderPipeline`, these shapes
    lazy-render themselves into a Texture (cached) upon initialization or
    resize. This allows them to be Z-Sorted and Batched just like any other
    Sprite, avoiding the performance penalty of immediate-mode drawing commands
    (like `pygame.draw.circle`) inside the render loop.
"""

from __future__ import annotations
from typing import Optional
import pygame

from pyguara.common.types import Vector2, Color
from pyguara.resources.types import Texture
from pyguara.graphics.types import Layer
from pyguara.graphics.backends.pygame.types import (
    PygameTexture,
)  # Concrete implementation


class Geometry:
    """Base class for procedural shapes implementing the Renderable protocol."""

    def __init__(self, layer: int = Layer.WORLD, z_index: float = 0.0):
        """Initialize the base geometry."""
        self._layer = layer
        self._z_index = z_index
        self._position = Vector2.zero()
        self._texture: Optional[Texture] = None
        self.rotation: float = 0.0
        self.scale: Vector2 = Vector2(1, 1)
        self._dirty = True  # Flag to regenerate texture if properties change

    @property
    def position(self) -> Vector2:
        """Get world position."""
        return self._position

    @position.setter
    def position(self, value: Vector2) -> None:
        self._position = value

    @property
    def layer(self) -> int:
        """Get sorting layer."""
        return self._layer

    @property
    def z_index(self) -> float:
        """Get vertical sort index."""
        return self._z_index

    @property
    def texture(self) -> Texture:
        """Lazy-loads the texture. If the shape is 'dirty', it regenerates."""
        if self._dirty or self._texture is None:
            self._generate_texture()
            self._dirty = False
        assert self._texture is not None
        return self._texture

    def _generate_texture(self) -> None:
        raise NotImplementedError("Subclasses must implement texture generation.")


class Box(Geometry):
    """
    A solid colored rectangle.

    Useful for prototyping (whiteboxing) levels, triggers, or UI backgrounds.
    """

    def __init__(
        self,
        width: int,
        height: int,
        color: Color,
        layer: int = Layer.WORLD,
        z_index: float = 0.0,
    ):
        """Initialize a box primitive."""
        super().__init__(layer, z_index)
        self._width = width
        self._height = height
        self._color = color

    def resize(self, width: int, height: int) -> None:
        """Update dimensions and force texture regeneration."""
        self._width = width
        self._height = height
        self._dirty = True

    def set_color(self, color: Color) -> None:
        """Update color and force texture regeneration."""
        self._color = color
        self._dirty = True

    def _generate_texture(self) -> None:
        # Create a new Surface
        surface = pygame.Surface((self._width, self._height), flags=pygame.SRCALPHA)

        # Fill with color
        # Note: Using standard pygame fill is faster than drawing a rect
        surface.fill(self._color)

        # Wrap in our engine's Texture type
        # We use a dummy path identifier for generated content
        self._texture = PygameTexture(f"gen_box_{id(self)}", surface)


class Circle(Geometry):
    """
    A solid colored circle.

    Useful for particles, rounded UI elements, or character placeholders.
    """

    def __init__(
        self, radius: int, color: Color, layer: int = Layer.WORLD, z_index: float = 0.0
    ):
        """Initialize a circle primitive."""
        super().__init__(layer, z_index)
        self._radius = radius
        self._color = color

    @property
    def radius(self) -> int:
        """Get the circle radius."""
        return self._radius

    @radius.setter
    def radius(self, value: int) -> None:
        self._radius = value
        self._dirty = True

    def _generate_texture(self) -> None:
        diameter = self._radius * 2
        surface = pygame.Surface((diameter, diameter), flags=pygame.SRCALPHA)

        # Draw the circle on the transparent surface
        center = (self._radius, self._radius)
        pygame.draw.circle(surface, self._color, center, self._radius)

        self._texture = PygameTexture(f"gen_circle_{id(self)}", surface)
