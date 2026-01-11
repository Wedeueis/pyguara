"""Easing functions for smooth animations and transitions.

Provides a comprehensive set of easing functions for interpolating values.
All functions take a normalized time value t ∈ [0, 1] and return an eased value.
"""

import math
from enum import Enum, auto


class EasingType(Enum):
    """Available easing function types."""

    # Basic
    LINEAR = auto()

    # Quadratic
    EASE_IN_QUAD = auto()
    EASE_OUT_QUAD = auto()
    EASE_IN_OUT_QUAD = auto()

    # Cubic
    EASE_IN_CUBIC = auto()
    EASE_OUT_CUBIC = auto()
    EASE_IN_OUT_CUBIC = auto()

    # Quartic
    EASE_IN_QUART = auto()
    EASE_OUT_QUART = auto()
    EASE_IN_OUT_QUART = auto()

    # Quintic
    EASE_IN_QUINT = auto()
    EASE_OUT_QUINT = auto()
    EASE_IN_OUT_QUINT = auto()

    # Sine
    EASE_IN_SINE = auto()
    EASE_OUT_SINE = auto()
    EASE_IN_OUT_SINE = auto()

    # Exponential
    EASE_IN_EXPO = auto()
    EASE_OUT_EXPO = auto()
    EASE_IN_OUT_EXPO = auto()

    # Circular
    EASE_IN_CIRC = auto()
    EASE_OUT_CIRC = auto()
    EASE_IN_OUT_CIRC = auto()

    # Elastic
    EASE_IN_ELASTIC = auto()
    EASE_OUT_ELASTIC = auto()
    EASE_IN_OUT_ELASTIC = auto()

    # Back
    EASE_IN_BACK = auto()
    EASE_OUT_BACK = auto()
    EASE_IN_OUT_BACK = auto()

    # Bounce
    EASE_IN_BOUNCE = auto()
    EASE_OUT_BOUNCE = auto()
    EASE_IN_OUT_BOUNCE = auto()


def linear(t: float) -> float:
    """Linear interpolation (no easing)."""
    return t


def ease_in_quad(t: float) -> float:
    """Quadratic ease in (accelerating from zero)."""
    return t * t


def ease_out_quad(t: float) -> float:
    """Quadratic ease out (decelerating to zero)."""
    return t * (2.0 - t)


def ease_in_out_quad(t: float) -> float:
    """Quadratic ease in/out (acceleration until halfway, then deceleration)."""
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - 2.0 * (1.0 - t) * (1.0 - t)


def ease_in_cubic(t: float) -> float:
    """Cubic ease in."""
    return t * t * t


