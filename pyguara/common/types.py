"""
Common data structures and mathematical primitives for the pyGuara engine.

This module provides the foundational types (Vector2, Color, Rect) used throughout
the engine. It leverages inheritance from low-level libraries (Pymunk, Pygame)
to ensure zero-cost performance for heavy mathematical operations while defining
a standardized, engine-specific API surface.
"""

from __future__ import annotations
import math
from typing import Union, Tuple, List, Any

import pymunk
import pygame

# Type alias for coordinates to allow flexibility in inputs
Coordinate = Union[Tuple[float, float], List[float], pymunk.Vec2d]


class Vector2(pymunk.Vec2d):
    """
    A 2D column vector used for positions, velocities, and physics.

    Inherits from `pymunk.Vec2d` to utilize C-optimized math operations essential
    for the physics engine. It standardizes method names to avoid leaking
    Pymunk-specific naming (like `cpvrotate`) into the game logic.

    Attributes:
        x (float): The X component.
        y (float): The Y component.
    """

    @property
    def magnitude(self) -> float:
        """
        Get the length (magnitude) of the vector.

        Returns:
            float: The length of the vector.
        """
        return float(self.length)

    @property
    def sqr_magnitude(self) -> float:
        """
        Get the squared length of the vector.

        Faster than magnitude() as it avoids the square root calculation.
        Useful for distance comparisons.

        Returns:
            float: The squared length.
        """
        return float(self.x * self.x + self.y * self.y)

    # --- Operator Overloads (Fixing Return Types) ---

    def __add__(self, other: Any) -> Vector2:
        """Vector addition."""
        if hasattr(other, "x") and hasattr(other, "y"):
            return Vector2(self.x + other.x, self.y + other.y)
        v = super().__add__(other)
        return Vector2(v.x, v.y)

    def __sub__(self, other: Any) -> Vector2:
        """Vector subtraction."""
        if hasattr(other, "x") and hasattr(other, "y"):
            return Vector2(self.x - other.x, self.y - other.y)
        v = super().__sub__(other)
        return Vector2(v.x, v.y)

    def __mul__(self, other: float) -> Vector2:  # type: ignore[override]
        """Scalar multiplication (Vector * float)."""
        # Ignored override because Tuple expects int (repetition), we want float (math)
        v = super().__mul__(other)
        return Vector2(v.x, v.y)

    def __rmul__(self, other: float) -> Vector2:  # type: ignore[override]
        """Reverse scalar multiplication (float * Vector)."""
        # Ignored override because Tuple expects int (repetition), we want float (math)
        v = super().__rmul__(other)
        return Vector2(v.x, v.y)

    def __truediv__(self, other: float) -> Vector2:
        """Scalar division (Vector / float)."""
        v = super().__truediv__(other)
        return Vector2(v.x, v.y)

    def __neg__(self) -> Vector2:
        """Negation (-Vector)."""
        return Vector2(-self.x, -self.y)

    def dot(self, other: Any) -> float:
        """
        Dot product.

        Accepts Any (tuples or Vectors) to satisfy LSP against pymunk.Vec2d.
        """
        return float(super().dot(other))

    def cross(self, other: Any) -> float:
        """
        Cross product / Determinant.

        Accepts Any (tuples or Vectors) to satisfy LSP against pymunk.Vec2d.
        """
        return float(super().cross(other))

    def normalize(self) -> Vector2:
        """
        Return a new vector with the same direction but length of 1.0.

        Returns:
            Vector2: The normalized vector.
        """
        # We cast the result back to Vector2 to maintain type consistency
        v = super().normalized()
        return Vector2(v.x, v.y)

    def rotated(self, angle_radians: float) -> Vector2:
        """
        Return a new vector rotated by the given angle in radians.

        Overrides pymunk.Vec2d.rotated to ensure Vector2 return type.

        Args:
            angle_radians (float): Rotation angle in radians.

        Returns:
            Vector2: The rotated vector.
        """
        v = super().rotated(angle_radians)
        return Vector2(v.x, v.y)

    def rotate(self, angle_degrees: float) -> Vector2:
        """
        Return a new vector rotated by the given angle.

        Args:
            angle_degrees (float): The angle to rotate by, in degrees.

        Returns:
            Vector2: The rotated vector.
        """
        return self.rotated(math.radians(angle_degrees))

    def distance_to(self, other: Vector2) -> float:
        """
        Calculate the distance between this vector and another.

        Args:
            other (Vector2): The target vector.

        Returns:
            float: The distance between the points.
        """
        return float(self.get_distance(other))

    def lerp(self, target: Vector2, t: float) -> Vector2:
        """
        Linearly interpolate between this vector and the target.

        Args:
            target (Vector2): The end vector.
            t (float): The interpolation factor (0.0 to 1.0).

        Returns:
            Vector2: A new vector representing the interpolated position.
        """
        # Helper implementation since Pymunk's interpolate can be obscure
        x = self.x + (target.x - self.x) * t
        y = self.y + (target.y - self.y) * t
        return Vector2(x, y)

    def to_tuple(self) -> Tuple[float, float]:
        """
        Convert the vector to a standard Python float tuple.

        Returns:
            Tuple[float, float]: (x, y)
        """
        return (self.x, self.y)

    def to_int_tuple(self) -> Tuple[int, int]:
        """
        Convert the vector to an integer tuple.

        Essential for pixel-perfect rendering calls in Pygame which
        do not accept floats.

        Returns:
            Tuple[int, int]: (int(x), int(y))
        """
        return (int(self.x), int(self.y))

    @staticmethod
    def zero() -> Vector2:
        """Return a Vector2(0, 0)."""
        return Vector2(0, 0)

    @staticmethod
    def one() -> Vector2:
        """Return a Vector2(1, 1)."""
        return Vector2(1, 1)

    @staticmethod
    def up() -> Vector2:
        """Return a Vector2(0, -1). Note: Y is down in Pygame/SDL."""
        return Vector2(0, -1)

    @staticmethod
    def right() -> Vector2:
        """Return a Vector2(1, 0)."""
        return Vector2(1, 0)


