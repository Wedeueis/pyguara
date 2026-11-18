"""The Rust `Vector2` against the Python it replaced, in `tests/reference/`.

Every method, on awkward values and on random ones, must give the same
floats to the last bit or raise the same exception. `repr` is the
comparison: it round-trips every float exactly and treats two NaNs as the
same, which `==` does not.
"""

from __future__ import annotations

import copy
import math
import pickle
from collections.abc import Callable
from typing import Any

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from tests.reference.vector2 import ReferenceVector2

AWKWARD = [0.0, -0.0, 1.0, -1.0, 0.1, 3.0, -7.0, 1e-320, 1e308, -1e308, math.inf, -math.inf, math.nan]  # fmt: skip


def _values() -> list[tuple[float, float]]:
    rng = RandomStream(7)
    pairs = [(x, y) for x in AWKWARD for y in AWKWARD[::3]]
    pairs += [(rng.uniform(-1e4, 1e4), rng.uniform(-1e4, 1e4)) for _ in range(400)]
    pairs += [(rng.uniform(-1, 1), rng.uniform(-1e-6, 1e-6)) for _ in range(100)]
    return pairs


VALUES = _values()
SCALARS = [*AWKWARD, 0.5, 2.0, 1e-3, 37.5, -2.25]


def _outcome(compute: Callable[..., Any], *arguments: Any) -> str:
    try:
        result = compute(*arguments)
    except Exception as error:  # noqa: BLE001 - the type is the comparison
        return f"raises {type(error).__name__}"
    if isinstance(result, tuple):
        return repr(tuple(_spell(item) for item in result))
    return _spell(result)


def _spell(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{type(value).__name__}:{value!r}"
    return repr(value)


def _agree(method: Callable[[Any], Any]) -> None:
    """Apply `method` to every value as a Vector2 and as the reference."""
    for x, y in VALUES:
        real = _outcome(lambda: method(Vector2(x, y)))  # noqa: B023 - called at once
        reference = _outcome(lambda: method(ReferenceVector2(x, y)))  # noqa: B023
        assert real == reference, (x, y)


def _agree_with(method: Callable[[Any, Any], Any]) -> None:
    """Apply `method` to pairs of values, the second shifted along."""
    shifted = VALUES[5:] + VALUES[:5]
    for (ax, ay), (bx, by) in zip(VALUES, shifted, strict=True):
        real = _outcome(method, Vector2(ax, ay), Vector2(bx, by))
        reference = _outcome(method, ReferenceVector2(ax, ay), ReferenceVector2(bx, by))
        assert real == reference, ((ax, ay), (bx, by))


def _agree_scaled(method: Callable[[Any, float], Any]) -> None:
    """Apply `method` with every scalar, on a sample of the values."""
    for x, y in VALUES[::5]:
        for scalar in SCALARS:
            real = _outcome(method, Vector2(x, y), scalar)
            reference = _outcome(method, ReferenceVector2(x, y), scalar)
            assert real == reference, ((x, y), scalar)


UNARY = {
    "neg": lambda v: -v,
    "pos": lambda v: +v,
    "abs": abs,
    "bool": bool,
    "length": lambda v: v.length,
    "magnitude": lambda v: v.magnitude,
    "length_squared": lambda v: v.length_squared,
    "sqr_magnitude": lambda v: v.sqr_magnitude,
    "angle": lambda v: v.angle,
    "angle_degrees": lambda v: v.angle_degrees,
    "polar_tuple": lambda v: v.polar_tuple,
    "int_tuple": lambda v: v.int_tuple,
    "normalize": lambda v: v.normalize(),
    "normalized": lambda v: v.normalized(),
    "normalized_and_length": lambda v: v.normalized_and_length(),
    "perpendicular": lambda v: v.perpendicular(),
    "perpendicular_normal": lambda v: v.perpendicular_normal(),
    "to_tuple": lambda v: v.to_tuple(),
    "to_int_tuple": lambda v: v.to_int_tuple(),
}

BINARY = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "add a tuple": lambda a, b: a + (b.x, b.y),
    "radd a tuple": lambda a, b: (b.x, b.y) + a,
    "rsub a list": lambda a, b: [b.x, b.y] - a,
    "dot": lambda a, b: a.dot(b),
    "cross": lambda a, b: a.cross(b),
    "get_distance": lambda a, b: a.get_distance(b),
    "distance_to": lambda a, b: a.distance_to(b),
    "get_distance_squared": lambda a, b: a.get_distance_squared(b),
    "get_angle_between": lambda a, b: a.get_angle_between(b),
    "get_angle_degrees_between": lambda a, b: a.get_angle_degrees_between(b),
    "projection": lambda a, b: a.projection(b),
    "reject": lambda a, b: a.reject(b),
    "convert_to_basis": lambda a, b: a.convert_to_basis(b, b.perpendicular()),
    "cpvrotate": lambda a, b: a.cpvrotate(b),
    "cpvunrotate": lambda a, b: a.cpvunrotate(b),
    "reflect": lambda a, b: a.reflect(b),
    "lerp": lambda a, b: a.lerp(b, 0.3),
    "interpolate_to": lambda a, b: a.interpolate_to(b, 1.7),
    "move_towards": lambda a, b: a.move_towards(b, 12.5),
    "snapped to a vector": lambda a, b: a.snapped(b),
}

