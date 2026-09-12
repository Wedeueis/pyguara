"""Coloured shape particles: sparks, embers, splashes, debris.

A pool of short-lived primitives drawn through `IRenderer.draw_circle` and
`draw_line` rather than as textured sprites.

`ParticleSystem` is the right tool when particles *are* sprites. These are
not, and the distinction is forced by the backend: under ModernGL the
sprite path carries no per-instance tint, so a textured particle can only
ever be white, while the shape path takes a colour per primitive and
batches each shape type into one instanced draw call anyway. Anything
whose whole point is its colour -- an ember, a blood spray, a rain splash
-- therefore goes through shapes.

Typical use, composed into a scene rather than resolved from DI::

    sparks = Sparks()
    sparks.burst(position, Color(255, 180, 60), count=14, streak=True)
    sparks.update(dt)
    sparks.render(renderer, offset=shake_offset)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import IRenderer


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

    def __init__(self, capacity: int = 320, rng: RandomStream | None = None) -> None:
        """Pre-allocate the pool.

        Args:
            capacity: Maximum particles alive at once. A burst that would
                exceed it drops the excess rather than growing, the same
                way `ParticleSystem` does.
            rng: Random stream driving spread and speed jitter.
        """
        self._pool = [_Spark() for _ in range(capacity)]
        self._next = 0
        self._rng = rng if rng is not None else RandomStream()

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

    def update(self, dt: float) -> None:
        """Integrate every live particle and retire the expired ones.

        Args:
            dt: Seconds since the last frame.
        """
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

    def _acquire(self) -> _Spark | None:
        """Return the next free pool slot, or None when the pool is full."""
        start = self._next
        while True:
            spark = self._pool[self._next]
            self._next = (self._next + 1) % len(self._pool)
            if not spark.active:
                return spark
            if self._next == start:
                return None
