"""Tests for the native Color and Rect value types (wayfinder ticket 31).

Color and Rect stopped being pygame.Color/pygame.Rect subclasses -- these
tests cover the surface the decision (ticket 05) called for, since no
dedicated test file existed for `common/types.py` before this ticket.
"""

import pytest

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


class TestRectMove:
    def test_move_offsets_and_keeps_size(self) -> None:
        assert Rect(1, 2, 10, 20).move(3, -4) == Rect(4, -2, 10, 20)

    def test_move_does_not_mutate(self) -> None:
        r = Rect(1, 2, 10, 20)
        r.move(5, 5)
        assert r == Rect(1, 2, 10, 20)


class TestRectClip:
    def test_clip_returns_the_overlap(self) -> None:
        assert Rect(0, 0, 10, 10).clip(Rect(5, 5, 10, 10)) == Rect(5, 5, 5, 5)

    def test_clip_of_a_contained_rect_is_that_rect(self) -> None:
        inner = Rect(2, 2, 3, 3)
        assert Rect(0, 0, 10, 10).clip(inner) == inner

    def test_no_overlap_is_zero_sized_at_self_position(self) -> None:
        """Not at the origin -- `pygame.Rect.clip` puts it at the clipped
        rectangle's own position. The first implementation returned
        `Rect(0, 0, 0, 0)`, which agrees with pygame only for a rectangle
        that happens to sit at the origin, and the probe that "confirmed"
        it used exactly such a rectangle. A differential test caught it."""
        result = Rect(19, -2, 8, 1).clip(Rect(-25, 28, 38, 3))
        assert result == Rect(19, -2, 0, 0)

    def test_an_edge_touch_is_not_an_overlap(self) -> None:
        """Rect bounds are half-open, as `contains_point` already is."""
        assert Rect(0, 0, 5, 5).clip(Rect(5, 0, 5, 5)).size == (0, 0)

    def test_intersection_is_an_alias(self) -> None:
        a, b = Rect(0, 0, 10, 10), Rect(5, 5, 10, 10)
        assert a.intersection(b) == a.clip(b)


class TestRectUnion:
    def test_union_covers_both(self) -> None:
        assert Rect(0, 0, 10, 10).union(Rect(5, 5, 10, 10)) == Rect(0, 0, 15, 15)

    def test_union_with_a_contained_rect_is_unchanged(self) -> None:
        outer = Rect(0, 0, 10, 10)
        assert outer.union(Rect(2, 2, 3, 3)) == outer

    def test_union_is_symmetric(self) -> None:
        a, b = Rect(-5, 3, 4, 4), Rect(10, -2, 6, 9)
        assert a.union(b) == b.union(a)


class TestRectClamp:
    def test_clamp_moves_a_smaller_rect_inside(self) -> None:
        assert Rect(0, 0, 4, 4).clamp(Rect(10, 10, 20, 20)) == Rect(10, 10, 4, 4)

    def test_clamp_leaves_an_already_inside_rect_alone(self) -> None:
        inside = Rect(12, 12, 4, 4)
        assert inside.clamp(Rect(10, 10, 20, 20)) == inside

    def test_clamp_pushes_back_from_the_far_edge(self) -> None:
        assert Rect(100, 12, 4, 4).clamp(Rect(10, 10, 20, 20)) == Rect(26, 12, 4, 4)

    def test_a_rect_too_large_is_centred_on_the_target(self) -> None:
        """What a camera clamped to a level smaller than its viewport wants,
        and the case that pinned down the rule: pygame centres as
        `other.centerx - self.width // 2`, *not* by halving the leftover.
        Two earlier attempts each matched about three quarters of random
        inputs and disagreed with each other on the rest, because neither
        was the rule."""
        assert Rect(0, -10, 26, 3).clamp(Rect(-13, 5, 1, 28)) == Rect(-26, 5, 26, 3)