class Color(pygame.Color):
    """
    A container for RGBA color values.

    Inherits from `pygame.Color` to allow direct usage in rendering functions
    and bitwise operations.
    """

    @staticmethod
    def from_hex(hex_str: str) -> Color:
        """
        Create a Color object from a generic hex string.

        Args:
            hex_str (str): A string like "#FF00AA" or "0xFF00AA".

        Returns:
            Color: The parsed color object.
        """
        return Color(hex_str)

    @property
    def normalized(self) -> Tuple[float, float, float, float]:  # type: ignore[override]
        """
        Get the RGBA values normalized to the 0.0 - 1.0 range.

        Useful for integration with shaders or OpenGL backends.

        Returns:
            Tuple[float, float, float, float]: (r, g, b, a) as floats.
        """
        return (self.r / 255.0, self.g / 255.0, self.b / 255.0, self.a / 255.0)

    def lerp(self, target: Any, t: float) -> Color:
        """
        Linearly interpolate this color towards a target color.

        Args:
            target (Color): The destination color.
            t (float): Interpolation factor (0.0 to 1.0).

        Returns:
            Color: The blended color.
        """
        # Use Pygame's built-in gamma-corrected lerp if available,
        # or simple arithmetic. We wrap the return to ensure it's our Type.
        return Color(super().lerp(target, t))


class Rect(pygame.Rect):
    """
    A 2D Rectangle defined by position (x, y) and size (width, height).

    Inherits from `pygame.Rect` for optimized collision checks and
    rendering utility.

    Attributes:
        x (int): Left position.
        y (int): Top position.
        width (int): Rectangle width.
        height (int): Rectangle height.
    """

    @property
    def position(self) -> Vector2:
        """
        Get the top-left position as a Vector2.

        Returns:
            Vector2: The (x, y) coordinates.
        """
        return Vector2(self.x, self.y)

    @property
    def center_vec(self) -> Vector2:
        """
        Get the center point as a Vector2.

        Returns:
            Vector2: The (center_x, center_y) coordinates.
        """
        return Vector2(self.centerx, self.centery)

    def contains_point(self, point: Vector2) -> bool:
        """
        Check if a vector point is inside this rectangle.

        Args:
            point (Vector2): The point to check.

        Returns:
            bool: True if inside, False otherwise.
        """
        return bool(self.collidepoint(point.x, point.y))
