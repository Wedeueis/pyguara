"""Foundational value types for the PyGuara engine.

`Vector2`, `Color` and `Rect` are the primitives every other subsystem shares.

`Vector2` subclasses `pymunk.Vec2d` for C-optimised math and to pass into the
physics backend without conversion. `Color` and `Rect` are plain dataclasses
with no backend dependency -- neither pygame nor ModernGL is imported here.
Conversion to a backend's native types happens only at that backend's
boundary, in `graphics/backends/pygame/conversions.py`.

Axis convention:
    Y increases downwards, matching SDL, pygame and the engine's own default
    gravity (`PhysicsConfig.gravity_y` is positive for a platformer). "Up" is
    therefore negative Y. Every direction helper in this module and in
    `Transform` follows that convention.
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from typing import Any, ClassVar

import pymunk

Coordinate = tuple[float, float] | list[float] | pymunk.Vec2d
"""Anything accepted where a 2D coordinate is expected."""

_CHANNEL_MIN = 0
_CHANNEL_MAX = 255


class Vector2(pymunk.Vec2d):
    """An immutable 2D vector for positions, velocities and directions.

    Subclasses `pymunk.Vec2d` for C-optimised math, overriding the operators
    and transforms so they return `Vector2` rather than `Vec2d`, and renaming
    Pymunk-specific spellings so they do not leak into game code.

    Being a `NamedTuple` subclass, a `Vector2` is immutable and hashable:
    every method here returns a new vector rather than mutating in place.

    Attributes:
        x: The X component.
        y: The Y component, increasing downwards.
    """

    @property
    def magnitude(self) -> float:
        """The length of the vector."""
        return float(self.length)

    @property
    def sqr_magnitude(self) -> float:
        """The squared length of the vector.

        Avoids the square root in `magnitude`, so prefer it when comparing
        distances rather than needing a real one.
        """
        return float(self.x * self.x + self.y * self.y)

    def __add__(self, other: Any) -> Vector2:
        """Add another vector or coordinate pair."""
        if hasattr(other, "x") and hasattr(other, "y"):
            return Vector2(self.x + other.x, self.y + other.y)
        v = super().__add__(other)
        return Vector2(v.x, v.y)

    def __sub__(self, other: Any) -> Vector2:
        """Subtract another vector or coordinate pair."""
        if hasattr(other, "x") and hasattr(other, "y"):
            return Vector2(self.x - other.x, self.y - other.y)
        v = super().__sub__(other)
        return Vector2(v.x, v.y)

    def __mul__(self, other: float) -> Vector2:  # type: ignore[override]
        """Scale by a scalar."""
        # Overrides tuple.__mul__, which would repeat the tuple for an int.
        v = super().__mul__(other)
        return Vector2(v.x, v.y)

    def __rmul__(self, other: float) -> Vector2:  # type: ignore[override]
        """Scale by a scalar, with the scalar on the left."""
        v = super().__rmul__(other)
        return Vector2(v.x, v.y)

    def __truediv__(self, other: float) -> Vector2:
        """Divide by a scalar.

        Raises:
            ZeroDivisionError: If `other` is zero.
        """
        v = super().__truediv__(other)
        return Vector2(v.x, v.y)

    def __neg__(self) -> Vector2:
        """Return the vector pointing the opposite way."""
        return Vector2(-self.x, -self.y)

    def dot(self, other: Any) -> float:
        """Return the dot product with another vector or coordinate pair.

        Args:
            other: Any object with `x` and `y`, or a coordinate pair. Typed
                loosely to stay substitutable for `pymunk.Vec2d.dot`.

        Returns:
            The scalar dot product.
        """
        return float(super().dot(other))

    def cross(self, other: Any) -> float:
        """Return the 2D cross product (determinant) with another vector.

        Args:
            other: Any object with `x` and `y`, or a coordinate pair.

        Returns:
            The scalar cross product.
        """
        return float(super().cross(other))

    def normalize(self) -> Vector2:
        """Return a unit vector in the same direction.

        Returns:
            The normalised vector, or a zero vector if this one has no length.
        """
        v = super().normalized()
        return Vector2(v.x, v.y)

    def rotated(self, angle_radians: float) -> Vector2:
        """Return this vector rotated by an angle in **radians**.

        Args:
            angle_radians: Rotation angle in radians.

        Returns:
            The rotated vector.
        """
        v = super().rotated(angle_radians)
        return Vector2(v.x, v.y)

    def rotate_degrees(self, angle_degrees: float) -> Vector2:
        """Return this vector rotated by an angle in **degrees**.

        Named explicitly rather than `rotate`: a bare `rotate`/`rotated` pair
        differing only in angle unit is impossible to read correctly at a call
        site, and `Transform.rotate()` takes radians.

        Args:
            angle_degrees: Rotation angle in degrees.

        Returns:
            The rotated vector.
        """
        return self.rotated(math.radians(angle_degrees))

    def distance_to(self, other: Vector2) -> float:
        """Return the distance to another point.

        Args:
            other: The target point.

        Returns:
            The straight-line distance.
        """
        return float(self.get_distance(other))

    def lerp(self, target: Vector2, t: float) -> Vector2:
        """Linearly interpolate towards a target.

        `t` is not clamped, so values outside 0..1 extrapolate.

        Args:
            target: The end point.
            t: Interpolation factor, 0.0 at self and 1.0 at target.

        Returns:
            The interpolated point.
        """
        return Vector2(
            self.x + (target.x - self.x) * t,
            self.y + (target.y - self.y) * t,
        )

    def to_tuple(self) -> tuple[float, float]:
        """Return the components as a plain float tuple."""
        return (self.x, self.y)

    def to_int_tuple(self) -> tuple[int, int]:
        """Return the components truncated to a plain int tuple.

        Truncates towards zero, matching how pygame treats float coordinates.
        """
        return (int(self.x), int(self.y))

    @staticmethod
    def zero() -> Vector2:
        """Return `(0, 0)`."""
        return Vector2(0, 0)

    @staticmethod
    def one() -> Vector2:
        """Return `(1, 1)`."""
        return Vector2(1, 1)

    @staticmethod
    def up() -> Vector2:
        """Return `(0, -1)`. Y increases downwards, so up is negative."""
        return Vector2(0, -1)

    @staticmethod
    def down() -> Vector2:
        """Return `(0, 1)`. Y increases downwards, so down is positive."""
        return Vector2(0, 1)

    @staticmethod
    def left() -> Vector2:
        """Return `(-1, 0)`."""
        return Vector2(-1, 0)

    @staticmethod
    def right() -> Vector2:
        """Return `(1, 0)`."""
        return Vector2(1, 0)


@dataclass(slots=True)
class Color:
    """An RGBA colour, one byte per channel.

    A backend-agnostic value type. Channels are coerced to `int` and clamped
    to 0-255 on construction, so colour arithmetic that overshoots -- a fade,
    a brightness multiplier, an out-of-range HSV conversion -- saturates
    instead of handing a backend a value it cannot represent.

    Attributes:
        r: Red channel, 0-255.
        g: Green channel, 0-255.
        b: Blue channel, 0-255.
        a: Alpha channel, 0-255. Defaults to fully opaque.
    """

    r: int
    g: int
    b: int
    a: int = 255

    # Assigned below the class body: a dataclass cannot reference its own
    # not-yet-defined type from inside it. ClassVar keeps them off the
    # generated __init__.
    WHITE: ClassVar[Color]
    BLACK: ClassVar[Color]
    RED: ClassVar[Color]
    GREEN: ClassVar[Color]
    BLUE: ClassVar[Color]
    YELLOW: ClassVar[Color]
    CYAN: ClassVar[Color]
    MAGENTA: ClassVar[Color]
    TRANSPARENT: ClassVar[Color]

    def __post_init__(self) -> None:
        """Coerce every channel to an int within 0-255."""
        self.r = _clamp_channel(self.r)
        self.g = _clamp_channel(self.g)
        self.b = _clamp_channel(self.b)
        self.a = _clamp_channel(self.a)

    @staticmethod
    def from_hex(hex_str: str) -> Color:
        """Parse a colour from a hex string.

        Args:
            hex_str: A string such as `"#FF00AA"`, `"0xFF00AA"`, or with an
                alpha pair, `"#FF00AAFF"`.

        Returns:
            The parsed colour.

        Raises:
            ValueError: If the string is not a valid 6- or 8-digit hex colour.
        """
        s = hex_str.strip()
        if s.startswith("#"):
            s = s[1:]
        elif s.startswith(("0x", "0X")):
            s = s[2:]

        try:
            if len(s) == 6:
                return Color(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
            if len(s) == 8:
                return Color(
                    int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16)
                )
        except ValueError:
            raise ValueError(f"Invalid hex color string: {hex_str!r}") from None
        raise ValueError(f"Invalid hex color string: {hex_str!r}")

    def to_hex(self, include_alpha: bool = False) -> str:
        """Format the colour as a `#RRGGBB` string.

        Args:
            include_alpha: Append the alpha pair, giving `#RRGGBBAA`.

        Returns:
            The hex string, upper case.
        """
        base = f"#{self.r:02X}{self.g:02X}{self.b:02X}"
        return f"{base}{self.a:02X}" if include_alpha else base

    @property
    def normalized(self) -> tuple[float, float, float, float]:
        """The channels as floats in 0.0-1.0, for shaders and GL backends."""
        return (self.r / 255.0, self.g / 255.0, self.b / 255.0, self.a / 255.0)

    def lerp(self, target: Color, t: float) -> Color:
        """Linearly interpolate towards another colour.

        Args:
            target: The destination colour.
            t: Interpolation factor, clamped to 0.0-1.0.

        Returns:
            The blended colour.
        """
        t = max(0.0, min(1.0, t))
        return Color(
            round(self.r + (target.r - self.r) * t),
            round(self.g + (target.g - self.g) * t),
            round(self.b + (target.b - self.b) * t),
            round(self.a + (target.a - self.a) * t),
        )

    def to_hsv(self) -> tuple[float, float, float]:
        """Convert to HSV, discarding alpha.

        Returns:
            `(hue in 0-360, saturation in 0-1, value in 0-1)`.
        """
        h, s, v = colorsys.rgb_to_hsv(self.r / 255.0, self.g / 255.0, self.b / 255.0)
        return (h * 360.0, s, v)

    @staticmethod
    def from_hsv(hue: float, saturation: float, value: float, a: int = 255) -> Color:
        """Build a colour from HSV components.

        Args:
            hue: Hue in degrees; wraps at 360.
            saturation: Saturation in 0.0-1.0.
            value: Brightness in 0.0-1.0.
            a: Alpha channel, 0-255.

        Returns:
            The resulting colour, with channels clamped to 0-255.
        """
        r, g, b = colorsys.hsv_to_rgb((hue % 360.0) / 360.0, saturation, value)
        return Color(round(r * 255), round(g * 255), round(b * 255), a)

    def __getitem__(self, index: int) -> int:
        """Return a channel by index, ordered r, g, b, a."""
        return (self.r, self.g, self.b, self.a)[index]

    def __len__(self) -> int:
        """Return 4, the number of channels."""
        return 4


def _clamp_channel(value: float) -> int:
    """Coerce a channel value to an int within 0-255.

    Args:
        value: The raw channel value.

    Returns:
        The truncated, clamped channel.
    """
    return max(_CHANNEL_MIN, min(_CHANNEL_MAX, int(value)))


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
    """An axis-aligned rectangle in integer pixel coordinates.

    A backend-agnostic value type. Mutable, matching `pygame.Rect`, because
    the UI layout engine assigns to `rect.x` and friends in place.

    Attributes:
        x: Left position.
        y: Top position.
        width: Width in pixels.
        height: Height in pixels.
    """

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        """Truncate the fields to int, as `pygame.Rect` always did.

        Several call sites build a Rect straight from `Vector2` components
        without an explicit cast and rely on this.
        """
        self.x = int(self.x)
        self.y = int(self.y)
        self.width = int(self.width)
        self.height = int(self.height)

    @property
    def left(self) -> int:
        """The left edge; an alias for `x`."""
        return self.x

    @property
    def top(self) -> int:
        """The top edge; an alias for `y`."""
        return self.y

    @property
    def right(self) -> int:
        """The right edge, `x + width`."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """The bottom edge, `y + height`."""
        return self.y + self.height

    @property
    def centerx(self) -> int:
        """The horizontal centre."""
        return self.x + self.width // 2

    @property
    def centery(self) -> int:
        """The vertical centre."""
        return self.y + self.height // 2

    @property
    def position(self) -> Vector2:
        """The top-left corner as a vector."""
        return Vector2(self.x, self.y)

    @property
    def center_vec(self) -> Vector2:
        """The centre point as a vector."""
        return Vector2(self.centerx, self.centery)

    @property
    def size(self) -> tuple[int, int]:
        """The `(width, height)` pair."""
        return (self.width, self.height)

    def contains_point(self, point: Vector2) -> bool:
        """Report whether a point falls inside this rectangle.

        Right and bottom edges are exclusive, matching
        `pygame.Rect.collidepoint`.

        Args:
            point: The point to test.

        Returns:
            True if the point is inside.
        """
        return self.left <= point.x < self.right and self.top <= point.y < self.bottom

    def colliderect(self, other: Rect) -> bool:
        """Report whether this rectangle overlaps another.

        Touching edges do not count as an overlap.

        Args:
            other: The rectangle to test against.

        Returns:
            True if the two rectangles overlap.
        """
        return (
            self.left < other.right
            and self.right > other.left
            and self.top < other.bottom
            and self.bottom > other.top
        )

    def contains(self, other: Rect) -> bool:
        """Report whether another rectangle lies entirely within this one.

        Args:
            other: The candidate rectangle.

        Returns:
            True if `other` is fully inside, edges inclusive.
        """
        return (
            self.left <= other.left
            and self.top <= other.top
            and self.right >= other.right
            and self.bottom >= other.bottom
        )

    def inflate(self, dx: int, dy: int) -> Rect:
        """Return a copy grown by `dx`/`dy`, keeping the same centre.

        Negative deltas shrink. The offset truncates towards zero rather than
        flooring, so odd negative deltas land where `pygame.Rect.inflate`
        puts them.

        Args:
            dx: Amount to grow the width by, split across both sides.
            dy: Amount to grow the height by, split across top and bottom.

        Returns:
            The resized rectangle.
        """
        return Rect(
            self.x - int(dx / 2),
            self.y - int(dy / 2),
            self.width + dx,
            self.height + dy,
        )