class TestRectFit:
    def test_fit_preserves_aspect_and_centres(self) -> None:
        assert Rect(0, 0, 20, 10).fit(Rect(0, 0, 100, 100)) == Rect(0, 25, 100, 50)

    def test_fit_lands_exactly_on_the_constraining_axis(self) -> None:
        """Where this deliberately beats `pygame.Rect.fit`: pygame divides
        by a float ratio, so `36 / (36 / 35)` is `34.999...` and truncates
        to 34 -- a unit short of the height it just asked for. Integer
        arithmetic on the dominant axis lands on it exactly."""
        assert Rect(0, 0, 13, 36).fit(Rect(0, 0, 23, 35)).height == 35

    def test_fit_never_overflows_the_target(self) -> None:
        for size in ((13, 36), (36, 13), (7, 7), (40, 1), (1, 40)):
            result = Rect(0, 0, *size).fit(Rect(0, 0, 23, 35))
            assert result.width <= 23 and result.height <= 35, size


class TestRectScaleBy:
    def test_scale_by_grows_about_the_centre(self) -> None:
        r = Rect(0, 0, 10, 10)
        assert r.scale_by(1.5) == Rect(-2, -2, 15, 15)

    def test_scale_by_shrinks(self) -> None:
        assert Rect(0, 0, 10, 10).scale_by(0.5) == Rect(2, 2, 5, 5)

    def test_scale_by_takes_separate_axes(self) -> None:
        assert Rect(0, 0, 10, 10).scale_by(2, 1) == Rect(-5, 0, 20, 10)

    def test_scale_by_keeps_the_centre_within_a_pixel(self) -> None:
        """The documented property, since this is the one helper that does
        not bit-match pygame -- pygame-ce's rounding is not reproducible
        from any single rule."""
        r = Rect(3, 5, 7, 9)
        scaled = r.scale_by(1.5)
        assert abs(scaled.centerx - r.centerx) <= 1
        assert abs(scaled.centery - r.centery) <= 1


class TestRectCollideList:
    def test_collidelist_returns_the_first_index(self) -> None:
        a = Rect(0, 0, 10, 10)
        assert a.collidelist([Rect(100, 100, 5, 5), Rect(5, 5, 10, 10)]) == 1

    def test_collidelist_returns_minus_one_for_no_hit(self) -> None:
        """The pygame convention, kept so `if (hit := ...) >= 0` works."""
        assert Rect(0, 0, 10, 10).collidelist([Rect(100, 100, 5, 5)]) == -1

    def test_collidelist_of_nothing_is_minus_one(self) -> None:
        assert Rect(0, 0, 10, 10).collidelist([]) == -1

    def test_collidelistall_returns_every_index(self) -> None:
        a = Rect(0, 0, 10, 10)
        hits = a.collidelistall(
            [Rect(1, 1, 2, 2), Rect(100, 100, 5, 5), Rect(5, 5, 10, 10)]
        )
        assert hits == [0, 2]

    def test_collidelistall_of_no_hits_is_empty(self) -> None:
        assert Rect(0, 0, 10, 10).collidelistall([Rect(50, 50, 1, 1)]) == []


class TestRectPygameParity:
    """Differential parity against `pygame.Rect`, which is what these
    helpers exist to stand in for.

    Randomised and seeded rather than hand-picked: every single-case probe
    I wrote by hand agreed with pygame while the implementation was wrong,
    because the cases I chose were too tidy -- a rectangle at the origin
    hides `clip`'s position behaviour entirely. Three real bugs came out of
    running this over a few thousand inputs.

    `fit` and `scale_by` are excluded deliberately and tested above on their
    own terms; both divergences are documented on the methods.
    """

    @staticmethod
    def _cases(count: int = 400):
        import random

        random.seed(20261008)
        for _ in range(count):
            yield (
                (
                    random.randint(-30, 30),
                    random.randint(-30, 30),
                    random.randint(1, 40),
                    random.randint(1, 40),
                ),
                (
                    random.randint(-30, 30),
                    random.randint(-30, 30),
                    random.randint(1, 40),
                    random.randint(1, 40),
                ),
            )

    def test_move_clip_union_clamp_match_pygame(self) -> None:
        import pygame

        for a, b in self._cases():
            mine, theirs = Rect(*a), pygame.Rect(*a)
            other, their_other = Rect(*b), pygame.Rect(*b)

            for name in ("move", "clip", "union", "clamp"):
                if name == "move":
                    got, want = mine.move(3, -4), theirs.move(3, -4)
                else:
                    got = getattr(mine, name)(other)
                    want = getattr(theirs, name)(their_other)
                assert (got.x, got.y, got.width, got.height) == tuple(want), (
                    f"{name}: self={a} other={b}"
                )

    def test_collidelist_matches_pygame(self) -> None:
        import pygame

        for a, b in self._cases(200):
            assert Rect(*a).collidelist([Rect(*b)]) == pygame.Rect(*a).collidelist(
                [pygame.Rect(*b)]
            )


