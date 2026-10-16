#!/usr/bin/env python3
"""Can pymunk accept a `Vector2` that is not a `pymunk.Vec2d` subclass?

RFC-0003 (`project/backlog/active/rust_core.md`) reimplements `Vector2` as a
PyO3 `#[pyclass]` wrapping `glam::Vec2`, and states that tuple unpacking
keeps "compatibilidade total com o Pymunk CFFI". This answers that question
by asking pymunk, because the answer decides whether the RFC's Marco 1 is a
speedup or a tax -- see `docs/adr/0003-native-core-spike.md`, finding 1.

Kept as a tool rather than a test: it describes a dependency's behaviour
rather than ours, and it is the kind of claim someone will want to re-run
against a future pymunk before trusting an ADR written against 7.2.0.

    uv run python tools/preflight_pymunk_vector.py

Exits non-zero if any entry point rejects the stand-in, which today is the
expected result.
"""

from __future__ import annotations

import sys
from typing import Any

import pymunk


class RustLikeVector2:
    """What a PyO3 pyclass can offer: the sequence protocol, no Vec2d ancestry.

    A `#[pyclass]` can implement `__iter__`, `__len__` and `__getitem__`. It
    cannot extend a variable-length built-in like `tuple`, which is what
    `pymunk.Vec2d` is -- and that turns out to be the thing that matters.
    """

    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        """Store the components as plain floats."""
        self.x = float(x)
        self.y = float(y)

    def __iter__(self) -> Any:
        """Yield x then y, so tuple unpacking works."""
        yield self.x
        yield self.y

    def __len__(self) -> int:
        """Two components."""
        return 2

    def __getitem__(self, index: int) -> float:
        """Index as a 2-sequence."""
        return (self.x, self.y)[index]


def main() -> int:
    """Try every pymunk entry point the engine passes a vector to.

    Returns:
        0 if all of them accept the stand-in, 1 otherwise.
    """
    vector = RustLikeVector2(3.0, 4.0)
    other = RustLikeVector2(9.0, 9.0)
    space = pymunk.Space()
    body = pymunk.Body(1.0, 1.0)
    space.add(body)

    attempts: list[tuple[str, Any]] = [
        ("body.position = v", lambda: setattr(body, "position", vector)),
        ("body.velocity = v", lambda: setattr(body, "velocity", vector)),
        ("space.gravity = v", lambda: setattr(space, "gravity", vector)),
        (
            "body.apply_impulse_at_local_point(v)",
            lambda: body.apply_impulse_at_local_point(vector),
        ),
        (
            "body.apply_force_at_world_point(v, v)",
            lambda: body.apply_force_at_world_point(vector, vector),
        ),
        ("pymunk.Circle(body, 5, v)", lambda: pymunk.Circle(body, 5.0, vector)),
        (
            "pymunk.Transform(tx=v.x, ty=v.y)",
            lambda: pymunk.Transform(tx=vector.x, ty=vector.y),
        ),
        (
            "pymunk.Poly(body, [v, v, v])",
            lambda: pymunk.Poly(
                body,
                [RustLikeVector2(0, 0), RustLikeVector2(1, 0), RustLikeVector2(1, 1)],
            ),
        ),
        (
            "space.point_query_nearest(v, 10, filter)",
            lambda: space.point_query_nearest(vector, 10.0, pymunk.ShapeFilter()),
        ),
        (
            "space.segment_query_first(v, v2, 0, filter)",
            lambda: space.segment_query_first(vector, other, 0.0, pymunk.ShapeFilter()),
        ),
    ]

    width = max(len(label) for label, _ in attempts)
    rejected = 0
    for label, attempt in attempts:
        try:
            attempt()
            print(f"  {label:<{width}}  OK")
        except Exception as error:  # noqa: BLE001 - reporting, not handling
            rejected += 1
            print(f"  {label:<{width}}  REJECTED  {type(error).__name__}: {error}")

    print(
        f"\n{rejected} of {len(attempts)} pymunk entry points reject a "
        f"non-Vec2d vector."
    )
    print(f"Vector2's MRO today: {[c.__name__ for c in pymunk.Vec2d.__mro__]}")
    print(
        "`Vec2d` is a tuple subclass, which is why CFFI accepts it and why a "
        "pyclass cannot stand in for it."
    )
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
