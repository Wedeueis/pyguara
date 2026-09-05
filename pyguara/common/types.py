"""
Common data structures and mathematical primitives for the pyGuara engine.

This module provides the foundational types (Vector2, Color, Rect) used throughout
the engine. `Vector2` inherits from `pymunk.Vec2d` for C-optimized physics math.
`Color` and `Rect` are plain, backend-agnostic dataclasses -- neither pygame nor
ModernGL is a dependency of this module. Conversion to a backend's native types
(e.g. `pygame.Color`/`pygame.Rect`) happens only at that backend's boundary.
"""

from __future__ import annotations
import colorsys
import math
from dataclasses import dataclass
from typing import ClassVar, Union, Tuple, List, Any

import pymunk

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


@dataclass(slots=True)
class Color:
    """
    A container for RGBA color values (0-255 per channel).

    A plain, backend-agnostic value type -- no longer a `pygame.Color`
    subclass (wayfinder ticket 31), so ModernGL never has to touch pygame to
    represent a color. Only the pygame backend ever constructs a real
    `pygame.Color`, via `graphics/backends/pygame/conversions.py`.

    Attributes:
        r (int): Red channel, 0-255.
        g (int): Green channel, 0-255.
        b (int): Blue channel, 0-255.
        a (int): Alpha channel, 0-255. Defaults to fully opaque.
    """

    r: int
    g: int
    b: int
    a: int = 255

    # Common named colors -- assigned after the class body below, since a
    # dataclass can't reference its own not-yet-defined type in its class
    # body. Declared here (ClassVar, so the dataclass doesn't treat them as
    # instance fields) purely for parity with Rect's added surface; no
    # in-repo caller uses them yet.
    WHITE: ClassVar[Color]
    BLACK: ClassVar[Color]
    RED: ClassVar[Color]
    GREEN: ClassVar[Color]
    BLUE: ClassVar[Color]
    YELLOW: ClassVar[Color]
    CYAN: ClassVar[Color]
    MAGENTA: ClassVar[Color]
    TRANSPARENT: ClassVar[Color]

    @staticmethod
    def from_hex(hex_str: str) -> Color:
        """
        Create a Color object from a hex string.

        Args:
            hex_str (str): A string like "#FF00AA", "0xFF00AA", or with an
                optional alpha pair ("#FF00AAFF").

        Returns:
            Color: The parsed color object.

        Raises:
            ValueError: If the string isn't a valid 6 or 8-digit hex color.
        """
        s = hex_str.strip()
        if s.startswith("#"):
            s = s[1:]
        elif s.startswith(("0x", "0X")):
            s = s[2:]

        if len(s) == 6:
            return Color(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        if len(s) == 8:
            return Color(
                int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16)
            )
        raise ValueError(f"Invalid hex color string: {hex_str!r}")

    @property
    def normalized(self) -> Tuple[float, float, float, float]:
        """
        Get the RGBA values normalized to the 0.0 - 1.0 range.

        Useful for integration with shaders or OpenGL backends.

        Returns:
            Tuple[float, float, float, float]: (r, g, b, a) as floats.
        """
        return (self.r / 255.0, self.g / 255.0, self.b / 255.0, self.a / 255.0)

    def lerp(self, target: Color, t: float) -> Color:
        """
        Linearly interpolate this color towards a target color.

        Args:
            target (Color): The destination color.
            t (float): Interpolation factor (0.0 to 1.0).

        Returns:
            Color: The blended color.
        """
        t = max(0.0, min(1.0, t))
        return Color(
            round(self.r + (target.r - self.r) * t),
            round(self.g + (target.g - self.g) * t),
            round(self.b + (target.b - self.b) * t),
            round(self.a + (target.a - self.a) * t),
        )

    def to_hsv(self) -> Tuple[float, float, float]:
        """
        Convert to HSV.

        Returns:
            Tuple[float, float, float]: (hue in 0-360, saturation 0-1, value 0-1).
        """
        h, s, v = colorsys.rgb_to_hsv(self.r / 255.0, self.g / 255.0, self.b / 255.0)
        return (h * 360.0, s, v)

    @staticmethod
    def from_hsv(hue: float, saturation: float, value: float, a: int = 255) -> Color:
        """
        Create a Color from HSV components.

        Args:
            hue (float): Hue in degrees (0-360).
            saturation (float): Saturation (0.0-1.0).
            value (float): Value/brightness (0.0-1.0).
            a (int): Alpha channel, 0-255.

        Returns:
            Color: The resulting RGB color.
        """
        r, g, b = colorsys.hsv_to_rgb((hue % 360.0) / 360.0, saturation, value)
        return Color(round(r * 255), round(g * 255), round(b * 255), a)

    def __getitem__(self, index: int) -> int:
        """Support tuple-like indexing (color[0] == r, ..., color[3] == a)."""
        return (self.r, self.g, self.b, self.a)[index]

    def __len__(self) -> int:
        """Return 4, the number of channels (r, g, b, a)."""
        return 4


