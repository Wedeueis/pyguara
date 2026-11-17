"""Coloured shape particles: sparks, embers, splashes, debris.

A pool of short-lived primitives drawn through `IRenderer.draw_circle`
and `draw_line`, not as textured sprites. Use `ParticleSystem` when
particles are sprites; a spark has no texture, takes a colour per
primitive, and batches each shape type into one instanced draw.

The pool is held in Rust as arrays, and hands its primitives to a
renderer that can take them through `ShapeBatch`. It has no Python
implementation. See `docs/guides/performance.md`.

Example:
    sparks = Sparks()
    sparks.burst(position, Color(255, 180, 60), count=14, streak=True)
    sparks.update(dt)
    sparks.render(renderer, offset=shake_offset)
"""

from __future__ import annotations

import math
from typing import Any

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import IRenderer, ShapeBatchRenderer
from pyguara.graphics.types import ShapeBatch, ShapeKind
from pyguara.native import require_extension


class Sparks:
    """A pool of short-lived coloured particles."""

    def __init__(self, capacity: int = 320, rng: RandomStream | None = None) -> None:
        """Pre-allocate the pool.

        Args:
            capacity: Maximum particles alive at once. A burst that would
                exceed it drops the excess rather than growing, the same
                way `ParticleSystem` does.
            rng: Random stream driving spread and speed jitter.

        Raises:
            RuntimeError: If the native extension cannot be imported.
        """
        self._capacity = capacity
        self._rng = rng if rng is not None else RandomStream()
        self._native: Any = require_extension("Sparks").NativeSparkPool(capacity)

    @property
    def live_count(self) -> int:
        """How many sparks are currently alive."""
        return int(self._native.live_count())

    def burst(
        self,
        position: Vector2,
        color: Color,
        *,
        count: int = 12,
        speed: float = 160.0,
        speed_jitter: float = 0.55,
        direction: float | None = None,
        spread: float = math.tau,
        life: float = 0.55,
        radius: float = 3.0,
        gravity: float = 220.0,
        drag: float = 0.92,
        streak: bool = False,
    ) -> None:
        """Emit a burst of particles from one point.

        Args:
            position: Screen-space origin.
            color: Starting colour; alpha fades to zero over `life`.
            count: How many particles to emit.
            speed: Base speed in pixels per second.
            speed_jitter: Fraction of `speed` to vary each particle by.
            direction: Centre angle in radians, or None for a full circle.
            spread: Angular width of the cone around `direction`.
            life: Seconds each particle lives.
            radius: Particle radius in pixels.
            gravity: Downward acceleration in pixels per second squared.
            drag: Per-frame velocity retention; below 1.0 slows them down.
            streak: Draw each particle as a short line along its velocity
                instead of a dot -- right for rain splashes and embers.
        """
        # The random draws stay in Python: a burst takes three per spark
        # from the engine's seeded stream, and a replay restores that seed.
        # Only as many sparks as will fit are drawn for, so a burst that
        # overflows leaves the stream where a smaller one would have.
        spawnable = min(count, self._capacity - int(self._native.live_count()))

        velocity_x: list[float] = []
        velocity_y: list[float] = []
        lives: list[float] = []
        for _ in range(spawnable):
            if direction is None:
                angle = self._rng.uniform(0.0, math.tau)
            else:
                angle = direction + self._rng.uniform(-spread / 2, spread / 2)
            magnitude = speed * (1.0 + self._rng.uniform(-speed_jitter, speed_jitter))
            velocity_x.append(math.cos(angle) * magnitude)
            velocity_y.append(math.sin(angle) * magnitude)
            lives.append(life * (1.0 + self._rng.uniform(-0.25, 0.25)))

        self._native.burst(
            position.x,
            position.y,
            velocity_x,
            velocity_y,
            lives,
            radius,
            (color.r, color.g, color.b, color.a),
            gravity,
            drag,
            streak,
        )

    def update(self, dt: float) -> None:
        """Integrate every live particle and retire the expired ones.

        Args:
            dt: Seconds since the last frame.
        """
        self._native.update(dt)

    def render(self, renderer: IRenderer, offset: Vector2 = Vector2.zero()) -> None:
        """Draw every live particle.

        A renderer that implements `ShapeBatchRenderer` receives two calls
        for the whole pool, with the primitives packed in Rust. Any other
        renderer gets one call per spark.

        Args:
            renderer: Target renderer, batched if it can be.
            offset: Screen-space offset applied to every particle, so the
                sparks shake with the rest of the arena.
        """
        if isinstance(renderer, ShapeBatchRenderer):
            circles, lines = self._native.pack_rows(offset.x, offset.y)
            if circles:
                renderer.render_shapes(ShapeBatch(ShapeKind.CIRCLE, circles))
            if lines:
                renderer.render_shapes(ShapeBatch(ShapeKind.LINE, lines))
            return

        dots, streaks = self._native.pack_draw_calls(offset.x, offset.y)
        for x, y, dot_radius, dot_color in dots:
            renderer.draw_circle(Vector2(x, y), dot_radius, Color(*dot_color))
        for start_x, start_y, end_x, end_y, width, line_color in streaks:
            renderer.draw_line(
                Vector2(start_x, start_y),
                Vector2(end_x, end_y),
                Color(*line_color),
                width=width,
            )
