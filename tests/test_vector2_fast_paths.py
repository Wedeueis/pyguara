"""`Vector2`'s operator fast paths against the long way round.

Each operator has a shortcut for the operand types game code passes and
falls through to `pymunk.Vec2d` for the rest. The shortcut must be
indistinguishable: same value to the last bit, same component types, same
exception. `_Reference` below is the class as it was before the shortcuts
existed, so this compares against the real former behaviour rather than a
description of it.

`repr` is the comparison, on purpose. It round-trips every float exactly,
tells `1` from `1.0`, and treats two NaNs as equal, which `==` does not.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from fractions import Fraction
from typing import Any

import pymunk
import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2


class _Reference(pymunk.Vec2d):
    """`Vector2`'s operators exactly as they were written before."""

    @property
    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y)

    def __add__(self, other: Any) -> Any:
        if hasattr(other, "x") and hasattr(other, "y"):
            return _Reference(self.x + other.x, self.y + other.y)
        v = super().__add__(other)
        return _Reference(v.x, v.y)

    def __sub__(self, other: Any) -> Any:
        if hasattr(other, "x") and hasattr(other, "y"):
            return _Reference(self.x - other.x, self.y - other.y)
        v = super().__sub__(other)
        return _Reference(v.x, v.y)

    def __mul__(self, other: Any) -> Any:
        v = super().__mul__(other)
        return _Reference(v.x, v.y)

    def __rmul__(self, other: Any) -> Any:
        v = super().__rmul__(other)
        return _Reference(v.x, v.y)

    def __truediv__(self, other: Any) -> Any:
        v = super().__truediv__(other)
        return _Reference(v.x, v.y)

    def __neg__(self) -> Any:
        return _Reference(-self.x, -self.y)

    def normalize(self) -> Any:
        v = super().normalized()
        return _Reference(v.x, v.y)


def _outcome(compute: Callable[[], Any]) -> str:
    """What an expression produced: its components and their types, or its error."""
    try:
        result = compute()
    except Exception as error:  # noqa: BLE001 - the error type is the result
        return f"raises {type(error).__name__}"
    if isinstance(result, tuple):
        return repr([(component, type(component).__name__) for component in result])
    return repr((result, type(result).__name__))


def _same(real: Callable[[], Any], reference: Callable[[], Any]) -> None:
    assert _outcome(real) == _outcome(reference)


AWKWARD = [0.0, -0.0, 1.0, -1.0, 0.1, 1e-320, 1e308, -1e308, math.inf, -math.inf, math.nan, 3, -7, 0]  # fmt: skip


def _values() -> list[tuple[Any, Any]]:
    stream = RandomStream(11)
    pairs: list[tuple[Any, Any]] = [(x, y) for x in AWKWARD for y in AWKWARD[::3]]
    pairs += [
        (stream.uniform(-1e6, 1e6), stream.uniform(-1e6, 1e6)) for _ in range(300)
    ]
    pairs += [(stream.uniform(-1, 1), stream.uniform(-1, 1)) for _ in range(300)]
    pairs += [(stream.randint(-50, 50), stream.randint(-50, 50)) for _ in range(60)]
    return pairs


VALUES = _values()
SCALARS: list[Any] = [*AWKWARD, 2.5, 1 / 3, 1e-9, 60, True, False, Fraction(1, 3), "2", None, (1, 2)]  # fmt: skip


class TestAgainstTheFormerOperators:
    def test_addition_and_subtraction_of_vectors(self) -> None:
        for (ax, ay), (bx, by) in zip(VALUES, reversed(VALUES), strict=True):
            a, b = Vector2(ax, ay), Vector2(bx, by)
            ra, rb = _Reference(ax, ay), _Reference(bx, by)
            _same(lambda a=a, b=b: a + b, lambda ra=ra, rb=rb: ra + rb)
            _same(lambda a=a, b=b: a - b, lambda ra=ra, rb=rb: ra - rb)

    def test_scaling_and_division(self) -> None:
        for x, y in VALUES[::7]:
            vector, reference = Vector2(x, y), _Reference(x, y)
            for scalar in SCALARS:
                _same(
                    lambda s=scalar, v=vector: v * s,
                    lambda s=scalar, r=reference: r * s,
                )
                _same(
                    lambda s=scalar, v=vector: s * v,
                    lambda s=scalar, r=reference: s * r,
                )
                _same(
                    lambda s=scalar, v=vector: v / s,
                    lambda s=scalar, r=reference: r / s,
                )

    def test_negation_and_normalisation(self) -> None:
        for x, y in VALUES:
            vector, reference = Vector2(x, y), _Reference(x, y)
            _same(lambda v=vector: -v, lambda r=reference: -r)
            _same(vector.normalize, reference.normalize)

    @pytest.mark.parametrize(
        "other",
        [
            pymunk.Vec2d(1.5, -2.0),
            (1.5, -2.0),
            [1.5, -2.0],
            (1, 2, 3),
            "ab",
            3.0,
            None,
        ],
    )
    def test_anything_that_is_not_a_vector_takes_the_old_route(
        self, other: Any
    ) -> None:
        vector, reference = Vector2(0.25, 8.0), _Reference(0.25, 8.0)

        _same(lambda: vector + other, lambda: reference + other)
        _same(lambda: vector - other, lambda: reference - other)


class TestTheResultIsStillAVector2:
    @pytest.mark.parametrize(
        "compute",
        [
            lambda v: v + v,
            lambda v: v - v,
            lambda v: v * 2.0,
            lambda v: 2 * v,
            lambda v: v / 4,
            lambda v: -v,
            lambda v: v.normalize(),
            lambda v: Vector2(0.0, 0.0).normalize(),
        ],
    )
    def test_type_hash_and_equality(self, compute: Any) -> None:
        result = compute(Vector2(3.0, 4.0))

        assert type(result) is Vector2
        assert isinstance(result, pymunk.Vec2d)
        assert result == Vector2(result.x, result.y)
        assert hash(result) == hash(Vector2(result.x, result.y))

    def test_an_int_times_a_vector_scales_it_rather_than_repeating_it(self) -> None:
        # `tuple.__mul__` would give (1.0, 2.0, 1.0, 2.0).
        assert Vector2(1.0, 2.0) * 2 == Vector2(2.0, 4.0)
        assert 2 * Vector2(1.0, 2.0) == Vector2(2.0, 4.0)
