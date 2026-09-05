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
        assert Color.WHITE == Color(255, 255, 255)
        assert Color.BLACK == Color(0, 0, 0)
        assert Color.TRANSPARENT == Color(0, 0, 0, 0)

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
