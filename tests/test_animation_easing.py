"""Tests for easing functions."""

import pytest

from pyguara.animation.easing import (
    EasingType,
    ease,
    linear,
    ease_in_quad,
    ease_out_quad,
    ease_in_out_quad,
    ease_in_cubic,
    ease_out_cubic,
    ease_in_out_cubic,
    ease_in_sine,
    ease_out_sine,
    ease_in_out_sine,
    ease_in_expo,
    ease_out_expo,
    ease_in_out_expo,
    ease_in_circ,
    ease_out_circ,
    ease_in_out_circ,
    ease_in_elastic,
    ease_out_elastic,
    ease_in_out_elastic,
    ease_in_back,
    ease_out_back,
    ease_in_out_back,
    ease_in_bounce,
    ease_out_bounce,
    ease_in_out_bounce,
)


class TestLinearEasing:
    """Test linear easing function."""

    def test_linear_at_endpoints(self):
        """Linear should return exact values at 0 and 1."""
        assert linear(0.0) == 0.0
        assert linear(1.0) == 1.0

    def test_linear_midpoint(self):
        """Linear should return exact midpoint."""
        assert linear(0.5) == 0.5

    def test_linear_is_identity(self):
        """Linear should be identity function."""
        assert linear(0.25) == 0.25
        assert linear(0.75) == 0.75


class TestQuadraticEasing:
    """Test quadratic easing functions."""

    def test_ease_in_quad_endpoints(self):
        """Ease in quad should return 0 and 1 at endpoints."""
        assert ease_in_quad(0.0) == 0.0
        assert ease_in_quad(1.0) == 1.0

    def test_ease_in_quad_accelerates(self):
        """Ease in quad should accelerate (slow start)."""
        assert ease_in_quad(0.5) == 0.25
        assert ease_in_quad(0.25) < 0.25

    def test_ease_out_quad_endpoints(self):
        """Ease out quad should return 0 and 1 at endpoints."""
        assert ease_out_quad(0.0) == 0.0
        assert ease_out_quad(1.0) == 1.0

    def test_ease_out_quad_decelerates(self):
        """Ease out quad should decelerate (fast start)."""
        assert ease_out_quad(0.5) == 0.75
        assert ease_out_quad(0.25) > 0.25

    def test_ease_in_out_quad_endpoints(self):
        """Ease in/out quad should return 0 and 1 at endpoints."""
        assert ease_in_out_quad(0.0) == 0.0
        assert ease_in_out_quad(1.0) == 1.0

    def test_ease_in_out_quad_symmetric(self):
        """Ease in/out quad should be symmetric around midpoint."""
        assert ease_in_out_quad(0.5) == 0.5


class TestCubicEasing:
    """Test cubic easing functions."""

    def test_ease_in_cubic_endpoints(self):
        """Ease in cubic should return 0 and 1 at endpoints."""
        assert ease_in_cubic(0.0) == 0.0
        assert ease_in_cubic(1.0) == 1.0

    def test_ease_out_cubic_endpoints(self):
        """Ease out cubic should return 0 and 1 at endpoints."""
        assert ease_out_cubic(0.0) == 0.0
        assert ease_out_cubic(1.0) == 1.0

    def test_ease_in_out_cubic_endpoints(self):
        """Ease in/out cubic should return 0 and 1 at endpoints."""
        assert ease_in_out_cubic(0.0) == 0.0
        assert ease_in_out_cubic(1.0) == 1.0


class TestSineEasing:
    """Test sinusoidal easing functions."""

    def test_ease_in_sine_endpoints(self):
        """Ease in sine should return 0 and 1 at endpoints."""
        assert ease_in_sine(0.0) == pytest.approx(0.0)
        assert ease_in_sine(1.0) == pytest.approx(1.0)

    def test_ease_out_sine_endpoints(self):
        """Ease out sine should return 0 and 1 at endpoints."""
        assert ease_out_sine(0.0) == pytest.approx(0.0)
        assert ease_out_sine(1.0) == pytest.approx(1.0)

    def test_ease_in_out_sine_endpoints(self):
        """Ease in/out sine should return 0 and 1 at endpoints."""
        assert ease_in_out_sine(0.0) == pytest.approx(0.0)
        assert ease_in_out_sine(1.0) == pytest.approx(1.0)


class TestExponentialEasing:
    """Test exponential easing functions."""

    def test_ease_in_expo_endpoints(self):
        """Ease in expo should return 0 and 1 at endpoints."""
        assert ease_in_expo(0.0) == 0.0
        assert ease_in_expo(1.0) == pytest.approx(1.0, rel=1e-6)

    def test_ease_out_expo_endpoints(self):
        """Ease out expo should return 0 and 1 at endpoints."""
        assert ease_out_expo(0.0) == pytest.approx(0.0, rel=1e-6)
        assert ease_out_expo(1.0) == 1.0

    def test_ease_in_out_expo_endpoints(self):
        """Ease in/out expo should return 0 and 1 at endpoints."""
        assert ease_in_out_expo(0.0) == 0.0
        assert ease_in_out_expo(1.0) == 1.0