class TestVector2GameMath:
    """The helpers `steering.py`, `CharacterMover` and camera-follow each
    reimplemented subsets of (#64).

    Several of the ones that issue listed as missing were **already there**
    under pymunk names -- `project` is `projection()`, `angle_to` is
    `get_angle_between()`, and `angle`/`perpendicular` are inherited. Only
    the genuinely absent ones are added, so there is one spelling of each
    rather than two.
    """

    def test_clamp_magnitude_shortens_a_long_vector(self) -> None:
        clamped = Vector2(3, 4).clamp_magnitude(1)
        assert round(clamped.length, 6) == 1.0

    def test_clamp_magnitude_leaves_a_short_vector_alone(self) -> None:
        """The difference from pymunk's inherited `scale_to_length()`, which
        scales both ways and would *lengthen* this one. A speed cap wants
        only the shortening half."""
        assert Vector2(3, 4).clamp_magnitude(10) == Vector2(3, 4)

    def test_clamp_magnitude_of_zero_length_is_safe(self) -> None:
        assert Vector2(0, 0).clamp_magnitude(5) == Vector2(0, 0)

    def test_a_non_positive_clamp_gives_the_zero_vector(self) -> None:
        assert Vector2(3, 4).clamp_magnitude(0) == Vector2(0, 0)

    def test_move_towards_steps_without_overshooting(self) -> None:
        assert Vector2(0, 0).move_towards(Vector2(10, 0), 3) == Vector2(3, 0)

    def test_move_towards_lands_exactly_on_a_near_target(self) -> None:
        """Overshooting is the bug this exists to avoid -- a chaser that
        jitters around its target forever."""
        assert Vector2(0, 0).move_towards(Vector2(2, 0), 99) == Vector2(2, 0)

    def test_move_towards_zero_distance_does_not_move(self) -> None:
        assert Vector2(1, 1).move_towards(Vector2(9, 9), 0) == Vector2(1, 1)

    def test_reflect_mirrors_about_a_normal(self) -> None:
        assert Vector2(1, -1).reflect(Vector2(0, 1)) == Vector2(1, 1)

    def test_reflect_normalises_the_normal_itself(self) -> None:
        """A caller passing a surface direction of any length gets the right
        answer rather than a silently scaled one."""
        assert Vector2(1, -1).reflect(Vector2(0, 5)) == Vector2(1, 1)

    def test_reflect_off_a_zero_normal_is_unchanged(self) -> None:
        """No plane to mirror about. Returning the vector beats dividing by
        zero or inventing a direction."""
        assert Vector2(1, -1).reflect(Vector2(0, 0)) == Vector2(1, -1)

    def test_projection_and_reject_decompose_the_vector(self) -> None:
        """The property that makes `reject` worth having: together with
        pymunk's inherited `projection()` it splits a vector into "along"
        and "across" a direction, which is how sliding along a wall works."""
        v, axis = Vector2(3, 4), Vector2(1, 0)
        along, across = v.projection(axis), v.reject(axis)
        assert Vector2(along.x + across.x, along.y + across.y) == v

    def test_reject_of_a_parallel_vector_is_zero(self) -> None:
        assert Vector2(5, 0).reject(Vector2(1, 0)) == Vector2(0, 0)

    def test_snapped_rounds_to_the_grid(self) -> None:
        assert Vector2(13, 27).snapped(10) == Vector2(10, 30)

    def test_snapped_accepts_a_per_axis_grid(self) -> None:
        assert Vector2(13, 27).snapped(Vector2(10, 5)) == Vector2(10, 25)

    def test_a_zero_grid_leaves_that_axis_alone(self) -> None:
        """Rather than dividing by zero."""
        assert Vector2(13, 27).snapped(0) == Vector2(13, 27)

    def test_from_angle_degrees_takes_degrees(self) -> None:
        """pymunk's inherited `from_polar()` takes **radians**, which is the
        easy mistake: `from_polar(1, 90)` is 90 radians, not a quarter
        turn."""
        quarter = Vector2.from_angle_degrees(90)
        assert round(quarter.x, 6) == 0.0
        assert round(quarter.y, 6) == 1.0

    def test_from_angle_degrees_honours_length(self) -> None:
        assert round(Vector2.from_angle_degrees(0, 5).x, 6) == 5.0

    def test_from_angle_degrees_differs_from_from_polar(self) -> None:
        assert Vector2.from_angle_degrees(90) != Vector2.from_polar(1, 90)


