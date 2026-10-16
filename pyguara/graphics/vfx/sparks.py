"""Coloured shape particles: sparks, embers, splashes, debris.

A pool of short-lived primitives drawn through `IRenderer.draw_circle` and
`draw_line` rather than as textured sprites.

`ParticleSystem` is the right tool when particles *are* sprites. These are
not: a spark has no texture to bind, and none worth authoring for a
two-pixel dot. The shape path takes a colour per primitive, binds no
texture at all, and still batches each shape type into one instanced draw
call, so an ember, a blood spray or a rain splash costs less through
shapes than through sprites.

This module once justified itself differently -- that ModernGL's sprite
path carried no per-instance tint, so a textured particle could only ever
be white. That was true, and is no longer: the GL sprite path packs an
RGBA tint per instance. The reasoning above is the one that survives it.

Typical use, composed into a scene rather than resolved from DI::

    sparks = Sparks()
    sparks.burst(position, Color(255, 180, 60), count=14, streak=True)
    sparks.update(dt)
    sparks.render(renderer, offset=shake_offset)

Backed by the optional native pool when the extension is built, which is
13-20x on a spark frame. Unlike `ParticleSystem`, most of that comes from
the *render* half: a spark costs a whole `draw_circle` or `draw_line` call
where a particle costs a share of one batch, so 55-71% of a Python spark
frame is call overhead. The native path packs the primitives in Rust and
hands them over through `ShapeBatch`, which is why that type exists. A
renderer that cannot take a batch still gets one call per spark, and the
pure-Python pool runs when there is no extension at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import IRenderer, ShapeBatchRenderer
from pyguara.graphics.types import ShapeBatch, ShapeKind
from pyguara.native import native_module


@dataclass(slots=True)
class _Spark:
    """One pooled particle. Inactive entries keep their storage."""

    position: Vector2 = field(default_factory=Vector2.zero)
    velocity: Vector2 = field(default_factory=Vector2.zero)
    life: float = 0.0
    life_total: float = 1.0
    radius: float = 2.0
    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    gravity: float = 0.0
    drag: float = 1.0
    streak: bool = False
    active: bool = False


class Sparks:
    """A pool of short-lived coloured particles."""

    def __init__(
        self,
        capacity: int = 320,
        rng: RandomStream | None = None,
        *,
        accelerate: bool | None = None,
    ) -> None:
        """Pre-allocate the pool.

        Args:
            capacity: Maximum particles alive at once. A burst that would
                exceed it drops the excess rather than growing, the same
                way `ParticleSystem` does.
            rng: Random stream driving spread and speed jitter.
            accelerate: Whether to back the pool with the native
                structure-of-arrays pool. None, the default, defers to the
                engine-wide setting -- `PerformanceConfig.native_acceleration`,
                resolved once at bootstrap -- so a game decides this in one
                place rather than per pool. True demands the extension and
                raises if it is missing; False forces the Python pool.
                Both are overrides for tests and for the parity suite,
                not a second configuration surface.

        Raises:
            RuntimeError: If `accelerate=True` and the extension is absent.
        """
        self._capacity = capacity
        self._next = 0
        self._rng = rng if rng is not None else RandomStream()

        native = native_module() if accelerate is not False else None
        if accelerate and native is None:
            raise RuntimeError(
                "accelerate=True but the native extension is not available. "
                "Build it with `cargo build --release`, or leave "
                "`accelerate` unset to fall back to Python."
            )
        self._native = native.NativeSparkPool(capacity) if native else None

        # Only the Python path has per-spark objects. Kept as `_pool` for
        # the code that has always read it; empty under acceleration, where
        # `live_count` is the way to ask.
        self._pool: list[_Spark] = (
            [] if self._native is not None else [_Spark() for _ in range(capacity)]
        )

    @property
    def accelerated(self) -> bool:
        """Whether this pool is backed by the native extension."""
        return self._native is not None

    @property
    def live_count(self) -> int:
        """How many sparks are currently alive.

        The way to ask on either path: the Python pool exposes `_pool` and
        the native one has no per-spark objects to expose.
        """
        if self._native is not None:
            return int(self._native.live_count())
        return sum(1 for spark in self._pool if spark.active)

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
        if self._native is not None:
            self._burst_native(
                position,
                color,
                count,
                speed,
                speed_jitter,
                direction,
                spread,
                life,
                radius,
                gravity,
                drag,
                streak,
            )
            return

        for _ in range(count):
            spark = self._acquire()
            if spark is None:
                return

            if direction is None:
                angle = self._rng.uniform(0.0, math.tau)
            else:
                angle = direction + self._rng.uniform(-spread / 2, spread / 2)
            magnitude = speed * (1.0 + self._rng.uniform(-speed_jitter, speed_jitter))

            spark.position = position
            spark.velocity = Vector2(
                math.cos(angle) * magnitude, math.sin(angle) * magnitude
            )
            spark.life = life * (1.0 + self._rng.uniform(-0.25, 0.25))
            spark.life_total = spark.life
            spark.radius = radius
            spark.color = color
            spark.gravity = gravity
            spark.drag = drag
            spark.streak = streak
            spark.active = True

    def _burst_native(
        self,
        position: Vector2,
        color: Color,
        count: int,
        speed: float,
        speed_jitter: float,
        direction: float | None,
        spread: float,
        life: float,
        radius: float,
        gravity: float,
        drag: float,
        streak: bool,
    ) -> None:
        """Emit a burst into the native pool, in one crossing.

        **The random draws stay here on purpose**, for the reason
        `ParticleSystem._emit_native` gives: a burst takes three draws per
        spark from the engine's seeded stream, and a replay reproduces a
        run by restoring that seed. Drawing them in Rust would put them
        outside what the seed controls. They are computed here and handed
        over as whole arrays, so this is one FFI call however many sparks
        it spawns.

        **Only as many as will fit are drawn for**, because the Python pool
        draws nothing for a spark it cannot place -- it asks for a slot
        first and gives up when there is none. Drawing `count` sets
        regardless would leave the two paths' streams at different
        positions after any burst that overflowed, and every later burst
        would then differ.

        Args:
            position: Screen-space origin.
            color: Starting colour.
            count: How many to emit; the pool takes what it can fit.
            speed: Base speed in pixels per second.
            speed_jitter: Fraction of `speed` to vary each spark by.
            direction: Centre angle in radians, or None for a full circle.
            spread: Angular width of the cone around `direction`.
            life: Seconds each spark lives, jittered per spark.
            radius: Spark radius in pixels.
            gravity: Downward acceleration.
            drag: Per-frame velocity retention.
            streak: Draw as a line along the velocity rather than a dot.
        """
        assert self._native is not None
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
        if self._native is not None:
            self._native.update(dt)
            return

        for spark in self._pool:
            if not spark.active:
                continue

            spark.life -= dt
            if spark.life <= 0.0:
                spark.active = False
                continue

            spark.velocity = Vector2(
                spark.velocity.x * spark.drag,
                spark.velocity.y * spark.drag + spark.gravity * dt,
            )
            spark.position = spark.position + spark.velocity * dt

    def render(self, renderer: IRenderer, offset: Vector2 = Vector2.zero()) -> None:
        """Draw every live particle.

        Args:
            renderer: Target renderer.
            offset: Screen-space offset applied to every particle, so the
                sparks shake with the rest of the arena.
        """
        if self._native is not None:
            self._render_native(renderer, offset)
            return

        for spark in self._pool:
            if not spark.active:
                continue

            remaining = spark.life / spark.life_total if spark.life_total > 0 else 0.0
            color = Color(
                spark.color.r,
                spark.color.g,
                spark.color.b,
                int(spark.color.a * remaining),
            )
            position = spark.position + offset

            if spark.streak:
                tail = position - spark.velocity * 0.03
                renderer.draw_line(
                    tail, position, color, width=max(1, int(spark.radius))
                )
            else:
                renderer.draw_circle(position, spark.radius * remaining, color)

    def _render_native(self, renderer: IRenderer, offset: Vector2) -> None:
        """Draw the native pool, batched where the renderer can take it.

        This is the half of the port that pays. A spark is one primitive,
        so the Python pool makes one `draw_circle` or `draw_line` call per
        live spark and spends most of a busy frame in that call overhead
        rather than in arithmetic. A renderer that implements
        `ShapeBatchRenderer` instead receives two calls for the whole pool,
        with the primitives packed natively: measured 8-15x on the render
        half and 13-20x on the frame.

        A renderer that cannot batch gets one call per spark, as before --
        the ModernGL world renderer is the only backend where batching is
        free, and a software backend would be doing this loop internally
        anyway. The arithmetic is still native, which is the 1.9x that
        remains.

        Args:
            renderer: Target renderer, batched if it can be.
            offset: Screen-space offset applied to every spark.
        """
        assert self._native is not None

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

    def _acquire(self) -> _Spark | None:
        """Return the next free pool slot, or None when the pool is full."""
        start = self._next
        while True:
            spark = self._pool[self._next]
            self._next = (self._next + 1) % self._capacity
            if not spark.active:
                return spark
            if self._next == start:
                return None