SCALED = {
    "mul": lambda v, s: v * s,
    "rmul": lambda v, s: s * v,
    "truediv": lambda v, s: v / s,
    "floordiv": lambda v, s: v // s,
    "rotated": lambda v, s: v.rotated(s),
    "rotated_degrees": lambda v, s: v.rotated_degrees(s),
    "rotate_degrees": lambda v, s: v.rotate_degrees(s),
    "scale_to_length": lambda v, s: v.scale_to_length(s),
    "clamp_magnitude": lambda v, s: v.clamp_magnitude(s),
    "snapped": lambda v, s: v.snapped(s),
}


@pytest.mark.parametrize("name", UNARY)
def test_every_unary_method_agrees(name: str) -> None:
    _agree(UNARY[name])


@pytest.mark.parametrize("name", BINARY)
def test_every_method_on_two_vectors_agrees(name: str) -> None:
    _agree_with(BINARY[name])


@pytest.mark.parametrize("name", SCALED)
def test_every_method_with_a_scalar_agrees(name: str) -> None:
    _agree_scaled(SCALED[name])


@pytest.mark.parametrize("scalar", SCALARS)
def test_the_constructors_from_an_angle_agree(scalar: float) -> None:
    for length in (1.0, 2.5, -3.0, 0.0):
        assert _outcome(Vector2.from_polar, length, scalar) == _outcome(
            ReferenceVector2.from_polar, length, scalar
        )
        assert _outcome(Vector2.from_angle_degrees, scalar, length) == _outcome(
            ReferenceVector2.from_angle_degrees, scalar, length
        )


class TestItIsStillTheTupleItWas:
    """What code wrote against a tuple subclass keeps working."""

    def test_it_equals_and_hashes_as_its_tuple(self) -> None:
        for x, y in VALUES:
            if math.isnan(x) or math.isnan(y):
                continue
            assert Vector2(x, y) == (x, y)
            assert hash(Vector2(x, y)) == hash((x, y))
        assert {(1, 2): "found"}[Vector2(1, 2)] == "found"
        assert Vector2(1, 2) != (1, 3)
        assert Vector2(1, 2) != (1, 2, 3)

    def test_a_list_is_not_equal_to_it_as_a_tuple_was_not(self) -> None:
        assert Vector2(1, 2) != [1, 2]

    def test_it_unpacks_indexes_and_has_a_length(self) -> None:
        x, y = Vector2(3, 4)
        assert (x, y) == (3.0, 4.0)
        assert (Vector2(3, 4)[0], Vector2(3, 4)[-1], len(Vector2(3, 4))) == (
            3.0,
            4.0,
            2,
        )
        with pytest.raises(IndexError):
            Vector2(3, 4)[2]

    def test_it_round_trips_through_pickle_and_copy(self) -> None:
        vector = Vector2(-0.0, 1e-320)
        assert repr(pickle.loads(pickle.dumps(vector))) == repr(vector)
        assert copy.deepcopy(vector) is vector

    def test_every_component_reads_back_exactly(self) -> None:
        """`x` and `y` are member descriptors at a measured offset."""
        for x, y in VALUES:
            vector = Vector2(x, y)
            assert (repr(vector.x), repr(vector.y)) == (repr(x), repr(y))
            assert (repr(vector[0]), repr(vector[-1])) == (repr(x), repr(y))
            computed = vector + Vector2(0.0, 0.0)
            assert repr((computed.x, computed.y)) == repr((x + 0.0, y + 0.0))

    def test_its_components_are_always_floats(self) -> None:
        assert [type(value) for value in Vector2(1, 2)] == [float, float]
        assert Vector2(True, 2).x == 1.0

    def test_a_non_number_is_refused_at_construction(self) -> None:
        with pytest.raises(TypeError):
            Vector2("1", 2)  # type: ignore[arg-type]

    def test_multiplying_two_vectors_is_refused(self) -> None:
        with pytest.raises(TypeError):
            Vector2(1, 2) * Vector2(1, 2)  # type: ignore[operator]

    def test_an_object_with_x_and_y_is_a_coordinate(self) -> None:
        class Point:
            x = 1.5
            y = -2.0

        assert Vector2(1, 1) + Point() == Vector2(2.5, -1.0)  # type: ignore[operator]

    def test_it_is_immutable(self) -> None:
        with pytest.raises(AttributeError):
            Vector2(1, 2).x = 3  # type: ignore[misc]
