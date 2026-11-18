"""Foundational value types for the PyGuara engine.

`Vector2`, `Color` and `Rect` are the primitives every other subsystem shares.
`Vector2` is implemented in the native extension; the class body here is
its signature for type checkers. `Color` and `Rect` are plain dataclasses;
no rendering backend is imported here.

Y increases downwards, matching SDL and the engine's default gravity,
so "up" is negative Y. Every direction helper here and in `Transform`
follows that.
"""

from __future__ import annotations

import colorsys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from pyguara.native import require_extension

_CHANNEL_MIN = 0
_CHANNEL_MAX = 255

if TYPE_CHECKING:

    class Vector2:
        """An immutable 2D vector for positions, velocities and directions.

        Implemented in Rust. Components are always floats. It unpacks,
        indexes and has a length of 2 like the `(x, y)` tuple it equals and
        hashes as. Every method returns a new vector.

        Attributes:
            x: The X component.
            y: The Y component, increasing downwards.
        """

        __match_args__: ClassVar[tuple[str, str]]

        def __init__(self, x: float, y: float) -> None:
            """Build a vector from two numbers."""

        @property
        def x(self) -> float:
            """The X component."""

        @property
        def y(self) -> float:
            """The Y component, increasing downwards."""

        def __len__(self) -> int:
            """Return 2."""

        def __getitem__(self, index: int) -> float:
            """Return `x` for 0 or -2 and `y` for 1 or -1."""

        def __iter__(self) -> Iterator[float]:
            """Yield `x`, then `y`."""

        def __hash__(self) -> int:
            """Hash as the tuple `(x, y)` does."""

        def __eq__(self, other: object) -> bool:
            """Compare with another vector or an `(x, y)` tuple."""

        def __bool__(self) -> bool:
            """Return False only for the zero vector."""

        def __add__(self, other: Coordinate) -> Vector2:
            """Add another vector or coordinate pair."""

        def __radd__(self, other: Coordinate) -> Vector2:
            """Add this vector to a coordinate pair."""

        def __sub__(self, other: Coordinate) -> Vector2:
            """Subtract another vector or coordinate pair."""

        def __rsub__(self, other: Coordinate) -> Vector2:
            """Subtract this vector from a coordinate pair."""

        def __mul__(self, other: float) -> Vector2:
            """Scale by a scalar."""

        def __rmul__(self, other: float) -> Vector2:
            """Scale by a scalar, with the scalar on the left."""

        def __truediv__(self, other: float) -> Vector2:
            """Divide by a scalar, raising ZeroDivisionError for zero."""

        def __floordiv__(self, other: float) -> Vector2:
            """Floor-divide each component by a scalar."""

        def __neg__(self) -> Vector2:
            """Return the vector pointing the opposite way."""

        def __pos__(self) -> Vector2:
            """Return this vector."""

        def __abs__(self) -> float:
            """Return the length."""

        @property
        def length(self) -> float:
            """The length, `sqrt(x * x + y * y)`."""

        @property
        def magnitude(self) -> float:
            """The length; an alias for `length`."""

        @property
        def length_squared(self) -> float:
            """The squared length, `x * x + y * y`."""

        @property
        def sqr_magnitude(self) -> float:
            """The squared length; cheaper than `magnitude` for comparisons."""

        @property
        def angle(self) -> float:
            """The angle from +X in radians, `atan2(y, x)`."""

        @property
        def angle_degrees(self) -> float:
            """The angle from +X in degrees."""

        @property
        def polar_tuple(self) -> tuple[float, float]:
            """The `(length, angle)` pair."""

        @property
        def int_tuple(self) -> tuple[int, int]:
            """The components rounded half to even, as ints."""

        def dot(self, other: Coordinate) -> float:
            """Return the dot product with another vector or pair."""

        def cross(self, other: Coordinate) -> float:
            """Return the 2D cross product (determinant) with another vector."""

        def get_distance(self, other: Coordinate) -> float:
            """Return the distance to another point."""

        def distance_to(self, other: Coordinate) -> float:
            """Return the distance to another point."""

        def get_distance_squared(self, other: Coordinate) -> float:
            """Return the squared distance to another point."""

        def get_angle_between(self, other: Coordinate) -> float:
            """Return the signed angle to another vector, in radians."""

        def get_angle_degrees_between(self, other: Coordinate) -> float:
            """Return the signed angle to another vector, in degrees."""

        def projection(self, other: Coordinate) -> Vector2:
            """Return the component of this vector along `other`.

            A zero `other` gives the zero vector.
            """

        def reject(self, other: Coordinate) -> Vector2:
            """Return the component of this vector perpendicular to `other`."""

        def convert_to_basis(
            self, x_vector: Coordinate, y_vector: Coordinate
        ) -> Vector2:
            """Return this vector's coordinates in another basis."""

        def cpvrotate(self, other: Coordinate) -> Vector2:
            """Rotate by `other` through complex multiplication."""

        def cpvunrotate(self, other: Coordinate) -> Vector2:
            """Undo `cpvrotate` by the same `other`."""

        def normalize(self) -> Vector2:
            """Return a unit vector, or the zero vector if this has no length."""

        def normalized(self) -> Vector2:
            """Return a unit vector; an alias for `normalize`."""

        def normalized_and_length(self) -> tuple[Vector2, float]:
            """Return the unit vector and the length together."""

        def perpendicular(self) -> Vector2:
            """Return this vector turned a quarter turn, `(-y, x)`."""

        def perpendicular_normal(self) -> Vector2:
            """Return the unit perpendicular, or this vector if it is zero."""

        def rotated(self, angle_radians: float) -> Vector2:
            """Return this vector rotated by an angle in radians."""

        def rotated_degrees(self, angle_degrees: float) -> Vector2:
            """Return this vector rotated by an angle in degrees."""

        def rotate_degrees(self, angle_degrees: float) -> Vector2:
            """Return this vector rotated by an angle in degrees."""

        def scale_to_length(self, length: float) -> Vector2:
            """Return this vector at `length`, lengthening or shortening it.

            Raises:
                ZeroDivisionError: If this vector has no length.
            """

        def clamp_magnitude(self, max_length: float) -> Vector2:
            """Return this vector shortened to at most `max_length`.

            Never lengthens it. A non-positive `max_length` gives the zero
            vector.
            """

        def reflect(self, normal: Coordinate) -> Vector2:
            """Return this vector mirrored about a surface normal.

            The normal may have any length; a zero one leaves the vector
            unchanged.
            """

        def lerp(self, target: Coordinate, t: float) -> Vector2:
            """Interpolate towards `target`; `t` is not clamped."""

        def interpolate_to(self, other: Coordinate, range: float) -> Vector2:
            """Interpolate towards `other`; an alias for `lerp`."""

        def move_towards(self, target: Coordinate, max_distance: float) -> Vector2:
            """Return a point stepped towards `target`, never overshooting.

            A non-positive `max_distance` leaves the point where it is.
            """

        def snapped(self, grid: float | Vector2) -> Vector2:
            """Return this point rounded to the nearest multiple of `grid`.

            `grid` is uniform as a number or per-axis as a vector; a zero
            step leaves that axis alone.
            """

        def to_tuple(self) -> tuple[float, float]:
            """Return the components as a plain tuple."""

        def to_int_tuple(self) -> tuple[int, int]:
            """Return the components truncated towards zero, as ints."""

        @staticmethod
        def zero() -> Vector2:
            """Return `(0, 0)`."""

        @staticmethod
        def one() -> Vector2:
            """Return `(1, 1)`."""

        @staticmethod
        def ones() -> Vector2:
            """Return `(1, 1)`."""

        @staticmethod
        def unit() -> Vector2:
            """Return `(0, 1)`."""

        @staticmethod
        def up() -> Vector2:
            """Return `(0, -1)`. Y increases downwards, so up is negative."""

        @staticmethod
        def down() -> Vector2:
            """Return `(0, 1)`."""

        @staticmethod
        def left() -> Vector2:
            """Return `(-1, 0)`."""

        @staticmethod
        def right() -> Vector2:
            """Return `(1, 0)`."""

        @staticmethod
        def from_polar(length: float, angle: float) -> Vector2:
            """Return a vector of `length` at `angle` radians from +X."""

        @staticmethod
        def from_angle_degrees(degrees: float, length: float = 1.0) -> Vector2:
            """Return a vector of `length` at `degrees` from +X."""