class TestCircularEasing:
    """Test circular easing functions."""

    def test_ease_in_circ_endpoints(self):
        """Ease in circ should return 0 and 1 at endpoints."""
        assert ease_in_circ(0.0) == pytest.approx(0.0)
        assert ease_in_circ(1.0) == pytest.approx(1.0)

    def test_ease_out_circ_endpoints(self):
        """Ease out circ should return 0 and 1 at endpoints."""
        assert ease_out_circ(0.0) == pytest.approx(0.0)
        assert ease_out_circ(1.0) == pytest.approx(1.0)

    def test_ease_in_out_circ_endpoints(self):
        """Ease in/out circ should return 0 and 1 at endpoints."""
        assert ease_in_out_circ(0.0) == pytest.approx(0.0)
        assert ease_in_out_circ(1.0) == pytest.approx(1.0)


class TestElasticEasing:
    """Test elastic easing functions."""

    def test_ease_in_elastic_endpoints(self):
        """Ease in elastic should return 0 and 1 at endpoints."""
        assert ease_in_elastic(0.0) == 0.0
        assert ease_in_elastic(1.0) == 1.0

    def test_ease_out_elastic_endpoints(self):
        """Ease out elastic should return 0 and 1 at endpoints."""
        assert ease_out_elastic(0.0) == 0.0
        assert ease_out_elastic(1.0) == 1.0

    def test_ease_in_out_elastic_endpoints(self):
        """Ease in/out elastic should return 0 and 1 at endpoints."""
        assert ease_in_out_elastic(0.0) == 0.0
        assert ease_in_out_elastic(1.0) == 1.0

    def test_ease_out_elastic_oscillates(self):
        """Ease out elastic should oscillate (overshoot)."""
        # Should go above 1.0 at some point
        values = [ease_out_elastic(t / 100.0) for t in range(101)]
        assert any(v > 1.0 for v in values)


class TestBackEasing:
    """Test back easing functions."""

    def test_ease_in_back_endpoints(self):
        """Ease in back should return 0 and 1 at endpoints."""
        assert ease_in_back(0.0) == pytest.approx(0.0)
        assert ease_in_back(1.0) == pytest.approx(1.0)

    def test_ease_out_back_endpoints(self):
        """Ease out back should return 0 and 1 at endpoints."""
        assert ease_out_back(0.0) == pytest.approx(0.0)
        assert ease_out_back(1.0) == pytest.approx(1.0)

    def test_ease_in_out_back_endpoints(self):
        """Ease in/out back should return 0 and 1 at endpoints."""
        assert ease_in_out_back(0.0) == pytest.approx(0.0)
        assert ease_in_out_back(1.0) == pytest.approx(1.0)

    def test_ease_in_back_overshoots(self):
        """Ease in back should go below 0."""
        values = [ease_in_back(t / 100.0) for t in range(101)]
        assert any(v < 0.0 for v in values)


class TestBounceEasing:
    """Test bounce easing functions."""

    def test_ease_in_bounce_endpoints(self):
        """Ease in bounce should return 0 and 1 at endpoints."""
        assert ease_in_bounce(0.0) == pytest.approx(0.0)
        assert ease_in_bounce(1.0) == pytest.approx(1.0)

    def test_ease_out_bounce_endpoints(self):
        """Ease out bounce should return 0 and 1 at endpoints."""
        assert ease_out_bounce(0.0) == pytest.approx(0.0)
        assert ease_out_bounce(1.0) == pytest.approx(1.0)

    def test_ease_in_out_bounce_endpoints(self):
        """Ease in/out bounce should return 0 and 1 at endpoints."""
        assert ease_in_out_bounce(0.0) == pytest.approx(0.0)
        assert ease_in_out_bounce(1.0) == pytest.approx(1.0)


class TestEaseFunction:
    """Test the main ease() function."""

    def test_ease_with_linear(self):
        """ease() should work with LINEAR type."""
        assert ease(0.5, EasingType.LINEAR) == 0.5

    def test_ease_with_quad(self):
        """ease() should work with quadratic types."""
        assert ease(0.5, EasingType.EASE_IN_QUAD) == 0.25
        assert ease(0.5, EasingType.EASE_OUT_QUAD) == 0.75

    def test_ease_clamps_input(self):
        """ease() should clamp input to [0, 1]."""
        assert ease(-0.5, EasingType.LINEAR) == 0.0
        assert ease(1.5, EasingType.LINEAR) == 1.0

    def test_ease_with_all_types(self):
        """ease() should work with all easing types."""
        for easing_type in EasingType:
            result = ease(0.5, easing_type)
            assert isinstance(result, float)

    def test_ease_endpoints_for_all_types(self):
        """All easing types should return 0 and 1 at endpoints."""
        for easing_type in EasingType:
            assert ease(0.0, easing_type) == pytest.approx(0.0, abs=1e-6)
            assert ease(1.0, easing_type) == pytest.approx(1.0, abs=1e-6)


class TestEasingMonotonicity:
    """Test that ease-in functions are monotonically increasing."""

    def test_ease_in_types_monotonic(self):
        """Ease-in types should be monotonically increasing."""
        ease_in_types = [
            EasingType.EASE_IN_QUAD,
            EasingType.EASE_IN_CUBIC,
            EasingType.EASE_IN_QUART,
            EasingType.EASE_IN_QUINT,
            EasingType.EASE_IN_SINE,
            EasingType.EASE_IN_CIRC,
        ]

        for easing_type in ease_in_types:
            prev_value = 0.0
            for t in range(101):
                current_value = ease(t / 100.0, easing_type)
                assert current_value >= prev_value
                prev_value = current_value
