"""Tests for the native Color and Rect value types (wayfinder ticket 31).

Color and Rect stopped being pygame.Color/pygame.Rect subclasses -- these
tests cover the surface the decision (ticket 05) called for, since no
dedicated test file existed for `common/types.py` before this ticket.
"""

from pyguara.common.types import Color, Rect, Vector2


class TestColor:
    def test_construction_defaults_alpha_to_opaque(self) -> None:
        c = Color(10, 20, 30)
        assert (c.r, c.g, c.b, c.a) == (10, 20, 30, 255)

    def test_equality_is_by_value(self) -> None:
        assert Color(1, 2, 3, 4) == Color(1, 2, 3, 4)
        assert Color(1, 2, 3, 4) != Color(1, 2, 3, 5)

    def test_mutability(self) -> None:
        c = Color(1, 2, 3)
        c.r = 200
        assert c.r == 200

    def test_from_hex_six_digit(self) -> None:
        assert Color.from_hex("#FF00AA") == Color(255, 0, 170)
        assert Color.from_hex("0xFF00AA") == Color(255, 0, 170)

    def test_from_hex_eight_digit_with_alpha(self) -> None:
        assert Color.from_hex("#00FF00FF") == Color(0, 255, 0, 255)

    def test_from_hex_rejects_invalid_length(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            Color.from_hex("#FFF")

    def test_normalized(self) -> None:
        assert Color(255, 0, 128, 0).normalized == (1.0, 0.0, 128 / 255.0, 0.0)

    def test_lerp(self) -> None:
        assert Color(0, 0, 0, 0).lerp(Color(100, 200, 50, 255), 0.5) == Color(
            50, 100, 25, 128
        )

    def test_hsv_round_trip(self) -> None:
        original = Color(200, 100, 50)
        h, s, v = original.to_hsv()
        restored = Color.from_hsv(h, s, v)
        # Round-trip through float HSV can be off by a rounding unit.
        assert abs(restored.r - original.r) <= 1
        assert abs(restored.g - original.g) <= 1
        assert abs(restored.b - original.b) <= 1

    def test_named_color_constants(self) -> None:
        assert Color(255, 255, 255) == Color.WHITE
        assert Color(0, 0, 0) == Color.BLACK
        assert Color(0, 0, 0, 0) == Color.TRANSPARENT

    def test_indexing_and_length(self) -> None:
        c = Color(1, 2, 3, 4)
        assert (c[0], c[1], c[2], c[3]) == (1, 2, 3, 4)
        assert len(c) == 4


class TestRect:
    def test_construction_truncates_floats_to_int(self) -> None:
        r = Rect(1.7, 2.9, 3.2, 4.8)
        assert (r.x, r.y, r.width, r.height) == (1, 2, 3, 4)

    def test_mutability(self) -> None:
        r = Rect(0, 0, 10, 10)
        r.x = 50
        assert r.x == 50

    def test_equality_is_by_value(self) -> None:
        assert Rect(0, 0, 10, 10) == Rect(0, 0, 10, 10)
        assert Rect(0, 0, 10, 10) != Rect(0, 0, 10, 11)

    def test_edges(self) -> None:
        r = Rect(10, 20, 30, 40)
        assert r.left == 10
        assert r.top == 20
        assert r.right == 40
        assert r.bottom == 60
        assert r.centerx == 25
        assert r.centery == 40

    def test_position_and_center_vec(self) -> None:
        r = Rect(10, 20, 30, 40)
        assert r.position == Vector2(10, 20)
        assert r.center_vec == Vector2(25, 40)

    def test_contains_point_excludes_right_and_bottom_edges(self) -> None:
        r = Rect(0, 0, 10, 10)
        assert r.contains_point(Vector2(0, 0))
        assert r.contains_point(Vector2(9, 9))
        assert not r.contains_point(Vector2(10, 10))
        assert not r.contains_point(Vector2(-1, 5))

    def test_colliderect(self) -> None:
        r = Rect(0, 0, 10, 10)
        assert r.colliderect(Rect(5, 5, 10, 10))
        assert not r.colliderect(Rect(10, 10, 10, 10))  # touching edge only
        assert not r.colliderect(Rect(100, 100, 10, 10))

    def test_contains(self) -> None:
        outer = Rect(0, 0, 20, 20)
        assert outer.contains(Rect(5, 5, 5, 5))
        assert outer.contains(Rect(0, 0, 20, 20))  # itself
        assert not outer.contains(Rect(15, 15, 10, 10))

    def test_inflate_keeps_center(self) -> None:
        r = Rect(10, 10, 10, 10)
        inflated = r.inflate(4, 4)
        assert inflated == Rect(8, 8, 14, 14)
        assert inflated.center_vec == r.center_vec


class TestColorChannelClamping:
    """Channels are coerced and clamped, as Rect's coordinates already were.

    Color stopped being a pygame.Color subclass (which validated its own
    range) and gained no replacement, so out-of-range values propagated
    silently all the way to the backend.
    """

    def test_channels_above_range_saturate(self) -> None:
        assert Color(300, 256, 999) == Color(255, 255, 255)

    def test_channels_below_range_clamp_to_zero(self) -> None:
        assert Color(-5, -1, -999, -3) == Color(0, 0, 0, 0)

    def test_float_channels_are_coerced_to_int(self) -> None:
        c = Color(1.9, 2.1, 3.5)  # type: ignore[arg-type]
        assert (c.r, c.g, c.b) == (1, 2, 3)
        assert all(isinstance(v, int) for v in (c.r, c.g, c.b))

    def test_out_of_range_hsv_saturates_instead_of_producing_garbage(self) -> None:
        """from_hsv with saturation/value > 1 used to yield Color(1275, -5100, -5100)."""
        assert Color.from_hsv(0, 5, 5) == Color(255, 0, 0)

    def test_lerp_result_stays_in_range(self) -> None:
        assert Color(0, 0, 0).lerp(Color(255, 255, 255), 0.5) == Color(128, 128, 128)

    def test_normalized_never_exceeds_one(self) -> None:
        assert Color(999, 999, 999, 999).normalized == (1.0, 1.0, 1.0, 1.0)


class TestColorHex:
    def test_to_hex_round_trips(self) -> None:
        assert Color.from_hex(Color(255, 0, 170).to_hex()) == Color(255, 0, 170)

    def test_to_hex_with_alpha(self) -> None:
        assert Color(255, 0, 170, 128).to_hex(include_alpha=True) == "#FF00AA80"

    def test_from_hex_rejects_non_hex_digits(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Invalid hex color"):
            Color.from_hex("#GGHHII")


class TestRectInflate:
    def test_inflate_matches_pygame_for_odd_negative_deltas(self) -> None:
        """Floor division put the origin at 3; pygame truncates towards zero,
        giving 2. Rect exists to stand in for pygame.Rect, so it must agree."""
        assert Rect(0, 0, 10, 10).inflate(-5, -5) == Rect(2, 2, 5, 5)

    def test_inflate_grows_keeping_center(self) -> None:
        r = Rect(10, 10, 10, 10)
        assert r.inflate(4, 4).center_vec == r.center_vec

    def test_size(self) -> None:
        assert Rect(1, 2, 30, 40).size == (30, 40)


class TestVector2Arithmetic:
    def test_add_and_subtract_return_vector2(self) -> None:
        result = Vector2(1, 2) + Vector2(3, 4)
        assert result == Vector2(4, 6)
        assert isinstance(result, Vector2)
        assert isinstance(Vector2(1, 2) - Vector2(3, 4), Vector2)

    def test_scalar_multiplication_both_sides(self) -> None:
        assert Vector2(1, 2) * 3 == Vector2(3, 6)
        assert 3 * Vector2(1, 2) == Vector2(3, 6)
        assert isinstance(3 * Vector2(1, 2), Vector2)

    def test_scalar_multiplication_does_not_repeat_the_tuple(self) -> None:
        """tuple.__mul__ would turn v * 3 into a 6-element tuple."""
        assert len(Vector2(1, 2) * 3) == 2

    def test_division_and_negation(self) -> None:
        assert Vector2(4, 6) / 2 == Vector2(2, 3)
        assert -Vector2(1, -2) == Vector2(-1, 2)

    def test_addition_accepts_a_plain_tuple(self) -> None:
        assert Vector2(1, 2) + (3, 4) == Vector2(4, 6)

    def test_vector_is_immutable(self) -> None:
        import pytest

        with pytest.raises(AttributeError):
            Vector2(1, 2).x = 5  # type: ignore[misc]


class TestVector2Geometry:
    def test_magnitude_and_sqr_magnitude(self) -> None:
        assert Vector2(3, 4).magnitude == 5.0
        assert Vector2(3, 4).sqr_magnitude == 25.0

    def test_normalize_gives_unit_length(self) -> None:
        assert Vector2(3, 4).normalize() == Vector2(0.6, 0.8)

    def test_normalize_of_zero_vector_does_not_raise(self) -> None:
        assert Vector2(0, 0).normalize() == Vector2(0, 0)

    def test_dot_and_cross(self) -> None:
        assert Vector2(1, 0).dot(Vector2(0, 1)) == 0.0
        assert Vector2(1, 0).cross(Vector2(0, 1)) == 1.0

    def test_distance_to(self) -> None:
        assert Vector2(0, 0).distance_to(Vector2(3, 4)) == 5.0

    def test_lerp_endpoints_and_midpoint(self) -> None:
        a, b = Vector2(0, 0), Vector2(10, 20)
        assert a.lerp(b, 0.0) == a
        assert a.lerp(b, 1.0) == b
        assert a.lerp(b, 0.5) == Vector2(5, 10)

    def test_to_tuple_and_to_int_tuple(self) -> None:
        assert Vector2(1.7, -2.7).to_tuple() == (1.7, -2.7)
        assert Vector2(1.7, -2.7).to_int_tuple() == (1, -2)


class TestVector2Rotation:
    def test_rotated_takes_radians(self) -> None:
        import math

        result = Vector2(1, 0).rotated(math.pi / 2)
        assert abs(result.x) < 1e-9
        assert abs(result.y - 1.0) < 1e-9

    def test_rotate_degrees_takes_degrees(self) -> None:
        result = Vector2(1, 0).rotate_degrees(90)
        assert abs(result.x) < 1e-9
        assert abs(result.y - 1.0) < 1e-9

    def test_rotate_is_gone_so_the_unit_cannot_be_confused(self) -> None:
        """`rotate` (degrees) sat next to `rotated` (radians), and
        Transform.rotate() takes radians. A one-letter difference deciding the
        angle unit is unreadable at a call site, so the ambiguous name was
        removed rather than documented."""
        assert not hasattr(Vector2(1, 0), "rotate")

    def test_rotation_preserves_length(self) -> None:
        assert abs(Vector2(3, 4).rotate_degrees(37).magnitude - 5.0) < 1e-9


class TestVector2Directions:
    def test_axis_convention_is_y_down(self) -> None:
        """Y grows downwards (SDL/pygame, and the engine's positive default
        gravity), so up is negative Y."""
        assert Vector2.up() == Vector2(0, -1)
        assert Vector2.down() == Vector2(0, 1)
        assert Vector2.left() == Vector2(-1, 0)
        assert Vector2.right() == Vector2(1, 0)

    def test_opposites_cancel(self) -> None:
        assert Vector2.up() + Vector2.down() == Vector2.zero()
        assert Vector2.left() + Vector2.right() == Vector2.zero()

    def test_zero_and_one(self) -> None:
        assert Vector2.zero() == Vector2(0, 0)
        assert Vector2.one() == Vector2(1, 1)