Color.WHITE = Color(255, 255, 255)
Color.BLACK = Color(0, 0, 0)
Color.RED = Color(255, 0, 0)
Color.GREEN = Color(0, 255, 0)
Color.BLUE = Color(0, 0, 255)
Color.YELLOW = Color(255, 255, 0)
Color.CYAN = Color(0, 255, 255)
Color.MAGENTA = Color(255, 0, 255)
Color.TRANSPARENT = Color(0, 0, 0, 0)


@dataclass(slots=True)
class Rect:
    """
    A 2D Rectangle defined by position (x, y) and size (width, height).

    A plain, backend-agnostic value type -- no longer a `pygame.Rect`
    subclass (wayfinder ticket 31). Only the pygame backend ever constructs
    a real `pygame.Rect`, via `graphics/backends/pygame/conversions.py`.
    Mutable, matching pygame.Rect's own semantics -- in-place assignment
    (`rect.x = 5`) stays legal, which the UI layout engine relies on.

    Attributes:
        x (int): Left position.
        y (int): Top position.
        width (int): Rectangle width.
        height (int): Rectangle height.
    """

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        """Truncate to int, matching pygame.Rect's own coordinate semantics.

        Several call sites construct a Rect directly from Vector2
        components (floats) without an explicit `int()` cast, relying on
        this truncation exactly as pygame.Rect always performed it.
        """
        self.x = int(self.x)
        self.y = int(self.y)
        self.width = int(self.width)
        self.height = int(self.height)

    @property
    def left(self) -> int:
        """Get the left edge (alias for x)."""
        return self.x

    @property
    def top(self) -> int:
        """Get the top edge (alias for y)."""
        return self.y

    @property
    def right(self) -> int:
        """Get the right edge (x + width)."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Get the bottom edge (y + height)."""
        return self.y + self.height

    @property
    def centerx(self) -> int:
        """Get the horizontal center."""
        return self.x + self.width // 2

    @property
    def centery(self) -> int:
        """Get the vertical center."""
        return self.y + self.height // 2

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

        Right/bottom edges are exclusive, matching pygame.Rect.collidepoint.

        Args:
            point (Vector2): The point to check.

        Returns:
            bool: True if inside, False otherwise.
        """
        return self.left <= point.x < self.right and self.top <= point.y < self.bottom

    def colliderect(self, other: Rect) -> bool:
        """
        Check if this rectangle overlaps another.

        Args:
            other (Rect): The other rectangle.

        Returns:
            bool: True if the two rectangles overlap at all.
        """
        return (
            self.left < other.right
            and self.right > other.left
            and self.top < other.bottom
            and self.bottom > other.top
        )

    def contains(self, other: Rect) -> bool:
        """
        Check if another rectangle is entirely within this one.

        Args:
            other (Rect): The candidate rectangle.

        Returns:
            bool: True if `other` is completely inside this rectangle.
        """
        return (
            self.left <= other.left
            and self.top <= other.top
            and self.right >= other.right
            and self.bottom >= other.bottom
        )

    def inflate(self, dx: int, dy: int) -> Rect:
        """
        Return a new Rect grown (or shrunk) by dx/dy, keeping the same center.

        Args:
            dx (int): Amount to grow the width by (split evenly on each side).
            dy (int): Amount to grow the height by (split evenly top/bottom).

        Returns:
            Rect: The new, resized rectangle.
        """
        return Rect(
            self.x - dx // 2, self.y - dy // 2, self.width + dx, self.height + dy
        )