class TestColorHelpers:
    def test_with_alpha_keeps_the_hue(self) -> None:
        assert Color(100, 150, 200).with_alpha(128) == Color(100, 150, 200, 128)

    def test_darken_mixes_towards_black(self) -> None:
        assert Color(100, 150, 200).darken(0.5) == Color(50, 75, 100)

    def test_darken_keeps_alpha(self) -> None:
        """Darkening is not fading. Conflating them is how a shadow ends up
        see-through."""
        assert Color(100, 150, 200, 128).darken(0.5).a == 128

    def test_lighten_mixes_towards_white(self) -> None:
        assert Color(0, 0, 0).lighten(1.0) == Color(255, 255, 255)

    def test_darken_and_lighten_clamp_their_amount(self) -> None:
        """So a negative cannot accidentally brighten."""
        base = Color(100, 150, 200)
        assert base.darken(-5) == base
        assert base.darken(99) == Color(0, 0, 0)
        assert base.lighten(-5) == base

    def test_multiply_by_white_is_identity(self) -> None:
        """What makes it a *tint*: multiplying scales each channel rather
        than mixing towards the other colour, so white changes nothing."""
        base = Color(100, 150, 200)
        assert base.multiply(Color.WHITE) == base

    def test_multiply_by_red_keeps_only_red(self) -> None:
        assert Color(100, 150, 200).multiply(Color.RED) == Color(100, 0, 0)

    def test_grey_builds_a_neutral(self) -> None:
        assert Color.grey(200) == Color(200, 200, 200)

    def test_the_grey_constants_are_neutral(self) -> None:
        for grey in (Color.GREY, Color.LIGHT_GREY, Color.DARK_GREY):
            assert grey.r == grey.g == grey.b

    def test_ramp_lands_on_an_interior_stop(self) -> None:
        stops = [Color.GREEN, Color.YELLOW, Color.RED]
        assert Color.ramp(stops, 0.5) == Color.YELLOW

    def test_ramp_hits_both_ends(self) -> None:
        stops = [Color.GREEN, Color.RED]
        assert Color.ramp(stops, 0.0) == Color.GREEN
        assert Color.ramp(stops, 1.0) == Color.RED

    def test_ramp_clamps_outside_the_range(self) -> None:
        stops = [Color.GREEN, Color.RED]
        assert Color.ramp(stops, 9.0) == Color.RED
        assert Color.ramp(stops, -9.0) == Color.GREEN

    def test_a_single_stop_ramp_is_that_colour(self) -> None:
        assert Color.ramp([Color.RED], 0.7) == Color.RED

    def test_an_empty_ramp_is_an_error(self) -> None:
        """Nothing sensible to return, and a silent black would look like a
        working gradient."""
        with pytest.raises(ValueError, match="at least one stop"):
            Color.ramp([], 0.5)