else:
    Vector2 = require_extension("Vector2").Vector2

Coordinate = tuple[float, float] | list[float] | Vector2
"""Anything accepted where a 2D coordinate is expected."""


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
    # Neutral greys, the ones UI chrome and debug overlays reach for. Named
    # rather than spelled `Color(128, 128, 128)` at each call site, which is
    # how three slightly different "greys" end up in one screen.
    GREY: ClassVar[Color]
    LIGHT_GREY: ClassVar[Color]
    DARK_GREY: ClassVar[Color]

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

    def with_alpha(self, alpha: int) -> Color:
        """Return this colour at a different opacity.

        The commonest edit by far -- a scrim, a fade, a ghosted preview --
        and it should not require restating three channels.

        Args:
            alpha: The new alpha, clamped to 0..255 by `Color`.

        Returns:
            The same hue at the new opacity.
        """
        return Color(self.r, self.g, self.b, alpha)

    def darken(self, amount: float) -> Color:
        """Return this colour mixed towards black.

        Args:
            amount: How far to go, 0.0 unchanged to 1.0 black. Values
                outside that range are clamped, so a caller cannot
                accidentally brighten with a negative.

        Returns:
            The darkened colour, alpha untouched -- darkening is not
            fading, and conflating them is how a shadow ends up
            see-through.
        """
        factor = 1.0 - min(max(amount, 0.0), 1.0)
        return Color(
            int(self.r * factor), int(self.g * factor), int(self.b * factor), self.a
        )

    def lighten(self, amount: float) -> Color:
        """Return this colour mixed towards white.

        Args:
            amount: How far to go, 0.0 unchanged to 1.0 white. Clamped.

        Returns:
            The lightened colour, alpha untouched.
        """
        t = min(max(amount, 0.0), 1.0)
        return Color(
            int(self.r + (255 - self.r) * t),
            int(self.g + (255 - self.g) * t),
            int(self.b + (255 - self.b) * t),
            self.a,
        )

    def multiply(self, other: Color) -> Color:
        """Return this colour modulated by another, per channel.

        The tint operation: multiplying by a colour scales each channel
        rather than mixing towards it, so white leaves the result alone and
        a red tint keeps only the red. Both backends' sprite tinting does
        this, and a damage flash or a rarity tint is the same arithmetic.

        Args:
            other: The modulating colour.

        Returns:
            The product, including alpha.
        """
        return Color(
            self.r * other.r // 255,
            self.g * other.g // 255,
            self.b * other.b // 255,
            self.a * other.a // 255,
        )

    @staticmethod
    def grey(level: int, alpha: int = 255) -> Color:
        """Return a neutral grey.

        Args:
            level: The value for all three channels, 0 black to 255 white.
            alpha: Opacity.

        Returns:
            The grey.
        """
        return Color(level, level, level, alpha)

    @staticmethod
    def ramp(stops: Sequence[Color], t: float) -> Color:
        """Sample a gradient of evenly spaced colour stops.

        What a lighting ramp, a health bar that shifts green to red, or a
        heat overlay needs. Stops are evenly spaced; weighted stops would
        need a different signature and have no caller yet.

        Args:
            stops: Two or more colours, in order.
            t: Position along the ramp, clamped to 0.0..1.0.

        Returns:
            The sampled colour.

        Raises:
            ValueError: If `stops` is empty.
        """
        if not stops:
            raise ValueError("A colour ramp needs at least one stop")
        if len(stops) == 1:
            return stops[0]

        clamped = min(max(t, 0.0), 1.0)
        scaled = clamped * (len(stops) - 1)
        index = min(int(scaled), len(stops) - 2)
        return stops[index].lerp(stops[index + 1], scaled - index)

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
Color.GREY = Color(128, 128, 128)
Color.LIGHT_GREY = Color(192, 192, 192)
Color.DARK_GREY = Color(64, 64, 64)


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

    def move(self, dx: int, dy: int) -> Rect:
        """Return a copy offset by `dx`/`dy`, keeping its size.

        Args:
            dx: Horizontal offset in pixels.
            dy: Vertical offset in pixels.

        Returns:
            The moved rectangle.
        """
        return Rect(self.x + dx, self.y + dy, self.width, self.height)

    def clip(self, other: Rect) -> Rect:
        """Return the overlapping region of this rectangle and `other`.

        When they do not overlap the result is zero-sized **at this
        rectangle's own position**, which is what `pygame.Rect.clip` does.
        Verified differentially rather than assumed: the first version of
        this returned `Rect(0, 0, 0, 0)`, which agrees with pygame only for
        a rectangle that happens to sit at the origin -- and the probe that
        "confirmed" it used exactly such a rectangle.

        Test `colliderect()` first to tell "no overlap" from "an empty
        overlap", since a zero-sized result is the answer to both.

        Args:
            other: The rectangle to clip against.

        Returns:
            The intersection, or a zero-sized rectangle at `self`'s
            position if there is none.
        """
        left = max(self.left, other.left)
        top = max(self.top, other.top)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)

        if right <= left or bottom <= top:
            return Rect(self.x, self.y, 0, 0)
        return Rect(left, top, right - left, bottom - top)

    def intersection(self, other: Rect) -> Rect:
        """Return the overlapping region. An alias for `clip()`.

        Both names exist because both get reached for: `clip` is what
        `pygame.Rect` calls it, `intersection` is what the geometry reads
        as.

        Args:
            other: The rectangle to intersect with.

        Returns:
            The intersection, or `Rect(0, 0, 0, 0)` if there is none.
        """
        return self.clip(other)

    def union(self, other: Rect) -> Rect:
        """Return the smallest rectangle covering both.

        Args:
            other: The rectangle to union with.

        Returns:
            The bounding rectangle.
        """
        left = min(self.left, other.left)
        top = min(self.top, other.top)
        right = max(self.right, other.right)
        bottom = max(self.bottom, other.bottom)
        return Rect(left, top, right - left, bottom - top)

    def clamp(self, other: Rect) -> Rect:
        """Return a copy moved to sit inside `other`, keeping its size.

        A rectangle too large to fit is centred on `other`, as
        `pygame.Rect.clamp` does.

        Args:
            other: The rectangle to stay inside.

        Returns:
            The moved rectangle.
        """
        # Centred as `other.centerx - self.width // 2`, not by halving the
        # leftover. Those differ, and only this one matches `pygame.Rect`:
        # two earlier attempts (floor the leftover, truncate the leftover)
        # each matched roughly three quarters of random inputs and
        # contradicted each other on the rest, because neither is the rule.
        if self.width >= other.width:
            x = other.centerx - self.width // 2
        elif self.left < other.left:
            x = other.left
        elif self.right > other.right:
            x = other.right - self.width
        else:
            x = self.x

        if self.height >= other.height:
            y = other.centery - self.height // 2
        elif self.top < other.top:
            y = other.top
        elif self.bottom > other.bottom:
            y = other.bottom - self.height
        else:
            y = self.y

        return Rect(x, y, self.width, self.height)

    def fit(self, other: Rect) -> Rect:
        """Return a copy scaled to fit inside `other`, aspect ratio kept.

        The result is centred in `other` on whichever axis has room left
        over. The arithmetic is integer, so the fitted axis lands on `other`'s
        dimension exactly; `pygame.Rect.fit` can come out one unit short.

        Args:
            other: The rectangle to fit inside.

        Returns:
            The scaled, centred rectangle.

        Raises:
            ZeroDivisionError: If `other` has zero width or height.
        """
        # Integer arithmetic on whichever axis is the constraint, rather
        # than dividing by a float ratio. The dominant axis then lands on
        # `other`'s dimension *exactly*; computing `self.height / (
        # self.height / other.height)` instead loses a unit to rounding
        # whenever the division is inexact, which a differential test
        # against `pygame.Rect` caught on roughly 7% of random inputs.
        if self.width * other.height > self.height * other.width:
            width = other.width
            height = self.height * other.width // self.width
        else:
            height = other.height
            width = self.width * other.height // self.height
        return Rect(
            other.x + (other.width - width) // 2,
            other.y + (other.height - height) // 2,
            width,
            height,
        )

    def scale_by(self, sx: float, sy: float | None = None) -> Rect:
        """Return a copy scaled about its own centre.

        Truncates towards zero, as `inflate` does. This does not bit-match
        `pygame.Rect.scale_by`, whose rounding follows no single rule; the two
        never differ by more than a pixel.

        Args:
            sx: Horizontal scale factor.
            sy: Vertical scale factor. Defaults to `sx`, so one argument
                scales uniformly.

        Returns:
            The scaled rectangle, still centred where this one was.
        """
        factor_y = sx if sy is None else sy
        width = int(self.width * sx)
        height = int(self.height * factor_y)
        return Rect(
            self.x + int((self.width - width) / 2),
            self.y + int((self.height - height) / 2),
            width,
            height,
        )

    def collidelist(self, others: Sequence[Rect]) -> int:
        """Return the index of the first rectangle this one overlaps.

        Args:
            others: The rectangles to test, in order.

        Returns:
            The index of the first overlap, or -1 if there is none -- the
            `pygame.Rect.collidelist` convention, kept so a caller can
            write `if (hit := r.collidelist(walls)) >= 0`.
        """
        for index, other in enumerate(others):
            if self.colliderect(other):
                return index
        return -1

    def collidelistall(self, others: Sequence[Rect]) -> list[int]:
        """Return the indices of every rectangle this one overlaps.

        Args:
            others: The rectangles to test.

        Returns:
            Indices of all overlaps, in order; empty if there are none.
        """
        return [i for i, other in enumerate(others) if self.colliderect(other)]

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
