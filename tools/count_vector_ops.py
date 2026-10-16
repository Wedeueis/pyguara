#!/usr/bin/env python3
"""Count the `Vector2` operations a frame performs, and what they cost.

The question RFC-0003's maths rewrite turns on: a Rust `Vector2` is worth
its compatibility risk only if enough code does vector arithmetic for the
per-operation saving to add up. See `docs/adr/0003-native-core-spike.md`.

Counts rather than times, because the counting wrappers would dominate any
timing. The implied cost is the count multiplied by per-operation figures
measured separately on this machine, so re-measure `COST_NS` before
trusting the millisecond column on different hardware.

    uv run python tools/count_vector_ops.py

Reports the hot systems. The demos are deliberately not included: the ones
that run without a GL context sit in menus and idle scenes (1-8 operations
a frame), and the vector-heavy ones need a GL context this cannot provide.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyguara.common.types import Color, Vector2  # noqa: E402
from pyguara.graphics.components.particles import ParticleSystem  # noqa: E402
from pyguara.graphics.vfx.sparks import Sparks  # noqa: E402

# Nanoseconds per operation, min of 5 x 200k on this machine.
COST_NS = {
    "__add__": 432.4,
    "__sub__": 432.4,
    "__mul__": 1115.1,
    "__rmul__": 1115.1,
    "__truediv__": 1115.1,
    "magnitude": 252.6,
    "sqr_magnitude": 252.6,
    "normalize": 1847.1,
    "__new__": 246.4,
}

_counts: dict[str, int] = {}


class _FakeTexture:
    """A texture the pools can hold without a GL context."""

    @property
    def width(self) -> int:
        """Width in pixels."""
        return 8

    @property
    def height(self) -> int:
        """Height in pixels."""
        return 8

    @property
    def native_handle(self) -> object:
        """Never bound; the pools only store it."""
        return self


def _instrument() -> None:
    """Wrap every counted operation on `Vector2`."""
    for name in ("__add__", "__sub__", "__mul__", "__rmul__", "__truediv__"):
        original = getattr(Vector2, name)

        def binary(
            self: Vector2, other: object, _o: object = original, _n: str = name
        ) -> object:
            _counts[_n] = _counts.get(_n, 0) + 1
            return _o(self, other)  # type: ignore[operator]

        setattr(Vector2, name, binary)

    original_new = Vector2.__new__

    def new(cls: type, *args: object, **kwargs: object) -> object:
        _counts["__new__"] = _counts.get("__new__", 0) + 1
        return original_new(cls, *args, **kwargs)  # type: ignore[arg-type]

    Vector2.__new__ = new  # type: ignore[assignment]

    for name in ("magnitude", "sqr_magnitude"):
        prop = getattr(Vector2, name, None)
        if isinstance(prop, property) and prop.fget is not None:

            def getter(self: Vector2, _f: object = prop.fget, _n: str = name) -> object:
                _counts[_n] = _counts.get(_n, 0) + 1
                return _f(self)  # type: ignore[operator]

            setattr(Vector2, name, property(getter))

    method = getattr(Vector2, "normalize", None)
    if callable(method):

        def normalize(
            self: Vector2, *a: object, _m: object = method, **k: object
        ) -> object:
            _counts["normalize"] = _counts.get("normalize", 0) + 1
            return _m(self, *a, **k)  # type: ignore[operator]

        Vector2.normalize = normalize  # type: ignore[assignment]


def _report(label: str, ticks: int) -> None:
    """Print operations per tick and the implied cost, then reset."""
    total = sum(_counts.values())
    nanoseconds = sum(_counts.get(k, 0) * COST_NS.get(k, 0) for k in _counts)
    busiest = sorted(_counts.items(), key=lambda kv: -kv[1])[:4]
    breakdown = " ".join(
        f"{name.strip('_')}={count / ticks:.0f}" for name, count in busiest if count
    )
    print(
        f"{label:34} {total / ticks:9.0f} {nanoseconds / ticks / 1e6:12.3f}"
        f"   {breakdown}"
    )
    _counts.clear()


def _particles(capacity: int, live: int) -> ParticleSystem:
    """A particle system with `live` slots occupied."""
    system = ParticleSystem(capacity=capacity)
    if live:
        system.emit(
            _FakeTexture(),  # type: ignore[arg-type]
            Vector2(0.0, 0.0),
            count=live,
            life=1e6,
        )
    return system


def _sparks(capacity: int, live: int) -> Sparks:
    """A spark pool with `live` slots occupied."""
    pool = Sparks(capacity=capacity)
    if live:
        pool.burst(Vector2(0.0, 0.0), count=live, life=1e6, color=Color(255, 255, 255))
    return pool


def main() -> int:
    """Count across flocking and the object pools.

    Returns:
        0 always; this reports rather than asserts.
    """
    _instrument()
    from tests.performance.conftest import build_flock, uniform_spread_for

    ticks = 10
    print(f"{'system':34} {'ops/tick':>9} {'implied ms':>12}   breakdown")

    for agents in (500, 1000, 2000):
        _, system = build_flock(agents, spread=uniform_spread_for(agents))
        system.update(1 / 60)  # settle, then count steady state
        _counts.clear()
        for _ in range(ticks):
            system.update(1 / 60)
        _report(f"FlockingSystem, {agents} agents", ticks)

    for label, pool in (
        ("ParticleSystem, 1000 live", _particles(1000, 1000)),
        ("ParticleSystem, 4000 live", _particles(4000, 4000)),
        ("Sparks, 1000 live", _sparks(1000, 1000)),
    ):
        pool.update(1 / 60)
        _counts.clear()
        for _ in range(ticks):
            pool.update(1 / 60)
        _report(label, ticks)

    return 0


if __name__ == "__main__":
    sys.exit(main())