def ease_out_cubic(t: float) -> float:
    """Cubic ease out."""
    return 1.0 + (t - 1.0) ** 3


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease in/out."""
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 + 4.0 * (t - 1.0) ** 3


def ease_in_quart(t: float) -> float:
    """Quartic ease in."""
    return t * t * t * t


def ease_out_quart(t: float) -> float:
    """Quartic ease out."""
    return 1.0 - (1.0 - t) ** 4


def ease_in_out_quart(t: float) -> float:
    """Quartic ease in/out."""
    if t < 0.5:
        return 8.0 * t * t * t * t
    return 1.0 - 8.0 * (1.0 - t) ** 4


def ease_in_quint(t: float) -> float:
    """Quintic ease in."""
    return t * t * t * t * t


def ease_out_quint(t: float) -> float:
    """Quintic ease out."""
    return 1.0 + (t - 1.0) ** 5


def ease_in_out_quint(t: float) -> float:
    """Quintic ease in/out."""
    if t < 0.5:
        return 16.0 * t * t * t * t * t
    return 1.0 + 16.0 * (t - 1.0) ** 5


def ease_in_sine(t: float) -> float:
    """Sinusoidal ease in."""
    return 1.0 - math.cos(t * math.pi / 2.0)


def ease_out_sine(t: float) -> float:
    """Sinusoidal ease out."""
    return math.sin(t * math.pi / 2.0)


def ease_in_out_sine(t: float) -> float:
    """Sinusoidal ease in/out."""
    return 0.5 * (1.0 - math.cos(t * math.pi))


def ease_in_expo(t: float) -> float:
    """Exponential ease in."""
    if t == 0.0:
        return 0.0
    return math.pow(2.0, 10.0 * (t - 1.0))


def ease_out_expo(t: float) -> float:
    """Exponential ease out."""
    if t == 1.0:
        return 1.0
    return 1.0 - math.pow(2.0, -10.0 * t)


def ease_in_out_expo(t: float) -> float:
    """Exponential ease in/out."""
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0

    if t < 0.5:
        return 0.5 * math.pow(2.0, 20.0 * t - 10.0)
    return 0.5 * (2.0 - math.pow(2.0, -20.0 * t + 10.0))


def ease_in_circ(t: float) -> float:
    """Circular ease in."""
    return 1.0 - math.sqrt(1.0 - t * t)


def ease_out_circ(t: float) -> float:
    """Circular ease out."""
    return math.sqrt(1.0 - (t - 1.0) * (t - 1.0))


def ease_in_out_circ(t: float) -> float:
    """Circular ease in/out."""
    if t < 0.5:
        return 0.5 * (1.0 - math.sqrt(1.0 - 4.0 * t * t))
    return 0.5 * (math.sqrt(1.0 - 4.0 * (t - 1.0) * (t - 1.0)) + 1.0)


def ease_in_elastic(t: float) -> float:
    """Elastic ease in (like a spring)."""
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0

    return -math.pow(2.0, 10.0 * t - 10.0) * math.sin(
        (t * 10.0 - 10.75) * (2.0 * math.pi) / 3.0
    )


def ease_out_elastic(t: float) -> float:
    """Elastic ease out (like a spring)."""
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0

    return (
        math.pow(2.0, -10.0 * t) * math.sin((t * 10.0 - 0.75) * (2.0 * math.pi) / 3.0)
        + 1.0
    )


def ease_in_out_elastic(t: float) -> float:
    """Elastic ease in/out."""
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0

    c5 = (2.0 * math.pi) / 4.5

    if t < 0.5:
        return (
            -(math.pow(2.0, 20.0 * t - 10.0) * math.sin((20.0 * t - 11.125) * c5)) / 2.0
        )
    return (
        math.pow(2.0, -20.0 * t + 10.0) * math.sin((20.0 * t - 11.125) * c5)
    ) / 2.0 + 1.0


def ease_in_back(t: float) -> float:
    """Back ease in (overshoot)."""
    c1 = 1.70158
    c3 = c1 + 1.0
    return c3 * t * t * t - c1 * t * t


def ease_out_back(t: float) -> float:
    """Back ease out (overshoot)."""
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def ease_in_out_back(t: float) -> float:
    """Back ease in/out (overshoot)."""
    c1 = 1.70158
    c2 = c1 * 1.525

    if t < 0.5:
        return (2.0 * t) ** 2 * ((c2 + 1.0) * 2.0 * t - c2) / 2.0
    return ((2.0 * t - 2.0) ** 2 * ((c2 + 1.0) * (t * 2.0 - 2.0) + c2) + 2.0) / 2.0


def ease_out_bounce(t: float) -> float:
    """Bounce ease out."""
    n1 = 7.5625
    d1 = 2.75

    if t < 1.0 / d1:
        return n1 * t * t
    elif t < 2.0 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1
        return n1 * t * t + 0.984375


def ease_in_bounce(t: float) -> float:
    """Bounce ease in."""
    return 1.0 - ease_out_bounce(1.0 - t)


def ease_in_out_bounce(t: float) -> float:
    """Bounce ease in/out."""
    if t < 0.5:
        return (1.0 - ease_out_bounce(1.0 - 2.0 * t)) / 2.0
    return (1.0 + ease_out_bounce(2.0 * t - 1.0)) / 2.0


def ease(t: float, easing_type: EasingType) -> float:
    """Apply easing function to normalized time.

    Args:
        t: Normalized time value [0, 1]
        easing_type: Type of easing to apply

    Returns:
        Eased value (typically [0, 1], but some functions may overshoot)
    """
    # Clamp input
    t = max(0.0, min(1.0, t))

    # Map enum to function
    easing_map = {
        EasingType.LINEAR: linear,
        EasingType.EASE_IN_QUAD: ease_in_quad,
        EasingType.EASE_OUT_QUAD: ease_out_quad,
        EasingType.EASE_IN_OUT_QUAD: ease_in_out_quad,
        EasingType.EASE_IN_CUBIC: ease_in_cubic,
        EasingType.EASE_OUT_CUBIC: ease_out_cubic,
        EasingType.EASE_IN_OUT_CUBIC: ease_in_out_cubic,
        EasingType.EASE_IN_QUART: ease_in_quart,
        EasingType.EASE_OUT_QUART: ease_out_quart,
        EasingType.EASE_IN_OUT_QUART: ease_in_out_quart,
        EasingType.EASE_IN_QUINT: ease_in_quint,
        EasingType.EASE_OUT_QUINT: ease_out_quint,
        EasingType.EASE_IN_OUT_QUINT: ease_in_out_quint,
        EasingType.EASE_IN_SINE: ease_in_sine,
        EasingType.EASE_OUT_SINE: ease_out_sine,
        EasingType.EASE_IN_OUT_SINE: ease_in_out_sine,
        EasingType.EASE_IN_EXPO: ease_in_expo,
        EasingType.EASE_OUT_EXPO: ease_out_expo,
        EasingType.EASE_IN_OUT_EXPO: ease_in_out_expo,
        EasingType.EASE_IN_CIRC: ease_in_circ,
        EasingType.EASE_OUT_CIRC: ease_out_circ,
        EasingType.EASE_IN_OUT_CIRC: ease_in_out_circ,
        EasingType.EASE_IN_ELASTIC: ease_in_elastic,
        EasingType.EASE_OUT_ELASTIC: ease_out_elastic,
        EasingType.EASE_IN_OUT_ELASTIC: ease_in_out_elastic,
        EasingType.EASE_IN_BACK: ease_in_back,
        EasingType.EASE_OUT_BACK: ease_out_back,
        EasingType.EASE_IN_OUT_BACK: ease_in_out_back,
        EasingType.EASE_IN_BOUNCE: ease_in_bounce,
        EasingType.EASE_OUT_BOUNCE: ease_out_bounce,
        EasingType.EASE_IN_OUT_BOUNCE: ease_in_out_bounce,
    }

    func = easing_map.get(easing_type, linear)
    return func(t)
