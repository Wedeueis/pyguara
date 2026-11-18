"""`Vector2` as plain Python, for the Rust class to be held to.

Each method is the former Python implementation -- the engine's own
`Vector2` methods and the `pymunk.Vec2d` ones it inherited -- with the
same operations in the same order. Two deliberate differences:

- Components are floats, as they are in Rust; the former class kept ints.
- Squares are `x * x`. pymunk spelled some as `x ** 2`, which differs from
  it in the last bit for some inputs and which Rust cannot reproduce;
  `length` already used `x * x`, and now every square does.
"""

from __future__ import annotations

import math
from typing import Any


def _pair(other: Any) -> tuple[float, float]:
    """Read an operand as the Rust `Pair` does."""
    if isinstance(other, ReferenceVector2):
        return other.x, other.y
    if isinstance(other, tuple | list) and len(other) == 2:
        return float(other[0]), float(other[1])
    return float(other.x), float(other.y)


class ReferenceVector2:
    """The former `Vector2`, on floats."""

    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        """Store both components as floats."""
        self.x = float(x)
        self.y = float(y)

    def __repr__(self) -> str:
        """Spell it as the Rust class does."""
        return f"Vector2({self.x!r}, {self.y!r})"

    def __add__(self, other: Any) -> ReferenceVector2:
        ox, oy = _pair(other)
        return ReferenceVector2(self.x + ox, self.y + oy)

    def __radd__(self, other: Any) -> ReferenceVector2:
        ox, oy = _pair(other)
        return ReferenceVector2(ox + self.x, oy + self.y)

    def __sub__(self, other: Any) -> ReferenceVector2:
        ox, oy = _pair(other)
        return ReferenceVector2(self.x - ox, self.y - oy)

    def __rsub__(self, other: Any) -> ReferenceVector2:
        ox, oy = _pair(other)
        return ReferenceVector2(ox - self.x, oy - self.y)

    def __mul__(self, other: float) -> ReferenceVector2:
        return ReferenceVector2(self.x * other, self.y * other)

    def __rmul__(self, other: float) -> ReferenceVector2:
        return ReferenceVector2(self.x * other, self.y * other)

    def __truediv__(self, other: float) -> ReferenceVector2:
        return ReferenceVector2(self.x / other, self.y / other)

    def __floordiv__(self, other: float) -> ReferenceVector2:
        return ReferenceVector2(self.x // other, self.y // other)

    def __neg__(self) -> ReferenceVector2:
        return ReferenceVector2(-self.x, -self.y)

    def __pos__(self) -> ReferenceVector2:
        return ReferenceVector2(self.x, self.y)

    def __abs__(self) -> float:
        return self.length

    def __bool__(self) -> bool:
        return self.x != 0 or self.y != 0

    @property
    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y)

    @property
    def magnitude(self) -> float:
        return self.length

    @property
    def length_squared(self) -> float:
        return self.x * self.x + self.y * self.y

    @property
    def sqr_magnitude(self) -> float:
        return self.x * self.x + self.y * self.y

    @property
    def angle(self) -> float:
        return math.atan2(self.y, self.x)

    @property
    def angle_degrees(self) -> float:
        return math.degrees(self.angle)

    @property
    def polar_tuple(self) -> tuple[float, float]:
        return self.length, self.angle

    @property
    def int_tuple(self) -> tuple[int, int]:
        return round(self.x), round(self.y)

    def dot(self, other: Any) -> float:
        ox, oy = _pair(other)
        return self.x * ox + self.y * oy

    def cross(self, other: Any) -> float:
        ox, oy = _pair(other)
        return self.x * oy - self.y * ox

    def get_distance_squared(self, other: Any) -> float:
        ox, oy = _pair(other)
        dx = self.x - ox
        dy = self.y - oy
        return dx * dx + dy * dy

    def get_distance(self, other: Any) -> float:
        return math.sqrt(self.get_distance_squared(other))

    def distance_to(self, other: Any) -> float:
        return self.get_distance(other)

    def get_angle_between(self, other: Any) -> float:
        ox, oy = _pair(other)
        cross = self.x * oy - self.y * ox
        dot = self.x * ox + self.y * oy
        return math.atan2(cross, dot)

    def get_angle_degrees_between(self, other: Any) -> float:
        return math.degrees(self.get_angle_between(other))

    def projection(self, other: Any) -> ReferenceVector2:
        ox, oy = _pair(other)
        other_length_sqrd = ox * ox + oy * oy
        if other_length_sqrd == 0.0:
            return ReferenceVector2(0.0, 0.0)
        new_length = self.dot(other) / other_length_sqrd
        return ReferenceVector2(ox * new_length, oy * new_length)

    def reject(self, other: Any) -> ReferenceVector2:
        projected = self.projection(other)
        return ReferenceVector2(self.x - projected.x, self.y - projected.y)

    def convert_to_basis(self, x_vector: Any, y_vector: Any) -> ReferenceVector2:
        xx, xy = _pair(x_vector)
        yx, yy = _pair(y_vector)
        x = self.dot(x_vector) / (xx * xx + xy * xy)
        y = self.dot(y_vector) / (yx * yx + yy * yy)
        return ReferenceVector2(x, y)

    def cpvrotate(self, other: Any) -> ReferenceVector2:
        ox, oy = _pair(other)
        return ReferenceVector2(self.x * ox - self.y * oy, self.x * oy + self.y * ox)

    def cpvunrotate(self, other: Any) -> ReferenceVector2:
        ox, oy = _pair(other)
        return ReferenceVector2(self.x * ox + self.y * oy, self.y * ox - self.x * oy)

    def normalize(self) -> ReferenceVector2:
        length = self.length
        if length != 0:
            return ReferenceVector2(self.x / length, self.y / length)
        return ReferenceVector2(0.0, 0.0)

    def normalized(self) -> ReferenceVector2:
        return self.normalize()

    def normalized_and_length(self) -> tuple[ReferenceVector2, float]:
        length = self.length
        if length != 0:
            return ReferenceVector2(self.x / length, self.y / length), length
        return ReferenceVector2(0.0, 0.0), 0.0

    def perpendicular(self) -> ReferenceVector2:
        return ReferenceVector2(-self.y, self.x)

    def perpendicular_normal(self) -> ReferenceVector2:
        length = self.length
        if length != 0:
            return ReferenceVector2(-self.y / length, self.x / length)
        return ReferenceVector2(self.x, self.y)

    def rotated(self, angle_radians: float) -> ReferenceVector2:
        cos = math.cos(angle_radians)
        sin = math.sin(angle_radians)
        x = self.x * cos - self.y * sin
        y = self.x * sin + self.y * cos
        return ReferenceVector2(x, y)

    def rotated_degrees(self, angle_degrees: float) -> ReferenceVector2:
        return self.rotated(math.radians(angle_degrees))

    def rotate_degrees(self, angle_degrees: float) -> ReferenceVector2:
        return self.rotated(math.radians(angle_degrees))

    def scale_to_length(self, length: float) -> ReferenceVector2:
        old_length = self.length
        return ReferenceVector2(
            self.x * length / old_length, self.y * length / old_length
        )

    def clamp_magnitude(self, max_length: float) -> ReferenceVector2:
        if max_length <= 0:
            return ReferenceVector2(0.0, 0.0)
        length = self.length
        if length <= max_length or length == 0:
            return ReferenceVector2(self.x, self.y)
        scale = max_length / length
        return ReferenceVector2(self.x * scale, self.y * scale)

    def reflect(self, normal: Any) -> ReferenceVector2:
        nx0, ny0 = _pair(normal)
        length = math.sqrt(nx0 * nx0 + ny0 * ny0)
        if length == 0:
            return ReferenceVector2(self.x, self.y)
        nx, ny = nx0 / length, ny0 / length
        dot = self.x * nx + self.y * ny
        return ReferenceVector2(self.x - 2.0 * dot * nx, self.y - 2.0 * dot * ny)

    def lerp(self, target: Any, t: float) -> ReferenceVector2:
        tx, ty = _pair(target)
        return ReferenceVector2(self.x + (tx - self.x) * t, self.y + (ty - self.y) * t)

    def interpolate_to(self, other: Any, range: float) -> ReferenceVector2:  # noqa: A002
        return self.lerp(other, range)

    def move_towards(self, target: Any, max_distance: float) -> ReferenceVector2:
        tx, ty = _pair(target)
        if max_distance <= 0:
            return ReferenceVector2(self.x, self.y)
        delta = ReferenceVector2(tx - self.x, ty - self.y)
        distance = delta.length
        if distance <= max_distance or distance == 0:
            return ReferenceVector2(tx, ty)
        scale = max_distance / distance
        return ReferenceVector2(self.x + delta.x * scale, self.y + delta.y * scale)

    def snapped(self, grid: Any) -> ReferenceVector2:
        if isinstance(grid, ReferenceVector2):
            step_x, step_y = grid.x, grid.y
        else:
            step_x, step_y = float(grid), float(grid)
        return ReferenceVector2(
            self.x if step_x == 0 else round(self.x / step_x) * step_x,
            self.y if step_y == 0 else round(self.y / step_y) * step_y,
        )

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    def to_int_tuple(self) -> tuple[int, int]:
        return (int(self.x), int(self.y))

    @staticmethod
    def from_polar(length: float, angle: float) -> ReferenceVector2:
        return ReferenceVector2(math.cos(angle) * length, math.sin(angle) * length)

    @staticmethod
    def from_angle_degrees(degrees: float, length: float = 1.0) -> ReferenceVector2:
        radians = math.radians(degrees)
        return ReferenceVector2(math.cos(radians) * length, math.sin(radians) * length)
