"""Taking a value apart into numbers, and putting it back as itself.

`Tween` interpolates numbers. Games tween `Vector2` positions and `Color`
tints, and the old answer was "tween the components and rebuild it
yourself" -- so every call site carried the same three lines, and
`Tween.current_value` handed back a plain tuple where a `Vector2` went in.
Writing that tuple back to `transform.position` is a bug that surfaces as
an `AttributeError` several frames later.

Decomposing here instead means one place knows that a `Color`'s channels
are bytes that must be rounded and clamped, that a `Vector2` is floats, and
that a plain tuple should come back a plain tuple.
"""

from typing import Any

from pyguara.common.types import Color, Vector2

Components = tuple[float, ...]


def is_scalar(value: object) -> bool:
    """Report whether a value is a plain number.

    `bool` is excluded although it is an `int` subclass: tweening True to
    False is never what anyone meant.

    Args:
        value: The value to test.

    Returns:
        True for an int or float that is not a bool.
    """
    return isinstance(value, int | float) and not isinstance(value, bool)


def decompose(value: Any) -> float | Components:
    """Reduce a value to the numbers an interpolation can work on.

    Args:
        value: A number, a `Vector2`, a `Color`, or any tuple/list of
            numbers.

    Returns:
        The number itself, or a tuple of its components.

    Raises:
        TypeError: If the value is not something this module can take
            apart. Raised here rather than at the first interpolation, so
            the message names the value the caller actually passed.
    """
    if is_scalar(value):
        return float(value)
    if isinstance(value, Color):
        return (float(value.r), float(value.g), float(value.b), float(value.a))
    if isinstance(value, tuple | list):
        # Vector2 is a tuple subclass, so it lands here.
        return tuple(float(component) for component in value)
    raise TypeError(
        f"Cannot interpolate a {type(value).__name__}. Supported: numbers, "
        f"Vector2, Color, and tuples or lists of numbers."
    )


def recompose(template: Any, components: float | Components) -> Any:
    """Rebuild a value of `template`'s type from interpolated numbers.

    The template is the *original* endpoint, not a type argument, because
    the shape has to come from somewhere and the endpoint is already in
    hand at every call site.

    Args:
        template: The value whose type the result should have.
        components: What `decompose` produced, after interpolation.

    Returns:
        A value of the same type as `template`.
    """
    if is_scalar(template) or is_scalar(components):
        return components
    assert isinstance(components, tuple)

    if isinstance(template, Color):
        # Color's own constructor rounds and clamps, which is exactly what
        # a fade overshooting 255 or dipping below 0 needs.
        return Color(*(int(round(component)) for component in components))
    if isinstance(template, Vector2):
        return Vector2(components[0], components[1])
    if isinstance(template, list):
        return list(components)
    return components


def interpolate(start: Any, end: Any, t: float) -> Any:
    """Interpolate between two values of the same shape.

    Args:
        start: The value at `t == 0`.
        end: The value at `t == 1`.
        t: Position between them, already eased. Not clamped -- an elastic
            or back easing deliberately overshoots, and clamping here would
            flatten exactly the part of the curve that makes those easings
            worth having.

    Returns:
        A value of `start`'s type.

    Raises:
        TypeError: If either value cannot be decomposed.
        ValueError: If the two shapes do not match.
    """
    raw_start = decompose(start)
    raw_end = decompose(end)

    if isinstance(raw_start, float) != isinstance(raw_end, float):
        raise ValueError(
            f"Cannot interpolate between a {type(start).__name__} and a "
            f"{type(end).__name__}: one is a number and the other is not."
        )

    if isinstance(raw_start, float) and isinstance(raw_end, float):
        return raw_start + (raw_end - raw_start) * t

    assert isinstance(raw_start, tuple) and isinstance(raw_end, tuple)
    if len(raw_start) != len(raw_end):
        raise ValueError(
            f"Cannot interpolate between values of different length: "
            f"{len(raw_start)} and {len(raw_end)}."
        )

    return recompose(
        start,
        tuple(s + (e - s) * t for s, e in zip(raw_start, raw_end, strict=True)),
    )
